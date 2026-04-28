# Deployment Handoff

## What exists now

This project now has:
- Python audit and lead-review workers
- A live local dashboard
- CSV upload intake
- AI BDR intake queue generation

Local dashboard entrypoint:
- `./run.sh dashboard`

Default local URL:
- `http://localhost:8787`

## Recommended deployment shape

### Best short-term option
Use:
- GitHub for source control
- Vercel for the frontend or future React UI
- Render or Railway for the Python app/API

Why:
- the current dashboard is Python-backed
- Vercel is excellent for frontend hosting, preview deployments, and polished UI iteration
- Render or Railway is simpler for a small Python web service with file uploads

### If you insist on Vercel-only
That is possible, but I would first refactor the current Python server into a framework shape better suited for serverless deployment.
The cleanest version would be:
- React/Next.js frontend on Vercel
- API routes or a separate Python service for background work and uploads

## Environment and secrets

Keep these out of GitHub and in deployment secrets:
- `PIPEDRIVE_API_KEY`
- `BRAVE_SEARCH_API_KEY`

Environment variables currently expected:
- `PIPEDRIVE_COMPANY_DOMAIN`
- `PIPEDRIVE_API_BASE`
- `PIPEDRIVE_API_KEY`
- `ACTION_MODE`
- `DEMO_DONE_STAGE_NAME`

## GitHub handoff checklist

Tomorrow, once access is available:
1. create or share the GitHub repo
2. push the current workspace branch
3. set deployment secrets
4. choose hosting target
5. wire a stable URL
6. add authentication before wider team rollout

## Immediate next deployment tasks

1. move file-backed state toward a more deployment-safe store
2. add login or access protection
3. separate frontend and backend cleanly
4. replace local file upload storage with durable cloud storage if needed
5. add background processing for uploaded lead files

## Current local storage

These stay local right now and should not be committed:
- `.secrets/`
- `uploads/`
- generated outputs in `output/`

## Suggested next milestone

Turn uploaded CSV rows into a full AI BDR workflow:
- normalize
- dedupe check
- enrichment lookup
- territory assignment
- Pipedrive write plan
- approval and audit trail
