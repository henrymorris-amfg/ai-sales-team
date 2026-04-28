# Multi-Agent Revenue Ops Architecture

## Goal
Run four specialized agents with one shared control surface:
- Sales Ops agent
- AI BDR for USA & Canada
- AI BDR for UK & Ireland
- AI BDR for EU

## Recommended model
### 1. One orchestration layer
Use one shared orchestration service that owns:
- Pipedrive access
- Google Chat delivery
- audit logs
- lead queues
- scoring rules
- dashboard state

### 2. Four specialist agents
#### Sales Ops agent
Owns:
- CRM hygiene
- duplicate detection
- stage compliance
- next activity enforcement
- demo/value checks
- lead disqualification recommendations

#### AI BDR USA & Canada
Owns:
- CNC leads in USA & Canada
- follow-up drafting
- region-specific qualification and routing
- local market nuance and timezone-aware outreach suggestions

#### AI BDR UK & Ireland
Owns:
- CNC leads in UK & Ireland
- same operating model, region-tailored

#### AI BDR EU
Owns:
- CNC leads in EU
- same operating model, region-tailored

## Shared dashboard requirements
The dashboard should show all four agents together in one place.

### Top-level widgets
- agent health/status
- leads processed today
- recommendations made
- archives recommended
- archives auto-completed
- hygiene violations found
- unresolved owner nudges
- false positive rate

### Per-agent panels
For each agent show:
- scope
- queue size
- throughput today
- last run time
- current blockers
- recent actions
- confidence distribution
- top accounts/leads being handled

### Shared control actions
- pause/resume each agent
- adjust region scope
- adjust scoring thresholds
- toggle recommend-only vs auto mode
- broadcast instruction to all agents
- send instruction to one agent
- compare outputs across agents

## Best communication pattern
### Recommended
- One shared dashboard for monitoring
- One shared manager chat room for summaries
- One direct chat target per agent for instructions
- One shared memory and audit store

### Simultaneous communication
Use a control layer that fans out the same instruction to all agents at once.
Examples:
- "tighten disqualification threshold"
- "pause auto-archive"
- "focus on aerospace and defense this week"

## Data partitioning
### Shared
- product positioning
- qualification policy
- disqualification model
- audit schema
- templates

### Agent-specific
- region filter
- timezone
- regional account ownership
- language/tone variants if needed

## Dashboard implementation recommendation
### Phase 1
Build a simple shared dashboard backed by generated JSON files:
- agent-status.json
- lead-review-queue-first-100.json
- owner-summary.json
- findings.json
- run-history.json

### Phase 2
Add SQLite-backed dashboard views and simple charts.

### Phase 3
Add direct controls for each agent and bulk instruction fan-out.

## How to track all four agents cleanly
Represent each agent as:
- agent_id
- name
- scope
- status
- queue_count
- processed_today
- errors_today
- last_action_at
- delivery_target

## Recommended next build step
Create a shared `agent-status.json` plus a dashboard document that can be rendered in the Control UI.
