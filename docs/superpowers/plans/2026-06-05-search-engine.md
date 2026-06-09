# Dutch Lexicon Search Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent FastAPI search service for Dutch dictionary lookup, autocomplete, semantic sense search, graph expansion, query logging, and benchmark reporting.

**Architecture:** The service runs on a 4 vCPU / 8 GB RAM host and uses Supabase/Postgres as the source of truth and pgvector HNSW backend. FastAPI owns request orchestration, in-memory dictionary indexes, Alibaba Cloud `text-embedding-v4` query embeddings, sense-to-lemma aggregation, explainable reranking, and structured research logs.

**Tech Stack:** Python 3.12+, FastAPI, uvicorn, asyncpg, httpx, Supabase/Postgres, pgvector HNSW, Alibaba Cloud Model Studio `text-embedding-v4` with 1024-dimensional embeddings, unittest.

---

## Execution Notes

This workspace is currently not a git repository. Each task includes a checkpoint command that commits when `.git` exists and otherwise prints a clear no-git checkpoint. Do not initialize git unless the user explicitly asks.

Use this test command unless a task gives a narrower command:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover tests -v
```

Use this import path convention:

```text
lexicon_search/      New search service package
tests/               Existing unittest suite plus new search tests
scripts/             Existing script directory for runnable utilities
supabase/migrations/ Existing Supabase migration directory
docs/                Design, plan, and operations docs
deploy/              Service deployment templates
```

## File Structure

Create these files:

- `requirements-search.txt`: Runtime dependencies for the search service.
- `lexicon_search/__init__.py`: Package marker and version string.
- `lexicon_search/config.py`: Environment parsing and runtime settings.
- `lexicon_search/normalization.py`: Query, lemma, form, accent, and punctuation normalization.
- `lexicon_search/models.py`: Dataclasses for dictionary candidates, semantic candidates, results, logs, and index rows.
- `lexicon_search/scoring.py`: Dictionary score, semantic score, edit distance, and score explanations.
- `lexicon_search/dictionary.py`: In-memory lemma/form/prefix indexes and lookup/suggest methods.
- `lexicon_search/db.py`: Async Postgres pool lifecycle and vector literal helpers.
- `lexicon_search/repositories.py`: Supabase/Postgres queries for dictionaries, semantic candidates, graph relations, logs, and benchmark rows.
- `lexicon_search/embeddings.py`: Alibaba Cloud OpenAI-compatible embedding client.
- `lexicon_search/index_builder.py`: Batch sense text export, hashing, embedding generation, and upsert orchestration.
- `lexicon_search/semantic.py`: Query embedding, pgvector candidate fetch, sense-to-lemma aggregation, reranking.
- `lexicon_search/graph.py`: One-hop graph expansion from lemma and sense relations.
- `lexicon_search/service.py`: High-level lookup, suggest, semantic search, logging orchestration.
- `lexicon_search/api.py`: FastAPI app and route models.
- `scripts/rebuild_search_index.py`: CLI for batch index rebuild.
- `scripts/run_search_benchmarks.py`: CLI for benchmark execution.
- `scripts/run_search_service.py`: Local service launcher.
- `supabase/migrations/20260605090000_search_engine_schema.sql`: Search tables, HNSW index, and `match_senses` RPC.
- `deploy/search-engine.env.example`: Server environment template.
- `deploy/search-engine.service`: systemd service template for a 4c8g host.
- `docs/search-engine-operations.md`: Deployment, capacity, failure, and benchmark runbook.

Create or modify these tests:

- `tests/test_search_config.py`
- `tests/test_search_normalization.py`
- `tests/test_search_models.py`
- `tests/test_search_scoring.py`
- `tests/test_dictionary_index.py`
- `tests/test_search_db.py`
- `tests/test_embeddings.py`
- `tests/test_index_builder.py`
- `tests/test_semantic_search.py`
- `tests/test_graph_expansion.py`
- `tests/test_search_service.py`
- `tests/test_search_api.py`
- `tests/test_search_benchmarks.py`

---

### Task 1: Search Package Skeleton And Dependencies

**Files:**
- Create: `requirements-search.txt`
- Create: `lexicon_search/__init__.py`
- Test: `tests/test_search_config.py`

- [ ] **Step 1: Write the failing package import test**

Create `tests/test_search_config.py`:

```python
import unittest


