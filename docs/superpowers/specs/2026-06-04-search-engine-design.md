# Dutch Lexicon Search Engine Design

Date: 2026-06-04

## Goal

Build a production-MVP independent search service for the Dutch lexicon application. The service supports two user-facing search modes:

- Dictionary lookup mode for exact lookup, inflected-form lookup, autocomplete, fuzzy correction, and "did you mean" suggestions.
- Semantic lookup mode for Chinese, English, and Dutch natural-language queries that retrieve Dutch lexical entries by meaning.

The search engine itself is also a research subject. The implementation must produce enough structured logs, benchmark data, and explainable scoring metadata to support a later research report on retrieval quality, latency, index design, reranking, graph expansion, and operational tradeoffs.

## Existing Context

The project already has a Supabase/Postgres lexicon schema with these core tables:

- `lemmas`
- `forms`
- `lemma_pos_entries`
- `senses`
- `sense_translations`
- `examples`
- `lemma_examples`
- `lemma_relations`
- `sense_relations`

The schema already enables `pg_trgm` and defines trigram indexes on lemma/form text fields. It also already stores graph-like relation tables for lemma and sense relationships. The search design should use these existing structures rather than creating a separate graph store in the first version.

## Performance Targets

The first version targets product-MVP latency, not a bottom-up custom search engine implementation:

- Dictionary lookup P95: less than 50 ms for hot-path queries.
- Semantic lookup P95: less than 150 ms for typical top-10 queries.
- Semantic result limit: default 10, maximum 50.
- Query service: independent FastAPI service.
- Source of truth: Supabase/Postgres.

The service can later be profiled for a Go serving-layer rewrite, but Python/FastAPI is the first implementation target because the critical vector search work is delegated to native Postgres/pgvector indexes and because Python is better for embedding, evaluation, and research iteration.

## Chosen Architecture

Use architecture option A: an independent FastAPI search service with Supabase pgvector as the vector retrieval backend.

```text
Client / App
  -> FastAPI Search Service
      -> Dictionary Engine
          -> in-memory lemma/form index
          -> in-memory prefix index
          -> Supabase pg_trgm fallback
      -> Semantic Engine
          -> Alibaba Cloud Model Studio text-embedding-v4, 1024 dimensions
          -> Supabase pgvector HNSW cosine RPC
          -> sense-to-lemma aggregation
      -> Graph Expansion
          -> lemma_relations
          -> sense_relations
      -> Reranker
          -> exactness, similarity, frequency, level
      -> Query Logger and Benchmark Recorder
  -> Supabase Postgres
```

## Non-Goals For Version 1

- Do not build a custom HNSW, FAISS-equivalent, or bottom-up vector index implementation.
- Do not introduce Qdrant or another dedicated vector database into the production path.
- Do not use graph relations to change the primary semantic result ordering in the first version.
- Do not embed examples, lemma text, POS labels, frequency values, levels, or UI metadata into the first version of sense embeddings.
- Do not implement real-time index mutation as the primary update path. Batch rebuild is the first version path.

## Embedding Model

The primary embedding model is Alibaba Cloud Model Studio `text-embedding-v4`.

Settings:

- Dimension: 1024.
- Supported query languages: Chinese, English, Dutch.
- Indexed object grain: sense.
- Display result grain: lemma.
- Similarity metric: cosine.
- Vector backend: Supabase Postgres with pgvector HNSW.

Sense embedding text is deliberately minimal:

```text
definition_nl: <Dutch definition text>
translation_zh: <Chinese sense translation>
translation_en: <English sense translation>
```

If one field is missing, the builder omits that line and embeds the remaining sense text. Empty embedding text is skipped and reported in the index build output.

## API Design

Public query APIs:

```text
GET /health
GET /lookup?q=<query>&limit=<1..5>
GET /suggest?q=<prefix>&limit=<1..20>
POST /semantic-search
```

Admin and research APIs:

```text
POST /admin/rebuild-index
POST /admin/update-sense-embedding
POST /admin/refresh-lemma
GET /admin/benchmark-runs/{run_id}
```

`/lookup` returns a best match when confidence is high and a top-5 `did_you_mean` list when correction is needed:

```json
{
  "query": "gelopen",
  "mode": "lookup",
  "best_match": {
    "lemma_id": 1,
    "lemma": "lopen",
    "confidence": 0.96,
    "match_type": "form_exact"
  },
  "did_you_mean": []
}
```

`/semantic-search` accepts an optional limit with default 10 and maximum 50:

```json
{
  "query": "<Chinese query text meaning movement or walking>",
  "limit": 10,
  "include_related": true
}
```

It returns lemma-level results, each with the best matching sense:

