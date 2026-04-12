#!/usr/bin/env python3
"""Seed MongoDB Atlas with 1 000 synthetic documents per trip collection.

For each of trip_flights, trip_hotels, and trip_cars this script:
  1. Generates 1 000 random documents from realistic data lists.
  2. Computes embedded_description (512-dim) via Voyage AI (voyage-3-lite) in batches.
  3. Bulk-inserts the documents into Atlas.
  4. Creates a vectorSearch index named "vector_index" on each collection.

Usage:
  export ATLAS_MONGODB_URI="mongodb+srv://..."
  export VOYAGE_AI_API_KEY="..."
  python seed_data.py
"""

import os
import random
import sys
import time

import certifi
import requests
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ATLAS_URI = os.getenv("ATLAS_MONGODB_URI", "")
VOYAGE_KEY = os.getenv("VOYAGE_AI_API_KEY", "")
VOYAGE_MODEL = "voyage-3-lite"
VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
EMBED_DIM = 512
BATCH_SIZE = 96
DOCS_PER_COLLECTION = 1000

if not ATLAS_URI:
    sys.exit("Set ATLAS_MONGODB_URI in your environment")
if not VOYAGE_KEY:
    sys.exit("Set VOYAGE_AI_API_KEY in your environment")

client = MongoClient(ATLAS_URI, tlsCAFile=certifi.where())
db = client.get_default_database(default="trip_data")

# ---------------------------------------------------------------------------
# Reference data lists
# ---------------------------------------------------------------------------

AIRLINES = [
    "Air France", "Lufthansa", "KLM", "British Airways", "Iberia",
    "Ryanair", "EasyJet", "Turkish Airlines", "Swiss International",
    "Emirates", "Qatar Airways", "Alitalia", "SAS Scandinavian",
    "TAP Air Portugal", "Austrian Airlines", "Aegean Airlines",
    "Finnair", "Norwegian Air", "Vueling", "Wizz Air",
]

CITIES = [
    ("Paris", "CDG", "France"), ("London", "LHR", "UK"), ("Milan", "MXP", "Italy"),
    ("Madrid", "MAD", "Spain"), ("Berlin", "BER", "Germany"), ("Amsterdam", "AMS", "Netherlands"),
    ("Lisbon", "LIS", "Portugal"), ("Rome", "FCO", "Italy"), ("Barcelona", "BCN", "Spain"),
    ("Vienna", "VIE", "Austria"), ("Munich", "MUC", "Germany"), ("Zurich", "ZRH", "Switzerland"),
    ("Istanbul", "IST", "Turkey"), ("Athens", "ATH", "Greece"), ("Dublin", "DUB", "Ireland"),
    ("Stockholm", "ARN", "Sweden"), ("Oslo", "OSL", "Norway"), ("Helsinki", "HEL", "Finland"),
    ("Copenhagen", "CPH", "Denmark"), ("Brussels", "BRU", "Belgium"),
    ("Prague", "PRG", "Czech Republic"), ("Warsaw", "WAW", "Poland"),
    ("Budapest", "BUD", "Hungary"), ("Bucharest", "OTP", "Romania"),
    ("Dubai", "DXB", "UAE"), ("Doha", "DOH", "Qatar"),
    ("New York", "JFK", "USA"), ("Los Angeles", "LAX", "USA"),
    ("Tokyo", "NRT", "Japan"), ("Singapore", "SIN", "Singapore"),
]

TRAVEL_CLASSES = ["economy", "premium economy", "business", "first"]

HOTEL_NAMES = [
    "Grand Hotel", "Palace Hotel", "Park Inn", "Marriott", "Hilton",
    "Hyatt Regency", "Radisson Blu", "Holiday Inn", "Novotel", "Ibis",
    "Four Seasons", "Ritz-Carlton", "Sheraton", "Sofitel", "Mercure",
    "InterContinental", "Best Western", "Crowne Plaza", "Westin", "Melia",
]

NEIGHBORHOODS = [
    "City Center", "Old Town", "Business District", "Waterfront", "Airport Area",
    "University Quarter", "Historic District", "Art District", "Financial Quarter",
    "Beachfront", "Mountain View", "Garden District", "Riverside", "Downtown",
]