class SearchPackageTests(unittest.TestCase):
    def test_package_imports(self):
        import lexicon_search

        self.assertEqual(lexicon_search.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the package import test and verify it fails**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lexicon_search'`.

- [ ] **Step 3: Create the dependency file**

Create `requirements-search.txt`:

```text
fastapi>=0.115,<1
uvicorn[standard]>=0.32,<1
asyncpg>=0.30,<1
httpx>=0.28,<1
```

- [ ] **Step 4: Create the package marker**

Create `lexicon_search/__init__.py`:

```python
from __future__ import annotations

__version__ = "0.1.0"
```

- [ ] **Step 5: Run the package import test and verify it passes**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_config.py -v
```

Expected: PASS with `Ran 1 test`.

- [ ] **Step 6: Checkpoint**

Run:

```bash
if test -d .git; then git add requirements-search.txt lexicon_search/__init__.py tests/test_search_config.py && git commit -m "feat: add search service package skeleton"; else echo "not a git repository; checkpoint after Task 1"; fi
```

Expected when this workspace is unchanged: `not a git repository; checkpoint after Task 1`.

---

### Task 2: Runtime Configuration

**Files:**
- Create: `lexicon_search/config.py`
- Modify: `tests/test_search_config.py`

- [ ] **Step 1: Extend the config tests**

Replace `tests/test_search_config.py` with:

```python
import unittest

from lexicon_search.config import SearchConfig, load_config


class SearchPackageTests(unittest.TestCase):
    def test_package_imports(self):
        import lexicon_search

        self.assertEqual(lexicon_search.__version__, "0.1.0")


class SearchConfigTests(unittest.TestCase):
    def test_load_config_from_mapping(self):
        config = load_config(
            {
                "DATABASE_URL": "postgresql://user:pass@example.com:5432/postgres",
                "BAILIAN_API_KEY": "sk-test",
                "BAILIAN_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "SEARCH_INDEX_VERSION": "search-2026-06-05",
                "SEARCH_LOG_QUERIES": "false",
                "SEARCH_MAX_LIMIT": "50",
                "SEARCH_EMBEDDING_DIM": "1024",
            }
        )

        self.assertIsInstance(config, SearchConfig)
        self.assertEqual(config.database_url, "postgresql://user:pass@example.com:5432/postgres")
        self.assertEqual(config.bailian_api_key, "sk-test")
        self.assertEqual(config.bailian_base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.assertEqual(config.index_version, "search-2026-06-05")
        self.assertFalse(config.log_queries)
        self.assertEqual(config.max_limit, 50)
        self.assertEqual(config.embedding_dim, 1024)

    def test_missing_required_values_raise(self):
        with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
            load_config({"BAILIAN_API_KEY": "sk-test"})

        with self.assertRaisesRegex(ValueError, "BAILIAN_API_KEY"):
            load_config({"DATABASE_URL": "postgresql://example"})

    def test_limit_and_dimension_are_validated(self):
        with self.assertRaisesRegex(ValueError, "SEARCH_MAX_LIMIT"):
            load_config(
                {
                    "DATABASE_URL": "postgresql://example",
                    "BAILIAN_API_KEY": "sk-test",
                    "SEARCH_MAX_LIMIT": "500",
                }
            )

        with self.assertRaisesRegex(ValueError, "SEARCH_EMBEDDING_DIM"):
            load_config(
                {
                    "DATABASE_URL": "postgresql://example",
                    "BAILIAN_API_KEY": "sk-test",
                    "SEARCH_EMBEDDING_DIM": "1536",
                }
            )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the config tests and verify they fail**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lexicon_search.config'`.

- [ ] **Step 3: Implement `lexicon_search/config.py`**

Create `lexicon_search/config.py`:

```python
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
        bailian_base_url=values.get("BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/"),
        embedding_model=values.get("SEARCH_EMBEDDING_MODEL", "text-embedding-v4").strip() or "text-embedding-v4",
        embedding_dim=embedding_dim,
        index_version=values.get("SEARCH_INDEX_VERSION", "search-v1").strip() or "search-v1",
        max_limit=max_limit,
        log_queries=_bool_value(values, "SEARCH_LOG_QUERIES", True),
    )
```

- [ ] **Step 4: Run the config tests and verify they pass**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_config.py -v
```

Expected: PASS with `Ran 4 tests`.

- [ ] **Step 5: Checkpoint**

Run:

```bash
if test -d .git; then git add lexicon_search/config.py tests/test_search_config.py && git commit -m "feat: add search service configuration"; else echo "not a git repository; checkpoint after Task 2"; fi
```

---

### Task 3: Query Normalization

**Files:**
- Create: `lexicon_search/normalization.py`
- Test: `tests/test_search_normalization.py`

- [ ] **Step 1: Write normalization tests**

Create `tests/test_search_normalization.py`:

```python
import unittest

from lexicon_search.normalization import accent_key, normalize_query, punctuation_key


class SearchNormalizationTests(unittest.TestCase):
    def test_normalize_query_uses_nfc_casefold_and_trim(self):
        self.assertEqual(normalize_query("  CAFÉ  "), "café")

    def test_accent_key_removes_combining_marks(self):
        self.assertEqual(accent_key("café"), "cafe")
        self.assertEqual(accent_key("e\u0301én"), "een")

    def test_punctuation_key_normalizes_apostrophes_and_hyphens(self):
        self.assertEqual(punctuation_key("opa's fiets"), "opa s fiets")
        self.assertEqual(punctuation_key("auto-ongeluk"), "auto ongeluk")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run normalization tests and verify they fail**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_normalization.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lexicon_search.normalization'`.

- [ ] **Step 3: Implement normalization helpers**

Create `lexicon_search/normalization.py`:

```python
from __future__ import annotations

import re
import unicodedata


PUNCT_RE = re.compile(r"[-'’`´]+")
SPACE_RE = re.compile(r"\s+")


def normalize_query(value: str) -> str:
    return SPACE_RE.sub(" ", unicodedata.normalize("NFC", value).strip().casefold())


def accent_key(value: str) -> str:
    normalized = unicodedata.normalize("NFD", normalize_query(value))
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", stripped)


def punctuation_key(value: str) -> str:
    replaced = PUNCT_RE.sub(" ", accent_key(value))
    return SPACE_RE.sub(" ", replaced).strip()
```

- [ ] **Step 4: Run normalization tests and verify they pass**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_normalization.py -v
```

Expected: PASS with `Ran 3 tests`.

- [ ] **Step 5: Checkpoint**

Run:

```bash
if test -d .git; then git add lexicon_search/normalization.py tests/test_search_normalization.py && git commit -m "feat: add search normalization helpers"; else echo "not a git repository; checkpoint after Task 3"; fi
```

---

### Task 4: Search Domain Models

**Files:**
- Create: `lexicon_search/models.py`
- Test: `tests/test_search_models.py`

- [ ] **Step 1: Write model tests**

Create `tests/test_search_models.py`:

```python
import unittest

from lexicon_search.models import LemmaSummary, LookupCandidate, SemanticCandidate


class SearchModelTests(unittest.TestCase):
    def test_lookup_candidate_to_public_dict(self):
        lemma = LemmaSummary(lemma_id=1, lemma="lopen", lemma_norm="lopen", level=1, frequency=1200)
        candidate = LookupCandidate(
            lemma=lemma,
            form_id=5,
            form="gelopen",
            match_type="form_exact",
            score=0.96,
            confidence=0.96,
        )

        self.assertEqual(
            candidate.to_public_dict(),
            {
                "lemma_id": 1,
                "lemma": "lopen",
                "level": 1,
                "form_id": 5,
                "form": "gelopen",
                "match_type": "form_exact",
                "score": 0.96,
                "confidence": 0.96,
            },
        )

    def test_semantic_candidate_similarity(self):
        candidate = SemanticCandidate(
            sense_id=10,
            lemma_id=1,
            lemma="lopen",
            level=1,
            definition_nl="zich te voet voortbewegen",
            translation_zh="步行",
            translation_en="to walk",
            vector_similarity=0.82,
            frequency=1200,
        )

        self.assertEqual(candidate.best_sense_id, 10)
        self.assertEqual(candidate.lemma, "lopen")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run model tests and verify they fail**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_models.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lexicon_search.models'`.

- [ ] **Step 3: Implement models**

Create `lexicon_search/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LemmaSummary:
    lemma_id: int
    lemma: str
    lemma_norm: str
    level: int | None
    frequency: int


@dataclass(frozen=True)
class FormSummary:
    form_id: int
    form: str
    form_norm: str
    lemma: LemmaSummary
    is_canonical: bool
    frequency: int


@dataclass(frozen=True)
class LookupCandidate:
    lemma: LemmaSummary
    form_id: int | None
    form: str | None
    match_type: str
    score: float
    confidence: float

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "lemma_id": self.lemma.lemma_id,
            "lemma": self.lemma.lemma,
            "level": self.lemma.level,
            "form_id": self.form_id,
            "form": self.form,
            "match_type": self.match_type,
            "score": round(self.score, 6),
            "confidence": round(self.confidence, 6),
        }


@dataclass(frozen=True)
class SemanticCandidate:
    sense_id: int
    lemma_id: int
    lemma: str
    level: int | None
    definition_nl: str
    translation_zh: str
    translation_en: str
    vector_similarity: float
    frequency: int
    best_sense_id: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "best_sense_id", self.sense_id)


@dataclass(frozen=True)
class RelatedResult:
    lemma_id: int
    lemma: str
    relation_type: str
    source_result_lemma_id: int
    source_result_sense_id: int | None
    source: str
    score: float


@dataclass(frozen=True)
class SearchLogRecord:
    query: str
    mode: str
    detected_language: str | None
    latency_ms: int
    candidate_count: int | None
    result_count: int
    top_lemma_ids: list[int]
    top_sense_ids: list[int]
    cache_hit: bool
    embedding_model: str | None
    index_version: str | None
```

- [ ] **Step 4: Run model tests and verify they pass**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_models.py -v
```

Expected: PASS with `Ran 2 tests`.

- [ ] **Step 5: Checkpoint**

Run:

```bash
if test -d .git; then git add lexicon_search/models.py tests/test_search_models.py && git commit -m "feat: add search domain models"; else echo "not a git repository; checkpoint after Task 4"; fi
```

---

### Task 5: Scoring Functions

**Files:**
- Create: `lexicon_search/scoring.py`
- Test: `tests/test_search_scoring.py`

- [ ] **Step 1: Write scoring tests**

Create `tests/test_search_scoring.py`:

```python
import unittest

from lexicon_search.scoring import (
    dictionary_score,
    edit_distance,
    normalized_similarity,
    semantic_score,
)


class SearchScoringTests(unittest.TestCase):
    def test_edit_distance(self):
        self.assertEqual(edit_distance("lopen", "lopen"), 0)
        self.assertEqual(edit_distance("lopen", "lopem"), 1)
        self.assertEqual(edit_distance("lopen", "lopenen"), 2)

    def test_normalized_similarity(self):
        self.assertEqual(normalized_similarity("lopen", "lopen"), 1.0)
        self.assertGreater(normalized_similarity("lopen", "lopem"), 0.7)

    def test_dictionary_score_prefers_exact_match(self):
        exact = dictionary_score(
            exact_match=True,
            normalized_similarity_value=1.0,
            frequency=100,
            is_canonical=True,
            level=1,
        )
        fuzzy = dictionary_score(
            exact_match=False,
            normalized_similarity_value=0.85,
            frequency=100,
            is_canonical=True,
            level=1,
        )
        self.assertGreater(exact.score, fuzzy.score)
        self.assertIn("exact_match", exact.reasons)

    def test_semantic_score_uses_similarity_as_main_signal(self):
        high = semantic_score(vector_similarity=0.9, frequency=10, level=4)
        low = semantic_score(vector_similarity=0.7, frequency=100000, level=1)
        self.assertGreater(high.score, low.score)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run scoring tests and verify they fail**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_scoring.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lexicon_search.scoring'`.

- [ ] **Step 3: Implement scoring functions**

Create `lexicon_search/scoring.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ScoreBreakdown:
    score: float
    reasons: dict[str, float]


def edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + cost,
                )
            )
        previous = current
    return previous[-1]


def normalized_similarity(left: str, right: str) -> float:
    max_len = max(len(left), len(right), 1)
    return max(0.0, 1.0 - edit_distance(left, right) / max_len)


def _frequency_boost(frequency: int, weight: float) -> float:
    if frequency <= 0:
        return 0.0
    return min(math.log10(frequency + 1) / 6.0, 1.0) * weight


def _level_boost(level: int | None, weight: float) -> float:
    if level is None:
        return 0.0
    if level <= 1:
        return weight
    if level == 2:
        return weight * 0.7
    if level == 3:
        return weight * 0.35
    return 0.0


def dictionary_score(
    *,
    exact_match: bool,
    normalized_similarity_value: float,
    frequency: int,
    is_canonical: bool,
    level: int | None,
) -> ScoreBreakdown:
    reasons = {
        "exact_match": 1.0 if exact_match else 0.0,
        "normalized_similarity": max(0.0, min(normalized_similarity_value, 1.0)) * 0.4,
        "frequency_boost": _frequency_boost(frequency, 0.2),
        "canonical_boost": 0.1 if is_canonical else 0.0,
        "level_boost": _level_boost(level, 0.05),
    }
    return ScoreBreakdown(score=sum(reasons.values()), reasons=reasons)


def semantic_score(*, vector_similarity: float, frequency: int, level: int | None) -> ScoreBreakdown:
    reasons = {
        "semantic_score": max(0.0, min(vector_similarity, 1.0)),
        "frequency_boost": _frequency_boost(frequency, 0.08),
        "level_boost": _level_boost(level, 0.03),
    }
    return ScoreBreakdown(score=sum(reasons.values()), reasons=reasons)
```

- [ ] **Step 4: Run scoring tests and verify they pass**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_scoring.py -v
```

Expected: PASS with `Ran 4 tests`.

- [ ] **Step 5: Checkpoint**

Run:

```bash
if test -d .git; then git add lexicon_search/scoring.py tests/test_search_scoring.py && git commit -m "feat: add search scoring functions"; else echo "not a git repository; checkpoint after Task 5"; fi
```

---

### Task 6: In-Memory Dictionary Index

**Files:**
- Create: `lexicon_search/dictionary.py`
- Test: `tests/test_dictionary_index.py`

- [ ] **Step 1: Write dictionary index tests**

Create `tests/test_dictionary_index.py`:

```python
import unittest

from lexicon_search.dictionary import DictionaryIndex
from lexicon_search.models import FormSummary, LemmaSummary


class DictionaryIndexTests(unittest.TestCase):
    def setUp(self):
        self.lopen = LemmaSummary(lemma_id=1, lemma="lopen", lemma_norm="lopen", level=1, frequency=1200)
        self.lezen = LemmaSummary(lemma_id=2, lemma="lezen", lemma_norm="lezen", level=1, frequency=900)
        self.index = DictionaryIndex.from_rows(
            lemmas=[self.lopen, self.lezen],
            forms=[
                FormSummary(
                    form_id=10,
                    form="gelopen",
                    form_norm="gelopen",
                    lemma=self.lopen,
                    is_canonical=False,
                    frequency=300,
                ),
                FormSummary(
                    form_id=11,
                    form="lopen",
                    form_norm="lopen",
                    lemma=self.lopen,
                    is_canonical=True,
                    frequency=1200,
                ),
            ],
        )

    def test_lookup_exact_form_returns_lemma(self):
        candidates = self.index.lookup("gelopen", limit=5)

        self.assertEqual(candidates[0].lemma.lemma, "lopen")
        self.assertEqual(candidates[0].match_type, "form_exact")

    def test_lookup_exact_lemma_returns_lemma(self):
        candidates = self.index.lookup("lezen", limit=5)

        self.assertEqual(candidates[0].lemma.lemma, "lezen")
        self.assertEqual(candidates[0].match_type, "lemma_exact")

    def test_suggest_prefix_returns_ranked_candidates(self):
        suggestions = self.index.suggest("lo", limit=5)

        self.assertEqual(suggestions[0].lemma.lemma, "lopen")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run dictionary tests and verify they fail**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_dictionary_index.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lexicon_search.dictionary'`.

- [ ] **Step 3: Implement dictionary index**

Create `lexicon_search/dictionary.py`:

```python
from __future__ import annotations

from collections import defaultdict

from lexicon_search.models import FormSummary, LemmaSummary, LookupCandidate
from lexicon_search.normalization import accent_key, normalize_query, punctuation_key
from lexicon_search.scoring import dictionary_score, normalized_similarity


class DictionaryIndex:
    def __init__(
        self,
        lemmas_by_norm: dict[str, LemmaSummary],
        forms_by_norm: dict[str, list[FormSummary]],
        accent_entries: dict[str, list[LookupCandidate]],
        prefix_entries: dict[str, list[LookupCandidate]],
    ) -> None:
        self.lemmas_by_norm = lemmas_by_norm
        self.forms_by_norm = forms_by_norm
        self.accent_entries = accent_entries
        self.prefix_entries = prefix_entries

    @classmethod
    def from_rows(cls, lemmas: list[LemmaSummary], forms: list[FormSummary]) -> "DictionaryIndex":
        lemmas_by_norm = {lemma.lemma_norm: lemma for lemma in lemmas}
        forms_by_norm: dict[str, list[FormSummary]] = defaultdict(list)
        accent_entries: dict[str, list[LookupCandidate]] = defaultdict(list)
        prefix_entries: dict[str, list[LookupCandidate]] = defaultdict(list)

        for form in forms:
            forms_by_norm[form.form_norm].append(form)
            candidate = _candidate_from_form(form, form.form_norm, "form_exact")
            accent_entries[accent_key(form.form_norm)].append(candidate)
            accent_entries[punctuation_key(form.form_norm)].append(candidate)
            for prefix in _prefixes(form.form_norm):
                prefix_entries[prefix].append(candidate)

        for lemma in lemmas:
            candidate = _candidate_from_lemma(lemma, "lemma_exact")
            accent_entries[accent_key(lemma.lemma_norm)].append(candidate)
            accent_entries[punctuation_key(lemma.lemma_norm)].append(candidate)
            for prefix in _prefixes(lemma.lemma_norm):
                prefix_entries[prefix].append(candidate)

        for entries in prefix_entries.values():
            entries.sort(key=lambda item: (-item.score, item.lemma.lemma))

        return cls(dict(lemmas_by_norm), dict(forms_by_norm), dict(accent_entries), dict(prefix_entries))

    def lookup(self, query: str, limit: int = 5) -> list[LookupCandidate]:
        normalized = normalize_query(query)
        candidates: list[LookupCandidate] = []

        for form in self.forms_by_norm.get(normalized, []):
            candidates.append(_candidate_from_form(form, normalized, "form_exact"))

        lemma = self.lemmas_by_norm.get(normalized)
        if lemma is not None:
            candidates.append(_candidate_from_lemma(lemma, "lemma_exact"))

        if not candidates:
            candidates.extend(self.accent_entries.get(accent_key(normalized), []))

        if not candidates:
            candidates.extend(self.accent_entries.get(punctuation_key(normalized), []))

        return _dedupe_candidates(candidates)[:limit]

    def suggest(self, query: str, limit: int = 10) -> list[LookupCandidate]:
        normalized = normalize_query(query)
        candidates = self.prefix_entries.get(normalized, [])
        return _dedupe_candidates(candidates)[:limit]


def _prefixes(value: str) -> list[str]:
    return [value[:index] for index in range(1, min(len(value), 20) + 1)]


def _candidate_from_form(form: FormSummary, query: str, match_type: str) -> LookupCandidate:
    breakdown = dictionary_score(
        exact_match=form.form_norm == query,
        normalized_similarity_value=normalized_similarity(query, form.form_norm),
        frequency=form.frequency or form.lemma.frequency,
        is_canonical=form.is_canonical,
        level=form.lemma.level,
    )
    return LookupCandidate(
        lemma=form.lemma,
        form_id=form.form_id,
        form=form.form,
        match_type=match_type,
        score=breakdown.score,
        confidence=min(breakdown.score, 1.0),
    )


def _candidate_from_lemma(lemma: LemmaSummary, match_type: str) -> LookupCandidate:
    breakdown = dictionary_score(
        exact_match=True,
        normalized_similarity_value=1.0,
        frequency=lemma.frequency,
        is_canonical=True,
        level=lemma.level,
    )
    return LookupCandidate(
        lemma=lemma,
        form_id=None,
        form=None,
        match_type=match_type,
        score=breakdown.score,
        confidence=min(breakdown.score, 1.0),
    )


def _dedupe_candidates(candidates: list[LookupCandidate]) -> list[LookupCandidate]:
    best: dict[int, LookupCandidate] = {}
    for candidate in candidates:
        existing = best.get(candidate.lemma.lemma_id)
        if existing is None or candidate.score > existing.score:
            best[candidate.lemma.lemma_id] = candidate
    return sorted(best.values(), key=lambda item: (-item.score, item.lemma.lemma))
```

- [ ] **Step 4: Run dictionary tests and verify they pass**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_dictionary_index.py -v
```

Expected: PASS with `Ran 3 tests`.

- [ ] **Step 5: Checkpoint**

Run:

```bash
if test -d .git; then git add lexicon_search/dictionary.py tests/test_dictionary_index.py && git commit -m "feat: add in-memory dictionary index"; else echo "not a git repository; checkpoint after Task 6"; fi
```

---

### Task 7: Supabase Search Schema And Vector RPC

**Files:**
- Create: `supabase/migrations/20260605090000_search_engine_schema.sql`

- [ ] **Step 1: Check Supabase CLI availability**

Run:

```bash
supabase --version
```

Expected: prints a Supabase CLI version. If the command is missing, create the migration file manually at the path in this task and apply it through the Supabase dashboard SQL editor during integration verification.

- [ ] **Step 2: Create the search schema migration**

Create `supabase/migrations/20260605090000_search_engine_schema.sql`:

```sql
create extension if not exists vector with schema extensions;

create table if not exists public.sense_embeddings (
  id bigserial primary key,
  sense_id bigint not null references public.senses(id) on delete cascade,
  embedding_model text not null,
  embedding_dim integer not null check (embedding_dim = 1024),
  embedding extensions.vector(1024) not null,
  embedding_text_hash text not null,
  embedding_text_preview text,
  index_version text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (sense_id, embedding_model, embedding_dim)
);

create index if not exists sense_embeddings_sense_id_idx
  on public.sense_embeddings (sense_id);

create index if not exists sense_embeddings_index_version_idx
  on public.sense_embeddings (index_version);

create index if not exists sense_embeddings_embedding_hnsw_idx
  on public.sense_embeddings
  using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

create table if not exists public.search_query_logs (
  id bigserial primary key,
  query text not null,
  mode text not null check (mode in ('lookup', 'suggest', 'semantic')),
  detected_language text,
  latency_ms integer not null check (latency_ms >= 0),
  candidate_count integer,
  result_count integer not null check (result_count >= 0),
  top_lemma_ids bigint[],
  top_sense_ids bigint[],
  cache_hit boolean not null default false,
  embedding_model text,
  index_version text,
  request_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists search_query_logs_created_at_idx
  on public.search_query_logs (created_at desc);

create index if not exists search_query_logs_mode_created_idx
  on public.search_query_logs (mode, created_at desc);

create table if not exists public.search_benchmark_queries (
  id bigserial primary key,
  query text not null,
  mode text not null check (mode in ('lookup', 'suggest', 'semantic')),
  language text,
  expected_lemma_ids bigint[],
  expected_sense_ids bigint[],
  tags text[] not null default '{}',
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.search_benchmark_runs (
  id uuid primary key default gen_random_uuid(),
  index_version text not null,
  embedding_model text,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  metrics jsonb not null default '{}'::jsonb,
  notes text
);

drop trigger if exists sense_embeddings_set_updated_at on public.sense_embeddings;
create trigger sense_embeddings_set_updated_at
before update on public.sense_embeddings
for each row execute function public.set_updated_at();

drop trigger if exists search_benchmark_queries_set_updated_at on public.search_benchmark_queries;
create trigger search_benchmark_queries_set_updated_at
before update on public.search_benchmark_queries
for each row execute function public.set_updated_at();

create or replace function public.match_senses(
  query_embedding extensions.vector(1024),
  match_count integer default 50,
  active_index_version text default null
)
returns table (
  sense_id bigint,
  lemma_id bigint,
  lemma text,
  level smallint,
  definition_nl text,
  translation_zh text,
  translation_en text,
  frequency bigint,
  distance double precision,
  similarity double precision
)
language sql
stable
as $$
  with ranked as (
    select
      s.id as sense_id,
      s.lemma_id,
      l.lemma,
      l.level,
      coalesce(s.display_definition_nl, s.definition_nl, '') as definition_nl,
      max(st_zh.gloss) filter (where st_zh.lang = 'zh') as translation_zh,
      max(st_en.gloss) filter (where st_en.lang = 'en') as translation_en,
      coalesce(l.cc100_freq, l.subtlex_freq, 0) as frequency,
      (se.embedding <=> query_embedding)::double precision as distance
    from public.sense_embeddings se
    join public.senses s on s.id = se.sense_id
    join public.lemmas l on l.id = s.lemma_id
    left join public.sense_translations st_zh
      on st_zh.sense_id = s.id and st_zh.lang = 'zh'
    left join public.sense_translations st_en
      on st_en.sense_id = s.id and st_en.lang = 'en'
    where s.merged_into_sense_id is null
      and (active_index_version is null or se.index_version = active_index_version)
    group by
      s.id,
      s.lemma_id,
      l.lemma,
      l.level,
      s.display_definition_nl,
      s.definition_nl,
      l.cc100_freq,
      l.subtlex_freq,
      se.embedding
    order by se.embedding <=> query_embedding
    limit least(greatest(match_count, 1), 250)
  )
  select
    ranked.sense_id,
    ranked.lemma_id,
    ranked.lemma,
    ranked.level,
    ranked.definition_nl,
    coalesce(ranked.translation_zh, '') as translation_zh,
    coalesce(ranked.translation_en, '') as translation_en,
    ranked.frequency,
    ranked.distance,
    (1.0 - ranked.distance) as similarity
  from ranked
  order by ranked.distance asc;
$$;

alter table public.sense_embeddings enable row level security;
alter table public.search_query_logs enable row level security;
alter table public.search_benchmark_queries enable row level security;
alter table public.search_benchmark_runs enable row level security;

revoke all on public.sense_embeddings from anon, authenticated;
revoke all on public.search_query_logs from anon, authenticated;
revoke all on public.search_benchmark_queries from anon, authenticated;
revoke all on public.search_benchmark_runs from anon, authenticated;
revoke all on function public.match_senses(extensions.vector(1024), integer, text) from public;
grant execute on function public.match_senses(extensions.vector(1024), integer, text) to authenticated;
```

- [ ] **Step 3: Validate SQL syntax locally when Supabase CLI exists**

Run:

```bash
supabase db reset --local --yes
```

Expected: local reset completes and applies `20260605090000_search_engine_schema.sql`. If Docker or the local Supabase stack is unavailable, record the exact command failure in the execution notes and validate through the remote SQL editor before running integration tests.

- [ ] **Step 4: Checkpoint**

Run:

```bash
if test -d .git; then git add supabase/migrations/20260605090000_search_engine_schema.sql && git commit -m "feat: add search engine schema"; else echo "not a git repository; checkpoint after Task 7"; fi
```

---

### Task 8: Database Client And Repository Interfaces

**Files:**
- Create: `lexicon_search/db.py`
- Create: `lexicon_search/repositories.py`
- Test: `tests/test_search_db.py`

- [ ] **Step 1: Write DB helper tests**

Create `tests/test_search_db.py`:

```python
import unittest

from lexicon_search.db import vector_literal


class SearchDbTests(unittest.TestCase):
    def test_vector_literal_serializes_1024_dimension_vectors(self):
        value = vector_literal([0.1] * 1024)

        self.assertTrue(value.startswith("[0.1,"))
        self.assertTrue(value.endswith("]"))

    def test_vector_literal_rejects_wrong_dimension(self):
        with self.assertRaisesRegex(ValueError, "1024"):
            vector_literal([0.1, 0.2])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run DB tests and verify they fail**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_db.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lexicon_search.db'`.

- [ ] **Step 3: Implement DB helpers**

Create `lexicon_search/db.py`:

```python
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
```

- [ ] **Step 4: Implement repository interfaces**

Create `lexicon_search/repositories.py`:

```python
from __future__ import annotations

import json
from typing import Any

from lexicon_search.db import Database, vector_literal
from lexicon_search.models import FormSummary, LemmaSummary, LookupCandidate, RelatedResult, SearchLogRecord, SemanticCandidate
from lexicon_search.scoring import dictionary_score


class SearchRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def load_dictionary_rows(self) -> tuple[list[LemmaSummary], list[FormSummary]]:
        async with self.database.acquire() as connection:
            lemma_rows = await connection.fetch(
                """
                select id, lemma, lemma_norm, level, coalesce(cc100_freq, subtlex_freq, 0) as frequency
                from public.lemmas
                where review_status = 'accepted'
                """
            )
            form_rows = await connection.fetch(
                """
                select
                  f.id as form_id,
                  f.form,
                  f.form_norm,
                  f.is_canonical,
                  coalesce(fcs.freq_count, 0) as frequency,
                  l.id as lemma_id,
                  l.lemma,
                  l.lemma_norm,
                  l.level,
                  coalesce(l.cc100_freq, l.subtlex_freq, 0) as lemma_frequency
                from public.forms f
                join public.lemmas l on l.id = f.lemma_id
                left join public.form_corpus_stats fcs on fcs.form_id = f.id
                where l.review_status = 'accepted'
                """
            )

        lemmas = [
            LemmaSummary(
                lemma_id=int(row["id"]),
                lemma=row["lemma"],
                lemma_norm=row["lemma_norm"],
                level=row["level"],
                frequency=int(row["frequency"] or 0),
            )
            for row in lemma_rows
        ]
        lemmas_by_id = {lemma.lemma_id: lemma for lemma in lemmas}
        forms = [
            FormSummary(
                form_id=int(row["form_id"]),
                form=row["form"],
                form_norm=row["form_norm"],
                lemma=lemmas_by_id[int(row["lemma_id"])],
                is_canonical=bool(row["is_canonical"]),
                frequency=int(row["frequency"] or 0),
            )
            for row in form_rows
            if int(row["lemma_id"]) in lemmas_by_id
        ]
        return lemmas, forms

    async def match_senses(self, embedding: list[float], candidate_count: int, index_version: str) -> list[SemanticCandidate]:
        literal = vector_literal(embedding)
        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                select *
                from public.match_senses($1::extensions.vector(1024), $2::integer, $3::text)
                """,
                literal,
                candidate_count,
                index_version,
            )
        return [
            SemanticCandidate(
                sense_id=int(row["sense_id"]),
                lemma_id=int(row["lemma_id"]),
                lemma=row["lemma"],
                level=row["level"],
                definition_nl=row["definition_nl"] or "",
                translation_zh=row["translation_zh"] or "",
                translation_en=row["translation_en"] or "",
                vector_similarity=float(row["similarity"]),
                frequency=int(row["frequency"] or 0),
            )
            for row in rows
        ]

    async def fuzzy_lookup(self, query_norm: str, limit: int) -> list[LookupCandidate]:
        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                select *
                from (
                  select
                    l.id as lemma_id,
                    l.lemma,
                    l.lemma_norm,
                    l.level,
                    coalesce(l.cc100_freq, l.subtlex_freq, 0) as frequency,
                    null::bigint as form_id,
                    null::text as form,
                    true as is_canonical,
                    'lemma_fuzzy' as match_type,
                    similarity(l.lemma_norm, $1) as text_similarity
                  from public.lemmas l
                  where l.review_status = 'accepted'
                    and l.lemma_norm % $1
                  union all
                  select
                    l.id as lemma_id,
                    l.lemma,
                    l.lemma_norm,
                    l.level,
                    coalesce(fcs.freq_count, l.cc100_freq, l.subtlex_freq, 0) as frequency,
                    f.id as form_id,
                    f.form,
                    f.is_canonical,
                    'form_fuzzy' as match_type,
                    similarity(f.form_norm, $1) as text_similarity
                  from public.forms f
                  join public.lemmas l on l.id = f.lemma_id
                  left join public.form_corpus_stats fcs on fcs.form_id = f.id
                  where l.review_status = 'accepted'
                    and f.form_norm % $1
                ) candidates
                order by text_similarity desc, frequency desc, lemma asc
                limit $2
                """,
                query_norm,
                limit,
            )
        output = []
        for row in rows:
            lemma = LemmaSummary(
                lemma_id=int(row["lemma_id"]),
                lemma=row["lemma"],
                lemma_norm=row["lemma_norm"],
                level=row["level"],
                frequency=int(row["frequency"] or 0),
            )
            breakdown = dictionary_score(
                exact_match=False,
                normalized_similarity_value=float(row["text_similarity"] or 0.0),
                frequency=int(row["frequency"] or 0),
                is_canonical=bool(row["is_canonical"]),
                level=row["level"],
            )
            output.append(
                LookupCandidate(
                    lemma=lemma,
                    form_id=None if row["form_id"] is None else int(row["form_id"]),
                    form=row["form"],
                    match_type=row["match_type"],
                    score=breakdown.score,
                    confidence=min(breakdown.score, 1.0),
                )
            )
        return output

    async def fuzzy_suggest(self, query_norm: str, limit: int) -> list[LookupCandidate]:
        return await self.fuzzy_lookup(query_norm, limit)

    async def write_query_log(self, record: SearchLogRecord, request_metadata: dict[str, Any]) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                insert into public.search_query_logs (
                  query, mode, detected_language, latency_ms, candidate_count, result_count,
                  top_lemma_ids, top_sense_ids, cache_hit, embedding_model, index_version, request_metadata
                )
                values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)
                """,
                record.query,
                record.mode,
                record.detected_language,
                record.latency_ms,
                record.candidate_count,
                record.result_count,
                record.top_lemma_ids,
                record.top_sense_ids,
                record.cache_hit,
                record.embedding_model,
                record.index_version,
                json.dumps(request_metadata, ensure_ascii=False, sort_keys=True),
            )

    async def load_related_results(self, lemma_ids: list[int], sense_ids: list[int]) -> list[RelatedResult]:
        if not lemma_ids and not sense_ids:
            return []
        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                select
                  lr.lemma_id_to as lemma_id,
                  l.lemma,
                  lr.relation_type,
                  lr.lemma_id_from as source_result_lemma_id,
                  null::bigint as source_result_sense_id,
                  'lemma_relations' as source,
                  lr.confidence::double precision as score
                from public.lemma_relations lr
                join public.lemmas l on l.id = lr.lemma_id_to
                where lr.lemma_id_from = any($1::bigint[])
                union all
                select
                  target.lemma_id as lemma_id,
                  l.lemma,
                  sr.relation_type,
                  source.lemma_id as source_result_lemma_id,
                  sr.sense_id_from as source_result_sense_id,
                  'sense_relations' as source,
                  sr.confidence::double precision as score
                from public.sense_relations sr
                join public.senses source on source.id = sr.sense_id_from
                join public.senses target on target.id = sr.sense_id_to
                join public.lemmas l on l.id = target.lemma_id
                where sr.sense_id_from = any($2::bigint[])
                  and sr.sense_id_to is not null
                """,
                lemma_ids,
                sense_ids,
            )
        return [
            RelatedResult(
                lemma_id=int(row["lemma_id"]),
                lemma=row["lemma"],
                relation_type=row["relation_type"],
                source_result_lemma_id=int(row["source_result_lemma_id"]),
                source_result_sense_id=None if row["source_result_sense_id"] is None else int(row["source_result_sense_id"]),
                source=row["source"],
                score=float(row["score"] or 0.0),
            )
            for row in rows
        ]
```

- [ ] **Step 5: Run DB tests and verify they pass**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_db.py -v
```

Expected: PASS with `Ran 3 tests`.

- [ ] **Step 6: Checkpoint**

Run:

```bash
if test -d .git; then git add lexicon_search/db.py lexicon_search/repositories.py tests/test_search_db.py && git commit -m "feat: add search database repository"; else echo "not a git repository; checkpoint after Task 8"; fi
```

---

### Task 9: Alibaba Embedding Client

**Files:**
- Create: `lexicon_search/embeddings.py`
- Test: `tests/test_embeddings.py`

- [ ] **Step 1: Write embedding client tests**

Create `tests/test_embeddings.py`:

```python
import asyncio
import unittest

import httpx

from lexicon_search.embeddings import BailianEmbeddingClient


class EmbeddingClientTests(unittest.TestCase):
    def test_embed_texts_posts_openai_compatible_request(self):
        async def run_test():
            requests = []

            def handler(request: httpx.Request) -> httpx.Response:
                requests.append(request)
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {"index": 0, "embedding": [0.1] * 1024},
                            {"index": 1, "embedding": [0.2] * 1024},
                        ]
                    },
                )

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport, base_url="https://example.test") as http_client:
                client = BailianEmbeddingClient(
                    api_key="sk-test",
                    base_url="https://example.test",
                    model="text-embedding-v4",
                    dimension=1024,
                    http_client=http_client,
                )
                vectors = await client.embed_texts(["lopen", "lezen"])

            self.assertEqual(len(vectors), 2)
            self.assertEqual(len(vectors[0]), 1024)
            self.assertEqual(requests[0].url.path, "/embeddings")
            self.assertIn("Bearer sk-test", requests[0].headers["Authorization"])

        asyncio.run(run_test())

    def test_wrong_vector_dimension_raises(self):
        async def run_test():
            def handler(request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport, base_url="https://example.test") as http_client:
                client = BailianEmbeddingClient(
                    api_key="sk-test",
                    base_url="https://example.test",
                    model="text-embedding-v4",
                    dimension=1024,
                    http_client=http_client,
                )
                with self.assertRaisesRegex(ValueError, "1024"):
                    await client.embed_texts(["lopen"])

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run embedding tests and verify they fail**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_embeddings.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lexicon_search.embeddings'`.

