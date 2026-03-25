"""Orchestrator entry point for the StrategyGPT agent team.

Supports three modes via AGENT_ARGS:
  - mode=sourcing:  Runs Lead Sourcer -> Lead Qualifier
  - mode=outreach:  Runs Voice Caller on already-qualified leads
  - mode=full:      Runs the complete pipeline end-to-end
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.utils import load_args, parse_categories
from shared.config import MIN_REVIEWS, MIN_RATING, MAX_LEADS_PER_RUN, CALLS_PER_BATCH
from orchestrator.graph import build_sourcing_graph, build_outreach_graph, build_full_graph

logger = get_logger("orchestrator")


def main():
    args = load_args()
    mode = args.get("mode", "full")

    logger.info("=" * 60)
    logger.info("StrategyGPT Orchestrator — mode: %s", mode)
    logger.info("=" * 60)

    if mode == "sourcing":
        return run_sourcing(args)
    elif mode == "outreach":
        return run_outreach(args)
    elif mode == "full":
        return run_full(args)
    else:
        logger.error("Unknown mode: %s (expected 'sourcing', 'outreach', or 'full')", mode)
        return None


def run_sourcing(args: dict):
    """Run the sourcing pipeline: Lead Sourcer -> Lead Qualifier."""
    city = args.get("city", "Austin, TX")
    categories = parse_categories(args.get("categories", "restaurant,plumber"))

    logger.info("Starting sourcing pipeline — city=%s, categories=%s", city, categories)

    graph = build_sourcing_graph()
    result = graph.invoke({
        "city": city,
        "categories": categories,
        "min_reviews": int(args.get("min_reviews", MIN_REVIEWS)),
        "min_rating": float(args.get("min_rating", MIN_RATING)),
        "max_leads": int(args.get("max_leads", MAX_LEADS_PER_RUN)),
        "raw_places": [],
        "filtered_leads": [],
        "stored_count": 0,
        "qualified_count": 0,
        "scripts_generated": 0,
        "current_agent": "",
        "status": "pending",
    })

    logger.info("=" * 60)
    logger.info("Sourcing pipeline complete!")
    logger.info("Stored: %d leads", result.get("stored_count", 0))
    logger.info("Qualified: %d leads", result.get("qualified_count", 0))
    logger.info("Scripts generated: %d", result.get("scripts_generated", 0))
    logger.info("=" * 60)

    print("\n--- SOURCING RESULTS ---")
    print(f"Leads stored:      {result.get('stored_count', 0)}")
    print(f"Leads qualified:   {result.get('qualified_count', 0)}")
    print(f"Scripts generated: {result.get('scripts_generated', 0)}")

    return result


def run_outreach(args: dict):
    """Run the outreach pipeline: Voice Caller."""
    batch_size = int(args.get("batch_size", CALLS_PER_BATCH))
    lead_ids = args.get("lead_ids", "all")

    logger.info("Starting outreach pipeline — batch_size=%d, lead_ids=%s", batch_size, lead_ids)

    graph = build_outreach_graph()
    result = graph.invoke({
        "lead_ids": lead_ids,
        "batch_size": batch_size,
        "leads_to_call": [],
        "call_results": [],
        "interested_count": 0,
        "not_interested_count": 0,
        "no_answer_count": 0,
        "current_agent": "",
        "status": "pending",
    })

    logger.info("=" * 60)
    logger.info("Outreach pipeline complete!")
    logger.info("Interested: %d", result.get("interested_count", 0))
    logger.info("Not interested: %d", result.get("not_interested_count", 0))
    logger.info("No answer: %d", result.get("no_answer_count", 0))
    logger.info("=" * 60)

    print("\n--- OUTREACH RESULTS ---")
    print(f"Interested:      {result.get('interested_count', 0)}")
    print(f"Not interested:  {result.get('not_interested_count', 0)}")
    print(f"No answer:       {result.get('no_answer_count', 0)}")

    return result


def run_full(args: dict):
    """Run the full pipeline: Lead Sourcer -> Lead Qualifier -> Voice Caller."""
    city = args.get("city", "Austin, TX")
    categories = parse_categories(args.get("categories", "restaurant,plumber"))
    batch_size = int(args.get("batch_size", CALLS_PER_BATCH))

    logger.info(
        "Starting full pipeline — city=%s, categories=%s, batch_size=%d",
        city, categories, batch_size,
    )

    graph = build_full_graph()
    result = graph.invoke({
        "city": city,
        "categories": categories,
        "min_reviews": int(args.get("min_reviews", MIN_REVIEWS)),
        "min_rating": float(args.get("min_rating", MIN_RATING)),
        "max_leads": int(args.get("max_leads", MAX_LEADS_PER_RUN)),
        "batch_size": batch_size,
        "raw_places": [],
        "filtered_leads": [],
        "stored_count": 0,
        "qualified_count": 0,
        "scripts_generated": 0,
        "leads_to_call": [],
        "call_results": [],
        "interested_count": 0,
        "not_interested_count": 0,
        "no_answer_count": 0,
        "current_agent": "",
        "status": "pending",
    })

    logger.info("=" * 60)
    logger.info("Full pipeline complete!")
    logger.info("Stored: %d | Qualified: %d | Scripts: %d",
                result.get("stored_count", 0),
                result.get("qualified_count", 0),
                result.get("scripts_generated", 0))
    logger.info("Interested: %d | Not interested: %d | No answer: %d",
                result.get("interested_count", 0),
                result.get("not_interested_count", 0),
                result.get("no_answer_count", 0))
    logger.info("=" * 60)

    print("\n--- FULL PIPELINE RESULTS ---")
    print(f"Leads stored:      {result.get('stored_count', 0)}")
    print(f"Leads qualified:   {result.get('qualified_count', 0)}")
    print(f"Scripts generated: {result.get('scripts_generated', 0)}")
    print(f"Interested:        {result.get('interested_count', 0)}")
    print(f"Not interested:    {result.get('not_interested_count', 0)}")
    print(f"No answer:         {result.get('no_answer_count', 0)}")

    return result


if __name__ == "__main__":
    main()
