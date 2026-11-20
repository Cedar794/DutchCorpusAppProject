"""Read bounded, source-attributed dictionary entries without model calls."""
from __future__ import annotations

import json
from typing import Any


def public_text(value: str | None) -> str | None:
    # The import pipeline stores this provenance marker in generated text.
    # Sources and review status remain in the response instead of the marker.
    return value.removesuffix("#aigc").rstrip() if value is not None else None


def page(items: list, total: int, offset: int, limit: int) -> dict[str, Any]:
    has_more = offset + len(items) < total
    return {"items": items, "total": total, "offset": offset, "limit": limit,
            "has_more": has_more, "next_offset": offset + len(items) if has_more else None}


def public_rows(rows) -> list[dict]:
    result = []
    for row in rows:
        item = dict(row)
        for key, value in item.items():
            if isinstance(value, str) and key != "morph_features":
                item[key] = public_text(value)
        if isinstance(item.get("morph_features"), str):
            item["morph_features"] = json.loads(item["morph_features"])
        result.append(item)
    return result


class EntryReader:
    def __init__(self, database):
        self.database = database

    async def load_entry(
        self, lemma_id: int, *, sense_offset=0, sense_limit=20,
        form_offset=0, form_limit=50, example_offset=0, example_limit=5,
        expression_offset=0, expression_limit=20,
    ) -> dict | None:
        async with self.database.acquire() as connection:
            # Counts, pages and related translations must describe one snapshot.
            async with connection.transaction(isolation="repeatable_read", readonly=True):
                lemma = await connection.fetchrow("""
                    select id as lemma_id, lemma, display_lemma, level, cefr_level,
                           is_academic, word_family, family_head_lemma_id, needs_review,
                           source_id, coalesce(cc100_freq, subtlex_freq, 0) as frequency
                    from public.lemmas where id=$1 and review_status='accepted'
                """, lemma_id)
                if lemma is None:
                    return None
                result = public_rows([lemma])[0]
                result["entry_url"] = f"/entries/{lemma_id}"
                result["parts_of_speech"] = public_rows(await connection.fetch("""
                    select p.id as lemma_pos_entry_id, p.pos, t.app_pos,
                           coalesce(t.app_pos_label_zh, t.description_zh) as label_zh,
                           coalesce(t.app_pos_label_en, t.english) as label_en,
                           t.dutch as label_nl, p.gender, p.article, p.is_primary, p.needs_review
                    from public.lemma_pos_entries p join public.pos_tags t on t.tag=p.pos
                    where p.lemma_id=$1
                    order by p.is_primary desc, t.display_order nulls last, p.pos, p.id
                """, lemma_id))
                totals = await connection.fetchrow("""
                    select
                      (select count(*) from public.senses where lemma_id=$1
                        and merged_into_sense_id is null and review_status<>'rejected') as senses,
                      (select count(*) from public.forms where lemma_id=$1 and is_active) as forms,
                      (select count(*) from public.lemma_examples where lemma_id=$1 and is_active) as examples,
                      (select count(*) from public.lexical_expressions e join public.senses s on s.id=e.sense_id
                        where e.lemma_id=$1 and s.lemma_id=$1 and e.review_status<>'rejected'
                        and s.merged_into_sense_id is null and s.review_status<>'rejected') as expressions
                """, lemma_id)
                senses = public_rows(await connection.fetch("""
                    select s.id as sense_id, s.lemma_pos_entry_id, p.pos, s.sense_no,
                           coalesce(nullif(btrim(s.display_definition_nl), ''), s.definition_nl, '') as definition_nl,
                           s.usage_note, s.domain, s.register, s.is_primary, s.is_core,
                           s.app_sense_order, s.review_status, s.confidence::float8, s.source_id
                    from public.senses s left join public.lemma_pos_entries p on p.id=s.lemma_pos_entry_id
                    where s.lemma_id=$1 and s.merged_into_sense_id is null and s.review_status<>'rejected'
                    order by s.app_sense_order nulls last, s.is_primary desc, s.id
                    limit $2 offset $3
                """, lemma_id, sense_limit, sense_offset))
                sense_ids = [item["sense_id"] for item in senses]
                translations = public_rows(await connection.fetch("""
                    select id as translation_id, sense_id, lang, gloss, explanation,
                           review_status, confidence::float8, source_id
                    from public.sense_translations where sense_id=any($1::bigint[])
                      and review_status<>'rejected' and btrim(gloss)<>''
                    order by sense_id, lang,
                      case review_status when 'accepted' then 0 when 'needs_review' then 1 else 2 end,
                      confidence desc nulls last, id desc
                """, sense_ids))
                examples, example_totals = await self._sense_example_previews(connection, sense_ids)
                for sense in senses:
                    sid = sense["sense_id"]
                    sense["translations"] = [t for t in translations if t["sense_id"] == sid]
                    for language in ("zh", "en"):
                        sense[f"translation_{language}"] = next(
                            (t["gloss"] for t in sense["translations"] if t["lang"] == language), "")
                    sense["examples"] = page([e for e in examples if e["sense_id"] == sid],
                                             example_totals.get(sid, 0), 0, 3)
                    sense["examples_url"] = f"/senses/{sid}/examples"
                result["senses"] = page(senses, totals["senses"], sense_offset, sense_limit)
                forms = public_rows(await connection.fetch("""
                    select id as form_id, lemma_pos_entry_id, form, form_type, app_form_role,
                           display_label_zh, display_label_en, morph_features, is_canonical,
                           is_observed, needs_review, confidence::float8, source_id
                    from public.forms where lemma_id=$1 and is_active
                    order by is_canonical desc, lemma_pos_entry_id nulls last, form_norm, id
                    limit $2 offset $3
                """, lemma_id, form_limit, form_offset))
                result["forms"] = page(forms, totals["forms"], form_offset, form_limit)
                corpus_examples = public_rows(await connection.fetch("""
                    select id as lemma_example_id, lemma_pos_entry_id, form_id, ex_nl,
                           quality_score::float8, source_id
                    from public.lemma_examples where lemma_id=$1 and is_active
                    order by quality_score desc nulls last, id limit $2 offset $3
                """, lemma_id, example_limit, example_offset))
                result["corpus_examples"] = page(corpus_examples, totals["examples"], example_offset, example_limit)
                result["corpus_examples"]["sense_disambiguated"] = False
                expressions = public_rows(await connection.fetch("""
                    select e.id as expression_id, e.lemma_pos_entry_id, e.sense_id, e.entry_kind,
                           e.expression_type, e.expression_nl, e.definition_nl, e.usage_note,
                           e.gloss_en, e.explanation_en, e.gloss_zh, e.explanation_zh,
                           e.example_nl, e.example_zh, e.review_status, e.confidence::float8, e.source_id
                    from public.lexical_expressions e join public.senses s on s.id=e.sense_id
                    where e.lemma_id=$1 and s.lemma_id=$1 and e.review_status<>'rejected'
                      and s.merged_into_sense_id is null and s.review_status<>'rejected'
                    order by e.id limit $2 offset $3
                """, lemma_id, expression_limit, expression_offset))
                result["expressions"] = page(expressions, totals["expressions"], expression_offset, expression_limit)
                result["sources"] = await self._sources(connection, result)
                return result

    async def load_sense_examples(self, sense_id: int, *, offset=0, limit=10) -> dict | None:
        async with self.database.acquire() as connection:
            async with connection.transaction(isolation="repeatable_read", readonly=True):
                lemma_id = await connection.fetchval("""
                    select s.lemma_id from public.senses s join public.lemmas l on l.id=s.lemma_id
                    where s.id=$1 and l.review_status='accepted'
                      and s.review_status<>'rejected' and s.merged_into_sense_id is null
                """, sense_id)
                if lemma_id is None:
                    return None
                total = await connection.fetchval(
                    "select count(*) from public.examples where sense_id=$1 and is_active", sense_id)
                examples = public_rows(await connection.fetch("""
                    select id as example_id, sense_id, ex_nl, cefr_level, quality_score::float8, source_id
                    from public.examples where sense_id=$1 and is_active
                    order by quality_score desc nulls last, id limit $2 offset $3
                """, sense_id, limit, offset))
                await self._example_translations(connection, examples)
                result = {"sense_id": sense_id, "lemma_id": lemma_id,
                          "entry_url": f"/entries/{lemma_id}", "examples": page(examples, total, offset, limit)}
                result["sources"] = await self._sources(connection, result)
                return result

    async def _sense_example_previews(self, connection, sense_ids):
        totals = {row["sense_id"]: row["total"] for row in await connection.fetch("""
            select sense_id, count(*) as total from public.examples
            where sense_id=any($1::bigint[]) and is_active group by sense_id
        """, sense_ids)}
        examples = public_rows(await connection.fetch("""
            select e.id as example_id, e.sense_id, e.ex_nl, e.cefr_level,
                   e.quality_score::float8, e.source_id
            from unnest($1::bigint[]) ids(sense_id)
            cross join lateral (
                select id, sense_id, ex_nl, cefr_level, quality_score, source_id
                from public.examples where sense_id=ids.sense_id and is_active
                order by quality_score desc nulls last, id limit 3
            ) e order by e.sense_id, e.quality_score desc nulls last, e.id
        """, sense_ids))
        await self._example_translations(connection, examples)
        return examples, totals

    async def _example_translations(self, connection, examples):
        translations = public_rows(await connection.fetch("""
            select id as translation_id, example_id, lang, translation, source_id
            from public.example_translations where example_id=any($1::bigint[])
              and btrim(translation)<>'' order by example_id, lang, id desc
        """, [e["example_id"] for e in examples]))
        for example in examples:
            example["translations"] = [t for t in translations if t["example_id"] == example["example_id"]]

    async def _sources(self, connection, result):
        source_ids = set()

        def collect(value):
            if isinstance(value, dict):
                if value.get("source_id") is not None:
                    source_ids.add(value["source_id"])
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(result)
        return [dict(row) for row in await connection.fetch("""
            select id as source_id, source_key, name, source_type, url, license,
                   license_url, attribution, version from public.sources
            where id=any($1::bigint[]) order by id
        """, sorted(source_ids))]
