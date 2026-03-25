"""Filter node — applies targeting criteria and deduplicates against MongoDB."""

from shared.logger import get_logger
from shared.mongo import get_leads_collection

logger = get_logger("lead_sourcer.filter_leads")


def filter_leads(state: dict) -> dict:
    if state.get("status") == "error":
        return state

    raw_places = state.get("raw_places", [])
    min_reviews = state.get("min_reviews", 10)
    min_rating = state.get("min_rating", 3.5)

    existing_ids = _get_existing_place_ids()

    filtered = []
    for place in raw_places:
        place_id = place.get("place_id", "")

        if place_id in existing_ids:
            continue

        if place.get("website"):
            continue

        if place.get("review_count", 0) < min_reviews:
            continue

        if place.get("rating", 0) < min_rating:
            continue

        if not place.get("phone"):
            continue

        if place.get("business_status") not in ("OPERATIONAL", ""):
            continue

        filtered.append(place)

    logger.info(
        "Filtered %d -> %d leads (min_reviews=%d, min_rating=%.1f, no website, has phone)",
        len(raw_places), len(filtered), min_reviews, min_rating,
    )
    return {"filtered_leads": filtered, "status": "leads_filtered"}


def _get_existing_place_ids() -> set[str]:
    """Return place_ids already stored in MongoDB to avoid duplicates."""
    col = get_leads_collection()
    cursor = col.find({}, {"place_id": 1})
    return {doc["place_id"] for doc in cursor if "place_id" in doc}
