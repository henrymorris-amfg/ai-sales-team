from __future__ import annotations

import csv
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests

from .apollo_client import load_apollo_client
from .config import load_config
from .pipedrive_client import PipedriveClient
from .site_review import review_site
from .territory_map import assign_owner


ROOT = Path(__file__).resolve().parents[1]
UPLOAD_CSV = ROOT / "uploads" / "NorthOhio100.csv"
QUALIFICATION_FILE = ROOT / "config" / "qualification-criteria.json"
SOURCE_INGEST_FILE = ROOT / "config" / "source-ingest.json"
HOMEPAGE_FIELD_KEY = "667dae8863844f07bf48be7af77ae678647c6afb"
STATE_FIELD_KEY = "dd4be7e718da24b3254c4981d89b5eb6a5fb0192"
CNC_LABEL_ID = "e028bea0-b37b-11ee-9581-d55a394d57f7"
PRIORITY_TITLES = [
    "Owner",
    "Managing Director",
    "President",
    "Vice President",
    "General Manager",
    "Engineering Manager",
    "Production Manager",
    "CEO",
    "VP Operations",
    "Operations Manager",
    "Head of Operations",
]
STATE_OPTION_IDS = {
    "alabama": 1196,
    "alberta": 1197,
    "arizona": 1198,
    "california": 1200,
    "colorado": 1202,
    "connecticut": 1203,
    "florida": 1204,
    "idaho": 1205,
    "illinois": 1206,
    "indiana": 1207,
    "kentucky": 1208,
    "maine": 1210,
    "massachusetts": 1211,
    "michigan": 1212,
    "minnesota": 1213,
    "missouri": 1214,
    "new hampshire": 1216,
    "new jersey": 1217,
    "new mexico": 1218,
    "new york": 1219,
    "ohio": 1220,
    "oklahoma": 1221,
    "ontario": 1222,
    "pennsylvania": 1223,
    "rhode island": 1224,
    "tennessee": 1225,
    "texas": 1226,
    "west virginia": 1227,
    "virginia": 1228,
    "utah": 1229,
    "south carolina": 1230,
    "oregon": 1231,
    "north carolina": 1232,
    "montana": 1233,
    "maryland": 1234,
    "kansas": 1235,
    "georgia": 1236,
    "delaware": 1237,
    "wisconsin": 1253,
    "south dakota": 1254,
    "washington": 1255,
    "north dakota": 1256,
    "iowa": 1257,
    "louisiana": 1308,
    "vermont": 1309,
    "nevada": 1314,
    "arkansas": 1315,
    "nebraska": 1316,
    "mississippi": 1317,
    "non-us": 1319,
    "wyoming": 1320,
}
KNOWN_STATES = sorted(STATE_OPTION_IDS.keys(), key=len, reverse=True)


def qualification_criteria() -> dict[str, Any]:
    return json.loads(QUALIFICATION_FILE.read_text(encoding="utf-8"))


def save_qualification_criteria(payload: dict[str, Any]) -> dict[str, Any]:
    QUALIFICATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUALIFICATION_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _load_rows() -> list[dict[str, str]]:
    with UPLOAD_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def source_ingest_config() -> dict[str, Any]:
    if not SOURCE_INGEST_FILE.exists():
        return {"preferred_source_url": None, "ignore_row_numbers": []}
    return json.loads(SOURCE_INGEST_FILE.read_text(encoding="utf-8"))


def _address_parts(address: str) -> tuple[str, str, str]:
    raw = (address or "").strip()
    lowered = raw.lower()
    state = next((candidate.title() for candidate in KNOWN_STATES if candidate in lowered), "")
    country = "United States" if any(token in lowered for token in [" us", ", us", "united states", "usa"]) else ""
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    city = ""
    if state:
        for index, part in enumerate(parts):
            if state.lower() in part.lower() and index > 0:
                city = parts[index - 1]
                break
    if not country:
        country = "United States" if state else ""
    return city, state, country


def _state_option_id(state: str) -> str | None:
    option_id = STATE_OPTION_IDS.get((state or "").strip().lower())
    return str(option_id) if option_id else None


