from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any

import requests

from .apollo_client import load_apollo_client
from .apollo_client import ApolloRateLimitError, ApolloTransientError
from .config import load_config
from .pipedrive_client import PipedriveClient
from .site_review import review_site
from .territory_map import assign_owner, assign_agent
from .customer_registry import is_customer
from .customer_registry import build_customer_registry


ROOT = Path(__file__).resolve().parents[1]
UPLOAD_CSV = ROOT / "uploads" / "NorthOhio100.csv"
QUEUE_FILE = ROOT / "output" / "bdr-intake-queue.json"
QUALIFICATION_FILE = ROOT / "config" / "qualification-criteria.json"
SOURCE_INGEST_FILE = ROOT / "config" / "source-ingest.json"
AUTOMATION_CONFIG_FILE = ROOT / "config" / "automation-config.json"
HOMEPAGE_FIELD_KEY = "667dae8863844f07bf48be7af77ae678647c6afb"
STATE_FIELD_KEY = "dd4be7e718da24b3254c4981d89b5eb6a5fb0192"
CNC_LABEL_ID = "e028bea0-b37b-11ee-9581-d55a394d57f7"
PRIORITY_TITLES = [
    "Owner",
    "Managing Director",
    "President",
    "Vice President",
    "General Manager",
    "Engineering Manager",
    "Production Manager",
    "CEO",
    "VP Operations",
    "Operations Manager",
    "Head of Operations",
]
STATE_OPTION_IDS = {
    "alabama": 1196,
    "alberta": 1197,
    "arizona": 1198,
    "california": 1200,
    "colorado": 1202,
    "connecticut": 1203,
    "florida": 1204,
    "idaho": 1205,
    "illinois": 1206,
    "indiana": 1207,
    "kentucky": 1208,
    "maine": 1210,
    "massachusetts": 1211,
    "michigan": 1212,
    "minnesota": 1213,
    "missouri": 1214,
    "new hampshire": 1216,
    "new jersey": 1217,
    "new mexico": 1218,
    "new york": 1219,
    "ohio": 1220,
    "oklahoma": 1221,
    "ontario": 1222,
    "pennsylvania": 1223,
    "rhode island": 1224,
    "tennessee": 1225,
    "texas": 1226,
    "west virginia": 1227,
    "virginia": 1228,
    "utah": 1229,
    "south carolina": 1230,
    "oregon": 1231,
    "north carolina": 1232,
    "montana": 1233,
    "maryland": 1234,
    "kansas": 1235,
    "georgia": 1236,
    "delaware": 1237,
    "wisconsin": 1253,
    "south dakota": 1254,
    "washington": 1255,
    "north dakota": 1256,
    "iowa": 1257,
    "louisiana": 1308,
    "vermont": 1309,
    "nevada": 1314,
    "arkansas": 1315,
    "nebraska": 1316,
    "mississippi": 1317,
    "non-us": 1319,
    "wyoming": 1320,
}
KNOWN_STATES = sorted(STATE_OPTION_IDS.keys(), key=len, reverse=True)
APOLLO_QUEUE_RETRY_MINUTES = 360
APOLLO_QUEUE_TRANSIENT_RETRY_MINUTES = 120
APOLLO_NO_MATCH_RETRY_DAYS = 7
APOLLO_CACHE_TTL_HOURS = 24
SITE_REVIEW_TIMEOUT_SECONDS = 12


@dataclass
class CandidateSkip(RuntimeError):
    message: str

    def __str__(self) -> str:
        return self.message


def qualification_criteria() -> dict[str, Any]:
    return json.loads(QUALIFICATION_FILE.read_text(encoding="utf-8"))


def save_qualification_criteria(payload: dict[str, Any]) -> dict[str, Any]:
    QUALIFICATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUALIFICATION_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _load_rows() -> list[dict[str, str]]:
    with UPLOAD_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_queue_items() -> list[dict[str, Any]]:
    if not QUEUE_FILE.exists():
        return []
    return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))


