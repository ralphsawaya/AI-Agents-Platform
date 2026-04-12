"""Trip Planner data API routes for the custom dashboard tab.

Manages chat thread persistence (local MongoDB) and exposes reservation
data from Atlas MongoDB for display in the Trip Planner UI.
Includes a seed endpoint that populates Atlas with sample trip data.
"""

import json
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import certifi
import requests as http_requests
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

from agent_platform.core.executor import execute_agent
from agent_platform.db.client import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trip", tags=["trip"])

MAX_THREADS = 5
DOCS_PER_COLLECTION = 1000
_CANCEL_WORDS = re.compile(r'\b(cancel|delete|remove|revoke|annul)\b', re.IGNORECASE)
_RESERVATION_ID_RE = re.compile(r'TRIP-\d{8}-[A-Z0-9]{4}')
VOYAGE_BATCH_SIZE = 96
VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-3-lite"
EMBED_DIM = 512

_atlas_client: MongoClient | None = None


def _ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def _err(msg: str) -> dict:
    return {"success": False, "data": None, "error": msg}


async def _get_atlas_uri(agent_id: str) -> str:
    db = get_database()
    doc = await db["team_settings"].find_one({"_id": agent_id})
    if doc:
        uri = (doc.get("integration_keys") or {}).get("ATLAS_MONGODB_URI", "")
        if uri:
            return uri
    return os.getenv("ATLAS_MONGODB_URI", "")


async def _get_voyage_key(agent_id: str) -> str:
    db = get_database()
    doc = await db["team_settings"].find_one({"_id": agent_id})
    if doc:
        key = (doc.get("integration_keys") or {}).get("VOYAGE_AI_API_KEY", "")
        if key:
            return key
    return os.getenv("VOYAGE_AI_API_KEY", "")


def _get_atlas_db(uri: str):
    global _atlas_client
    if not uri:
        return None
    if _atlas_client is None:
        _atlas_client = MongoClient(uri, tlsCAFile=certifi.where())
    return _atlas_client.get_default_database(default="trip_data")


# -- Chat Threads (stored on Atlas trip_data.trip_chatPersistence) -------------

class CreateThreadBody(BaseModel):
    title: str = "New Trip"


class SendMessageBody(BaseModel):
    message: str
    agent_id: str | None = None


def _get_chat_col(atlas_db):
    return atlas_db["trip_chatPersistence"]


@router.get("/{agent_id}/threads")
async def list_threads(agent_id: str):
    try:
        uri = await _get_atlas_uri(agent_id)
        atlas_db = _get_atlas_db(uri)
        if atlas_db is None:
            return _ok([])
        col = _get_chat_col(atlas_db)
        docs = list(col.find({"agent_id": agent_id}).sort("updated_at", -1).limit(MAX_THREADS))
        threads = [{
            "id": doc["_id"],
            "title": doc.get("title", "Untitled"),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
            "message_count": len(doc.get("messages", [])),
        } for doc in docs]
        return _ok(threads)
    except Exception as exc:
        logger.exception("list_threads error: %s", exc)
        return _ok([])


@router.post("/{agent_id}/threads")
async def create_thread(agent_id: str, body: CreateThreadBody | None = None):
    uri = await _get_atlas_uri(agent_id)
    atlas_db = _get_atlas_db(uri)
    if atlas_db is None:
        return _err("Atlas not configured")
    col = _get_chat_col(atlas_db)

    count = col.count_documents({"agent_id": agent_id})
    if count >= MAX_THREADS:
        oldest = list(col.find({"agent_id": agent_id}).sort("created_at", 1).limit(1))
        if oldest:
            col.delete_one({"_id": oldest[0]["_id"]})

    now = datetime.now(timezone.utc)
    thread_id = str(uuid4())
    doc = {
        "_id": thread_id,
        "agent_id": agent_id,
        "title": (body.title if body else "New Trip"),
        "messages": [],
        "created_at": now,
        "updated_at": now,
    }
    col.insert_one(doc)
    return _ok({"id": thread_id, "title": doc["title"]})


@router.get("/{agent_id}/threads/{thread_id}")
async def get_thread(agent_id: str, thread_id: str):
    uri = await _get_atlas_uri(agent_id)
    atlas_db = _get_atlas_db(uri)
    if atlas_db is None:
        return _err("Atlas not configured")
    doc = _get_chat_col(atlas_db).find_one({"_id": thread_id, "agent_id": agent_id})
    if not doc:
        return _err("Thread not found")
    doc["id"] = doc.pop("_id")
    return _ok(doc)


@router.delete("/{agent_id}/threads/{thread_id}")
async def delete_thread(agent_id: str, thread_id: str):
    uri = await _get_atlas_uri(agent_id)
    atlas_db = _get_atlas_db(uri)
    if atlas_db is None:
        return _err("Atlas not configured")
    result = _get_chat_col(atlas_db).delete_one({"_id": thread_id, "agent_id": agent_id})
    if result.deleted_count == 0:
        return _err("Thread not found")
    return _ok({"deleted": thread_id})


@router.get("/{agent_id}/threads/{thread_id}/search-progress")
async def search_progress(agent_id: str, thread_id: str):
    """Return partial search results as each sub-agent finishes."""
    db = get_database()
    doc = await db["trip_search_progress"].find_one({"_id": thread_id})
    if not doc:
        return _ok({"active": False, "flights": None, "hotels": None, "cars": None, "done": False})
    return _ok({
        "active": True,
        "flights": doc.get("flights"),
        "hotels": doc.get("hotels"),
        "cars": doc.get("cars"),
        "done": doc.get("done", False),
    })


