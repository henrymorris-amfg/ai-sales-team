from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def build_digest(findings_path: Path, max_examples_per_rule: int = 3) -> str:
    findings = json.loads(findings_path.read_text(encoding="utf-8"))
    by_owner = defaultdict(lambda: defaultdict(list))
    for finding in findings:
        by_owner[finding.get("owner_id")][finding["rule_id"]].append(finding)

    lines = ["Machining hygiene digest", ""]
    total = len(findings)
    lines.append(f"Total findings: {total}")
    lines.append("")

    for owner, rules in sorted(by_owner.items(), key=lambda item: str(item[0] if item[0] is not None else "zz-unassigned")):
        owner_label = str(owner) if owner is not None else "unassigned"
        owner_total = sum(len(items) for items in rules.values())
        lines.append(f"Owner {owner_label}: {owner_total}")
        for rule_id, items in sorted(rules.items()):
            lines.append(f"- {rule_id}: {len(items)}")
            for item in items[:max_examples_per_rule]:
                lines.append(f"  - {item['summary']}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


if __name__ == "__main__":
    output_dir = Path(__file__).resolve().parents[1] / "output"
    digest = build_digest(output_dir / "findings.json")
    target = output_dir / "google-chat-digest.txt"
    target.write_text(digest, encoding="utf-8")
    print(target)
