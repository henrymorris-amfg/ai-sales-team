#!/usr/bin/env bash
set -euo pipefail

case "${1:-audit}" in
  audit)
    python3 -m app.main
    ;;
  dashboard)
    python3 -m app.web_server
    ;;
  generate-dashboard)
    python3 -m app.dashboard
    ;;
  batch-review)
    python3 -m app.cnc_batch_review
    ;;
  process-uploads)
    python3 -m app.intake_queue
    ;;
  apollo-preview)
    python3 -m app.apollo_enrich_queue
    ;;
  *)
    echo "Usage: ./run.sh [audit|dashboard|generate-dashboard|batch-review|process-uploads|apollo-preview]" >&2
    exit 1
    ;;
esac
