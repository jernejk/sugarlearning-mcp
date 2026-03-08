"""CLI entry point for SugarLearning tools."""

from __future__ import annotations

import json
import re

import click

from .config import get_settings, reset_settings, _CONFIG_HOME


def _save_company_code(code: str) -> None:
    """Save company code to the config .env file."""
    env_path = _CONFIG_HOME / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    existing = env_path.read_text() if env_path.exists() else ""

    if "SL_COMPANY_CODE" in existing:
        updated = re.sub(r"SL_COMPANY_CODE=.*", f"SL_COMPANY_CODE={code}", existing)
        env_path.write_text(updated)
    else:
        with env_path.open("a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(f"SL_COMPANY_CODE={code}\n")
    reset_settings()
    click.echo(f"Company code set: {code}")


def _slugify(name: str) -> str:
    """Convert a name to a URL-friendly slug."""
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)  # strip non-alphanumeric
    s = re.sub(r"[\s_]+", "-", s)   # spaces/underscores to hyphens
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _item_url(item_id: int | str, name: str | None = None) -> str:
    """Build a SugarLearning item URL."""
    settings = get_settings()
    base = f"{settings.base_url}/{settings.company_code}/items/{item_id}"
    if name:
        base += f"/{_slugify(name)}"
    return base


def _module_url(module_id: int | str) -> str:
    """Build a SugarLearning admin module URL."""
    settings = get_settings()
    return f"{settings.base_url}/{settings.company_code}/admin/modules/{module_id}"


@click.group()
def cli():
    """SugarLearning data tools and tracker."""


@cli.command()
@click.option("--oauth", is_flag=True, help="Use full OAuth PKCE flow (requires registered redirect URI)")
@click.option("--token", "-t", help="Provide Bearer token directly (skip interactive prompt)")
@click.option("--refresh-token", "-r", help="Provide a refresh token (from browser localStorage)")
@click.option("--company", "-c", help="Set your company code (saves to config)")
def login(oauth: bool, token: str | None, refresh_token: str | None, company: str | None):
    """Authenticate with SugarLearning.

    Default: paste a Bearer token from browser DevTools.
    Use --company/-c to set your company code (e.g. sl login --company SSW).
    Use --oauth for full OAuth PKCE flow (if redirect URI is registered).
    Use -r/--refresh-token to provide a refresh token for auto-renewal.
    """
    if company:
        _save_company_code(company)

    if oauth:
        from .auth import login_oauth
        login_oauth()
    elif refresh_token:
        from .auth import login_with_refresh_token
        login_with_refresh_token(refresh_token)
    elif token:
        from .auth import login_with_token
        login_with_token(token)
    else:
        from .auth import login_with_token
        click.echo("Paste your Bearer token from browser DevTools.")
        click.echo("(Chrome: DevTools > Network > any SugarLearning API request > Authorization header)\n")
        bearer = click.prompt("Bearer token", hide_input=False)
        login_with_token(bearer)


@cli.command()
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
def sync(use_json: bool):
    """Fetch latest data, create snapshot, and show changes."""
    from .sync import sync as do_sync, format_diff

    snapshot_path, diff_path = do_sync()
    if diff_path:
        diff_data = json.loads(diff_path.read_text())
        if use_json:
            click.echo(json.dumps(diff_data, indent=2, default=str))
        else:
            click.echo("\n" + format_diff(diff_data))


@cli.command()
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
def diff(use_json: bool):
    """Show the latest diff."""
    from .sync import format_diff

    settings = get_settings()
    files = sorted(settings.diffs_dir.glob("*.json"))
    if not files:
        click.echo("No diffs found. Run 'sl sync' first.")
        return
    latest = json.loads(files[-1].read_text())
    if use_json:
        click.echo(json.dumps(latest, indent=2, default=str))
    else:
        click.echo(format_diff(latest))


