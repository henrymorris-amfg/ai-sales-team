from __future__ import annotations

import json
from pathlib import Path

from .config import load_config
from .pipedrive_client import PipedriveClient


MACHINING_PIPELINE_NAME = "Machining"


def main() -> None:
    config = load_config()
    client = PipedriveClient(config.api_base, config.api_key)
    output_dir = Path(__file__).resolve().parents[1] / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    pipelines = client.get_pipelines()
    stages = client.get_stages()
    users = client.get_users()
    activity_types = client.get_activity_types()
    deal_fields = client.get_deal_fields()
    person_fields = client.get_person_fields()
    organisation_fields = client.get_organisation_fields()
    lead_labels = client.get_lead_labels()

    machining_pipeline = next((row for row in pipelines if (row.get("name") or "").strip().lower() == MACHINING_PIPELINE_NAME.lower()), None)
    machining_stages = [row for row in stages if row.get("pipeline_id") == (machining_pipeline or {}).get("id")]

    payload = {
        "pipelines": pipelines,
        "machining_pipeline": machining_pipeline,
        "machining_stages": machining_stages,
        "stages": stages,
        "users": users,
        "activity_types": activity_types,
        "deal_fields": deal_fields,
        "person_fields": person_fields,
        "organisation_fields": organisation_fields,
        "lead_labels": lead_labels,
    }

    target = output_dir / "discovery.json"
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote discovery data to {target}")
    if machining_pipeline:
        print(f"Found Machining pipeline id={machining_pipeline.get('id')} with {len(machining_stages)} stages")
    else:
        print("Machining pipeline was not found")


if __name__ == "__main__":
    main()