- [ ] **Step 3: Implement embedding client**

Create `lexicon_search/embeddings.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx


class BailianEmbeddingClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        dimension: int,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimension = dimension
        self.http_client = http_client

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if len(texts) > 10:
            raise ValueError("text-embedding-v4 batch size must be 10 or fewer")

        payload: dict[str, Any] = {
            "model": self.model,
            "input": list(texts),
            "dimensions": self.dimension,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        if self.http_client is None:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
                response = await client.post("/embeddings", json=payload, headers=headers)
        else:
            response = await self.http_client.post("/embeddings", json=payload, headers=headers)

        response.raise_for_status()
        body = response.json()
        vectors_by_index = {
            int(item["index"]): [float(value) for value in item["embedding"]]
            for item in body.get("data", [])
        }

        vectors: list[list[float]] = []
        for index in range(len(texts)):
            vector = vectors_by_index[index]
            if len(vector) != self.dimension:
                raise ValueError(f"embedding response must have {self.dimension} dimensions")
            vectors.append(vector)
        return vectors

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]
```

- [ ] **Step 4: Run embedding tests and verify they pass**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_embeddings.py -v
```

Expected: PASS with `Ran 2 tests`.

- [ ] **Step 5: Checkpoint**

Run:

```bash
if test -d .git; then git add lexicon_search/embeddings.py tests/test_embeddings.py && git commit -m "feat: add Alibaba embedding client"; else echo "not a git repository; checkpoint after Task 9"; fi
```

---

### Task 10: Batch Index Builder

**Files:**
- Create: `lexicon_search/index_builder.py`
- Create: `scripts/rebuild_search_index.py`
- Test: `tests/test_index_builder.py`

- [ ] **Step 1: Write index builder tests**

Create `tests/test_index_builder.py`:

```python
import unittest

