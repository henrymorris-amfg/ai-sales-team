from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
SECRETS_FILE = WORKSPACE / ".secrets" / "pipedrive.env"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(ROOT / ".env")
_load_env_file(SECRETS_FILE)


@dataclass
class Config:
    company_domain: str
    api_base: str
    api_key: str
    action_mode: str = "audit_only"
    demo_done_stage_name: str = "Demo Done"


def load_config() -> Config:
    company_domain = os.getenv("PIPEDRIVE_COMPANY_DOMAIN", "").strip()
    api_base = os.getenv("PIPEDRIVE_API_BASE", "").strip()
    api_key = os.getenv("PIPEDRIVE_API_KEY", "").strip()

    if not api_base and company_domain:
        api_base = f"https://{company_domain}.pipedrive.com/api/v1"

    missing = [
        name for name, value in {
            "PIPEDRIVE_API_BASE": api_base,
            "PIPEDRIVE_API_KEY": api_key,
        }.items() if not value
    ]
    if missing:
        raise ValueError(f"Missing required config: {', '.join(missing)}")

    return Config(
        company_domain=company_domain,
        api_base=api_base,
        api_key=api_key,
        action_mode=os.getenv("ACTION_MODE", "audit_only").strip() or "audit_only",
        demo_done_stage_name=os.getenv("DEMO_DONE_STAGE_NAME", "Demo Done").strip() or "Demo Done",
    )
