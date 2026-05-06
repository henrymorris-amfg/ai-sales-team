from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests


class PipedriveClient:
    def __init__(self, api_base: str, api_key: str):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        merged = dict(params or {})
        merged["api_token"] = self.api_key
        response = self.session.get(f"{self.api_base}{path}", params=merged, timeout=60)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success", False):
            raise RuntimeError(f"Pipedrive API error: {payload}")
        return payload

    def _post(self, path: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = dict(data or {})
        response = self.session.post(
            f"{self.api_base}{path}",
            params={"api_token": self.api_key},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("success", False):
            raise RuntimeError(f"Pipedrive API error: {body}")
        return body

    def _put(self, path: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = dict(data or {})
        response = self.session.put(
            f"{self.api_base}{path}",
            params={"api_token": self.api_key},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("success", False):
            raise RuntimeError(f"Pipedrive API error: {body}")
        return body

    def _delete(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        merged = dict(params or {})
        merged["api_token"] = self.api_key
        response = self.session.delete(f"{self.api_base}{path}", params=merged, timeout=60)
        response.raise_for_status()
        body = response.json()
        if not body.get("success", False):
            raise RuntimeError(f"Pipedrive API error: {body}")
        return body

    def _get_all(self, path: str, params: Optional[Dict[str, Any]] = None, limit: int = 500) -> List[Dict[str, Any]]:
        start = 0
        rows: List[Dict[str, Any]] = []
        while True:
            merged = dict(params or {})
            merged["start"] = start
            merged["limit"] = limit
            payload = self._get(path, merged)
            batch = payload.get("data") or []
            if not batch:
                break
            rows.extend(batch)
            pagination = ((payload.get("additional_data") or {}).get("pagination") or {})
            if not pagination.get("more_items_in_collection"):
                break
            next_start = pagination.get("next_start")
            if next_start is None:
                break
            start = next_start
        return rows

    def get_pipelines(self) -> List[Dict[str, Any]]:
        return self._get("/pipelines").get("data") or []

    def get_stages(self) -> List[Dict[str, Any]]:
        return self._get("/stages").get("data") or []

    def get_users(self) -> List[Dict[str, Any]]:
        return self._get("/users").get("data") or []

    def get_activity_types(self) -> List[Dict[str, Any]]:
        return self._get("/activityTypes").get("data") or []

    def get_deal_fields(self) -> List[Dict[str, Any]]:
        return self._get_all("/dealFields")

    def get_person_fields(self) -> List[Dict[str, Any]]:
        return self._get_all("/personFields")

    def get_organisation_fields(self) -> List[Dict[str, Any]]:
        return self._get_all("/organizationFields")

    def get_lead_labels(self) -> List[Dict[str, Any]]:
        return self._get("/leadLabels").get("data") or []

    def get_leads(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self._get("/leads", {"limit": limit}).get("data") or []

    def get_all_leads(self, limit: int = 500) -> List[Dict[str, Any]]:
        return self._get_all("/leads", limit=limit)

    def get_deals(self, status: str = "open") -> List[Dict[str, Any]]:
        return self._get_all("/deals", {"status": status})

    def get_persons(self) -> List[Dict[str, Any]]:
        return self._get_all("/persons")

    def get_person(self, person_id: int) -> Dict[str, Any]:
        return self._get(f"/persons/{person_id}").get("data") or {}

    def get_organisations(self) -> List[Dict[str, Any]]:
        return self._get_all("/organizations")

    def get_organisation(self, organisation_id: int) -> Dict[str, Any]:
        return self._get(f"/organizations/{organisation_id}").get("data") or {}

    def get_activities(self, done: Optional[int] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if done is not None:
            params["done"] = done
        return self._get_all("/activities", params)

    def get_recent_activities(self, limit: int = 500, done: Optional[int] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"limit": limit}
        if done is not None:
            params["done"] = done
        return self._get("/activities", params).get("data") or []

    def get_deal_activities(self, deal_id: int) -> List[Dict[str, Any]]:
        return self._get_all(f"/deals/{deal_id}/activities")

    def search_persons(self, term: str, limit: int = 10) -> List[Dict[str, Any]]:
        return self._get("/persons/search", {"term": term, "limit": limit, "fields": "name,email"}).get("data", {}).get("items") or []

    def search_organisations(self, term: str, limit: int = 10) -> List[Dict[str, Any]]:
        return self._get("/organizations/search", {"term": term, "limit": limit, "fields": "name,address"}).get("data", {}).get("items") or []

    def create_organisation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._post("/organizations", payload).get("data") or {}

    def create_person(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._post("/persons", payload).get("data") or {}

    def create_lead(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._post("/leads", payload).get("data") or {}

    def create_note(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._post("/notes", payload).get("data") or {}

    def create_activity(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._post("/activities", payload).get("data") or {}

    def merge_organisation(self, survivor_id: int, duplicate_id: int) -> Dict[str, Any]:
        return self._put(f"/organizations/{survivor_id}/merge", {"merge_with_id": duplicate_id}).get("data") or {}

    def merge_person(self, survivor_id: int, duplicate_id: int) -> Dict[str, Any]:
        return self._put(f"/persons/{survivor_id}/merge", {"merge_with_id": duplicate_id}).get("data") or {}

    def delete_lead(self, lead_id: str) -> Dict[str, Any]:
        return self._delete(f"/leads/{lead_id}").get("data") or {}
