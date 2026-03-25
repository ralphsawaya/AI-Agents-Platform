"""Shared configuration for StrategyGPT agents."""

import os

AGENT_ID = os.getenv("AGENT_ID", "")

# --- LLM provider keys ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2048"))

# --- Google Maps ---
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# --- Voice API ---
VOICE_API_KEY = os.getenv("VOICE_API_KEY", "")
VOICE_API_PROVIDER = os.getenv("VOICE_API_PROVIDER", "bland")
MAX_CONCURRENT_CALLS = int(os.getenv("MAX_CONCURRENT_CALLS", "5"))
CALLS_PER_BATCH = int(os.getenv("CALLS_PER_BATCH", "20"))

# --- MongoDB ---
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = "agent_platform"

# --- Lead filtering defaults ---
MIN_REVIEWS = int(os.getenv("MIN_REVIEWS", "10"))
MIN_RATING = float(os.getenv("MIN_RATING", "3.5"))
MAX_LEADS_PER_RUN = int(os.getenv("MAX_LEADS_PER_RUN", "50"))

# --- Available LLM providers ---
LLM_PROVIDERS = {
    "groq": {
        "label": "Groq",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
        "default": "llama-3.3-70b-versatile",
    },
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
    "openai": {
        "label": "OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini", "o3-mini"],
        "default": "gpt-4o",
    },
}
