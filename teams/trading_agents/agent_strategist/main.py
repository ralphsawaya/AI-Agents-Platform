"""Standalone entry point for the Strategist agent."""

from agent_strategist.agent import build_strategist_graph


def main():
    graph = build_strategist_graph()
    result = graph.invoke({
        "regime": "ranging",
        "confidence": 0.8,
        "indicators": {},
        "strategy_candidates": [],
        "selected_strategy": "",
        "reasoning": "",
        "status": "pending",
    })
    print(f"Selected strategy: {result['selected_strategy']}")
    print(f"Reasoning: {result['reasoning']}")
    return result


if __name__ == "__main__":
    main()
