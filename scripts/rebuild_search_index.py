#!/usr/bin/env python3
"""Preview a bounded sample by default; --execute is required for paid API calls."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from lexicon_search.config import load_config
from lexicon_search.db import Database
from lexicon_search.embeddings import BailianEmbeddingClient
from lexicon_search.index_builder import rebuild_embeddings, build_embedding_text, hash_embedding_text
from lexicon_search.repositories import SearchRepository


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


async def run(args):
    if not 1 <= args.batch_size <= 10 or args.limit < 1:
        raise ValueError('batch-size must be 1..10 and limit must be positive')
    config = load_config()
    if config.use_demo_embeddings:
        raise ValueError('Demo embeddings cannot be written by this builder')
    if args.execute and not config.bailian_api_key:
        raise ValueError('BAILIAN_API_KEY is required for --execute')
    database = Database(config.database_url, min_size=1, max_size=4)
    await database.connect()
    output = Path(args.output)
    try:
        # Session lock protects concurrent builders until this connection is released.
        async with database.acquire() as lock:
            if not await lock.fetchval('select pg_try_advisory_lock(20261013, 1)'):
                raise RuntimeError('Another embedding builder is running')
            try:
                repository = SearchRepository(database)
                rows = await repository.load_senses_for_embedding(limit=None if args.all else args.limit)
                manifest = [{**asdict(row), 'text': build_embedding_text(row),
                             'hash': hash_embedding_text(build_embedding_text(row))} for row in rows]
                report = {
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'mode': 'execute' if args.execute else 'dry-run',
                    'model': config.embedding_model, 'dimension': config.embedding_dim,
                    'index_version': config.index_version, 'selected': len(rows),
                    'characters': sum(len(r['text']) for r in manifest),
                    'estimated_max_batches': (len(rows) + args.batch_size - 1) // args.batch_size,
                    'levels': dict(Counter(str(r.level) for r in rows)),
                    'pos': dict(Counter(r.pos for r in rows)),
                    'status': 'prepared', 'api_attempted': False,
                }
                write_json(output.with_name(output.stem + '-manifest.json'), manifest)
                write_json(output, report)
                if args.execute:
                    # Schema currently stores one version per sense/model/dimension.
                    # Refuse an implicit destructive replacement of another active version.
                    conflicting = await lock.fetchval(
                        'select count(*) from public.sense_embeddings where '
                        '(embedding_model=$1 and index_version<>$2) or '
                        '(index_version=$2 and embedding_model<>$1)',
                        config.embedding_model, config.index_version)
                    if conflicting:
                        raise RuntimeError('Conflicting index/model exists; back up and plan an offline rebuild')
                    class SnapshotRepository:
                        async def load_senses_for_embedding(self, limit=None):
                            return rows
                        load_embedding_hashes = repository.load_embedding_hashes
                        upsert_sense_embeddings = repository.upsert_sense_embeddings
                    def progress(stats):
                        report.update(stats, status='running')
                        write_json(output, report)
                    async with httpx.AsyncClient(base_url=config.bailian_base_url, timeout=30) as client:
                        embedder = BailianEmbeddingClient(
                            api_key=config.bailian_api_key, base_url=config.bailian_base_url,
                            model=config.embedding_model, dimension=config.embedding_dim,
                            http_client=client)
                        class TrackedEmbedder:
                            async def embed_texts(self, texts):
                                report.update(api_attempted=True, status='running')
                                write_json(output, report)
                                return await embedder.embed_texts(texts)
                        try:
                            result = await rebuild_embeddings(
                                repository=SnapshotRepository(), embedding_client=TrackedEmbedder(),
                                embedding_model=config.embedding_model, embedding_dim=config.embedding_dim,
                                index_version=config.index_version, batch_size=args.batch_size,
                                limit=None if args.all else args.limit, progress=progress)
                        except Exception as exc:
                            report.update(status='failed', error_type=type(exc).__name__)
                            write_json(output, report)
                            raise
                    report.update(result, status='complete')
                    write_json(output, report)
                print(json.dumps(report, ensure_ascii=False, indent=2))
            finally:
                await lock.execute('select pg_advisory_unlock(20261013, 1)')
    finally:
        await database.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-size', type=int, default=10)
    parser.add_argument('--limit', type=int, default=500)
    parser.add_argument('--all', action='store_true', help='Explicitly select the full corpus')
    parser.add_argument('--execute', action='store_true', help='Call Bailian and write real vectors')
    parser.add_argument('--output', default='outputs/embedding-pilot/report.json')
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
