from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
POLICY_FILE = ROOT / "config" / "action-policies.json"
ARCHIVE_APPROVALS = OUTPUT / "archive-approvals.json"
MERGE_APPROVALS = OUTPUT / "merge-approvals.json"


def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _policies() -> dict[str, Any]:
    return _load_json(POLICY_FILE, {"archive": {}, "merge": {}})


def refresh_pending_actions() -> dict[str, Any]:
    disq = _load_json(OUTPUT / "sales-ops-disqualification.json", {})
    dupes = _load_json(OUTPUT / "sales-ops-duplicates.json", {})
    policies = _policies()

    archive_items = []
    for item in disq.get("archive_candidates") or []:
        archive_items.append({
            "id": f"archive:{item.get('lead_id')}",
            "type": "archive",
            "lead_id": item.get("lead_id"),
            "title": item.get("title"),
            "score": item.get("score"),
            "confidence": item.get("confidence"),
            "reason": (item.get("disqualify_signals") or [])[:4],
            "status": "pending",
            "policy": policies.get("archive") or {},
        })

    merge_items = []
    for key in ["organisation_duplicates", "person_duplicates", "lead_duplicates"]:
        for item in dupes.get(key) or []:
            merge_items.append({
                "id": f"merge:{item.get('type')}:{item.get('cluster_key')}",
                "type": "merge",
                "record_type": item.get("type"),
                "cluster_key": item.get("cluster_key"),
                "survivor": item.get("survivor"),
                "duplicates": item.get("duplicates"),
                "confidence": item.get("confidence"),
                "status": "pending",
                "policy": policies.get("merge") or {},
            })

    _save_json(ARCHIVE_APPROVALS, {"generated_at": datetime.now(timezone.utc).isoformat(), "items": archive_items})
    _save_json(MERGE_APPROVALS, {"generated_at": datetime.now(timezone.utc).isoformat(), "items": merge_items})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "archive_pending": len(archive_items),
        "merge_pending": len(merge_items),
    }


def load_approvals(kind: str) -> dict[str, Any]:
    path = ARCHIVE_APPROVALS if kind == "archive" else MERGE_APPROVALS
    return _load_json(path, {"generated_at": None, "items": []})


def approve_action(kind: str, action_id: str) -> dict[str, Any]:
    path = ARCHIVE_APPROVALS if kind == "archive" else MERGE_APPROVALS
    payload = _load_json(path, {"generated_at": None, "items": []})
    for item in payload.get("items") or []:
        if item.get("id") == action_id:
            item["status"] = "approved"
            item["approved_at"] = datetime.now(timezone.utc).isoformat()
            _save_json(path, payload)
            return item
    raise ValueError(f"Action not found: {action_id}")


if __name__ == "__main__":
    print(json.dumps(refresh_pending_actions(), indent=2))
