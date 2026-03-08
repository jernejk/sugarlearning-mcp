"""Tests for per-module watch snapshots and change detection."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sugarlearning_tools.sync import (
    compute_watch_diff,
    has_watch_changes,
    save_watch_snap,
    load_watch_snap,
    watch_snap_path,
    clean_watch_snaps,
    fetch_module_snapshot,
)


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Override data_dir to use a temp directory."""
    mock_settings = MagicMock()
    mock_settings.data_dir = tmp_path
    with patch("sugarlearning_tools.sync.get_settings", return_value=mock_settings):
        yield tmp_path


# --- watch_snap_path ---

def test_watch_snap_path(tmp_data_dir):
    """Path follows snap-{id}.json convention."""
    p = watch_snap_path(6307)
    assert p == tmp_data_dir / "snap-6307.json"


def test_watch_snap_path_different_ids(tmp_data_dir):
    """Different module IDs produce different paths."""
    p1 = watch_snap_path(100)
    p2 = watch_snap_path(200)
    assert p1 != p2
    assert "snap-100.json" in str(p1)
    assert "snap-200.json" in str(p2)


# --- save_watch_snap / load_watch_snap ---

def test_save_and_load_watch_snap(tmp_data_dir):
    """Round-trip save and load preserves data."""
    snap = {
        "timestamp": "2026-03-08T10-00-00",
        "module_id": 6307,
        "module": {"id": 6307, "name": "Test Module"},
        "users": [{"userId": "alice", "emailAddress": "alice@test.com"}],
        "groups": [{"id": 1, "name": "Group A"}],
        "items": [{"id": 10, "name": "Item 1"}],
    }
    path = save_watch_snap(snap)
    assert path.exists()
    assert path.name == "snap-6307.json"

    loaded = load_watch_snap(6307)
    assert loaded is not None
    assert loaded["module_id"] == 6307
    assert loaded["users"][0]["emailAddress"] == "alice@test.com"


def test_load_watch_snap_missing(tmp_data_dir):
    """Loading a non-existent snap returns None."""
    result = load_watch_snap(9999)
    assert result is None


def test_save_overwrites_previous(tmp_data_dir):
    """Saving a new snap overwrites the old one for the same module."""
    snap1 = {"timestamp": "t1", "module_id": 100, "module": {}, "users": [], "groups": [], "items": []}
    snap2 = {"timestamp": "t2", "module_id": 100, "module": {}, "users": [{"userId": "new"}], "groups": [], "items": []}

    save_watch_snap(snap1)
    save_watch_snap(snap2)

    loaded = load_watch_snap(100)
    assert loaded["timestamp"] == "t2"
    assert len(loaded["users"]) == 1


# --- compute_watch_diff ---

def _make_snap(module_id=6307, timestamp="t1", users=None, groups=None, items=None, module=None):
    return {
        "timestamp": timestamp,
        "module_id": module_id,
        "module": module or {"id": module_id, "name": "Test"},
        "users": users or [],
        "groups": groups or [],
        "items": items or [],
    }


def test_diff_no_changes():
    """Identical snapshots produce no changes."""
    users = [{"userId": "a", "emailAddress": "a@test.com", "progressPercentage": 50}]
    groups = [{"id": 1, "name": "G1"}]
    items = [{"id": 10, "name": "Item 1"}]

    old = _make_snap(timestamp="t1", users=users, groups=groups, items=items)
    new = _make_snap(timestamp="t2", users=users, groups=groups, items=items)
    diff = compute_watch_diff(old, new)
    assert not has_watch_changes(diff)


def test_diff_user_added():
    """Detects a new user added to the module."""
    old = _make_snap(timestamp="t1", users=[{"userId": "a", "emailAddress": "a@test.com"}])
    new = _make_snap(timestamp="t2", users=[
        {"userId": "a", "emailAddress": "a@test.com"},
        {"userId": "b", "emailAddress": "b@test.com"},
    ])
    diff = compute_watch_diff(old, new)
    assert has_watch_changes(diff)
    assert len(diff["user_changes"]["added"]) == 1
    assert diff["user_changes"]["added"][0]["emailAddress"] == "b@test.com"
    assert len(diff["user_changes"]["removed"]) == 0


