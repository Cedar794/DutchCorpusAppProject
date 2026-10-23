from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

from lexicon_search.db import vector_literal


@dataclass(frozen=True)
class SenseEmbeddingInput:
    sense_id: int
    definition_nl: str
    translation_zh: str
    translation_en: str
    lemma: str = ''
    pos: str = ''
    level: int | None = None


class EmbeddingRepository(Protocol):
    async def load_senses_for_embedding(self, limit=None) -> list[SenseEmbeddingInput]:
        raise NotImplementedError

    async def load_embedding_hashes(self, model, dimension, version) -> dict[int, str]:
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
    def clean(text):
        return ' '.join(re.sub(r'#aigc\b', '', text, flags=re.IGNORECASE).split())
    if row.lemma:
        parts.append(f'lemma: {clean(row.lemma)}')
    if row.pos:
        parts.append(f'pos: {clean(row.pos)}')
    if row.definition_nl.strip():
        parts.append(f"definition_nl: {clean(row.definition_nl)}")
    if row.translation_zh.strip():
        parts.append(f"translation_zh: {clean(row.translation_zh)}")
    if row.translation_en.strip():
        parts.append(f"translation_en: {clean(row.translation_en)}")
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
    limit: int | None = None,
    progress=None,
) -> dict[str, int]:
    if not 1 <= batch_size <= 10:
        raise ValueError('batch_size must be between 1 and 10')
    inputs = await repository.load_senses_for_embedding(limit=limit)
    hashes = await repository.load_embedding_hashes(embedding_model, embedding_dim, index_version)
    embedded = 0
    skipped = 0
    unchanged = 0

    for start in range(0, len(inputs), batch_size):
        batch = inputs[start : start + batch_size]
        texts = [build_embedding_text(row) for row in batch]
        usable = []
        for row, text in zip(batch, texts, strict=True):
            if not row.definition_nl.strip():
                skipped += 1
            elif hashes.get(row.sense_id) == hash_embedding_text(text):
                unchanged += 1
            else:
                usable.append((row, text))
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
        if progress:
            progress({'selected': len(inputs), 'embedded': embedded, 'unchanged': unchanged,
                      'skipped': skipped, 'last_sense_id': usable[-1][0].sense_id})

    return {'selected': len(inputs), "embedded": embedded, "skipped": skipped, 'unchanged': unchanged}
