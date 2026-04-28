# AE Territory Assignment

## Purpose
Assign leads to human AEs based on `Country` and `State` lead fields.

## Visible territory rules from handbook screenshots
### Europe
- Joe / Julian: UK & Ireland
- Toby: Nordics (Sweden, Finland, Norway, Denmark)
- Tad: North Eastern Europe (Poland, Baltics)
- Tad: Eastern Europe (Romania, Hungary, Slovakia, Slovenia, Croatia, Bosnia, Serbia, Bulgaria, Albania, Greece)
- Unassigned: DACH (Germany, Switzerland, Austria)
- Unassigned: France, Italy, Iberia
- Callum: Benelux (Belgium, Netherlands, Luxembourg)

### North America
- Ben: New England (Maine, New Hampshire, Vermont)
- Unassigned: Northeast (Massachusetts, Rhode Island, Connecticut, New York, New Jersey)
- Toby: Great Lakes East (Indiana, Michigan)
- Callum: Ohio Valley (Ohio, Pennsylvania, West Virginia)
- Henry: Great Lakes West (Wisconsin, Illinois)
- Unassigned: Central Plains (Iowa, Kansas, Minnesota, Missouri, Nebraska, North Dakota, South Dakota, Colorado)
- Unassigned: Mid-South & Atlantic (North Carolina, South Carolina, Tennessee, Kentucky, Virginia, Maryland, Delaware, Arkansas)
- Tad: Gulf (Florida, Mississippi, Alabama, Georgia)
- Joe: South Central (Texas, Oklahoma, New Mexico, Louisiana)
- Unassigned: Mountain West (Washington, Oregon, Arizona, Idaho, Montana, Nevada, Utah, Wyoming)
- Ben: California
- Julian: Canada, Ontario
- Julian: Canada, Quebec
- Julian: Canada, British Columbia & Alberta

## Explicit examples from user
- Texas = Joe Payne
- Canada = Julian Earl

## Assignment logic
1. If `Country` is Canada, assign Julian.
2. If `Country` is UK or Ireland, assign Joe/Julian rule based on final internal split policy.
3. If `Country` is USA, use `State` to map according to the territory matrix.
4. If territory row is unassigned, route to a holding queue for manual assignment.
5. Save assignment reason in the lead note.

## Recommended next improvement
Create a machine-readable territory map file keyed by country and US/Canada region values so the BDR agents can auto-assign cleanly.