@cli.command()
@click.argument("module_id", type=int)
@click.option("--limit", "-l", type=int, default=0, help="Limit number of users shown (0 = all)")
@click.option("--skip", "-s", type=int, default=0, help="Skip first N users")
@click.option("--quiet", "-q", is_flag=True, help="Only output if changes detected (useful for cron/scripts)")
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
def watch(module_id: int, limit: int, skip: int, quiet: bool, use_json: bool):
    """Watch a module for changes. Fetches live data and compares against previous watch."""
    from .sync import (
        fetch_module_snapshot,
        load_watch_snap,
        save_watch_snap,
        compute_watch_diff,
        has_watch_changes,
    )

    snap = fetch_module_snapshot(module_id)
    mod_name = snap.get("module", {}).get("name", str(module_id))

    # Compare against previous watch snapshot
    previous = load_watch_snap(module_id)
    changed = False
    diff = None
    if previous:
        diff = compute_watch_diff(previous, snap)
        changed = has_watch_changes(diff)

    # In quiet mode, skip all output if no changes (and not first watch)
    if quiet and previous and not changed:
        save_watch_snap(snap)
        return

    if use_json:
        output = {
            "module": {"id": module_id, "name": mod_name, "url": _module_url(module_id)},
            "users": snap.get("users", []),
            "groups": snap.get("groups", []),
            "items": snap.get("items", []),
            "changes": diff if changed else None,
            "first_watch": previous is None,
        }
        click.echo(json.dumps(output, indent=2, default=str))
    else:
        click.echo(f"Module: {mod_name} (ID: {module_id})")
        click.echo(f"URL:    {_module_url(module_id)}")

        # Show current users
        users = snap.get("users", [])
        total_users = len(users)
        display_users = users[skip:] if skip else users
        if limit:
            display_users = display_users[:limit]

        click.echo(f"\nCurrent users ({total_users} total, showing {len(display_users)}):")
        for u in display_users:
            email = u.get("emailAddress", u.get("userId", "?"))
            pct = u.get("progressPercentage", 0)
            click.echo(f"  {email} — {pct}% complete")

        # Show current groups
        groups = snap.get("groups", [])
        click.echo(f"\nCurrent groups ({len(groups)}):")
        for g in groups:
            click.echo(f"  {g.get('name', '?')} ({g.get('userCount', 0)} users)")

        # Show current items
        items = snap.get("items", [])
        click.echo(f"\nCurrent items ({len(items)}):")
        for item in items:
            iname = item.get("name", "?")
            iid = item.get("id", "?")
            click.echo(f"  {iname}")
            click.echo(f"    URL: {_item_url(iid, iname)}")

        # Show changes
        if previous and diff:
            if changed:
                click.echo(f"\nChanges since last watch ({previous['timestamp']}):")
                uc = diff["user_changes"]
                if uc["added"]:
                    for u in uc["added"]:
                        click.echo(f"  + User: {u.get('emailAddress', u.get('userId', '?'))}")
                if uc["removed"]:
                    for u in uc["removed"]:
                        click.echo(f"  - User: {u.get('emailAddress', u.get('userId', '?'))}")
                gc = diff["group_changes"]
                if gc["added"]:
                    for g in gc["added"]:
                        click.echo(f"  + Group: {g.get('name', '?')}")
                if gc["removed"]:
                    for g in gc["removed"]:
                        click.echo(f"  - Group: {g.get('name', '?')}")
                ic = diff["item_changes"]
                if ic["added"]:
                    for i in ic["added"]:
                        click.echo(f"  + Item: {i.get('name', '?')}")
                if ic["removed"]:
                    for i in ic["removed"]:
                        click.echo(f"  - Item: {i.get('name', '?')}")
                if ic["changed"]:
                    for i in ic["changed"]:
                        click.echo(f"  ~ Item: {i.get('name', '?')}")
                mc = diff.get("module_changes", {})
                if mc:
                    for field, vals in mc.items():
                        click.echo(f"  ~ Module {field}: {vals['old']} -> {vals['new']}")
            else:
                click.echo(f"\nNo changes since last watch ({previous['timestamp']}).")
        else:
            click.echo("\nFirst watch — snapshot saved for future comparisons.")

    # Save current snapshot for next comparison
    save_watch_snap(snap)


@cli.command()
@click.option("--limit", "-l", type=int, default=0, help="Limit number of snapshots shown (0 = all)")
@click.option("--skip", "-s", type=int, default=0, help="Skip first N snapshots")
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
def history(limit: int, skip: int, use_json: bool):
    """List all snapshots."""
    settings = get_settings()
    files = sorted(settings.snapshots_dir.glob("*.json"))
    if not files:
        click.echo("No snapshots found. Run 'sl sync' first.")
        return
    display = files[skip:] if skip else files
    if limit:
        display = display[:limit]

    if use_json:
        output = [{"name": f.stem, "size": f.stat().st_size} for f in display]
        click.echo(json.dumps(output, indent=2))
    else:
        click.echo(f"Snapshots ({len(files)} total, showing {len(display)}):\n")
        for f in display:
            size = f.stat().st_size
            click.echo(f"  {f.stem}  ({size:,} bytes)")


