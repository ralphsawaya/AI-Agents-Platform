"""Plan-and-Execute orchestrator + reserve pipeline.

Agent graph:
    plan -> execute -> (replan | synthesize) -> END

Reserve graph:
    create_reservation -> END
"""

from __future__ import annotations

import json
import random
import string
import threading
from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from orchestrator.state import TripAgentState, TripReserveState
from orchestrator.tools import (
    ToolContext,
    execute_tool_calls,
    mark_search_progress_done,
    reset_search_progress,
    set_planned_categories,
)
from shared.atlas import get_chat_persistence, get_reservations
from shared.config import AGENT_ID
from shared.llm import get_llm
from shared.memory import format_preferences_for_prompt, learn_from_thread, load_preferences
from shared.prompt_loader import load_prompt_raw
from shared.json_utils import extract_json
from shared.utils import hotel_nights_from_trip_dates
from shared.logger import get_logger

logger = get_logger("orchestrator.graph")

MAX_REPLAN = 2
_SEARCH_TOOLS = {"search_flights", "search_hotels", "search_cars"}
_TOOL_TO_MODIFY_CATEGORY = {
    "search_flights": "flight",
    "search_hotels": "hotel",
    "search_cars": "car",
}


def _build_history_prompt(query: str, chat_history: list, extra: str = "") -> str:
    parts = []
    if extra:
        parts.append(extra)
        parts.append("")
    if chat_history:
        parts.append("Conversation so far:")
        for msg in chat_history[-8:]:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            if len(content) > 400:
                content = content[:400] + "..."
            parts.append(f"  {role}: {content}")
        parts.append("")
    parts.append(f'Latest user message: "{query}"')
    parts.append("")
    parts.append("Return JSON only:")
    return "\n".join(parts)


def _tool_context(state: dict) -> ToolContext:
    return ToolContext(
        query=state.get("query", ""),
        thread_id=state.get("thread_id", ""),
        reservation_id=state.get("reservation_id", ""),
        reservation=state.get("reservation") or {},
    )


def _merge_search_results(existing: dict, new: dict) -> dict:
    merged = {"flights": [], "hotels": [], "cars": []}
    for key in merged:
        prev = (existing or {}).get(key) or []
        curr = (new or {}).get(key) or []
        merged[key] = curr if curr else prev
    return merged


# -- Plan-and-Execute nodes ---------------------------------------------------

def plan_node(state: dict) -> dict:
    query = state.get("query", "")
    chat_history = state.get("chat_history", [])
    mode = state.get("mode", "chat")
    replan_count = state.get("replan_count", 0)
    tool_results = state.get("tool_results", [])

    logger.info("Plan node — mode=%s replan=%d", mode, replan_count)

    if state.get("thread_id") and replan_count == 0:
        reset_search_progress(state["thread_id"])

    prefs = load_preferences(AGENT_ID)
    prefs_text = format_preferences_for_prompt(prefs)
    system = load_prompt_raw("trip_planner_plan")
    if prefs_text:
        system = system + "\n\n" + prefs_text

    extra = ""
    if mode == "modify":
        reservation = state.get("reservation") or {}
        extra = (
            f"MODIFY MODE: User wants to change one item in reservation "
            f"{state.get('reservation_id', '')}.\n"
            f"Current reservation summary: {json.dumps(reservation, default=str)[:800]}\n"
            f"Search only the category the user wants to replace."
        )
    elif replan_count > 0 and tool_results:
        extra = (
            "REPLAN: Previous tool calls returned empty or poor results.\n"
            f"Previous results: {json.dumps(tool_results, default=str)[:2000]}\n"
            "Return intent 'replan' with adjusted tool_calls."
        )

    try:
        llm = get_llm()
        raw = llm.invoke(_build_history_prompt(query, chat_history, extra), system=system)
        plan = extract_json(raw)
    except Exception as exc:
        logger.error("Plan LLM failed: %s", exc)
        return {
            "intent": "chat",
            "reply": "I'm having trouble processing that right now. Please try again.",
            "plan": {},
            "tool_results": [],
        }

    if not isinstance(plan, dict):
        plan = {}

    intent = plan.get("intent", "chat")
    if intent not in ("chat", "search", "replan"):
        intent = "search" if plan.get("tool_calls") else "chat"

    reply = plan.get("reply") or ""
    tool_calls = plan.get("tool_calls") or []
    if not isinstance(tool_calls, list):
        tool_calls = []

    if intent in ("search", "replan") and not tool_calls:
        intent = "chat"
        reply = reply or "Could you tell me more about where you'd like to travel?"

    logger.info("Plan intent=%s tools=%s", intent, [c.get("tool") for c in tool_calls])

    modify_category = state.get("modify_category", "")
    if mode == "modify" and not modify_category:
        for call in tool_calls:
            cat = _TOOL_TO_MODIFY_CATEGORY.get(call.get("tool", ""))
            if cat:
                modify_category = cat
                break

    return {
        "plan": plan,
        "intent": intent,
        "reply": reply,
        "modify_category": modify_category,
    }


