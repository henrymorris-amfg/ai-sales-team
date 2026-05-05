#!/usr/bin/env bash
set -euo pipefail
cd /root/.openclaw/workspace/ai-sales-team/sales-ops-agent
mkdir -p logs
{
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] starting hourly AI BDR batch"
  python3 -m app.bdr_batch_create
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] finished hourly AI BDR batch"
} >> logs/hourly-bdr-run.log 2>&1
