#!/usr/bin/env bash
# Same-origin real backend + frontend: bash frontend/serve.sh --port 8801 [--semantic]
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/scripts/run_local_preview.py" "$@"
