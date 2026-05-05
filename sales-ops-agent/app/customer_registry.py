from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import load_config
from .pipedrive_client import PipedriveClient

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT / "output" / "customers.json"
SUMMARY_FILE = ROOT / "output" / "customers-summary.json"
MANUAL_FILE = ROOT / "config" / "customers-manual.json"
HOMEPAGE_FIELD_KEY = "667dae8863844f07bf48be7af77ae678647c6afb"


def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _domain(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.netloc or parsed.path or "").strip().lower().split("/", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def _email_domain(value: Any) -> str:
    values = value if isinstance(value, list) else [value]
    for item in values:
        if isinstance(item, dict):
            item = item.get("value")
        text = str(item or "").strip().lower()
        if "@" in text:
            return text.split("@", 1)[1]
    return ""


def _name(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _id_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("value") or value.get("id")
    return value


def build_customer_registry() -> dict[str, Any]:
    cfg = load_config()
    client = PipedriveClient(cfg.api_base, cfg.api_key)
    deals = client.get_deals(status="won")
    org_cache: dict[int, dict[str, Any]] = {}
    person_cache: dict[int, dict[str, Any]] = {}
    customers: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str, str]] = set()

    for deal in deals:
        org_id = _id_value(deal.get("org_id") or deal.get("organization_id"))
        person_id = _id_value(deal.get("person_id"))
        org = client.get_organisation(int(org_id)) if org_id not in {None, ""} else {}
        person = client.get_person(int(person_id)) if person_id not in {None, ""} else {}
        if org_id:
            org_cache[int(org_id)] = org
        if person_id:
            person_cache[int(person_id)] = person
        org_name = org.get("name") or deal.get("org_name") or ""
        domain = _domain(org.get(HOMEPAGE_FIELD_KEY) or org.get("website") or person.get("website") or _email_domain(person.get("email")))
        key = (str(org_id or ""), str(person_id or ""), _name(org_name), domain)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        customers.append({
            "source": "won_deal",
            "deal_id": deal.get("id"),
            "deal_title": deal.get("title"),
            "deal_won_time": deal.get("won_time") or deal.get("update_time"),
            "organisation_id": org_id,
            "organisation_name": org_name,
            "person_id": person_id,
            "person_name": person.get("name") or deal.get("person_name"),
            "domain": domain,
            "homepage": org.get(HOMEPAGE_FIELD_KEY) or org.get("website"),
        })

    manual = (_load_json(MANUAL_FILE, {"customers": []}) or {}).get("customers") or []
    for item in manual:
        key = (str(item.get("organisation_id") or ""), str(item.get("person_id") or ""), _name(item.get("organisation_name") or ""), _domain(item.get("homepage") or item.get("domain")))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        customers.append({
            "source": "manual",
            "deal_id": None,
            "deal_title": None,
            "deal_won_time": None,
            "organisation_id": item.get("organisation_id"),
            "organisation_name": item.get("organisation_name"),
            "person_id": item.get("person_id"),
            "person_name": item.get("person_name"),
            "domain": _domain(item.get("homepage") or item.get("domain")),
            "homepage": item.get("homepage"),
        })

    customers = sorted(customers, key=lambda row: (str(row.get("deal_won_time") or ""), str(row.get("organisation_name") or "")), reverse=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(customers),
        "customers": customers,
    }
    summary = {
        "generated_at": payload["generated_at"],
        "count": len(customers),
        "domains": sorted({row.get("domain") for row in customers if row.get("domain")})[:2000],
        "organisation_ids": sorted({str(row.get("organisation_id")) for row in customers if row.get("organisation_id")})[:2000],
        "person_ids": sorted({str(row.get("person_id")) for row in customers if row.get("person_id")})[:2000],
        "names": sorted({row.get("organisation_name") for row in customers if row.get("organisation_name")})[:2000],
    }
    _save_json(OUTPUT_FILE, payload)
    _save_json(SUMMARY_FILE, summary)
    return payload


def load_customer_registry() -> dict[str, Any]:
    return _load_json(OUTPUT_FILE, {"generated_at": None, "count": 0, "customers": []})


def load_customer_summary() -> dict[str, Any]:
    return _load_json(SUMMARY_FILE, {"generated_at": None, "count": 0, "domains": [], "organisation_ids": [], "person_ids": [], "names": []})


def is_customer(*, organisation_id: Any = None, person_id: Any = None, company: str | None = None, website: str | None = None, domain: str | None = None) -> bool:
    summary = load_customer_summary()
    domain = (domain or _domain(website)).strip().lower()
    if organisation_id and str(organisation_id) in set(summary.get("organisation_ids") or []):
        return True
    if person_id and str(person_id) in set(summary.get("person_ids") or []):
        return True
    if company and _name(company) in {_name(item) for item in (summary.get("names") or [])}:
        return True
    if domain and domain in set(summary.get("domains") or []):
        return True
    return False


if __name__ == "__main__":
    print(json.dumps(build_customer_registry(), indent=2))
