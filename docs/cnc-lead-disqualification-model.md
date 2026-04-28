# CNC Lead Qualification Model

## Purpose
Score CNC-labelled leads using website evidence. Higher score means better fit.

## Recommendation bands
- 80 to 100: very good fit
- 60 to 79: good fit
- 21 to 59: needs human review
- 0 to 20: very poor fit, auto-archive eligible

## Fit understanding based on AMFG
AMFG sells manufacturing software for quoting and production workflow management. Best-fit CNC prospects are manufacturers with real production complexity, quoting pain, RFQ flow, CAD/drawing intake, and CNC machining operations.

## Scoring structure
- Start every lead at 50
- Add positive points for strong AMFG-fit signals
- Subtract points for disqualifying signals
- Keep the model a bit softer, especially for mixed machining shops that also mention adjacent processes

## Negative signals, subtract points
### Very bad, -30 to -24
- sheet metal only
- laser cutting only
- waterjet only
- stamping
- roll forming
- forging
- no in-house manufacturing capability
- not accepting RFQs

### Bad, -22 to -16
- Swiss screw heavy focus
- tool and die focus
- casting focus
- extrusion focus
- jigs / fixtures only
- mostly 2D simple drawing work
- instant quote only

### Softer negatives, -18 to -10
- fabrication mentioned, but not automatically disqualifying on its own
- additive manufacturing only
- molding focus
- consultancy without machine-shop evidence

## Positive signals, add points
### Strong positives, +18 to +14
- precision machining
- CNC machining
- 5-axis
- build-to-print
- request a quote / RFQ
- subcontract manufacturing

### Medium positives, +12 to +8
- CNC milling
- CNC turning
- mill-turn
- billet / blank machining
- CAD
- engineering drawings
- estimating / production planning

### Supporting positives, +8 to +5
- aerospace
- medical
- defense
- ISO 9001
- AS9100
- MES / ERP context

## Special rules
- If a lead has both strong fit and strong disqualifier signals, keep it in review instead of auto-archiving.
- If the website cannot be fetched, do not archive. Route to review.
- If the lead is labelled CNC but scores very low, include evidence because label and website are in conflict.

## Output format
Each scored lead should produce:
- lead_id
- title
- label_ids
- website
- score
- recommendation
- fit_signals
- disqualify_signals
- evidence snippets
- conflict_flag

## Rollout rule
- First 100 CNC leads: recommend only
- After reviewed precision is acceptable: auto-archive only 0 to 20 score leads with explicit evidence
