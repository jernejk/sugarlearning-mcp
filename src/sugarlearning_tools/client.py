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
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise httpx.HTTPStatusError(
                f"{resp.status_code}: {detail}",
                request=resp.request,
                response=resp,
            )
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

    def get_item(
        self,
        item_id: int,
        user_alias: str | None = None,
        timezone_offset_minutes: int = 0,
        visit_source: str = "cli",
    ) -> dict:
        """Get a learning item's full details and content for a user."""
        alias = user_alias or "me"
        return self._get(
            f"/api/v2/company/{self.company_code}/user/{alias}/item/{item_id}",
            params={
                "timeZoneOffsetInMinutes": timezone_offset_minutes,
                "visitSource": visit_source,
            },
        )

    # --- Module List (non-admin) ---

    def get_module_list(self) -> list[dict]:
        """Get module list (public/employee view)."""
        return self._get(f"/api/v2/{self.company_code}/modulelist")

    # --- Item Actions ---

    def complete_item(
        self,
        company_user_item_id: int,
        action: int = 1,
        comment: str | None = None,
    ) -> dict:
        """Complete a learning item by creating an activity.

        Args:
            company_user_item_id: The CompanyUserItem ID (from backlog).
            action: 0 = Request (user marks done), 1 = Approve (approver approves).
            comment: Optional comment to include with the action.
        """
        settings = get_settings()
        item_url = f"{settings.base_url}/{self.company_code}/backlog"
        body = {
            "Action": action,
            "Comment": comment or "",
            "ItemUrl": item_url,
            "ApprovalUrl": item_url,
        }
        return self._post(
            f"/api/v2/activity/{self.company_code}/Create",
            json_body=body,
            params={"Id": company_user_item_id},
        )

    def save_note(
        self,
        item_id: int,
        content: str,
        company_user_item_id: int | None = None,
        note_format: str = "markdown",
    ) -> None:
        """Save or update a private note on a learning item.

        Args:
            item_id: The learning item ID.
            content: The note text.
            company_user_item_id: The CompanyUserItem ID. If not provided, uses item_id.
            note_format: 'markdown' or 'html'.
        """
        fmt = 1 if note_format.lower() == "html" else 0
        body = {
            "CompanyUserItemId": company_user_item_id or item_id,
            "Content": content,
            "Format": fmt,
        }
        url = f"{self.base_url}/api/v2/company/{self.company_code}/user/me/item/{item_id}/notes"
        resp = httpx.post(url, headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()

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

    # --- Leaderboard ---

    def get_leaderboard_summary(self) -> dict:
        """Get leaderboard summary (company info + available groups)."""
        return self._get(
            f"/api/Leaderboard/GetLeaderboardSummary?companyCode={self.company_code}"
        )

    def get_leaderboard(self, group_id: str = "all") -> list[dict]:
        """Get leaderboard user rankings.

        Args:
            group_id: Group ID to filter by, or 'all' for everyone.
        """
        return self._get(
            f"/api/Leaderboard/GetLeaderboardUserSummary"
            f"?companyCode={self.company_code}&groupId={group_id}"
        )

    # --- User Profile ---

    def get_my_profile(self) -> dict:
        """Get current user's profile including badges."""
        return self._get("/api/v2/users/me?companyId=0")

    def get_user_profile(self, user_alias: str) -> dict:
        """Get a user's profile by their alias (e.g. 'jk').

        Args:
            user_alias: The user's username alias.
        """
        return self._get(
            f"/api/v2/users/MyProfile?userNameAlias={user_alias}&companyId=0"
        )
