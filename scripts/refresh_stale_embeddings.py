#!/usr/bin/env python3
"""Refresh only reviewed senses with explicitly invalidated embeddings."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lexicon_search.api_budget import OnlineModelBudget
from lexicon_search.config import load_config
from lexicon_search.db import Database
from lexicon_search.embeddings import BailianEmbeddingClient
from lexicon_search.index_builder import build_embedding_text, hash_embedding_text, rebuild_embeddings
from lexicon_search.repositories import SearchRepository


async def refresh(*, execute=False, output: Path):
    config = load_config()
    database = Database(config.database_url, min_size=1, max_size=4)
    await database.connect()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with database.acquire() as lock:
            if not await lock.fetchval('select pg_try_advisory_lock(20261013, 1)'):
                raise RuntimeError('Another embedding builder is running')
            try:
                stale = await lock.fetch('''select sense_id,embedding_text_hash from public.sense_embeddings
                    where embedding_model=$1 and embedding_dim=$2 and index_version like 'stale:%' ''',
                    config.embedding_model, config.embedding_dim)
                ids = {r['sense_id']: r['embedding_text_hash'] for r in stale}
                repository = SearchRepository(database)
                inputs = [r for r in await repository.load_senses_for_embedding() if r.sense_id in ids]
                unchanged = [r.sense_id for r in inputs if ids[r.sense_id] == hash_embedding_text(build_embedding_text(r))]
                remaining = [r for r in inputs if r.sense_id not in unchanged]
                report = {'execute':execute,'selected':len(inputs),'invalidated':len(stale),
                          'unchanged_text':len(unchanged),'needs_new_vector':len(remaining),
                          'excluded_or_unavailable':len(stale)-len(inputs)}
                output.write_text(json.dumps(report,indent=2)+'\n')
                if not execute:
                    return report
                if config.use_demo_embeddings:
                    raise ValueError('Real embeddings are required')
                budget = OnlineModelBudget(config.api_budget_ledger,
                    total_cny=config.api_budget_total_cny,daily_cny=config.api_budget_daily_cny)
                if unchanged:
                    await lock.execute('''update public.sense_embeddings set index_version=$1,updated_at=now()
                        where sense_id=any($2::bigint[]) and embedding_model=$3 and embedding_dim=$4
                        and index_version like 'stale:%' ''',config.index_version,unchanged,
                        config.embedding_model,config.embedding_dim)
                class SnapshotRepository:
                    async def load_senses_for_embedding(self, limit=None):
                        return remaining
                    load_embedding_hashes = repository.load_embedding_hashes
                    upsert_sense_embeddings = repository.upsert_sense_embeddings
                async with httpx.AsyncClient(base_url=config.bailian_base_url,timeout=30,
                        event_hooks={'request':[budget.request],'response':[budget.response]}) as client:
                    embedder = BailianEmbeddingClient(api_key=config.bailian_api_key,
                        base_url=config.bailian_base_url,model=config.embedding_model,
                        dimension=config.embedding_dim,http_client=client,max_retries=0)
                    def progress(stats):
                        report.update(stats,status='running')
                        output.write_text(json.dumps(report,indent=2)+'\n')
                    result = await rebuild_embeddings(repository=SnapshotRepository(),
                        embedding_client=embedder,embedding_model=config.embedding_model,
                        embedding_dim=config.embedding_dim,index_version=config.index_version,
                        batch_size=10,progress=progress)
                report.update(result,status='complete')
                output.write_text(json.dumps(report,indent=2)+'\n')
                return report
            finally:
                await lock.execute('select pg_advisory_unlock(20261013, 1)')
    finally:
        await database.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--output',type=Path,default=Path('outputs/stale-embedding-refresh.json'))
    args=parser.parse_args()
    print(json.dumps(asyncio.run(refresh(execute=args.execute,output=args.output)),indent=2))