from lexicon_search.index_builder import SenseEmbeddingInput, build_embedding_text, hash_embedding_text


class IndexBuilderTests(unittest.TestCase):
    def test_build_embedding_text_uses_only_sense_text(self):
        row = SenseEmbeddingInput(
            sense_id=1,
            definition_nl="zich te voet voortbewegen",
            translation_zh="步行",
            translation_en="to walk",
        )

        text = build_embedding_text(row)

        self.assertIn("definition_nl: zich te voet voortbewegen", text)
        self.assertIn("translation_zh:", text)
        self.assertIn("translation_en: to walk", text)
        self.assertNotIn("lemma", text)

    def test_hash_embedding_text_is_stable(self):
        self.assertEqual(hash_embedding_text("abc"), hash_embedding_text("abc"))
        self.assertNotEqual(hash_embedding_text("abc"), hash_embedding_text("abcd"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run index builder tests and verify they fail**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_index_builder.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lexicon_search.index_builder'`.

- [ ] **Step 3: Implement index builder primitives**

Create `lexicon_search/index_builder.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from lexicon_search.db import vector_literal


@dataclass(frozen=True)
class SenseEmbeddingInput:
    sense_id: int
    definition_nl: str
    translation_zh: str
    translation_en: str


class EmbeddingRepository(Protocol):
    async def load_senses_for_embedding(self) -> list[SenseEmbeddingInput]:
        raise NotImplementedError

    async def upsert_sense_embeddings(
        self,
        rows: list[tuple[int, str, int, str, str, str, str]],
    ) -> None:
        raise NotImplementedError


class EmbeddingClient(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


def build_embedding_text(row: SenseEmbeddingInput) -> str:
    parts = []
    if row.definition_nl.strip():
        parts.append(f"definition_nl: {row.definition_nl.strip()}")
    if row.translation_zh.strip():
        parts.append(f"translation_zh: {row.translation_zh.strip()}")
    if row.translation_en.strip():
        parts.append(f"translation_en: {row.translation_en.strip()}")
    return "\n".join(parts)


def hash_embedding_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def rebuild_embeddings(
    *,
    repository: EmbeddingRepository,
    embedding_client: EmbeddingClient,
    embedding_model: str,
    embedding_dim: int,
    index_version: str,
    batch_size: int = 10,
) -> dict[str, int]:
    inputs = await repository.load_senses_for_embedding()
    embedded = 0
    skipped = 0

    for start in range(0, len(inputs), batch_size):
        batch = inputs[start : start + batch_size]
        texts = [build_embedding_text(row) for row in batch]
        usable = [(row, text) for row, text in zip(batch, texts, strict=True) if text.strip()]
        skipped += len(batch) - len(usable)
        if not usable:
            continue

        vectors = await embedding_client.embed_texts([text for _, text in usable])
        upsert_rows = []
        for (row, text), vector in zip(usable, vectors, strict=True):
            upsert_rows.append(
                (
                    row.sense_id,
                    embedding_model,
                    embedding_dim,
                    vector_literal(vector, embedding_dim),
                    hash_embedding_text(text),
                    text[:500],
                    index_version,
                )
            )
        await repository.upsert_sense_embeddings(upsert_rows)
        embedded += len(upsert_rows)

    return {"embedded": embedded, "skipped": skipped}
```

- [ ] **Step 4: Add repository methods for index building**

Append these methods inside `SearchRepository` in `lexicon_search/repositories.py`:

```python
    async def load_senses_for_embedding(self) -> list["SenseEmbeddingInput"]:
        from lexicon_search.index_builder import SenseEmbeddingInput

        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                select
                  s.id as sense_id,
                  coalesce(s.display_definition_nl, s.definition_nl, '') as definition_nl,
                  coalesce(max(st_zh.gloss) filter (where st_zh.lang = 'zh'), '') as translation_zh,
                  coalesce(max(st_en.gloss) filter (where st_en.lang = 'en'), '') as translation_en
                from public.senses s
                left join public.sense_translations st_zh
                  on st_zh.sense_id = s.id and st_zh.lang = 'zh'
                left join public.sense_translations st_en
                  on st_en.sense_id = s.id and st_en.lang = 'en'
                where s.merged_into_sense_id is null
                group by s.id, s.display_definition_nl, s.definition_nl
                order by s.id
                """
            )
        return [
            SenseEmbeddingInput(
                sense_id=int(row["sense_id"]),
                definition_nl=row["definition_nl"] or "",
                translation_zh=row["translation_zh"] or "",
                translation_en=row["translation_en"] or "",
            )
            for row in rows
        ]

    async def upsert_sense_embeddings(self, rows: list[tuple[int, str, int, str, str, str, str]]) -> None:
        if not rows:
            return
        async with self.database.acquire() as connection:
            await connection.executemany(
                """
                insert into public.sense_embeddings (
                  sense_id, embedding_model, embedding_dim, embedding,
                  embedding_text_hash, embedding_text_preview, index_version
                )
                values ($1, $2, $3, $4::extensions.vector(1024), $5, $6, $7)
                on conflict (sense_id, embedding_model, embedding_dim) do update set
                  embedding = excluded.embedding,
                  embedding_text_hash = excluded.embedding_text_hash,
                  embedding_text_preview = excluded.embedding_text_preview,
                  index_version = excluded.index_version,
                  updated_at = now()
                """,
                rows,
            )
```

- [ ] **Step 5: Create rebuild CLI**

Create `scripts/rebuild_search_index.py`:

```python
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
```

- [ ] **Step 6: Run index builder tests and verify they pass**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_index_builder.py -v
```

Expected: PASS with `Ran 2 tests`.

- [ ] **Step 7: Checkpoint**

Run:

```bash
if test -d .git; then git add lexicon_search/index_builder.py lexicon_search/repositories.py scripts/rebuild_search_index.py tests/test_index_builder.py && git commit -m "feat: add search embedding rebuild pipeline"; else echo "not a git repository; checkpoint after Task 10"; fi
```

---

### Task 11: Semantic Search Engine

**Files:**
- Create: `lexicon_search/semantic.py`
- Test: `tests/test_semantic_search.py`

- [ ] **Step 1: Write semantic search tests**

Create `tests/test_semantic_search.py`:

```python
import asyncio
import unittest

from lexicon_search.models import SemanticCandidate
from lexicon_search.semantic import SemanticSearchEngine, candidate_count_for_limit


class FakeEmbedder:
    async def embed_text(self, text):
        return [0.1] * 1024


class FakeRepository:
    async def match_senses(self, embedding, candidate_count, index_version):
        return [
            SemanticCandidate(10, 1, "lopen", 1, "def1", "zh1", "en1", 0.82, 1200),
            SemanticCandidate(11, 1, "lopen", 1, "def2", "zh2", "en2", 0.75, 1200),
            SemanticCandidate(20, 2, "wandelen", 2, "def3", "zh3", "en3", 0.80, 800),
        ]


class SemanticSearchTests(unittest.TestCase):
    def test_candidate_count_for_limit(self):
        self.assertEqual(candidate_count_for_limit(10), 50)
        self.assertEqual(candidate_count_for_limit(50), 250)

    def test_search_aggregates_senses_to_lemmas(self):
        async def run_test():
            engine = SemanticSearchEngine(FakeEmbedder(), FakeRepository(), index_version="search-test")
            result = await engine.search("walk", limit=10)
            self.assertEqual([item["lemma"] for item in result["results"]], ["lopen", "wandelen"])
            self.assertEqual(result["results"][0]["matched_sense"]["sense_id"], 10)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run semantic tests and verify they fail**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_semantic_search.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lexicon_search.semantic'`.

- [ ] **Step 3: Implement semantic search engine**

Create `lexicon_search/semantic.py`:

```python
from __future__ import annotations

from typing import Protocol

from lexicon_search.models import SemanticCandidate
from lexicon_search.scoring import semantic_score


class QueryEmbedder(Protocol):
    async def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError


class SemanticRepository(Protocol):
    async def match_senses(self, embedding: list[float], candidate_count: int, index_version: str) -> list[SemanticCandidate]:
        raise NotImplementedError


def candidate_count_for_limit(limit: int) -> int:
    return min(max(limit * 5, 50), 250)


class SemanticSearchEngine:
    def __init__(self, embedder: QueryEmbedder, repository: SemanticRepository, index_version: str) -> None:
        self.embedder = embedder
        self.repository = repository
        self.index_version = index_version

    async def search(self, query: str, limit: int) -> dict:
        embedding = await self.embedder.embed_text(query)
        candidates = await self.repository.match_senses(
            embedding=embedding,
            candidate_count=candidate_count_for_limit(limit),
            index_version=self.index_version,
        )
        by_lemma: dict[int, tuple[SemanticCandidate, float, dict[str, float]]] = {}
        for candidate in candidates:
            breakdown = semantic_score(
                vector_similarity=candidate.vector_similarity,
                frequency=candidate.frequency,
                level=candidate.level,
            )
            existing = by_lemma.get(candidate.lemma_id)
            if existing is None or breakdown.score > existing[1]:
                by_lemma[candidate.lemma_id] = (candidate, breakdown.score, breakdown.reasons)

        ordered = sorted(by_lemma.values(), key=lambda item: (-item[1], item[0].lemma))[:limit]
        return {
            "results": [
                {
                    "lemma_id": candidate.lemma_id,
                    "lemma": candidate.lemma,
                    "level": candidate.level,
                    "score": round(score, 6),
                    "matched_sense": {
                        "sense_id": candidate.sense_id,
                        "definition_nl": candidate.definition_nl,
                        "translation_zh": candidate.translation_zh,
                        "translation_en": candidate.translation_en,
                        "semantic_score": round(candidate.vector_similarity, 6),
                    },
                    "matched_reason": {key: round(value, 6) for key, value in reasons.items()},
                }
                for candidate, score, reasons in ordered
            ],
            "candidate_count": candidate_count_for_limit(limit),
        }
```

- [ ] **Step 4: Run semantic tests and verify they pass**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_semantic_search.py -v
```

Expected: PASS with `Ran 2 tests`.

- [ ] **Step 5: Checkpoint**

Run:

```bash
if test -d .git; then git add lexicon_search/semantic.py tests/test_semantic_search.py && git commit -m "feat: add semantic search engine"; else echo "not a git repository; checkpoint after Task 11"; fi
```

---

### Task 12: Graph Expansion

**Files:**
- Create: `lexicon_search/graph.py`
- Test: `tests/test_graph_expansion.py`

- [ ] **Step 1: Write graph expansion tests**

Create `tests/test_graph_expansion.py`:

```python
import unittest

from lexicon_search.graph import rank_related_results
from lexicon_search.models import RelatedResult


class GraphExpansionTests(unittest.TestCase):
    def test_rank_related_results_filters_primary_lemmas_and_dedupes(self):
        related = [
            RelatedResult(lemma_id=2, lemma="wandelen", relation_type="synonym", source_result_lemma_id=1, source_result_sense_id=None, source="lemma_relations", score=0.8),
            RelatedResult(lemma_id=1, lemma="lopen", relation_type="family", source_result_lemma_id=1, source_result_sense_id=None, source="lemma_relations", score=1.0),
            RelatedResult(lemma_id=2, lemma="wandelen", relation_type="related", source_result_lemma_id=1, source_result_sense_id=None, source="sense_relations", score=0.5),
        ]

        ranked = rank_related_results(related, primary_lemma_ids=[1], limit=5)

        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].lemma, "wandelen")
        self.assertEqual(ranked[0].relation_type, "synonym")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run graph tests and verify they fail**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_graph_expansion.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lexicon_search.graph'`.