def _detect_message_mode(msg: str) -> tuple[str, str | None]:
    """Classify a user message into (mode, reservation_id | None).

    Returns one of:
      ("reserve", None)       — internal reservation payload
      ("update", None)        — internal update payload (__UPDATE__...)
      ("cancel", "TRIP-...")  — cancellation request with extracted ID
      ("modify", "TRIP-...")  — modification request with extracted ID
      ("chat", None)          — normal search / conversational query
    """
    if msg.startswith("__RESERVE__"):
        return "reserve", None
    if msg.startswith("__UPDATE__"):
        return "update", None

    res_id_match = _RESERVATION_ID_RE.search(msg)
    if res_id_match:
        lower = msg.lower()
        if any(w in lower for w in ("cancel", "delete", "remove", "revoke", "annul",
                                     "cancl", "canel", "cancle")):
            return "cancel", res_id_match.group()
        if any(w in lower for w in ("change", "modify", "swap", "replace", "update",
                                     "switch", "different", "instead", "upgrade",
                                     "downgrade", "prefer")):
            return "modify", res_id_match.group()

    return "chat", None


@router.post("/{agent_id}/threads/{thread_id}/messages")
async def send_message(agent_id: str, thread_id: str, body: SendMessageBody):
    uri = await _get_atlas_uri(agent_id)
    atlas_db = _get_atlas_db(uri)
    if atlas_db is None:
        return _err("Atlas not configured")
    col = _get_chat_col(atlas_db)

    thread = col.find_one({"_id": thread_id, "agent_id": agent_id})
    if not thread:
        return _err("Thread not found")

    now = datetime.now(timezone.utc)
    msg_text = body.message

    mode, cancel_id = _detect_message_mode(msg_text)
    logger.info("Message intent detected — mode: %s, cancel_id: %s", mode, cancel_id)

    if mode == "reserve":
        try:
            payload = json.loads(msg_text[len("__RESERVE__"):])
        except Exception:
            return _err("Invalid reservation payload")

        user_msg = {
            "role": "user",
            "content": "Confirming reservation...",
            "timestamp": now.isoformat(),
        }
        col.update_one(
            {"_id": thread_id},
            {"$push": {"messages": user_msg}, "$set": {"updated_at": now}},
        )

        run_doc = await execute_agent(
            agent_id=agent_id,
            args={
                "mode": "reserve",
                "thread_id": thread_id,
                "selected_flight": payload.get("selected_flight", {}),
                "selected_hotel": payload.get("selected_hotel", {}),
                "selected_car": payload.get("selected_car", {}),
                "trip_dates": payload.get("trip_dates", {}),
            },
        )

    elif mode == "cancel":
        user_msg = {
            "role": "user",
            "content": msg_text,
            "timestamp": now.isoformat(),
        }
        col.update_one(
            {"_id": thread_id},
            {"$push": {"messages": user_msg}, "$set": {"updated_at": now}},
        )

        run_doc = await execute_agent(
            agent_id=agent_id,
            args={
                "mode": "cancel",
                "thread_id": thread_id,
                "reservation_id": cancel_id,
            },
        )

    elif mode == "modify":
        user_msg = {
            "role": "user",
            "content": msg_text,
            "timestamp": now.isoformat(),
        }
        col.update_one(
            {"_id": thread_id},
            {"$push": {"messages": user_msg}, "$set": {"updated_at": now}},
        )

        recent = thread.get("messages", [])[-8:]
        chat_history = [{"role": m["role"], "content": m["content"]} for m in recent
                        if m.get("role") in ("user", "assistant") and m.get("content")]

        local_db = get_database()
        await local_db["trip_search_progress"].delete_one({"_id": thread_id})

        run_doc = await execute_agent(
            agent_id=agent_id,
            args={
                "mode": "modify",
                "thread_id": thread_id,
                "reservation_id": cancel_id,
                "message": msg_text,
                "chat_history": chat_history,
            },
        )

    elif mode == "update":
        try:
            payload = json.loads(msg_text[len("__UPDATE__"):])
        except Exception:
            return _err("Invalid update payload")

        user_msg = {
            "role": "user",
            "content": "Updating reservation...",
            "timestamp": now.isoformat(),
        }
        col.update_one(
            {"_id": thread_id},
            {"$push": {"messages": user_msg}, "$set": {"updated_at": now}},
        )

        run_doc = await execute_agent(
            agent_id=agent_id,
            args={
                "mode": "update",
                "thread_id": thread_id,
                "reservation_id": payload.get("reservation_id", ""),
                "category": payload.get("category", ""),
                "selected_item": payload.get("selected_item", {}),
            },
        )

    else:
        user_msg = {
            "role": "user",
            "content": msg_text,
            "timestamp": now.isoformat(),
        }
        col.update_one(
            {"_id": thread_id},
            {"$push": {"messages": user_msg}, "$set": {"updated_at": now}},
        )

        local_db = get_database()
        await local_db["trip_search_progress"].delete_one({"_id": thread_id})

        recent = thread.get("messages", [])[-8:]
        chat_history = [{"role": m["role"], "content": m["content"]} for m in recent
                        if m.get("role") in ("user", "assistant") and m.get("content")]

        run_doc = await execute_agent(
            agent_id=agent_id,
            args={
                "mode": "chat", "thread_id": thread_id,
                "message": msg_text, "chat_history": chat_history,
            },
        )

    return _ok({"run_id": run_doc["_id"], "thread_id": thread_id, "mode": mode})