@cli.command()
@click.argument("query")
@click.option("--limit", "-l", type=int, default=0, help="Limit number of results (0 = all)")
@click.option("--status", type=click.Choice(["all", "outstanding", "completed", "blocked"], case_sensitive=False), default="all", help="Filter by backlog status (searches your backlog instead of snapshot)")
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
def search(query: str, limit: int, status: str, use_json: bool):
    """Search learning items. Uses Qdrant if available, otherwise searches latest snapshot.

    With --status, searches your personal backlog filtered by completion state.
    """
    settings = get_settings()

    # If status filter is set, search within backlog items
    if status != "all":
        _search_backlog(query, status, limit, use_json=use_json)
        return

    # Try Qdrant first (only if collection exists)
    try:
        from qdrant_client import QdrantClient
        qc = QdrantClient(url=settings.qdrant_url, timeout=2)
        if qc.collection_exists(settings.qdrant_collection):
            from .qdrant_index import search_items
            qdrant_limit = limit if limit else 20
            results = search_items(query, limit=qdrant_limit)
            if results:
                if use_json:
                    click.echo(json.dumps(results, indent=2, default=str))
                else:
                    click.echo(f"Qdrant results for '{query}':\n")
                    for r in results:
                        score = r.get("score", 0)
                        payload = r.get("payload", {})
                        rid = payload.get("id", "?")
                        rname = payload.get("name", "?")
                        rtype = payload.get("type", "item")
                        prefix = "📦" if rtype == "module" else "📄"
                        click.echo(f"  {prefix} [{score:.3f}] {rname}")
                        if payload.get("module_name"):
                            click.echo(f"          Module: {payload['module_name']}")
                        if rtype == "module":
                            click.echo(f"          URL: {_module_url(rid)}")
                        else:
                            click.echo(f"          URL: {_item_url(rid, rname)}")
                return
    except Exception:
        pass

    # Fallback: text search in latest snapshot
    snapshots = sorted(settings.snapshots_dir.glob("*.json"))
    if not snapshots:
        click.echo("No snapshots found. Run 'sl sync' first.")
        return

    snapshot = json.loads(snapshots[-1].read_text())
    terms = query.lower().split()
    results = []

    # Search modules
    for m in snapshot.get("modules", []):
        name = (m.get("name") or "").lower()
        desc = (m.get("description") or "").lower()
        if any(t in name or t in desc for t in terms):
            results.append(("module", m.get("id"), m.get("name"), None, None))

    # Search learning items
    for mid, items in snapshot.get("module_items", {}).items():
        mod_name = mid
        for m in snapshot.get("modules", []):
            if str(m.get("id")) == mid:
                mod_name = m.get("name", mid)
                break
        for item in items:
            name = (item.get("name") or "").lower()
            desc = (item.get("description") or "").lower()
            if any(t in name or t in desc for t in terms):
                results.append(("item", item.get("id"), item.get("name"), mod_name, None))

    _display_search_results(results, query, limit, use_json=use_json)


def _search_backlog(query: str, status: str, limit: int, use_json: bool = False):
    """Search within the user's backlog items, filtered by status."""
    from .client import SugarLearningClient

    client = SugarLearningClient()
    data = client.get_backlog()

    status_map = {"outstanding": "Outstanding", "completed": "Completed", "blocked": "Blocked"}
    target_state = status_map[status]
    terms = query.lower().split()
    results = []

    for m in data.get("modules", []):
        mod_name = m.get("name", "?")
        for item in m.get("items", []):
            if item.get("state") != target_state:
                continue
            iname = (item.get("itemName") or "").lower()
            if any(t in iname for t in terms):
                results.append(("item", item.get("itemId"), item.get("itemName"), mod_name, item.get("state")))

    _display_search_results(results, query, limit, status_label=status, use_json=use_json)


def _display_search_results(results: list, query: str, limit: int, status_label: str | None = None, use_json: bool = False):
    """Render search results."""
    display = results[:limit] if limit else results

    if use_json:
        output = [
            {
                "type": kind,
                "id": rid,
                "name": name,
                "module": mod_name,
                "status": state,
                "url": _module_url(rid) if kind == "module" else _item_url(rid, name),
            }
            for kind, rid, name, mod_name, state in display
        ]
        click.echo(json.dumps(output, indent=2, default=str))
        return

    if not results:
        extra = f" with status '{status_label}'" if status_label else ""
        click.echo(f"No results for '{query}'{extra}.")
        return

    extra = f" ({status_label})" if status_label else ""
    count_msg = f"Found {len(results)} result(s) for '{query}'{extra}"
    if limit and limit < len(results):
        count_msg += f" (showing {len(display)})"
    click.echo(count_msg + ":\n")

    for kind, rid, name, mod_name, state in display:
        prefix = "📦" if kind == "module" else "📄"
        state_tag = f" [{state}]" if state else ""
        click.echo(f"  {prefix} [{rid}] {name}{state_tag}")
        if kind == "module":
            click.echo(f"          URL: {_module_url(rid)}")
        else:
            click.echo(f"          URL: {_item_url(rid, name)}")
            if mod_name:
                click.echo(f"          Module: {mod_name}")


