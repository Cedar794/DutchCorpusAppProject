from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field


class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)
    include_related: bool = True


def create_app(service: Any) -> FastAPI:
    app = FastAPI(title="Dutch Lexicon Search Service", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/lookup")
    async def lookup(q: str = Query(min_length=1), limit: int = Query(default=5, ge=1, le=5)) -> dict[str, Any]:
        return await service.lookup(q, limit)

    @app.get("/suggest")
    async def suggest(q: str = Query(min_length=1), limit: int = Query(default=10, ge=1, le=20)) -> dict[str, Any]:
        return await service.suggest(q, limit)

    @app.post("/semantic-search")
    async def semantic_search(request: SemanticSearchRequest) -> dict[str, Any]:
        return await service.semantic_search(request.query, request.limit, request.include_related)

    return app