def execute_tools_node(state: dict) -> dict:
    plan = state.get("plan") or {}
    tool_calls = plan.get("tool_calls") or []
    ctx = _tool_context(state)

    set_planned_categories(state.get("thread_id", ""), tool_calls)
    tool_results, search_results, tool_trace = execute_tool_calls(tool_calls, ctx)
    merged = _merge_search_results(state.get("search_results") or {}, search_results)

    prev_trace = list(state.get("tool_trace") or [])
    return {
        "tool_results": tool_results,
        "search_results": merged,
        "tool_trace": prev_trace + tool_trace,
    }


def synthesize_node(state: dict) -> dict:
    query = state.get("query", "")
    search_results = state.get("search_results") or {"flights": [], "hotels": [], "cars": []}
    tool_results = state.get("tool_results") or []
    mode = state.get("mode", "chat")

    prefs = load_preferences(AGENT_ID)
    prefs_text = format_preferences_for_prompt(prefs)

    system = load_prompt_raw("trip_planner_synthesize")
    if prefs_text:
        system = system + "\n\nUser preferences:\n" + prefs_text

    payload = {
        "user_query": query,
        "search_results": search_results,
        "tool_results_summary": [
            {"tool": tr.get("tool"), "count": tr.get("count", 0)}
            for tr in tool_results
        ],
    }

    if mode == "modify":
        payload["modify_mode"] = True
        payload["reservation_id"] = state.get("reservation_id", "")
        payload["category"] = state.get("modify_category", "")

    prompt = (
        f"User request: {query}\n\n"
        f"Data:\n{json.dumps(payload, default=str)[:6000]}\n\n"
        "Return JSON only."
    )

    reply = ""
    proposed_bundle = None
    final_search_results = search_results

    try:
        llm = get_llm()
        raw = llm.invoke(prompt, system=system)
        parsed = extract_json(raw)
        if isinstance(parsed, dict) and parsed:
            reply = parsed.get("content") or ""
            proposed_bundle = parsed.get("proposed_bundle")
    except Exception as exc:
        logger.warning("Synthesize LLM failed: %s", exc)

    if not proposed_bundle and any(final_search_results.get(k) for k in ("flights", "hotels", "cars")):
        flights = final_search_results.get("flights") or []
        hotels = final_search_results.get("hotels") or []
        cars = final_search_results.get("cars") or []
        reservation = state.get("reservation") or {}
        nights = hotel_nights_from_trip_dates(reservation.get("trip_dates"))
        total = 0.0
        if flights:
            total += flights[0].get("price_eur", 0)
        if hotels:
            total += hotels[0].get("price_per_night_eur", 0) * nights
        if cars:
            total += cars[0].get("price_per_day_eur", 0) * nights
        proposed_bundle = {
            "flight": flights[0] if flights else None,
            "hotel": hotels[0] if hotels else None,
            "car": cars[0] if cars else None,
            "rationale": "Top matches from your search.",
            "total_cost_eur": round(total, 2),
        }

    if not reply:
        parts = []
        if final_search_results.get("flights"):
            parts.append(f"{len(final_search_results['flights'])} flights")
        if final_search_results.get("hotels"):
            parts.append(f"{len(final_search_results['hotels'])} hotels")
        if final_search_results.get("cars"):
            parts.append(f"{len(final_search_results['cars'])} cars")
        reply = ("I found " + ", ".join(parts) + ". Review the options and confirm when ready.") if parts else \
            "I couldn't find matching options. Try different criteria."

    thread_id = state.get("thread_id", "")
    if thread_id:
        mark_search_progress_done(thread_id)

    return {
        "reply": reply,
        "search_results": final_search_results,
        "proposed_bundle": proposed_bundle,
    }