@cli.command()
def index():
    """Build/rebuild Qdrant index from latest snapshot."""
    from .qdrant_index import build_index

    settings = get_settings()
    files = sorted(settings.snapshots_dir.glob("*.json"))
    if not files:
        click.echo("No snapshots found. Run 'sl sync' first.")
        return
    snapshot = json.loads(files[-1].read_text())
    build_index(snapshot)
    click.echo("Qdrant index built successfully.")


@cli.command()
def mcp():
    """Start the MCP server."""
    from .mcp_server import mcp as mcp_server

    mcp_server.run()


@cli.command()
@click.option("--limit", "-l", type=int, default=0, help="Limit number of modules shown (0 = all)")
@click.option("--skip", "-s", type=int, default=0, help="Skip first N modules")
@click.option("--status", type=click.Choice(["all", "outstanding", "completed", "blocked"], case_sensitive=False), default="all", help="Filter items by status")
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
def backlog(limit: int, skip: int, status: str, use_json: bool):
    """Show your current learning backlog."""
    from .client import SugarLearningClient

    client = SugarLearningClient()
    data = client.get_backlog()

    modules = data.get("modules", [])

    # Filter items by status within each module
    if status != "all":
        status_map = {"outstanding": "Outstanding", "completed": "Completed", "blocked": "Blocked"}
        target_state = status_map[status]
        filtered_modules = []
        for m in modules:
            items = [i for i in m.get("items", []) if i.get("state") == target_state]
            if items:
                fm = dict(m)
                fm["items"] = items
                filtered_modules.append(fm)
        modules = filtered_modules

    display = modules[skip:] if skip else modules
    if limit:
        display = display[:limit]

    if use_json:
        output = {
            "totalItems": data.get("totalItems", 0),
            "totalCompletedItems": data.get("totalCompletedItems", 0),
            "totalOutstandingItems": data.get("totalOutstandingItems", 0),
            "totalBlockedItems": data.get("totalBlockedItems", 0),
            "status_filter": status,
            "modules": display,
        }
        click.echo(json.dumps(output, indent=2, default=str))
        return

    click.echo(f"Total items: {data.get('totalItems', 0)}")
    click.echo(f"  Completed: {data.get('totalCompletedItems', 0)}")
    click.echo(f"  Outstanding: {data.get('totalOutstandingItems', 0)}")
    click.echo(f"  Blocked: {data.get('totalBlockedItems', 0)}")

    if status != "all":
        click.echo(f"\n  Showing: {status} items only")

    if display:
        total_items = sum(len(m.get("items", [])) for m in modules)
        click.echo(f"\nModules ({len(modules)} with matching items, {total_items} items total, showing {len(display)} modules):")
        for m in display:
            name = m.get("name", "?")
            items = m.get("items", [])
            mid = m.get("id", "?")
            click.echo(f"  {name} ({len(items)} items)")
            click.echo(f"    URL: {_module_url(mid)}")
            for item in items:
                iname = item.get("itemName", "?")
                iid = item.get("itemId", "?")
                state = item.get("state", "?")
                click.echo(f"      [{state}] {iname}")
                click.echo(f"        URL: {_item_url(iid, iname)}")
    else:
        click.echo(f"\nNo {status} items found.")


