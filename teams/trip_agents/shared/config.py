"""Shared configuration for trip agents."""

import os

AGENT_ID = os.getenv("AGENT_ID", "")

# --- LLM provider keys ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4096"))

# --- Trip-specific keys ---
VOYAGE_AI_API_KEY = os.getenv("VOYAGE_AI_API_KEY", "")
ATLAS_MONGODB_URI = os.getenv("ATLAS_MONGODB_URI", "")

# --- Local MongoDB (platform) ---
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = "agent_platform"

# --- Voyage AI ---
VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-3-lite")
VOYAGE_EMBED_DIM = 512

# --- Atlas collection names ---
FLIGHTS_COLLECTION = "trip_flights"
HOTELS_COLLECTION = "trip_hotels"
CARS_COLLECTION = "trip_cars"
RESERVATIONS_COLLECTION = "trip_reservations"
CHAT_COLLECTION = "trip_chatPersistence"
LONG_MEMORY_COLLECTION = "trip_longMemory"

# --- Available LLM models per provider ---
LLM_PROVIDERS = {
    "gemini": {
        "label": "Google Gemini",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
        "default": "gemini-2.5-flash",
    },
    "claude": {
        "label": "Anthropic Claude",
        "models": ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"],
        "default": "claude-sonnet-4-20250514",
    },
    "deepseek": {
        "label": "DeepSeek",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default": "deepseek-chat",
    },
    "groq": {
        "label": "Groq",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
        "default": "llama-3.3-70b-versatile",
    },
    "openai": {
        "label": "OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini", "o3-mini"],
        "default": "gpt-4o",
    },
}
