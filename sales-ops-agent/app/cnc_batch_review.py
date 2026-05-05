from __future__ import annotations

import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import load_config
from .customer_registry import build_customer_registry, is_customer
from .lead_review import _extract_website_candidates, _fetch_text, _is_cnc_lead
from .pipedrive_client import PipedriveClient
from .website_review import review_text


DEFAULT_BATCH_SIZE = 200
DEFAULT_SEED = 42
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"


def build_random_batch_review(batch_size: int = DEFAULT_BATCH_SIZE, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    build_customer_registry()
    config = load_config()
    client = PipedriveClient(config.api_base, config.api_key)
    leads = client.get_all_leads(limit=500)
    cnc_leads = [
        lead for lead in leads
        if _is_cnc_lead(lead) and not is_customer(
            organisation_id=lead.get("organization_id"),
            person_id=lead.get("person_id"),
            company=(lead.get("title") or "").split(" - ")[0],
        )
    ]

    rng = random.Random(seed)
    sample = list(cnc_leads)
    rng.shuffle(sample)
    sample = sample[: min(batch_size, len(sample))]

    org_cache: dict[int, dict[str, Any]] = {}
    person_cache: dict[int, dict[str, Any]] = {}
    fetch_cache: dict[str, str] = {}
    results: list[dict[str, Any]] = []

    for lead in sample:
        title = lead.get("title") or lead.get("name") or "Untitled lead"
        candidates = _extract_website_candidates(lead, client, org_cache, person_cache)
        if not candidates:
            results.append({
                "lead_id": lead.get("id"),
                "title": title,
                "recommendation": "needs_review",
                "score": 0,
                "confidence": 0.0,
                "website": None,
                "website_candidates": [],
                "reason": "No website found on lead, organisation, or person data.",
                "fit_signals": [],
                "disqualify_signals": [],
                "conflict_flag": False,
            })
            continue

        last_error = None
        reviewed = False
        for candidate in candidates[:2]:
            try:
                text = fetch_cache.get(candidate)
                if text is None:
                    text = _fetch_text(candidate)
                    fetch_cache[candidate] = text
                review = review_text(text)
                results.append({
                    "lead_id": lead.get("id"),
                    "title": title,
                    "recommendation": review.recommendation,
                    "score": review.score,
                    "confidence": review.confidence,
                    "website": candidate,
                    "website_candidates": candidates,
                    "reason": None,
                    "fit_signals": review.fit_signals,
                    "disqualify_signals": review.disqualify_signals,
                    "conflict_flag": review.conflict_flag,
                })
                reviewed = True
                break
            except Exception as exc:
                last_error = str(exc)

        if not reviewed:
            results.append({
                "lead_id": lead.get("id"),
                "title": title,
                "recommendation": "needs_review",
                "score": 0,
                "confidence": 0.0,
                "website": candidates[0] if candidates else None,
                "website_candidates": candidates,
                "reason": f"Website fetch failed: {last_error}",
                "fit_signals": [],
                "disqualify_signals": [],
                "conflict_flag": False,
            })

    recommendation_counts = Counter(item["recommendation"] for item in results)
    score_bands = {
        "80_100": sum(1 for item in results if item["score"] >= 80),
        "60_79": sum(1 for item in results if 60 <= item["score"] <= 79),
        "21_59": sum(1 for item in results if 21 <= item["score"] <= 59),
        "0_20": sum(1 for item in results if item["score"] <= 20),
    }
    archive_candidates = sorted(
        [item for item in results if item["recommendation"] == "archive_disqualified"],
        key=lambda item: (item["score"], -item["confidence"]),
    )
    good_fits = sorted(
        [item for item in results if item["score"] >= 80],
        key=lambda item: (-item["score"], -item["confidence"]),
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_type": "random_cnc_leads",
        "batch_size": len(results),
        "seed": seed,
        "total_cnc_leads_available": len(cnc_leads),
        "recommendation_counts": dict(recommendation_counts),
        "score_bands": score_bands,
        "archive_candidates": archive_candidates,
        "good_fits": good_fits,
        "results": results,
    }
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# CNC Lead Review Batch Report")
    lines.append("")
    lines.append(f"- Generated: {report['generated_at']}")
    lines.append(f"- Sample type: random CNC leads")
    lines.append(f"- Random seed: {report['seed']}")
    lines.append(f"- Leads reviewed: {report['batch_size']}")
    lines.append(f"- Total CNC-labelled leads available: {report['total_cnc_leads_available']}")
    lines.append("")
    lines.append("## Score bands")
    lines.append(f"- 80 to 100: {report['score_bands']['80_100']}")
    lines.append(f"- 60 to 79: {report['score_bands']['60_79']}")
    lines.append(f"- 21 to 59: {report['score_bands']['21_59']}")
    lines.append(f"- 0 to 20: {report['score_bands']['0_20']}")
    lines.append("")
    lines.append("## Recommendation counts")
    for name, count in sorted(report["recommendation_counts"].items()):
        lines.append(f"- {name}: {count}")
    lines.append("")
    lines.append("## Top archive candidates")
    if report["archive_candidates"]:
        for item in report["archive_candidates"][:15]:
            reason_bits = item.get("disqualify_signals") or ([item.get("reason")] if item.get("reason") else [])
            reason = ", ".join(str(bit) for bit in reason_bits[:4] if bit)
            lines.append(f"- {item['title']} | score {item['score']} | confidence {item['confidence']} | {reason}")
    else:
        lines.append("- None in this batch")
    lines.append("")
    lines.append("## Top very good fits")
    if report["good_fits"]:
        for item in report["good_fits"][:15]:
            reason = ", ".join(item.get("fit_signals")[:4])
            lines.append(f"- {item['title']} | score {item['score']} | confidence {item['confidence']} | {reason}")
    else:
        lines.append("- None in this batch")
    return "\n".join(lines) + "\n"


def main() -> None:
    report = build_random_batch_review()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "cnc-random-review-200.json"
    md_path = OUTPUT_DIR / "cnc-random-review-200.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
