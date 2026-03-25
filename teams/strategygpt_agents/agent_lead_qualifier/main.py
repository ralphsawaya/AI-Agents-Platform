"""Standalone entry point for the Lead Qualifier agent."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from agent_lead_qualifier.agent import build_lead_qualifier_graph

logger = get_logger("agent_lead_qualifier")


def run():
    logger.info("Lead Qualifier starting")

    graph = build_lead_qualifier_graph()
    result = graph.invoke({
        "new_leads": [],
        "qualified_leads": [],
        "invalid_leads": [],
        "qualified_count": 0,
        "scripts_generated": 0,
        "status": "pending",
    })

    logger.info(
        "Lead Qualifier complete — qualified=%d, scripts=%d",
        result.get("qualified_count", 0),
        result.get("scripts_generated", 0),
    )
    return result


if __name__ == "__main__":
    run()