# -- Prompt Suggestions --------------------------------------------------------

_PROMPT_TEMPLATES = [
    "My partner and I are planning a romantic getaway from {orig} to {dest} around {date}. "
    "We'd love a {flight_class} flight, ideally a direct connection if available. "
    "For accommodation, find us a {stars}-star hotel in the {hotel_neighborhood} area of {hotel_city} "
    "that has {amenity} and {amenity2} — something with a cozy atmosphere. "
    "We'll also need a stylish {color} {car_make} {car_model} to explore the region.",

    "I'm organizing a business trip from {orig} to {dest} on {date}. "
    "I need a {flight_class} flight with {airline} or similar carrier, departing in the morning if possible. "
    "Book a {stars}-star hotel in {hotel_city} near the {hotel_neighborhood} with {amenity} and {amenity2} — "
    "I'll need a quiet room for late-night work. "
    "Also arrange a {car_cat} rental, preferably a {car_make} with {transmission} transmission for the commute.",

    "We're a family of four looking to fly from {orig} to {dest} around {date} in {flight_class}. "
    "We need a family-friendly {stars}-star hotel in {hotel_city} with {amenity} and {amenity2} — "
    "the kids would love a pool and some outdoor space near {hotel_neighborhood}. "
    "For getting around, we'd like a spacious {car_cat} car, something like a {car_make} {car_model} "
    "with {transmission} transmission, {fuel} powered.",

    "I'm a solo traveler looking for an adventurous trip. Fly me from {orig} to {dest} "
    "around {date} in {flight_class} — I don't mind a stopover if it saves money. "
    "I want a comfortable hotel in {hotel_city}, at least {stars} stars, near the {hotel_neighborhood}, "
    "with {amenity} to unwind after long days of exploring. "
    "Rent me a {color} {car_make} {car_model}, {fuel} {car_cat} — I plan to do some scenic driving.",

    "Planning a week-long holiday from {orig} to {dest} departing around {date}. "
    "I'd like to fly {flight_class} with {airline}. "
    "For our stay in {hotel_city}, find a {stars}-star hotel in the {hotel_neighborhood} "
    "that offers {amenity}, {amenity2}, and ideally a rooftop terrace with city views. "
    "We'll need a {color} {car_cat} rental — a {car_make} {car_model} would be perfect "
    "for day trips along the coast.",

    "Looking for a luxury escape: {flight_class} flight from {orig} to {dest} around {date}, "
    "a prestigious {stars}-star hotel in {hotel_city}'s {hotel_neighborhood} district "
    "with {amenity}, {amenity2}, and world-class dining. "
    "Complete the experience with a {color} {car_make} {car_model} — "
    "I want a {fuel} {car_cat} with {transmission} transmission for touring the countryside.",

    "Quick weekend trip needed! Fly {airline} from {orig} to {dest} around {date} "
    "in {flight_class} — I prefer a non-stop flight and a morning departure. "
    "Book a {stars}-star hotel in the heart of {hotel_city} near {hotel_neighborhood} "
    "with {amenity}. For transport, get me a compact {car_make} with {transmission} — "
    "just need something reliable for getting around the city.",

    "I'm treating my parents to a trip from {orig} to {dest} around {date}. "
    "They'd appreciate a comfortable {flight_class} flight, nothing too early in the morning. "
    "Find them a lovely {stars}-star hotel in {hotel_city}'s {hotel_neighborhood} area "
    "with {amenity} and {amenity2} — they value quiet, clean rooms and attentive service. "
    "Also book a comfortable {car_cat} {car_make}, {transmission} with {fuel} engine, "
    "in {color} if possible.",
]


@router.get("/{agent_id}/suggestions")
async def get_suggestions(agent_id: str):
    """Return 3 natural-language prompts built from random real Atlas documents."""
    try:
        uri = await _get_atlas_uri(agent_id)
        if not uri:
            return _ok({"suggestions": _fallback_suggestions()})
        atlas_db = _get_atlas_db(uri)
        if atlas_db is None:
            return _ok({"suggestions": _fallback_suggestions()})

        flights = list(atlas_db["trip_flights"].aggregate([{"$sample": {"size": 6}}]))
        hotels = list(atlas_db["trip_hotels"].aggregate([{"$sample": {"size": 6}}]))
        cars = list(atlas_db["trip_cars"].aggregate([{"$sample": {"size": 6}}]))

        if not flights or not hotels or not cars:
            return _ok({"suggestions": _fallback_suggestions()})

        templates = random.sample(_PROMPT_TEMPLATES, min(3, len(_PROMPT_TEMPLATES)))
        suggestions = []
        for i, tmpl in enumerate(templates):
            f = flights[i % len(flights)]
            h = hotels[i % len(hotels)]
            c = cars[i % len(cars)]
            amenities = h.get("amenities", ["pool"])
            prompt = tmpl.format(
                airline=f.get("airline", ""),
                orig=f.get("origin_city", ""),
                dest=f.get("destination_city", ""),
                date=f.get("date", "2026-06-15"),
                flight_class=f.get("travel_class", "economy"),
                stars=h.get("stars", 4),
                hotel_city=h.get("city", ""),
                hotel_neighborhood=h.get("neighborhood", "City Center"),
                amenity=amenities[0] if amenities else "pool",
                amenity2=amenities[1] if len(amenities) > 1 else "gym",
                rating=h.get("rating", 4.0),
                color=c.get("color", ""),
                car_make=c.get("make", ""),
                car_model=c.get("model", ""),
                car_cat=c.get("category", ""),
                transmission=c.get("transmission", "automatic"),
                fuel=c.get("fuel_type", ""),
            )
            suggestions.append(prompt)
        return _ok({"suggestions": suggestions})
    except Exception as exc:
        logger.warning("Suggestions generation failed: %s", exc)
        return _ok({"suggestions": _fallback_suggestions()})


