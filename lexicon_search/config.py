from __future__ import annotations

from dataclasses import dataclass
from os import environ
from typing import Mapping


@dataclass(frozen=True)
class SearchConfig:
    database_url: str
    bailian_api_key: str
    bailian_base_url: str
    embedding_model: str
    embedding_dim: int
    index_version: str
    max_limit: int
    log_queries: bool


def _required(source: Mapping[str, str], key: str) -> str:
    value = source.get(key, "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _int_value(source: Mapping[str, str], key: str, default: int) -> int:
    raw = source.get(key, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _bool_value(source: Mapping[str, str], key: str, default: bool) -> bool:
    raw = source.get(key)
    if raw is None:
        return default
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{key} must be true or false")


def load_config(source: Mapping[str, str] | None = None) -> SearchConfig:
    values = environ if source is None else source
    max_limit = _int_value(values, "SEARCH_MAX_LIMIT", 50)
    if max_limit < 1 or max_limit > 50:
        raise ValueError("SEARCH_MAX_LIMIT must be between 1 and 50")

    embedding_dim = _int_value(values, "SEARCH_EMBEDDING_DIM", 1024)
    if embedding_dim != 1024:
        raise ValueError("SEARCH_EMBEDDING_DIM must be 1024")

    return SearchConfig(
        database_url=_required(values, "DATABASE_URL"),
        bailian_api_key=_required(values, "BAILIAN_API_KEY"),
        bailian_base_url=values.get(
            "BAILIAN_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ).rstrip("/"),
        embedding_model=values.get("SEARCH_EMBEDDING_MODEL", "text-embedding-v4").strip()
        or "text-embedding-v4",
        embedding_dim=embedding_dim,
        index_version=values.get("SEARCH_INDEX_VERSION", "search-v1").strip() or "search-v1",
        max_limit=max_limit,
        log_queries=_bool_value(values, "SEARCH_LOG_QUERIES", True),
    )
