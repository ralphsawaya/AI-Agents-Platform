"""Generate personalised call scripts for each qualified lead using LLM."""

from shared.llm import get_llm
from shared.logger import get_logger
from shared.mongo import get_leads_collection
from agent_lead_qualifier.prompts.prompt_templates import SCRIPT_GENERATION_PROMPT, SCRIPT_SYSTEM_PROMPT

logger = get_logger("lead_qualifier.generate_scripts")


def generate_scripts(state: dict) -> dict:
    if state.get("status") in ("error", "no_leads"):
        return state

    qualified = state.get("qualified_leads", [])
    if not qualified:
        return {"scripts_generated": 0, "status": "no_qualified_leads"}

    llm = get_llm()
    col = get_leads_collection()
    generated = 0

    for lead in qualified:
        prompt = SCRIPT_GENERATION_PROMPT.format(
            business_name=lead["business_name"],
            category=lead.get("category", "business"),
            city=lead.get("city", ""),
            rating=lead.get("rating", 0),
            review_count=lead.get("review_count", 0),
        )

        try:
            script = llm.invoke(prompt, system=SCRIPT_SYSTEM_PROMPT)
            col.update_one(
                {"place_id": lead["place_id"]},
                {"$set": {"call_script": script, "status": "qualified"}},
            )
            generated += 1
            logger.info("Script generated for %s", lead["business_name"])
        except Exception as exc:
            logger.error("Script generation failed for %s: %s", lead["business_name"], exc)

    logger.info("Generated %d call scripts out of %d qualified leads", generated, len(qualified))
    return {"scripts_generated": generated, "status": "scripts_generated"}
