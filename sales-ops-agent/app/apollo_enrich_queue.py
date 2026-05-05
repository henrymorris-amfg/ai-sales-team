from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from .apollo_client import load_apollo_client


ROOT = Path(__file__).resolve().parents[1]
QUEUE_FILE = ROOT / "output" / "bdr-intake-queue.json"
OUTPUT_FILE = ROOT / "output" / "apollo-enrichment-preview.json"
PRIORITY_TITLES = [
    "CEO",
    "COO",
    "Owner",
    "Managing Director",
    "Operations Director",
    "Head of Manufacturing",
    "Production Manager",
    "Manufacturing Engineer",
]


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
        org_result = client.search_organizations(domain=domain, name=company, per_page=3)
        people_result = {}
        people_error = ""
        try:
            people_result = client.search_people(
                organization_name=company,
                domain=domain,
                titles=PRIORITY_TITLES,
                per_page=5,
            )
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