def _fallback_suggestions():
    return [
        "My partner and I are planning a romantic week in Rome, flying from Paris in business class "
        "around mid-June. We'd love a 4-star boutique hotel near the Historic District with a "
        "rooftop terrace, spa, and restaurant. For exploring Tuscany on day trips, book us a "
        "stylish red BMW convertible with automatic transmission.",
        "I'm organizing a solo adventure from London to Barcelona in late August. I'd like an "
        "economy flight to save money — stopovers are fine. Find me a 3-star hotel in the "
        "Old Town with free WiFi and a bar, and rent me a compact blue Volkswagen Golf, "
        "manual diesel, for driving along the Costa Brava.",
        "Family holiday from Amsterdam to Lisbon departing around July 10th in premium economy. "
        "We need a family-friendly 4-star hotel in the Waterfront area with a pool, kids club, "
        "and shuttle service. Book a spacious white Toyota RAV4 SUV with automatic transmission "
        "so we can explore the Algarve coast together.",
    ]


# -- Reservations --------------------------------------------------------------

@router.get("/{agent_id}/reservations")
async def list_reservations(agent_id: str):
    try:
        uri = await _get_atlas_uri(agent_id)
        if not uri:
            return _err("ATLAS_MONGODB_URI not configured")
        db = _get_atlas_db(uri)
        if db is None:
            return _err("Cannot connect to Atlas")
        docs = list(
            db["trip_reservations"]
            .find({"agent_id": agent_id})
            .sort("created_at", -1)
            .limit(20)
        )
        for d in docs:
            d["id"] = str(d.pop("_id"))
        return _ok(docs)
    except Exception as exc:
        logger.exception("Failed to list reservations: %s", exc)
        return _err(str(exc))


@router.delete("/{agent_id}/reservations/{reservation_id}")
async def delete_reservation(agent_id: str, reservation_id: str):
    try:
        uri = await _get_atlas_uri(agent_id)
        if not uri:
            return _err("ATLAS_MONGODB_URI not configured")
        atlas_db = _get_atlas_db(uri)
        if atlas_db is None:
            return _err("Cannot connect to Atlas")
        result = atlas_db["trip_reservations"].delete_one({"_id": reservation_id})
        if result.deleted_count == 0:
            return _err("Reservation not found")
        return _ok({"deleted": reservation_id})
    except Exception as exc:
        logger.exception("Failed to delete reservation: %s", exc)
        return _err(str(exc))


# -- Long-Term Memory ----------------------------------------------------------

@router.get("/{agent_id}/memory")
async def get_memory(agent_id: str):
    """Return stored user preferences from trip_longMemory."""
    try:
        uri = await _get_atlas_uri(agent_id)
        atlas_db = _get_atlas_db(uri)
        if atlas_db is None:
            return _ok({"preferences": []})
        doc = atlas_db["trip_longMemory"].find_one({"_id": agent_id})
        prefs = doc.get("preferences", []) if doc else []
        for p in prefs:
            if "learned_at" in p:
                p["learned_at"] = str(p["learned_at"])
        return _ok({"preferences": prefs})
    except Exception as exc:
        logger.exception("Failed to load memory: %s", exc)
        return _ok({"preferences": []})


@router.delete("/{agent_id}/memory")
async def clear_memory(agent_id: str):
    """Clear all stored preferences."""
    try:
        uri = await _get_atlas_uri(agent_id)
        atlas_db = _get_atlas_db(uri)
        if atlas_db is None:
            return _err("Atlas not configured")
        atlas_db["trip_longMemory"].delete_one({"_id": agent_id})
        return _ok({"cleared": True})
    except Exception as exc:
        logger.exception("Failed to clear memory: %s", exc)
        return _err(str(exc))


# -- Seed Data -----------------------------------------------------------------

@router.get("/{agent_id}/seed/status")
async def seed_status(agent_id: str):
    """Check whether sample data already exists in Atlas."""
    try:
        uri = await _get_atlas_uri(agent_id)
        if not uri:
            return _ok({"seeded": False, "reason": "ATLAS_MONGODB_URI not configured"})
        atlas_db = _get_atlas_db(uri)
        if atlas_db is None:
            return _ok({"seeded": False, "reason": "Cannot connect to Atlas"})

        counts = {
            "trip_flights": atlas_db["trip_flights"].count_documents({}),
            "trip_hotels": atlas_db["trip_hotels"].count_documents({}),
            "trip_cars": atlas_db["trip_cars"].count_documents({}),
        }
        total = sum(counts.values())
        if total >= 2500:
            return _ok({"seeded": True, "counts": counts, "total": total})
        return _ok({"seeded": False, "counts": counts, "total": total})
    except Exception as exc:
        logger.exception("Seed status check failed: %s", exc)
        return _err(str(exc))


@router.post("/{agent_id}/seed")
async def seed_data(agent_id: str, background_tasks: BackgroundTasks):
    """Generate 1000 sample documents per collection, embed them with Voyage AI,
    and insert into Atlas. Runs in a background task to avoid request timeout."""
    uri = await _get_atlas_uri(agent_id)
    voyage_key = await _get_voyage_key(agent_id)
    if not uri:
        return _err("ATLAS_MONGODB_URI not configured — set it in Settings first")
    if not voyage_key:
        return _err("VOYAGE_AI_API_KEY not configured — set it in Settings first")

    atlas_db = _get_atlas_db(uri)
    if atlas_db is None:
        return _err("Cannot connect to Atlas")

    background_tasks.add_task(_run_seed, atlas_db, voyage_key, agent_id)
    return _ok({"started": True, "message": "Seeding started in background"})


