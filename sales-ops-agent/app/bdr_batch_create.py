from __future__ import annotations

import json
from pathlib import Path

from .bdr_full_flow import run


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "bdr-batch-results.json"


def run_batch(limit: int = 3) -> dict:
    results = []
    errors = []
    for _ in range(limit):
        try:
            result = run()
            results.append(
                {
                    "lead_id": (result.get("created_lead") or {}).get("id"),
                    "lead_title": (result.get("created_lead") or {}).get("title"),
                    "owner_name": result.get("owner_name"),
                    "score": result.get("score"),
                    "state": ((result.get("created_note") or {}).get("content") or "").split("State: ")[-1].split("<br />")[0] if result.get("created_note") else None,
                    "source_company": result.get("source_company"),
                }
            )
        except Exception as exc:
            errors.append(str(exc))
            break
    payload = {"created": len(results), "results": results, "errors": errors}
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_batch(), indent=2))
