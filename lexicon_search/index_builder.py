from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from lexicon_search.db import vector_literal


@dataclass(frozen=True)
class SenseEmbeddingInput:
    sense_id: int
    definition_nl: str
    translation_zh: str
    translation_en: str


class EmbeddingRepository(Protocol):
    async def load_senses_for_embedding(self) -> list[SenseEmbeddingInput]:
        raise NotImplementedError

    async def upsert_sense_embeddings(
        self,
        rows: list[tuple[int, str, int, str, str, str, str]],
    ) -> None:
        raise NotImplementedError


class EmbeddingClient(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


def build_embedding_text(row: SenseEmbeddingInput) -> str:
    parts = []
    if row.definition_nl.strip():
        parts.append(f"definition_nl: {row.definition_nl.strip()}")
    if row.translation_zh.strip():
        parts.append(f"translation_zh: {row.translation_zh.strip()}")
    if row.translation_en.strip():
        parts.append(f"translation_en: {row.translation_en.strip()}")
    return "\n".join(parts)


def hash_embedding_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def rebuild_embeddings(
    *,
    repository: EmbeddingRepository,
    embedding_client: EmbeddingClient,
    embedding_model: str,
    embedding_dim: int,
    index_version: str,
    batch_size: int = 10,
) -> dict[str, int]:
    inputs = await repository.load_senses_for_embedding()
    embedded = 0
    skipped = 0

    for start in range(0, len(inputs), batch_size):
        batch = inputs[start : start + batch_size]
        texts = [build_embedding_text(row) for row in batch]
        usable = [(row, text) for row, text in zip(batch, texts, strict=True) if text.strip()]
        skipped += len(batch) - len(usable)
        if not usable:
            continue

        vectors = await embedding_client.embed_texts([text for _, text in usable])
        upsert_rows = []
        for (row, text), vector in zip(usable, vectors, strict=True):
            upsert_rows.append(
                (
                    row.sense_id,
                    embedding_model,
                    embedding_dim,
                    vector_literal(vector, embedding_dim),
                    hash_embedding_text(text),
                    text[:500],
                    index_version,
                )
            )
        await repository.upsert_sense_embeddings(upsert_rows)
        embedded += len(upsert_rows)

    return {"embedded": embedded, "skipped": skipped}
