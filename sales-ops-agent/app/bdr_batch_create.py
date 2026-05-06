from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .apollo_client import ApolloRateLimitError
from .bdr_full_flow import CandidateSkip, automation_config, run, source_ingest_config


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "bdr-batch-results.json"
HISTORY = ROOT / "output" / "bdr-run-history.json"
STATE = ROOT / "output" / "bdr-run-state.json"


def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_batch(limit: int | None = None) -> dict:
    config = automation_config()
    batch_cfg = config.get("batch") or {}
    safety = config.get("safety") or {}
    state = _load_json(
        STATE,
        {
            "paused": False,
            "pause_reason": None,
            "consecutive_error_runs": 0,
            "consecutive_duplicate_runs": 0,
        },
    )

    if state.get("paused"):
        payload = {
            "created": 0,
            "results": [],
            "errors": [state.get("pause_reason") or "AUTO_PAUSED"],
            "skips": [],
            "source": source_ingest_config(),
            "paused": True,
        }
        _save_json(OUTPUT, payload)
        return payload

    run_limit = limit or batch_cfg.get("limit") or 3
    results = []
    errors = []
    skips = []
    for _ in range(run_limit):
        try:
            result = run()
            results.append(
                {
                    "lead_id": (result.get("created_lead") or {}).get("id"),
                    "lead_title": (result.get("created_lead") or {}).get("title"),
                    "assigned_agent": result.get("assigned_agent"),
                    "owner_name": result.get("owner_name"),
                    "score": result.get("score"),
                    "state": ((result.get("created_note") or {}).get("content") or "").split("State: ")[-1].split("<br />")[0] if result.get("created_note") else None,
                    "source_company": result.get("source_company"),
                }
            )
        except ApolloRateLimitError as exc:
            skips.append(f"Apollo rate limited current lead and moved on: {exc}")
            continue
        except CandidateSkip as exc:
            skips.append(str(exc))
            continue
        except Exception as exc:
            message = str(exc)
            if "429" in message or "too many requests" in message.lower():
                skips.append(f"Apollo rate limited current lead and moved on: {message}")
                continue
            if message.startswith("Lead skipped:") or "duplicate" in message.lower():
                skips.append(message)
                continue
            errors.append(message)
            break

    if errors:
        state["consecutive_error_runs"] = int(state.get("consecutive_error_runs", 0)) + 1
    else:
        state["consecutive_error_runs"] = 0

    if skips and all("duplicate" in item.lower() for item in skips):
        state["consecutive_duplicate_runs"] = int(state.get("consecutive_duplicate_runs", 0)) + 1
    else:
        state["consecutive_duplicate_runs"] = 0

    if state["consecutive_error_runs"] >= int(safety.get("pause_after_consecutive_error_runs", 9999)):
        state["paused"] = True
        state["pause_reason"] = f"{safety.get('pause_reason_prefix', 'AUTO_PAUSED')}: too many consecutive error runs"
    elif state["consecutive_duplicate_runs"] >= int(safety.get("pause_after_consecutive_duplicate_runs", 9999)):
        state["paused"] = True
        state["pause_reason"] = f"{safety.get('pause_reason_prefix', 'AUTO_PAUSED')}: too many consecutive duplicate-only runs"
    else:
        state["paused"] = False
        state["pause_reason"] = None

    payload = {
        "created": len(results),
        "results": results,
        "errors": errors,
        "skips": skips,
        "source": source_ingest_config(),
        "paused": state.get("paused", False),
        "pause_reason": state.get("pause_reason"),
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_json(OUTPUT, payload)
    _save_json(STATE, state)

    history = _load_json(HISTORY, [])
    history.insert(0, payload)
    _save_json(HISTORY, history[:50])
    return payload


if __name__ == "__main__":
    print(json.dumps(run_batch(), indent=2))
