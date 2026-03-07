"""Prompt templates for the Risk Manager agent (reserved for future LLM-based risk assessment)."""

RISK_ASSESSMENT_PROMPT = """You are a risk manager for a BTC/USDT spot trading system. Evaluate whether this trade should be approved.

TRADE DETAILS:
- Action: {action}
- Position Size: {position_size} BTC ({position_value} USDT)
- Entry Price: {entry_price}
- Stop Loss: {stop_loss}
- Take Profit: {take_profit}

ACCOUNT STATE:
- Balance: {balance} USDT
- Current Exposure: {exposure} USDT
- Open Orders: {open_orders}
- Portfolio Drawdown: {drawdown}%

Respond with APPROVE or REJECT followed by a brief reason."""
