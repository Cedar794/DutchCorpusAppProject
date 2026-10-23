#!/usr/bin/env python3
from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
import os
import logging
import sqlite3
import sys
from pathlib import Path

import uvicorn
import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lexicon_search.api import create_app
from lexicon_search.config import load_config
from lexicon_search.db import Database
from lexicon_search.dictionary import DictionaryIndex
from lexicon_search.embeddings import BailianEmbeddingClient
from lexicon_search.repositories import SearchRepository
from lexicon_search.semantic import SemanticSearchEngine
from lexicon_search.service import SearchService
from lexicon_search.rate_limit import IPRateLimiter
from lexicon_search.api_budget import OnlineModelBudget
from lexicon_search.query_rewrite import BailianQueryRewriter


@asynccontextmanager
async def service_context(config):
    # Lifespan, request handlers and shutdown share the server's event loop.
    database = Database(config.database_url, min_size=1, max_size=12)
    async with AsyncExitStack() as resources:
        try:
            await database.connect()
            repository = SearchRepository(database)
            lemmas, forms = await repository.load_dictionary_rows()
            if not lemmas or not forms:
                raise RuntimeError('Dictionary is empty; refusing to serve traffic')
            dictionary = DictionaryIndex.from_rows(lemmas, forms)
            semantic_engine = None
            if config.semantic_enabled:
                if not await repository.embedding_count(config.embedding_model, config.index_version):
                    raise RuntimeError('No vectors for configured model/index; build index first')
                if config.use_demo_embeddings:
                    raise ValueError('Demo embeddings are not allowed in the deployed service')
                try:
                    budget = OnlineModelBudget(config.api_budget_ledger,
                        total_cny=config.api_budget_total_cny, daily_cny=config.api_budget_daily_cny)
                except (OSError, sqlite3.Error, ValueError):
                    logging.getLogger(__name__).warning('Online budget unavailable; model calls blocked')
                    budget = OnlineModelBudget(config.api_budget_ledger, total_cny='0', daily_cny='0')
                hooks = {'request':[budget.request], 'response':[budget.response]}
                client = await resources.enter_async_context(
                    httpx.AsyncClient(base_url=config.bailian_base_url, timeout=30,
                        limits=httpx.Limits(max_connections=4), event_hooks=hooks))
                embedder = BailianEmbeddingClient(
                    api_key=config.bailian_api_key,
                    base_url=config.bailian_base_url,
                    model=config.embedding_model,
                    dimension=config.embedding_dim,
                    http_client=client,
                    max_retries=0,
                )
                rewrite_client = await resources.enter_async_context(httpx.AsyncClient(
                    base_url=config.rewrite_base_url, timeout=config.rewrite_timeout_ms/1000,
                    limits=httpx.Limits(max_connections=2), event_hooks=hooks))
                rewriter = BailianQueryRewriter(api_key=config.rewrite_api_key,
                    http_client=rewrite_client, timeout_seconds=config.rewrite_timeout_ms/1000,
                    enabled=config.rewrite_enabled)
                semantic_engine = SemanticSearchEngine(embedder, repository, config.index_version, rewriter=rewriter)
            yield SearchService(
                dictionary, semantic_engine, repository,
                log_queries=config.log_queries,
                embedding_model=config.embedding_model,
                index_version=config.index_version,
            )
        finally:
            await database.close()


def main() -> None:
    config = load_config()
    trusted_proxies = os.environ.get('SEARCH_TRUSTED_PROXIES', '').strip()
    if '*' in trusted_proxies:
        raise ValueError('SEARCH_TRUSTED_PROXIES must list explicit proxy IPs')
    app = create_app(max_semantic_limit=config.max_limit, service_context=lambda: service_context(config), limiter=IPRateLimiter(
        config.rate_limit_per_minute, config.semantic_rate_limit_per_minute, config.rate_limit_burst))
    uvicorn.run(app, host=os.environ.get('SEARCH_HOST', '127.0.0.1'),
                port=int(os.environ.get('SEARCH_PORT', '8080')), workers=1,
                proxy_headers=bool(trusted_proxies), forwarded_allow_ips=trusted_proxies,
                limit_concurrency=100, timeout_keep_alive=5)


if __name__ == "__main__":
    main()
