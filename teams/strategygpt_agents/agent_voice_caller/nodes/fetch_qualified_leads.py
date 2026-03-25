"""Fetch qualified leads that are ready for outreach calls."""

from shared.logger import get_logger
from shared.mongo import get_leads_collection

logger = get_logger("voice_caller.fetch_qualified_leads")


def fetch_qualified_leads(state: dict) -> dict:
    batch_size = state.get("batch_size", 20)
    col = get_leads_collection()

    cursor = col.find({"status": "qualified"}).limit(batch_size)
    leads = list(cursor)

    logger.info("Fetched %d qualified leads for calling", len(leads))

    if not leads:
        return {"leads_to_call": [], "status": "no_leads"}

    serialised = []
    for doc in leads:
        serialised.append({
            "place_id": doc["place_id"],
            "business_name": doc["business_name"],
            "phone": doc["phone"],
            "category": doc.get("category", ""),
            "city": doc.get("city", ""),
            "call_script": doc.get("call_script", ""),
        })

    return {"leads_to_call": serialised, "status": "leads_ready"}
