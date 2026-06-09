from __future__ import annotations

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
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimension = dimension
        self.http_client = http_client

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
                response = await client.post("/embeddings", json=payload, headers=headers)
        else:
            response = await self.http_client.post("/embeddings", json=payload, headers=headers)

        response.raise_for_status()
        body = response.json()
        vectors_by_index = {
            int(item["index"]): [float(value) for value in item["embedding"]]
            for item in body.get("data", [])
        }

        vectors: list[list[float]] = []
        for index in range(len(texts)):
            vector = vectors_by_index[index]
            if len(vector) != self.dimension:
                raise ValueError(f"embedding response must have {self.dimension} dimensions")
            vectors.append(vector)
        return vectors

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]
