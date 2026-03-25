"""StrategyGPT data API routes for the custom dashboard tabs."""

import logging
from typing import Any

from fastapi import APIRouter

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
async def get_calls(page: int = 1, limit: int = 20, outcome: str = ""):
    """Paginated call log with optional outcome filter."""
    db = get_database()
    col = db["strategygpt_calls"]

    query: dict = {}
    if outcome:
        query["outcome"] = outcome

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
