from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import load_config
from .lead_review import _extract_website_candidates, _fetch_text, _is_cnc_lead
from .pipedrive_client import PipedriveClient
from .website_review import review_text
from .customer_registry import is_customer
from .customer_registry import build_customer_registry
from .action_center import refresh_pending_actions

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"
CONFIG_FILE = ROOT / "config" / "sales-ops-config.json"
WORD_RE = re.compile(r"[^a-z0-9]+")
LEGAL_SUFFIXES = {"inc", "llc", "ltd", "limited", "corp", "corporation", "co", "company", "mfg", "manufacturing"}


def worker_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {
            "disqualification": {"mode": "recommend_only", "batch_size": 200, "archive_score_max": 20, "minimum_confidence": 0.55, "require_no_conflict_flag": True},
            "duplicates": {"mode": "recommend_only", "max_candidates_per_type": 200, "organisation_similarity_min": 0.9, "person_similarity_min": 0.92, "lead_similarity_min": 0.9},
        }
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def _normalize_name(value: Any) -> str:
    text = WORD_RE.sub(" ", str(value or "").lower()).strip()
    parts = [part for part in text.split() if part and part not in LEGAL_SUFFIXES]
    return " ".join(parts)


def _domain_from_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.netloc or parsed.path or "").strip().lower().split("/", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def _first_email(value: Any) -> str:
    values = value if isinstance(value, list) else [value]
    for item in values:
        if isinstance(item, dict):
            item = item.get("value")
        text = str(item or "").strip().lower()
        if "@" in text:
            return text
    return ""


def _first_phone(value: Any) -> str:
    values = value if isinstance(value, list) else [value]
    for item in values:
        if isinstance(item, dict):
            item = item.get("value")
        digits = "".join(ch for ch in str(item or "") if ch.isdigit())
        if digits:
            return digits
    return ""


def _pick_survivor(records: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(
        records,
        key=lambda row: (
            -int(bool(row.get("active_flag", True))),
            str(row.get("update_time") or ""),
            str(row.get("add_time") or ""),
            str(row.get("id") or ""),
        ),
        reverse=True,
    )[0]


def _record_summary(row: dict[str, Any], *, domain: str = "") -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "name": row.get("name") or row.get("title"),
        "domain": domain or _domain_from_url(row.get("website") or row.get("667dae8863844f07bf48be7af77ae678647c6afb")),
        "email": _first_email(row.get("email")),
        "phone": _first_phone(row.get("phone")),
        "owner_id": row.get("owner_id"),
        "org_id": row.get("org_id") or row.get("organization_id"),
        "person_id": row.get("person_id"),
        "update_time": row.get("update_time"),
        "add_time": row.get("add_time"),
    }


def build_disqualification_report(client: PipedriveClient, cfg: dict[str, Any]) -> dict[str, Any]:
    disq_cfg = cfg.get("disqualification") or {}
    leads = client.get_all_leads(limit=500)
    cnc_leads = [lead for lead in leads if _is_cnc_lead(lead)]
    batch_size = min(int(disq_cfg.get("batch_size") or 200), len(cnc_leads))
    org_cache: dict[int, dict[str, Any]] = {}
    person_cache: dict[int, dict[str, Any]] = {}
    fetch_cache: dict[str, str] = {}
    reviewed = []
    archive_candidates = []

    for lead in sorted(cnc_leads, key=lambda row: str(row.get("update_time") or ""), reverse=True)[:batch_size]:
        if is_customer(
            organisation_id=lead.get("organization_id"),
            person_id=lead.get("person_id"),
            company=(lead.get("title") or "").split(" - ")[0],
        ):
            continue
        candidates = _extract_website_candidates(lead, client, org_cache, person_cache)
        entry = {
            "lead_id": lead.get("id"),
            "title": lead.get("title") or lead.get("name") or "Untitled lead",
            "owner_id": lead.get("owner_id"),
            "person_id": lead.get("person_id"),
            "organization_id": lead.get("organization_id"),
            "website_candidates": candidates,
            "mode": disq_cfg.get("mode", "recommend_only"),
        }
        if not candidates:
            entry.update({"status": "needs_review", "reason": "No website found", "score": 0, "confidence": 0.0, "action": "none"})
            reviewed.append(entry)
            continue

        last_error = None
        for candidate in candidates[:1]:
            try:
                text = fetch_cache.get(candidate)
                if text is None:
                    text = _fetch_text(candidate)
                    fetch_cache[candidate] = text
                result = review_text(text)
                entry.update({
                    "website": candidate,
                    "score": result.score,
                    "confidence": result.confidence,
                    "recommendation": result.recommendation,
                    "fit_signals": result.fit_signals,
                    "disqualify_signals": result.disqualify_signals,
                    "conflict_flag": result.conflict_flag,
                    "status": "reviewed",
                })
                action = "none"
                if (
                    result.recommendation == "archive_disqualified"
                    and result.score <= int(disq_cfg.get("archive_score_max") or 20)
                    and result.confidence >= float(disq_cfg.get("minimum_confidence") or 0.55)
                    and (not disq_cfg.get("require_no_conflict_flag", True) or not result.conflict_flag)
                ):
                    action = "recommend_archive"
                    archive_candidates.append(entry.copy())
                entry["action"] = action
                reviewed.append(entry)
                break
            except Exception as exc:
                last_error = str(exc)
        else:
            entry.update({"status": "needs_review", "reason": f"Website fetch failed: {last_error}", "score": 0, "confidence": 0.0, "action": "none"})
            reviewed.append(entry)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": disq_cfg.get("mode", "recommend_only"),
        "batch_size": len(reviewed),
        "archive_candidates": sorted(archive_candidates, key=lambda row: (row.get("score", 999), -float(row.get("confidence", 0)))),
        "reviewed": reviewed,
    }


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def build_duplicate_report(client: PipedriveClient, cfg: dict[str, Any]) -> dict[str, Any]:
    dup_cfg = cfg.get("duplicates") or {}
    organisations = client.get_organisations()
    persons = client.get_persons()
    leads = client.get_all_leads(limit=500)

    org_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    org_candidates = []
    for org in organisations:
        if is_customer(organisation_id=org.get("id"), company=org.get("name"), website=org.get("667dae8863844f07bf48be7af77ae678647c6afb") or org.get("website")):
            continue
        domain = _domain_from_url(org.get("667dae8863844f07bf48be7af77ae678647c6afb") or org.get("website") or org.get("name"))
        key = domain or _normalize_name(org.get("name"))
        if key:
            org_groups[key].append(org)
    for key, rows in org_groups.items():
        if len(rows) < 2:
            continue
        normalized_names = {_normalize_name(row.get("name")) for row in rows}
        if len(normalized_names) > 1:
            ratio = min(_similar(a, b) for a in normalized_names for b in normalized_names if a != b) if len(normalized_names) > 1 else 1.0
            if ratio < float(dup_cfg.get("organisation_similarity_min") or 0.9):
                continue
        survivor = _pick_survivor(rows)
        org_candidates.append({
            "type": "organisation",
            "mode": dup_cfg.get("mode", "recommend_only"),
            "confidence": round(0.7 + min(0.25, 0.05 * (len(rows) - 2)), 2),
            "cluster_key": key,
            "survivor": _record_summary(survivor, domain=key if "." in key else ""),
            "duplicates": [_record_summary(row) for row in rows if row.get("id") != survivor.get("id")],
            "reason": "Same website domain or near-identical organisation name",
            "recommended_action": "recommend_merge",
        })

    person_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    person_candidates = []
    for person in persons:
        if is_customer(person_id=person.get("id"), company=person.get("org_name"), domain=(_first_email(person.get("email")).split("@", 1)[1] if "@" in _first_email(person.get("email")) else "")):
            continue
        email = _first_email(person.get("email"))
        org_name = _normalize_name((person.get("org_name") or ""))
        key = email or f"{_normalize_name(person.get('name'))}|{org_name}"
        if key and key != "|":
            person_groups[key].append(person)
    for key, rows in person_groups.items():
        if len(rows) < 2:
            continue
        names = {_normalize_name(row.get("name")) for row in rows}
        if len(names) > 1:
            ratio = min(_similar(a, b) for a in names for b in names if a != b) if len(names) > 1 else 1.0
            if ratio < float(dup_cfg.get("person_similarity_min") or 0.92):
                continue
        survivor = _pick_survivor(rows)
        person_candidates.append({
            "type": "person",
            "mode": dup_cfg.get("mode", "recommend_only"),
            "confidence": round(0.75 + min(0.2, 0.05 * (len(rows) - 2)), 2),
            "cluster_key": key,
            "survivor": _record_summary(survivor),
            "duplicates": [_record_summary(row) for row in rows if row.get("id") != survivor.get("id")],
            "reason": "Same email or same person name within the same organisation",
            "recommended_action": "recommend_merge",
        })

    lead_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    lead_candidates = []
    for lead in leads:
        if is_customer(
            organisation_id=lead.get("organization_id"),
            person_id=lead.get("person_id"),
            company=(lead.get("title") or "").split(" - ")[0],
        ):
            continue
        org_id = lead.get("organization_id") or ""
        person_id = lead.get("person_id") or ""
        title_key = _normalize_name(lead.get("title") or lead.get("name"))
        key = f"{org_id}|{person_id}|{title_key}"
        if key != "||":
            lead_groups[key].append(lead)
    for key, rows in lead_groups.items():
        if len(rows) < 2:
            continue
        titles = {_normalize_name(row.get("title") or row.get("name")) for row in rows}
        if len(titles) > 1:
            ratio = min(_similar(a, b) for a in titles for b in titles if a != b) if len(titles) > 1 else 1.0
            if ratio < float(dup_cfg.get("lead_similarity_min") or 0.9):
                continue
        survivor = _pick_survivor(rows)
        lead_candidates.append({
            "type": "lead",
            "mode": dup_cfg.get("mode", "recommend_only"),
            "confidence": round(0.7 + min(0.2, 0.05 * (len(rows) - 2)), 2),
            "cluster_key": key,
            "survivor": _record_summary(survivor),
            "duplicates": [_record_summary(row) for row in rows if row.get("id") != survivor.get("id")],
            "reason": "Same linked org/person and matching lead title",
            "recommended_action": "recommend_merge_or_archive_duplicate",
        })

    max_items = int(dup_cfg.get("max_candidates_per_type") or 200)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": dup_cfg.get("mode", "recommend_only"),
        "organisation_duplicates": sorted(org_candidates, key=lambda row: (-row["confidence"], len(row["duplicates"])))[:max_items],
        "person_duplicates": sorted(person_candidates, key=lambda row: (-row["confidence"], len(row["duplicates"])))[:max_items],
        "lead_duplicates": sorted(lead_candidates, key=lambda row: (-row["confidence"], len(row["duplicates"])))[:max_items],
    }


def run_sales_ops_workers() -> dict[str, Any]:
    cfg = worker_config()
    build_customer_registry()
    config = load_config()
    client = PipedriveClient(config.api_base, config.api_key)
    disqualification = build_disqualification_report(client, cfg)
    duplicates = build_duplicate_report(client, cfg)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disqualification_mode": disqualification.get("mode"),
        "duplicate_mode": duplicates.get("mode"),
        "archive_recommendations": len(disqualification.get("archive_candidates") or []),
        "organisation_duplicate_clusters": len(duplicates.get("organisation_duplicates") or []),
        "person_duplicate_clusters": len(duplicates.get("person_duplicates") or []),
        "lead_duplicate_clusters": len(duplicates.get("lead_duplicates") or []),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "sales-ops-disqualification.json").write_text(json.dumps(disqualification, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "sales-ops-duplicates.json").write_text(json.dumps(duplicates, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "sales-ops-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    refresh_pending_actions()
    return summary


if __name__ == "__main__":
    print(json.dumps(run_sales_ops_workers(), indent=2))
