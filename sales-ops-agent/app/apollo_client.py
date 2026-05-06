from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from . import config as _config  # noqa: F401  Ensures local secret env files are loaded.


@dataclass
class ApolloRateLimitError(RuntimeError):
    message: str
    retry_after_seconds: int | None = None

    def __str__(self) -> str:
        return self.message


@dataclass
class ApolloTransientError(RuntimeError):
    message: str
    retry_after_seconds: int | None = None

    def __str__(self) -> str:
        return self.message


class ApolloClient:
    def __init__(self, api_key: str, api_base: str = "https://api.apollo.io/api/v1", timeout_seconds: int = 12) -> None:
        self.api_key = api_key.strip()
        self.api_base = api_base.rstrip("/")
        self.timeout_seconds = max(3, int(timeout_seconds))
        if not self.api_key:
            raise ValueError("Missing APOLLO_API_KEY")

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{self.api_base}{path}",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": self.api_key,
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise ApolloTransientError(message=f"Apollo request timed out for path: {path}") from exc
        except requests.RequestException as exc:
            raise ApolloTransientError(message=f"Apollo request failed for path: {path}: {exc}") from exc
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            retry_after_seconds: int | None = None
            if retry_after:
                try:
                    retry_after_seconds = max(0, int(float(retry_after)))
                except ValueError:
                    retry_after_seconds = None
            raise ApolloRateLimitError(
                message=f"429 Too Many Requests for url: {response.url}",
                retry_after_seconds=retry_after_seconds,
            )
        response.raise_for_status()
        return response.json()

    def search_organizations(self, *, domain: str = "", name: str = "", per_page: int = 5) -> dict[str, Any]:
        payload: dict[str, Any] = {"page": 1, "per_page": per_page}
        if domain:
            payload["q_organization_domains"] = [domain]
        if name:
            payload["q_organization_name"] = name
        return self._post("/organizations/search", payload)

    def search_people(
        self,
        *,
        organization_name: str = "",
        domain: str = "",
        titles: list[str] | None = None,
        per_page: int = 5,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"page": 1, "per_page": per_page}
        if organization_name:
            payload["q_organization_name"] = organization_name
        if domain:
            payload["q_organization_domains"] = [domain]
        if titles:
            payload["person_titles"] = titles
        return self._post("/mixed_people/api_search", payload)

    def match_person(
        self,
        *,
        name: str = "",
        organization_name: str = "",
        domain: str = "",
        linkedin_url: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name:
            payload["name"] = name
        if organization_name:
            payload["organization_name"] = organization_name
        if domain:
            payload["domain"] = domain
        if linkedin_url:
            payload["linkedin_url"] = linkedin_url
        return self._post("/people/match", payload)

    def bulk_match_people(self, details: list[dict[str, Any]]) -> dict[str, Any]:
        return self._post("/people/bulk_match", {"details": details})


def load_apollo_client() -> ApolloClient:
    import os

    api_key = os.getenv("APOLLO_API_KEY", "").strip()
    api_base = os.getenv("APOLLO_API_BASE", "https://api.apollo.io/api/v1").strip() or "https://api.apollo.io/api/v1"
    timeout_seconds = int((os.getenv("APOLLO_API_TIMEOUT_SECONDS", "12") or "12").strip())
    return ApolloClient(api_key=api_key, api_base=api_base, timeout_seconds=timeout_seconds)
