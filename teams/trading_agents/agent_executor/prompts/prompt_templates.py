"""Prompt templates for the Executor agent (reserved for future LLM-based execution decisions)."""

EXECUTION_SUMMARY_PROMPT = """Summarize the following trade execution for logging:
- Action: {action}
- Ticker: {ticker}
- Quantity: {quantity}
- Fill Price: {fill_price}
- Stop Loss: {stop_loss}
- Take Profit: {take_profit}
- Status: {status}

Provide a one-sentence summary."""
