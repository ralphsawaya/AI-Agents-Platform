"""Prompt templates for agent_alpha."""

SUMMARIZE_TEMPLATE = """Please summarize the following text concisely.
Preserve key points and main arguments.

Text:
{text}

Summary:"""

BULLET_SUMMARY_TEMPLATE = """Extract the key points from the following text
as a bulleted list:

Text:
{text}

Key Points:"""
