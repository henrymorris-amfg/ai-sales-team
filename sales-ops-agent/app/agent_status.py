from __future__ import annotations

import json
from pathlib import Path


AGENTS = [
    {
        "agent_id": "sales-ops",
        "name": "Sales Ops",
        "scope": "CRM hygiene, duplicates, stage compliance, CNC lead disqualification",
        "status": "active",
        "region": "global",
    },
    {
        "agent_id": "bdr-us-ca",
        "name": "AI BDR USA & Canada",
        "scope": "CNC outbound and qualification for USA & Canada",
        "status": "planned",
        "region": "USA & Canada",
    },
    {
        "agent_id": "bdr-uk-ie",
        "name": "AI BDR UK & Ireland",
        "scope": "CNC outbound and qualification for UK & Ireland",
        "status": "planned",
        "region": "UK & Ireland",
    },
    {
        "agent_id": "bdr-eu",
        "name": "AI BDR EU",
        "scope": "CNC outbound and qualification for EU",
        "status": "planned",
        "region": "EU",
    },
]


def main() -> None:
    output_dir = Path(__file__).resolve().parents[1] / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    findings = json.loads((output_dir / "findings.json").read_text(encoding="utf-8")) if (output_dir / "findings.json").exists() else []
    cnc_queue = json.loads((output_dir / "cnc-lead-review-queue-first-100.json").read_text(encoding="utf-8")) if (output_dir / "cnc-lead-review-queue-first-100.json").exists() else []

    status = []
    for agent in AGENTS:
        row = dict(agent)
        if agent["agent_id"] == "sales-ops":
            row["queue_count"] = len(cnc_queue)
            row["processed_today"] = len(findings)
            row["errors_today"] = 0
        else:
            row["queue_count"] = 0
            row["processed_today"] = 0
            row["errors_today"] = 0
        status.append(row)

    target = output_dir / "agent-status.json"
    target.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
