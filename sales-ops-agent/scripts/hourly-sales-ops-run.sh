#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/.openclaw/workspace/ai-sales-team/sales-ops-agent"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

cd "$ROOT"
python3 -m app.sales_ops_worker >> "$LOG_DIR/sales-ops-worker.log" 2>&1
