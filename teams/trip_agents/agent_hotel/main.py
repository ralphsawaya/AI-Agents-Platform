"""Standalone entry point for the Hotel Search agent."""

from agent_hotel.agent import build_hotel_graph


def main():
    graph = build_hotel_graph()
    result = graph.invoke({
        "query": "4-star hotel in Milan with pool and gym",
        "query_embedding": [], "results": [], "status": "pending",
    })
    print(f"Found {len(result.get('results', []))} hotels")
    for r in result.get("results", []):
        print(f"  {r.get('name')} — {r.get('stars')}* — EUR{r.get('price_per_night_eur')}/night")
    return result


if __name__ == "__main__":
    main()
