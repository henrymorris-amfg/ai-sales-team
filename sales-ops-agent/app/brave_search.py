from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
SECRETS_FILE = WORKSPACE / ".secrets" / "brave.env"


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


_load_env_file(SECRETS_FILE)


def brave_search(query: str, count: int = 5) -> dict:
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Missing BRAVE_SEARCH_API_KEY")

    params = {"q": query, "count": count}
    url = f"https://api.search.brave.com/res/v1/web/search?{urlencode(params)}"
    response = requests.get(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m app.brave_search '<query>' [count]")
    query = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    result = brave_search(query, count=count)

    web = (result.get("web") or {}).get("results") or []
    trimmed = [
        {
            "title": item.get("title"),
            "url": item.get("url"),
            "description": item.get("description"),
        }
        for item in web
    ]
    print(json.dumps(trimmed, indent=2))


if __name__ == "__main__":
    main()
