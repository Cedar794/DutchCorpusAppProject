#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
RUN_NAME="${1:-annotated_full_live_w8_b4000}"

cd "$ROOT"
export PYTHONUNBUFFERED=1

exec "$PYTHON" "$ROOT/scripts/run_annotated_batches.py" \
  --batch-lines 4000 \
  --workers 8 \
  --run-name "$RUN_NAME" \
  --backend native \
  --native-prefix local/frog-llvm-omp \
  --frog-threads 1 \
  --live-merge \
  --resume \
  --manifest-write-interval-seconds 300
