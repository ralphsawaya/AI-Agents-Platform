"""Shared data models used across trading agents."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class MarketRegimeType(str, Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"


class StrategyName(str, Enum):
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    SCALPING = "scalping"


class TradeAction(str, Enum):
    BUY = "buy"
    SELL = "sell"
    CLOSE = "close"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class Indicators:
    adx: float = 0.0
    atr: float = 0.0
    atr_pct: float = 0.0
    bb_width: float = 0.0
    bb_upper: float = 0.0
    bb_lower: float = 0.0
    bb_middle: float = 0.0
    ema_fast: float = 0.0
    ema_mid: float = 0.0
    ema_slow: float = 0.0
    ema_fast_slope: float = 0.0
    ema_mid_slope: float = 0.0
    ema_slow_slope: float = 0.0
    rsi: float = 0.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_hist: float = 0.0
    volume_ratio: float = 0.0
    current_price: float = 0.0


@dataclass
class MarketRegime:
    regime: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    indicators: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TradeSignal:
    strategy_name: str = ""
    action: str = ""
    ticker: str = "BTCUSDT"
    price: float = 0.0


@dataclass
class RiskParams:
    position_size: float = 0.0
    stop_loss_price: float = 0.0
    take_profit_price: float = 0.0
    risk_amount: float = 0.0
    approved: bool = False
    rejection_reason: str = ""


@dataclass
class Order:
    order_id: str = ""
    side: str = ""
    quantity: float = 0.0
    price: float = 0.0
    fill_price: float = 0.0
    status: str = "pending"
    order_type: str = "MARKET"
    stop_loss_order_id: str = ""
