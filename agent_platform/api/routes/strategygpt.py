"""StrategyGPT data API routes for the custom dashboard tabs."""

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from agent_platform.db.client import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/strategygpt", tags=["strategygpt"])


def _ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def _err(msg: str) -> dict:
    return {"success": False, "data": None, "error": msg}


# -- Dashboard summary --------------------------------------------------------

@router.get("/summary")
async def get_summary():
    """Aggregate lead counts by status + call outcome stats."""
    db = get_database()
    leads = db["strategygpt_leads"]
    calls = db["strategygpt_calls"]

    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    status_counts: dict[str, int] = {}
    async for doc in leads.aggregate(pipeline):
        status_counts[doc["_id"] or "unknown"] = doc["count"]

    total = sum(status_counts.values())
    qualified = status_counts.get("qualified", 0)
    interested = status_counts.get("interested", 0)
    not_interested = status_counts.get("not_interested", 0)
    voicemail = status_counts.get("voicemail", 0)
    callback = status_counts.get("callback_requested", 0)
    no_answer = status_counts.get("no_answer", 0)
    invalid = status_counts.get("invalid", 0)
    new_leads = status_counts.get("new", 0)
    called = interested + not_interested + voicemail + callback + no_answer

    call_count = await calls.count_documents({})

    avg_duration_cursor = calls.aggregate([
        {"$group": {"_id": None, "avg": {"$avg": "$duration_seconds"}}}
    ])
    avg_duration = 0
    async for doc in avg_duration_cursor:
        avg_duration = doc.get("avg", 0) or 0

    city_pipeline = [
        {"$group": {"_id": "$city", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    cities = []
    async for doc in leads.aggregate(city_pipeline):
        if doc["_id"]:
            cities.append({"city": doc["_id"], "count": doc["count"]})

    category_pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    categories = []
    async for doc in leads.aggregate(category_pipeline):
        if doc["_id"]:
            categories.append({"category": doc["_id"], "count": doc["count"]})

    return _ok({
        "total_leads": total,
        "new": new_leads,
        "qualified": qualified,
        "invalid": invalid,
        "called": called,
        "interested": interested,
        "not_interested": not_interested,
        "voicemail": voicemail,
        "callback_requested": callback,
        "no_answer": no_answer,
        "total_calls": call_count,
        "avg_call_duration": round(avg_duration, 1),
        "conversion_rate": round(interested / called * 100, 1) if called else 0,
        "qualification_rate": round((qualified + called) / total * 100, 1) if total else 0,
        "cities": cities,
        "categories": categories,
        "status_counts": status_counts,
    })


# -- Leads (paginated) --------------------------------------------------------

@router.get("/leads")
async def get_leads(page: int = 1, limit: int = 20, status: str = ""):
    """Paginated lead list with optional status filter."""
    db = get_database()
    col = db["strategygpt_leads"]

    query: dict = {}
    if status:
        query["status"] = status

    total = await col.count_documents(query)
    skip = (page - 1) * limit

    cursor = col.find(query).sort("created_at", -1).skip(skip).limit(limit)
    results = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)

    return _ok({
        "leads": results,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, (total + limit - 1) // limit),
    })


# -- Calls (paginated) --------------------------------------------------------

@router.get("/calls")
async def get_calls(page: int = 1, limit: int = 20, outcome: str = "", is_test: str = ""):
    """Paginated call log with optional outcome and test filter."""
    db = get_database()
    col = db["strategygpt_calls"]

    query: dict = {}
    if outcome:
        query["outcome"] = outcome
    if is_test == "true":
        query["is_test"] = True
    elif is_test == "false":
        query["is_test"] = {"$ne": True}

    total = await col.count_documents(query)
    skip = (page - 1) * limit

    cursor = col.find(query).sort("called_at", -1).skip(skip).limit(limit)
    results = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)

    return _ok({
        "calls": results,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, (total + limit - 1) // limit),
    })


# -- Call outcome breakdown ----------------------------------------------------

@router.get("/call-stats")
async def get_call_stats():
    """Aggregate call outcomes."""
    db = get_database()
    col = db["strategygpt_calls"]

    pipeline = [
        {"$match": {"is_test": {"$ne": True}}},
        {"$group": {
            "_id": "$outcome",
            "count": {"$sum": 1},
            "avg_duration": {"$avg": "$duration_seconds"},
        }},
    ]
    results = []
    async for doc in col.aggregate(pipeline):
        results.append({
            "outcome": doc["_id"] or "unknown",
            "count": doc["count"],
            "avg_duration": round(doc.get("avg_duration", 0) or 0, 1),
        })

    return _ok(results)


# -- Test call -----------------------------------------------------------------

class TestCallRequest(BaseModel):
    phone: str
    business_name: str = "Test Business"
    script: str = ""


DEFAULT_TEST_SCRIPT = (
    "Hi there! This is a quick test call from StrategyGPT. "
    "We help small businesses get a professional website built within 24 hours, "
    "completely free, with zero commitment. If you love it, there's a small one-time fee. "
    "If not, no charge at all. Would you be interested in learning more? "
    "This is just a test — thanks for your time!"
)


@router.post("/test-call")
async def place_test_call(body: TestCallRequest):
    """Place a single test call to verify voice API connectivity and script quality."""
    import subprocess
    import json
    import os
    from pathlib import Path

    phone = body.phone.strip()
    if not phone:
        return _err("Phone number is required")

    script = body.script.strip() or DEFAULT_TEST_SCRIPT
    business_name = body.business_name.strip()

    db = get_database()

    agent = await db["agents"].find_one({"custom_tabs": {"$exists": True}, "root_folder": "strategygpt_agents"})
    if not agent:
        agents_list = await db["agents"].find({"custom_tabs": {"$exists": True}}).to_list(length=20)
        agent = next((a for a in agents_list if "strategygpt" in a.get("name", "").lower() or "website" in a.get("name", "").lower()), None)
        if not agent:
            return _err("StrategyGPT agent team not found in database")

    agent_id = agent["_id"]
    store_path = agent.get("upload_path", "")
    root_folder = agent.get("root_folder", "strategygpt_agents")
    team_dir = os.path.join(store_path, root_folder)
    venv_python = os.path.join(store_path, ".venv", "bin", "python")

    if not os.path.isfile(venv_python):
        return _err(f"Virtual environment not ready at {venv_python}")

    test_script_code = f'''
import sys, os, json
sys.path.insert(0, "{team_dir}")
os.chdir("{team_dir}")

from shared.logger import get_logger
from agent_voice_caller.tools.voice_tools import place_call

logger = get_logger("test_call")

phone = {json.dumps(phone)}
script = {json.dumps(script)}

logger.info("Placing test call to %s", phone)
try:
    result = place_call(phone=phone, script=script)
    print("CALL_RESULT:" + json.dumps(result))
except Exception as exc:
    print("CALL_ERROR:" + str(exc))
'''

    env = {**os.environ}

    # All settings from MongoDB — no .env files
    settings_doc = await db["team_settings"].find_one({"_id": agent_id})
    if settings_doc:
        if settings_doc.get("voice_provider"):
            env["VOICE_API_PROVIDER"] = settings_doc["voice_provider"]
        for k, v in settings_doc.get("integration_keys", {}).items():
            if k and v:
                env[k] = v
    if "MONGODB_URI" not in env:
        env["MONGODB_URI"] = "mongodb://localhost:27017"

    try:
        proc = subprocess.run(
            [venv_python, "-c", test_script_code],
            capture_output=True, text=True, timeout=60, env=env,
            cwd=team_dir,
        )
        stdout = proc.stdout
        stderr = proc.stderr

        if proc.returncode != 0:
            err_detail = stderr.strip()[-300:] if stderr else stdout.strip()[-300:]
            return _err(f"Subprocess failed (exit {proc.returncode}): {err_detail}")

        if "CALL_ERROR:" in stdout:
            error_msg = stdout.split("CALL_ERROR:")[1].strip()
            return _err(f"Voice API error: {error_msg}")

        call_result = {}
        if "CALL_RESULT:" in stdout:
            raw = stdout.split("CALL_RESULT:")[1].strip()
            call_result = json.loads(raw)
        else:
            return _err("No response from voice API. stdout: " + (stdout.strip()[-200:] or "(empty)"))

        call_id = call_result.get("call_id", "test_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))

        await db["strategygpt_calls"].insert_one({
            "place_id": "test",
            "call_id": call_id,
            "business_name": business_name,
            "phone": phone,
            "outcome": "test_pending",
            "duration_seconds": 0,
            "transcript_summary": f"Test call — script: {script[:100]}...",
            "called_at": datetime.now(timezone.utc),
            "is_test": True,
        })

        logger.info("Test call placed to %s — call_id=%s", phone, call_id)
        return _ok({
            "call_id": call_id,
            "phone": phone,
            "status": call_result.get("status", "initiated"),
            "message": f"Test call initiated to {phone}",
            "stdout": stdout[-500:] if stdout else "",
            "stderr": stderr[-500:] if stderr else "",
        })

    except subprocess.TimeoutExpired:
        return _err("Test call timed out after 60 seconds")
    except Exception as exc:
        logger.error("Test call failed: %s", exc)
        return _err(str(exc)[:500])


# -- Refresh pending test-call statuses from Bland.ai --------------------------

BLAND_BASE_URL = "https://api.bland.ai/v1"


async def _get_voice_api_key() -> str:
    """Retrieve the VOICE_API_KEY from team_settings."""
    db = get_database()
    agent = await db["agents"].find_one({"root_folder": "strategygpt_agents"})
    if not agent:
        return ""
    doc = await db["team_settings"].find_one({"_id": agent["_id"]})
    if not doc:
        return ""
    return (doc.get("integration_keys") or {}).get("VOICE_API_KEY", "")


def _map_bland_disposition(data: dict) -> tuple[str, bool]:
    """Map Bland.ai call data to a simplified outcome label.

    Returns (outcome, needs_llm) — needs_llm is True when the transcript
    should be sent to the LLM for classification.
    """
    status = (data.get("status") or "").lower()
    completed_bool = data.get("completed", False)
    queue = (data.get("queue_status") or "").lower()

    is_done = completed_bool or status == "completed" or queue == "complete"
    if not is_done:
        if queue == "queued":
            return "queued", False
        return "test_pending", False

    answered_by = data.get("answered_by")
    transcript = data.get("concatenated_transcript", "")
    has_user_speech = "user:" in (transcript or "").lower()

    if not answered_by and not has_user_speech:
        return "no_answer", False

    analysis = data.get("analysis") or {}
    disposition = (analysis.get("disposition") or "").lower()
    if disposition in ("interested", "not_interested", "voicemail", "callback_requested", "no_answer"):
        return disposition, False

    return "needs_llm", True


CLASSIFY_PROMPT = (
    "You are a call outcome classifier. Read the phone call transcript below "
    "and reply with EXACTLY one word — the call outcome.\n\n"
    "Possible outcomes:\n"
    "- interested  (the person wants to learn more or said yes)\n"
    "- not_interested  (the person declined, said no, or hung up)\n"
    "- voicemail  (reached voicemail / answering machine)\n"
    "- callback_requested  (asked to be called back later)\n"
    "- no_answer  (nobody answered or line was dead)\n\n"
    "Reply with ONLY the single outcome word, nothing else.\n\n"
    "TRANSCRIPT:\n"
)

_LLM_ENDPOINTS = {
    "claude": "https://api.anthropic.com/v1/messages",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
}


async def _classify_with_llm(transcript: str, settings: dict) -> str | None:
    """Ask the configured LLM to classify a call transcript."""
    provider = (settings.get("llm_provider") or "").lower()
    model = settings.get("llm_model") or ""
    api_keys = settings.get("api_keys") or {}
    api_key = api_keys.get(provider, "")

    if not api_key or not provider:
        return None

    prompt_text = CLASSIFY_PROMPT + transcript[:2000]

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            if provider == "claude":
                classify_model = "claude-3-haiku-20240307" if "claude" in model else model
                resp = await client.post(
                    _LLM_ENDPOINTS["claude"],
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": classify_model,
                        "max_tokens": 20,
                        "messages": [{"role": "user", "content": prompt_text}],
                    },
                )
                resp.raise_for_status()
                text = resp.json()["content"][0]["text"].strip().lower()

            elif provider == "gemini":
                url = _LLM_ENDPOINTS["gemini"].format(model=model)
                resp = await client.post(
                    f"{url}?key={api_key}",
                    json={
                        "contents": [{"parts": [{"text": prompt_text}]}],
                        "generationConfig": {"maxOutputTokens": 20},
                    },
                )
                resp.raise_for_status()
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip().lower()

            else:
                endpoint = _LLM_ENDPOINTS.get(provider)
                if not endpoint:
                    return None
                resp = await client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 20,
                        "messages": [{"role": "user", "content": prompt_text}],
                    },
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"].strip().lower()

        valid = {"interested", "not_interested", "voicemail", "callback_requested", "no_answer"}
        return text if text in valid else None

    except Exception as exc:
        logger.warning("LLM classification failed (%s): %s", provider, exc)
        return None


