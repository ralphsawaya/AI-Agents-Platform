"""Dual-mode orchestrator: Search pipeline and Reserve pipeline.

Search Pipeline (parallel fan-out/fan-in):
    parse_query -> [flight_search, hotel_search, car_search] -> aggregate -> END

Reserve Pipeline:
    create_reservation -> END
"""

import random
import string
import threading
from datetime import datetime, timezone

from langgraph.graph import StateGraph, START, END

from orchestrator.state import TripSearchState, TripReserveState
from agent_flight.agent import build_flight_graph
from agent_hotel.agent import build_hotel_graph
from agent_car.agent import build_car_graph
from shared.atlas import get_reservations, get_chat_persistence, get_search_progress
from shared.query_parser import parse_query_filters
from shared.memory import learn_from_thread, load_preferences, format_preferences_for_prompt
from shared.prompt_loader import load_prompt
from shared.config import AGENT_ID
from shared.logger import get_logger

logger = get_logger("orchestrator.graph")

def _publish_partial(thread_id: str, category: str, results: list):
    """Write partial search results to Atlas so the UI can stream them."""
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


# -- Search Pipeline Nodes ----------------------------------------------------

def parse_query(state: dict) -> dict:
    """Classify intent + extract structured filters from the query."""
    query = state.get("query", "")
    chat_history = state.get("chat_history", [])
    logger.info("Orchestrator: parsing query (%d chars, %d history msgs)", len(query), len(chat_history))

    prefs = load_preferences(AGENT_ID)
    prefs_text = format_preferences_for_prompt(prefs)
    if prefs_text:
        logger.info("Injecting %d long-term preferences into query parser", len(prefs))

    parsed = parse_query_filters(query, chat_history=chat_history, user_prefs=prefs_text)
    is_search = parsed.get("is_search", False)

    if not is_search:
        reply = parsed.get("reply", "I'm a trip booking assistant. Tell me where you'd like to travel!")
        logger.info("Not a search request — replying: %s", reply[:120])
        return {
            "is_search": False,
            "nonsearch_reply": reply,
            "flight_filters": {}, "hotel_filters": {}, "car_filters": {},
        }

    logger.info("Search request — filters — flight: %s | hotel: %s | car: %s",
                parsed.get("flight", {}), parsed.get("hotel", {}), parsed.get("car", {}))

    thread_id = state.get("thread_id", "")
    if thread_id:
        try:
            get_search_progress().update_one(
                {"_id": thread_id},
                {"$set": {"flights": None, "hotels": None, "cars": None, "done": False,
                           "started_at": datetime.now(timezone.utc)}},
                upsert=True,
            )
        except Exception:
            pass

    return {
        "is_search": True,
        "nonsearch_reply": "",
        "flight_filters": parsed.get("flight", {}),
        "hotel_filters": parsed.get("hotel", {}),
        "car_filters": parsed.get("car", {}),
    }


def run_flight_search(state: dict) -> dict:
    if not state.get("is_search", False):
        return {"flight_results": []}
    logger.info("Orchestrator: running Flight Search agent")
    result = build_flight_graph().invoke({
        "query": state["query"], "query_embedding": [],
        "filters": state.get("flight_filters", {}),
        "results": [], "status": "pending",
    })
    results = result.get("results", [])
    _publish_partial(state.get("thread_id", ""), "flights", results)
    return {"flight_results": results}


def run_hotel_search(state: dict) -> dict:
    if not state.get("is_search", False):
        return {"hotel_results": []}
    logger.info("Orchestrator: running Hotel Search agent")
    result = build_hotel_graph().invoke({
        "query": state["query"], "query_embedding": [],
        "filters": state.get("hotel_filters", {}),
        "results": [], "status": "pending",
    })
    results = result.get("results", [])
    _publish_partial(state.get("thread_id", ""), "hotels", results)
    return {"hotel_results": results}


def run_car_search(state: dict) -> dict:
    if not state.get("is_search", False):
        return {"car_results": []}
    logger.info("Orchestrator: running Car Rental Search agent")
    result = build_car_graph().invoke({
        "query": state["query"], "query_embedding": [],
        "filters": state.get("car_filters", {}),
        "results": [], "status": "pending",
    })
    results = result.get("results", [])
    _publish_partial(state.get("thread_id", ""), "cars", results)
    return {"car_results": results}


