from __future__ import annotations

from dataclasses import dataclass, field
from os import environ
from typing import Mapping

from lexicon_search.api_budget import money_units


@dataclass(frozen=True)
class SearchConfig:
    database_url: str
    bailian_api_key: str = field(repr=False)
    bailian_base_url: str
    embedding_model: str
    embedding_dim: int
    index_version: str
    max_limit: int
    log_queries: bool
    use_demo_embeddings: bool
    semantic_enabled: bool = False
    rate_limit_per_minute: int = 60
    semantic_rate_limit_per_minute: int = 10
    rate_limit_burst: int = 10
    rewrite_enabled: bool = True
    rewrite_api_key: str = field(default='', repr=False)
    rewrite_base_url: str = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    rewrite_timeout_ms: int = 1200
    api_budget_total_cny: str = '0'
    api_budget_daily_cny: str = '0'
    api_budget_ledger: str = 'local/search-api-budget.sqlite3'


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

    semantic_enabled = _bool_value(values, "SEARCH_SEMANTIC_ENABLED", False)
    demo = _bool_value(values, "SEARCH_USE_DEMO_EMBEDDINGS", False)
    rewrite_timeout_ms = _int_value(values, 'SEARCH_REWRITE_TIMEOUT_MS', 1200)
    if not 100 <= rewrite_timeout_ms <= 5000:
        raise ValueError('SEARCH_REWRITE_TIMEOUT_MS must be between 100 and 5000')
    budgets = {}
    for key in ('SEARCH_API_BUDGET_TOTAL_CNY', 'SEARCH_API_BUDGET_DAILY_CNY'):
        budgets[key] = values.get(key, '0').strip()
        try:
            money_units(budgets[key])
        except ValueError:
            raise ValueError(f'{key} must be nonnegative CNY with at most 7 decimal places') from None
    limits = {}
    for key, default in (("SEARCH_RATE_LIMIT_PER_MINUTE", 60),
                         ("SEARCH_SEMANTIC_RATE_LIMIT_PER_MINUTE", 10),
                         ("SEARCH_RATE_LIMIT_BURST", 10)):
        limits[key] = _int_value(values, key, default)
        if not 1 <= limits[key] <= 1000:
            raise ValueError(f"{key} must be between 1 and 1000")
    return SearchConfig(
        database_url=_required(values, "DATABASE_URL"),
        bailian_api_key=(_required(values, "BAILIAN_API_KEY") if semantic_enabled and not demo
                         else values.get("BAILIAN_API_KEY", "").strip()),
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
        use_demo_embeddings=demo,
        semantic_enabled=semantic_enabled,
        rate_limit_per_minute=limits["SEARCH_RATE_LIMIT_PER_MINUTE"],
        semantic_rate_limit_per_minute=limits["SEARCH_SEMANTIC_RATE_LIMIT_PER_MINUTE"],
        rate_limit_burst=limits["SEARCH_RATE_LIMIT_BURST"],
        rewrite_enabled=_bool_value(values, 'SEARCH_REWRITE_ENABLED', True),
        rewrite_api_key=values.get('BAILIAN_REWRITE_API_KEY', '').strip(),
        rewrite_base_url=values.get('BAILIAN_REWRITE_BASE_URL',
            'https://dashscope.aliyuncs.com/compatible-mode/v1').rstrip('/'),
        rewrite_timeout_ms=rewrite_timeout_ms,
        api_budget_total_cny=budgets['SEARCH_API_BUDGET_TOTAL_CNY'],
        api_budget_daily_cny=budgets['SEARCH_API_BUDGET_DAILY_CNY'],
        api_budget_ledger=values.get('SEARCH_API_BUDGET_LEDGER', 'local/search-api-budget.sqlite3').strip()
            or 'local/search-api-budget.sqlite3',
    )
