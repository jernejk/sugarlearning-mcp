"""Tests for MCP server tools.

Uses FastMCP's call_tool() to invoke tools with mocked API client.
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sugarlearning_tools.mcp_server import mcp


# --- Fixtures ---

FAKE_MODULES = [
    {"id": 1, "name": "Induction", "description": "New starter induction", "manager": "Alice", "items": 5, "users": 10},
    {"id": 2, "name": "Security", "description": "Security training", "manager": "Bob", "items": 3, "users": 8},
]

FAKE_MODULE_DETAIL = {
    "id": 1,
    "name": "Induction",
    "description": "New starter induction",
    "manager": "Alice",
    "learningItems": 5,
}

FAKE_USERS = [
    {"userId": "u1", "emailAddress": "alice@test.com", "progressPercentage": 100},
    {"userId": "u2", "emailAddress": "bob@test.com", "progressPercentage": 50},
]

FAKE_GROUPS = [
    {"id": 10, "name": "Developers", "userCount": 5},
]

FAKE_ITEMS = [
    {"id": 100, "name": "Read the handbook", "description": "Employee handbook"},
    {"id": 101, "name": "Complete training", "description": "Finish all modules"},
]

FAKE_BACKLOG = {
    "totalItems": 3,
    "totalCompletedItems": 1,
    "totalOutstandingItems": 2,
    "modules": [{"id": 1, "name": "Induction", "items": []}],
}


def _mock_client():
    """Create a mock SugarLearningClient."""
    client = MagicMock()
    client.get_modules.return_value = FAKE_MODULES
    client.get_module.return_value = FAKE_MODULE_DETAIL
    client.get_module_users.return_value = FAKE_USERS
    client.get_module_groups.return_value = FAKE_GROUPS
    client.get_module_items.return_value = FAKE_ITEMS
    client.get_backlog.return_value = FAKE_BACKLOG
    client.get_module_list.return_value = FAKE_MODULES
    return client


def _extract_text(result) -> str:
    """Extract text from a FastMCP ToolResult."""
    return result.content[0].text


def _extract_data(result):
    """Extract and parse JSON from a FastMCP ToolResult."""
    return json.loads(_extract_text(result))


# --- Tool tests ---


@pytest.mark.anyio
async def test_list_modules():
    mock = _mock_client()
    with patch("sugarlearning_tools.mcp_server._client", return_value=mock):
        result = await mcp.call_tool("list_modules")
        data = _extract_data(result)
        assert len(data) == 2
        assert data[0]["name"] == "Induction"
        mock.get_modules.assert_called_once()


@pytest.mark.anyio
async def test_get_module():
    mock = _mock_client()
    with patch("sugarlearning_tools.mcp_server._client", return_value=mock):
        result = await mcp.call_tool("get_module", {"module_id": 1})
        data = _extract_data(result)
        assert data["name"] == "Induction"
        mock.get_module.assert_called_once_with(1)


@pytest.mark.anyio
async def test_get_module_users():
    mock = _mock_client()
    with patch("sugarlearning_tools.mcp_server._client", return_value=mock):
        result = await mcp.call_tool("get_module_users", {"module_id": 1})
        data = _extract_data(result)
        assert len(data) == 2
        assert data[0]["emailAddress"] == "alice@test.com"
        mock.get_module_users.assert_called_once_with(1)


@pytest.mark.anyio
async def test_get_module_groups():
    mock = _mock_client()
    with patch("sugarlearning_tools.mcp_server._client", return_value=mock):
        result = await mcp.call_tool("get_module_groups", {"module_id": 1})
        data = _extract_data(result)
        assert len(data) == 1
        assert data[0]["name"] == "Developers"


@pytest.mark.anyio
async def test_get_module_items():
    mock = _mock_client()
    with patch("sugarlearning_tools.mcp_server._client", return_value=mock):
        result = await mcp.call_tool("get_module_items", {"module_id": 1})
        data = _extract_data(result)
        assert len(data) == 2
        assert data[0]["name"] == "Read the handbook"


@pytest.mark.anyio
async def test_get_backlog():
    mock = _mock_client()
    with patch("sugarlearning_tools.mcp_server._client", return_value=mock):
        result = await mcp.call_tool("get_backlog", {})
        data = _extract_data(result)
        assert data["totalItems"] == 3
        mock.get_backlog.assert_called_once_with(None)


@pytest.mark.anyio
async def test_get_backlog_with_user_id():
    mock = _mock_client()
    with patch("sugarlearning_tools.mcp_server._client", return_value=mock):
        result = await mcp.call_tool("get_backlog", {"user_id": "alice"})
        _extract_data(result)
        mock.get_backlog.assert_called_once_with("alice")


@pytest.mark.anyio
async def test_get_module_list():
    mock = _mock_client()
    with patch("sugarlearning_tools.mcp_server._client", return_value=mock):
        result = await mcp.call_tool("get_module_list")
        data = _extract_data(result)
        assert len(data) == 2
        mock.get_module_list.assert_called_once()


@pytest.mark.anyio
async def test_get_recent_changes(tmp_path, monkeypatch):
    """get_recent_changes reads diff files from diffs_dir."""
    diffs_dir = tmp_path / "diffs"
    diffs_dir.mkdir()
    diff_data = {"from": "t1", "to": "t2", "modules": {"added": [{"name": "New"}], "removed": [], "changed": []}}
    (diffs_dir / "2025-01-01.json").write_text(json.dumps(diff_data))

    settings = MagicMock()
    settings.diffs_dir = diffs_dir
    monkeypatch.setattr("sugarlearning_tools.mcp_server.get_settings", lambda: settings)

    result = await mcp.call_tool("get_recent_changes", {"count": 5})
    data = _extract_data(result)
    assert len(data) == 1
    assert data[0]["modules"]["added"][0]["name"] == "New"


@pytest.mark.anyio
async def test_search_learning_text_fallback():
    """When Qdrant search raises, text fallback should filter modules by query."""
    mock = _mock_client()
    with patch("sugarlearning_tools.mcp_server._client", return_value=mock):
        # Make qdrant_index.search_items raise, forcing text fallback
        with patch("sugarlearning_tools.qdrant_index.search_items", side_effect=Exception("no qdrant")):
            result = await mcp.call_tool("search_learning", {"query": "security"})
            data = _extract_data(result)
            assert len(data) == 1
            assert data[0]["name"] == "Security"


@pytest.mark.anyio
async def test_search_learning_with_limit():
    """search_learning should respect limit parameter."""
    mock = _mock_client()
    with patch("sugarlearning_tools.mcp_server._client", return_value=mock):
        with patch("sugarlearning_tools.qdrant_index.search_items", side_effect=Exception("no qdrant")):
            result = await mcp.call_tool("search_learning", {"query": "i", "limit": 1})
            data = _extract_data(result)
            assert len(data) <= 1
