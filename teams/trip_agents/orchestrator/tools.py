"""Tool registry for the Plan-and-Execute trip agent.

Plain Python functions invoked from JSON plans — not LangChain @tool decorators.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from agent_car.agent import build_car_graph
from agent_flight.agent import build_flight_graph
from agent_hotel.agent import build_hotel_graph
from shared.atlas import get_reservations, get_search_progress, reservation_filter
from shared.config import AGENT_ID
from shared.logger import get_logger
from shared.memory import load_preferences
from shared.filters import _clean_car_filters, _clean_flight_filters, _clean_hotel_filters

logger = get_logger("orchestrator.tools")

_SEARCH_TOOL_TO_CATEGORY = {
    "search_flights": "flights",
    "search_hotels": "hotels",
    "search_cars": "cars",
}

# Compiled once — avoid re-building LangGraph on every tool call.
_FLIGHT_GRAPH = build_flight_graph()
_HOTEL_GRAPH = build_hotel_graph()
_CAR_GRAPH = build_car_graph()

_GRAPH_BY_BUILDER: dict[Callable, Any] = {
    build_flight_graph: _FLIGHT_GRAPH,
    build_hotel_graph: _HOTEL_GRAPH,
    build_car_graph: _CAR_GRAPH,
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
    graph = _GRAPH_BY_BUILDER.get(build_graph)
    if graph is None:
        graph = build_graph()
        _GRAPH_BY_BUILDER[build_graph] = graph
    result = graph.invoke({
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
    doc = get_reservations().find_one(reservation_filter(res_id))
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
                "done": False,
                "phase": "searching",
                "started_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )
    except Exception as exc:
        logger.warning("Failed to reset search progress for %s: %s", thread_id, exc)


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
    except Exception as exc:
        logger.warning("Failed to set planned categories for %s: %s", thread_id, exc)


def mark_search_progress_synthesizing(thread_id: str):
    """Signal UI that searches finished and the agent is building a recommendation."""
    if not thread_id:
        return
    try:
        get_search_progress().update_one(
            {"_id": thread_id},
            {"$set": {"phase": "synthesizing", "done": False}},
            upsert=True,
        )
    except Exception as exc:
        logger.warning("Failed to mark synthesizing for %s: %s", thread_id, exc)


def mark_search_progress_done(thread_id: str):
    if not thread_id:
        return
    try:
        get_search_progress().update_one(
            {"_id": thread_id},
            {"$set": {"done": True, "phase": "done"}},
        )
    except Exception as exc:
        logger.warning("Failed to mark search progress done for %s: %s", thread_id, exc)


def _run_single_tool(
    call: dict,
    ctx: ToolContext,
) -> tuple[dict, dict[str, list], dict]:
    """Execute one planned tool. Returns (tool_result, search_slice, trace_entry)."""
    name = call.get("tool", "")
    args = call.get("args") or {}
    if not isinstance(args, dict):
        args = {}

    fn = TOOL_REGISTRY.get(name)
    if not fn:
        logger.warning("Unknown tool in plan: %s", name)
        tr = {"tool": name, "args": args, "results": [], "error": "unknown_tool", "count": 0}
        trace = {"tool": name, "args": args, "result_count": 0, "error": "unknown_tool"}
        return tr, {}, trace

    try:
        logger.info("Executing tool: %s args=%s", name, args)
        results = fn(ctx, args)
        search_slice: dict[str, list] = {}
        if name in _SEARCH_TOOL_TO_CATEGORY:
            category = _SEARCH_TOOL_TO_CATEGORY[name]
            search_slice[category] = results if isinstance(results, list) else []
        count = len(results) if isinstance(results, list) else (1 if results else 0)
        tr = {"tool": name, "args": args, "results": results, "count": count}
        trace = {"tool": name, "args": args, "result_count": count}
        return tr, search_slice, trace
    except Exception as exc:
        logger.error("Tool %s failed: %s", name, exc)
        tr = {"tool": name, "args": args, "results": [], "error": str(exc), "count": 0}
        trace = {"tool": name, "args": args, "result_count": 0, "error": str(exc)}
        return tr, {}, trace


def execute_tool_calls(tool_calls: list[dict], ctx: ToolContext) -> tuple[list[dict], dict, list[dict]]:
    """Run planned tools. Independent search tools run in parallel."""
    tool_results: list[dict] = []
    search_results: dict[str, list] = {"flights": [], "hotels": [], "cars": []}
    tool_trace: list[dict] = []

    search_calls = [c for c in tool_calls if c.get("tool") in _SEARCH_TOOL_TO_CATEGORY]
    other_calls = [c for c in tool_calls if c.get("tool") not in _SEARCH_TOOL_TO_CATEGORY]

    ordered_results: list[tuple[dict, dict[str, list], dict]] = []

    for call in other_calls:
        ordered_results.append(_run_single_tool(call, ctx))

    if len(search_calls) <= 1:
        for call in search_calls:
            ordered_results.append(_run_single_tool(call, ctx))
    else:
        with ThreadPoolExecutor(max_workers=min(len(search_calls), 3)) as pool:
            futures = {pool.submit(_run_single_tool, call, ctx): call for call in search_calls}
            for future in as_completed(futures):
                ordered_results.append(future.result())

    for tr, search_slice, trace in ordered_results:
        tool_results.append(tr)
        tool_trace.append(trace)
        for key, items in search_slice.items():
            search_results[key] = items

    return tool_results, search_results, tool_trace
