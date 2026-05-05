# AI BDR Flow

## Goal
Create a coordinated AI Sales Team that feeds high-quality, territory-assigned opportunities to human AEs.

## Proposed flow
1. Ingest leads from CSV or third-party website.
2. Normalize company, website, country, state, and source data.
3. Assign a qualification score.
4. Trigger Apollo enrichment to find relevant contacts.
5. Check Pipedrive for duplicates.
6. If record exists, enrich missing information.
7. If not, add lead records for the best contacts found.
8. Always set the lead `State` custom field from the website or Apollo address, for example `Michigan`.
9. Assign owner based on `Country` and `State` territory rules.
10. Add a short lead note containing only the qualification score, the state, and the justification bullet points.
11. Create a `Call` activity for the assigned AE due the next day, with no time entered.
12. Alert the human AE in Google Chat.

## Agent roles
### Sales Ops
- owns hygiene logic
- owns scoring policy
- owns duplicates and compliance

### AI BDR regional agents
- own regional sourcing and qualification
- own enrichment requests
- own assignment to human AEs in region
- own handoff notes and alerts

## Guardrails
- recommend-only mode for first 100 scored CNC leads
- no auto-archive without evidence
- no lead ownership changes without logged reason
- duplicate checks before any create
- every score must leave an audit note
