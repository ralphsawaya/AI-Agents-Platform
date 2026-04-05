"""Standalone entry point for the Executor agent."""

from agent_executor.agent import build_executor_graph


def main():
    graph = build_executor_graph()
    result = graph.invoke({
        "signal": {"action": "buy", "price": 50000.0, "ticker": "BTCUSDT", "strategy_name": "ema_trend"},
        "risk_params": {"position_size": 0.001, "stop_loss_price": 49000.0, "take_profit_price": 52000.0, "approved": True},
        "dry_run": True,
        "order_id": "",
        "fill_price": 0.0,
        "order_status": "",
        "stop_loss_order_id": "",
        "trade_record": {},
        "status": "pending",
    })
    print(f"Order status: {result['order_status']}")
    return result


if __name__ == "__main__":
    main()
