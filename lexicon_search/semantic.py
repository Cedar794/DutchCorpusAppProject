from __future__ import annotations

from typing import Protocol

from lexicon_search.models import SemanticCandidate
from lexicon_search.scoring import semantic_score
from lexicon_search.query_rewrite import PROMPT_VERSION, RewriteResult
from lexicon_search.entry_details import public_text


class QueryEmbedder(Protocol):
    async def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError


class SemanticRepository(Protocol):
    async def match_senses(
        self,
        embedding: list[float],
        candidate_count: int,
        index_version: str,
    ) -> list[SemanticCandidate]:
        raise NotImplementedError


def candidate_count_for_limit(limit: int) -> int:
    return min(max(limit * 5, 50), 250)


class SemanticSearchEngine:
    def __init__(self, embedder: QueryEmbedder, repository: SemanticRepository, index_version: str, *, rewriter=None) -> None:
        self.embedder = embedder
        self.repository = repository
        self.index_version = index_version
        self.rewriter = rewriter

    async def search(self, query: str, limit: int) -> dict:
        rewrite = await self.rewriter.rewrite(query) if self.rewriter else RewriteResult(query,'disabled')
        embedding = await self.embedder.embed_text(rewrite.query)
        candidates = await self.repository.match_senses(
            embedding=embedding,
            candidate_count=candidate_count_for_limit(limit),
            index_version=self.index_version,
        )
        by_lemma: dict[int, tuple[SemanticCandidate, float, dict[str, float]]] = {}
        for candidate in candidates:
            breakdown = semantic_score(
                vector_similarity=candidate.vector_similarity,
                frequency=candidate.frequency,
                level=candidate.level,
            )
            existing = by_lemma.get(candidate.lemma_id)
            if existing is None or breakdown.score > existing[1]:
                by_lemma[candidate.lemma_id] = (candidate, breakdown.score, breakdown.reasons)

        ordered = sorted(by_lemma.values(), key=lambda item: (-item[1], item[0].lemma))[:limit]
        return {
            "results": [
                {
                    "lemma_id": candidate.lemma_id,
                    "entry_url": f"/entries/{candidate.lemma_id}",
                    "lemma": candidate.lemma,
                    "level": candidate.level,
                    "score": round(score, 6),
                    "matched_sense": {
                        "sense_id": candidate.sense_id,
                        "definition_nl": public_text(candidate.definition_nl),
                        "translation_zh": public_text(candidate.translation_zh),
                        "translation_en": public_text(candidate.translation_en),
                        "semantic_score": round(candidate.vector_similarity, 6),
                    },
                    "matched_reason": {key: round(value, 6) for key, value in reasons.items()},
                }
                for candidate, score, reasons in ordered
            ],
            "candidate_count": candidate_count_for_limit(limit),
            "query_rewrite": {"query":rewrite.query, "status":rewrite.status,
                              "model":self.rewriter.model if self.rewriter else None,
                              "prompt_version":PROMPT_VERSION if self.rewriter else None},
        }
