from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .apollo_client import ApolloRateLimitError
from .bdr_full_flow import automation_config, run, source_ingest_config


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


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def run_batch(limit: int | None = None) -> dict:
    config = automation_config()
    batch_cfg = config.get("batch") or {}
    safety = config.get("safety") or {}
    rate_limit_cfg = config.get("rate_limit") or {}
    default_cooldown_minutes = int(rate_limit_cfg.get("apollo_cooldown_minutes", 180))
    max_cooldown_minutes = int(rate_limit_cfg.get("apollo_max_cooldown_minutes", 720))
    now = datetime.now(timezone.utc)
    state = _load_json(
        STATE,
        {
            "paused": False,
            "pause_reason": None,
            "consecutive_error_runs": 0,
            "consecutive_duplicate_runs": 0,
            "consecutive_apollo_rate_limits": 0,
            "apollo_retry_after": None,
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

    apollo_retry_after = _parse_iso_datetime(state.get("apollo_retry_after"))
    if apollo_retry_after and now < apollo_retry_after:
        wait_minutes = max(1, int((apollo_retry_after - now).total_seconds() // 60))
        payload = {
            "created": 0,
            "results": [],
            "errors": [],
            "skips": [f"Apollo cooldown active until {apollo_retry_after.isoformat()} ({wait_minutes} min remaining)"],
            "source": source_ingest_config(),
            "paused": False,
            "pause_reason": f"Apollo cooldown active until {apollo_retry_after.isoformat()}",
            "ran_at": now.isoformat(),
        }
        _save_json(OUTPUT, payload)
        history = _load_json(HISTORY, [])
        history.insert(0, payload)
        _save_json(HISTORY, history[:50])
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
            cooldown_seconds = exc.retry_after_seconds or (default_cooldown_minutes * 60)
            next_retry = now + timedelta(seconds=min(cooldown_seconds, max_cooldown_minutes * 60))
            state["consecutive_apollo_rate_limits"] = int(state.get("consecutive_apollo_rate_limits", 0)) + 1
            state["apollo_retry_after"] = next_retry.isoformat()
            errors.append(f"Transient Apollo rate limit: {exc}")
            break
        except Exception as exc:
            message = str(exc)
            if "429" in message or "too many requests" in message.lower():
                state["consecutive_apollo_rate_limits"] = int(state.get("consecutive_apollo_rate_limits", 0)) + 1
                next_retry = now + timedelta(minutes=default_cooldown_minutes)
                state["apollo_retry_after"] = next_retry.isoformat()
                errors.append(f"Transient Apollo rate limit: {message}")
                break
            if message.startswith("Lead skipped:") or "duplicate" in message.lower():
                skips.append(message)
                continue
            errors.append(message)
            break

    transient_rate_limit = bool(errors and all("Transient Apollo rate limit:" in item for item in errors))

    if errors and not transient_rate_limit:
        state["consecutive_error_runs"] = int(state.get("consecutive_error_runs", 0)) + 1
    else:
        state["consecutive_error_runs"] = 0

    if not transient_rate_limit:
        state["consecutive_apollo_rate_limits"] = 0
        state["apollo_retry_after"] = None

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
        state["pause_reason"] = "Transient Apollo rate limit, will retry next run" if transient_rate_limit else None

    payload = {
        "created": len(results),
        "results": results,
        "errors": errors,
        "skips": skips,
        "source": source_ingest_config(),
        "paused": state.get("paused", False),
        "pause_reason": state.get("pause_reason"),
        "apollo_retry_after": state.get("apollo_retry_after"),
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
