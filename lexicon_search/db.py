from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

import asyncpg


def vector_literal(values: Sequence[float], expected_dim: int = 1024) -> str:
    if len(values) != expected_dim:
        raise ValueError(f"embedding vector must have {expected_dim} dimensions")
    return "[" + ",".join(f"{float(value):.9g}" for value in values) + "]"


class Database:
    def __init__(self, database_url: str, min_size: int = 1, max_size: int = 10) -> None:
        self.database_url = database_url
        self.min_size = min_size
        self.max_size = max_size
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(
            self.database_url,
            min_size=self.min_size,
            max_size=self.max_size,
            command_timeout=30,
            server_settings={"search_path": "public,extensions,pg_catalog"},
        )

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[asyncpg.Connection]:
        if self.pool is None:
            raise RuntimeError("database pool is not connected")
        async with self.pool.acquire() as connection:
            yield connection
