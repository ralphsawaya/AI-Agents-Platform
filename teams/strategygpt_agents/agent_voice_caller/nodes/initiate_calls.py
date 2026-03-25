"""Initiate AI voice calls to each qualified lead via the configured voice API."""

import time

from shared.logger import get_logger
from shared.config import VOICE_API_KEY, VOICE_API_PROVIDER, MAX_CONCURRENT_CALLS
from shared.mongo import get_leads_collection
from agent_voice_caller.tools.voice_tools import place_call

logger = get_logger("voice_caller.initiate_calls")


def initiate_calls(state: dict) -> dict:
    if state.get("status") in ("error", "no_leads"):
        return state

    leads = state.get("leads_to_call", [])
    if not leads:
        return {"status": "no_leads"}

    if not VOICE_API_KEY:
        logger.error("VOICE_API_KEY is not set — cannot place calls")
        return {"status": "error"}

    col = get_leads_collection()
    call_results = []

    for i, lead in enumerate(leads):
        logger.info(
            "[%d/%d] Calling %s at %s",
            i + 1, len(leads), lead["business_name"], lead["phone"],
        )

        try:
            result = place_call(
                phone=lead["phone"],
                script=lead.get("call_script", ""),
                provider=VOICE_API_PROVIDER,
            )
            call_results.append({
                "place_id": lead["place_id"],
                "business_name": lead["business_name"],
                "phone": lead["phone"],
                "call_id": result.get("call_id", ""),
                "status": "call_placed",
            })
            col.update_one(
                {"place_id": lead["place_id"]},
                {"$set": {"status": "called"}},
            )
        except Exception as exc:
            logger.error("Call failed for %s: %s", lead["business_name"], exc)
            call_results.append({
                "place_id": lead["place_id"],
                "business_name": lead["business_name"],
                "phone": lead["phone"],
                "call_id": "",
                "status": "call_failed",
                "error": str(exc),
            })

        if (i + 1) % MAX_CONCURRENT_CALLS == 0:
            logger.info("Rate limit pause — waiting 5s")
            time.sleep(5)

    logger.info("Initiated %d calls", len(call_results))
    return {"call_results": call_results, "status": "calls_initiated"}
