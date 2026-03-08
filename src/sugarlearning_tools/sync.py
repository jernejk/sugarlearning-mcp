"""Fetch data from SugarLearning, create snapshots, and compute diffs."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .client import SugarLearningClient
from .config import get_settings


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


def _latest_snapshot() -> Path | None:
    settings = get_settings()
    files = sorted(settings.snapshots_dir.glob("*.json"))
    return files[-1] if files else None


def fetch_snapshot(client: SugarLearningClient | None = None) -> dict:
    """Fetch all data and return as a snapshot dict."""
    if client is None:
        client = SugarLearningClient()

    print("Fetching modules...", file=sys.stderr)
    modules = client.get_modules()

    module_users: dict[str, list] = {}
    module_groups: dict[str, list] = {}
    module_items: dict[str, list] = {}

    for i, mod in enumerate(modules):
        raw_id = mod.get("id")
        if raw_id is None:
            print(f"  [{i+1}/{len(modules)}] Skipping module with no ID", file=sys.stderr)
            continue
        mid = str(raw_id)
        name = mod.get("name", "?")
        print(f"  [{i+1}/{len(modules)}] {name} (ID: {mid})", file=sys.stderr)

        try:
            module_users[mid] = client.get_module_users(int(mid))
        except Exception as e:
            print(f"    Warning: could not fetch users: {e}", file=sys.stderr)
            module_users[mid] = []

        try:
            module_groups[mid] = client.get_module_groups(int(mid))
        except Exception as e:
            print(f"    Warning: could not fetch groups: {e}", file=sys.stderr)
            module_groups[mid] = []

        try:
            module_items[mid] = client.get_module_items(int(mid))
        except Exception as e:
            print(f"    Warning: could not fetch items: {e}", file=sys.stderr)
            module_items[mid] = []

    return {
        "timestamp": _timestamp(),
        "modules": modules,
        "module_users": module_users,
        "module_groups": module_groups,
        "module_items": module_items,
    }


def save_snapshot(snapshot: dict) -> Path:
    """Save snapshot to disk."""
    settings = get_settings()
    ts = snapshot["timestamp"]
    path = settings.snapshots_dir / f"{ts}.json"
    path.write_text(json.dumps(snapshot, indent=2, default=str))
    print(f"Snapshot saved: {path}", file=sys.stderr)
    return path


def compute_diff(old: dict, new: dict) -> dict:
    """Compute differences between two snapshots."""
    changes: dict = {
        "from": old.get("timestamp", "?"),
        "to": new.get("timestamp", "?"),
        "modules": {"added": [], "removed": [], "changed": []},
        "user_assignments": {},
        "group_assignments": {},
        "items": {},
    }

    # Module-level changes
    old_modules = {str(m["id"]): m for m in old.get("modules", [])}
    new_modules = {str(m["id"]): m for m in new.get("modules", [])}

    old_ids = set(old_modules.keys())
    new_ids = set(new_modules.keys())

    for mid in new_ids - old_ids:
        changes["modules"]["added"].append(new_modules[mid])
    for mid in old_ids - new_ids:
        changes["modules"]["removed"].append(old_modules[mid])
    for mid in old_ids & new_ids:
        diffs = _dict_diff(old_modules[mid], new_modules[mid])
        if diffs:
            changes["modules"]["changed"].append({"id": mid, "name": new_modules[mid].get("name"), "changes": diffs})

    # User assignment changes per module
    for mid in new_ids:
        old_users = {u.get("userId") or u.get("emailAddress"): u for u in old.get("module_users", {}).get(mid, [])}
        new_users = {u.get("userId") or u.get("emailAddress"): u for u in new.get("module_users", {}).get(mid, [])}
        added = [new_users[k] for k in set(new_users) - set(old_users)]
        removed = [old_users[k] for k in set(old_users) - set(new_users)]
        if added or removed:
            mod_name = new_modules.get(mid, {}).get("name", mid)
            changes["user_assignments"][mid] = {
                "module_name": mod_name,
                "added": added,
                "removed": removed,
            }

    # Group assignment changes per module
    for mid in new_ids:
        old_groups = {str(g.get("id")): g for g in old.get("module_groups", {}).get(mid, [])}
        new_groups = {str(g.get("id")): g for g in new.get("module_groups", {}).get(mid, [])}
        added = [new_groups[k] for k in set(new_groups) - set(old_groups)]
        removed = [old_groups[k] for k in set(old_groups) - set(new_groups)]
        if added or removed:
            mod_name = new_modules.get(mid, {}).get("name", mid)
            changes["group_assignments"][mid] = {
                "module_name": mod_name,
                "added": added,
                "removed": removed,
            }

    # Learning item changes per module
    for mid in new_ids:
        old_items = {str(i.get("id")): i for i in old.get("module_items", {}).get(mid, [])}
        new_items = {str(i.get("id")): i for i in new.get("module_items", {}).get(mid, [])}
        added = [new_items[k] for k in set(new_items) - set(old_items)]
        removed = [old_items[k] for k in set(old_items) - set(new_items)]
        changed = []
        for iid in set(old_items) & set(new_items):
            diffs = _dict_diff(old_items[iid], new_items[iid])
            if diffs:
                changed.append({"id": iid, "name": new_items[iid].get("name"), "changes": diffs})
        if added or removed or changed:
            mod_name = new_modules.get(mid, {}).get("name", mid)
            changes["items"][mid] = {
                "module_name": mod_name,
                "added": added,
                "removed": removed,
                "changed": changed,
            }

    return changes


def save_diff(diff: dict) -> Path | None:
    """Save diff to disk. Returns None if no meaningful changes."""
    has_changes = (
        diff["modules"]["added"]
        or diff["modules"]["removed"]
        or diff["modules"]["changed"]
        or diff["user_assignments"]
        or diff["group_assignments"]
        or diff["items"]
    )
    if not has_changes:
        return None

    settings = get_settings()
    path = settings.diffs_dir / f"{diff['to']}.json"
    path.write_text(json.dumps(diff, indent=2, default=str))
    return path


def sync() -> tuple[Path, Path | None]:
    """Full sync: fetch, snapshot, diff against previous."""
    client = SugarLearningClient()
    snapshot = fetch_snapshot(client)
    snapshot_path = save_snapshot(snapshot)

    prev = _latest_snapshot_before(snapshot_path)
    diff_path = None
    if prev:
        old = json.loads(prev.read_text())
        diff = compute_diff(old, snapshot)
        diff_path = save_diff(diff)
        if diff_path:
            print(f"Changes detected! Diff saved: {diff_path}", file=sys.stderr)
        else:
            print("No changes detected since last sync.", file=sys.stderr)
    else:
        print("First sync - no previous snapshot to compare.", file=sys.stderr)

    # Clean up per-module watch snapshots (full sync supersedes them)
    removed = clean_watch_snaps()
    if removed:
        print(f"Cleaned up {len(removed)} watch snapshot(s).", file=sys.stderr)

    return snapshot_path, diff_path


def _latest_snapshot_before(current: Path) -> Path | None:
    settings = get_settings()
    files = sorted(settings.snapshots_dir.glob("*.json"))
    files = [f for f in files if f != current]
    return files[-1] if files else None


def _dict_diff(old: dict, new: dict) -> dict:
    """Compare two dicts, return changed fields."""
    diffs = {}
    all_keys = set(old.keys()) | set(new.keys())
    for key in all_keys:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val:
            diffs[key] = {"old": old_val, "new": new_val}
    return diffs


def fetch_module_snapshot(module_id: int, client: SugarLearningClient | None = None) -> dict:
    """Fetch data for a single module and return as a watch snapshot."""
    if client is None:
        client = SugarLearningClient()

    module = client.get_module(module_id)

    try:
        users = client.get_module_users(module_id)
    except Exception:
        users = []

    try:
        groups = client.get_module_groups(module_id)
    except Exception:
        groups = []

    try:
        items = client.get_module_items(module_id)
    except Exception:
        items = []

    return {
        "timestamp": _timestamp(),
        "module_id": module_id,
        "module": module,
        "users": users,
        "groups": groups,
        "items": items,
    }


def watch_snap_path(module_id: int) -> Path:
    """Return the path for a per-module watch snapshot."""
    settings = get_settings()
    return settings.data_dir / f"snap-{module_id}.json"


def save_watch_snap(snap: dict) -> Path:
    """Save a per-module watch snapshot."""
    path = watch_snap_path(snap["module_id"])
    path.write_text(json.dumps(snap, indent=2, default=str))
    return path


def load_watch_snap(module_id: int) -> dict | None:
    """Load a previous watch snapshot, or None if it doesn't exist."""
    path = watch_snap_path(module_id)
    if path.exists():
        return json.loads(path.read_text())
    return None