@router.post("/refresh-test-calls")
async def refresh_test_calls():
    """Poll Bland.ai for any test calls still in 'test_pending' and update their status."""
    db = get_database()
    col = db["strategygpt_calls"]

    pending = await col.find({"is_test": True, "outcome": "test_pending"}).to_list(length=50)
    if not pending:
        return _ok({"refreshed": 0})

    api_key = await _get_voice_api_key()
    if not api_key:
        return _err("VOICE_API_KEY not configured — cannot poll Bland.ai")

    refreshed = 0

    stale_ids = [c["_id"] for c in pending if (c.get("call_id", "")).startswith("test_")]
    if stale_ids:
        await col.update_many(
            {"_id": {"$in": stale_ids}},
            {"$set": {"outcome": "expired", "updated_at": datetime.now(timezone.utc)}},
        )
        refreshed += len(stale_ids)

    agent = await db["agents"].find_one({"root_folder": "strategygpt_agents"})
    settings_doc = await db["team_settings"].find_one({"_id": agent["_id"]}) if agent else None

    async with httpx.AsyncClient(timeout=15) as client:
        for call in pending:
            call_id = call.get("call_id", "")
            if not call_id or call_id.startswith("test_"):
                continue
            try:
                resp = await client.get(
                    f"{BLAND_BASE_URL}/calls/{call_id}",
                    headers={"Authorization": api_key},
                )
                if resp.status_code != 200:
                    logger.warning("Bland.ai status check %s returned %s", call_id, resp.status_code)
                    continue
                data = resp.json()
                outcome, needs_llm = _map_bland_disposition(data)
                if outcome == "test_pending":
                    continue
                if outcome == "queued":
                    called_at = call.get("called_at")
                    if called_at and (datetime.now(timezone.utc) - called_at).total_seconds() > 300:
                        outcome = "failed"
                    else:
                        continue

                transcript = data.get("concatenated_transcript", "")
                if needs_llm and transcript and settings_doc:
                    llm_result = await _classify_with_llm(transcript, settings_doc)
                    if llm_result:
                        outcome = llm_result

                raw_dur = data.get("corrected_duration") or (data.get("call_length", 0) or 0) * 60
                duration = float(raw_dur) if raw_dur else 0.0
                update: dict[str, Any] = {
                    "outcome": outcome,
                    "duration_seconds": duration,
                    "updated_at": datetime.now(timezone.utc),
                }
                if transcript:
                    update["transcript_summary"] = transcript[:500]
                await col.update_one({"_id": call["_id"]}, {"$set": update})
                refreshed += 1
            except Exception as exc:
                logger.warning("Failed to refresh test call %s: %s", call_id, exc)

    return _ok({"refreshed": refreshed})


@router.delete("/test-calls")
async def delete_all_test_calls():
    """Remove every test call from the strategygpt_calls collection."""
    db = get_database()
    result = await db["strategygpt_calls"].delete_many({"is_test": True})
    return _ok({"deleted": result.deleted_count})