```json
{
  "query": "<Chinese query text meaning movement or walking>",
  "language": "zh",
  "results": [
    {
      "lemma_id": 1,
      "lemma": "lopen",
      "level": 1,
      "score": 0.87,
      "matched_sense": {
        "sense_id": 10,
        "definition_nl": "...",
        "translation_zh": "...",
        "translation_en": "...",
        "semantic_score": 0.83
      },
      "matched_reason": {
        "semantic_score": 0.83,
        "frequency_boost": 0.03,
        "level_boost": 0.01
      }
    }
  ],
  "related_results": [
    {
      "lemma_id": 2,
      "lemma": "...",
      "relation_type": "synonym",
      "source_result_lemma_id": 1,
      "source": "lemma_relations",
      "score": 0.62
    }
  ]
}
```

## Supabase Data Model Additions

Add `vector` if it is not already enabled. Supabase provides pgvector through the Postgres extension, and vector similarity queries should be wrapped in SQL functions/RPC because PostgREST is not the right interface for raw vector operators.

New table: `sense_embeddings`

```text
id bigserial primary key
sense_id bigint not null references public.senses(id) on delete cascade
embedding_model text not null
embedding_dim integer not null
embedding extensions.vector(1024) not null
embedding_text_hash text not null
embedding_text_preview text
index_version text not null
created_at timestamptz not null default now()
updated_at timestamptz not null default now()
unique (sense_id, embedding_model, embedding_dim)
```

Indexes:

```text
HNSW index on embedding using cosine distance
btree index on sense_id
btree index on index_version
```

New table: `search_query_logs`

```text
id bigserial primary key
query text not null
mode text not null
detected_language text
latency_ms integer not null
candidate_count integer
result_count integer
top_lemma_ids bigint[]
top_sense_ids bigint[]
cache_hit boolean not null default false
embedding_model text
index_version text
request_metadata jsonb not null default '{}'::jsonb
created_at timestamptz not null default now()
```

New table: `search_benchmark_queries`

```text
id bigserial primary key
query text not null
mode text not null
language text
expected_lemma_ids bigint[]
expected_sense_ids bigint[]
tags text[] not null default '{}'
notes text
created_at timestamptz not null default now()
updated_at timestamptz not null default now()
```

New table: `search_benchmark_runs`

```text
id uuid primary key
index_version text not null
embedding_model text
started_at timestamptz not null
finished_at timestamptz
metrics jsonb not null default '{}'::jsonb
notes text
```

These tables should have RLS enabled before exposure through the Supabase Data API. Public query logs should not be publicly readable by default.

## Dictionary Lookup Algorithm

The search service builds an in-memory dictionary snapshot from Supabase:

```text
lemma_norm -> lemma summary
form_norm -> form and lemma summary
accent-insensitive key -> candidate ids
prefix key -> ranked candidate ids
```

`/lookup` flow:

```text
1. Normalize query:
   - Unicode NFC
   - lowercase
   - trim surrounding whitespace
   - maintain an accent-insensitive auxiliary key
2. Exact form lookup through form_norm.
3. Exact lemma lookup through lemma_norm.
4. Variant lookup through accent-insensitive and punctuation-normalized keys.
5. Fuzzy fallback using Supabase pg_trgm plus edit-distance filtering.
6. Rerank candidates.
7. Return best_match when confidence is high, otherwise return did_you_mean top 5.
```

Dictionary reranking should prefer:

```text
exact form match
exact lemma match
accent-insensitive exact match
prefix match
trigram similarity
edit-distance similarity
form frequency
canonical form
learner level
```

Suggested first-version score shape:

```text
dictionary_score =
  exact_match * 1.0
  + normalized_similarity * 0.4
  + log_frequency_boost * 0.2
  + canonical_boost * 0.1
  + learner_level_boost * 0.05
```

The constants are initial weights, not fixed research conclusions. Query logs and benchmark sets should be used to tune them.

## Suggest Algorithm

`/suggest` is separate from `/lookup`.

Flow:

```text
1. Normalize prefix.
2. Query in-memory prefix index.
3. If too few candidates are found, use pg_trgm fallback.
4. Rank by prefix strength, frequency, level, canonical status, and alphabetical stability.
5. Return compact suggestion cards, not full lexical detail.
```

The prefix index can start as a simple service-memory structure built during index loading. It can later be replaced by a trie, finite-state transducer, or compact prefix table if memory or loading time becomes a problem.

## Semantic Search Algorithm

`/semantic-search` flow:

```text
1. Validate limit:
   - default 10
   - maximum 50
2. Detect language:
   - zh, en, nl, or unknown
3. Generate query embedding with text-embedding-v4, 1024 dimensions.
4. Call Supabase RPC match_senses(query_embedding, candidate_count).
5. Convert pgvector distance to similarity.
6. Aggregate sense candidates to lemma candidates:
   - keep each lemma's highest-scoring matched sense
   - retain secondary matching senses for diagnostics if requested
7. Apply light reranking.
8. Return top lemma results.
9. Add related_results from graph expansion when requested.
10. Write structured query log.
```

