# Pipedrive Rule Logic

## Rule format
Each rule should output:
- rule_id
- title
- entity_type
- entity_id
- owner_id
- severity
- confidence
- summary
- evidence
- suggested_action

## R001 Duplicate person by exact email
### Logic
Trigger when two or more person records share the same normalized email address.
### Severity
- medium by default
- high if both records have open deals or activities
### Confidence
- 0.98 for exact same email
### Suggested action
Recommend merge review, keep the record with most linked data as primary.

## R002 Duplicate person by name plus company or domain
### Logic
Trigger when same normalized full name appears with matching organisation domain or organisation name.
### Severity
- low to medium
### Confidence
- 0.70 to 0.90 depending on overlap
### Evidence
- person names
- email domains
- organisation names

## R003 Duplicate organisation by exact website domain
### Logic
Trigger when two or more organisation records share the same normalized root domain.
### Severity
- high if both have open deals
- medium otherwise
### Confidence
- 0.97

## R004 Duplicate organisation by similar normalized name
### Logic
Normalize names by removing punctuation and legal suffixes like ltd, limited, inc, llc, plc, gmbh.
Calculate similarity. Trigger when similarity is above threshold and country or domain also overlaps.
### Confidence
- 0.75 to 0.95
### Safety
Never auto-merge from this rule alone.

## R005 Deal missing value after demo done
### Logic
If deal stage is at or beyond configured demo done stage and deal value is null, zero, or blank, create finding.
### Severity
- medium immediately
- high after 2 business days in same state
### Confidence
- 1.0
### Suggested action
Ask AE to set expected deal value or confirm why the opportunity should remain open.

## R006 Open deal has no next activity
### Logic
If deal status is open and there is no linked future activity on the deal, create finding.
### Severity
- medium
- high if no future activity and no completed activity in last 7 days
### Confidence
- 1.0
### Suggested action
Ask AE to add a next step with date and type.

## R007 Rotting deal by stage inactivity
### Logic
Trigger based on stage-specific inactivity thresholds.
Suggested starting thresholds:
- demo scheduled: 7 days with no stage movement and no future activity
- demo done: 5 days with no value or no future activity
- proposal sent: 10 days with no future activity or note
- negotiation: 14 days with no movement
### Severity
- medium for first breach
- high after repeated breach or 2x threshold
### Suggested action
Prompt AE to advance stage, add next step, update close date, or mark lost with reason.

## R008 Demo activity logged on wrong object
### Logic
Find activities whose type or subject indicates demo, but they are attached to organisation, person, or lead and not linked to a deal.
### Severity
- medium
### Confidence
- 0.95 when activity type is a configured demo type
- 0.80 when inferred from subject text
### Suggested action
Ask AE to relog or relink the activity to the correct deal.

## R009 Lead disqualified by website evidence
### Logic
Website contains explicit non-fit indicators matching handbook disqualifiers.
Examples:
- fabrication
- sheet metal
- laser cutting
- waterjet
- Swiss screw machining
- stamping
- roll forming
- tool and die
- casting
- forging
- extrusions
- no in-house machines
- instant quote only
### Confidence scoring
- +0.20 for each strong explicit disqualifier
- +0.10 for each moderate disqualifier
- -0.15 for each strong fit signal
### Auto-archive condition
- confidence >= 0.90
- at least 2 strong disqualifiers
- no strong fit signal present
- evidence saved with URL and snippets

## R010 Lead qualified by website evidence
### Logic
Website contains explicit fit indicators.
Examples:
- precision machining
- CNC milling
- 5-axis
- build to print
- RFQ upload or CAD quoting
- low volume high mix
### Output
Recommend keep active or prioritize.

## Normalization logic
### Email normalization
- lower-case
- trim whitespace
- discard placeholder values

### Domain normalization
- lower-case
- strip protocol, www, paths, and query params
- optionally reduce to registrable root domain

### Company name normalization
- lower-case
- remove punctuation
- collapse whitespace
- strip legal suffixes

## Primary record ranking for duplicate recommendations
Prefer the record with:
1. open deals
2. more completed activities
3. more populated fields
4. newer updates only as a tiebreaker

## Delivery policy
- low severity: daily digest only
- medium severity: AE nudge and manager digest
- high severity: same-day AE nudge, manager digest, repeated reminder if unresolved

## Recommended next tuning step
Review 30 to 50 real records and adjust thresholds before enabling any writeback.