def persist_and_learn(state: dict) -> dict:
    """Save assistant message and trigger background memory extraction."""
    thread_id = state.get("thread_id", "")
    if not thread_id:
        return {}

    intent = state.get("intent", "chat")
    reply = state.get("reply", "")
    search_results = state.get("search_results")
    proposed_bundle = state.get("proposed_bundle")
    tool_trace = state.get("tool_trace") or []
    mode = state.get("mode", "chat")

    try:
        col = get_chat_persistence()
        now = datetime.now(timezone.utc)
        msg: dict = {
            "role": "assistant",
            "content": reply,
            "timestamp": now.isoformat(),
        }

        if intent in ("search", "replan") and search_results:
            msg["search_results"] = search_results
        if proposed_bundle and mode != "modify":
            msg["proposed_bundle"] = proposed_bundle
        if tool_trace:
            msg["tool_trace"] = tool_trace
        if mode == "modify" and state.get("reservation_id"):
            cat = state.get("modify_category", "")
            cat_map = {"flight": "flights", "hotel": "hotels", "car": "cars"}
            results = (search_results or {}).get(cat_map.get(cat, ""), [])
            if not results:
                for c, key in cat_map.items():
                    if (search_results or {}).get(key):
                        cat = c
                        results = search_results[key]
                        break
            if results:
                msg["modify_results"] = {
                    "reservation_id": state.get("reservation_id"),
                    "category": cat,
                    "results": results,
                }

        col.update_one(
            {"_id": thread_id},
            {"$push": {"messages": msg}, "$set": {"updated_at": now}},
        )
        logger.info("Saved assistant message to thread %s", thread_id)
    except Exception as exc:
        logger.error("Failed to persist message: %s", exc)

    chat_history = list(state.get("chat_history", []))
    query = state.get("query", "")
    if query:
        chat_history = chat_history + [{"role": "user", "content": query}]
    if reply:
        chat_history = chat_history + [{"role": "assistant", "content": reply}]

    def _run():
        try:
            learn_from_thread(AGENT_ID, chat_history)
        except Exception as exc:
            logger.warning("Memory extraction failed: %s", exc)

    if chat_history:
        threading.Thread(target=_run, daemon=True).start()

    return {}


def route_after_plan(state: dict) -> str:
    if state.get("intent") == "chat":
        return "persist"
    return "execute"


def route_after_execute(state: dict) -> str:
    replan_count = state.get("replan_count", 0)
    tool_results = state.get("tool_results") or []

    search_invoked = [tr for tr in tool_results if tr.get("tool") in _SEARCH_TOOLS]
    empty_search = bool(search_invoked) and all(tr.get("count", 0) == 0 for tr in search_invoked)

    if empty_search and replan_count < MAX_REPLAN:
        logger.info("Empty search results — replanning (%d/%d)", replan_count + 1, MAX_REPLAN)
        return "replan"

    return "synthesize"


def replan_bump(state: dict) -> dict:
    return {"replan_count": state.get("replan_count", 0) + 1}


# -- Reserve pipeline (unchanged) ---------------------------------------------

def _generate_reservation_id(dt: datetime) -> str:
    date_part = dt.strftime("%Y%m%d")
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"TRIP-{date_part}-{suffix}"


