from __future__ import annotations

TERRITORY_RULES = {
    "canada": {"*": "Julian Earl"},
    "united kingdom": {"*": "Joe/Julian"},
    "ireland": {"*": "Joe/Julian"},
    "sweden": {"*": "Toby"},
    "finland": {"*": "Toby"},
    "norway": {"*": "Toby"},
    "denmark": {"*": "Toby"},
    "poland": {"*": "Tad"},
    "estonia": {"*": "Tad"},
    "latvia": {"*": "Tad"},
    "lithuania": {"*": "Tad"},
    "romania": {"*": "Tad"},
    "hungary": {"*": "Tad"},
    "slovakia": {"*": "Tad"},
    "slovenia": {"*": "Tad"},
    "croatia": {"*": "Tad"},
    "bosnia and herzegovina": {"*": "Tad"},
    "serbia": {"*": "Tad"},
    "bulgaria": {"*": "Tad"},
    "albania": {"*": "Tad"},
    "greece": {"*": "Tad"},
    "belgium": {"*": "Callum"},
    "netherlands": {"*": "Callum"},
    "luxembourg": {"*": "Callum"},
    "united states": {
        "maine": "Ben",
        "new hampshire": "Ben",
        "vermont": "Ben",
        "indiana": "Toby",
        "michigan": "Toby",
        "ohio": "Callum",
        "pennsylvania": "Callum",
        "west virginia": "Callum",
        "wisconsin": "Henry",
        "illinois": "Henry",
        "florida": "Tad",
        "mississippi": "Tad",
        "alabama": "Tad",
        "georgia": "Tad",
        "texas": "Joe Payne",
        "oklahoma": "Joe Payne",
        "new mexico": "Joe Payne",
        "louisiana": "Joe Payne",
        "california": "Ben",
    },
}


def assign_owner(country: str | None, state: str | None) -> str | None:
    if not country:
        return None
    country_key = country.strip().lower()
    state_key = (state or "").strip().lower()
    rules = TERRITORY_RULES.get(country_key)
    if not rules:
        return None
    return rules.get(state_key) or rules.get("*")
