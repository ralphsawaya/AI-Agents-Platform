"""Google Gemini LLM wrapper for trading agents."""

from google import genai
from google.genai import types

from shared.config import GEMINI_API_KEY, LLM_MODEL, LLM_TEMPERATURE, MAX_TOKENS

_client = genai.Client(api_key=GEMINI_API_KEY)


class GeminiLLM:
    """Wrapper around the Google GenAI SDK that exposes a simple .invoke() API."""

    def __init__(self, model: str = LLM_MODEL):
        self.model = model
        self.temperature = LLM_TEMPERATURE
        self.max_tokens = MAX_TOKENS

    def invoke(self, prompt: str, system: str = "") -> str:
        config = types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
        )
        if system:
            config.system_instruction = system
        response = _client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return response.text


def get_llm() -> GeminiLLM:
    """Return a configured Gemini LLM instance."""
    return GeminiLLM()
