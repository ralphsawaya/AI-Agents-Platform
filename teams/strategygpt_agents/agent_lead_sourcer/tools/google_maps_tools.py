"""Google Maps Places API tools for the Lead Sourcer agent."""

import requests
from langchain_core.tools import tool

from shared.config import GOOGLE_MAPS_API_KEY

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"


@tool
def search_places_api(query: str, location: str) -> list[dict]:
    """Search Google Maps for businesses matching a query in a location."""
    full_query = f"{query} in {location}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.nationalPhoneNumber,places.rating,places.userRatingCount,"
            "places.websiteUri,places.primaryType"
        ),
    }
    body = {"textQuery": full_query, "languageCode": "en"}
    resp = requests.post(PLACES_TEXT_SEARCH_URL, json=body, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json().get("places", [])


@tool
def get_place_details(place_id: str) -> dict:
    """Fetch detailed information for a specific Google Maps place."""
    headers = {
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": (
            "id,displayName,formattedAddress,nationalPhoneNumber,"
            "internationalPhoneNumber,rating,userRatingCount,"
            "websiteUri,primaryType,regularOpeningHours,businessStatus"
        ),
    }
    url = PLACE_DETAILS_URL.format(place_id=place_id)
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()
