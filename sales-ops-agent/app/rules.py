from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from typing import Iterable, List, Set

from .models import Activity, Deal, Finding, Organisation, Person
from .normalize import normalize_company_name, normalize_domain, normalize_email


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def rule_missing_deal_value(deals: Iterable[Deal], demo_done_deal_ids: Set[int]) -> List[Finding]:
    findings: List[Finding] = []
    for deal in deals:
        if deal.status != "open":
            continue
        if deal.id not in demo_done_deal_ids:
            continue
        if deal.value not in (None, 0, 0.0):
            continue
        findings.append(Finding(
            rule_id="R005",
            entity_type="deal",
            entity_id=str(deal.id),
            owner_id=deal.owner_id,
            severity="medium",
            confidence=1.0,
            summary=f"Deal '{deal.title}' has a completed Demo activity but no deal value.",
            evidence={"pipeline_name": deal.pipeline_name, "stage_name": deal.stage_name, "value": deal.value},
            suggested_action="Set the expected deal value or confirm why the deal should remain open.",
        ))
    return findings


def rule_missing_next_activity(deals: Iterable[Deal]) -> List[Finding]:
    findings: List[Finding] = []
    for deal in deals:
        if deal.status != "open":
            continue
        if deal.next_activity_date:
            continue
        findings.append(Finding(
            rule_id="R006",
            entity_type="deal",
            entity_id=str(deal.id),
            owner_id=deal.owner_id,
            severity="medium",
            confidence=1.0,
            summary=f"Open deal '{deal.title}' has no next activity.",
            evidence={"pipeline_name": deal.pipeline_name, "stage_name": deal.stage_name, "next_activity_date": deal.next_activity_date},
            suggested_action="Add a next activity on the deal.",
        ))
    return findings


def rule_demo_activity_wrong_object(activities: Iterable[Activity]) -> List[Finding]:
    findings: List[Finding] = []
    for activity in activities:
        text = f"{activity.type or ''} {activity.subject or ''}".lower()
        if "demo" not in text:
            continue
        if activity.deal_id:
            continue
        findings.append(Finding(
            rule_id="R008",
            entity_type="activity",
            entity_id=str(activity.id),
            owner_id=activity.owner_id,
            severity="medium",
            confidence=0.95 if (activity.type or "").lower() == "demo" else 0.85,
            summary=f"Demo activity '{activity.subject}' is not linked to a deal.",
            evidence={
                "type": activity.type,
                "person_id": activity.person_id,
                "org_id": activity.org_id,
                "lead_id": activity.lead_id,
                "deal_id": activity.deal_id,
            },
            suggested_action="Relink or recreate the demo activity on the correct deal.",
        ))
    return findings


def rule_duplicate_people(persons: Iterable[Person]) -> List[Finding]:
    findings: List[Finding] = []
    by_email = defaultdict(list)
    for person in persons:
        for email in person.emails:
            normalized = normalize_email(email)
            if normalized:
                by_email[normalized].append(person)

    for normalized_email, matches in by_email.items():
        if len(matches) < 2:
            continue
        for person in matches:
            findings.append(Finding(
                rule_id="R001",
                entity_type="person",
                entity_id=str(person.id),
                owner_id=person.owner_id,
                severity="medium",
                confidence=0.98,
                summary=f"Possible duplicate person records share email {normalized_email}.",
                evidence={"email": normalized_email, "match_ids": [p.id for p in matches]},
                suggested_action="Review duplicate person records and merge carefully.",
            ))
    return findings


def rule_duplicate_organisations(orgs: Iterable[Organisation]) -> List[Finding]:
    findings: List[Finding] = []
    by_domain = defaultdict(list)
    normalized_orgs = []

    for org in orgs:
        domain = normalize_domain(org.website)
        if domain:
            by_domain[domain].append(org)
        normalized_orgs.append((org, normalize_company_name(org.name)))

    for domain, matches in by_domain.items():
        if len(matches) < 2:
            continue
        for org in matches:
            findings.append(Finding(
                rule_id="R003",
                entity_type="organisation",
                entity_id=str(org.id),
                owner_id=org.owner_id,
                severity="medium",
                confidence=0.97,
                summary=f"Possible duplicate organisations share domain {domain}.",
                evidence={"domain": domain, "match_ids": [o.id for o in matches]},
                suggested_action="Review organisation duplicates before merging.",
            ))

    for index, (left_org, left_name) in enumerate(normalized_orgs):
        if not left_name:
            continue
        for right_org, right_name in normalized_orgs[index + 1:]:
            if not right_name or left_org.id == right_org.id:
                continue
            score = _similarity(left_name, right_name)
            if score < 0.92:
                continue
            findings.append(Finding(
                rule_id="R004",
                entity_type="organisation",
                entity_id=str(left_org.id),
                owner_id=left_org.owner_id,
                severity="low",
                confidence=round(score, 2),
                summary=f"Organisation name looks similar to '{right_org.name}'.",
                evidence={"left_name": left_org.name, "right_name": right_org.name, "similarity": round(score, 2)},
                suggested_action="Review possible duplicate organisation names.",
            ))
    return findings


def run_all_rules(
    deals: Iterable[Deal],
    persons: Iterable[Person],
    orgs: Iterable[Organisation],
    activities: Iterable[Activity],
    demo_done_deal_ids: Set[int],
) -> List[Finding]:
    findings: List[Finding] = []
    findings.extend(rule_missing_deal_value(deals, demo_done_deal_ids))
    findings.extend(rule_missing_next_activity(deals))
    findings.extend(rule_demo_activity_wrong_object(activities))
    findings.extend(rule_duplicate_people(persons))
    findings.extend(rule_duplicate_organisations(orgs))
    return findings
