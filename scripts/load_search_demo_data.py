#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lexicon_search.db import Database
from lexicon_search.embeddings import DemoEmbeddingClient
from lexicon_search.index_builder import SenseEmbeddingInput, build_embedding_text, hash_embedding_text
from lexicon_search.repositories import SearchRepository


LOCAL_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

DEMO_ENTRIES = [
    {
        "lemma": "huis",
        "level": 1,
        "pos": "NOUN",
        "frequency": 950000,
        "forms": ["huis", "huizen"],
        "definition_nl": "gebouw of plaats waar mensen wonen",
        "translation_zh": "房子；家",
        "translation_en": "house; home",
    },
    {
        "lemma": "hond",
        "level": 1,
        "pos": "NOUN",
        "frequency": 420000,
        "forms": ["hond", "honden"],
        "definition_nl": "huisdier dat vaak blaft en bij mensen woont",
        "translation_zh": "狗",
        "translation_en": "dog",
    },
    {
        "lemma": "lopen",
        "level": 1,
        "pos": "VERB",
        "frequency": 780000,
        "forms": ["lopen", "loop", "loopt", "liep"],
        "definition_nl": "zich te voet voortbewegen",
        "translation_zh": "走；跑",
        "translation_en": "walk; run",
    },
    {
        "lemma": "lezen",
        "level": 1,
        "pos": "VERB",
        "frequency": 610000,
        "forms": ["lezen", "lees", "leest", "las"],
        "definition_nl": "geschreven tekst bekijken en begrijpen",
        "translation_zh": "阅读",
        "translation_en": "read",
    },
    {
        "lemma": "boek",
        "level": 1,
        "pos": "NOUN",
        "frequency": 530000,
        "forms": ["boek", "boeken"],
        "definition_nl": "voorwerp met pagina's om te lezen",
        "translation_zh": "书",
        "translation_en": "book",
    },
    {
        "lemma": "water",
        "level": 1,
        "pos": "NOUN",
        "frequency": 880000,
        "forms": ["water"],
        "definition_nl": "heldere vloeistof zonder kleur",
        "translation_zh": "水",
        "translation_en": "water",
    },
    {
        "lemma": "snel",
        "level": 2,
        "pos": "ADJ",
        "frequency": 470000,
        "forms": ["snel", "snelle", "sneller"],
        "definition_nl": "met hoge snelheid",
        "translation_zh": "快的；快速地",
        "translation_en": "fast; quick",
    },
]

DEMO_RELATIONS = [
    ("huis", "hond", "context_related", 0.72),
    ("lezen", "boek", "object_related", 0.95),
    ("boek", "lezen", "action_related", 0.88),
    ("lopen", "snel", "modifier_related", 0.74),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load a tiny local search demo dataset.")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", LOCAL_DATABASE_URL))
    parser.add_argument("--embedding-model", default="demo-embedding-v1")
    parser.add_argument("--embedding-dim", type=int, default=1024)
    parser.add_argument("--index-version", default=os.environ.get("SEARCH_INDEX_VERSION", "search-v1"))
    parser.add_argument("--allow-nonlocal", action="store_true")
    return parser.parse_args()


def assert_local_database(database_url: str, allow_nonlocal: bool) -> None:
    if allow_nonlocal:
        return
    host = urlparse(database_url).hostname
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Refusing to load demo data into a non-local database. Pass --allow-nonlocal to override.")