_sync_local_client: MongoClient | None = None


def _get_sync_local_db():
    """Synchronous PyMongo client for local MongoDB — safe to use from background threads."""
    global _sync_local_client
    if _sync_local_client is None:
        local_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        _sync_local_client = MongoClient(local_uri)
    return _sync_local_client[os.getenv("MONGODB_DB_NAME", "agent_platform")]


def _update_seed_progress(agent_id: str, status: str,
                          detail: str = "", error: str = ""):
    """Store seed progress in local MongoDB (synchronous)."""
    try:
        db = _get_sync_local_db()
        db["trip_seed_status"].update_one(
            {"_id": agent_id},
            {"$set": {"status": status, "detail": detail, "error": error,
                      "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    except Exception as exc:
        logger.warning("Failed to update seed progress: %s", exc)


def _run_seed(atlas_db, voyage_key: str, agent_id: str):
    """Synchronous background task that seeds all three collections."""
    try:
        _update_seed_progress(agent_id, "running", "Generating flight data...")

        for col_name, generator in [
            ("trip_flights", _gen_flights),
            ("trip_hotels", _gen_hotels),
            ("trip_cars", _gen_cars),
        ]:
            _update_seed_progress(agent_id, "running",
                                  f"Generating {col_name} documents...")
            docs = generator(DOCS_PER_COLLECTION)
            texts = [d["text_description"] for d in docs]

            _update_seed_progress(agent_id, "running",
                                  f"Embedding {col_name} ({len(texts)} texts)...")
            embeddings = _embed_all(texts, voyage_key)
            for doc, emb in zip(docs, embeddings):
                doc["embedded_description"] = emb

            _update_seed_progress(agent_id, "running",
                                  f"Inserting {col_name} into Atlas...")
            col = atlas_db[col_name]
            col.drop()
            col.insert_many(docs)

            _update_seed_progress(agent_id, "running",
                                  f"Creating vector index on {col_name}...")
            _create_vector_index(col)
            logger.info("Seeded %s with %d documents", col_name, len(docs))

        _update_seed_progress(agent_id, "complete",
                              "All 3 collections seeded & indexes created. "
                              "Indexes may take ~30s to become active.")
    except Exception as exc:
        logger.exception("Seed failed: %s", exc)
        _update_seed_progress(agent_id, "error", error=str(exc))


@router.get("/{agent_id}/seed/progress")
async def seed_progress(agent_id: str):
    """Poll seed operation progress."""
    db = get_database()
    doc = await db["trip_seed_status"].find_one({"_id": agent_id})
    if not doc:
        return _ok({"status": "idle"})
    return _ok({
        "status": doc.get("status", "idle"),
        "detail": doc.get("detail", ""),
        "error": doc.get("error", ""),
    })


# -- Seed: Voyage AI embedding ------------------------------------------------

def _embed_batch(texts: list[str], api_key: str) -> list[list[float]]:
    resp = http_requests.post(
        VOYAGE_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": VOYAGE_MODEL, "input": texts, "input_type": "document"},
        timeout=120,
    )
    resp.raise_for_status()
    return [item["embedding"] for item in resp.json()["data"]]


def _embed_all(texts: list[str], api_key: str) -> list[list[float]]:
    all_embeddings: list[list[float]] = []
    for start in range(0, len(texts), VOYAGE_BATCH_SIZE):
        batch = texts[start:start + VOYAGE_BATCH_SIZE]
        all_embeddings.extend(_embed_batch(batch, api_key))
        time.sleep(0.5)
    return all_embeddings


# -- Seed: Vector index -------------------------------------------------------

def _create_vector_index(col):
    try:
        existing = list(col.list_search_indexes())
        for idx in existing:
            if idx.get("name") == "vector_index":
                logger.info("Dropping old vector_index on %s before re-creating",
                            col.name)
                col.drop_search_index("vector_index")
                _wait_for_index_drop(col, "vector_index")
                break
    except Exception as exc:
        logger.info("list_search_indexes check: %s (proceeding to create)", exc)

    filter_fields = _COLLECTION_FILTER_FIELDS.get(col.name, [])
    fields = [{
        "type": "vector", "path": "embedded_description",
        "numDimensions": EMBED_DIM, "similarity": "cosine",
    }]
    for ff in filter_fields:
        fields.append({"type": "filter", "path": ff})

    logger.info("Creating vector_index on %s (dim=%d, filters=%s)",
                col.name, EMBED_DIM, filter_fields)
    try:
        col.create_search_index(model=SearchIndexModel(
            definition={"fields": fields},
            name="vector_index", type="vectorSearch",
        ))
        logger.info("vector_index creation submitted for %s", col.name)
    except Exception as exc:
        logger.error("Vector index creation failed on %s: %s", col.name, exc)


_COLLECTION_FILTER_FIELDS = {
    "trip_flights": ["origin_city", "destination_city", "travel_class"],
    "trip_hotels": ["city", "stars"],
    "trip_cars": ["color", "make", "category", "transmission", "fuel_type", "pickup_city"],
}


def _wait_for_index_drop(col, index_name: str, timeout: int = 60):
    """Block until a search index is fully removed (max timeout seconds)."""
    for _ in range(timeout):
        try:
            names = [idx.get("name") for idx in col.list_search_indexes()]
            if index_name not in names:
                return
        except Exception:
            return
        time.sleep(1)
    logger.warning("Timed out waiting for index %s to drop on %s", index_name, col.name)


# -- Seed: Document generators ------------------------------------------------

_AIRLINES = [
    "Air France", "Lufthansa", "KLM", "British Airways", "Iberia",
    "Ryanair", "EasyJet", "Turkish Airlines", "Swiss International",
    "Emirates", "Qatar Airways", "Alitalia", "SAS Scandinavian",
    "TAP Air Portugal", "Austrian Airlines", "Aegean Airlines",
    "Finnair", "Norwegian Air", "Vueling", "Wizz Air",
]
_CITIES = [
    ("Paris", "CDG", "France"), ("London", "LHR", "UK"), ("Milan", "MXP", "Italy"),
    ("Madrid", "MAD", "Spain"), ("Berlin", "BER", "Germany"),
    ("Amsterdam", "AMS", "Netherlands"), ("Lisbon", "LIS", "Portugal"),
    ("Rome", "FCO", "Italy"), ("Barcelona", "BCN", "Spain"),
    ("Vienna", "VIE", "Austria"), ("Munich", "MUC", "Germany"),
    ("Zurich", "ZRH", "Switzerland"), ("Istanbul", "IST", "Turkey"),
    ("Athens", "ATH", "Greece"), ("Dublin", "DUB", "Ireland"),
    ("Stockholm", "ARN", "Sweden"), ("Oslo", "OSL", "Norway"),
    ("Helsinki", "HEL", "Finland"), ("Copenhagen", "CPH", "Denmark"),
    ("Brussels", "BRU", "Belgium"), ("Prague", "PRG", "Czech Republic"),
    ("Warsaw", "WAW", "Poland"), ("Budapest", "BUD", "Hungary"),
    ("Bucharest", "OTP", "Romania"), ("Dubai", "DXB", "UAE"),
    ("Doha", "DOH", "Qatar"), ("New York", "JFK", "USA"),
    ("Los Angeles", "LAX", "USA"), ("Tokyo", "NRT", "Japan"),
    ("Singapore", "SIN", "Singapore"),
]
_CLASSES = ["economy", "premium economy", "business", "first"]
_HOTEL_NAMES = [
    "Grand Hotel", "Palace Hotel", "Park Inn", "Marriott", "Hilton",
    "Hyatt Regency", "Radisson Blu", "Holiday Inn", "Novotel", "Ibis",
    "Four Seasons", "Ritz-Carlton", "Sheraton", "Sofitel", "Mercure",
    "InterContinental", "Best Western", "Crowne Plaza", "Westin", "Melia",
]
_NEIGHBORHOODS = [
    "City Center", "Old Town", "Business District", "Waterfront", "Airport Area",
    "University Quarter", "Historic District", "Art District", "Financial Quarter",
    "Beachfront", "Mountain View", "Garden District", "Riverside", "Downtown",
]
_AMENITIES = [
    "pool", "gym", "spa", "restaurant", "bar", "free WiFi", "parking",
    "room service", "concierge", "laundry", "business center", "kids club",
    "rooftop terrace", "sauna", "tennis court", "shuttle service",
]
_ROOM_TYPES = ["standard", "deluxe", "suite", "junior suite", "penthouse", "family"]
_CAR_MAKES = [
    ("BMW", ["3 Series", "X3", "X5", "5 Series", "Z4"]),
    ("Mercedes", ["C-Class", "E-Class", "GLA", "GLC", "A-Class"]),
    ("Audi", ["A3", "A4", "Q3", "Q5", "TT"]),
    ("Volkswagen", ["Golf", "Passat", "Tiguan", "Polo", "T-Roc"]),
    ("Toyota", ["Corolla", "RAV4", "Camry", "Yaris", "C-HR"]),
    ("Renault", ["Clio", "Captur", "Megane", "Kadjar", "Scenic"]),
    ("Ford", ["Focus", "Fiesta", "Kuga", "Puma", "Mustang"]),
    ("Fiat", ["500", "Panda", "Tipo", "500X", "500L"]),
    ("Hyundai", ["i20", "Tucson", "Kona", "i30", "Santa Fe"]),
    ("Kia", ["Sportage", "Ceed", "Niro", "Stonic", "Rio"]),
]
_COLORS = ["black", "white", "silver", "red", "blue", "grey", "green", "dark blue"]
_CAR_CATEGORIES = ["economy", "compact", "mid-size", "full-size", "SUV", "luxury", "convertible"]
_TRANSMISSIONS = ["automatic", "manual"]
_FUEL_TYPES = ["gasoline", "diesel", "hybrid", "electric"]
_RENTAL_COS = ["Hertz", "Avis", "Europcar", "Sixt", "Enterprise", "Budget", "National"]

_FLIGHT_VIBES = {
    "economy": [
        "an affordable option for budget-conscious travelers",
        "a great value fare perfect for backpackers and casual tourists",
        "an economical choice ideal for short weekend getaways",
        "a wallet-friendly flight suitable for solo adventurers or students",
    ],
    "premium economy": [
        "offering extra legroom and comfort for a slightly higher fare",
        "a step above economy with wider seats and priority boarding, great for long-haul journeys",
        "combining affordability with comfort, perfect for business travelers on a budget",
        "featuring complimentary meals and extra baggage, ideal for couples seeking a smooth ride",
    ],
    "business": [
        "a premium experience with lie-flat seats, lounge access, and gourmet dining",
        "designed for executives and discerning travelers seeking productivity and comfort at altitude",
        "featuring priority check-in, spacious seating, and fine wines — ideal for corporate travel",
        "a luxurious cabin with noise-cancelling headphones, turndown service, and world-class cuisine",
    ],
    "first": [
        "the ultimate in air travel luxury with private suites, personal butlers, and Michelin-quality dining",
        "an exclusive experience featuring private cabins, onboard showers, and champagne on arrival",
        "reserved for those who demand the finest — silk pyjamas, caviar service, and chauffeur transfers",
        "the pinnacle of aviation comfort with enclosed suites, unlimited drinks, and concierge service",
    ],
}
_FLIGHT_STOP_DESC = {
    0: ["a convenient non-stop flight", "a direct connection with no layovers",
        "a seamless point-to-point journey"],
    1: ["includes one brief stopover", "with a single connection en route",
        "a one-stop itinerary with a comfortable layover"],
    2: ["a two-stop routing for adventurous travelers who enjoy a longer journey",
        "with two connections — ideal if you like exploring transit airports",
        "a multi-stop route offering a chance to stretch your legs along the way"],
}
_FLIGHT_TIME_DESC = {
    "early_morning": "an early-morning departure perfect for maximizing your day at the destination",
    "morning": "a relaxed morning departure giving you time for a proper breakfast before heading out",
    "afternoon": "an afternoon flight ideal for travelers who prefer sleeping in and a leisurely start",
    "evening": "an evening departure convenient for those wrapping up work before heading to the airport",
    "red_eye": "a late-night red-eye flight — perfect for saving on a hotel night and arriving fresh",
}

_HOTEL_VIBES = {
    2: [
        "a clean and affordable stay with everything you need for a comfortable night",
        "a cozy budget-friendly option great for travelers who spend most of their time exploring the city",
        "simple but well-maintained accommodation with friendly staff and a convenient location",
    ],
    3: [
        "a comfortable mid-range hotel offering a good balance of quality and affordability",
        "a reliable three-star property with modern rooms and thoughtful amenities for a pleasant stay",
        "an excellent value choice with well-appointed rooms and helpful, attentive service",
    ],
    4: [
        "an upscale hotel blending elegant design with top-notch service for a memorable experience",
        "a refined four-star property featuring stylish interiors, premium bedding, and an attentive concierge",
        "a sophisticated retreat perfect for both leisure and business travelers seeking luxury without excess",
    ],
    5: [
        "an ultra-luxury hotel delivering world-class hospitality, breathtaking views, and flawless attention to detail",
        "the crown jewel of the city's hotel scene — opulent suites, Michelin-starred dining, and a legendary spa",
        "an iconic five-star destination where every detail is curated for an unforgettable, once-in-a-lifetime stay",
    ],
}
_HOTEL_NBH_COLOR = {
    "City Center": "steps from the main attractions, shopping streets, and vibrant nightlife",
    "Old Town": "nestled among cobblestone lanes, historic architecture, and charming local cafés",
    "Business District": "surrounded by corporate headquarters, convention centers, and upscale dining",
    "Waterfront": "overlooking the water with stunning sunset views and a refreshing sea breeze",
    "Airport Area": "conveniently located minutes from the terminal, ideal for early flights or long layovers",
    "University Quarter": "in a lively neighborhood buzzing with students, bookshops, and affordable eateries",
    "Historic District": "surrounded by centuries-old monuments, museums, and cultural landmarks",
    "Art District": "immersed in galleries, street art, and creative studios — a haven for culture lovers",
    "Financial Quarter": "at the heart of the financial hub with sleek skyscrapers and premium restaurants",
    "Beachfront": "right on the sand with direct beach access, ocean views, and coastal walking paths",
    "Mountain View": "offering panoramic mountain vistas and crisp alpine air for a rejuvenating escape",
    "Garden District": "surrounded by lush parks, botanical gardens, and tree-lined boulevards",
    "Riverside": "along the river with scenic promenades, boat tours, and waterfront terraces",
    "Downtown": "in the beating heart of the city with easy access to transit, dining, and entertainment",
}

_CAR_VIBES = {
    "economy": [
        "a fuel-efficient city car perfect for navigating narrow streets and tight parking spots",
        "an affordable and nimble ride ideal for solo travelers or couples on a budget",
    ],
    "compact": [
        "a versatile compact car balancing fuel economy with enough space for luggage",
        "a practical choice for city exploration with the agility to handle winding roads",
    ],
    "mid-size": [
        "a comfortable mid-size sedan offering plenty of room for passengers and luggage on longer drives",
        "a well-rounded car perfect for road trips with a smooth ride and ample trunk space",
    ],
    "full-size": [
        "a spacious full-size vehicle ideal for families or groups needing maximum comfort and storage",
        "a roomy and powerful sedan delivering a smooth highway cruise with generous interior space",
    ],
    "SUV": [
        "a rugged SUV ready for mountain roads, countryside adventures, and family road trips",
        "a commanding all-wheel-drive SUV perfect for exploring beyond the city in any weather",
    ],
    "luxury": [
        "a prestigious luxury vehicle with leather interior, advanced tech, and head-turning design",
        "an executive-class ride for those who demand elegance, performance, and a premium driving experience",
    ],
    "convertible": [
        "a stylish convertible for coastal drives, scenic routes, and unforgettable open-air cruising",
        "a thrilling drop-top experience ideal for sunny destinations and memorable weekend escapes",
    ],
}
_CAR_FUEL_DESC = {
    "gasoline": "powered by a responsive gasoline engine",
    "diesel": "equipped with a torquey diesel engine offering excellent highway range",
    "hybrid": "a fuel-efficient hybrid combining electric and gasoline power for eco-conscious driving",
    "electric": "a fully electric vehicle with zero emissions — quiet, smooth, and environmentally friendly",
}


def _gen_flights(n: int) -> list[dict]:
    docs = []
    for _ in range(n):
        airline = random.choice(_AIRLINES)
        orig = random.choice(_CITIES)
        dest = random.choice([c for c in _CITIES if c[0] != orig[0]])
        tc = random.choice(_CLASSES)
        stops = random.choices([0, 1, 2], weights=[0.6, 0.3, 0.1])[0]
        hour = random.randint(5, 22)
        dur = random.randint(60, 720)
        price = round(random.uniform(50, 2500), 2)
        fn = f"{airline[:2].upper()}{random.randint(100, 9999)}"
        date = f"2026-{random.randint(1,12):02d}-{random.randint(1,28):02d}"

        if hour < 7:
            tod = "early_morning"
        elif hour < 12:
            tod = "morning"
        elif hour < 17:
            tod = "afternoon"
        elif hour < 21:
            tod = "evening"
        else:
            tod = "red_eye"

        hours_f, mins_f = divmod(dur, 60)
        dur_str = f"{hours_f}h {mins_f}min" if hours_f else f"{mins_f} minutes"

        text = (
            f"{airline} flight {fn} departing from {orig[0]} ({orig[1]}), {orig[2]} "
            f"to {dest[0]} ({dest[1]}), {dest[2]} on {date}. "
            f"This is {random.choice(_FLIGHT_VIBES[tc])}. "
            f"Scheduled departure at {hour:02d}:00 — {_FLIGHT_TIME_DESC[tod]}. "
            f"Total travel time is {dur_str}, {random.choice(_FLIGHT_STOP_DESC[stops])}. "
            f"Travel class: {tc}. Priced at EUR {price:.0f}."
        )

        docs.append({
            "airline": airline, "flight_number": fn,
            "origin": orig[1], "origin_city": orig[0], "origin_country": orig[2],
            "destination": dest[1], "destination_city": dest[0], "destination_country": dest[2],
            "departure_time": f"{hour:02d}:00",
            "arrival_time": f"{(hour + dur // 60) % 24:02d}:{dur % 60:02d}",
            "date": date, "price_eur": price, "travel_class": tc,
            "stops": stops, "duration_minutes": dur,
            "text_description": text, "embedded_description": [],
        })
    return docs


def _gen_hotels(n: int) -> list[dict]:
    docs = []
    for _ in range(n):
        ci = random.choice(_CITIES)
        name = f"{random.choice(_HOTEL_NAMES)} {ci[0]}"
        stars = random.randint(2, 5)
        price = round(random.uniform(40, 800), 2)
        nbh = random.choice(_NEIGHBORHOODS)
        ams = random.sample(_AMENITIES, random.randint(3, 8))
        rts = random.sample(_ROOM_TYPES, random.randint(1, 3))
        rating = round(random.uniform(3.0, 5.0), 1)

        nbh_desc = _HOTEL_NBH_COLOR.get(nbh, f"in the {nbh} area")
        vibe = random.choice(_HOTEL_VIBES[stars])

        text = (
            f"{name} — {vibe}. "
            f"This {stars}-star property is located in the {nbh} district of {ci[0]}, {ci[2]}, "
            f"{nbh_desc}. "
            f"Guests enjoy amenities including {', '.join(ams[:-1])}, and {ams[-1]}. "
            f"Room options range from {' to '.join(rts)} configurations. "
            f"Rated {rating} out of 5 by recent guests, with nightly rates starting at EUR {price:.0f}."
        )

        docs.append({
            "name": name, "city": ci[0], "country": ci[2],
            "stars": stars, "price_per_night_eur": price,
            "amenities": ams, "neighborhood": nbh, "rating": rating,
            "room_types": rts,
            "text_description": text, "embedded_description": [],
        })
    return docs


def _gen_cars(n: int) -> list[dict]:
    docs = []
    for _ in range(n):
        make, models = random.choice(_CAR_MAKES)
        model = random.choice(models)
        color = random.choice(_COLORS)
        cat = random.choice(_CAR_CATEGORIES)
        trans = random.choice(_TRANSMISSIONS)
        fuel = random.choice(_FUEL_TYPES)
        doors = random.choice([2, 4, 5])
        price = round(random.uniform(20, 350), 2)
        company = random.choice(_RENTAL_COS)
        ci = random.choice(_CITIES)

        vibe = random.choice(_CAR_VIBES[cat])
        fuel_desc = _CAR_FUEL_DESC[fuel]
        trans_desc = "smooth automatic gearbox" if trans == "automatic" else "engaging manual transmission"

        text = (
            f"{company} offers a {color} {make} {model} for rental in {ci[0]}, {ci[2]} — "
            f"{vibe}. "
            f"This {cat} vehicle features {doors} doors, a {trans_desc}, and is {fuel_desc}. "
            f"Available at EUR {price:.0f} per day, it's a great pick for exploring {ci[0]} "
            f"and the surrounding {ci[2]} countryside."
        )

        docs.append({
            "company": company, "make": make, "model": model,
            "color": color, "category": cat, "doors": doors,
            "transmission": trans, "fuel_type": fuel,
            "price_per_day_eur": price, "pickup_city": ci[0],
            "text_description": text, "embedded_description": [],
        })
    return docs
