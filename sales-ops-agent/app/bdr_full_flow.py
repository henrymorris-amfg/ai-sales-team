from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import requests

from .apollo_client import load_apollo_client
from .config import load_config
from .pipedrive_client import PipedriveClient
from .territory_map import assign_owner


ROOT = Path(__file__).resolve().parents[1]
UPLOAD_CSV = ROOT / "uploads" / "NorthOhio100.csv"
HOMEPAGE_FIELD_KEY = "667dae8863844f07bf48be7af77ae678647c6afb"
PRIORITY_TITLES = [
    "President",
    "Owner",
    "CEO",
    "Vice President Operations",
    "VP Operations",
    "Operations Manager",
    "Vice President",
    "Head of Operations",
]


def _load_rows() -> list[dict[str, str]]:
    with UPLOAD_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _address_parts(address: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in (address or "").split(",") if part.strip()]
    country = "United States"
    state = parts[-2] if len(parts) >= 2 else ""
    city = parts[-3] if len(parts) >= 3 else ""
    if parts and parts[-1].upper() in {"US", "USA", "UNITED STATES"}:
        country = "United States"
        state = parts[-2] if len(parts) >= 2 else ""
        city = parts[-3] if len(parts) >= 3 else ""
    return city, state, country


def _pick_owner_id(client: PipedriveClient, owner_name: str | None) -> int | None:
    if not owner_name:
        return None
    target = owner_name.strip().lower()
    for user in client.get_users():
        name = (user.get("name") or "").strip().lower()
        if target in name or name in target:
            return user.get("id")
    return None


def _apollo_person_detail(api_key: str, person_id: str) -> dict[str, Any]:
    response = requests.get(
        f"https://api.apollo.io/api/v1/people/{person_id}",
        headers={"X-Api-Key": api_key},
        timeout=45,
    )
    response.raise_for_status()
    return response.json().get("person") or {}


def _candidate_from_sheet(client: PipedriveClient, apollo_api_key: str) -> dict[str, Any]:
    apollo = load_apollo_client()
    for row in _load_rows():
        company = (row.get("Company Name") or "").strip()
        if not company:
            continue
        city, state, country = _address_parts(row.get("Address") or "")
        owner_name = assign_owner(country, state)
        owner_id = _pick_owner_id(client, owner_name)
        if not owner_id:
            continue

        people = apollo.search_people(organization_name=company, titles=PRIORITY_TITLES, per_page=5).get("people") or []
        for person in people:
            detail = _apollo_person_detail(apollo.api_key, person["id"])
            org = detail.get("organization") or {}
            org_name = (org.get("name") or company).strip()
            email = (detail.get("email") or "").strip()
            if "email_not_unlocked" in email:
                email = ""
            person_name = (detail.get("name") or "").strip()
            org_dupes = client.search_organisations(org_name, limit=5)
            person_dupes = client.search_persons(email or person_name, limit=5) if (email or person_name) else []
            if person_dupes:
                continue
            return {
                "sheet_row": row,
                "apollo_person": detail,
                "apollo_org": org,
                "owner_name": owner_name,
                "owner_id": owner_id,
                "city": city,
                "state": state,
                "country": country,
                "org_dupes": org_dupes,
                "person_dupes": person_dupes,
            }
    raise RuntimeError("No candidate found with Apollo match, no Pipedrive dupes, and a routable owner")