- [ ] **Step 3: Implement graph ranking**

Create `lexicon_search/graph.py`:

```python
from __future__ import annotations

from lexicon_search.models import RelatedResult


RELATION_PRIORITY = {
    "synonym": 1.0,
    "antonym": 0.9,
    "family": 0.8,
    "word_family": 0.8,
    "related": 0.6,
}


def rank_related_results(
    related: list[RelatedResult],
    *,
    primary_lemma_ids: list[int],
    limit: int,
) -> list[RelatedResult]:
    primary = set(primary_lemma_ids)
    best: dict[int, RelatedResult] = {}
    for item in related:
        if item.lemma_id in primary:
            continue
        existing = best.get(item.lemma_id)
        if existing is None or _sort_score(item) > _sort_score(existing):
            best[item.lemma_id] = item
    return sorted(best.values(), key=lambda item: (-_sort_score(item), item.lemma))[:limit]


def _sort_score(item: RelatedResult) -> float:
    relation_weight = RELATION_PRIORITY.get(item.relation_type, 0.5)
    return relation_weight + item.score * 0.2
```

- [ ] **Step 4: Run graph tests and verify they pass**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_graph_expansion.py -v
```

Expected: PASS with `Ran 1 test`.

- [ ] **Step 5: Checkpoint**

Run:

```bash
if test -d .git; then git add lexicon_search/graph.py tests/test_graph_expansion.py && git commit -m "feat: add graph result expansion"; else echo "not a git repository; checkpoint after Task 12"; fi
```

---

### Task 13: High-Level Search Service

**Files:**
- Create: `lexicon_search/service.py`
- Test: `tests/test_search_service.py`

- [ ] **Step 1: Write service tests**

Create `tests/test_search_service.py`:

```python
import asyncio
import unittest

