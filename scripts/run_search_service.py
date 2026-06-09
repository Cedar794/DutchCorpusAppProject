#!/usr/bin/env python3
from __future__ import annotations

import asyncio

import uvicorn

from lexicon_search.api import create_app
from lexicon_search.config import load_config
from lexicon_search.db import Database
from lexicon_search.dictionary import DictionaryIndex
from lexicon_search.embeddings import BailianEmbeddingClient
from lexicon_search.repositories import SearchRepository
from lexicon_search.semantic import SemanticSearchEngine
from lexicon_search.service import SearchService


async def build_service() -> tuple[SearchService, Database]:
    config = load_config()
    database = Database(config.database_url, min_size=1, max_size=12)
    await database.connect()
    repository = SearchRepository(database)
    lemmas, forms = await repository.load_dictionary_rows()
    dictionary = DictionaryIndex.from_rows(lemmas, forms)
    embedder = BailianEmbeddingClient(
        api_key=config.bailian_api_key,
        base_url=config.bailian_base_url,
        model=config.embedding_model,
        dimension=config.embedding_dim,
    )
    semantic_engine = SemanticSearchEngine(embedder, repository, config.index_version)
    return (
        SearchService(
            dictionary,
            semantic_engine,
            repository,
            log_queries=config.log_queries,
            embedding_model=config.embedding_model,
            index_version=config.index_version,
        ),
        database,
    )


def main() -> None:
    service, database = asyncio.run(build_service())
    app = create_app(service)
    try:
        uvicorn.run(app, host="0.0.0.0", port=8080, workers=1)
    finally:
        asyncio.run(database.close())


if __name__ == "__main__":
    main()