def _score_candidate(row: dict[str, str], apollo_org: dict[str, Any], apollo_person: dict[str, Any]) -> tuple[int, list[str]]:
    score = 50
    reasons: list[str] = []
    certifications = (row.get("Certifications") or "").lower()
    capabilities = (row.get("Capabilities") or "").lower()
    employees = int(re.sub(r"[^0-9]", "", row.get("Employees") or "0") or 0)
    title = (apollo_person.get("title") or "").lower()

    if any(token in capabilities for token in ["5-axis", "cnc machining", "cnc turning", "cnc milling"]):
        score += 15
        reasons.append("strong CNC capability signals")
    if any(token in certifications for token in ["iso 9001", "as9100", "itar"]):
        score += 15
        reasons.append("quality/compliance certifications present")
    if employees >= 5:
        score += 10
        reasons.append("team size suggests an active shop")
    if any(token in title for token in ["owner", "president", "vp", "operations"]):
        score += 10
        reasons.append("Apollo found a relevant decision-maker or operator contact")
    if apollo_org.get("industry"):
        score += 5
        reasons.append(f"Apollo industry: {apollo_org.get('industry')}")
    score = max(0, min(100, score))
    return score, reasons


def run() -> dict[str, Any]:
    cfg = load_config()
    client = PipedriveClient(cfg.api_base, cfg.api_key)
    candidate = _candidate_from_sheet(client, load_apollo_client().api_key)
    row = candidate["sheet_row"]
    apollo_person = candidate["apollo_person"]
    apollo_org = candidate["apollo_org"]
    score, reasons = _score_candidate(row, apollo_org, apollo_person)
    org_dupes = candidate.get("org_dupes") or []
    existing_org = ((org_dupes[0] or {}).get("item") or {}) if org_dupes else None

    if existing_org:
        organisation = existing_org
    else:
        org_payload = {
            "name": apollo_org.get("name") or row.get("Company Name"),
            "owner_id": candidate["owner_id"],
            "address": apollo_org.get("raw_address") or row.get("Address"),
            HOMEPAGE_FIELD_KEY: (apollo_org.get("website_url") or row.get("Website") or "").replace("http://", "https://"),
        }
        organisation = client.create_organisation(org_payload)

    person_payload = {
        "name": apollo_person.get("name"),
        "owner_id": candidate["owner_id"],
        "org_id": organisation.get("id"),
        "email": apollo_person.get("email") if apollo_person.get("email") and "email_not_unlocked" not in apollo_person.get("email", "") else None,
        "phone": (apollo_org.get("phone") or ""),
    }
    person_payload = {k: v for k, v in person_payload.items() if v not in {None, ""}}
    person = client.create_person(person_payload)

    lead_title = f"{organisation.get('name')} - {apollo_person.get('title') or 'Apollo lead'}"
    lead_payload = {
        "title": lead_title,
        "owner_id": candidate["owner_id"],
        "person_id": person.get("id"),
        "organization_id": organisation.get("id"),
    }
    lead = client.create_lead(lead_payload)

    note_lines = [
        f"AI BDR qualification score: {score}/100",
        f"Assigned owner: {candidate['owner_name']} (user id {candidate['owner_id']})",
        f"Contact: {apollo_person.get('name')} | {apollo_person.get('title')}",
        f"Website: {apollo_org.get('website_url') or row.get('Website')}",
        f"Address: {apollo_org.get('raw_address') or row.get('Address')}",
        "Why this lead scored well:",
    ]
    note_lines.extend(f"- {reason}" for reason in reasons)
    note_lines.extend([
        "Duplicate checks completed before create:",
        f"- org search on '{apollo_org.get('name') or row.get('Company Name')}' returned {len(org_dupes)} usable matches",
        f"- person search on '{apollo_person.get('email') or apollo_person.get('name')}' returned 0 usable matches",
        "Source: NorthOhio100 Google Sheet + Apollo enrichment",
    ])
    note = client.create_note({
        "content": "\n".join(note_lines),
        "lead_id": lead.get("id"),
        "person_id": person.get("id"),
        "org_id": organisation.get("id"),
    })

    result = {
        "created_organisation": organisation,
        "created_person": person,
        "created_lead": lead,
        "created_note": note,
        "score": score,
        "score_reasons": reasons,
        "owner_name": candidate["owner_name"],
        "source_company": row.get("Company Name"),
        "used_existing_org": bool(existing_org),
    }
    target = ROOT / "output" / "bdr-full-flow-result.json"
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