from lexicon_search.dictionary import DictionaryIndex
from lexicon_search.models import FormSummary, LemmaSummary
from lexicon_search.service import SearchService


class FakeSemanticEngine:
    async def search(self, query, limit):
        return {
            "results": [
                {
                    "lemma_id": 1,
                    "lemma": "lopen",
                    "level": 1,
                    "score": 0.9,
                    "matched_sense": {"sense_id": 10},
                    "matched_reason": {"semantic_score": 0.9},
                }
            ],
            "candidate_count": 50,
        }


class FakeRepository:
    async def fuzzy_lookup(self, query_norm, limit):
        return []

    async def fuzzy_suggest(self, query_norm, limit):
        return []

    async def load_related_results(self, lemma_ids, sense_ids):
        return []

    async def write_query_log(self, record, request_metadata):
        self.last_log = record


class SearchServiceTests(unittest.TestCase):
    def test_lookup_returns_best_match(self):
        async def run_test():
            lemma = LemmaSummary(1, "lopen", "lopen", 1, 1200)
            dictionary = DictionaryIndex.from_rows(
                [lemma],
                [FormSummary(10, "gelopen", "gelopen", lemma, False, 300)],
            )
            service = SearchService(dictionary, FakeSemanticEngine(), FakeRepository(), log_queries=True, embedding_model="text-embedding-v4", index_version="search-test")
            result = await service.lookup("gelopen", limit=5)
            self.assertEqual(result["best_match"]["lemma"], "lopen")
            self.assertEqual(result["did_you_mean"], [])

        asyncio.run(run_test())

    def test_semantic_search_returns_related_results_key(self):
        async def run_test():
            dictionary = DictionaryIndex.from_rows([], [])
            service = SearchService(dictionary, FakeSemanticEngine(), FakeRepository(), log_queries=True, embedding_model="text-embedding-v4", index_version="search-test")
            result = await service.semantic_search("walk", limit=10, include_related=True)
            self.assertEqual(result["results"][0]["lemma"], "lopen")
            self.assertEqual(result["related_results"], [])

        asyncio.run(run_test())

    def test_lookup_uses_fuzzy_fallback_when_dictionary_misses(self):
        async def run_test():
            lemma = LemmaSummary(2, "wandelen", "wandelen", 2, 800)

            class FuzzyRepository(FakeRepository):
                async def fuzzy_lookup(self, query_norm, limit):
                    from lexicon_search.models import LookupCandidate

                    return [LookupCandidate(lemma, None, None, "lemma_fuzzy", 0.7, 0.7)]

            dictionary = DictionaryIndex.from_rows([], [])
            service = SearchService(dictionary, FakeSemanticEngine(), FuzzyRepository(), log_queries=True, embedding_model="text-embedding-v4", index_version="search-test")
            result = await service.lookup("wandele", limit=5)
            self.assertIsNone(result["best_match"])
            self.assertEqual(result["did_you_mean"][0]["lemma"], "wandelen")

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run service tests and verify they fail**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_service.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lexicon_search.service'`.

