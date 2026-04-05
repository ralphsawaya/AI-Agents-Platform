"""Prompt templates for the Analyst agent."""

REGIME_CLASSIFICATION_PROMPT = """You are an expert cryptocurrency market analyst. Analyze the following BTC/USDT technical indicators and classify the current market regime.

CURRENT INDICATORS:
- Price: ${price}
- ADX (14): {adx} (trend strength: >22 = trending, <22 = weak/no trend)
- ATR (14): {atr} ({atr_pct}% of price)
- Bollinger Bands (20,2): Upper={bb_upper}, Middle={bb_middle}, Lower={bb_lower}, Width={bb_width}
- EMA(9): {ema_fast} (slope: {ema_fast_slope}%)
- EMA(21): {ema_mid} (slope: {ema_mid_slope}%)
- EMA(50): {ema_slow} (slope: {ema_slow_slope}%)
- RSI (14): {rsi}
- MACD: {macd}, Signal: {macd_signal}, Histogram: {macd_hist}
- Volume Ratio (vs 20-period MA): {volume_ratio}x

CLASSIFICATION RULES (4 regimes):
1. UPTREND: ADX > 22, EMA(9) > EMA(21) > EMA(50) (triple alignment), EMA(50) slope positive, MACD above signal. Sustained directional move upward.
2. DOWNTREND: ADX > 22, EMA(9) < EMA(21) < EMA(50) (reverse alignment), EMA(50) slope negative, MACD below signal. Sustained directional move downward.
3. RANGING: ADX < 22 or EMAs not aligned, price oscillating near BB middle, RSI between 35-65. Sideways/mean-reverting market with low directional bias.
4. VOLATILE_BREAKOUT: ATR > 2.5% of price, BB width > 4%, volume ratio > 1.5x. High-volatility expansion from consolidation, can occur in any direction.

PRIORITY: Check volatile_breakout first (rare, highest priority). Then check uptrend/downtrend. Default to ranging if signals are mixed.

Respond in EXACTLY this format (3 lines, no extra text):
REGIME: <one of: uptrend, downtrend, ranging, volatile_breakout>
CONFIDENCE: <percentage 0-100>
REASONING: <one paragraph explaining the key factors>"""


REGIME_SYSTEM_PROMPT = """You are a quantitative market analyst specializing in cryptocurrency markets. You analyze technical indicators to determine the current market regime for BTC/USDT. Your classifications directly drive automated strategy selection, so accuracy is critical. Always err on the side of caution — if signals are mixed, classify as 'ranging' rather than forcing a trend call. Use the simplified 4-regime model: uptrend, downtrend, ranging, volatile_breakout."""