def test_diff_user_removed():
    """Detects a user removed from the module."""
    old = _make_snap(timestamp="t1", users=[
        {"userId": "a", "emailAddress": "a@test.com"},
        {"userId": "b", "emailAddress": "b@test.com"},
    ])
    new = _make_snap(timestamp="t2", users=[{"userId": "a", "emailAddress": "a@test.com"}])
    diff = compute_watch_diff(old, new)
    assert has_watch_changes(diff)
    assert len(diff["user_changes"]["removed"]) == 1
    assert diff["user_changes"]["removed"][0]["emailAddress"] == "b@test.com"


def test_diff_user_added_and_removed():
    """Detects simultaneous add and remove."""
    old = _make_snap(timestamp="t1", users=[{"userId": "a", "emailAddress": "a@test.com"}])
    new = _make_snap(timestamp="t2", users=[{"userId": "b", "emailAddress": "b@test.com"}])
    diff = compute_watch_diff(old, new)
    assert has_watch_changes(diff)
    assert len(diff["user_changes"]["added"]) == 1
    assert len(diff["user_changes"]["removed"]) == 1


def test_diff_group_added():
    """Detects a new group assigned."""
    old = _make_snap(timestamp="t1", groups=[])
    new = _make_snap(timestamp="t2", groups=[{"id": 1, "name": "New Group"}])
    diff = compute_watch_diff(old, new)
    assert has_watch_changes(diff)
    assert len(diff["group_changes"]["added"]) == 1


def test_diff_group_removed():
    """Detects a group unassigned."""
    old = _make_snap(timestamp="t1", groups=[{"id": 1, "name": "Old Group"}])
    new = _make_snap(timestamp="t2", groups=[])
    diff = compute_watch_diff(old, new)
    assert has_watch_changes(diff)
    assert len(diff["group_changes"]["removed"]) == 1


def test_diff_item_added():
    """Detects a new learning item added."""
    old = _make_snap(timestamp="t1", items=[])
    new = _make_snap(timestamp="t2", items=[{"id": 10, "name": "New Item"}])
    diff = compute_watch_diff(old, new)
    assert has_watch_changes(diff)
    assert len(diff["item_changes"]["added"]) == 1
    assert diff["item_changes"]["added"][0]["name"] == "New Item"


def test_diff_item_removed():
    """Detects a learning item removed."""
    old = _make_snap(timestamp="t1", items=[{"id": 10, "name": "Gone Item"}])
    new = _make_snap(timestamp="t2", items=[])
    diff = compute_watch_diff(old, new)
    assert has_watch_changes(diff)
    assert len(diff["item_changes"]["removed"]) == 1


def test_diff_item_changed():
    """Detects changes to an existing learning item."""
    old = _make_snap(timestamp="t1", items=[{"id": 10, "name": "Item", "description": "old desc"}])
    new = _make_snap(timestamp="t2", items=[{"id": 10, "name": "Item", "description": "new desc"}])
    diff = compute_watch_diff(old, new)
    assert has_watch_changes(diff)
    assert len(diff["item_changes"]["changed"]) == 1
    assert diff["item_changes"]["changed"][0]["changes"]["description"]["old"] == "old desc"
    assert diff["item_changes"]["changed"][0]["changes"]["description"]["new"] == "new desc"


def test_diff_module_property_changed():
    """Detects changes to the module's own properties."""
    old = _make_snap(timestamp="t1", module={"id": 6307, "name": "Old Name"})
    new = _make_snap(timestamp="t2", module={"id": 6307, "name": "New Name"})
    diff = compute_watch_diff(old, new)
    assert has_watch_changes(diff)
    assert "name" in diff["module_changes"]


def test_diff_empty_to_empty():
    """No changes when both snapshots have no data."""
    old = _make_snap(timestamp="t1")
    new = _make_snap(timestamp="t2")
    diff = compute_watch_diff(old, new)
    assert not has_watch_changes(diff)


