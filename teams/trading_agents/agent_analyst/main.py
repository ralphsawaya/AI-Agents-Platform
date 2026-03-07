"""Standalone entry point for the Analyst agent."""

from agent_analyst.agent import build_analyst_graph


def main():
    graph = build_analyst_graph()
    result = graph.invoke({
        "ohlcv_4h": [],
        "ohlcv_1h": [],
        "indicators": {},
        "regime": "",
        "confidence": 0.0,
        "reasoning": "",
        "status": "pending",
    })
    print(f"Regime: {result['regime']} (confidence: {result['confidence']})")
    print(f"Reasoning: {result['reasoning']}")
    return result


if __name__ == "__main__":
    main()
