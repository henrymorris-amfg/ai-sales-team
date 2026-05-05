from __future__ import annotations

from typing import Any

import requests

from . import config as _config  # noqa: F401  Ensures local secret env files are loaded.


class ApolloClient:
    def __init__(self, api_key: str, api_base: str = "https://api.apollo.io/api/v1") -> None:
        self.api_key = api_key.strip()
        self.api_base = api_base.rstrip("/")
        if not self.api_key:
            raise ValueError("Missing APOLLO_API_KEY")

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            f"{self.api_base}{path}",
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": self.api_key,
            },
            json=payload,
            timeout=45,
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


def load_apollo_client() -> ApolloClient:
    import os

    api_key = os.getenv("APOLLO_API_KEY", "").strip()
    api_base = os.getenv("APOLLO_API_BASE", "https://api.apollo.io/api/v1").strip() or "https://api.apollo.io/api/v1"
    return ApolloClient(api_key=api_key, api_base=api_base)
