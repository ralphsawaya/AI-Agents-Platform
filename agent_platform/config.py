from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "agent_platform"
    AGENTS_STORE_PATH: str = str(Path(__file__).resolve().parent / "agents_store")
    DEFAULT_TIMEOUT_SECONDS: int = 300
    MAX_RUNS_TO_KEEP: int = 100
    FAILURE_ALERT_THRESHOLD: int = 3
    LOG_RETENTION_DAYS: int = 30
    PORT: int = 8000

    groq_api_key: str = ""
    anthropic_api_key: str = ""
    binance_api_key: str = ""
    binance_api_secret: str = ""
    tradingview_webhook_secret: str = ""

    trading_enabled: bool = True
    trading_dry_run: bool = True
    trading_max_daily_trades: int = 50
    trading_duplicate_window_seconds: int = 60

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
