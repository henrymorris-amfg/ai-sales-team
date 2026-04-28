# Sales Ops Agent Prototype

This is a starter prototype for a Pipedrive Sales Ops agent.

## What it does today
- Loads config from environment or local `.env`
- Reads a Pipedrive API key from environment or `.secrets/pipedrive.env`
- Fetches live Pipedrive metadata in read-only mode
- Filters the first hygiene run to the `Machining` pipeline
- Treats `Demo Done` as a completed `Demo` activity in the current audit window
- Normalizes records
- Runs starter hygiene rules
- Stores findings in SQLite
- Produces findings as JSON and a markdown report

## What it does not do yet
- Full incremental sync
- Manager digests
- Writebacks to Pipedrive
- Website disqualification at production scale

## Suggested first run
1. Add your real Pipedrive company domain to `.env` or environment variables.
2. Keep the API key in `.secrets/pipedrive.env`.
3. Run the discovery command to fetch pipelines, stages, users, activity types, and fields.
4. Run the audit command to generate the first markdown hygiene report and SQLite audit log.
5. Review outputs before turning on additional checks.

## Files
- `app/config.py` configuration loader
- `app/pipedrive_client.py` minimal API client
- `app/models.py` basic dataclasses
- `app/normalize.py` normalization helpers
- `app/rules.py` starter rule engine
- `app/discovery.py` field and stage discovery script
- `app/db.py` SQLite audit storage
- `app/reporting.py` markdown report builder
- `app/google_chat_digest.py` Google Chat digest formatter
- `app/owner_mapping.py` Pipedrive owner mapping export
- `app/lead_review.py` first-100 lead recommend-only review worker
- `app/main.py` starter audit runner

## Dashboard
- Generate the first branded static dashboard with `python3 -m app.dashboard`
- Open `output/dashboard.html` in a browser
- Run the live local dashboard with `./run.sh dashboard`
- Default local URL is `http://localhost:8787`
- The live dashboard reads from the generated JSON outputs in `output/`
- CSV upload is supported in the live dashboard and stores files in `uploads/`
- Uploaded CSVs can be turned into an AI BDR intake queue from the dashboard, or with `python3 -m app.intake_queue`
- Queue output is written to `output/bdr-intake-queue.json`
- Run a random 200-lead CNC review batch with `./run.sh batch-review`
- Batch review outputs are written to `output/cnc-random-review-200.json` and `output/cnc-random-review-200.md`
- Current design direction uses AMFG website cues: Inter, AMFG blue, charcoal, light neutral cards

## Recommended next improvements
- Add SQLite storage for snapshots and findings
- Add website review worker
- Add daily digest generator
- Add config file for stage IDs and custom field IDs
- Upgrade the dashboard from static HTML to a live web app with API-backed actions
