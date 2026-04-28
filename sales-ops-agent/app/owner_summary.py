from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def main() -> None:
    output_dir = Path(__file__).resolve().parents[1] / "output"
    findings = json.loads((output_dir / "findings.json").read_text(encoding="utf-8"))
    users = json.loads((output_dir / "pipedrive-user-directory.json").read_text(encoding="utf-8"))
    user_map = {row["pipedrive_user_id"]: row for row in users}

    grouped = defaultdict(list)
    for finding in findings:
        grouped[finding.get("owner_id")].append(finding)

    summary = []
    for owner_id, items in sorted(grouped.items(), key=lambda item: str(item[0] if item[0] is not None else "zz-unassigned")):
        user = user_map.get(owner_id)
        summary.append({
            "owner_id": owner_id,
            "owner_name": (user or {}).get("name") or "Unassigned",
            "owner_email": (user or {}).get("email"),
            "google_chat_target_candidate": (user or {}).get("google_chat_target_candidate"),
            "finding_count": len(items),
            "findings": items[:10],
        })

    target = output_dir / "owner-summary.json"
    target.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