Internal candidate count should be larger than the output limit because multiple matching senses may collapse into the same lemma:

```text
candidate_count = min(max(limit * 5, 50), 250)
```

Suggested first-version score shape:

```text
semantic_score =
  vector_similarity * 1.0
  + log_frequency_boost * 0.08
  + learner_level_boost * 0.03
```

The first version should avoid cross-encoder reranking unless offline evaluation later shows a clear quality gap.

## Graph Expansion

Graph relations are used for result expansion and explainability. They do not directly alter the primary ranking in version 1.

Sources:

```text
lemma_relations
sense_relations
family_head_lemma_id
word_family
```

Expansion flow:

```text
1. Take the top semantic or dictionary results.
2. Fetch one-hop lemma and sense relations.
3. Resolve related lemmas.
4. Filter duplicates already present in primary results.
5. Rank related results by source result rank, relation confidence, relation type priority, and related lemma frequency.
6. Return related_results with explicit relation metadata.
```

Relation metadata must include:

```text
relation_type
source_result_lemma_id
source_result_sense_id, when available
source table
relation confidence
```

## Index Rebuild Strategy

Version 1 uses offline batch rebuild with reserved incremental hooks.

Batch rebuild:

```text
1. Export eligible senses and translations from Supabase.
2. Build minimal embedding text from sense definitions and translations.
3. Hash embedding text for change detection.
4. Call text-embedding-v4 in batches.
5. Upsert rows into sense_embeddings.
6. Build or refresh pgvector HNSW index.
7. Build dictionary snapshot from lemmas and forms.
8. Run benchmark suite.
9. Record index_version and build metrics.
```

Reserved incremental interfaces:

```text
POST /admin/update-sense-embedding
POST /admin/refresh-lemma
```

The implementation can add them early as admin endpoints, but they should not be the main production indexing path until the batch path is stable and benchmarked.

## Research Logging And Evaluation

The search engine must emit structured logs for both product debugging and research reporting.

Record at minimum:

```text
query
mode
detected language
latency_ms
candidate_count
result_count
cache_hit
top lemma ids
top sense ids
embedding model
index version
score breakdown, when requested
```

Research report metrics:

```text
Latency: P50, P95, P99
Quality: Recall@K, MRR, nDCG@K
Dictionary: exact hit rate, correction acceptance rate
Semantic: sense recall, lemma aggregation quality
System: index size, index build time, embedding cost, query cost
```

Benchmark query sets should include:

```text
exact lemma lookup
inflected form lookup
misspelled lookup
prefix suggestion
Chinese semantic query
English semantic query
Dutch semantic query
ambiguous sense query
low-frequency lemma query
relation-expansion query
```

## Reliability And Operations

Service startup:

```text
1. Load configuration.
2. Connect to Supabase.
3. Load dictionary snapshot into memory.
4. Verify active index_version.
5. Start serving only after health checks pass.
```

Caching:

```text
in-process LRU for dictionary results
in-process LRU for query embeddings
optional later Redis for multi-instance deployments
```

Failure behavior:

```text
If embedding provider fails:
  semantic-search returns a controlled 503 with retry metadata.

If Supabase vector RPC fails:
  semantic-search returns a controlled 503.

If dictionary memory index is unavailable:
  lookup can fall back to Supabase exact/trigram queries, but health should degrade.
```

Secrets:

```text
Do not expose Supabase service role keys to clients.
Store Alibaba Cloud credentials only in server-side environment variables.
Keep admin endpoints protected.
```

## Verification Plan

Before declaring the first version usable:

```text
1. Unit-test normalization, exact lookup, fuzzy scoring, and limit validation.
2. Integration-test Supabase RPC for vector search.
3. Build a small sense embedding sample and verify HNSW queries return expected senses.
4. Benchmark dictionary lookup P50/P95/P99.
5. Benchmark semantic search P50/P95/P99.
6. Run benchmark queries and calculate Recall@K, MRR, and nDCG@K.
7. Inspect score explanations for representative Chinese, English, and Dutch queries.
8. Verify query logs are written without leaking secrets.
```

## References

- Supabase vector columns: https://supabase.com/docs/guides/ai/vector-columns
- Supabase HNSW indexes: https://supabase.com/docs/guides/ai/vector-indexes/hnsw-indexes
- Supabase pgvector extension: https://supabase.com/docs/guides/database/extensions/pgvector
- Alibaba Cloud Model Studio embedding documentation: https://help.aliyun.com/zh/model-studio/embedding
