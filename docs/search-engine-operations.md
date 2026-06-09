# Search Engine Operations

## Baseline Capacity

Use one 4 vCPU / 8 GB RAM API server for the first production MVP. Run one async service process and let the process keep a database pool of up to 12 connections. This first deployment favors one warmed dictionary index and async I/O over multiple worker processes.

## Supabase Capacity

Use a Supabase/Postgres compute tier with at least 8 GB RAM for the first production MVP. The API service memory is mostly dictionary indexes and request state; pgvector HNSW memory pressure belongs to Postgres.

## Deployment

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-search.txt
cp deploy/search-engine.env.example deploy/search-engine.env
python scripts/rebuild_search_index.py --batch-size 10
python scripts/run_search_service.py
```

## Health Check

```bash
curl http://127.0.0.1:8080/health
```

Expected response:

```json
{"status":"ok"}
```

## Load Check

Run 30 to 50 concurrent requests against `/lookup`, `/suggest`, and `/semantic-search`. Record P50, P95, P99, error rate, Supabase CPU, Supabase memory, and Alibaba embedding latency.

## Failure Modes

If Alibaba embedding calls fail, `/semantic-search` returns a controlled service error and dictionary endpoints remain available.

If Supabase vector search fails, `/semantic-search` returns a controlled service error and dictionary endpoints remain available.

If the in-memory dictionary index cannot load, `/health` must fail and the service should not receive production traffic.
