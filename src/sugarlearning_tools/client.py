"""SugarLearning API client using Bearer token auth."""

from __future__ import annotations

import httpx

from .auth import get_token
from .config import get_settings


def _to_camel(key: str) -> str:
    """Convert PascalCase to camelCase: 'EmailAddress' -> 'emailAddress'."""
    if not key:
        return key
    return key[0].lower() + key[1:]


def _normalize(data):
    """Recursively convert all dict keys from PascalCase to camelCase."""
    if isinstance(data, dict):
        return {_to_camel(k): _normalize(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_normalize(item) for item in data]
    return data


class SugarLearningClient:
    """Typed wrapper around the SugarLearning REST API."""

    def __init__(self, company_code: str | None = None):
        settings = get_settings()
        self.base_url = settings.base_url.rstrip("/")
        self.company_code = company_code or settings.company_code

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {get_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, **kwargs) -> dict | list:
        url = f"{self.base_url}{path}"
        resp = httpx.get(url, headers=self._headers(), timeout=30, **kwargs)
        resp.raise_for_status()
        return _normalize(resp.json())

    def _post(self, path: str, json_body: dict | None = None, **kwargs) -> dict | list:
        url = f"{self.base_url}{path}"
        resp = httpx.post(
            url, headers=self._headers(), json=json_body, timeout=30, **kwargs
        )
        resp.raise_for_status()
        return _normalize(resp.json())

    # --- Modules ---

    def get_modules(self) -> list[dict]:
        """Get all admin modules for the company."""
        return self._get(f"/api/v2/admin/{self.company_code}/modules")

    def get_module(self, module_id: int) -> dict:
        """Get a single module's details."""
        return self._get(f"/api/v2/admin/{self.company_code}/modules/{module_id}")

    def get_module_users(self, module_id: int) -> list[dict]:
        """Get users assigned to a module."""
        return self._get(
            f"/api/v2/admin/{self.company_code}/modules/{module_id}/moduleUsers"
        )

    def get_module_groups(self, module_id: int) -> list[dict]:
        """Get groups assigned to a module."""
        return self._get(
            f"/api/v2/admin/{self.company_code}/modules/{module_id}/companyGroup"
        )

    def get_module_items(self, module_id: int) -> list[dict]:
        """Get learning items in a module."""
        return self._get(
            f"/api/v2/admin/{self.company_code}/modules/learningItemList/{module_id}"
        )

    # --- Module List (non-admin) ---

    def get_module_list(self) -> list[dict]:
        """Get module list (public/employee view)."""
        return self._get(f"/api/v2/{self.company_code}/modulelist")

    # --- Backlog ---

    def get_backlog(self, user_id: str | None = None, status: int = 0) -> dict:
        """Get backlog for a company user.

        Args:
            user_id: User identifier (e.g. 'jk'). Defaults to configured user.
            status: Filter status (0 = all).
        """
        settings = get_settings()
        uid = user_id or settings.user_id
        return self._post(
            f"/api/v2/backlog/{self.company_code}/{uid}",
            json_body={"Status": status},
        )