AMENITIES = [
    "pool", "gym", "spa", "restaurant", "bar", "free WiFi", "parking",
    "room service", "concierge", "laundry", "business center", "kids club",
    "rooftop terrace", "sauna", "tennis court", "shuttle service",
]

ROOM_TYPES = ["standard", "deluxe", "suite", "junior suite", "penthouse", "family"]

CAR_MAKES = [
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

COLORS = ["black", "white", "silver", "red", "blue", "grey", "green", "dark blue"]
CAR_CATEGORIES = ["economy", "compact", "mid-size", "full-size", "SUV", "luxury", "convertible"]
TRANSMISSIONS = ["automatic", "manual"]
FUEL_TYPES = ["gasoline", "diesel", "hybrid", "electric"]
RENTAL_COMPANIES = ["Hertz", "Avis", "Europcar", "Sixt", "Enterprise", "Budget", "National"]

FLIGHT_VIBES = {
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
FLIGHT_STOP_DESC = {
    0: ["a convenient non-stop flight", "a direct connection with no layovers",
        "a seamless point-to-point journey"],
    1: ["includes one brief stopover", "with a single connection en route",
        "a one-stop itinerary with a comfortable layover"],
    2: ["a two-stop routing for adventurous travelers who enjoy a longer journey",
        "with two connections — ideal if you like exploring transit airports",
        "a multi-stop route offering a chance to stretch your legs along the way"],
}
FLIGHT_TIME_DESC = {
    "early_morning": "an early-morning departure perfect for maximizing your day at the destination",
    "morning": "a relaxed morning departure giving you time for a proper breakfast before heading out",
    "afternoon": "an afternoon flight ideal for travelers who prefer sleeping in and a leisurely start",
    "evening": "an evening departure convenient for those wrapping up work before heading to the airport",
    "red_eye": "a late-night red-eye flight — perfect for saving on a hotel night and arriving fresh",
}

HOTEL_VIBES = {
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
HOTEL_NBH_COLOR = {
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

CAR_VIBES = {
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
CAR_FUEL_DESC = {
    "gasoline": "powered by a responsive gasoline engine",
    "diesel": "equipped with a torquey diesel engine offering excellent highway range",
    "hybrid": "a fuel-efficient hybrid combining electric and gasoline power for eco-conscious driving",
    "electric": "a fully electric vehicle with zero emissions — quiet, smooth, and environmentally friendly",
}

# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using the Voyage AI API."""
    resp = requests.post(
        VOYAGE_URL,
        headers={"Authorization": f"Bearer {VOYAGE_KEY}", "Content-Type": "application/json"},
        json={"model": VOYAGE_MODEL, "input": texts, "input_type": "document"},
        timeout=120,
    )
    resp.raise_for_status()
    return [item["embedding"] for item in resp.json()["data"]]


def embed_all(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts in batches."""
    all_embeddings: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        print(f"  Embedding batch {start // BATCH_SIZE + 1}/{-(-len(texts) // BATCH_SIZE)} ({len(batch)} texts)")
        all_embeddings.extend(embed_batch(batch))
        time.sleep(0.5)
    return all_embeddings


# ---------------------------------------------------------------------------
# Document generators
# ---------------------------------------------------------------------------


def gen_flights(n: int) -> list[dict]:
    docs = []
    for _ in range(n):
        airline = random.choice(AIRLINES)
        orig = random.choice(CITIES)
        dest = random.choice([c for c in CITIES if c[0] != orig[0]])
        tc = random.choice(TRAVEL_CLASSES)
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
            f"This is {random.choice(FLIGHT_VIBES[tc])}. "
            f"Scheduled departure at {hour:02d}:00 — {FLIGHT_TIME_DESC[tod]}. "
            f"Total travel time is {dur_str}, {random.choice(FLIGHT_STOP_DESC[stops])}. "
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


def gen_hotels(n: int) -> list[dict]:
    docs = []
    for _ in range(n):
        ci = random.choice(CITIES)
        name = f"{random.choice(HOTEL_NAMES)} {ci[0]}"
        stars = random.randint(2, 5)
        price = round(random.uniform(40, 800), 2)
        nbh = random.choice(NEIGHBORHOODS)
        ams = random.sample(AMENITIES, random.randint(3, 8))
        rts = random.sample(ROOM_TYPES, random.randint(1, 3))
        rating = round(random.uniform(3.0, 5.0), 1)

        nbh_desc = HOTEL_NBH_COLOR.get(nbh, f"in the {nbh} area")
        vibe = random.choice(HOTEL_VIBES[stars])

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


def gen_cars(n: int) -> list[dict]:
    docs = []
    for _ in range(n):
        make, models = random.choice(CAR_MAKES)
        model = random.choice(models)
        color = random.choice(COLORS)
        cat = random.choice(CAR_CATEGORIES)
        trans = random.choice(TRANSMISSIONS)
        fuel = random.choice(FUEL_TYPES)
        doors = random.choice([2, 4, 5])
        price = round(random.uniform(20, 350), 2)
        company = random.choice(RENTAL_COMPANIES)
        ci = random.choice(CITIES)

        vibe = random.choice(CAR_VIBES[cat])
        fuel_desc = CAR_FUEL_DESC[fuel]
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


# ---------------------------------------------------------------------------
# Vector search index creation
# ---------------------------------------------------------------------------


def create_vector_index(collection_name: str):
    col = db[collection_name]
    try:
        existing = list(col.list_search_indexes())
        for idx in existing:
            if idx.get("name") == "vector_index":
                print(f"  Dropping old vector_index on {collection_name}...")
                col.drop_search_index("vector_index")
                _wait_for_index_drop(col, "vector_index")
                break
    except Exception as exc:
        print(f"  list_search_indexes check: {exc} (proceeding to create)")

    filter_fields = COLLECTION_FILTER_FIELDS.get(collection_name, [])
    fields = [{
        "type": "vector",
        "path": "embedded_description",
        "numDimensions": EMBED_DIM,
        "similarity": "cosine",
    }]
    for ff in filter_fields:
        fields.append({"type": "filter", "path": ff})

    print(f"  Creating vector_index on {collection_name} (dim={EMBED_DIM}, filters={filter_fields})...")
    model = SearchIndexModel(
        definition={"fields": fields},
        name="vector_index",
        type="vectorSearch",
    )
    col.create_search_index(model=model)
    print(f"  vector_index creation submitted for {collection_name}")


COLLECTION_FILTER_FIELDS = {
    "trip_flights": ["origin_city", "destination_city", "travel_class"],
    "trip_hotels": ["city", "stars"],
    "trip_cars": ["color", "make", "category", "transmission", "fuel_type", "pickup_city"],
}


def _wait_for_index_drop(col, index_name: str, timeout: int = 60):
    """Block until a search index is fully removed."""
    import time as _time
    for _ in range(timeout):
        try:
            names = [idx.get("name") for idx in col.list_search_indexes()]
            if index_name not in names:
                return
        except Exception:
            return
        _time.sleep(1)
    print(f"  WARNING: Timed out waiting for {index_name} to drop on {col.name}")
    print(f"  Index creation initiated for {collection_name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def seed_collection(name: str, generator):
    print(f"\n{'='*60}")
    print(f"Seeding {name} ({DOCS_PER_COLLECTION} documents)")
    print(f"{'='*60}")

    docs = generator(DOCS_PER_COLLECTION)
    texts = [d["text_description"] for d in docs]
    embeddings = embed_all(texts)

    for doc, emb in zip(docs, embeddings):
        doc["embedded_description"] = emb

    col = db[name]
    col.drop()
    result = col.insert_many(docs)
    print(f"  Inserted {len(result.inserted_ids)} documents into {name}")

    create_vector_index(name)


def main():
    print("Trip Data Seeder")
    print(f"Atlas URI: {ATLAS_URI[:30]}...")
    print(f"Database: {db.name}")

    seed_collection("trip_flights", gen_flights)
    seed_collection("trip_hotels", gen_hotels)
    seed_collection("trip_cars", gen_cars)

    print(f"\n{'='*60}")
    print("Seeding complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