def _normalise_domain(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.removeprefix("https://").removeprefix("http://").removeprefix("www.")
    return text.strip("/")


def _normalise_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _find_org_dupes(client: PipedriveClient, org_name: str, website: str) -> list[dict[str, Any]]:
    terms = [org_name]
    domain = _normalise_domain(website)
    if domain:
        terms.append(domain)
    hits: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for term in terms:
        for result in client.search_organisations(term, limit=10):
            item = result.get("item") or {}
            item_id = item.get("id")
            if not item_id or item_id in seen_ids:
                continue
            haystacks = [
                (item.get("name") or "").lower(),
                (item.get("address") or "").lower(),
                " ".join(str(v).lower() for v in (item.get("custom_fields") or [])),
            ]
            if org_name.lower() in haystacks[0] or any(domain and domain in hay for hay in haystacks):
                hits.append(result)
                seen_ids.add(item_id)
    return hits


def _pick_owner_id(client: PipedriveClient, owner_name: str | None) -> int | None:
    if not owner_name:
        return None
    target = owner_name.strip().lower()
    for user in client.get_users():
        name = (user.get("name") or "").strip().lower()
        if target in name or name in target:
            return user.get("id")
    return None


def _find_lead_dupe(client: PipedriveClient, organisation: dict[str, Any], source_company: str) -> dict[str, Any] | None:
    org_id = organisation.get("id")
    org_name = organisation.get("name") or source_company
    norm_org = _normalise_name(org_name)
    norm_source = _normalise_name(source_company)
    for lead in client.get_all_leads(limit=500):
        if lead.get("is_archived"):
            continue
        lead_org_id = lead.get("organization_id") or lead.get("related_org_id")
        title_norm = _normalise_name(lead.get("title") or "")
        if org_id and str(lead_org_id) == str(org_id):
            return lead
        if norm_org and norm_org in title_norm:
            return lead
        if norm_source and norm_source in title_norm:
            return lead
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
    ignore_rows = {int(value) for value in source_ingest_config().get("ignore_row_numbers", [])}
    for row_number, row in enumerate(_load_rows(), start=1):
        if row_number in ignore_rows:
            continue
        company = (row.get("Company Name") or "").strip()
        if not company:
            continue

        people = apollo.search_people(organization_name=company, titles=PRIORITY_TITLES, per_page=5).get("people") or []
        for person in people:
            detail = _apollo_person_detail(apollo.api_key, person["id"])
            org = detail.get("organization") or {}
            domain = _normalise_domain(org.get("website_url") or row.get("Website") or "")
            if (not detail.get("email")) or ("email_not_unlocked" in (detail.get("email") or "")):
                matched = apollo.match_person(
                    name=detail.get("name") or "",
                    organization_name=org.get("name") or company,
                    domain=domain,
                    linkedin_url=detail.get("linkedin_url") or "",
                ).get("person") or {}
                if matched:
                    detail = matched
                    org = detail.get("organization") or org
            city, state, country = _address_parts(org.get("raw_address") or row.get("Address") or "")
            owner_name = assign_owner(country, state)
            owner_id = _pick_owner_id(client, owner_name)
            if not owner_id:
                continue
            org_name = (org.get("name") or company).strip()
            email = (detail.get("email") or "").strip()
            if "email_not_unlocked" in email:
                email = ""
            if not email:
                continue
            person_name = (detail.get("name") or "").strip()
            org_dupes = _find_org_dupes(client, org_name, org.get("website_url") or row.get("Website") or "")
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


def _score_candidate(row: dict[str, str], apollo_org: dict[str, Any], apollo_person: dict[str, Any]) -> tuple[int, list[str], dict[str, Any]]:
    criteria = qualification_criteria()
    score = criteria["base_score"]
    reasons: list[str] = []
    site_review = {"homepage_url": apollo_org.get("website_url") or row.get("Website"), "homepage_text": "", "inspected_pages": []}
    try:
        site_review = review_site(apollo_org.get("website_url") or row.get("Website") or "")
    except Exception:
        pass
    evidence_parts = [
        row.get("Description") or "",
        row.get("Capabilities") or "",
        row.get("Certifications") or "",
        apollo_org.get("short_description") or "",
        " ".join(apollo_org.get("keywords") or []),
        apollo_org.get("industry") or "",
        apollo_org.get("website_url") or "",
        site_review.get("homepage_text") or "",
        " ".join((page.get("text") or "") for page in site_review.get("inspected_pages") or []),
        " ".join((page.get("label") or "") for page in site_review.get("inspected_pages") or []),
    ]
    evidence = " ".join(evidence_parts).lower()

    def has_any(*tokens: str) -> bool:
        return any(token.lower() in evidence for token in tokens)

    rules = {rule["key"]: rule for rule in criteria.get("rules", []) if rule.get("key")}

    if has_any("cnc machining", "cnc milling", "cnc turning", "precision machining", "machine shop"):
        score += rules["cnc_machining"]["points"]
        reasons.append("CNC machining evidence found")
    if has_any("request a quote", "quote", "rfq"):
        score += rules["quote_rfq"]["points"]
        reasons.append("quote or RFQ evidence found")
    if has_any("prototyp", "contract manufacturing", "build to print", "rapid turnaround"):
        score += rules["prototype_contract_build_to_print"]["points"]
        reasons.append("prototype or contract manufacturing evidence found")
    if has_any("5-axis", "5 axis"):
        score += rules["five_axis"]["points"]
        reasons.append("5-axis evidence found")
    if has_any("aerospace", "defence", "defense"):
        score += rules["aerospace_defence"]["points"]
        reasons.append("aerospace or defence evidence found")
    if has_any("itar"):
        score += rules["itar"]["points"]
        reasons.append("ITAR evidence found")
    if has_any("motorsport", "formula 1", "f1"):
        score += rules["motorsport_f1"]["points"]
        reasons.append("motorsport evidence found")
    if has_any("capabilities", "equipment"):
        score += rules["capabilities_equipment_page"]["points"]
        reasons.append("capabilities or equipment evidence found")
    if has_any("dmg mori", "mazak", "matsuura", "okuma", "hermle", "haas"):
        score += rules["target_machine_brands"]["points"]
        reasons.append("target machine-brand evidence found")
    if has_any("3d printing", "additive manufacturing"):
        score += rules["3d_printing"]["points"]
        reasons.append("3D printing evidence found")
    if has_any("medical", "iso 13485"):
        score += rules["medical_iso13485"]["points"]
        reasons.append("medical or ISO 13485 evidence found")
    if has_any("tight tolerance", "tight tolerances", "high precision", "complex parts", "complex component"):
        score += rules["tight_tolerance_precision_complex_parts"]["points"]
        reasons.append("tight tolerance or complex-part evidence found")
    if has_any("repair", "directory", "business directory", "automotive machine shops.cmac.ws"):
        score += rules["repair_directory_false_positive"]["points"]
        reasons.append("repair-shop or directory-style evidence found")
    if has_any("sheet metal", "fabrication", "welding", "bending", "stamping"):
        score += rules["sheet_metal_fabrication"]["points"]
        reasons.append("sheet metal or fabrication-heavy evidence found")
    if has_any("high volume", "serial production"):
        score += rules["high_volume_serial_production"]["points"]
        reasons.append("high-volume production evidence found")
    if has_any("edm", "wire edm", "sinker edm"):
        score += rules["edm"]["points"]
        reasons.append("EDM evidence found")

    score = max(criteria.get("cap", {}).get("min", 0), min(criteria.get("cap", {}).get("max", 100), score))
    return score, reasons, site_review


def run() -> dict[str, Any]:
    cfg = load_config()
    client = PipedriveClient(cfg.api_base, cfg.api_key)
    candidate = _candidate_from_sheet(client, load_apollo_client().api_key)
    row = candidate["sheet_row"]
    apollo_person = candidate["apollo_person"]
    apollo_org = candidate["apollo_org"]
    score, reasons, site_review = _score_candidate(row, apollo_org, apollo_person)
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
        STATE_FIELD_KEY: _state_option_id(candidate["state"]),
        "label_ids": [CNC_LABEL_ID],
    }
    lead_payload = {k: v for k, v in lead_payload.items() if v is not None and v != ""}
    existing_lead = _find_lead_dupe(client, organisation, row.get("Company Name") or organisation.get("name") or "")
    if existing_lead:
        raise RuntimeError(f"Lead duplicate detected for organisation {organisation.get('name')}, existing lead {existing_lead.get('id')}")
    lead = client.create_lead(lead_payload)

    note_lines = [
        f"Qualification score: {score}/100",
        f"State: {candidate['state']}",
        "Justification:",
    ]
    note_lines.extend(f"- {reason}" for reason in reasons)
    note = client.create_note({
        "content": "\n".join(note_lines),
        "lead_id": lead.get("id"),
        "person_id": person.get("id"),
        "org_id": organisation.get("id"),
    })
    activity = client.create_activity({
        "subject": "Call new lead",
        "type": "call",
        "lead_id": lead.get("id"),
        "person_id": person.get("id"),
        "org_id": organisation.get("id"),
        "user_id": candidate["owner_id"],
        "due_date": str(date.today() + timedelta(days=1)),
    })

    result = {
        "created_organisation": organisation,
        "created_person": person,
        "created_lead": lead,
        "created_note": note,
        "created_activity": activity,
        "score": score,
        "score_reasons": reasons,
        "owner_name": candidate["owner_name"],
        "source_company": row.get("Company Name"),
        "used_existing_org": bool(existing_org),
        "site_review": site_review,
    }
    target = ROOT / "output" / "bdr-full-flow-result.json"
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