def compute_watch_diff(old: dict, new: dict) -> dict:
    """Compute differences between two per-module watch snapshots."""
    changes: dict = {
        "from": old.get("timestamp", "?"),
        "to": new.get("timestamp", "?"),
        "module_id": new.get("module_id"),
        "module_changes": {},
        "user_changes": {"added": [], "removed": []},
        "group_changes": {"added": [], "removed": []},
        "item_changes": {"added": [], "removed": [], "changed": []},
    }

    # Module property changes
    module_diff = _dict_diff(old.get("module", {}), new.get("module", {}))
    if module_diff:
        changes["module_changes"] = module_diff

    # User assignment changes
    old_users = {u.get("userId") or u.get("emailAddress"): u for u in old.get("users", [])}
    new_users = {u.get("userId") or u.get("emailAddress"): u for u in new.get("users", [])}
    changes["user_changes"]["added"] = [new_users[k] for k in set(new_users) - set(old_users)]
    changes["user_changes"]["removed"] = [old_users[k] for k in set(old_users) - set(new_users)]

    # Group assignment changes
    old_groups = {str(g.get("id")): g for g in old.get("groups", [])}
    new_groups = {str(g.get("id")): g for g in new.get("groups", [])}
    changes["group_changes"]["added"] = [new_groups[k] for k in set(new_groups) - set(old_groups)]
    changes["group_changes"]["removed"] = [old_groups[k] for k in set(old_groups) - set(new_groups)]

    # Item changes
    old_items = {str(i.get("id")): i for i in old.get("items", [])}
    new_items = {str(i.get("id")): i for i in new.get("items", [])}
    changes["item_changes"]["added"] = [new_items[k] for k in set(new_items) - set(old_items)]
    changes["item_changes"]["removed"] = [old_items[k] for k in set(old_items) - set(new_items)]
    for iid in set(old_items) & set(new_items):
        diffs = _dict_diff(old_items[iid], new_items[iid])
        if diffs:
            changes["item_changes"]["changed"].append({"id": iid, "name": new_items[iid].get("name"), "changes": diffs})

    return changes


