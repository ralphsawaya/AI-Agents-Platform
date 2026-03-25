"""Standalone entry point for the Lead Sourcer agent."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.utils import load_args, parse_categories
from shared.config import MIN_REVIEWS, MIN_RATING, MAX_LEADS_PER_RUN
from agent_lead_sourcer.agent import build_lead_sourcer_graph

logger = get_logger("agent_lead_sourcer")


def run():
    args = load_args()
    city = args.get("city", "Austin, TX")
    categories = parse_categories(args.get("categories", "restaurant,plumber"))

    logger.info("Lead Sourcer starting — city=%s, categories=%s", city, categories)

    graph = build_lead_sourcer_graph()
    result = graph.invoke({
        "city": city,
        "categories": categories,
        "min_reviews": int(args.get("min_reviews", MIN_REVIEWS)),
        "min_rating": float(args.get("min_rating", MIN_RATING)),
        "max_leads": int(args.get("max_leads", MAX_LEADS_PER_RUN)),
        "raw_places": [],
        "filtered_leads": [],
        "stored_count": 0,
        "status": "pending",
    })

    logger.info("Lead Sourcer complete — stored %d leads", result.get("stored_count", 0))
    return result


if __name__ == "__main__":
    run()
