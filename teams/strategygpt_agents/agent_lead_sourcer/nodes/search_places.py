"""Search node — queries Google Maps Places API (Text Search) for businesses."""

import time
import requests

from shared.config import GOOGLE_MAPS_API_KEY
from shared.logger import get_logger

logger = get_logger("lead_sourcer.search_places")

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"


def search_places(state: dict) -> dict:
    city = state.get("city", "")
    categories = state.get("categories", [])
    max_leads = state.get("max_leads", 50)

    if not city:
        logger.error("No city provided")
        return {"status": "error"}

    if not GOOGLE_MAPS_API_KEY:
        logger.error("GOOGLE_MAPS_API_KEY is not set")
        return {"status": "error"}

    all_places = []

    for category in categories:
        query = f"{category} in {city}"
        logger.info("Searching: %s", query)

        places = _text_search(query, max_leads)
        all_places.extend(places)
        logger.info("Found %d results for '%s'", len(places), query)

        time.sleep(0.5)

    logger.info("Total raw places fetched: %d", len(all_places))
    return {"raw_places": all_places, "status": "places_fetched"}


def _text_search(query: str, max_results: int) -> list[dict]:
    """Call Places API (New) Text Search and paginate with nextPageToken."""
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.nationalPhoneNumber,places.internationalPhoneNumber,"
            "places.rating,places.userRatingCount,places.websiteUri,"
            "places.primaryType,places.businessStatus,"
            "places.regularOpeningHours,nextPageToken"
        ),
    }

    results: list[dict] = []
    page_token = None

    while len(results) < max_results:
        body: dict = {"textQuery": query, "languageCode": "en"}
        if page_token:
            body["pageToken"] = page_token

        try:
            resp = requests.post(PLACES_TEXT_SEARCH_URL, json=body, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("Places API request failed: %s", exc)
            break

        for place in data.get("places", []):
            results.append({
                "place_id": place.get("id", ""),
                "business_name": place.get("displayName", {}).get("text", ""),
                "address": place.get("formattedAddress", ""),
                "phone": place.get("internationalPhoneNumber", "")
                         or place.get("nationalPhoneNumber", ""),
                "rating": place.get("rating", 0),
                "review_count": place.get("userRatingCount", 0),
                "website": place.get("websiteUri", ""),
                "category": place.get("primaryType", ""),
                "business_status": place.get("businessStatus", ""),
                "opening_hours": place.get("regularOpeningHours", {}),
            })

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(1)

    return results[:max_results]
