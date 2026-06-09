from __future__ import annotations

import json
from typing import Any

from lexicon_search.db import Database, vector_literal
from lexicon_search.models import (
    FormSummary,
    LemmaSummary,
    LookupCandidate,
    RelatedResult,
    SearchLogRecord,
    SemanticCandidate,
)
from lexicon_search.scoring import dictionary_score


class SearchRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def load_dictionary_rows(self) -> tuple[list[LemmaSummary], list[FormSummary]]:
        async with self.database.acquire() as connection:
            lemma_rows = await connection.fetch(
                """
                select id, lemma, lemma_norm, level, coalesce(cc100_freq, subtlex_freq, 0) as frequency
                from public.lemmas
                where review_status = 'accepted'
                """
            )
            form_rows = await connection.fetch(
                """
                select
                  f.id as form_id,
                  f.form,
                  f.form_norm,
                  f.is_canonical,
                  coalesce(fcs.freq_count, 0) as frequency,
                  l.id as lemma_id,
                  l.lemma,
                  l.lemma_norm,
                  l.level,
                  coalesce(l.cc100_freq, l.subtlex_freq, 0) as lemma_frequency
                from public.forms f
                join public.lemmas l on l.id = f.lemma_id
                left join public.form_corpus_stats fcs on fcs.form_id = f.id
                where l.review_status = 'accepted'
                """
            )

        lemmas = [
            LemmaSummary(
                lemma_id=int(row["id"]),
                lemma=row["lemma"],
                lemma_norm=row["lemma_norm"],
                level=row["level"],
                frequency=int(row["frequency"] or 0),
            )
            for row in lemma_rows
        ]
        lemmas_by_id = {lemma.lemma_id: lemma for lemma in lemmas}
        forms = [
            FormSummary(
                form_id=int(row["form_id"]),
                form=row["form"],
                form_norm=row["form_norm"],
                lemma=lemmas_by_id[int(row["lemma_id"])],
                is_canonical=bool(row["is_canonical"]),
                frequency=int(row["frequency"] or 0),
            )
            for row in form_rows
            if int(row["lemma_id"]) in lemmas_by_id
        ]
        return lemmas, forms

    async def match_senses(
        self,
        embedding: list[float],
        candidate_count: int,
        index_version: str,
    ) -> list[SemanticCandidate]:
        literal = vector_literal(embedding)
        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                select *
                from public.match_senses($1::extensions.vector(1024), $2::integer, $3::text)
                """,
                literal,
                candidate_count,
                index_version,
            )
        return [
            SemanticCandidate(
                sense_id=int(row["sense_id"]),
                lemma_id=int(row["lemma_id"]),
                lemma=row["lemma"],
                level=row["level"],
                definition_nl=row["definition_nl"] or "",
                translation_zh=row["translation_zh"] or "",
                translation_en=row["translation_en"] or "",
                vector_similarity=float(row["similarity"]),
                frequency=int(row["frequency"] or 0),
            )
            for row in rows
        ]

    async def fuzzy_lookup(self, query_norm: str, limit: int) -> list[LookupCandidate]:
        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                select *
                from (
                  select
                    l.id as lemma_id,
                    l.lemma,
                    l.lemma_norm,
                    l.level,
                    coalesce(l.cc100_freq, l.subtlex_freq, 0) as frequency,
                    null::bigint as form_id,
                    null::text as form,
                    true as is_canonical,
                    'lemma_fuzzy' as match_type,
                    similarity(l.lemma_norm, $1) as text_similarity
                  from public.lemmas l
                  where l.review_status = 'accepted'
                    and l.lemma_norm % $1
                  union all
                  select
                    l.id as lemma_id,
                    l.lemma,
                    l.lemma_norm,
                    l.level,
                    coalesce(fcs.freq_count, l.cc100_freq, l.subtlex_freq, 0) as frequency,
                    f.id as form_id,
                    f.form,
                    f.is_canonical,
                    'form_fuzzy' as match_type,
                    similarity(f.form_norm, $1) as text_similarity
                  from public.forms f
                  join public.lemmas l on l.id = f.lemma_id
                  left join public.form_corpus_stats fcs on fcs.form_id = f.id
                  where l.review_status = 'accepted'
                    and f.form_norm % $1
                ) candidates
                order by text_similarity desc, frequency desc, lemma asc
                limit $2
                """,
                query_norm,
                limit,
            )
        output = []
        for row in rows:
            lemma = LemmaSummary(
                lemma_id=int(row["lemma_id"]),
                lemma=row["lemma"],
                lemma_norm=row["lemma_norm"],
                level=row["level"],
                frequency=int(row["frequency"] or 0),
            )
            breakdown = dictionary_score(
                exact_match=False,
                normalized_similarity_value=float(row["text_similarity"] or 0.0),
                frequency=int(row["frequency"] or 0),
                is_canonical=bool(row["is_canonical"]),
                level=row["level"],
            )
            output.append(
                LookupCandidate(
                    lemma=lemma,
                    form_id=None if row["form_id"] is None else int(row["form_id"]),
                    form=row["form"],
                    match_type=row["match_type"],
                    score=breakdown.score,
                    confidence=min(breakdown.score, 1.0),
                )
            )
        return output

    async def fuzzy_suggest(self, query_norm: str, limit: int) -> list[LookupCandidate]:
        return await self.fuzzy_lookup(query_norm, limit)

    async def write_query_log(self, record: SearchLogRecord, request_metadata: dict[str, Any]) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                insert into public.search_query_logs (
                  query, mode, detected_language, latency_ms, candidate_count, result_count,
                  top_lemma_ids, top_sense_ids, cache_hit, embedding_model, index_version, request_metadata
                )
                values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)
                """,
                record.query,
                record.mode,
                record.detected_language,
                record.latency_ms,
                record.candidate_count,
                record.result_count,
                record.top_lemma_ids,
                record.top_sense_ids,
                record.cache_hit,
                record.embedding_model,
                record.index_version,
                json.dumps(request_metadata, ensure_ascii=False, sort_keys=True),
            )

    async def load_related_results(self, lemma_ids: list[int], sense_ids: list[int]) -> list[RelatedResult]:
        if not lemma_ids and not sense_ids:
            return []
        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                select
                  lr.lemma_id_to as lemma_id,
                  l.lemma,
                  lr.relation_type,
                  lr.lemma_id_from as source_result_lemma_id,
                  null::bigint as source_result_sense_id,
                  'lemma_relations' as source,
                  lr.confidence::double precision as score
                from public.lemma_relations lr
                join public.lemmas l on l.id = lr.lemma_id_to
                where lr.lemma_id_from = any($1::bigint[])
                union all
                select
                  target.lemma_id as lemma_id,
                  l.lemma,
                  sr.relation_type,
                  source.lemma_id as source_result_lemma_id,
                  sr.sense_id_from as source_result_sense_id,
                  'sense_relations' as source,
                  sr.confidence::double precision as score
                from public.sense_relations sr
                join public.senses source on source.id = sr.sense_id_from
                join public.senses target on target.id = sr.sense_id_to
                join public.lemmas l on l.id = target.lemma_id
                where sr.sense_id_from = any($2::bigint[])
                  and sr.sense_id_to is not null
                """,
                lemma_ids,
                sense_ids,
            )
        return [
            RelatedResult(
                lemma_id=int(row["lemma_id"]),
                lemma=row["lemma"],
                relation_type=row["relation_type"],
                source_result_lemma_id=int(row["source_result_lemma_id"]),
                source_result_sense_id=None
                if row["source_result_sense_id"] is None
                else int(row["source_result_sense_id"]),
                source=row["source"],
                score=float(row["score"] or 0.0),
            )
            for row in rows
        ]

    async def load_senses_for_embedding(self) -> list["SenseEmbeddingInput"]:
        from lexicon_search.index_builder import SenseEmbeddingInput

        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                select
                  s.id as sense_id,
                  coalesce(s.display_definition_nl, s.definition_nl, '') as definition_nl,
                  coalesce(max(st_zh.gloss) filter (where st_zh.lang = 'zh'), '') as translation_zh,
                  coalesce(max(st_en.gloss) filter (where st_en.lang = 'en'), '') as translation_en
                from public.senses s
                left join public.sense_translations st_zh
                  on st_zh.sense_id = s.id and st_zh.lang = 'zh'
                left join public.sense_translations st_en
                  on st_en.sense_id = s.id and st_en.lang = 'en'
                where s.merged_into_sense_id is null
                group by s.id, s.display_definition_nl, s.definition_nl
                order by s.id
                """
            )
        return [
            SenseEmbeddingInput(
                sense_id=int(row["sense_id"]),
                definition_nl=row["definition_nl"] or "",
                translation_zh=row["translation_zh"] or "",
                translation_en=row["translation_en"] or "",
            )
            for row in rows
        ]

    async def upsert_sense_embeddings(self, rows: list[tuple[int, str, int, str, str, str, str]]) -> None:
        if not rows:
            return
        async with self.database.acquire() as connection:
            await connection.executemany(
                """
                insert into public.sense_embeddings (
                  sense_id, embedding_model, embedding_dim, embedding,
                  embedding_text_hash, embedding_text_preview, index_version
                )
                values ($1, $2, $3, $4::extensions.vector(1024), $5, $6, $7)
                on conflict (sense_id, embedding_model, embedding_dim) do update set
                  embedding = excluded.embedding,
                  embedding_text_hash = excluded.embedding_text_hash,
                  embedding_text_preview = excluded.embedding_text_preview,
                  index_version = excluded.index_version,
                  updated_at = now()
                """,
                rows,
            )
