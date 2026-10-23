from __future__ import annotations

from typing import Any
from contextlib import asynccontextmanager
import logging

import httpx
import asyncpg
from fastapi import FastAPI, Path, Query, HTTPException
from pydantic import BaseModel, Field
from lexicon_search.rate_limit import IPRateLimiter, QueryLimitMiddleware


class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=512, pattern=r"\S")
    limit: int = Field(default=10, ge=1, le=50)
    include_related: bool = True


def create_app(service: Any = None, *, service_context=None, limiter=None, max_semantic_limit=50) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        if service_context is None:
            yield
        else:
            async with service_context() as live_service:
                app.state.service = live_service
                try:
                    yield
                finally:
                    app.state.service = None

    app = FastAPI(title="Dutch Lexicon Search Service", version="0.1.0",
                  lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service
    app.add_middleware(QueryLimitMiddleware, limiter=limiter or IPRateLimiter())

    def current_service():
        if app.state.service is None:
            raise HTTPException(503, "Search service is not ready")
        return app.state.service

    @app.get("/health")
    async def health() -> dict[str, str]:
        live = current_service()
        if hasattr(live, 'ready'):
            try:
                await live.ready()
            except Exception:
                raise HTTPException(503, 'Search service is not ready') from None
        return {"status": "ok"}

    @app.get("/lookup")
    async def lookup(q: str = Query(min_length=1, max_length=128, pattern=r"\S"), limit: int = Query(default=5, ge=1, le=5)) -> dict[str, Any]:
        try:
            return await current_service().lookup(q.strip(), limit)
        except (asyncpg.PostgresError, ConnectionError, TimeoutError):
            raise HTTPException(503, 'Dictionary search is temporarily unavailable') from None

    @app.get("/suggest")
    async def suggest(q: str = Query(min_length=1, max_length=128, pattern=r"\S"), limit: int = Query(default=10, ge=1, le=20)) -> dict[str, Any]:
        try:
            return await current_service().suggest(q.strip(), limit)
        except (asyncpg.PostgresError, ConnectionError, TimeoutError):
            raise HTTPException(503, 'Dictionary search is temporarily unavailable') from None

    @app.get("/entries/{lemma_id}")
    async def entry(
        lemma_id: int = Path(ge=1, le=9223372036854775807),
        sense_offset: int = Query(default=0, ge=0, le=10000),
        sense_limit: int = Query(default=20, ge=1, le=50),
        form_offset: int = Query(default=0, ge=0, le=100000),
        form_limit: int = Query(default=50, ge=1, le=100),
        example_offset: int = Query(default=0, ge=0, le=10000),
        example_limit: int = Query(default=5, ge=1, le=20),
        expression_offset: int = Query(default=0, ge=0, le=10000),
        expression_limit: int = Query(default=20, ge=1, le=50),
    ) -> dict[str, Any]:
        try:
            result = await current_service().entry(
                lemma_id, sense_offset=sense_offset, sense_limit=sense_limit,
                form_offset=form_offset, form_limit=form_limit,
                example_offset=example_offset, example_limit=example_limit,
                expression_offset=expression_offset, expression_limit=expression_limit,
            )
        except (asyncpg.PostgresError, ConnectionError, TimeoutError):
            raise HTTPException(503, 'Dictionary entry is temporarily unavailable') from None
        if result is None:
            raise HTTPException(404, 'Dictionary entry not found')
        return result

    @app.get("/senses/{sense_id}/examples")
    async def sense_examples(
        sense_id: int = Path(ge=1, le=9223372036854775807),
        offset: int = Query(default=0, ge=0, le=10000),
        limit: int = Query(default=10, ge=1, le=20),
    ) -> dict[str, Any]:
        try:
            result = await current_service().sense_examples(sense_id, offset=offset, limit=limit)
        except (asyncpg.PostgresError, ConnectionError, TimeoutError):
            raise HTTPException(503, 'Dictionary examples are temporarily unavailable') from None
        if result is None:
            raise HTTPException(404, 'Dictionary sense not found')
        return result

    @app.post("/semantic-search")
    async def semantic_search(request: SemanticSearchRequest) -> dict[str, Any]:
        if request.limit > max_semantic_limit:
            raise HTTPException(422, f'limit must be at most {max_semantic_limit}')
        live = current_service()
        if getattr(live, 'semantic_engine', True) is None:
            raise HTTPException(503, 'Semantic search is not enabled')
        try:
            return await live.semantic_search(request.query.strip(), request.limit, request.include_related)
        except (httpx.HTTPError, ValueError, asyncpg.PostgresError, ConnectionError, TimeoutError):
            logging.getLogger(__name__).warning('Semantic provider request failed')
            raise HTTPException(503, 'Semantic search is temporarily unavailable') from None

    return app
