"""Orchestrator entry point for the trip agent team.

Supports multiple modes via AGENT_ARGS:
  - mode=search (or prompt field): Parallel search pipeline
  - mode=chat: Search pipeline with chat thread persistence
  - mode=reserve: Creates a reservation from selected options
  - mode=cancel: Cancels (deletes) an existing reservation by ID
  - mode=modify: Targeted search to replace one item in a reservation
  - mode=update: Applies a selected replacement to an existing reservation
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.utils import load_args
from orchestrator.graph import build_search_graph, build_reserve_graph

logger = get_logger("orchestrator")


def main():
    args = load_args()
    mode = args.get("mode", "search")

    logger.info("=" * 60)
    logger.info("Trip Orchestrator — mode: %s", mode)
    logger.info("=" * 60)

    if mode in ("search", "chat"):
        return run_search(args)
    elif mode == "reserve":
        return run_reserve(args)
    elif mode == "cancel":
        return run_cancel(args)
    elif mode == "modify":
        return run_modify(args)
    elif mode == "update":
        return run_update(args)
    else:
        logger.error("Unknown mode: %s", mode)
        return None


def run_search(args: dict):
    query = args.get("prompt") or args.get("message", "")
    thread_id = args.get("thread_id", "")
    chat_history = args.get("chat_history", [])

    if not query:
        logger.error("No search query provided")
        print(json.dumps({"error": "No search query provided"}))
        return None

    logger.info("Query: %s", query[:200])
    result = build_search_graph().invoke({
        "query": query, "thread_id": thread_id,
        "chat_history": chat_history,
        "is_search": True, "nonsearch_reply": "",
        "flight_filters": {}, "hotel_filters": {}, "car_filters": {},
        "flight_results": [], "hotel_results": [], "car_results": [],
        "error": "",
    })

    if not result.get("is_search", True):
        reply = result.get("nonsearch_reply", "")
        logger.info("Non-search reply: %s", reply[:200])
        output = {"status": "complete", "reply": reply, "thread_id": thread_id}
        print(f"\n__RESULT_JSON__:{json.dumps(output)}")
        return result

    flights = result.get("flight_results", [])
    hotels = result.get("hotel_results", [])
    cars = result.get("car_results", [])

    logger.info("=" * 60)
    logger.info("Search complete! Flights: %d | Hotels: %d | Cars: %d",
                len(flights), len(hotels), len(cars))
    logger.info("=" * 60)

    print("\n--- SEARCH RESULTS ---")
    print(f"Flights found: {len(flights)}")
    for i, f in enumerate(flights):
        print(f"  {i+1}. {f.get('airline','')} {f.get('flight_number','')} — EUR{f.get('price_eur',0)}")
    print(f"Hotels found: {len(hotels)}")
    for i, h in enumerate(hotels):
        print(f"  {i+1}. {h.get('name','')} — {h.get('stars',0)}* — EUR{h.get('price_per_night_eur',0)}/night")
    print(f"Cars found: {len(cars)}")
    for i, c in enumerate(cars):
        print(f"  {i+1}. {c.get('color','')} {c.get('make','')} {c.get('model','')} — EUR{c.get('price_per_day_eur',0)}/day")

    output = {"status": "complete", "flights": flights, "hotels": hotels,
              "cars": cars, "thread_id": thread_id}
    print(f"\n__RESULT_JSON__:{json.dumps(output)}")
    return result


def run_reserve(args: dict):
    thread_id = args.get("thread_id", "")
    selected_flight = args.get("selected_flight", {})
    selected_hotel = args.get("selected_hotel", {})
    selected_car = args.get("selected_car", {})
    trip_dates = args.get("trip_dates", {})

    if not any([selected_flight, selected_hotel, selected_car]):
        logger.error("No selection provided — at least one of flight, hotel, or car is required")
        print(json.dumps({"error": "No selection provided"}))
        return None

    logger.info("Creating reservation for thread: %s", thread_id)
    result = build_reserve_graph().invoke({
        "thread_id": thread_id,
        "selected_flight": selected_flight, "selected_hotel": selected_hotel,
        "selected_car": selected_car, "trip_dates": trip_dates,
        "reservation": {}, "status": "pending",
    })

    reservation = result.get("reservation", {})
    logger.info("=" * 60)
    logger.info("Reservation complete! Total: EUR%.2f", reservation.get("total_cost_eur", 0))
    logger.info("=" * 60)

    print("\n--- RESERVATION CONFIRMED ---")
    print(f"Traveler: {reservation.get('traveler_name', 'N/A')}")
    print(f"Total Cost: EUR{reservation.get('total_cost_eur', 0):.2f}")
    print(f"Status: {reservation.get('status', 'N/A')}")

    output = {"status": "complete", "reservation": reservation}
    print(f"\n__RESULT_JSON__:{json.dumps(output, default=str)}")
    return result


def run_cancel(args: dict):
    from datetime import datetime, timezone
    from shared.atlas import get_reservations, get_chat_persistence

    reservation_id = args.get("reservation_id", "")
    thread_id = args.get("thread_id", "")

    if not reservation_id:
        logger.error("No reservation_id provided for cancellation")
        output = {"status": "error", "error": "No reservation ID provided"}
        print(f"\n__RESULT_JSON__:{json.dumps(output)}")
        return None

    logger.info("Cancelling reservation: %s", reservation_id)

    try:
        col = get_reservations()
        existing = col.find_one({"_id": reservation_id})
        if not existing:
            msg = f"Reservation {reservation_id} was not found. It may have already been deleted."
            logger.warning(msg)
            _save_cancel_message(thread_id, reservation_id, success=False, detail=msg)
            output = {"status": "not_found", "reservation_id": reservation_id, "message": msg}
            print(f"\n__RESULT_JSON__:{json.dumps(output)}")
            return None

        result = col.delete_one({"_id": reservation_id})
        if result.deleted_count > 0:
            msg = f"Reservation {reservation_id} has been successfully cancelled."
            logger.info(msg)
            _save_cancel_message(thread_id, reservation_id, success=True, detail=msg)
            output = {"status": "complete", "reservation_id": reservation_id, "message": msg}
        else:
            msg = f"Could not delete reservation {reservation_id}. Please try again."
            logger.error(msg)
            _save_cancel_message(thread_id, reservation_id, success=False, detail=msg)
            output = {"status": "error", "reservation_id": reservation_id, "message": msg}

        print(f"\n__RESULT_JSON__:{json.dumps(output)}")
        return output

    except Exception as exc:
        msg = f"Failed to cancel reservation {reservation_id}: {exc}"
        logger.error(msg)
        _save_cancel_message(thread_id, reservation_id, success=False, detail=msg)
        output = {"status": "error", "error": str(exc)}
        print(f"\n__RESULT_JSON__:{json.dumps(output)}")
        return None


def _save_cancel_message(thread_id: str, reservation_id: str, success: bool, detail: str):
    if not thread_id:
        return
    try:
        from datetime import datetime, timezone
        from shared.atlas import get_chat_persistence

        col = get_chat_persistence()
        now = datetime.now(timezone.utc)
        col.update_one(
            {"_id": thread_id},
            {"$push": {"messages": {
                "role": "assistant",
                "content": detail,
                "timestamp": now.isoformat(),
                "cancellation": {
                    "reservation_id": reservation_id,
                    "success": success,
                },
            }}, "$set": {"updated_at": now}},
        )
    except Exception as exc:
        logger.error("Failed to save cancellation message: %s", exc)


def run_modify(args: dict):
    """Search for replacement options for one category in an existing reservation.

    Uses the same sub-agent graphs as the main search pipeline instead of
    duplicating vector-search logic.
    """
    from datetime import datetime, timezone
    from shared.atlas import get_reservations
    from shared.llm import get_llm
    from shared.prompt_loader import load_prompt
    from shared.query_parser import _clean_flight_filters, _clean_hotel_filters, _clean_car_filters
    from shared.atlas import get_search_progress
    from agent_flight.agent import build_flight_graph
    from agent_hotel.agent import build_hotel_graph
    from agent_car.agent import build_car_graph
    import re as _re

    reservation_id = args.get("reservation_id", "")
    thread_id = args.get("thread_id", "")
    message = args.get("message", "")

    if not reservation_id:
        _save_chat_msg(thread_id, "I need a reservation ID to modify. Please include it in your message.")
        output = {"status": "error", "error": "No reservation ID"}
        print(f"\n__RESULT_JSON__:{json.dumps(output)}")
        return None

    res_col = get_reservations()
    reservation = res_col.find_one({"_id": reservation_id})
    if not reservation:
        _save_chat_msg(thread_id, f"Reservation {reservation_id} was not found.")
        output = {"status": "not_found", "reservation_id": reservation_id}
        print(f"\n__RESULT_JSON__:{json.dumps(output)}")
        return None

    category = ""
    raw_filters = {}

    try:
        llm = get_llm()
        prompt = load_prompt(
            "modify_parser",
            reservation_id=reservation_id,
            message=message,
            flight_summary=json.dumps(reservation.get("flight", {}), default=str)[:200],
            hotel_summary=json.dumps(reservation.get("hotel", {}), default=str)[:200],
            car_summary=json.dumps(reservation.get("car", {}), default=str)[:200],
        )
        raw = llm.invoke(prompt)
        match = _re.search(r'\{.*\}', raw, _re.DOTALL)
        parsed = json.loads(match.group()) if match else {}
        category = parsed.get("category", "").lower()
        raw_filters = parsed.get("filters", {})
    except Exception as exc:
        logger.warning("LLM modify parse failed: %s", exc)

    if category not in ("flight", "hotel", "car"):
        _save_chat_msg(thread_id,
            "I couldn't determine which part of your reservation you'd like to change. "
            "Please specify if you want to change the flight, hotel, or car.")
        output = {"status": "error", "error": "Could not determine category"}
        print(f"\n__RESULT_JSON__:{json.dumps(output)}")
        return None

    if category == "flight":
        filters = _clean_flight_filters(raw_filters)
        if not filters.get("origin_city") and reservation.get("flight", {}).get("origin_city"):
            filters["origin_city"] = reservation["flight"]["origin_city"]
        if not filters.get("destination_city") and reservation.get("flight", {}).get("destination_city"):
            filters["destination_city"] = reservation["flight"]["destination_city"]
    elif category == "hotel":
        filters = _clean_hotel_filters(raw_filters)
        if not filters.get("city") and reservation.get("hotel", {}).get("city"):
            filters["city"] = reservation["hotel"]["city"]
    else:
        filters = _clean_car_filters(raw_filters)
        if not filters.get("pickup_city") and reservation.get("car", {}).get("pickup_city"):
            filters["pickup_city"] = reservation["car"]["pickup_city"]

    logger.info("Modify search — category: %s, filters: %s", category, filters)

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

    graph_builders = {
        "flight": build_flight_graph,
        "hotel": build_hotel_graph,
        "car": build_car_graph,
    }

    try:
        graph = graph_builders[category]()
        result = graph.invoke({
            "query": message, "query_embedding": [],
            "filters": filters,
            "results": [], "status": "pending",
        })
        results = result.get("results", [])
        logger.info("Modify search found %d %s results (filters: %s)", len(results), category, filters)

        if not results and filters:
            logger.info("No results with strict filters, retrying with relaxed filters")
            relaxed = {k: v for k, v in filters.items()
                       if k not in ("pickup_city", "origin_city", "destination_city", "city")}
            if relaxed != filters:
                result = graph.invoke({
                    "query": message, "query_embedding": [],
                    "filters": relaxed,
                    "results": [], "status": "pending",
                })
                results = result.get("results", [])
                logger.info("Relaxed search found %d %s results", len(results), category)
    except Exception as exc:
        logger.error("Modify search failed: %s", exc)
        results = []

    progress_key = {"flight": "flights", "hotel": "hotels", "car": "cars"}[category]
    if thread_id:
        try:
            get_search_progress().update_one(
                {"_id": thread_id},
                {"$set": {progress_key: results, "done": True}},
            )
        except Exception:
            pass

    current_item = reservation.get(category, {})
    current_desc = _item_desc(category, current_item)

    if results:
        summary = (f"Here are some alternative {category} options to replace "
                   f"**{current_desc}** in reservation {reservation_id}. "
                   f"Select one and click 'Update Reservation' to apply the change.")
    else:
        summary = (f"I searched for alternative {category} options to replace "
                   f"**{current_desc}** in reservation {reservation_id}, "
                   f"but couldn't find any matches. Try describing what you're looking for "
                   f"differently, or with fewer constraints.")
    _save_chat_msg(thread_id, summary, modify_results={
        "reservation_id": reservation_id,
        "category": category,
        "results": results,
    })

    output = {"status": "complete", "mode": "modify", "reservation_id": reservation_id,
              "category": category, "results": results, "thread_id": thread_id}
    print(f"\n__RESULT_JSON__:{json.dumps(output, default=str)}")
    return output


def run_update(args: dict):
    """Apply a selected replacement to an existing reservation."""
    from datetime import datetime, timezone
    from shared.atlas import get_reservations, get_chat_persistence

    reservation_id = args.get("reservation_id", "")
    category = args.get("category", "")
    selected_item = args.get("selected_item", {})
    thread_id = args.get("thread_id", "")

    if not reservation_id or not category or not selected_item:
        _save_chat_msg(thread_id, "Missing information for the update. Please try again.")
        output = {"status": "error", "error": "Missing parameters"}
        print(f"\n__RESULT_JSON__:{json.dumps(output)}")
        return None

    try:
        res_col = get_reservations()
        reservation = res_col.find_one({"_id": reservation_id})
        if not reservation:
            _save_chat_msg(thread_id, f"Reservation {reservation_id} was not found.")
            output = {"status": "not_found"}
            print(f"\n__RESULT_JSON__:{json.dumps(output)}")
            return None

        old_item = reservation.get(category, {})
        trip_dates = reservation.get("trip_dates", {})
        hotel_nights = 1
        if trip_dates.get("start") and trip_dates.get("end"):
            try:
                start = datetime.fromisoformat(trip_dates["start"])
                end = datetime.fromisoformat(trip_dates["end"])
                hotel_nights = max((end - start).days, 1)
            except (ValueError, TypeError):
                pass

        update_fields = {category: selected_item}

        total = 0.0
        for cat in ("flight", "hotel", "car"):
            item = selected_item if cat == category else reservation.get(cat, {})
            if not item:
                continue
            if cat == "flight":
                total += item.get("price_eur", 0)
            elif cat == "hotel":
                total += item.get("price_per_night_eur", 0) * hotel_nights
            else:
                total += item.get("price_per_day_eur", 0) * hotel_nights
        update_fields["total_cost_eur"] = round(total, 2)

        res_col.update_one({"_id": reservation_id}, {"$set": update_fields})
        logger.info("Updated %s in reservation %s, new total: EUR%.2f",
                     category, reservation_id, total)

        old_desc = _item_desc(category, old_item)
        new_desc = _item_desc(category, selected_item)
        msg = (f"Reservation {reservation_id} updated! "
               f"Changed {category}: {old_desc} → {new_desc}. "
               f"New total: EUR{total:.2f}.")

        if thread_id:
            now = datetime.now(timezone.utc)
            get_chat_persistence().update_one(
                {"_id": thread_id},
                {"$push": {"messages": {
                    "role": "assistant", "content": msg,
                    "timestamp": now.isoformat(),
                    "reservation_update": {
                        "reservation_id": reservation_id,
                        "category": category, "success": True,
                    },
                }}, "$set": {"updated_at": now}},
            )

        output = {"status": "complete", "reservation_id": reservation_id, "message": msg}
        print(f"\n__RESULT_JSON__:{json.dumps(output, default=str)}")
        return output

    except Exception as exc:
        logger.error("Update failed: %s", exc)
        _save_chat_msg(thread_id, f"Failed to update reservation: {exc}")
        output = {"status": "error", "error": str(exc)}
        print(f"\n__RESULT_JSON__:{json.dumps(output)}")
        return None


def _item_desc(category: str, item: dict) -> str:
    if not item:
        return "none"
    if category == "flight":
        return f"{item.get('airline','')} {item.get('flight_number','')}"
    elif category == "hotel":
        return f"{item.get('name','')} ({item.get('stars',0)}★)"
    else:
        return f"{item.get('color','')} {item.get('make','')} {item.get('model','')}"


def _save_chat_msg(thread_id: str, content: str, modify_results: dict | None = None):
    if not thread_id:
        return
    try:
        from datetime import datetime, timezone
        from shared.atlas import get_chat_persistence

        col = get_chat_persistence()
        now = datetime.now(timezone.utc)
        msg = {"role": "assistant", "content": content, "timestamp": now.isoformat()}
        if modify_results:
            msg["modify_results"] = modify_results
        col.update_one(
            {"_id": thread_id},
            {"$push": {"messages": msg}, "$set": {"updated_at": now}},
        )
    except Exception as exc:
        logger.error("Failed to save chat message: %s", exc)


if __name__ == "__main__":
    main()
