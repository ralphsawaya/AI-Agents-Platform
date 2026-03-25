"""Prompt templates for the Lead Qualifier agent."""

SCRIPT_SYSTEM_PROMPT = (
    "You are a friendly, professional sales script writer for an AI voice assistant. "
    "You write concise, warm phone scripts that pitch a free website creation offer "
    "to small business owners. The script should sound natural and conversational, "
    "not robotic. Keep it under 200 words."
)

SCRIPT_GENERATION_PROMPT = """Write a personalised AI voice call script for the following business.

BUSINESS DETAILS:
- Name: {business_name}
- Type: {category}
- City: {city}
- Google Rating: {rating}/5 ({review_count} reviews)

THE OFFER:
We will build the owner a professional website within 24 hours, completely free, with zero commitment.
If they are satisfied with the website, they pay a one-time fixed fee.
If not satisfied, there is absolutely no charge and no obligation.

SCRIPT REQUIREMENTS:
1. Greet by business name
2. Briefly compliment their Google reviews / rating
3. Note that we noticed they don't have a website yet
4. Present the free website offer clearly
5. Ask if they would be interested
6. If yes, confirm the best email to send the finished website to
7. If no, thank them politely and end the call

Return only the script text, no headers or labels."""
