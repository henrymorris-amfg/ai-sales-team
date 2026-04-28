# Sales Ops Agent Technical Spec

## Purpose
This system monitors Pipedrive for CRM hygiene issues, generates rep and manager actions, and processes leads at scale for qualification and disqualification.

## Primary goals
- Detect duplicate organisations and people
- Enforce deal value capture after demo completion
- Ensure every active deal has a next activity
- Identify rotting deals and push for correct status updates
- Detect demo activities logged against the wrong record type
- Review up to 200 leads per day using website evidence and handbook criteria

## Non-goals for v1
- Blind auto-merging duplicates
- Blind auto-closing deals as lost
- High-risk write actions without audit trail
- Full autonomous qualification without a human review lane

## Users
- AEs: receive prompts and hygiene nudges
- Sales manager / Sales Ops: receive digests, exceptions, and trend reporting
- Admin: configures field mappings, thresholds, and delivery settings

## Core workflows
### 1. CRM hygiene monitoring
1. Pull changed deals, people, organisations, leads, and activities from Pipedrive.
2. Normalize records into a local working store.
3. Evaluate deterministic rules.
4. Create findings with severity, evidence, owner, and suggested action.
5. Deliver outputs as:
   - AE nudges
   - manager digest
   - review queue items
   - optional low-risk writebacks

### 2. Lead website review
1. Select the next batch of leads.
2. Fetch websites and extract readable text.
3. Score against ICP and disqualification criteria.
4. Produce recommendation plus evidence.
5. Route high-confidence non-fits to archive recommendation or auto-archive, depending on configured mode.

## Proposed system components
### A. Pipedrive connector
Responsibilities:
- Authenticate via API key from environment or secret file
- Pull records incrementally
- Fetch custom field metadata
- Write low-risk updates when enabled

### B. Normalization layer
Responsibilities:
- Normalize company names
- Normalize website domains
- Normalize email domains
- Standardize stage names and activity types
- Prepare features for rules

### C. Rule engine
Responsibilities:
- Run deterministic checks on normalized records
- Emit findings with:
  - rule_id
  - entity_type
  - entity_id
  - owner_id
  - severity
  - confidence
  - evidence
  - suggested_action

### D. Website qualification worker
Responsibilities:
- Fetch website text
- Extract evidence signals
- Score fit and non-fit indicators
- Produce recommendation and confidence
- Keep evidence snippets and URLs

### E. Action dispatcher
Responsibilities:
- Create rep-facing nudges
- Generate manager digest
- Optionally write notes or activities into Pipedrive
- Respect action mode: audit_only, suggest_only, auto_low_risk

### F. Audit and reporting layer
Responsibilities:
- Persist findings and actions
- Track false positives and overrides
- Report trends by AE, stage, and rule

## Data model
### RecordSnapshot
- source_type: deal | person | organisation | lead | activity
- source_id: string
- payload: JSON
- fetched_at: timestamp
- updated_at: timestamp

### Finding
- id
- run_id
- rule_id
- entity_type
- entity_id
- owner_id
- severity: low | medium | high
- confidence: 0 to 1
- status: open | dismissed | resolved | actioned
- summary
- evidence_json
- suggested_action
- created_at

### ActionLog
- id
- finding_id
- action_type
- destination
- payload_json
- success
- created_at

### LeadReview
- id
- lead_id
- website
- fit_score
- disqualify_score
- recommendation
- confidence
- evidence_json
- review_status
- created_at

## Modes
### audit_only
- No writebacks
- Generates findings and reports only

### suggest_only
- Generates findings and recommended actions
- Human approves changes

### auto_low_risk
- Automatically performs narrowly allowed actions
- Example: create reminder note or internal task
- Does not merge duplicates or mark deals lost without policy approval

## Threshold recommendations
- Duplicate org auto-merge: disabled
- Duplicate person auto-merge: disabled
- Missing value after demo done: medium after 0 days, high after 2 business days
- Missing next activity: medium after 0 days, high after 3 days
- Rotting deal: stage-specific thresholds
- Auto-archive lead: only when confidence >= 0.90 and evidence includes at least 2 explicit disqualifiers

## External interfaces
### Inputs
- Pipedrive API
- Website URLs from leads or organisations
- Field mapping config

### Outputs
- CSV report
- JSON findings
- Pipedrive notes or activities
- Slack or email digests later if enabled

## Config required from user team
- Pipedrive company domain
- API key location
- Exact pipeline and stage names
- Custom field IDs
- Lost reason taxonomy
- Destination for AE nudges and manager digests
- Archive policy: recommend vs auto-archive

## Delivery recommendation
### Phase 1
- audit_only
- manager digest
- weekly false-positive review

### Phase 2
- AE nudges
- suggest_only remediation

### Phase 3
- auto_low_risk actions
- lead website worker in daily batches

## Success metrics
- Duplicate rate reduced over time
- % open deals with next activity
- % post-demo deals with value populated
- # rotting deals resolved per week
- lead archive precision on reviewed sample
- rep response time to hygiene prompts

## Risks and mitigations
- False positives in disqualification, mitigate with evidence and review queue
- Wrong field mapping, mitigate with metadata discovery and config validation
- Alert fatigue, mitigate with batching and severity thresholds
- API limits, mitigate with incremental sync and cached metadata

## Recommended immediate next build step
Implement a read-only discovery script that:
1. tests Pipedrive auth
2. fetches pipelines, stages, activity types, and field metadata
3. writes a field dictionary for review