- [ ] **Step 3: Implement high-level service**

Create `lexicon_search/service.py`:

```python
from __future__ import annotations

import time
from typing import Any

from lexicon_search.dictionary import DictionaryIndex
from lexicon_search.graph import rank_related_results
from lexicon_search.models import SearchLogRecord
from lexicon_search.normalization import normalize_query


class SearchService:
    def __init__(
        self,
        dictionary: DictionaryIndex,
        semantic_engine: Any,
        repository: Any,
        *,
        log_queries: bool,
        embedding_model: str,
        index_version: str,
    ) -> None:
        self.dictionary = dictionary
        self.semantic_engine = semantic_engine
        self.repository = repository
        self.log_queries = log_queries
        self.embedding_model = embedding_model
        self.index_version = index_version

    async def lookup(self, query: str, limit: int = 5) -> dict[str, Any]:
        start = time.perf_counter()
        candidates = self.dictionary.lookup(query, limit=limit)
        if not candidates:
            candidates = await self.repository.fuzzy_lookup(normalize_query(query), limit)
        best_match = candidates[0].to_public_dict() if candidates and candidates[0].confidence >= 0.85 else None
        did_you_mean = [] if best_match is not None else [candidate.to_public_dict() for candidate in candidates]
        result = {
            "query": query,
            "mode": "lookup",
            "best_match": best_match,
            "did_you_mean": did_you_mean,
        }
        await self._log(
            query=query,
            mode="lookup",
            started_at=start,
            candidate_count=len(candidates),
            result_count=1 if best_match else len(did_you_mean),
            top_lemma_ids=[candidates[0].lemma.lemma_id] if candidates else [],
            top_sense_ids=[],
        )
        return result

    async def suggest(self, query: str, limit: int = 10) -> dict[str, Any]:
        start = time.perf_counter()
        candidates = self.dictionary.suggest(query, limit=limit)
        if len(candidates) < limit:
            seen = {candidate.lemma.lemma_id for candidate in candidates}
            for candidate in await self.repository.fuzzy_suggest(normalize_query(query), limit):
                if candidate.lemma.lemma_id not in seen:
                    candidates.append(candidate)
                    seen.add(candidate.lemma.lemma_id)
                if len(candidates) >= limit:
                    break
        result = {
            "query": query,
            "mode": "suggest",
            "suggestions": [candidate.to_public_dict() for candidate in candidates],
        }
        await self._log(
            query=query,
            mode="suggest",
            started_at=start,
            candidate_count=len(candidates),
            result_count=len(candidates),
            top_lemma_ids=[candidate.lemma.lemma_id for candidate in candidates],
            top_sense_ids=[],
        )
        return result

    async def semantic_search(self, query: str, limit: int, include_related: bool) -> dict[str, Any]:
        start = time.perf_counter()
        semantic_result = await self.semantic_engine.search(query, limit=limit)
        results = semantic_result["results"]
        top_lemma_ids = [int(item["lemma_id"]) for item in results]
        top_sense_ids = [int(item["matched_sense"]["sense_id"]) for item in results if item.get("matched_sense")]
        related_results = []
        if include_related:
            related = await self.repository.load_related_results(top_lemma_ids, top_sense_ids)
            related_results = [
                {
                    "lemma_id": item.lemma_id,
                    "lemma": item.lemma,
                    "relation_type": item.relation_type,
                    "source_result_lemma_id": item.source_result_lemma_id,
                    "source_result_sense_id": item.source_result_sense_id,
                    "source": item.source,
                    "score": round(item.score, 6),
                }
                for item in rank_related_results(related, primary_lemma_ids=top_lemma_ids, limit=limit)
            ]
        result = {
            "query": query,
            "language": "unknown",
            "results": results,
            "related_results": related_results,
        }
        await self._log(
            query=query,
            mode="semantic",
            started_at=start,
            candidate_count=semantic_result["candidate_count"],
            result_count=len(results),
            top_lemma_ids=top_lemma_ids,
            top_sense_ids=top_sense_ids,
        )
        return result

    async def _log(
        self,
        *,
        query: str,
        mode: str,
        started_at: float,
        candidate_count: int,
        result_count: int,
        top_lemma_ids: list[int],
        top_sense_ids: list[int],
    ) -> None:
        if not self.log_queries:
            return
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        record = SearchLogRecord(
            query=query,
            mode=mode,
            detected_language=None,
            latency_ms=latency_ms,
            candidate_count=candidate_count,
            result_count=result_count,
            top_lemma_ids=top_lemma_ids,
            top_sense_ids=top_sense_ids,
            cache_hit=False,
            embedding_model=self.embedding_model if mode == "semantic" else None,
            index_version=self.index_version,
        )
        await self.repository.write_query_log(record, request_metadata={})
```

