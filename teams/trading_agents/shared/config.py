"""Shared configuration for trading agents."""

import os

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
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
