from __future__ import annotations

import json
from pathlib import Path

from .config import load_config
from .lead_review import _extract_website_candidates, _is_cnc_lead, _score_lead_priority
from .pipedrive_client import PipedriveClient


BATCH_SIZE = 100
ENRICHMENT_POOL_SIZE = 400


def main() -> None:
    config = load_config()
    client = PipedriveClient(config.api_base, config.api_key)
    leads = client.get_all_leads(limit=500)

    cnc_leads = [lead for lead in leads if _is_cnc_lead(lead)]
    cnc_leads.sort(key=lambda lead: str(lead.get("update_time") or ""), reverse=True)

    org_cache = {}
    person_cache = {}
    prepared = []
    for lead in cnc_leads[:ENRICHMENT_POOL_SIZE]:
        candidates = _extract_website_candidates(lead, client, org_cache, person_cache)
        prepared.append((lead, candidates))

    prepared.sort(key=lambda item: _score_lead_priority(item[0], item[1]))

    queue = []
    for lead, candidates in prepared[:BATCH_SIZE]:
        queue.append({
            "lead_id": lead.get("id"),
            "title": lead.get("title") or lead.get("name"),
            "label_ids": lead.get("label_ids") or [],
            "owner_id": lead.get("owner_id"),
            "organization_id": lead.get("organization_id"),
            "person_id": lead.get("person_id"),
            "website_candidates": candidates,
            "has_website_candidate": bool(candidates),
            "priority_reason": "website_candidate" if candidates else "missing_website",
            "update_time": lead.get("update_time"),
        })

    output_dir = Path(__file__).resolve().parents[1] / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "cnc-lead-review-queue-first-100.json"
    target.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    print(target)
    print(f"Wrote {len(queue)} queued CNC leads from {len(cnc_leads)} total CNC-labelled leads")


if __name__ == "__main__":
    main()