def test_diff_multiple_changes():
    """Detects user, group, and item changes in the same diff."""
    old = _make_snap(
        timestamp="t1",
        users=[{"userId": "a", "emailAddress": "a@test.com"}],
        groups=[{"id": 1, "name": "G1"}],
        items=[{"id": 10, "name": "Item 1"}],
    )
    new = _make_snap(
        timestamp="t2",
        users=[{"userId": "b", "emailAddress": "b@test.com"}],
        groups=[{"id": 2, "name": "G2"}],
        items=[{"id": 20, "name": "Item 2"}],
    )
    diff = compute_watch_diff(old, new)
    assert has_watch_changes(diff)
    assert len(diff["user_changes"]["added"]) == 1
    assert len(diff["user_changes"]["removed"]) == 1
    assert len(diff["group_changes"]["added"]) == 1
    assert len(diff["group_changes"]["removed"]) == 1
    assert len(diff["item_changes"]["added"]) == 1
    assert len(diff["item_changes"]["removed"]) == 1


# --- clean_watch_snaps ---

def test_clean_watch_snaps_removes_all(tmp_data_dir):
    """Cleaning removes all snap-*.json files."""
    (tmp_data_dir / "snap-100.json").write_text("{}")
    (tmp_data_dir / "snap-200.json").write_text("{}")
    (tmp_data_dir / "snap-300.json").write_text("{}")

    removed = clean_watch_snaps()
    assert len(removed) == 3
    assert not list(tmp_data_dir.glob("snap-*.json"))


def test_clean_watch_snaps_ignores_other_files(tmp_data_dir):
    """Cleaning only removes snap-*.json, not other files."""
    (tmp_data_dir / "snap-100.json").write_text("{}")
    (tmp_data_dir / "other-file.json").write_text("{}")
    (tmp_data_dir / "snapshot.json").write_text("{}")

    removed = clean_watch_snaps()
    assert len(removed) == 1
    assert (tmp_data_dir / "other-file.json").exists()
    assert (tmp_data_dir / "snapshot.json").exists()


def test_clean_watch_snaps_empty_dir(tmp_data_dir):
    """Cleaning an empty directory returns empty list."""
    removed = clean_watch_snaps()
    assert removed == []


# --- has_watch_changes ---

def test_has_watch_changes_false_on_empty_diff():
    """Empty diff reports no changes."""
    diff = {
        "module_changes": {},
        "user_changes": {"added": [], "removed": []},
        "group_changes": {"added": [], "removed": []},
        "item_changes": {"added": [], "removed": [], "changed": []},
    }
    assert not has_watch_changes(diff)


def test_has_watch_changes_true_on_any_change():
    """Any non-empty change section triggers True."""
    base = {
        "module_changes": {},
        "user_changes": {"added": [], "removed": []},
        "group_changes": {"added": [], "removed": []},
        "item_changes": {"added": [], "removed": [], "changed": []},
    }

    # User added
    d = {**base, "user_changes": {"added": [{"userId": "x"}], "removed": []}}
    assert has_watch_changes(d)

    # Group removed
    d = {**base, "group_changes": {"added": [], "removed": [{"id": 1}]}}
    assert has_watch_changes(d)

    # Item changed
    d = {**base, "item_changes": {"added": [], "removed": [], "changed": [{"id": 1}]}}
    assert has_watch_changes(d)

    # Module changes
    d = {**base, "module_changes": {"name": {"old": "a", "new": "b"}}}
    assert has_watch_changes(d)


# --- fetch_module_snapshot ---

def test_fetch_module_snapshot_calls_api():
    """fetch_module_snapshot calls the right API methods."""
    mock_client = MagicMock()
    mock_client.get_module.return_value = {"id": 42, "name": "Test Module"}
    mock_client.get_module_users.return_value = [{"userId": "alice"}]
    mock_client.get_module_groups.return_value = [{"id": 1, "name": "G1"}]
    mock_client.get_module_items.return_value = [{"id": 10, "name": "Item"}]

    snap = fetch_module_snapshot(42, client=mock_client)

    mock_client.get_module.assert_called_once_with(42)
    mock_client.get_module_users.assert_called_once_with(42)
    mock_client.get_module_groups.assert_called_once_with(42)
    mock_client.get_module_items.assert_called_once_with(42)

    assert snap["module_id"] == 42
    assert snap["module"]["name"] == "Test Module"
    assert len(snap["users"]) == 1
    assert len(snap["groups"]) == 1
    assert len(snap["items"]) == 1
    assert "timestamp" in snap


