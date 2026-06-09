from __future__ import annotations

import time
from typing import Any

from lexicon_search.dictionary import DictionaryIndex
from lexicon_search.graph import rank_related_results
from lexicon_search.models import SearchLogRecord
from lexicon_search.normalization import normalize_query


class SearchService:
    def __init__(
        self,
        dictionary: DictionaryIndex,
        semantic_engine: Any,
        repository: Any,
        *,
        log_queries: bool,
        embedding_model: str,
        index_version: str,
    ) -> None:
        self.dictionary = dictionary
        self.semantic_engine = semantic_engine
        self.repository = repository
        self.log_queries = log_queries
        self.embedding_model = embedding_model
        self.index_version = index_version

    async def lookup(self, query: str, limit: int = 5) -> dict[str, Any]:
        start = time.perf_counter()
        candidates = self.dictionary.lookup(query, limit=limit)
        if not candidates:
            candidates = await self.repository.fuzzy_lookup(normalize_query(query), limit)
        best_match = candidates[0].to_public_dict() if candidates and candidates[0].confidence >= 0.85 else None
        did_you_mean = [] if best_match is not None else [candidate.to_public_dict() for candidate in candidates]
        result = {
            "query": query,
            "mode": "lookup",
            "best_match": best_match,
            "did_you_mean": did_you_mean,
        }
        await self._log(
            query=query,
            mode="lookup",
            started_at=start,
            candidate_count=len(candidates),
            result_count=1 if best_match else len(did_you_mean),
            top_lemma_ids=[candidates[0].lemma.lemma_id] if candidates else [],
            top_sense_ids=[],
        )
        return result

    async def suggest(self, query: str, limit: int = 10) -> dict[str, Any]:
        start = time.perf_counter()
        candidates = self.dictionary.suggest(query, limit=limit)
        if len(candidates) < limit:
            seen = {candidate.lemma.lemma_id for candidate in candidates}
            for candidate in await self.repository.fuzzy_suggest(normalize_query(query), limit):
                if candidate.lemma.lemma_id not in seen:
                    candidates.append(candidate)
                    seen.add(candidate.lemma.lemma_id)
                if len(candidates) >= limit:
                    break
        result = {
            "query": query,
            "mode": "suggest",
            "suggestions": [candidate.to_public_dict() for candidate in candidates],
        }
        await self._log(
            query=query,
            mode="suggest",
            started_at=start,
            candidate_count=len(candidates),
            result_count=len(candidates),
            top_lemma_ids=[candidate.lemma.lemma_id for candidate in candidates],
            top_sense_ids=[],
        )
        return result

    async def semantic_search(self, query: str, limit: int, include_related: bool) -> dict[str, Any]:
        start = time.perf_counter()
        semantic_result = await self.semantic_engine.search(query, limit=limit)
        results = semantic_result["results"]
        top_lemma_ids = [int(item["lemma_id"]) for item in results]
        top_sense_ids = [int(item["matched_sense"]["sense_id"]) for item in results if item.get("matched_sense")]
        related_results = []
        if include_related:
            related = await self.repository.load_related_results(top_lemma_ids, top_sense_ids)
            related_results = [
                {
                    "lemma_id": item.lemma_id,
                    "lemma": item.lemma,
                    "relation_type": item.relation_type,
                    "source_result_lemma_id": item.source_result_lemma_id,
                    "source_result_sense_id": item.source_result_sense_id,
                    "source": item.source,
                    "score": round(item.score, 6),
                }
                for item in rank_related_results(related, primary_lemma_ids=top_lemma_ids, limit=limit)
            ]
        result = {
            "query": query,
            "language": "unknown",
            "results": results,
            "related_results": related_results,
        }
        await self._log(
            query=query,
            mode="semantic",
            started_at=start,
            candidate_count=semantic_result["candidate_count"],
            result_count=len(results),
            top_lemma_ids=top_lemma_ids,
            top_sense_ids=top_sense_ids,
        )
        return result

    async def _log(
        self,
        *,
        query: str,
        mode: str,
        started_at: float,
        candidate_count: int,
        result_count: int,
        top_lemma_ids: list[int],
        top_sense_ids: list[int],
    ) -> None:
        if not self.log_queries:
            return
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        record = SearchLogRecord(
            query=query,
            mode=mode,
            detected_language=None,
            latency_ms=latency_ms,
            candidate_count=candidate_count,
            result_count=result_count,
            top_lemma_ids=top_lemma_ids,
            top_sense_ids=top_sense_ids,
            cache_hit=False,
            embedding_model=self.embedding_model if mode == "semantic" else None,
            index_version=self.index_version,
        )
        await self.repository.write_query_log(record, request_metadata={})