def _save_queue_items(items: list[dict[str, Any]]) -> None:
    QUEUE_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _update_queue_item(queue_id: str | None, **changes: Any) -> None:
    if not queue_id:
        return
    items = _load_queue_items()
    for item in items:
        if item.get("queue_id") == queue_id:
            item.update(changes)
            break
    _save_queue_items(items)


def _apollo_retry_after_seconds_from_response(response: requests.Response | None) -> int | None:
    if response is None:
        return None
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return None
    try:
        return max(0, int(float(retry_after)))
    except ValueError:
        return None


def _queue_item_is_ready(queue_item: dict[str, Any]) -> bool:
    retry_at = str(queue_item.get("apollo_retry_after") or "").strip()
    if not retry_at:
        return True
    try:
        retry_dt = date.fromisoformat(retry_at[:10]) if len(retry_at) == 10 else None
    except ValueError:
        retry_dt = None
    if retry_dt is not None:
        return True
    try:
        retry_dt_full = datetime.fromisoformat(retry_at)
    except Exception:
        return True
    if retry_dt_full.tzinfo is None:
        retry_dt_full = retry_dt_full.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= retry_dt_full.astimezone(timezone.utc)


def _mark_apollo_retry_later(queue_id: str | None, message: str, retry_after_seconds: int | None = None) -> None:
    if not queue_id:
        return
    next_retry = datetime.now(timezone.utc) + timedelta(seconds=retry_after_seconds or (APOLLO_QUEUE_RETRY_MINUTES * 60))
    _update_queue_item(
        queue_id,
        apollo_status="rate_limited",
        apollo_last_error=message,
        apollo_last_error_at=datetime.now(timezone.utc).isoformat(),
        apollo_retry_after=next_retry.isoformat(),
        next_step="retry_apollo_later",
    )


def _mark_apollo_transient_retry_later(queue_id: str | None, message: str, retry_after_seconds: int | None = None) -> None:
    if not queue_id:
        return
    next_retry = datetime.now(timezone.utc) + timedelta(seconds=retry_after_seconds or (APOLLO_QUEUE_TRANSIENT_RETRY_MINUTES * 60))
    _update_queue_item(
        queue_id,
        apollo_status="transient_error",
        apollo_last_error=message,
        apollo_last_error_at=datetime.now(timezone.utc).isoformat(),
        apollo_retry_after=next_retry.isoformat(),
        next_step="retry_apollo_later",
    )


def source_ingest_config() -> dict[str, Any]:
    if AUTOMATION_CONFIG_FILE.exists():
        return (json.loads(AUTOMATION_CONFIG_FILE.read_text(encoding="utf-8")) or {}).get("source") or {"preferred_source_url": None, "ignore_row_numbers": []}
    if not SOURCE_INGEST_FILE.exists():
        return {"preferred_source_url": None, "ignore_row_numbers": []}
    return json.loads(SOURCE_INGEST_FILE.read_text(encoding="utf-8"))


def automation_config() -> dict[str, Any]:
    if not AUTOMATION_CONFIG_FILE.exists():
        return {"batch": {"limit": 3, "min_score": 35}, "safety": {}}
    return json.loads(AUTOMATION_CONFIG_FILE.read_text(encoding="utf-8"))


def _address_parts(address: str) -> tuple[str, str, str]:
    raw = (address or "").strip()
    lowered = raw.lower()
    state = next((candidate.title() for candidate in KNOWN_STATES if candidate in lowered), "")
    country = "United States" if any(token in lowered for token in [" us", ", us", "united states", "usa"]) else ""
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    city = ""
    if state:
        for index, part in enumerate(parts):
            if state.lower() in part.lower() and index > 0:
                city = parts[index - 1]
                break
    if not country:
        country = "United States" if state else ""
    return city, state, country


def _state_option_id(state: str) -> str | None:
    option_id = STATE_OPTION_IDS.get((state or "").strip().lower())
    return str(option_id) if option_id else None


