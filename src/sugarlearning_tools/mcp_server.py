"""FastMCP server exposing SugarLearning data to AI agents."""

from __future__ import annotations

import json

from fastmcp import FastMCP

from .client import SugarLearningClient
from .config import get_settings

mcp = FastMCP("SugarLearning")


def _client() -> SugarLearningClient:
    return SugarLearningClient()


@mcp.tool
def list_modules() -> list[dict]:
    """List all learning modules in SugarLearning with their metadata (name, manager, item counts, user counts)."""
    return _client().get_modules()


@mcp.tool
def get_module(module_id: int) -> dict:
    """Get detailed information about a specific learning module by its ID."""
    return _client().get_module(module_id)


@mcp.tool
def get_module_users(module_id: int) -> list[dict]:
    """Get all users assigned to a specific module, including their progress percentage and completion status."""
    return _client().get_module_users(module_id)


@mcp.tool
def get_module_groups(module_id: int) -> list[dict]:
    """Get all groups assigned to a specific module."""
    return _client().get_module_groups(module_id)


@mcp.tool
def get_module_items(module_id: int) -> list[dict]:
    """Get all learning items within a specific module."""
    return _client().get_module_items(module_id)


@mcp.tool
def get_backlog(user_id: str | None = None) -> dict:
    """Get the learning backlog for a user, showing all assigned modules and items with completion status.

    Args:
        user_id: User identifier. Defaults to configured user.
    """
    return _client().get_backlog(user_id)


@mcp.tool
def get_recent_changes(count: int = 5) -> list[dict]:
    """Get recent change diffs showing what changed in SugarLearning (new modules, new items, user assignment changes).

    Args:
        count: Number of recent diffs to return (default 5).
    """
    settings = get_settings()
    files = sorted(settings.diffs_dir.glob("*.json"))[-count:]
    results = []
    for f in files:
        diff = json.loads(f.read_text())
        results.append(diff)
    return results


@mcp.tool
def search_learning(query: str, limit: int = 10) -> list[dict]:
    """Semantic search across all learning modules and items using Qdrant vector search.

    Requires Qdrant to be running and indexed (run 'sl index' first).
    Falls back to listing all modules if Qdrant is unavailable.

    Args:
        query: Natural language search query.
        limit: Maximum number of results to return.
    """
    try:
        from .qdrant_index import search_items
        results = search_items(query, limit=limit)
        if results:
            return results
    except Exception:
        pass

    # Fallback: text search in module names
    modules = _client().get_modules()
    q = query.lower()
    matches = [m for m in modules if q in (m.get("name", "") or "").lower() or q in (m.get("description", "") or "").lower()]
    return matches[:limit]


@mcp.tool
def get_module_list() -> list[dict]:
    """Get the module list (employee/public view) - simpler than admin modules."""
    return _client().get_module_list()


@mcp.tool
def get_leaderboard(group_id: str = "all", limit: int = 20) -> list[dict]:
    """Get company leaderboard rankings showing user progress, points, and badges.

    Args:
        group_id: Group ID to filter by, or 'all' for everyone.
        limit: Maximum number of users to return (default 20).
    """
    data = _client().get_leaderboard(group_id=group_id)
    # Filter out 0% users by default
    data = [u for u in data if u.get("percentageOfPointEarned", 0) > 0]
    return data[:limit]


@mcp.tool
def get_user_profile(user_alias: str | None = None) -> dict:
    """Get a user's profile including badges, companies, and personal info.

    Args:
        user_alias: User's alias (e.g. 'jk'). Defaults to current user.
    """
    client = _client()
    if user_alias:
        return client.get_user_profile(user_alias)
    return client.get_my_profile()


@mcp.tool
def get_user_badges(user_alias: str | None = None) -> list[dict]:
    """Get badges earned by a user, showing which modules they completed.

    Args:
        user_alias: User's alias (e.g. 'jk'). Defaults to current user.
    """
    client = _client()
    if user_alias:
        profile = client.get_user_profile(user_alias)
    else:
        profile = client.get_my_profile()
    return profile.get("badges", [])


if __name__ == "__main__":
    mcp.run()
