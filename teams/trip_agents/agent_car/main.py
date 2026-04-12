"""Standalone entry point for the Car Rental Search agent."""

from agent_car.agent import build_car_graph


def main():
    graph = build_car_graph()
    result = graph.invoke({
        "query": "Black 2-door BMW automatic transmission",
        "query_embedding": [], "results": [], "status": "pending",
    })
    print(f"Found {len(result.get('results', []))} car rentals")
    for r in result.get("results", []):
        print(f"  {r.get('make')} {r.get('model')} — EUR{r.get('price_per_day_eur')}/day")
    return result


if __name__ == "__main__":
    main()
