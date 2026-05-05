from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TERRITORY_FILE = ROOT / "config" / "territories.json"


def _load_territories() -> dict[str, Any]:
    if not TERRITORY_FILE.exists():
        return {"owners": {}, "unassigned": {}}
    return json.loads(TERRITORY_FILE.read_text(encoding="utf-8"))


def owner_territories() -> dict[str, Any]:
    return _load_territories()


def assign_agent(country: str | None, state: str | None = None) -> str:
    country_key = (country or "").strip().lower()
    if country_key in {"usa", "us", "united states", "canada"}:
        return "bdr-us-ca"
    if country_key in {"uk", "united kingdom", "ireland"}:
        return "bdr-uk-ie"
    if country_key:
        return "bdr-eu"
    return "unassigned"


def assign_owner(country: str | None, state: str | None) -> str | None:
    country_key = (country or "").strip().lower()
    state_key = (state or "").strip().lower()
    data = _load_territories()

    for owner, details in (data.get("owners") or {}).items():
        countries = {str(item).strip().lower() for item in (details.get("countries") or [])}
        states = {str(item).strip().lower() for item in (details.get("states") or [])}
        if country_key and country_key in countries:
            return owner
        if state_key and state_key in states:
            return owner
    return None