def create_reservation(state: dict) -> dict:
    logger.info("Orchestrator: creating reservation")
    flight = state.get("selected_flight", {})
    hotel = state.get("selected_hotel", {})
    car = state.get("selected_car", {})
    trip_dates = state.get("trip_dates", {})
    thread_id = state.get("thread_id", "")

    hotel_nights = hotel_nights_from_trip_dates(trip_dates, default=1)

    total = 0.0
    if flight:
        total += flight.get("price_eur", 0)
    if hotel:
        total += hotel.get("price_per_night_eur", 0) * hotel_nights
    if car:
        total += car.get("price_per_day_eur", 0) * hotel_nights

    now = datetime.now(timezone.utc)
    res_id = _generate_reservation_id(now)
    traveler_name = (state.get("traveler_name") or "").strip() or "Guest"
    reservation = {
        "_id": res_id,
        "traveler_name": traveler_name,
        "trip_dates": trip_dates,
        "total_cost_eur": round(total, 2),
        "status": "confirmed",
        "thread_id": thread_id,
        "agent_id": AGENT_ID,
        "created_at": now,
    }
    if flight:
        reservation["flight"] = flight
    if hotel:
        reservation["hotel"] = hotel
    if car:
        reservation["car"] = car

    try:
        get_reservations().insert_one(reservation)
        logger.info("Reservation created: %s (total: EUR%.2f)", res_id, total)
    except Exception as exc:
        logger.error("Failed to create reservation: %s", exc)
        return {"reservation": {}, "status": "error"}

    parts = []
    if flight:
        parts.append(f"flight ({flight.get('airline', '')} {flight.get('flight_number', '')})")
    if hotel:
        parts.append(f"hotel ({hotel.get('name', '')})")
    if car:
        parts.append(f"car ({car.get('make', '')} {car.get('model', '')})")
    booked_text = ", ".join(parts)

    if thread_id:
        try:
            get_chat_persistence().update_one(
                {"_id": thread_id},
                {"$push": {"messages": {
                    "role": "assistant",
                    "content": (
                        f"Your reservation has been confirmed! Booked: {booked_text}. "
                        f"Total cost: EUR{total:.2f}."
                    ),
                    "timestamp": now.isoformat(),
                    "reservation": reservation,
                }}, "$set": {"updated_at": now}},
            )
        except Exception as exc:
            logger.error("Failed to save reservation message: %s", exc)

    return {"reservation": reservation, "status": "complete"}


# -- Graph builders -----------------------------------------------------------

_AGENT_GRAPH = None
_RESERVE_GRAPH = None


def build_agent_graph():
    """Plan -> execute -> (replan loop) -> synthesize -> persist."""
    global _AGENT_GRAPH
    if _AGENT_GRAPH is not None:
        return _AGENT_GRAPH

    graph = StateGraph(TripAgentState)
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_tools_node)
    graph.add_node("replan_bump", replan_bump)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("persist", persist_and_learn)

    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", route_after_plan, {
        "execute": "execute",
        "persist": "persist",
    })
    graph.add_conditional_edges("execute", route_after_execute, {
        "replan": "replan_bump",
        "synthesize": "synthesize",
    })
    graph.add_edge("replan_bump", "plan")
    graph.add_edge("synthesize", "persist")
    graph.add_edge("persist", END)
    _AGENT_GRAPH = graph.compile()
    return _AGENT_GRAPH


def build_search_graph():
    """Backward-compatible alias for the agent graph."""
    return build_agent_graph()


def build_reserve_graph():
    global _RESERVE_GRAPH
    if _RESERVE_GRAPH is not None:
        return _RESERVE_GRAPH

    graph = StateGraph(TripReserveState)
    graph.add_node("create_reservation", create_reservation)
    graph.set_entry_point("create_reservation")
    graph.add_edge("create_reservation", END)
    _RESERVE_GRAPH = graph.compile()
    return _RESERVE_GRAPH


def _initial_agent_state(
    query: str,
    thread_id: str = "",
    chat_history: list | None = None,
    mode: str = "chat",
    reservation_id: str = "",
    reservation: dict | None = None,
    modify_category: str = "",
) -> dict:
    return {
        "query": query,
        "thread_id": thread_id,
        "chat_history": chat_history or [],
        "mode": mode,
        "reservation_id": reservation_id,
        "reservation": reservation or {},
        "plan": {},
        "intent": "",
        "reply": "",
        "tool_results": [],
        "search_results": {"flights": [], "hotels": [], "cars": []},
        "proposed_bundle": None,
        "tool_trace": [],
        "replan_count": 0,
        "modify_category": modify_category,
        "error": "",
    }
