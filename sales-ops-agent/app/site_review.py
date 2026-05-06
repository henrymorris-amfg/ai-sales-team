from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
import os

import requests


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "site-review.json"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; OpenClaw/1.0)"}
TARGET_LINK_WORDS = ["capabilities", "equipment", "quote", "rfq", "request a quote"]
REQUEST_TIMEOUT_SECONDS = max(3, int((os.getenv("SITE_REVIEW_REQUEST_TIMEOUT_SECONDS", "8") or "8").strip()))
MAX_LINKS_TO_INSPECT = max(1, int((os.getenv("SITE_REVIEW_MAX_LINKS", "2") or "2").strip()))


def _fetch(url: str) -> tuple[str, str]:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.url, response.text


def _clean_text(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _extract_links(base_url: str, html: str) -> list[dict[str, str]]:
    links = []
    for href, label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, flags=re.I | re.S):
        text = _clean_text(label).lower()
        abs_url = urljoin(base_url, href)
        if any(word in text for word in TARGET_LINK_WORDS):
            links.append({"label": text, "url": abs_url})
    deduped = []
    seen = set()
    for link in links:
        key = link["url"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(link)
    return deduped[:8]


def review_site(url: str) -> dict:
    base_url, homepage_html = _fetch(url if url.startswith("http") else f"https://{url}")
    homepage_text = _clean_text(homepage_html)
    links = _extract_links(base_url, homepage_html)
    pages = []
    for link in links[:MAX_LINKS_TO_INSPECT]:
        try:
            final_url, html = _fetch(link["url"])
            pages.append({
                "label": link["label"],
                "url": final_url,
                "text": _clean_text(html)[:12000],
            })
        except Exception as exc:
            pages.append({"label": link["label"], "url": link["url"], "error": str(exc)})
    payload = {
        "homepage_url": base_url,
        "homepage_text": homepage_text[:15000],
        "candidate_pages": links,
        "inspected_pages": pages,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "https://www.qtstamping.com"
    print(json.dumps(review_site(target), indent=2))
