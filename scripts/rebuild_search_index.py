#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio

from lexicon_search.config import load_config
from lexicon_search.db import Database
from lexicon_search.embeddings import BailianEmbeddingClient
from lexicon_search.index_builder import rebuild_embeddings
from lexicon_search.repositories import SearchRepository


async def main_async() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()

    config = load_config()
    database = Database(config.database_url, min_size=1, max_size=4)
    await database.connect()
    try:
        repository = SearchRepository(database)
        embedding_client = BailianEmbeddingClient(
            api_key=config.bailian_api_key,
            base_url=config.bailian_base_url,
            model=config.embedding_model,
            dimension=config.embedding_dim,
        )
        result = await rebuild_embeddings(
            repository=repository,
            embedding_client=embedding_client,
            embedding_model=config.embedding_model,
            embedding_dim=config.embedding_dim,
            index_version=config.index_version,
            batch_size=args.batch_size,
        )
        print(result)
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(main_async())