def has_watch_changes(diff: dict) -> bool:
    """Check if a watch diff has any meaningful changes."""
    return bool(
        diff.get("module_changes")
        or diff["user_changes"]["added"]
        or diff["user_changes"]["removed"]
        or diff["group_changes"]["added"]
        or diff["group_changes"]["removed"]
        or diff["item_changes"]["added"]
        or diff["item_changes"]["removed"]
        or diff["item_changes"]["changed"]
    )


def clean_watch_snaps() -> list[Path]:
    """Remove all per-module watch snapshots. Returns list of removed paths."""
    settings = get_settings()
    removed = []
    for snap_file in settings.data_dir.glob("snap-*.json"):
        snap_file.unlink()
        removed.append(snap_file)
    return removed


def format_diff(diff: dict) -> str:
    """Format a diff dict as human-readable text."""
    lines = [f"Changes from {diff['from']} to {diff['to']}:", ""]

    mods = diff["modules"]
    if mods["added"]:
        lines.append(f"  New modules ({len(mods['added'])}):")
        for m in mods["added"]:
            lines.append(f"    + {m.get('name', '?')} (ID: {m.get('id')})")
    if mods["removed"]:
        lines.append(f"  Removed modules ({len(mods['removed'])}):")
        for m in mods["removed"]:
            lines.append(f"    - {m.get('name', '?')} (ID: {m.get('id')})")
    if mods["changed"]:
        lines.append(f"  Changed modules ({len(mods['changed'])}):")
        for m in mods["changed"]:
            lines.append(f"    ~ {m.get('name', '?')} (ID: {m['id']})")
            for field, vals in m["changes"].items():
                lines.append(f"      {field}: {vals['old']} -> {vals['new']}")

    for mid, data in diff.get("user_assignments", {}).items():
        lines.append(f"  User assignments for '{data['module_name']}' (ID: {mid}):")
        for u in data.get("added", []):
            lines.append(f"    + {u.get('emailAddress', u.get('userId', '?'))}")
        for u in data.get("removed", []):
            lines.append(f"    - {u.get('emailAddress', u.get('userId', '?'))}")

    for mid, data in diff.get("group_assignments", {}).items():
        lines.append(f"  Group assignments for '{data['module_name']}' (ID: {mid}):")
        for g in data.get("added", []):
            lines.append(f"    + {g.get('name', '?')}")
        for g in data.get("removed", []):
            lines.append(f"    - {g.get('name', '?')}")

    for mid, data in diff.get("items", {}).items():
        lines.append(f"  Items for '{data['module_name']}' (ID: {mid}):")
        for i in data.get("added", []):
            lines.append(f"    + {i.get('name', '?')}")
        for i in data.get("removed", []):
            lines.append(f"    - {i.get('name', '?')}")
        for i in data.get("changed", []):
            lines.append(f"    ~ {i.get('name', '?')}")

    return "\n".join(lines)
