from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .territory_map import assign_owner


ROOT = Path(__file__).resolve().parents[1]
UPLOADS_FILE = ROOT / "output" / "upload-jobs.json"
QUEUE_FILE = ROOT / "output" / "bdr-intake-queue.json"


def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


ALIASES = {
    "company": ["company", "company_name", "account", "organisation", "organization", "business_name"],
    "website": ["website", "domain", "url", "company_website"],
    "country": ["country", "region_country"],
    "state": ["state", "province", "region", "state_region"],
    "first_name": ["first_name", "firstname", "given_name"],
    "last_name": ["last_name", "lastname", "surname", "family_name"],
    "full_name": ["full_name", "name", "contact_name"],
    "email": ["email", "work_email", "business_email"],
    "phone": ["phone", "mobile", "telephone", "work_phone"],
    "linkedin": ["linkedin", "linkedin_url"],
}


def _pick(row: dict, keys: list[str]) -> str:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for key in keys:
        value = lowered.get(key)
        if value:
            return str(value).strip()
    return ""


def _normalize_row(row: dict, upload_id: str, filename: str, index: int) -> dict:
    full_name = _pick(row, ALIASES["full_name"])
    first_name = _pick(row, ALIASES["first_name"])
    last_name = _pick(row, ALIASES["last_name"])
    if not full_name:
        full_name = " ".join(part for part in [first_name, last_name] if part).strip()

    company = _pick(row, ALIASES["company"])
    website = _pick(row, ALIASES["website"])
    country = _pick(row, ALIASES["country"])
    state = _pick(row, ALIASES["state"])
    owner = assign_owner(country, state)

    routing_region = "unassigned"
    if country.lower() in {"usa", "us", "united states", "canada"}:
        routing_region = "bdr-us-ca"
    elif country.lower() in {"uk", "united kingdom", "ireland"}:
        routing_region = "bdr-uk-ie"
    elif country:
        routing_region = "bdr-eu"

    website_status = "ready"
    if not website:
        website_status = "needs_website_recovery"

    contact_status = "ready" if (_pick(row, ALIASES["email"]) or full_name) else "needs_contact_enrichment"

    return {
        "queue_id": f"{upload_id}-{index:05d}",
        "source_upload_id": upload_id,
        "source_filename": filename,
        "status": "queued",
        "company": company,
        "website": website,
        "country": country,
        "state": state,
        "contact_full_name": full_name,
        "contact_first_name": first_name,
        "contact_last_name": last_name,
        "email": _pick(row, ALIASES["email"]),
        "phone": _pick(row, ALIASES["phone"]),
        "linkedin": _pick(row, ALIASES["linkedin"]),
        "assigned_agent": routing_region,
        "assigned_owner": owner,
        "routing_status": "owner_assigned" if owner else "owner_unassigned",
        "website_status": website_status,
        "contact_status": contact_status,
        "priority": "high" if website and owner else "medium",
        "next_step": "qualify_and_enrich",
        "raw": row,
    }


def process_uploads() -> dict:
    jobs = _load_json(UPLOADS_FILE, [])
    existing_queue = _load_json(QUEUE_FILE, [])
    existing_ids = {item.get("queue_id") for item in existing_queue}
    added = []
    processed_jobs = 0

    for job in jobs:
        if job.get("status") not in {"queued", "uploaded"}:
            continue

        stored_path = ROOT / str(job.get("stored_path") or "")
        if not stored_path.exists():
            job["status"] = "missing_file"
            continue

        with stored_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)

        normalized = []
        for index, row in enumerate(rows, start=1):
            item = _normalize_row(row, str(job.get("id") or "upload"), str(job.get("filename") or "upload.csv"), index)
            if item["queue_id"] in existing_ids:
                continue
            existing_ids.add(item["queue_id"])
            normalized.append(item)

        existing_queue.extend(normalized)
        added.extend(normalized)
        job["status"] = "processed"
        job["processed_at"] = datetime.now(timezone.utc).isoformat()
        job["queue_items_created"] = len(normalized)
        processed_jobs += 1

    _save_json(QUEUE_FILE, existing_queue)
    _save_json(UPLOADS_FILE, jobs)

    return {
        "processed_jobs": processed_jobs,
        "items_added": len(added),
        "queue_size": len(existing_queue),
        "new_items": added[:20],
    }


if __name__ == "__main__":
    print(json.dumps(process_uploads(), indent=2))
