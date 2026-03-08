"""MongoDB timeseries cache for Binance OHLCV data.

Uses a timeseries collection with a 4-year TTL so stale candles are
automatically purged by MongoDB.  The cache layer downloads only the
missing date ranges from Binance, keeping subsequent backtest runs
near-instant.
"""

import logging

import pandas as pd
from pymongo import MongoClient
from pymongo.errors import CollectionInvalid

from agent_platform.config import settings

logger = logging.getLogger(__name__)

_COLLECTION = "ohlcv"
_TTL_SECONDS = 4 * 365 * 24 * 60 * 60  # ~126 million seconds

_TF_DELTA = {
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "1d": pd.Timedelta(days=1),
}

_sync_client: MongoClient | None = None


def _get_db():
    global _sync_client
    if _sync_client is None:
        _sync_client = MongoClient(settings.MONGODB_URI)
    return _sync_client[settings.MONGODB_DB_NAME]


def _ensure_collection():
    db = _get_db()
    try:
        db.create_collection(
            _COLLECTION,
            timeseries={
                "timeField": "timestamp",
                "metaField": "meta",
                "granularity": "minutes",
            },
            expireAfterSeconds=_TTL_SECONDS,
        )
        logger.info("Created timeseries collection '%s' with 4-year TTL", _COLLECTION)
    except CollectionInvalid:
        pass


def get_cached_range(symbol: str, timeframe: str):
    """Return (min_ts, max_ts, count) of cached candles."""
    _ensure_collection()
    coll = _get_db()[_COLLECTION]
    pipeline = [
        {"$match": {"meta": {"symbol": symbol, "timeframe": timeframe}}},
        {"$group": {
            "_id": None,
            "min_ts": {"$min": "$timestamp"},
            "max_ts": {"$max": "$timestamp"},
            "count": {"$sum": 1},
        }},
    ]
    result = list(coll.aggregate(pipeline))
    if not result:
        return None, None, 0
    r = result[0]
    return (
        pd.Timestamp(r["min_ts"], tz="UTC"),
        pd.Timestamp(r["max_ts"], tz="UTC"),
        r["count"],
    )


def load_cached(symbol: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
    """Load cached OHLCV data from MongoDB as a DataFrame."""
    _ensure_collection()
    coll = _get_db()[_COLLECTION]

    start_ts = pd.Timestamp(start, tz="UTC").to_pydatetime()
    end_ts = pd.Timestamp(end, tz="UTC").to_pydatetime()

    cursor = coll.find(
        {
            "meta": {"symbol": symbol, "timeframe": timeframe},
            "timestamp": {"$gte": start_ts, "$lt": end_ts},
        },
        {"_id": 0, "timestamp": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
    ).sort("timestamp", 1)

    rows = list(cursor)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).rename(columns={
        "timestamp": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    })
    df["Date"] = pd.to_datetime(df["Date"], utc=True)
    df = df.set_index("Date")
    return df


def store_ohlcv(symbol: str, timeframe: str, df: pd.DataFrame) -> int:
    """Bulk-insert OHLCV candles. Returns the number of new documents stored."""
    if df.empty:
        return 0

    _ensure_collection()
    coll = _get_db()[_COLLECTION]
    meta = {"symbol": symbol, "timeframe": timeframe}

    docs = [
        {
            "timestamp": ts.to_pydatetime(),
            "meta": meta,
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row["Volume"]),
        }
        for ts, row in df.iterrows()
    ]

    batch_size = 5000
    inserted = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i : i + batch_size]
        result = coll.insert_many(batch, ordered=False)
        inserted += len(result.inserted_ids)

    logger.info("Stored %d candles for %s/%s", inserted, symbol, timeframe)
    return inserted
