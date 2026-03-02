"""Groq LLM wrapper for TeamAB agents."""

from groq import Groq

from shared.config import GROQ_API_KEY, LLM_MODEL, LLM_TEMPERATURE, MAX_TOKENS

_client = Groq(api_key=GROQ_API_KEY)


class GroqLLM:
    """Wrapper around the Groq SDK that exposes a simple .invoke() API."""

    def __init__(self, model: str = LLM_MODEL):
        self.model = model
        self.temperature = LLM_TEMPERATURE
        self.max_tokens = MAX_TOKENS

    def invoke(self, prompt: str) -> str:
        response = _client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content


def get_llm() -> GroqLLM:
    """Return a configured Groq LLM instance."""
    return GroqLLM()
