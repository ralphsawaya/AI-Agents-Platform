"""Poll call results and record final outcomes in MongoDB."""

import time
from datetime import datetime, timezone

from shared.logger import get_logger
from shared.mongo import get_leads_collection, get_calls_collection
from agent_voice_caller.tools.voice_tools import get_call_status

logger = get_logger("voice_caller.record_outcomes")

MAX_POLL_ATTEMPTS = 12
POLL_INTERVAL_SECONDS = 10


def record_outcomes(state: dict) -> dict:
    if state.get("status") in ("error", "no_leads"):
        return state

    call_results = state.get("call_results", [])
    if not call_results:
        return {"status": "no_calls"}

    leads_col = get_leads_collection()
    calls_col = get_calls_collection()

    interested = 0
    not_interested = 0
    no_answer = 0

    for entry in call_results:
        call_id = entry.get("call_id", "")
        place_id = entry.get("place_id", "")

        if not call_id or entry.get("status") == "call_failed":
            no_answer += 1
            continue

        outcome = _poll_call_outcome(call_id)

        lead_status = _map_outcome_to_status(outcome.get("disposition", "no_answer"))
        if lead_status == "interested":
            interested += 1
        elif lead_status == "not_interested":
            not_interested += 1
        else:
            no_answer += 1

        leads_col.update_one(
            {"place_id": place_id},
            {"$set": {"status": lead_status}},
        )

        calls_col.insert_one({
            "place_id": place_id,
            "call_id": call_id,
            "business_name": entry.get("business_name", ""),
            "phone": entry.get("phone", ""),
            "outcome": lead_status,
            "duration_seconds": outcome.get("duration", 0),
            "transcript_summary": outcome.get("transcript", ""),
            "called_at": datetime.now(timezone.utc),
        })

    logger.info(
        "Outcomes recorded: interested=%d, not_interested=%d, no_answer=%d",
        interested, not_interested, no_answer,
    )

    return {
        "interested_count": interested,
        "not_interested_count": not_interested,
        "no_answer_count": no_answer,
        "status": "outcomes_recorded",
    }


def _poll_call_outcome(call_id: str) -> dict:
    """Poll the voice API for a call's final result."""
    for attempt in range(MAX_POLL_ATTEMPTS):
        try:
            result = get_call_status(call_id)
            if result.get("completed", False):
                return result
        except Exception as exc:
            logger.warning("Poll attempt %d for call %s failed: %s", attempt + 1, call_id, exc)

        time.sleep(POLL_INTERVAL_SECONDS)

    logger.warning("Call %s did not complete within polling window", call_id)
    return {"disposition": "no_answer", "duration": 0, "transcript": ""}


def _map_outcome_to_status(disposition: str) -> str:
    """Map a voice API disposition string to a lead status."""
    mapping = {
        "interested": "interested",
        "yes": "interested",
        "not_interested": "not_interested",
        "no": "not_interested",
        "voicemail": "voicemail",
        "callback": "callback_requested",
        "callback_requested": "callback_requested",
        "no_answer": "no_answer",
        "busy": "no_answer",
        "failed": "no_answer",
    }
    return mapping.get(disposition.lower(), "no_answer")