def aggregate_results(state: dict) -> dict:
    """Save final combined message, mark progress as done, and learn preferences."""
    thread_id = state.get("thread_id", "")

    if not state.get("is_search", False):
        reply = state.get("nonsearch_reply", "I'm a trip booking assistant. Tell me where you'd like to travel!")
        logger.info("Orchestrator: non-search — saving reply to thread")
        if thread_id:
            _save_text_reply(thread_id, reply)
            _learn_from_thread_safe(thread_id, state)
        return {}

    flights = state.get("flight_results", [])
    hotels = state.get("hotel_results", [])
    cars = state.get("car_results", [])

    logger.info("Orchestrator: aggregating — %d flights, %d hotels, %d cars",
                len(flights), len(hotels), len(cars))

    search_results = {"flights": flights, "hotels": hotels, "cars": cars}
    if thread_id:
        _save_assistant_message(thread_id, state.get("query", ""), search_results)
        try:
            get_search_progress().update_one(
                {"_id": thread_id}, {"$set": {"done": True}},
            )
        except Exception:
            pass
        _learn_from_thread_safe(thread_id, state)

    return {}


def _learn_from_thread_safe(thread_id: str, state: dict):
    """Extract and persist user preferences in a background thread."""
    chat_history = list(state.get("chat_history", []))
    query = state.get("query", "")
    if query:
        chat_history = chat_history + [{"role": "user", "content": query}]
    if not chat_history:
        return

    def _run():
        try:
            learn_from_thread(AGENT_ID, chat_history)
        except Exception as exc:
            logger.warning("Long-term memory extraction failed (non-fatal): %s", exc)

    threading.Thread(target=_run, daemon=True).start()


def _save_text_reply(thread_id: str, text: str):
    """Save a plain text assistant message (no search results)."""
    try:
        col = get_chat_persistence()
        now = datetime.now(timezone.utc)
        col.update_one(
            {"_id": thread_id},
            {"$push": {"messages": {
                "role": "assistant", "content": text, "timestamp": now.isoformat(),
            }}, "$set": {"updated_at": now}},
        )
        logger.info("Saved text reply to thread %s", thread_id)
    except Exception as exc:
        logger.error("Failed to save text reply: %s", exc)


def _generate_search_summary(query: str, search_results: dict) -> str:
    """Use the LLM to write a natural, conversational summary of search results."""
    try:
        from shared.llm import get_llm
        llm = get_llm()

        flights = search_results.get("flights", [])
        hotels = search_results.get("hotels", [])
        cars = search_results.get("cars", [])

        brief = []
        for f in flights[:3]:
            brief.append(f"Flight: {f.get('airline','')} {f.get('flight_number','')}, "
                         f"{f.get('origin_city','')}→{f.get('destination_city','')}, "
                         f"{f.get('travel_class','')}, EUR{f.get('price_eur',0):.0f}")
        for h in hotels[:3]:
            brief.append(f"Hotel: {h.get('name','')}, {h.get('stars',0)}★, "
                         f"{h.get('city','')}, EUR{h.get('price_per_night_eur',0):.0f}/night")
        for c in cars[:3]:
            brief.append(f"Car: {c.get('color','')} {c.get('make','')} {c.get('model','')}, "
                         f"{c.get('category','')}, EUR{c.get('price_per_day_eur',0):.0f}/day")

        prefs = load_preferences(AGENT_ID)
        prefs_section = ""
        if prefs:
            prefs_section = ("\n\nUser's known preferences:\n"
                + "\n".join(f"- {p.get('fact','')}" for p in prefs)
                + "\nMention if any result matches a known preference.")

        prompt = load_prompt(
            "search_summary",
            query=query,
            results_brief="\n".join(brief),
            prefs_section=prefs_section,
        )
        return llm.invoke(prompt).strip().strip('"')
    except Exception as exc:
        logger.warning("LLM summary failed, using fallback: %s", exc)
        parts = []
        if search_results.get("flights"):
            parts.append(f"{len(search_results['flights'])} flights")
        if search_results.get("hotels"):
            parts.append(f"{len(search_results['hotels'])} hotels")
        if search_results.get("cars"):
            parts.append(f"{len(search_results['cars'])} car rentals")
        return ("I found " + ", ".join(parts) + " for you.") if parts else \
               "I couldn't find any results matching your criteria. Try adjusting your search."


