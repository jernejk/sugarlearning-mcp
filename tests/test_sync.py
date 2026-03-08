"""Tests for snapshot diff logic."""

from unittest.mock import MagicMock

from sugarlearning_tools.sync import compute_diff, _dict_diff, format_diff, fetch_snapshot


def test_dict_diff_no_changes():
    assert _dict_diff({"a": 1, "b": 2}, {"a": 1, "b": 2}) == {}


def test_dict_diff_changed_value():
    result = _dict_diff({"a": 1}, {"a": 2})
    assert result == {"a": {"old": 1, "new": 2}}


def test_dict_diff_added_key():
    result = _dict_diff({"a": 1}, {"a": 1, "b": 2})
    assert result == {"b": {"old": None, "new": 2}}


def test_dict_diff_removed_key():
    result = _dict_diff({"a": 1, "b": 2}, {"a": 1})
    assert result == {"b": {"old": 2, "new": None}}


def _make_snapshot(modules, module_users=None, module_groups=None, module_items=None, ts="t1"):
    return {
        "timestamp": ts,
        "modules": modules,
        "module_users": module_users or {},
        "module_groups": module_groups or {},
        "module_items": module_items or {},
    }


def test_compute_diff_no_changes():
    mods = [{"id": 1, "name": "Mod A"}]
    old = _make_snapshot(mods, ts="t1")
    new = _make_snapshot(mods, ts="t2")
    diff = compute_diff(old, new)
    assert diff["modules"]["added"] == []
    assert diff["modules"]["removed"] == []
    assert diff["modules"]["changed"] == []
    assert diff["user_assignments"] == {}


def test_compute_diff_added_module():
    old = _make_snapshot([{"id": 1, "name": "Mod A"}], ts="t1")
    new = _make_snapshot([{"id": 1, "name": "Mod A"}, {"id": 2, "name": "Mod B"}], ts="t2")
    diff = compute_diff(old, new)
    assert len(diff["modules"]["added"]) == 1
    assert diff["modules"]["added"][0]["name"] == "Mod B"


def test_compute_diff_removed_module():
    old = _make_snapshot([{"id": 1, "name": "Mod A"}, {"id": 2, "name": "Mod B"}], ts="t1")
    new = _make_snapshot([{"id": 1, "name": "Mod A"}], ts="t2")
    diff = compute_diff(old, new)
    assert len(diff["modules"]["removed"]) == 1
    assert diff["modules"]["removed"][0]["name"] == "Mod B"


def test_compute_diff_changed_module():
    old = _make_snapshot([{"id": 1, "name": "Old Name"}], ts="t1")
    new = _make_snapshot([{"id": 1, "name": "New Name"}], ts="t2")
    diff = compute_diff(old, new)
    assert len(diff["modules"]["changed"]) == 1
    assert diff["modules"]["changed"][0]["changes"]["name"] == {"old": "Old Name", "new": "New Name"}


def test_compute_diff_user_assignment_added():
    mods = [{"id": 1, "name": "Mod A"}]
    old = _make_snapshot(mods, module_users={"1": []}, ts="t1")
    new = _make_snapshot(
        mods,
        module_users={"1": [{"userId": "u1", "emailAddress": "alice@example.com", "progressPercentage": 0}]},
        ts="t2",
    )
    diff = compute_diff(old, new)
    assert "1" in diff["user_assignments"]
    assert len(diff["user_assignments"]["1"]["added"]) == 1
    assert diff["user_assignments"]["1"]["removed"] == []


def test_compute_diff_user_assignment_removed():
    mods = [{"id": 1, "name": "Mod A"}]
    old = _make_snapshot(
        mods,
        module_users={"1": [{"userId": "u1", "emailAddress": "alice@example.com"}]},
        ts="t1",
    )
    new = _make_snapshot(mods, module_users={"1": []}, ts="t2")
    diff = compute_diff(old, new)
    assert "1" in diff["user_assignments"]
    assert len(diff["user_assignments"]["1"]["removed"]) == 1


def test_compute_diff_group_assignment_added():
    mods = [{"id": 1, "name": "Mod A"}]
    old = _make_snapshot(mods, module_groups={"1": []}, ts="t1")
    new = _make_snapshot(
        mods,
        module_groups={"1": [{"id": 10, "name": "Developers", "userCount": 5}]},
        ts="t2",
    )
    diff = compute_diff(old, new)
    assert "1" in diff["group_assignments"]
    assert len(diff["group_assignments"]["1"]["added"]) == 1


def test_compute_diff_learning_item_added():
    mods = [{"id": 1, "name": "Mod A"}]
    old = _make_snapshot(mods, module_items={"1": []}, ts="t1")
    new = _make_snapshot(
        mods,
        module_items={"1": [{"id": 100, "name": "New Item"}]},
        ts="t2",
    )
    diff = compute_diff(old, new)
    assert "1" in diff["items"]
    assert len(diff["items"]["1"]["added"]) == 1


def test_format_diff_produces_output():
    diff = {
        "from": "t1",
        "to": "t2",
        "modules": {
            "added": [{"name": "New Module", "id": 99}],
            "removed": [],
            "changed": [],
        },
        "user_assignments": {},
        "group_assignments": {},
        "items": {},
    }
    output = format_diff(diff)
    assert "New Module" in output
    assert "t1" in output
    assert "t2" in output


# --- fetch_snapshot edge cases ---

def test_fetch_snapshot_skips_modules_with_no_id():
    """Modules with id=None should be skipped without crashing."""
    client = MagicMock()
    client.get_modules.return_value = [
        {"id": None, "name": "Bad Module"},
        {"id": 1, "name": "Good Module"},
    ]
    client.get_module_users.return_value = [{"userId": "u1"}]
    client.get_module_groups.return_value = []
    client.get_module_items.return_value = []

    snap = fetch_snapshot(client)
    # Should only have module 1, not the None-id one
    assert "1" in snap["module_users"]
    assert "None" not in snap["module_users"]


def test_fetch_snapshot_handles_api_errors_gracefully():
    """API errors for individual modules should not crash the whole sync."""
    client = MagicMock()
    client.get_modules.return_value = [{"id": 1, "name": "Module 1"}]
    client.get_module_users.side_effect = Exception("API error")
    client.get_module_groups.side_effect = Exception("API error")
    client.get_module_items.side_effect = Exception("API error")

    snap = fetch_snapshot(client)
    assert snap["module_users"]["1"] == []
    assert snap["module_groups"]["1"] == []
    assert snap["module_items"]["1"] == []