async def load_demo_data(database: Database) -> dict[str, int]:
    lemma_ids: dict[str, int] = {}
    sense_ids: list[int] = []

    async with database.acquire() as connection:
        async with connection.transaction():
            source_id = await connection.fetchval(
                """
                insert into public.sources (source_key, name, source_type, license, attribution, notes)
                values (
                  'local_search_demo',
                  'Local search demo',
                  'demo',
                  'internal',
                  'Generated local sample rows for API demos.',
                  'Safe to delete; loaded by scripts/load_search_demo_data.py.'
                )
                on conflict (source_key) do update set
                  name = excluded.name,
                  source_type = excluded.source_type,
                  license = excluded.license,
                  attribution = excluded.attribution,
                  notes = excluded.notes,
                  updated_at = now()
                returning id
                """
            )
            await connection.execute("delete from public.lemmas where source_id = $1", source_id)

            for entry in DEMO_ENTRIES:
                lemma_norm = entry["lemma"]
                lemma_id = await connection.fetchval(
                    """
                    insert into public.lemmas (
                      lemma, lemma_norm, display_lemma, level, cc100_freq, source_id, review_status
                    )
                    values ($1, $2, $1, $3, $4, $5, 'accepted')
                    returning id
                    """,
                    entry["lemma"],
                    lemma_norm,
                    entry["level"],
                    entry["frequency"],
                    source_id,
                )
                lemma_ids[entry["lemma"]] = int(lemma_id)

                pos_entry_id = await connection.fetchval(
                    """
                    insert into public.lemma_pos_entries (
                      lemma_id, pos, pos_source, pos_confidence, is_primary
                    )
                    values ($1, $2, 'local_search_demo', 1.0, true)
                    returning id
                    """,
                    lemma_id,
                    entry["pos"],
                )

                for index, form in enumerate(entry["forms"]):
                    await connection.execute(
                        """
                        insert into public.forms (
                          lemma_id, lemma_pos_entry_id, form, form_norm, form_type,
                          source_id, is_canonical, confidence
                        )
                        values ($1, $2, $3, $3, $4, $5, $6, 1.0)
                        """,
                        lemma_id,
                        pos_entry_id,
                        form,
                        "canonical" if index == 0 else "inflected",
                        source_id,
                        index == 0,
                    )

                sense_id = await connection.fetchval(
                    """
                    insert into public.senses (
                      lemma_id, lemma_pos_entry_id, source_id, external_id, sense_no,
                      definition_nl, confidence, is_primary, review_status
                    )
                    values ($1, $2, $3, $4, '1', $5, 1.0, true, 'accepted')
                    returning id
                    """,
                    lemma_id,
                    pos_entry_id,
                    source_id,
                    f"local-demo:{entry['lemma']}:1",
                    entry["definition_nl"],
                )
                sense_ids.append(int(sense_id))

                await connection.executemany(
                    """
                    insert into public.sense_translations (sense_id, lang, gloss, source_id, confidence)
                    values ($1, $2, $3, $4, 1.0)
                    """,
                    [
                        (sense_id, "zh", entry["translation_zh"], source_id),
                        (sense_id, "en", entry["translation_en"], source_id),
                    ],
                )

            for from_lemma, to_lemma, relation_type, confidence in DEMO_RELATIONS:
                await connection.execute(
                    """
                    insert into public.lemma_relations (
                      lemma_id_from, lemma_id_to, relation_type, source_id, confidence
                    )
                    values ($1, $2, $3, $4, $5)
                    """,
                    lemma_ids[from_lemma],
                    lemma_ids[to_lemma],
                    relation_type,
                    source_id,
                    confidence,
                )

    return {"lemmas": len(DEMO_ENTRIES), "senses": len(sense_ids)}


async def load_demo_embeddings(
    *,
    database: Database,
    embedding_model: str,
    embedding_dim: int,
    index_version: str,
) -> dict[str, int]:
    repository = SearchRepository(database)
    embedder = DemoEmbeddingClient(dimension=embedding_dim)
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            select
              s.id as sense_id,
              coalesce(s.display_definition_nl, s.definition_nl, '') as definition_nl,
              coalesce(max(st_zh.gloss) filter (where st_zh.lang = 'zh'), '') as translation_zh,
              coalesce(max(st_en.gloss) filter (where st_en.lang = 'en'), '') as translation_en
            from public.senses s
            join public.sources src on src.id = s.source_id
            left join public.sense_translations st_zh on st_zh.sense_id = s.id and st_zh.lang = 'zh'
            left join public.sense_translations st_en on st_en.sense_id = s.id and st_en.lang = 'en'
            where src.source_key = 'local_search_demo'
            group by s.id, s.display_definition_nl, s.definition_nl
            order by s.id
            """
        )

    inputs = [
        SenseEmbeddingInput(
            sense_id=int(row["sense_id"]),
            definition_nl=row["definition_nl"] or "",
            translation_zh=row["translation_zh"] or "",
            translation_en=row["translation_en"] or "",
        )
        for row in rows
    ]
    texts = [build_embedding_text(row) for row in inputs]
    vectors = await embedder.embed_texts(texts)
    await repository.upsert_sense_embeddings(
        [
            (
                row.sense_id,
                embedding_model,
                embedding_dim,
                _vector_literal(vector),
                hash_embedding_text(text),
                text[:500],
                index_version,
            )
            for row, text, vector in zip(inputs, texts, vectors, strict=True)
            if text.strip()
        ]
    )
    return {"embedded": len(vectors)}


def _vector_literal(vector: list[float]) -> str:
    from lexicon_search.db import vector_literal

    return vector_literal(vector)


async def main() -> None:
    args = parse_args()
    assert_local_database(args.database_url, args.allow_nonlocal)
    database = Database(args.database_url, min_size=1, max_size=4)
    await database.connect()
    try:
        loaded = await load_demo_data(database)
        embedded = await load_demo_embeddings(
            database=database,
            embedding_model=args.embedding_model,
            embedding_dim=args.embedding_dim,
            index_version=args.index_version,
        )
    finally:
        await database.close()
    print({**loaded, **embedded, "index_version": args.index_version, "embedding_model": args.embedding_model})


if __name__ == "__main__":
    asyncio.run(main())
