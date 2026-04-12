"""Multi-provider LLM wrapper for trip agents.

Supports Google Gemini, Anthropic Claude, DeepSeek, Groq, and OpenAI.
The active provider/model is read from MongoDB (team_settings collection)
and falls back to environment variables.

Includes retry logic (tenacity) and singleton client caching per provider+model.
"""

from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from shared.config import LLM_TEMPERATURE, MAX_TOKENS
from shared.mongo import load_llm_config
from shared.logger import get_logger

logger = get_logger("shared.llm")

LLM_TIMEOUT = 30


def _llm_retry():
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        before_sleep=lambda rs: logger.warning(
            "LLM call failed (attempt %d), retrying: %s", rs.attempt_number, rs.outcome.exception()
        ),
    )


class _GeminiLLM:
    def __init__(self, model: str, api_key: str):
        from google import genai
        self._types = genai.types
        self._client = genai.Client(api_key=api_key)
        self.model = model

    @_llm_retry()
    def invoke(self, prompt: str, system: str = "") -> str:
        config = self._types.GenerateContentConfig(
            temperature=LLM_TEMPERATURE, max_output_tokens=MAX_TOKENS,
        )
        if system:
            config.system_instruction = system
        response = self._client.models.generate_content(
            model=self.model, contents=prompt, config=config,
        )
        return response.text


class _ClaudeLLM:
    def __init__(self, model: str, api_key: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=LLM_TIMEOUT)
        self.model = model

    @_llm_retry()
    def invoke(self, prompt: str, system: str = "") -> str:
        kwargs: dict = {
            "model": self.model, "max_tokens": MAX_TOKENS,
            "temperature": LLM_TEMPERATURE,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        return self._client.messages.create(**kwargs).content[0].text


class _DeepSeekLLM:
    def __init__(self, model: str, api_key: str):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=LLM_TIMEOUT)
        self.model = model

    @_llm_retry()
    def invoke(self, prompt: str, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._client.chat.completions.create(
            model=self.model, messages=messages,
            temperature=LLM_TEMPERATURE, max_tokens=MAX_TOKENS,
        ).choices[0].message.content


class _GroqLLM:
    def __init__(self, model: str, api_key: str):
        from groq import Groq
        self._client = Groq(api_key=api_key, timeout=LLM_TIMEOUT)
        self.model = model

    @_llm_retry()
    def invoke(self, prompt: str, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._client.chat.completions.create(
            messages=messages, model=self.model,
            temperature=LLM_TEMPERATURE, max_tokens=MAX_TOKENS,
        ).choices[0].message.content


class _OpenAILLM:
    def __init__(self, model: str, api_key: str):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, timeout=LLM_TIMEOUT)
        self.model = model

    @_llm_retry()
    def invoke(self, prompt: str, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._client.chat.completions.create(
            model=self.model, messages=messages,
            temperature=LLM_TEMPERATURE, max_tokens=MAX_TOKENS,
        ).choices[0].message.content


_PROVIDER_MAP = {
    "gemini": _GeminiLLM, "claude": _ClaudeLLM, "deepseek": _DeepSeekLLM,
    "groq": _GroqLLM, "openai": _OpenAILLM,
}

_llm_cache: dict[tuple[str, str], object] = {}


def get_llm():
    """Return a cached LLM instance based on team_settings (MongoDB -> env fallback)."""
    provider, model, api_key = load_llm_config()
    cache_key = (provider, model)
    if cache_key in _llm_cache:
        return _llm_cache[cache_key]
    cls = _PROVIDER_MAP.get(provider)
    if cls is None:
        raise ValueError(f"Unknown LLM provider: {provider}")
    instance = cls(model, api_key)
    _llm_cache[cache_key] = instance
    logger.info("Created and cached LLM client: %s/%s", provider, model)
    return instance
