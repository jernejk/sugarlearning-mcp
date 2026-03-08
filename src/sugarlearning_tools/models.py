"""Pydantic models matching SugarLearning API responses."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class AdminModuleItem(BaseModel):
    id: int
    name: str
    description: str | None = None
    manager_id: str | None = None
    manager: str | None = None
    manager_email: str | None = None
    items: int = 0
    archived_items: int = 0
    priority: int = 0
    drafts: int = 0
    points: int = 0
    groups: int = 0
    users: int = 0
    reminder: bool = False
    has_badge: bool = False

    model_config = {"extra": "allow"}


class CompanyUser(BaseModel):
    user_id: str | None = None
    email_address: str | None = None
    progress_percentage: int = 0
    completed_items_count: int = 0
    total_items_count: int = 0
    last_completed_utc: datetime | None = None
    since: datetime | None = None
    is_assigned: bool = False

    model_config = {"extra": "allow"}


class AssignedGroup(BaseModel):
    id: str | None = None
    is_assigned: bool = False
    name: str | None = None
    description: str | None = None
    user_count: int = 0

    model_config = {"extra": "allow"}


class LearningItem(BaseModel):
    id: int | None = None
    name: str | None = None
    description: str | None = None
    status: str | None = None
    module_id: int | None = None
    module_name: str | None = None

    model_config = {"extra": "allow"}


class BacklogModule(BaseModel):
    id: int | None = None
    name: str | None = None
    items: list[dict] | None = None

    model_config = {"extra": "allow"}


class Backlog(BaseModel):
    total_completed_items: int = 0
    total_blocked_items: int = 0
    total_outstanding_items: int = 0
    total_items: int = 0
    modules: list[BacklogModule] | None = None

    model_config = {"extra": "allow"}


class Snapshot(BaseModel):
    """Full data snapshot for change tracking."""
    timestamp: str
    modules: list[dict]
    module_users: dict[str, list[dict]]  # module_id -> users
    module_groups: dict[str, list[dict]]  # module_id -> groups
    module_items: dict[str, list[dict]]  # module_id -> learning items