- [ ] **Step 4: Run service tests and verify they pass**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_service.py -v
```

Expected: PASS with `Ran 3 tests`.

- [ ] **Step 5: Checkpoint**

Run:

```bash
if test -d .git; then git add lexicon_search/service.py tests/test_search_service.py && git commit -m "feat: add high-level search service"; else echo "not a git repository; checkpoint after Task 13"; fi
```

---

### Task 14: FastAPI Routes And Service Startup

**Files:**
- Create: `lexicon_search/api.py`
- Create: `scripts/run_search_service.py`
- Test: `tests/test_search_api.py`

**Route surface:**
- `GET /health`
- `GET /lookup`
- `GET /suggest`
- `POST /semantic-search`

- [ ] **Step 1: Write API tests**

Create `tests/test_search_api.py`:

```python
import unittest

from fastapi.testclient import TestClient

from lexicon_search.api import create_app


class FakeService:
    async def lookup(self, query, limit):
        return {"query": query, "mode": "lookup", "best_match": None, "did_you_mean": []}

    async def suggest(self, query, limit):
        return {"query": query, "mode": "suggest", "suggestions": []}

    async def semantic_search(self, query, limit, include_related):
        return {"query": query, "language": "unknown", "results": [], "related_results": []}


class SearchApiTests(unittest.TestCase):
    def test_health(self):
        client = TestClient(create_app(FakeService()))
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_lookup_endpoint(self):
        client = TestClient(create_app(FakeService()))
        response = client.get("/lookup", params={"q": "gelopen"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "lookup")

    def test_semantic_limit_is_capped(self):
        client = TestClient(create_app(FakeService()))
        response = client.post("/semantic-search", json={"query": "walk", "limit": 500})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_api.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lexicon_search.api'`.

- [ ] **Step 3: Implement FastAPI app**

Create `lexicon_search/api.py`:

```python
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
```

- [ ] **Step 4: Create service launcher**

Create `scripts/run_search_service.py`:

```python
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
    config = load_config()
    service, database = asyncio.run(build_service())
    app = create_app(service)
    try:
        uvicorn.run(app, host="0.0.0.0", port=8080, workers=1)
    finally:
        asyncio.run(database.close())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run API tests and verify they pass**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_api.py -v
```

Expected: PASS with `Ran 3 tests`.

- [ ] **Step 6: Checkpoint**

Run:

```bash
if test -d .git; then git add lexicon_search/api.py scripts/run_search_service.py tests/test_search_api.py && git commit -m "feat: add search API routes"; else echo "not a git repository; checkpoint after Task 14"; fi
```

---

### Task 15: Benchmark Metrics And Operations Docs

**Files:**
- Create: `scripts/run_search_benchmarks.py`
- Create: `tests/test_search_benchmarks.py`
- Create: `deploy/search-engine.env.example`
- Create: `deploy/search-engine.service`
- Create: `docs/search-engine-operations.md`

- [ ] **Step 1: Write benchmark metric tests**

Create `tests/test_search_benchmarks.py`:

```python
import unittest

from scripts.run_search_benchmarks import reciprocal_rank, recall_at_k


class SearchBenchmarkTests(unittest.TestCase):
    def test_recall_at_k(self):
        self.assertEqual(recall_at_k([1, 2, 3], [2, 4], 3), 0.5)
        self.assertEqual(recall_at_k([1, 2, 3], [4, 5], 3), 0.0)

    def test_reciprocal_rank(self):
        self.assertEqual(reciprocal_rank([3, 2, 1], [2]), 0.5)
        self.assertEqual(reciprocal_rank([3, 2, 1], [5]), 0.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run benchmark tests and verify they fail**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_benchmarks.py -v
```

Expected: FAIL with `ModuleNotFoundError` or import failure for `scripts.run_search_benchmarks`.

- [ ] **Step 3: Implement benchmark script primitives**

Create `scripts/run_search_benchmarks.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def recall_at_k(predicted_ids: list[int], expected_ids: list[int], k: int) -> float:
    expected = set(expected_ids)
    if not expected:
        return 0.0
    predicted = set(predicted_ids[:k])
    return len(predicted & expected) / len(expected)


def reciprocal_rank(predicted_ids: list[int], expected_ids: list[int]) -> float:
    expected = set(expected_ids)
    for index, predicted_id in enumerate(predicted_ids, start=1):
        if predicted_id in expected:
            return 1.0 / index
    return 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="outputs/search_benchmark_metrics.json")
    args = parser.parse_args()

    metrics = {
        "recall_at_10": 0.0,
        "mrr": 0.0,
        "query_count": 0,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create environment template**

Create `deploy/search-engine.env.example`:

```text
DATABASE_URL=postgresql://search_service_user:change-me@db.example.supabase.co:5432/postgres
BAILIAN_API_KEY=replace-with-server-side-key
BAILIAN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
SEARCH_EMBEDDING_MODEL=text-embedding-v4
SEARCH_EMBEDDING_DIM=1024
SEARCH_INDEX_VERSION=search-v1
SEARCH_MAX_LIMIT=50
SEARCH_LOG_QUERIES=true
```

- [ ] **Step 5: Create 4c8g systemd service template**

Create `deploy/search-engine.service`:

```ini
[Unit]
Description=Dutch Lexicon Search Engine
After=network.target

[Service]
Type=simple
WorkingDirectory=/srv/dutch-corpus
EnvironmentFile=/srv/dutch-corpus/deploy/search-engine.env
ExecStart=/srv/dutch-corpus/.venv/bin/python scripts/run_search_service.py
Restart=always
RestartSec=5
User=search
Group=search
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 6: Create operations runbook**

Create `docs/search-engine-operations.md`:

```markdown
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
```

- [ ] **Step 7: Run benchmark tests and verify they pass**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_benchmarks.py -v
```

Expected: PASS with `Ran 2 tests`.

- [ ] **Step 8: Run the full search-related test suite**

Run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_search_config.py tests/test_search_normalization.py tests/test_search_models.py tests/test_search_scoring.py tests/test_dictionary_index.py tests/test_search_db.py tests/test_embeddings.py tests/test_index_builder.py tests/test_semantic_search.py tests/test_graph_expansion.py tests/test_search_service.py tests/test_search_api.py tests/test_search_benchmarks.py -v
```

Expected: PASS with all listed tests passing.

- [ ] **Step 9: Checkpoint**

Run:

```bash
if test -d .git; then git add scripts/run_search_benchmarks.py tests/test_search_benchmarks.py deploy/search-engine.env.example deploy/search-engine.service docs/search-engine-operations.md && git commit -m "docs: add search engine operations plan"; else echo "not a git repository; checkpoint after Task 15"; fi
```

---

## Final Verification

After all tasks are complete, run:

```bash
/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover tests -v
```

Expected: all existing tests and all new search tests pass.

Then install service dependencies in the intended runtime:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-search.txt
```

Then verify import startup:

```bash
. .venv/bin/activate
python -c "from lexicon_search.config import load_config; print('search imports ok')"
```

Expected:

```text
search imports ok
```

Then apply the Supabase migration through the validated deployment path and run:

```bash
SEARCH_INDEX_VERSION=search-v1 python scripts/rebuild_search_index.py --batch-size 10
```

Expected:

```text
{'embedded': 35885, 'skipped': 0}
```

The exact embedded count may differ if the Supabase source data has changed since the local export; differences must be recorded in the benchmark notes with the current count from `select count(*) from public.senses where merged_into_sense_id is null`.

Finally start the service on the 4c8g host:

```bash
. .venv/bin/activate
python scripts/run_search_service.py
```

Expected:

```text
Uvicorn running on http://0.0.0.0:8080
```

Run smoke checks:

```bash
curl http://127.0.0.1:8080/health
curl "http://127.0.0.1:8080/lookup?q=gelopen"
curl "http://127.0.0.1:8080/suggest?q=ge"
curl -X POST http://127.0.0.1:8080/semantic-search -H 'Content-Type: application/json' -d '{"query":"walk","limit":10,"include_related":true}'
```

Expected:

```text
/health returns {"status":"ok"}
/lookup returns mode lookup
/suggest returns mode suggest
/semantic-search returns results and related_results arrays
```
