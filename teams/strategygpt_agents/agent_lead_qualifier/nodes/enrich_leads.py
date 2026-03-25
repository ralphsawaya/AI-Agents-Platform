"""Enrich and validate leads — phone format, DNC check, business status."""

from shared.logger import get_logger
from shared.utils import format_phone_us
from shared.mongo import get_leads_collection, get_dnc_collection

logger = get_logger("lead_qualifier.enrich_leads")


def enrich_leads(state: dict) -> dict:
    if state.get("status") in ("error", "no_leads"):
        return state

    new_leads = state.get("new_leads", [])
    dnc_numbers = _load_dnc_set()

    qualified = []
    invalid = []
    col = get_leads_collection()

    for lead in new_leads:
        normalised_phone = format_phone_us(lead.get("phone", ""))

        if not normalised_phone:
            logger.info("Invalid phone for %s — skipping", lead["business_name"])
            col.update_one({"place_id": lead["place_id"]}, {"$set": {"status": "invalid"}})
            invalid.append(lead)
            continue

        if normalised_phone in dnc_numbers:
            logger.info("DNC hit for %s — skipping", lead["business_name"])
            col.update_one({"place_id": lead["place_id"]}, {"$set": {"status": "invalid"}})
            invalid.append(lead)
            continue

        lead["phone"] = normalised_phone
        qualified.append(lead)

    logger.info(
        "Enrichment complete: %d qualified, %d invalid out of %d",
        len(qualified), len(invalid), len(new_leads),
    )

    return {
        "qualified_leads": qualified,
        "invalid_leads": invalid,
        "qualified_count": len(qualified),
        "status": "leads_enriched",
    }


def _load_dnc_set() -> set[str]:
    """Load internal Do Not Call list from MongoDB."""
    col = get_dnc_collection()
    return {doc["phone"] for doc in col.find({}, {"phone": 1}) if "phone" in doc}
