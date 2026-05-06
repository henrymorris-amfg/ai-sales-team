from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from .apollo_client import load_apollo_client
from .bdr_full_flow import PRIORITY_TITLES, _apollo_org_candidates, _apollo_people_candidates, _is_bad_apollo_target


ROOT = Path(__file__).resolve().parents[1]
QUEUE_FILE = ROOT / "output" / "bdr-intake-queue.json"
OUTPUT_FILE = ROOT / "output" / "apollo-enrichment-preview.json"
def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _domain_from_website(website: str) -> str:
    value = (website or "").strip()
    if not value:
        return ""
    candidate = value if "://" in value else f"https://{value}"
    netloc = urlparse(candidate).netloc.lower()
    return netloc.removeprefix("www.")


def _pick_items(queue: list[dict], limit: int = 10) -> list[dict]:
    ranked = sorted(
        queue,
        key=lambda item: (
            0 if item.get("website_status") == "ready" else 1,
            0 if item.get("routing_status") == "owner_assigned" else 1,
            0 if item.get("contact_status") == "needs_contact_enrichment" else 1,
            item.get("queue_id", ""),
        ),
    )
    return ranked[:limit]


def build_preview(limit: int = 10) -> dict:
    queue = _load_json(QUEUE_FILE, [])
    client = load_apollo_client()
    items = _pick_items(queue, limit=limit)
    previews = []

    for item in items:
        domain = _domain_from_website(str(item.get("website") or ""))
        company = str(item.get("company") or "").strip()
        if _is_bad_apollo_target(company, domain):
            previews.append(
                {
                    "queue_id": item.get("queue_id"),
                    "company": company,
                    "website": item.get("website"),
                    "assigned_agent": item.get("assigned_agent"),
                    "assigned_owner": item.get("assigned_owner"),
                    "website_domain": domain,
                    "apollo_organizations": [],
                    "apollo_people": [],
                    "resolved_email": "",
                    "apollo_people_error": "Skipped invalid Apollo target",
                }
            )
            continue
        org_result = {"organizations": _apollo_org_candidates(client, company, domain)[:3]}
        people_result = {}
        people_error = ""
        resolved_email = ""
        try:
            primary_org = (org_result.get("organizations") or [None])[0]
            people_result = {"people": _apollo_people_candidates(client, company, domain, primary_org)[:5]}
            people = people_result.get("people") or []
            if people:
                top = people[0]
                matched = client.match_person(
                    name=top.get('name') or f"{top.get('first_name') or ''} {top.get('last_name_obfuscated') or ''}".replace('*', '').strip(),
                    organization_name=(primary_org or {}).get('name') or company,
                    domain=_domain_from_website((primary_org or {}).get('website_url') or (primary_org or {}).get('primary_domain') or domain),
                ).get("person") or {}
                resolved_email = matched.get("email") or ""
        except Exception as exc:
            people_error = str(exc)

        previews.append(
            {
                "queue_id": item.get("queue_id"),
                "company": company,
                "website": item.get("website"),
                "assigned_agent": item.get("assigned_agent"),
                "assigned_owner": item.get("assigned_owner"),
                "website_domain": domain,
                "apollo_organizations": (org_result.get("organizations") or [])[:3],
                "apollo_people": (people_result.get("people") or [])[:5],
                "resolved_email": resolved_email,
                "apollo_people_error": people_error,
            }
        )

    payload = {
        "queue_items_scanned": len(items),
        "preview_generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "items": previews,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(build_preview(), indent=2))
