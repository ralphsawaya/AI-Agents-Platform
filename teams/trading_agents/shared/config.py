"""Shared configuration for trading agents."""

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

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = "agent_platform"

TRADING_PAIR = os.getenv("TRADING_PAIR", "BTCUSDT")
BASE_ASSET = "BTC"
QUOTE_ASSET = "USDT"

# Risk defaults
MAX_RISK_PER_TRADE = float(os.getenv("MAX_RISK_PER_TRADE", "0.02"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "3"))
MAX_DRAWDOWN = float(os.getenv("MAX_DRAWDOWN", "0.10"))

# Indicator periods
ADX_PERIOD = 14
ATR_PERIOD = 14
BB_PERIOD = 20
BB_STD = 2.0
EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50
RSI_PERIOD = 14
VOLUME_MA_PERIOD = 20

# Available LLM models per provider
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

# Defaults schema — used as fallback when MongoDB has no trading_config document
RISK_DEFAULTS = {
    "max_risk_per_trade": MAX_RISK_PER_TRADE,
    "max_open_positions": MAX_OPEN_POSITIONS,
    "max_drawdown": MAX_DRAWDOWN,
}

INDICATOR_DEFAULTS = {
    "adx_period": ADX_PERIOD,
    "atr_period": ATR_PERIOD,
    "bb_period": BB_PERIOD,
    "bb_std": BB_STD,
    "ema_fast": EMA_FAST,
    "ema_mid": EMA_MID,
    "ema_slow": EMA_SLOW,
    "rsi_period": RSI_PERIOD,
    "volume_ma_period": VOLUME_MA_PERIOD,
}


def get_trading_config_defaults() -> dict:
    """Return the full default trading config dict."""
    return {
        "llm_provider": LLM_PROVIDER,
        "llm_model": LLM_MODEL,
        "risk_defaults": dict(RISK_DEFAULTS),
        "indicator_periods": dict(INDICATOR_DEFAULTS),
    }
