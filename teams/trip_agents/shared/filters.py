"""Validate and normalize search filter dicts from LLM tool plans."""

_VALID_CLASSES = {"economy", "premium economy", "business", "first"}
_VALID_CATEGORIES = {"economy", "compact", "mid-size", "full-size", "SUV", "luxury", "convertible"}
_VALID_TRANSMISSIONS = {"automatic", "manual"}
_VALID_FUELS = {"gasoline", "diesel", "hybrid", "electric"}


def clean_flight_filters(f: dict) -> dict:
    if not isinstance(f, dict):
        return {}
    out = {}
    if f.get("origin_city"):
        out["origin_city"] = str(f["origin_city"])
    if f.get("destination_city"):
        out["destination_city"] = str(f["destination_city"])
    if f.get("travel_class") and str(f["travel_class"]).lower() in _VALID_CLASSES:
        out["travel_class"] = str(f["travel_class"]).lower()
    return out


def clean_hotel_filters(h: dict) -> dict:
    if not isinstance(h, dict):
        return {}
    out = {}
    if h.get("city"):
        out["city"] = str(h["city"])
    if h.get("stars") and isinstance(h["stars"], (int, float)):
        out["stars"] = int(h["stars"])
    return out


def clean_car_filters(c: dict) -> dict:
    if not isinstance(c, dict):
        return {}
    out = {}
    if c.get("color"):
        out["color"] = str(c["color"]).lower()
    if c.get("make"):
        out["make"] = str(c["make"])
    if c.get("category") and str(c["category"]).lower() in _VALID_CATEGORIES:
        out["category"] = str(c["category"]).lower()
    if c.get("transmission") and str(c["transmission"]).lower() in _VALID_TRANSMISSIONS:
        out["transmission"] = str(c["transmission"]).lower()
    if c.get("fuel_type") and str(c["fuel_type"]).lower() in _VALID_FUELS:
        out["fuel_type"] = str(c["fuel_type"]).lower()
    if c.get("pickup_city"):
        out["pickup_city"] = str(c["pickup_city"])
    return out


# Backward-compatible aliases used by orchestrator/tools.py
_clean_flight_filters = clean_flight_filters
_clean_hotel_filters = clean_hotel_filters
_clean_car_filters = clean_car_filters
