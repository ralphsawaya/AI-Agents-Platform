"""Prompt templates for the Lead Sourcer agent."""

CATEGORY_EXPANSION_PROMPT = """Given the target location "{city}" and the broad business category "{category}",
generate a list of 5 specific search queries that would find small and medium businesses
in that category on Google Maps. Return only the queries, one per line.

Example for "restaurant" in "Austin, TX":
restaurant Austin TX
cafe Austin TX
diner Austin TX
bakery Austin TX
food truck Austin TX

Queries:"""
