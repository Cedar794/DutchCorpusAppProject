from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LemmaSummary:
    lemma_id: int
    lemma: str
    lemma_norm: str
    level: int | None
    frequency: int


@dataclass(frozen=True)
class FormSummary:
    form_id: int
    form: str
    form_norm: str
    lemma: LemmaSummary
    is_canonical: bool
    frequency: int


@dataclass(frozen=True)
class LookupCandidate:
    lemma: LemmaSummary
    form_id: int | None
    form: str | None
    match_type: str
    score: float
    confidence: float

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "lemma_id": self.lemma.lemma_id,
            "entry_url": f"/entries/{self.lemma.lemma_id}",
            "lemma": self.lemma.lemma,
            "level": self.lemma.level,
            "form_id": self.form_id,
            "form": self.form,
            "match_type": self.match_type,
            "score": round(self.score, 6),
            "confidence": round(self.confidence, 6),
        }


@dataclass(frozen=True)
class SemanticCandidate:
    sense_id: int
    lemma_id: int
    lemma: str
    level: int | None
    definition_nl: str
    translation_zh: str
    translation_en: str
    vector_similarity: float
    frequency: int
    best_sense_id: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "best_sense_id", self.sense_id)


@dataclass(frozen=True)
class RelatedResult:
    lemma_id: int
    lemma: str
    relation_type: str
    source_result_lemma_id: int
    source_result_sense_id: int | None
    source: str
    score: float


@dataclass(frozen=True)
class SearchLogRecord:
    query: str
    mode: str
    detected_language: str | None
    latency_ms: int
    candidate_count: int | None
    result_count: int
    top_lemma_ids: list[int]
    top_sense_ids: list[int]
    cache_hit: bool
    embedding_model: str | None
    index_version: str | None