@cli.command()
@click.option("--group", "-g", default="all", help="Filter by group ID (default: all)")
@click.option("--limit", "-l", type=int, default=0, help="Limit number of users shown (0 = all)")
@click.option("--all", "show_all", is_flag=True, help="Include users with 0%% progress")
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
def leaderboard(group: str, limit: int, show_all: bool, use_json: bool):
    """Show company leaderboard rankings."""
    from .client import SugarLearningClient

    client = SugarLearningClient()
    data = client.get_leaderboard(group_id=group)

    # By default, hide 0% progress users (matching the UI checkbox)
    if not show_all:
        data = [u for u in data if u.get("percentageOfPointEarned", 0) > 0]

    display = data[:limit] if limit else data

    if use_json:
        click.echo(json.dumps(display, indent=2, default=str))
        return

    click.echo(f"Leaderboard ({len(data)} users{', showing ' + str(len(display)) if limit else ''}):\n")
    click.echo(f"{'#':>4}  {'User':<30}  {'Progress':>10}  {'Points':>7}  {'Badges':>7}")
    click.echo(f"{'—' * 4}  {'—' * 30}  {'—' * 10}  {'—' * 7}  {'—' * 7}")
    for u in display:
        pos = u.get("position", "?")
        name = u.get("fullName") or u.get("userNameAlias", "?")
        pct = u.get("percentageOfPointEarned", 0)
        points = u.get("totalPointsEarned", 0)
        badges = u.get("totalBadges", 0)
        click.echo(f"{pos:>4}  {name:<30}  {pct:>9}%  {points:>7}  {badges:>7}")


@cli.command()
@click.argument("user_alias", required=False)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
def badges(user_alias: str | None, use_json: bool):
    """Show badges earned by a user. Defaults to current user."""
    from .client import SugarLearningClient

    client = SugarLearningClient()
    if user_alias:
        profile = client.get_user_profile(user_alias)
    else:
        profile = client.get_my_profile()

    badge_list = profile.get("badges", [])
    user_name = profile.get("firstName", "") + " " + profile.get("lastName", "")
    user_name = user_name.strip() or profile.get("userNameAlias", "?")

    if use_json:
        click.echo(json.dumps(badge_list, indent=2, default=str))
        return

    if not badge_list:
        click.echo(f"{user_name} has no badges yet.")
        return

    click.echo(f"Badges for {user_name} ({len(badge_list)} total):\n")
    for b in badge_list:
        mod_name = b.get("moduleName", "?")
        granted = b.get("grantedText") or b.get("grantedDateTimeText", "?")
        losing = b.get("losingText")
        line = f"  🏅 {mod_name}  (earned {granted})"
        if losing:
            line += f"  ⚠️  expiring {losing}"
        click.echo(line)


@cli.command()
@click.argument("user_alias", required=False)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
def profile(user_alias: str | None, use_json: bool):
    """Show user profile with stats, rank, and badges. Defaults to current user."""
    from .client import SugarLearningClient

    client = SugarLearningClient()
    if user_alias:
        prof = client.get_user_profile(user_alias)
    else:
        prof = client.get_my_profile()

    alias = prof.get("userNameAlias", user_alias or "?")
    full_name = (prof.get("firstName", "") + " " + prof.get("lastName", "")).strip()
    badge_list = prof.get("badges", [])

    # Find this user's leaderboard entry for rank/points/stats
    lb_entry = None
    try:
        lb = client.get_leaderboard()
        for entry in lb:
            if (entry.get("userNameAlias") or "").lower() == alias.lower():
                lb_entry = entry
                break
    except Exception:
        pass

    if use_json:
        output = {
            "alias": alias,
            "fullName": full_name,
            "badges": badge_list,
            "leaderboard": lb_entry,
        }
        click.echo(json.dumps(output, indent=2, default=str))
        return

    click.echo(f"Profile: {full_name or alias}")
    click.echo(f"  Alias: {alias}")

    if lb_entry:
        click.echo(f"  Rank: #{lb_entry.get('position', '?')}")
        click.echo(f"  Progress: {lb_entry.get('percentageOfPointEarned', 0)}%")
        click.echo(f"  Points: {lb_entry.get('totalPointsEarned', 0)} / {lb_entry.get('totalPoints', 0)}")
        click.echo(f"  Completed: {lb_entry.get('totalCompleted', 0)} / {lb_entry.get('totalAssigned', 0)} items")
        click.echo(f"  Badges: {lb_entry.get('totalBadges', 0)}")
        if lb_entry.get("lastCompletedDateTime"):
            click.echo(f"  Last completed: {lb_entry['lastCompletedDateTime']}")
        if lb_entry.get("joinedDateTime"):
            click.echo(f"  Joined: {lb_entry['joinedDateTime']}")
        groups = lb_entry.get("groupNames", [])
        if groups:
            click.echo(f"  Groups: {', '.join(groups)}")
    else:
        click.echo(f"  Badges: {len(badge_list)}")

    if badge_list:
        click.echo(f"\n  Recent badges:")
        for b in badge_list[:5]:
            click.echo(f"    🏅 {b.get('moduleName', '?')} ({b.get('grantedText', '?')})")
        if len(badge_list) > 5:
            click.echo(f"    ... and {len(badge_list) - 5} more")


if __name__ == "__main__":
    cli()
