#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
RUN_NAME="${1:-annotated_full_live_w8_b4000}"
RUN_DIR="$ROOT/outputs/annotated_batches/$RUN_NAME"
LOG_DIR="$RUN_DIR/logs"
LOG_PATH="$LOG_DIR/run_$(date -u +%Y%m%dT%H%M%SZ).log"
ERR_LOG_PATH="${LOG_PATH%.log}.err.log"
PID_PATH="$RUN_DIR/run.pid"
SCREEN_NAME="dutch_full_${RUN_NAME//[^A-Za-z0-9_]/_}"

mkdir -p "$LOG_DIR"

if [[ -f "$PID_PATH" ]]; then
  OLD_PID="$(cat "$PID_PATH")"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Run already appears active: pid=$OLD_PID"
    echo "PID: $PID_PATH"
    echo "Log: $(ls -t "$LOG_DIR"/run_*.log 2>/dev/null | head -n 1)"
    exit 0
  fi
fi

if screen -ls | awk '{ print $1 }' | grep -q "\\.${SCREEN_NAME}$"; then
  echo "screen session already appears active: $SCREEN_NAME"
  echo "Log: $(ls -t "$LOG_DIR"/run_*.log 2>/dev/null | head -n 1)"
  exit 0
fi

screen -dmS "$SCREEN_NAME" /bin/zsh -lc \
  "exec '$ROOT/scripts/run_full_live_worker.sh' '$RUN_NAME' >> '$LOG_PATH' 2>> '$ERR_LOG_PATH'"
sleep 1
PID="$(pgrep -f "run_annotated_batches.py .*--run-name $RUN_NAME" | head -n 1 || true)"
if [[ -n "$PID" ]]; then
  echo "$PID" > "$PID_PATH"
fi

echo "Started full live run"
echo "Run name: $RUN_NAME"
echo "screen session: $SCREEN_NAME"
echo "PID: ${PID:-unknown}"
echo "PID path: $PID_PATH"
echo "Log: $LOG_PATH"
echo "Error log: $ERR_LOG_PATH"