def _normalise_domain(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.removeprefix("https://").removeprefix("http://").removeprefix("www.")
    return text.strip("/")


def _normalise_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _looks_like_placeholder_company(company: str) -> bool:
    text = _normalise_name(company)
    return text in {"acmeprecision", "betacnc", "examplecompany", "testcompany"}


def _looks_like_placeholder_domain(domain: str) -> bool:
    text = _normalise_domain(domain)
    return (not text) or text.endswith(".example") or text == "example.com" or text.startswith("example.")


def _is_bad_apollo_target(company: str, website: str) -> str | None:
    domain = _normalise_domain(website)
    if _looks_like_placeholder_company(company):
        return "placeholder_company"
    if _looks_like_placeholder_domain(domain):
        return "placeholder_domain"
    return None


def _mark_queue_no_match(queue_id: str | None, status: str, message: str, *, retry_days: int | None = None) -> None:
    if not queue_id:
        return
    changes: dict[str, Any] = {
        "apollo_status": status,
        "apollo_last_error": message,
        "apollo_last_error_at": datetime.now(timezone.utc).isoformat(),
        "next_step": "review_apollo_match",
    }
    if retry_days:
        changes["apollo_retry_after"] = (datetime.now(timezone.utc) + timedelta(days=retry_days)).isoformat()
        changes["next_step"] = "retry_apollo_later"
    _update_queue_item(queue_id, **changes)


def _cache_is_fresh(timestamp: str | None, ttl_hours: int = APOLLO_CACHE_TTL_HOURS) -> bool:
    if not timestamp:
        return False
    try:
        cached_at = datetime.fromisoformat(timestamp)
    except Exception:
        return False
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - cached_at.astimezone(timezone.utc) <= timedelta(hours=ttl_hours)


def _title_rank(title: str) -> tuple[int, int]:
    lowered = (title or "").strip().lower()
    for idx, preferred in enumerate(PRIORITY_TITLES):
        pref = preferred.lower()
        if lowered == pref:
            return (0, idx)
        if pref in lowered:
            return (1, idx)
    if any(token in lowered for token in ["president", "owner", "founder", "chief", "vp", "vice president", "general manager", "engineering manager", "production manager", "operations"]):
        return (2, 50)
    return (9, 999)


def _sort_people(people: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(person: dict[str, Any]) -> tuple[int, int, int, str]:
        title = person.get("title") or person.get("job_title") or ""
        has_email = 0 if (person.get("email") and "email_not_unlocked" not in str(person.get("email"))) else 1
        seniority = 0 if person.get("seniority") else 1
        return (*_title_rank(title), has_email, seniority, (person.get("name") or "").lower())

    return sorted(people, key=key)


def _apollo_org_candidates(apollo, company: str, domain: str) -> list[dict[str, Any]]:
    searches = [
        {"name": company, "per_page": 5},
        {"domain": domain, "per_page": 5} if domain else None,
        {"name": company, "domain": domain, "per_page": 5} if domain else None,
    ]
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for params in searches:
        if not params:
            continue
        result = apollo.search_organizations(**params)
        for org in result.get("organizations") or []:
            org_id = str(org.get("id") or "")
            marker = org_id or f"{_normalise_name(org.get('name') or '')}|{_normalise_domain(org.get('website_url') or org.get('primary_domain') or '')}"
            if marker in seen:
                continue
            seen.add(marker)
            hits.append(org)
    return hits


def _apollo_people_candidates(apollo, company: str, domain: str, org: dict[str, Any] | None) -> list[dict[str, Any]]:
    org_name = (org or {}).get("name") or company
    org_domain = _normalise_domain((org or {}).get("website_url") or (org or {}).get("primary_domain") or domain)
    searches = [
        {"organization_name": org_name, "per_page": 25},
        {"organization_name": org_name, "domain": org_domain, "per_page": 25} if org_domain else None,
        {"organization_name": company, "per_page": 25} if company and company != org_name else None,
        {"domain": org_domain, "per_page": 25} if org_domain else None,
        {"organization_name": org_name, "titles": PRIORITY_TITLES, "per_page": 25},
    ]
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for params in searches:
        if not params:
            continue
        result = apollo.search_people(**params)
        for person in result.get("people") or []:
            person_id = str(person.get("id") or "")
            marker = person_id or f"{_normalise_name(person.get('name') or '')}|{_normalise_name(person.get('title') or '')}"
            if marker in seen:
                continue
            seen.add(marker)
            hits.append(person)
        if hits:
            break
    return _sort_people(hits)


def _find_org_dupes(client: PipedriveClient, org_name: str, website: str) -> list[dict[str, Any]]:
    terms = [org_name]
    domain = _normalise_domain(website)
    if domain:
        terms.append(domain)
    hits: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for term in terms:
        for result in client.search_organisations(term, limit=10):
            item = result.get("item") or {}
            item_id = item.get("id")
            if not item_id or item_id in seen_ids:
                continue
            haystacks = [
                (item.get("name") or "").lower(),
                (item.get("address") or "").lower(),
                " ".join(str(v).lower() for v in (item.get("custom_fields") or [])),
            ]
            if org_name.lower() in haystacks[0] or any(domain and domain in hay for hay in haystacks):
                hits.append(result)
                seen_ids.add(item_id)
    return hits


def _pick_owner_id(client: PipedriveClient, owner_name: str | None) -> int | None:
    if not owner_name:
        return None
    target = owner_name.strip().lower()
    for user in client.get_users():
        name = (user.get("name") or "").strip().lower()
        if target in name or name in target:
            return user.get("id")
    return None


def _find_lead_dupe(client: PipedriveClient, organisation: dict[str, Any], source_company: str) -> dict[str, Any] | None:
    org_id = organisation.get("id")
    org_name = organisation.get("name") or source_company
    norm_org = _normalise_name(org_name)
    norm_source = _normalise_name(source_company)
    for lead in client.get_all_leads(limit=500):
        if lead.get("is_archived"):
            continue
        lead_org_id = lead.get("organization_id") or lead.get("related_org_id")
        title_norm = _normalise_name(lead.get("title") or "")
        if org_id and str(lead_org_id) == str(org_id):
            return lead
        if norm_org and norm_org in title_norm:
            return lead
        if norm_source and norm_source in title_norm:
            return lead
    return None


def _apollo_person_detail(api_key: str, person_id: str) -> dict[str, Any]:
    try:
        response = requests.get(
            f"https://api.apollo.io/api/v1/people/{person_id}",
            headers={"X-Api-Key": api_key},
            timeout=12,
        )
    except requests.Timeout as exc:
        raise ApolloTransientError(message=f"Apollo person detail timed out for person {person_id}") from exc
    except requests.RequestException as exc:
        raise ApolloTransientError(message=f"Apollo person detail failed for person {person_id}: {exc}") from exc
    if response.status_code == 429:
        raise ApolloRateLimitError(
            message=f"429 Too Many Requests for url: {response.url}",
            retry_after_seconds=_apollo_retry_after_seconds_from_response(response),
        )
    response.raise_for_status()
    return response.json().get("person") or {}


def _apollo_resolve_candidate(apollo, queue_id: str | None, row: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    company = (row.get("Company Name") or "").strip()
    domain = _normalise_domain(row.get("Website") or "")
    queue_item = next((item for item in _load_queue_items() if item.get("queue_id") == queue_id), {}) if queue_id else {}
    cached_best_person = queue_item.get("apollo_best_person") or {}
    cached_best_org = queue_item.get("apollo_resolved_org") or {}
    if cached_best_person.get("email") and _cache_is_fresh(queue_item.get("apollo_cached_at")):
        return cached_best_person, cached_best_org
    try:
        org_candidates = _apollo_org_candidates(apollo, company, domain)
        org = org_candidates[0] if org_candidates else {}
    except ApolloRateLimitError as exc:
        _mark_apollo_retry_later(queue_id, str(exc), exc.retry_after_seconds)
        return None
    except ApolloTransientError as exc:
        _mark_apollo_transient_retry_later(queue_id, str(exc))
        return None

    try:
        people = _apollo_people_candidates(apollo, company, domain, org)
    except ApolloRateLimitError as exc:
        _mark_apollo_retry_later(queue_id, str(exc), exc.retry_after_seconds)
        return None
    except ApolloTransientError as exc:
        _mark_apollo_transient_retry_later(queue_id, str(exc))
        return None

    _update_queue_item(
        queue_id,
        apollo_cached_at=datetime.now(timezone.utc).isoformat(),
        apollo_resolved_org={
            "id": org.get("id"),
            "name": org.get("name"),
            "website_url": org.get("website_url"),
            "primary_domain": org.get("primary_domain"),
            "raw_address": org.get("raw_address"),
            "phone": org.get("phone"),
        } if org else {},
        apollo_people_count=len(people),
        apollo_unlocked_email_count=0,
        apollo_top_people=[
            {
                "id": person.get("id"),
                "name": person.get("name"),
                "title": person.get("title") or person.get("job_title"),
                "email": person.get("email"),
                "linkedin_url": person.get("linkedin_url"),
            }
            for person in people[:5]
        ],
    )

    if not people:
        _mark_queue_no_match(queue_id, "no_people_match", f"Apollo found no people for {company}", retry_days=APOLLO_NO_MATCH_RETRY_DAYS)
        return None

    for person in people:
        try:
            detail = _apollo_person_detail(apollo.api_key, person["id"])
        except ApolloRateLimitError as exc:
            _mark_apollo_retry_later(queue_id, str(exc), exc.retry_after_seconds)
            return None
        except ApolloTransientError as exc:
            _mark_apollo_transient_retry_later(queue_id, str(exc))
            return None
        detail_org = detail.get("organization") or org
        detail_domain = _normalise_domain(detail_org.get("website_url") or detail_org.get("primary_domain") or domain)
        email = (detail.get("email") or "").strip()
        if (not email) or ("email_not_unlocked" in email):
            try:
                matched = apollo.match_person(
                    name=detail.get("name") or person.get("name") or "",
                    organization_name=detail_org.get("name") or company,
                    domain=detail_domain,
                    linkedin_url=detail.get("linkedin_url") or person.get("linkedin_url") or "",
                ).get("person") or {}
            except ApolloRateLimitError as exc:
                _mark_apollo_retry_later(queue_id, str(exc), exc.retry_after_seconds)
                return None
            except ApolloTransientError as exc:
                _mark_apollo_transient_retry_later(queue_id, str(exc))
                return None
            if matched:
                detail = matched
                detail_org = detail.get("organization") or detail_org
                email = (detail.get("email") or "").strip()
        if email and "email_not_unlocked" not in email:
            _update_queue_item(
                queue_id,
                apollo_status="matched",
                apollo_best_person={
                    "id": detail.get("id"),
                    "name": detail.get("name"),
                    "title": detail.get("title"),
                    "email": detail.get("email"),
                    "linkedin_url": detail.get("linkedin_url"),
                    "organization": detail.get("organization") or detail_org,
                },
                apollo_resolved_org={
                    "id": detail_org.get("id"),
                    "name": detail_org.get("name"),
                    "website_url": detail_org.get("website_url"),
                    "primary_domain": detail_org.get("primary_domain"),
                    "raw_address": detail_org.get("raw_address"),
                    "phone": detail_org.get("phone"),
                },
                apollo_unlocked_email_count=1,
                apollo_last_error=None,
                apollo_retry_after=None,
                next_step="ready_for_creation",
            )
            return detail, detail_org

    _mark_queue_no_match(queue_id, "no_email_after_match", f"Apollo found contacts for {company} but no unlocked email", retry_days=APOLLO_NO_MATCH_RETRY_DAYS)
    return None


def _candidate_from_sheet(client: PipedriveClient, apollo_api_key: str) -> dict[str, Any]:
    apollo = load_apollo_client()
    ignore_rows = {int(value) for value in source_ingest_config().get("ignore_row_numbers", [])}
    queue_candidates: list[tuple[int | None, dict[str, Any], dict[str, str]]] = []
    for item in _load_queue_items():
        if item.get("status") != "queued":
            continue
        if not _queue_item_is_ready(item):
            continue
        row = dict(item.get("raw") or {})
        row.setdefault("Company Name", item.get("company") or "")
        row.setdefault("Website", item.get("website") or "")
        row.setdefault("Address", item.get("source_address") or "")
        queue_candidates.append((None, item, row))
    row_iterable = queue_candidates or [(index, {}, row) for index, row in enumerate(_load_rows(), start=1)]

    for row_number, queue_item, row in row_iterable:
        if row_number in ignore_rows:
            continue
        company = (row.get("Company Name") or "").strip()
        if not company:
            continue
        bad_target_reason = _is_bad_apollo_target(company, row.get("Website") or "")
        if bad_target_reason:
            _update_queue_item(queue_item.get("queue_id"), status="invalid_apollo_target", next_step="skip_invalid_target", excluded_reason=bad_target_reason)
            continue
        if is_customer(company=company, website=row.get("Website") or ""):
            _update_queue_item(queue_item.get("queue_id"), status="excluded_customer", next_step="skip_existing_customer", excluded_reason="Existing customer from won deals list")
            continue

        resolved = _apollo_resolve_candidate(apollo, queue_item.get("queue_id"), row)
        if not resolved:
            continue
        detail, org = resolved
        city, state, country = _address_parts(org.get("raw_address") or row.get("Address") or "")
        owner_name = assign_owner(country, state)
        owner_id = _pick_owner_id(client, owner_name)
        if not owner_id:
            _mark_queue_no_match(queue_item.get("queue_id"), "no_routable_owner", f"No routable owner for {company}")
            continue
        org_name = (org.get("name") or company).strip()
        email = (detail.get("email") or "").strip()
        person_name = (detail.get("name") or "").strip()
        org_dupes = _find_org_dupes(client, org_name, org.get("website_url") or row.get("Website") or "")
        if is_customer(organisation_id=(org_dupes[0].get("item") or {}).get("id") if org_dupes else None, company=org_name, website=org.get("website_url") or row.get("Website") or ""):
            _update_queue_item(queue_item.get("queue_id"), status="excluded_customer", next_step="skip_existing_customer", excluded_reason="Existing customer from won deals list")
            continue
        person_dupes = client.search_persons(email or person_name, limit=5) if (email or person_name) else []
        if person_dupes:
            _update_queue_item(queue_item.get("queue_id"), status="duplicate_person", next_step="skip_duplicate_person")
            continue
        queue_snapshot = next((item for item in _load_queue_items() if item.get("queue_id") == queue_item.get("queue_id")), queue_item)
        return {
            "queue_id": queue_item.get("queue_id") if queue_item else None,
            "sheet_row": row,
            "apollo_person": detail,
            "apollo_org": org,
            "apollo_people_count": queue_snapshot.get("apollo_people_count"),
            "apollo_unlocked_email_count": queue_snapshot.get("apollo_unlocked_email_count"),
            "assigned_agent": assign_agent(country, state),
            "owner_name": owner_name,
            "owner_id": owner_id,
            "city": city,
            "state": state,
            "country": country,
            "org_dupes": org_dupes,
            "person_dupes": person_dupes,
        }
    raise CandidateSkip("No lead candidate ready after Apollo matching and duplicate checks")


def _score_candidate(row: dict[str, str], apollo_org: dict[str, Any], apollo_person: dict[str, Any]) -> tuple[int, list[str], dict[str, Any]]:
    criteria = qualification_criteria()
    score = criteria["base_score"]
    reasons: list[str] = []
    site_review = {"homepage_url": apollo_org.get("website_url") or row.get("Website"), "homepage_text": "", "inspected_pages": []}
    try:
        target_url = apollo_org.get("website_url") or row.get("Website") or ""
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(review_site, target_url)
            site_review = future.result(timeout=SITE_REVIEW_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        site_review = {
            "homepage_url": apollo_org.get("website_url") or row.get("Website"),
            "homepage_text": "",
            "inspected_pages": [],
            "error": f"site review timeout after {SITE_REVIEW_TIMEOUT_SECONDS}s",
        }
    except Exception:
        pass
    evidence_parts = [
        row.get("Description") or "",
        row.get("Capabilities") or "",
        row.get("Certifications") or "",
        apollo_org.get("short_description") or "",
        " ".join(apollo_org.get("keywords") or []),
        apollo_org.get("industry") or "",
        apollo_org.get("website_url") or "",
        site_review.get("homepage_text") or "",
        " ".join((page.get("text") or "") for page in site_review.get("inspected_pages") or []),
        " ".join((page.get("label") or "") for page in site_review.get("inspected_pages") or []),
    ]
    evidence = " ".join(evidence_parts).lower()

    def has_any(*tokens: str) -> bool:
        return any(token.lower() in evidence for token in tokens)

    rules = {rule["key"]: rule for rule in criteria.get("rules", []) if rule.get("key")}

    if has_any("cnc machining", "cnc milling", "cnc turning", "precision machining", "machine shop"):
        score += rules["cnc_machining"]["points"]
        reasons.append("CNC machining evidence found")
    if has_any("request a quote", "quote", "rfq"):
        score += rules["quote_rfq"]["points"]
        reasons.append("quote or RFQ evidence found")
    if has_any("prototyp", "contract manufacturing", "build to print", "rapid turnaround"):
        score += rules["prototype_contract_build_to_print"]["points"]
        reasons.append("prototype or contract manufacturing evidence found")
    if has_any("5-axis", "5 axis"):
        score += rules["five_axis"]["points"]
        reasons.append("5-axis evidence found")
    if has_any("aerospace", "defence", "defense"):
        score += rules["aerospace_defence"]["points"]
        reasons.append("aerospace or defence evidence found")
    if has_any("itar"):
        score += rules["itar"]["points"]
        reasons.append("ITAR evidence found")
    if has_any("motorsport", "formula 1", "f1"):
        score += rules["motorsport_f1"]["points"]
        reasons.append("motorsport evidence found")
    if has_any("capabilities", "equipment"):
        score += rules["capabilities_equipment_page"]["points"]
        reasons.append("capabilities or equipment evidence found")
    if has_any("dmg mori", "mazak", "matsuura", "okuma", "hermle", "haas"):
        score += rules["target_machine_brands"]["points"]
        reasons.append("target machine-brand evidence found")
    if has_any("3d printing", "additive manufacturing"):
        score += rules["3d_printing"]["points"]
        reasons.append("3D printing evidence found")
    if has_any("medical", "iso 13485"):
        score += rules["medical_iso13485"]["points"]
        reasons.append("medical or ISO 13485 evidence found")
    if has_any("tight tolerance", "tight tolerances", "high precision", "complex parts", "complex component"):
        score += rules["tight_tolerance_precision_complex_parts"]["points"]
        reasons.append("tight tolerance or complex-part evidence found")
    if has_any("repair", "directory", "business directory", "automotive machine shops.cmac.ws"):
        score += rules["repair_directory_false_positive"]["points"]
        reasons.append("repair-shop or directory-style evidence found")
    if has_any("sheet metal", "fabrication", "welding", "bending", "stamping"):
        score += rules["sheet_metal_fabrication"]["points"]
        reasons.append("sheet metal or fabrication-heavy evidence found")
    if has_any("high volume", "serial production"):
        score += rules["high_volume_serial_production"]["points"]
        reasons.append("high-volume production evidence found")
    if has_any("edm", "wire edm", "sinker edm"):
        score += rules["edm"]["points"]
        reasons.append("EDM evidence found")

    score = max(criteria.get("cap", {}).get("min", 0), min(criteria.get("cap", {}).get("max", 100), score))
    return score, reasons, site_review


def run() -> dict[str, Any]:
    build_customer_registry()
    cfg = load_config()
    client = PipedriveClient(cfg.api_base, cfg.api_key)
    candidate = _candidate_from_sheet(client, load_apollo_client().api_key)
    row = candidate["sheet_row"]
    apollo_person = candidate["apollo_person"]
    apollo_org = candidate["apollo_org"]
    score, reasons, site_review = _score_candidate(row, apollo_org, apollo_person)
    if is_customer(company=row.get("Company Name") or apollo_org.get("name") or "", website=apollo_org.get("website_url") or row.get("Website") or ""):
        _update_queue_item(candidate.get("queue_id"), status="excluded_customer", next_step="skip_existing_customer", excluded_reason="Existing customer from won deals list")
        raise RuntimeError(f"Lead skipped: existing customer {row.get('Company Name') or apollo_org.get('name')}")
    min_score = ((automation_config().get("batch") or {}).get("min_score") or 0)
    if score < min_score:
        _update_queue_item(candidate.get("queue_id"), status="scored_below_threshold", next_step="manual_review", last_score=score)
        raise RuntimeError(f"Lead skipped: score {score} below threshold {min_score} for {row.get('Company Name')}")
    org_dupes = candidate.get("org_dupes") or []
    existing_org = ((org_dupes[0] or {}).get("item") or {}) if org_dupes else None

    if existing_org:
        organisation = existing_org
    else:
        org_payload = {
            "name": apollo_org.get("name") or row.get("Company Name"),
            "owner_id": candidate["owner_id"],
            "address": apollo_org.get("raw_address") or row.get("Address"),
            HOMEPAGE_FIELD_KEY: (apollo_org.get("website_url") or row.get("Website") or "").replace("http://", "https://"),
        }
        organisation = client.create_organisation(org_payload)

    person_payload = {
        "name": apollo_person.get("name"),
        "owner_id": candidate["owner_id"],
        "org_id": organisation.get("id"),
        "email": apollo_person.get("email") if apollo_person.get("email") and "email_not_unlocked" not in apollo_person.get("email", "") else None,
        "phone": (apollo_org.get("phone") or ""),
    }
    person_payload = {k: v for k, v in person_payload.items() if v not in {None, ""}}
    person = client.create_person(person_payload)

    lead_title = f"{organisation.get('name')} - {apollo_person.get('title') or 'Apollo lead'}"
    lead_payload = {
        "title": lead_title,
        "owner_id": candidate["owner_id"],
        "person_id": person.get("id"),
        "organization_id": organisation.get("id"),
        STATE_FIELD_KEY: _state_option_id(candidate["state"]),
        "label_ids": [CNC_LABEL_ID],
    }
    lead_payload = {k: v for k, v in lead_payload.items() if v is not None and v != ""}
    existing_lead = _find_lead_dupe(client, organisation, row.get("Company Name") or organisation.get("name") or "")
    if existing_lead:
        _update_queue_item(candidate.get("queue_id"), status="duplicate_lead", next_step="skip_duplicate", existing_lead_id=existing_lead.get("id"))
        raise RuntimeError(f"Lead duplicate detected for organisation {organisation.get('name')}, existing lead {existing_lead.get('id')}")
    lead = client.create_lead(lead_payload)

    note_lines = [
        f"Qualification score: {score}/100",
        f"State: {candidate['state']}",
        "Justification:",
    ]
    note_lines.extend(f"- {reason}" for reason in reasons)
    note = client.create_note({
        "content": "\n".join(note_lines),
        "lead_id": lead.get("id"),
        "person_id": person.get("id"),
        "org_id": organisation.get("id"),
    })
    activity = client.create_activity({
        "subject": "Call new lead",
        "type": "call",
        "lead_id": lead.get("id"),
        "person_id": person.get("id"),
        "org_id": organisation.get("id"),
        "user_id": candidate["owner_id"],
        "due_date": str(date.today() + timedelta(days=1)),
    })

    result = {
        "created_organisation": organisation,
        "created_person": person,
        "created_lead": lead,
        "created_note": note,
        "created_activity": activity,
        "score": score,
        "score_reasons": reasons,
        "owner_name": candidate["owner_name"],
        "assigned_agent": candidate.get("assigned_agent"),
        "source_company": row.get("Company Name"),
        "used_existing_org": bool(existing_org),
        "site_review": site_review,
        "apollo_people_count": candidate.get("apollo_people_count"),
        "apollo_unlocked_email_count": candidate.get("apollo_unlocked_email_count"),
        "apollo_resolved_org_name": (candidate.get("apollo_org") or {}).get("name"),
    }
    _update_queue_item(
        candidate.get("queue_id"),
        status="created",
        next_step="done",
        created_lead_id=lead.get("id"),
        created_person_id=person.get("id"),
        created_org_id=organisation.get("id"),
        assigned_owner=candidate.get("owner_name"),
        assigned_agent=candidate.get("assigned_agent"),
        last_score=score,
        apollo_status="created",
    )
    target = ROOT / "output" / "bdr-full-flow-result.json"
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