def test_fetch_module_snapshot_handles_api_errors():
    """fetch_module_snapshot gracefully handles API errors for users/groups/items."""
    mock_client = MagicMock()
    mock_client.get_module.return_value = {"id": 42, "name": "Test"}
    mock_client.get_module_users.side_effect = Exception("API error")
    mock_client.get_module_groups.side_effect = Exception("API error")
    mock_client.get_module_items.side_effect = Exception("API error")

    snap = fetch_module_snapshot(42, client=mock_client)

    assert snap["users"] == []
    assert snap["groups"] == []
    assert snap["items"] == []


# --- End-to-end scenario tests ---

def test_scenario_first_watch_then_changes(tmp_data_dir):
    """Simulate: first watch (no previous), then second watch with changes."""
    # First watch: no previous snap
    snap1 = _make_snap(
        timestamp="t1",
        users=[{"userId": "a", "emailAddress": "a@test.com"}],
        items=[{"id": 10, "name": "Item 1"}],
    )
    assert load_watch_snap(6307) is None  # No previous
    save_watch_snap(snap1)
    assert load_watch_snap(6307) is not None

    # Second watch: user added, item changed
    snap2 = _make_snap(
        timestamp="t2",
        users=[
            {"userId": "a", "emailAddress": "a@test.com"},
            {"userId": "b", "emailAddress": "b@test.com"},
        ],
        items=[{"id": 10, "name": "Item 1 Updated"}],
    )
    previous = load_watch_snap(6307)
    diff = compute_watch_diff(previous, snap2)
    assert has_watch_changes(diff)
    assert len(diff["user_changes"]["added"]) == 1
    assert len(diff["item_changes"]["changed"]) == 1

    save_watch_snap(snap2)
    loaded = load_watch_snap(6307)
    assert loaded["timestamp"] == "t2"


def test_scenario_watch_then_sync_clears_snaps(tmp_data_dir):
    """Simulate: watch creates snaps, sync clears them."""
    snap1 = _make_snap(module_id=100, timestamp="t1")
    snap2 = _make_snap(module_id=200, timestamp="t1")
    save_watch_snap(snap1)
    save_watch_snap(snap2)

    assert (tmp_data_dir / "snap-100.json").exists()
    assert (tmp_data_dir / "snap-200.json").exists()

    removed = clean_watch_snaps()
    assert len(removed) == 2
    assert load_watch_snap(100) is None
    assert load_watch_snap(200) is None


def test_scenario_no_changes_between_watches(tmp_data_dir):
    """Two identical watches should report no changes."""
    snap = _make_snap(
        timestamp="t1",
        users=[{"userId": "a", "emailAddress": "a@test.com"}],
        groups=[{"id": 1, "name": "G1"}],
        items=[{"id": 10, "name": "Item 1"}],
    )
    save_watch_snap(snap)

    snap2 = _make_snap(
        timestamp="t2",
        users=[{"userId": "a", "emailAddress": "a@test.com"}],
        groups=[{"id": 1, "name": "G1"}],
        items=[{"id": 10, "name": "Item 1"}],
    )
    previous = load_watch_snap(6307)
    diff = compute_watch_diff(previous, snap2)
    assert not has_watch_changes(diff)


def test_scenario_multiple_modules_independent(tmp_data_dir):
    """Watch snapshots for different modules don't interfere."""
    snap_a = _make_snap(module_id=100, timestamp="t1", users=[{"userId": "a"}])
    snap_b = _make_snap(module_id=200, timestamp="t1", users=[{"userId": "b"}])

    save_watch_snap(snap_a)
    save_watch_snap(snap_b)

    loaded_a = load_watch_snap(100)
    loaded_b = load_watch_snap(200)

    assert loaded_a["module_id"] == 100
    assert loaded_b["module_id"] == 200
    assert loaded_a["users"][0]["userId"] == "a"
    assert loaded_b["users"][0]["userId"] == "b"
