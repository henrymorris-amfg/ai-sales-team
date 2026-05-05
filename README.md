# AI Sales Team

AMFG-focused AI Sales Team workspace, centered on two things:

1. **Sales Ops automation** for Pipedrive hygiene and CNC lead disqualification
2. **A shared control dashboard** for Sales Ops plus regional AI BDR agents

## Current structure

- `sales-ops-agent/` - Python prototype for CRM hygiene, lead review, queue building, and the live dashboard
- `docs/` - project docs, operating rules, architecture, research, and rollout notes

## What is already working

- Pipedrive hygiene audit scaffolding
- CNC-focused lead review and batch review outputs
- Google Chat digest formatting
- CSV upload intake for AI BDR workflows
- Territory-aware intake queue routing
- Live local dashboard for team status, findings, queue health, and uploads
- Apollo enrichment preview scaffold for queued AI BDR leads

## Immediate roadmap

1. Put the Sales Ops loop on a reliable daily run
2. Increase CNC review throughput toward 200 leads/day
3. Turn the dashboard into the shared operating console for all four agents
4. Complete enrichment, dedupe, owner assignment, and handoff flow
5. Add deployable environments and authenticated web access

## Quick start

```bash
cd sales-ops-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./run.sh dashboard
```

Dashboard default URL: `http://localhost:8787`

## Notes

- Keep credentials out of git. Use local env files or `.secrets/`.
- Apollo credentials should live in `.secrets/apollo.env` as `APOLLO_API_KEY=...`.
- Run `./run.sh apollo-preview` from `sales-ops-agent/` to generate `output/apollo-enrichment-preview.json` for the next batch of queued leads.
- The current repo snapshot is the baseline import from the local working prototype.
