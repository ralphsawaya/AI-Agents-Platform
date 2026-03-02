"""LLM wrapper.

In a real deployment this would use langchain_openai.ChatOpenAI.
For this sample agent, we provide a mock that works without API keys
so the platform can be tested end-to-end.
"""

import os

from shared.config import LLM_MODEL, LLM_TEMPERATURE, MAX_TOKENS


class MockLLM:
    """Deterministic mock LLM for demo/testing purposes."""

    def __init__(self, model: str = LLM_MODEL):
        self.model = model

    def invoke(self, prompt: str) -> str:
        if "summarize" in prompt.lower() or "summary" in prompt.lower():
            return (
                "This is a concise summary of the provided text. "
                "The key points have been distilled into a shorter format "
                "while preserving the essential meaning and context."
            )
        if "report" in prompt.lower():
            return (
                "# Report\\n\\n"
                "## Executive Summary\\n"
                "Based on the analysis, the following conclusions were drawn.\\n\\n"
                "## Key Findings\\n"
                "1. The data indicates positive trends.\\n"
                "2. Areas for improvement were identified.\\n"
                "3. Recommendations are provided below.\\n\\n"
                "## Recommendations\\n"
                "Continue monitoring and iterate on the current approach."
            )
        return f"LLM response to: {prompt[:100]}"


def get_llm():
    """Return an LLM instance.

    Uses the real OpenAI client if OPENAI_API_KEY is set,
    otherwise falls back to MockLLM for testing.
    """
    if os.getenv("OPENAI_API_KEY"):
        try:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=LLM_MODEL,
                temperature=LLM_TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
        except ImportError:
            pass
    return MockLLM()
