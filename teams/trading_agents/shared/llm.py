"""Multi-provider LLM wrapper for trading agents.

Supports Google Gemini, Anthropic Claude, and DeepSeek.
The active provider/model is read from MongoDB (trading_config collection)
and falls back to environment variables.
"""

from __future__ import annotations

from shared.config import LLM_TEMPERATURE, MAX_TOKENS
from shared.mongo import load_llm_config


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

class _GeminiLLM:
    def __init__(self, model: str, api_key: str):
        from google import genai
        self._types = genai.types
        self._client = genai.Client(api_key=api_key)
        self.model = model

    def invoke(self, prompt: str, system: str = "") -> str:
        config = self._types.GenerateContentConfig(
            temperature=LLM_TEMPERATURE,
            max_output_tokens=MAX_TOKENS,
        )
        if system:
            config.system_instruction = system
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return response.text


class _ClaudeLLM:
    def __init__(self, model: str, api_key: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def invoke(self, prompt: str, system: str = "") -> str:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "temperature": LLM_TEMPERATURE,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        response = self._client.messages.create(**kwargs)
        return response.content[0].text


class _DeepSeekLLM:
    def __init__(self, model: str, api_key: str):
        from openai import OpenAI
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
        )
        self.model = model

    def invoke(self, prompt: str, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=LLM_TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        return response.choices[0].message.content


_PROVIDER_MAP = {
    "gemini": _GeminiLLM,
    "claude": _ClaudeLLM,
    "deepseek": _DeepSeekLLM,
}


def get_llm():
    """Return an LLM instance based on the current trading config (MongoDB → env fallback)."""
    provider, model, api_key = load_llm_config()
    cls = _PROVIDER_MAP.get(provider)
    if cls is None:
        raise ValueError(f"Unknown LLM provider: {provider}")
    return cls(model, api_key)
