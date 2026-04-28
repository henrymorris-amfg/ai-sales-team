from __future__ import annotations

import json
from pathlib import Path

from .config import load_config
from .db import Database
from .models import Activity, Deal, Organisation, Person
from .pipedrive_client import PipedriveClient
from .reporting import build_markdown_report
from .rules import run_all_rules


MACHINING_PIPELINE_NAME = "Machining"


def _safe_owner_id(value):
    if isinstance(value, dict):
        return value.get("value") or value.get("id")
    return value


def _safe_linked_id(value):
    if isinstance(value, dict):
        return value.get("value") or value.get("id")
    return value


def _deal_from_api(row, pipeline_names: dict[int, str], stage_names: dict[int, str]):
    pipeline_id = row.get("pipeline_id")
    stage_id = row.get("stage_id")
    return Deal(
        id=row["id"],
        title=row.get("title", ""),
        owner_id=_safe_owner_id(row.get("owner_id")),
        status=row.get("status", ""),
        pipeline_id=pipeline_id,
        pipeline_name=row.get("pipeline_name") or pipeline_names.get(pipeline_id, ""),
        stage_id=stage_id,
        stage_name=row.get("stage_name") or stage_names.get(stage_id, ""),
        value=row.get("value"),
        next_activity_date=row.get("next_activity_date"),
        last_activity_date=row.get("last_activity_date"),
        expected_close_date=row.get("expected_close_date"),
        org_id=_safe_linked_id(row.get("org_id")),
        person_id=_safe_linked_id(row.get("person_id")),
        raw=row,
    )


def _person_from_api(row):
    emails = []
    for item in row.get("email") or []:
        if isinstance(item, dict) and item.get("value"):
            emails.append(item["value"])
        elif isinstance(item, str):
            emails.append(item)
    return Person(
        id=row["id"],
        name=row.get("name", ""),
        owner_id=_safe_owner_id(row.get("owner_id")),
        emails=emails,
        org_id=_safe_linked_id(row.get("org_id")),
        raw=row,
    )


def _org_from_api(row):
    website = row.get("website")
    if not website:
        for field_name in ("web", "website", "site", "url"):
            if row.get(field_name):
                website = row.get(field_name)
                break
    return Organisation(
        id=row["id"],
        name=row.get("name", ""),
        owner_id=_safe_owner_id(row.get("owner_id")),
        website=website,
        raw=row,
    )


def _activity_from_api(row):
    return Activity(
        id=row["id"],
        subject=row.get("subject", ""),
        type=row.get("type"),
        owner_id=_safe_owner_id(row.get("user_id")),
        due_date=row.get("due_date"),
        done=bool(row.get("done")),
        deal_id=_safe_linked_id(row.get("deal_id")),
        person_id=_safe_linked_id(row.get("person_id")),
        org_id=_safe_linked_id(row.get("org_id")),
        lead_id=row.get("lead_id"),
        raw=row,
    )


def _is_machining_deal(deal: Deal) -> bool:
    return (deal.pipeline_name or "").strip().lower() == MACHINING_PIPELINE_NAME.lower()


def _machining_related_ids(deals: list[Deal]) -> tuple[set[int], set[int], set[int]]:
    deal_ids = {deal.id for deal in deals}
    org_ids = {deal.org_id for deal in deals if deal.org_id}
    person_ids = {deal.person_id for deal in deals if deal.person_id}
    return deal_ids, org_ids, person_ids


def _completed_demo_deal_ids(activities: list[Activity], deal_ids: set[int]) -> set[int]:
    results = set()
    for activity in activities:
        if not activity.done:
            continue
        if not activity.deal_id or activity.deal_id not in deal_ids:
            continue
        text = f"{activity.type or ''} {activity.subject or ''}".lower()
        if "demo" in text:
            results.add(activity.deal_id)
    return results


def main() -> None:
    config = load_config()
    client = PipedriveClient(config.api_base, config.api_key)

    pipelines = client.get_pipelines()
    stages = client.get_stages()
    pipeline_names = {row["id"]: row.get("name", "") for row in pipelines if row.get("id") is not None}
    stage_names = {row["id"]: row.get("name", "") for row in stages if row.get("id") is not None}

    all_deals = [_deal_from_api(row, pipeline_names, stage_names) for row in client.get_deals(status="open")]
    deals = [deal for deal in all_deals if _is_machining_deal(deal)]
    deal_ids, org_ids, person_ids = _machining_related_ids(deals)

    all_persons = [_person_from_api(row) for row in client.get_persons()]
    persons = [person for person in all_persons if person.id in person_ids or (person.org_id and person.org_id in org_ids)]

    all_orgs = [_org_from_api(row) for row in client.get_organisations()]
    orgs = [org for org in all_orgs if org.id in org_ids]

    recent_activity_rows = client.get_recent_activities(limit=1000)
    all_activities = [_activity_from_api(row) for row in recent_activity_rows]
    activities = [
        activity for activity in all_activities
        if (activity.deal_id and activity.deal_id in deal_ids)
        or (activity.org_id and activity.org_id in org_ids)
        or (activity.person_id and activity.person_id in person_ids)
        or activity.lead_id
    ]

    demo_done_deal_ids = _completed_demo_deal_ids(activities, deal_ids)
    findings = run_all_rules(
        deals=deals,
        persons=persons,
        orgs=orgs,
        activities=activities,
        demo_done_deal_ids=demo_done_deal_ids,
    )

    output_dir = Path(__file__).resolve().parents[1] / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    findings_file = output_dir / "findings.json"
    findings_file.write_text(json.dumps([finding.__dict__ for finding in findings], indent=2), encoding="utf-8")

    db = Database(output_dir / "sales_ops.sqlite3")
    notes = {
        "pipeline_name": MACHINING_PIPELINE_NAME,
        "deal_count": len(deals),
        "person_count": len(persons),
        "organisation_count": len(orgs),
        "activity_count": len(activities),
        "demo_done_deal_count": len(demo_done_deal_ids),
    }
    run_id = db.insert_run("machining_hygiene_audit", notes)
    db.insert_findings(run_id, findings)

    report_text = build_markdown_report(findings, notes)
    report_file = output_dir / "machining-hygiene-report.md"
    report_file.write_text(report_text, encoding="utf-8")

    print(f"Checked {len(deals)} Machining deals, {len(persons)} persons, {len(orgs)} organisations, {len(activities)} activities")
    print(f"Detected {len(demo_done_deal_ids)} deals with completed Demo activities in the recent activity window")
    print(f"Wrote {len(findings)} findings to {findings_file}")
    print(f"Stored audit run {run_id} in {output_dir / 'sales_ops.sqlite3'}")
    print(f"Wrote report to {report_file}")


if __name__ == "__main__":
    main()
