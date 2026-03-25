"""Fetch new leads from MongoDB that haven't been qualified yet."""

from shared.logger import get_logger
from shared.mongo import get_leads_collection
from shared.config import MAX_LEADS_PER_RUN

logger = get_logger("lead_qualifier.fetch_new_leads")


def fetch_new_leads(state: dict) -> dict:
    col = get_leads_collection()
    cursor = col.find({"status": "new"}).limit(MAX_LEADS_PER_RUN)
    leads = list(cursor)

    logger.info("Fetched %d new leads for qualification", len(leads))

    if not leads:
        return {"new_leads": [], "status": "no_leads"}

    serialised = []
    for doc in leads:
        serialised.append({
            "place_id": doc["place_id"],
            "business_name": doc["business_name"],
            "phone": doc["phone"],
            "address": doc.get("address", ""),
            "category": doc.get("category", ""),
            "review_count": doc.get("review_count", 0),
            "rating": doc.get("rating", 0),
            "city": doc.get("city", ""),
            "opening_hours": doc.get("opening_hours", {}),
        })

    return {"new_leads": serialised, "status": "leads_fetched"}
