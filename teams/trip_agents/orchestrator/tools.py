"""Tool registry for the Plan-and-Execute trip agent.

Plain Python functions invoked from JSON plans — not LangChain @tool decorators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from agent_car.agent import build_car_graph
from agent_flight.agent import build_flight_graph
from agent_hotel.agent import build_hotel_graph
from shared.atlas import get_reservations, get_search_progress
from shared.config import AGENT_ID
from shared.logger import get_logger
from shared.memory import load_preferences
from shared.query_parser import _clean_car_filters, _clean_flight_filters, _clean_hotel_filters

logger = get_logger("orchestrator.tools")

_SEARCH_TOOL_TO_CATEGORY = {
    "search_flights": "flights",
    "search_hotels": "hotels",
    "search_cars": "cars",
}


@dataclass
class ToolContext:
    query: str
    thread_id: str = ""
    reservation_id: str = ""
    reservation: dict = field(default_factory=dict)


def _publish_partial(thread_id: str, category: str, results: list):
    if not thread_id:
        return
    try:
        get_search_progress().update_one(
            {"_id": thread_id},
            {"$set": {category: results, f"{category}_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        logger.info("Published %d %s results for thread %s", len(results), category, thread_id)
    except Exception as exc:
        logger.warning("Failed to publish partial %s: %s", category, exc)


def _run_search_graph(build_graph: Callable, filters: dict, query: str) -> list[dict]:
    result = build_graph().invoke({
        "query": query,
        "query_embedding": [],
        "filters": filters,
        "results": [],
        "status": "pending",
    })
    return result.get("results", [])


def search_flights(ctx: ToolContext, args: dict) -> list[dict]:
    filters = _clean_flight_filters(args)
    results = _run_search_graph(build_flight_graph, filters, ctx.query)
    _publish_partial(ctx.thread_id, "flights", results)
    return results


def search_hotels(ctx: ToolContext, args: dict) -> list[dict]:
    filters = _clean_hotel_filters(args)
    results = _run_search_graph(build_hotel_graph, filters, ctx.query)
    _publish_partial(ctx.thread_id, "hotels", results)
    return results


def search_cars(ctx: ToolContext, args: dict) -> list[dict]:
    filters = _clean_car_filters(args)
    results = _run_search_graph(build_car_graph, filters, ctx.query)
    _publish_partial(ctx.thread_id, "cars", results)
    return results


def get_user_preferences(_ctx: ToolContext, _args: dict) -> list[dict]:
    return load_preferences(AGENT_ID)


def get_reservation(ctx: ToolContext, args: dict) -> dict:
    res_id = args.get("reservation_id") or ctx.reservation_id
    if not res_id:
        return {}
    doc = get_reservations().find_one({"_id": res_id})
    return doc or {}


TOOL_REGISTRY: dict[str, Callable[[ToolContext, dict], Any]] = {
    "search_flights": search_flights,
    "search_hotels": search_hotels,
    "search_cars": search_cars,
    "get_user_preferences": get_user_preferences,
    "get_reservation": get_reservation,
}


def reset_search_progress(thread_id: str):
    if not thread_id:
        return
    try:
        get_search_progress().update_one(
            {"_id": thread_id},
            {"$set": {
                "flights": None, "hotels": None, "cars": None,
                "categories": [],
                "done": False, "started_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )
    except Exception:
        pass


def set_planned_categories(thread_id: str, tool_calls: list[dict]):
    """Record which search categories the agent plan will run (for UI progress)."""
    if not thread_id:
        return
    categories: list[str] = []
    for call in tool_calls:
        cat = _SEARCH_TOOL_TO_CATEGORY.get(call.get("tool", ""))
        if cat and cat not in categories:
            categories.append(cat)
    if not categories:
        return
    try:
        get_search_progress().update_one(
            {"_id": thread_id},
            {"$set": {"categories": categories}},
            upsert=True,
        )
    except Exception:
        pass


def mark_search_progress_done(thread_id: str):
    if not thread_id:
        return
    try:
        get_search_progress().update_one({"_id": thread_id}, {"$set": {"done": True}})
    except Exception:
        pass


def execute_tool_calls(tool_calls: list[dict], ctx: ToolContext) -> tuple[list[dict], dict, list[dict]]:
    """Run planned tools sequentially. Returns (tool_results, search_results, tool_trace)."""
    tool_results: list[dict] = []
    search_results: dict[str, list] = {"flights": [], "hotels": [], "cars": []}
    tool_trace: list[dict] = []

    for call in tool_calls:
        name = call.get("tool", "")
        args = call.get("args") or {}
        if not isinstance(args, dict):
            args = {}

        fn = TOOL_REGISTRY.get(name)
        if not fn:
            logger.warning("Unknown tool in plan: %s", name)
            tool_results.append({"tool": name, "args": args, "results": [], "error": "unknown_tool"})
            tool_trace.append({"tool": name, "args": args, "result_count": 0, "error": "unknown_tool"})
            continue

        try:
            logger.info("Executing tool: %s args=%s", name, args)
            results = fn(ctx, args)
            if name in _SEARCH_TOOL_TO_CATEGORY:
                category = _SEARCH_TOOL_TO_CATEGORY[name]
                search_results[category] = results if isinstance(results, list) else []
            count = len(results) if isinstance(results, list) else (1 if results else 0)
            tool_results.append({"tool": name, "args": args, "results": results, "count": count})
            tool_trace.append({"tool": name, "args": args, "result_count": count})
        except Exception as exc:
            logger.error("Tool %s failed: %s", name, exc)
            tool_results.append({"tool": name, "args": args, "results": [], "error": str(exc)})
            tool_trace.append({"tool": name, "args": args, "result_count": 0, "error": str(exc)})

    return tool_results, search_results, tool_trace
