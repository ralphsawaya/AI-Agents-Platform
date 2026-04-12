"""Standalone entry point for the Flight Search agent."""

from agent_flight.agent import build_flight_graph


def main():
    graph = build_flight_graph()
    result = graph.invoke({
        "query": "Direct flight from Paris to Milan with Air France under 400 euros",
        "query_embedding": [], "results": [], "status": "pending",
    })
    print(f"Found {len(result.get('results', []))} flights")
    for r in result.get("results", []):
        print(f"  {r.get('airline')} {r.get('flight_number')} — €{r.get('price_eur')}")
    return result


if __name__ == "__main__":
    main()
