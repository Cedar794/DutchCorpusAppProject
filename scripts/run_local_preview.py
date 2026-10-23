#!/usr/bin/env python3
"""Serve Woordhuis and the real search API on one loopback origin."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn
from dotenv import dotenv_values
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lexicon_search.api import create_app
from lexicon_search.config import load_config
from lexicon_search.rate_limit import IPRateLimiter
from scripts.run_search_service import service_context

TEST_LEDGER = ROOT / 'local/budgets/query-rewrite-test-20261023.sqlite3'


def preview_config(*, semantic: bool = False):
    values = dict(os.environ)
    values.setdefault('DATABASE_URL', 'postgresql://postgres:postgres@127.0.0.1:54322/postgres')
    if semantic:
        # Reuse the already approved cumulative test budget; never create a fresh ledger.
        if not TEST_LEDGER.is_file():
            raise ValueError('Existing approved test-budget ledger is required for --semantic')
        for name in ('embedding-pilot.env', 'query-rewrite-test.env'):
            for key, value in dotenv_values(ROOT / 'local/secrets' / name).items():
                if value and not values.get(key):
                    values[key] = value
        if not values.get('BAILIAN_REWRITE_API_KEY'):
            raise ValueError('BAILIAN_REWRITE_API_KEY is required for --semantic')
    values.update({
        'SEARCH_SEMANTIC_ENABLED': str(semantic).lower(),
        'SEARCH_USE_DEMO_EMBEDDINGS': 'false',
        'SEARCH_REWRITE_ENABLED': 'true',
        'SEARCH_REWRITE_TIMEOUT_MS': '1200',
        'SEARCH_LOG_QUERIES': 'false',
        'SEARCH_RATE_LIMIT_PER_MINUTE': '60',
        'SEARCH_SEMANTIC_RATE_LIMIT_PER_MINUTE': '10',
        'SEARCH_RATE_LIMIT_BURST': '10',
        'SEARCH_API_BUDGET_TOTAL_CNY': '1' if semantic else '0',
        'SEARCH_API_BUDGET_DAILY_CNY': '1' if semantic else '0',
        'SEARCH_API_BUDGET_LEDGER': str(TEST_LEDGER),
    })
    return load_config(values)


class DevelopmentStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers['Cache-Control'] = 'no-cache'
        return response


def create_preview_app(config, *, service=None):
    app = create_app(
        service=service,
        service_context=(lambda: service_context(config)) if service is None else None,
        max_semantic_limit=config.max_limit,
        limiter=IPRateLimiter(config.rate_limit_per_minute,
                              config.semantic_rate_limit_per_minute,
                              config.rate_limit_burst),
    )
    # API routes must precede the static catch-all. Only site/ is publicly readable.
    app.mount('/', DevelopmentStaticFiles(directory=ROOT / 'frontend/site', html=True), name='woordhuis')
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8801)
    parser.add_argument('--semantic', action='store_true',
                        help='Enable real models using the existing cumulative 1 CNY test ledger')
    args = parser.parse_args()
    config = preview_config(semantic=args.semantic)
    print(f'Woordhuis: http://127.0.0.1:{args.port}/', flush=True)
    print('Real database; per-IP limits 60/min, burst 10/10s, semantic 10/min.', flush=True)
    if args.semantic:
        print('Real models enabled; shared existing test budget capped at 1 CNY total.', flush=True)
    uvicorn.run(create_preview_app(config), host='127.0.0.1', port=args.port,
                workers=1, proxy_headers=False, access_log=False,
                limit_concurrency=100, timeout_keep_alive=5)


if __name__ == '__main__':
    main()
