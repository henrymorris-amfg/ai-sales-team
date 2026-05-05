from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests

from .config import load_config
from .customer_registry import build_customer_registry, is_customer
from .pipedrive_client import PipedriveClient
from .website_review import review_text


BATCH_SIZE = 100
ENRICHMENT_POOL_SIZE = 400
ORGANISATION_HOMEPAGE_FIELD_KEY = "667dae8863844f07bf48be7af77ae678647c6afb"
CNC_LABEL_ID = "e028bea0-b37b-11ee-9581-d55a394d57f7"
URL_SPLIT_RE = re.compile(r"[\s,;|]+")


def _emails_to_domains(email_value: Any) -> list[str]:
    results: list[str] = []
    values = email_value if isinstance(email_value, list) else [email_value]
    for item in values:
        value = item.get("value") if isinstance(item, dict) else item
        if value and "@" in str(value):
            domain = str(value).split("@", 1)[1].strip().lower()
            if domain and domain not in results:
                results.append(domain)
    return results


def _split_urls(value: Any) -> list[str]:
    if not value:
        return []
    text = str(value).strip()
    if not text:
        return []
    parts = [part.strip() for part in URL_SPLIT_RE.split(text) if part.strip()]
    urls: list[str] = []
    for part in parts:
        cleaned = part.strip().strip("/")
        if cleaned.lower() in {"http:", "https:"}:
            continue
        if "." not in cleaned:
            continue
        urls.append(cleaned)
    return urls


def _website_candidates_from_record(record: Dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in (ORGANISATION_HOMEPAGE_FIELD_KEY, "website", "web", "url"):
        for candidate in _split_urls(record.get(key)):
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _normalize_url(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or parsed.path or "").strip().lower()
    host = host.split("/", 1)[0].strip()
    if host.startswith("www."):
        host = host[4:]
    return f"https://{host}" if host else ""


def _get_org(org_id: int, client: PipedriveClient, org_cache: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    organisation = org_cache.get(org_id)
    if organisation is None:
        organisation = client.get_organisation(org_id)
        org_cache[org_id] = organisation
    return organisation


def _get_person(person_id: int, client: PipedriveClient, person_cache: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    person = person_cache.get(person_id)
    if person is None:
        person = client.get_person(person_id)
        person_cache[person_id] = person
    return person


def _extract_website_candidates(
    lead: Dict[str, Any],
    client: PipedriveClient,
    org_cache: Dict[int, Dict[str, Any]],
    person_cache: Dict[int, Dict[str, Any]],
) -> list[str]:
    candidates: list[str] = []

    for candidate in _website_candidates_from_record(lead):
        normalized = _normalize_url(candidate)
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    org_id = lead.get("organization_id")
    if org_id:
        organisation = _get_org(int(org_id), client, org_cache)
        for candidate in _website_candidates_from_record(organisation):
            normalized = _normalize_url(candidate)
            if normalized and normalized not in candidates:
                candidates.append(normalized)
        for domain in _emails_to_domains(organisation.get("email")):
            normalized = _normalize_url(domain)
            if normalized and normalized not in candidates:
                candidates.append(normalized)

    person_id = lead.get("person_id")
    if person_id:
        person = _get_person(int(person_id), client, person_cache)
        for candidate in _website_candidates_from_record(person):
            normalized = _normalize_url(candidate)
            if normalized and normalized not in candidates:
                candidates.append(normalized)
        for domain in _emails_to_domains(person.get("email")):
            normalized = _normalize_url(domain)
            if normalized and normalized not in candidates:
                candidates.append(normalized)

    return candidates


def _fetch_text(url: str, timeout: int = 4) -> str:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 OpenClaw SalesOps Prototype"})
    response.raise_for_status()
    return response.text[:120000]


def _score_lead_priority(lead: Dict[str, Any], candidates: list[str]) -> tuple[int, int, str]:
    has_site = 0 if candidates else 1
    updated = str(lead.get("update_time") or "")
    return (has_site, 0 if lead.get("organization_id") else 1, updated)


def _is_cnc_lead(lead: Dict[str, Any]) -> bool:
    return CNC_LABEL_ID in (lead.get("label_ids") or [])


def build_recommendations(leads: List[Dict[str, Any]], client: PipedriveClient) -> List[Dict[str, Any]]:
    recommendations = []
    build_customer_registry()
    org_cache: Dict[int, Dict[str, Any]] = {}
    person_cache: Dict[int, Dict[str, Any]] = {}

    cnc_leads = [lead for lead in leads if _is_cnc_lead(lead)]
    cnc_leads.sort(key=lambda lead: str(lead.get("update_time") or ""), reverse=True)

    prepared = []
    for lead in cnc_leads[:ENRICHMENT_POOL_SIZE]:
        if is_customer(
            organisation_id=lead.get("organization_id"),
            person_id=lead.get("person_id"),
            company=(lead.get("title") or "").split(" - ")[0],
        ):
            continue
        candidates = _extract_website_candidates(lead, client, org_cache, person_cache)
        prepared.append((lead, candidates))

    prepared.sort(key=lambda item: _score_lead_priority(item[0], item[1]))

    fetch_cache: Dict[str, str] = {}
    for lead, candidates in prepared[:BATCH_SIZE]:
        title = lead.get("title") or lead.get("name")
        if not candidates:
            recommendations.append({
                "lead_id": lead.get("id"),
                "title": title,
                "label_ids": lead.get("label_ids") or [],
                "website": None,
                "website_candidates": [],
                "recommendation": "needs_review",
                "confidence": 0.0,
                "score": 0,
                "conflict_flag": False,
                "reason": "No website found on lead, organisation, or person data.",
            })
            continue

        last_error = None
        chosen_url = None
        for candidate in candidates[:1]:
            chosen_url = candidate
            try:
                text = fetch_cache.get(candidate)
                if text is None:
                    text = _fetch_text(candidate)
                    fetch_cache[candidate] = text
                result = review_text(text)
                recommendations.append({
                    "lead_id": lead.get("id"),
                    "title": title,
                    "label_ids": lead.get("label_ids") or [],
                    "website": candidate,
                    "website_candidates": candidates,
                    "recommendation": result.recommendation,
                    "confidence": result.confidence,
                    "score": result.score,
                    "conflict_flag": result.conflict_flag,
                    "fit_signals": result.fit_signals,
                    "disqualify_signals": result.disqualify_signals,
                })
                break
            except Exception as exc:
                last_error = str(exc)
        else:
            recommendations.append({
                "lead_id": lead.get("id"),
                "title": title,
                "label_ids": lead.get("label_ids") or [],
                "website": chosen_url,
                "website_candidates": candidates,
                "recommendation": "needs_review",
                "confidence": 0.0,
                "score": 0,
                "conflict_flag": False,
                "reason": f"Website fetch failed: {last_error}",
            })
    return recommendations


def main() -> None:
    config = load_config()
    client = PipedriveClient(config.api_base, config.api_key)
    leads = client.get_all_leads(limit=500)

    recommendations = build_recommendations(leads, client)
    output_dir = Path(__file__).resolve().parents[1] / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "cnc-lead-review-first-100.json"
    target.write_text(json.dumps(recommendations, indent=2), encoding="utf-8")
    print(target)
    print(f"Wrote {len(recommendations)} CNC lead review recommendations")


if __name__ == "__main__":
    main()
