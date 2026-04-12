"""Voyage AI embedding client.

Wraps the Voyage AI REST API to generate embeddings for text queries
used in MongoDB Atlas $vectorSearch.
"""

import requests

from shared.config import VOYAGE_MODEL
from shared.mongo import load_voyage_api_key
from shared.logger import get_logger

logger = get_logger("shared.voyage")

VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"


def embed_texts(texts: list[str], model: str | None = None,
                input_type: str = "document") -> list[list[float]]:
    """Embed a batch of texts using the Voyage AI API."""
    api_key = load_voyage_api_key()
    if not api_key:
        raise ValueError(
            "VOYAGE_AI_API_KEY is not configured. "
            "Set it in the Settings tab or as an environment variable."
        )
    response = requests.post(
        VOYAGE_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model or VOYAGE_MODEL,
            "input": texts,
            "input_type": input_type,
        },
        timeout=60,
    )
    response.raise_for_status()
    return [item["embedding"] for item in response.json()["data"]]


def embed_query(text: str, model: str | None = None) -> list[float]:
    """Embed a single search query."""
    return embed_texts([text], model=model, input_type="query")[0]


def embed_document(text: str, model: str | None = None) -> list[float]:
    """Embed a single document."""
    return embed_texts([text], model=model, input_type="document")[0]
