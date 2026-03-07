"""Standalone entry point for the Risk Manager agent."""

from agent_risk_manager.agent import build_risk_manager_graph


def main():
    graph = build_risk_manager_graph()
    result = graph.invoke({
        "signal": {"action": "buy", "price": 50000.0, "ticker": "BTCUSDT"},
        "account_balance": 0.0,
        "btc_balance": 0.0,
        "current_price": 0.0,
        "current_exposure": 0.0,
        "open_orders_count": 0,
        "atr": 0.0,
        "position_size": 0.0,
        "stop_loss_price": 0.0,
        "take_profit_price": 0.0,
        "risk_amount": 0.0,
        "approved": False,
        "rejection_reason": "",
        "dry_run": True,
        "status": "pending",
    })
    print(f"Approved: {result['approved']}")
    print(f"Position size: {result['position_size']}")
    return result


if __name__ == "__main__":
    main()
