"""StrategyGPT data API routes for the custom dashboard tabs."""

import logging
from datetime import datetime, timezone
from typing import Any

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
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "{team_dir}")
os.chdir("{team_dir}")

from shared.logger import get_logger
from agent_voice_caller.tools.voice_tools import place_call, get_call_status

logger = get_logger("test_call")

phone = {json.dumps(phone)}
script = {json.dumps(script)}

logger.info("Placing test call to %s", phone)
try:
    result = place_call(phone=phone, script=script)
    print("CALL_RESULT:" + __import__("json").dumps(result))
except Exception as exc:
    print("CALL_ERROR:" + str(exc))
'''

    env = {**os.environ}
    env_file = os.path.join(team_dir, ".env")
    if os.path.isfile(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()

    try:
        proc = subprocess.run(
            [venv_python, "-c", test_script_code],
            capture_output=True, text=True, timeout=60, env=env,
            cwd=team_dir,
        )
        stdout = proc.stdout
        stderr = proc.stderr

        if "CALL_ERROR:" in stdout:
            error_msg = stdout.split("CALL_ERROR:")[1].strip()
            return _err(f"Voice API error: {error_msg}")

        call_result = {}
        if "CALL_RESULT:" in stdout:
            raw = stdout.split("CALL_RESULT:")[1].strip()
            call_result = json.loads(raw)

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
