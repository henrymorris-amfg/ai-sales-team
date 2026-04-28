from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from .models import Finding


RULE_TITLES = {
    "R001": "Duplicate people by email",
    "R003": "Duplicate organisations by domain",
    "R004": "Similar organisation names",
    "R005": "Missing deal value after completed demo",
    "R006": "Open deal missing next activity",
    "R008": "Demo activity logged on wrong object",
}


def build_markdown_report(findings: Iterable[Finding], notes: dict | None = None) -> str:
    findings = list(findings)
    by_rule = Counter(f.rule_id for f in findings)
    by_owner = Counter(str(f.owner_id or "unassigned") for f in findings)
    by_severity = Counter(f.severity for f in findings)

    lines = ["# Machining Pipeline Hygiene Report", ""]
    if notes:
        lines.append(f"- Pipeline: {notes.get('pipeline_name', 'unknown')}")
        lines.append(f"- Deals checked: {notes.get('deal_count', 0)}")
        lines.append(f"- Persons checked: {notes.get('person_count', 0)}")
        lines.append(f"- Organisations checked: {notes.get('organisation_count', 0)}")
        lines.append(f"- Activities checked: {notes.get('activity_count', 0)}")
        lines.append("")

    lines.append("## Summary")
    lines.append(f"- Total findings: {len(findings)}")
    for severity, count in sorted(by_severity.items()):
        lines.append(f"- {severity.title()}: {count}")
    lines.append("")

    lines.append("## Findings by rule")
    for rule_id, count in sorted(by_rule.items()):
        lines.append(f"- {rule_id} {RULE_TITLES.get(rule_id, '')}: {count}")
    lines.append("")

    lines.append("## Findings by owner")
    for owner_id, count in by_owner.most_common():
        lines.append(f"- Owner {owner_id}: {count}")
    lines.append("")

    grouped = defaultdict(list)
    for finding in findings:
        grouped[finding.rule_id].append(finding)

    lines.append("## Sample findings")
    for rule_id, items in sorted(grouped.items()):
        lines.append(f"### {rule_id} {RULE_TITLES.get(rule_id, '')}")
        for finding in items[:10]:
            lines.append(f"- {finding.summary} (owner: {finding.owner_id}, confidence: {finding.confidence})")
        lines.append("")

    return "\n".join(lines).strip() + "\n"
