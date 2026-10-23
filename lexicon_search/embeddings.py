from __future__ import annotations

import hashlib
import math
import unicodedata
import asyncio
import random
from collections.abc import Sequence
from typing import Any

import httpx


class BailianEmbeddingClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        dimension: int,
        http_client: httpx.AsyncClient | None = None,
        max_retries: int = 3,
        sleep=asyncio.sleep,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimension = dimension
        self.http_client = http_client
        self.max_retries = max_retries
        self.sleep = sleep

    async def _post(self, client, payload, headers):
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.post('/embeddings', json=payload, headers=headers)
                response.raise_for_status()
                return response
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in {429, 500, 502, 503, 504}:
                    raise
                if attempt == self.max_retries:
                    raise
                delay = min(2 ** attempt + random.random(), 30)
                if isinstance(exc, httpx.HTTPStatusError):
                    try:
                        delay = max(delay, min(float(exc.response.headers.get('Retry-After', 0)), 60))
                    except ValueError:
                        pass
                await self.sleep(delay)

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if len(texts) > 10:
            raise ValueError("text-embedding-v4 batch size must be 10 or fewer")

        payload: dict[str, Any] = {
            "model": self.model,
            "input": list(texts),
            "dimensions": self.dimension,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        if self.http_client is None:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
                response = await self._post(client, payload, headers)
        else:
            response = await self._post(self.http_client, payload, headers)

        response.raise_for_status()
        body = response.json()
        try:
            data = body['data']
            if not isinstance(data, list) or any(type(item['index']) is not int for item in data):
                raise ValueError('Invalid embedding indexes')
            vectors_by_index = {
                item['index']: [float(value) for value in item['embedding']]
                for item in data
            }
            if len(data) != len(texts) or set(vectors_by_index) != set(range(len(texts))):
                raise ValueError('Embedding response has missing or duplicate indexes')
        except (KeyError, TypeError, OverflowError) as exc:
            raise ValueError('Invalid embedding response') from exc

        vectors: list[list[float]] = []
        for index in range(len(texts)):
            vector = vectors_by_index[index]
            if len(vector) != self.dimension or not all(math.isfinite(v) for v in vector) or not any(vector):
                raise ValueError(f"embedding response must have {self.dimension} dimensions")
            vectors.append(vector)
        return vectors

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]


class DemoEmbeddingClient:
    """Deterministic local embedder for demos when the real embedding service is unavailable."""

    def __init__(self, *, dimension: int = 1024) -> None:
        self.dimension = dimension

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_text(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            primary = int.from_bytes(digest[:4], "big") % self.dimension
            secondary = int.from_bytes(digest[4:8], "big") % self.dimension
            vector[primary] += 1.0
            vector[secondary] += 0.5
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFC", text.casefold())
    tokens: list[str] = []
    current: list[str] = []
    for char in normalized:
        if char.isalnum():
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current.clear()
    if current:
        tokens.append("".join(current))
    return tokens
