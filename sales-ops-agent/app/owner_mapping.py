from __future__ import annotations

import csv
import json
from pathlib import Path


def build_owner_mapping(discovery_path: Path, output_dir: Path) -> tuple[Path, Path]:
    data = json.loads(discovery_path.read_text(encoding="utf-8"))
    users = data.get("users") or []

    json_target = output_dir / "pipedrive-user-directory.json"
    csv_target = output_dir / "owner-mapping.csv"

    directory = []
    for user in users:
        email = user.get("email") or ""
        directory.append({
            "pipedrive_user_id": user.get("id"),
            "name": user.get("name"),
            "email": email,
            "active": bool(user.get("active_flag")),
            "google_chat_target_candidate": f"users/{email}" if email else None,
        })

    json_target.write_text(json.dumps(directory, indent=2), encoding="utf-8")

    with csv_target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["pipedrive_user_id", "name", "email", "active", "google_chat_target_candidate"],
        )
        writer.writeheader()
        writer.writerows(directory)

    return json_target, csv_target


if __name__ == "__main__":
    base = Path(__file__).resolve().parents[1] / "output"
    json_path, csv_path = build_owner_mapping(base / "discovery.json", base)
    print(json_path)
    print(csv_path)