def _save_assistant_message(thread_id: str, query: str, search_results: dict):
    try:
        col = get_chat_persistence()
        now = datetime.now(timezone.utc)
        content = _generate_search_summary(query, search_results)

        col.update_one(
            {"_id": thread_id},
            {"$push": {"messages": {
                "role": "assistant", "content": content,
                "timestamp": now.isoformat(), "search_results": search_results,
            }}, "$set": {"updated_at": now}},
        )
        logger.info("Saved assistant message to thread %s", thread_id)
    except Exception as exc:
        logger.error("Failed to save assistant message: %s", exc)


# -- Reserve Pipeline Nodes ---------------------------------------------------

def _generate_reservation_id(dt: datetime) -> str:
    """Generate a human-readable reservation ID like TRIP-20260412-K7X3."""
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

    hotel_nights = 1
    if trip_dates.get("start") and trip_dates.get("end"):
        try:
            start = datetime.fromisoformat(trip_dates["start"])
            end = datetime.fromisoformat(trip_dates["end"])
            hotel_nights = max((end - start).days, 1)
        except (ValueError, TypeError):
            pass

    total = 0.0
    if flight:
        total += flight.get("price_eur", 0)
    if hotel:
        total += hotel.get("price_per_night_eur", 0) * hotel_nights
    if car:
        total += car.get("price_per_day_eur", 0) * hotel_nights

    now = datetime.now(timezone.utc)
    res_id = _generate_reservation_id(now)
    reservation = {
        "_id": res_id,
        "traveler_name": "John Doe",
        "trip_dates": trip_dates, "total_cost_eur": round(total, 2),
        "status": "confirmed", "thread_id": thread_id,
        "agent_id": AGENT_ID, "created_at": now,
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
        parts.append(f"flight ({flight.get('airline','')} {flight.get('flight_number','')})")
    if hotel:
        parts.append(f"hotel ({hotel.get('name','')})")
    if car:
        parts.append(f"car ({car.get('make','')} {car.get('model','')})")
    booked_text = ", ".join(parts)

    if thread_id:
        try:
            get_chat_persistence().update_one(
                {"_id": thread_id},
                {"$push": {"messages": {
                    "role": "assistant",
                    "content": f"Your reservation has been confirmed! Booked: {booked_text}. Total cost: EUR{total:.2f}.",
                    "timestamp": now.isoformat(), "reservation": reservation,
                }}, "$set": {"updated_at": now}},
            )
        except Exception as exc:
            logger.error("Failed to save reservation message: %s", exc)

    return {"reservation": reservation, "status": "complete"}


# -- Graph Builders -----------------------------------------------------------

def build_search_graph():
    """Parallel fan-out: START -> parse_query -> [flight, hotel, car] -> aggregate -> END"""
    graph = StateGraph(TripSearchState)
    graph.add_node("parse_query", parse_query)
    graph.add_node("flight_search", run_flight_search)
    graph.add_node("hotel_search", run_hotel_search)
    graph.add_node("car_search", run_car_search)
    graph.add_node("aggregate", aggregate_results)

    graph.add_edge(START, "parse_query")
    graph.add_edge("parse_query", "flight_search")
    graph.add_edge("parse_query", "hotel_search")
    graph.add_edge("parse_query", "car_search")
    graph.add_edge("flight_search", "aggregate")
    graph.add_edge("hotel_search", "aggregate")
    graph.add_edge("car_search", "aggregate")
    graph.add_edge("aggregate", END)
    return graph.compile()


def build_reserve_graph():
    """create_reservation -> END"""
    graph = StateGraph(TripReserveState)
    graph.add_node("create_reservation", create_reservation)
    graph.set_entry_point("create_reservation")
    graph.add_edge("create_reservation", END)
    return graph.compile()
