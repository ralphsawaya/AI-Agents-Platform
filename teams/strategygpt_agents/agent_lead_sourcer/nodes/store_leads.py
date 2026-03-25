"""Store node — inserts filtered leads into MongoDB."""

from datetime import datetime, timezone

from shared.logger import get_logger
from shared.mongo import get_leads_collection

logger = get_logger("lead_sourcer.store_leads")


def store_leads(state: dict) -> dict:
    if state.get("status") == "error":
        return state

    filtered = state.get("filtered_leads", [])
    city = state.get("city", "")
    max_leads = state.get("max_leads", 50)

    to_insert = filtered[:max_leads]
    col = get_leads_collection()

    docs = []
    for lead in to_insert:
        docs.append({
            "place_id": lead["place_id"],
            "business_name": lead["business_name"],
            "phone": lead["phone"],
            "address": lead["address"],
            "category": lead.get("category", ""),
            "review_count": lead.get("review_count", 0),
            "rating": lead.get("rating", 0),
            "city": city,
            "opening_hours": lead.get("opening_hours", {}),
            "status": "new",
            "call_script": "",
            "created_at": datetime.now(timezone.utc),
        })

    if docs:
        col.insert_many(docs)

    logger.info("Stored %d new leads in MongoDB", len(docs))
    return {"stored_count": len(docs), "status": "leads_stored"}
