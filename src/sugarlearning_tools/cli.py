"""CLI entry point for SugarLearning tools."""

from __future__ import annotations

import json
from pathlib import Path

import click

from .config import get_settings


@click.group()
def cli():
    """SugarLearning data tools and tracker."""
    pass


@cli.command()
@click.option("--oauth", is_flag=True, help="Use full OAuth PKCE flow (requires registered redirect URI)")
@click.option("--token", "-t", help="Provide Bearer token directly (skip interactive prompt)")
@click.option("--refresh-token", "-r", help="Provide a refresh token (from browser localStorage)")
def login(oauth: bool, token: str | None, refresh_token: str | None):
    """Authenticate with SugarLearning.

    Default: paste a Bearer token from browser DevTools.
    Use --oauth for full OAuth PKCE flow (if redirect URI is registered).
    Use -r/--refresh-token to provide a refresh token for auto-renewal.
    """
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
def sync():
    """Fetch latest data, create snapshot, and show changes."""
    from .sync import sync as do_sync, format_diff

    snapshot_path, diff_path = do_sync()
    if diff_path:
        diff = json.loads(diff_path.read_text())
        click.echo("\n" + format_diff(diff))


@cli.command()
def diff():
    """Show the latest diff."""
    from .sync import format_diff

    settings = get_settings()
    files = sorted(settings.diffs_dir.glob("*.json"))
    if not files:
        click.echo("No diffs found. Run 'sl sync' first.")
        return
    latest = json.loads(files[-1].read_text())
    click.echo(format_diff(latest))


@cli.command()
@click.argument("module_id", type=int)
def watch(module_id: int):
    """Show assignment changes for a specific module across all diffs."""
    settings = get_settings()
    mid = str(module_id)

    # Show current assignments from latest snapshot
    snapshots = sorted(settings.snapshots_dir.glob("*.json"))
    if snapshots:
        latest = json.loads(snapshots[-1].read_text())
        users = latest.get("module_users", {}).get(mid, [])
        groups = latest.get("module_groups", {}).get(mid, [])

        # Find module name
        mod_name = mid
        for m in latest.get("modules", []):
            if str(m.get("id")) == mid:
                mod_name = m.get("name", mid)
                break

        click.echo(f"Module: {mod_name} (ID: {mid})")
        click.echo(f"\nCurrent users ({len(users)}):")
        for u in users:
            email = u.get("emailAddress", u.get("userId", "?"))
            pct = u.get("progressPercentage", 0)
            click.echo(f"  {email} — {pct}% complete")

        click.echo(f"\nCurrent groups ({len(groups)}):")
        for g in groups:
            click.echo(f"  {g.get('name', '?')} ({g.get('userCount', 0)} users)")

    # Show historical changes
    diffs = sorted(settings.diffs_dir.glob("*.json"))
    changes_found = False
    for diff_file in diffs:
        d = json.loads(diff_file.read_text())
        ua = d.get("user_assignments", {}).get(mid)
        ga = d.get("group_assignments", {}).get(mid)
        if ua or ga:
            if not changes_found:
                click.echo(f"\nAssignment history:")
                changes_found = True
            click.echo(f"\n  {d['to']}:")
            if ua:
                for u in ua.get("added", []):
                    click.echo(f"    + User: {u.get('emailAddress', u.get('userId', '?'))}")
                for u in ua.get("removed", []):
                    click.echo(f"    - User: {u.get('emailAddress', u.get('userId', '?'))}")
            if ga:
                for g in ga.get("added", []):
                    click.echo(f"    + Group: {g.get('name', '?')}")
                for g in ga.get("removed", []):
                    click.echo(f"    - Group: {g.get('name', '?')}")

    if not changes_found:
        click.echo("\nNo assignment changes recorded yet.")


@cli.command()
def history():
    """List all snapshots."""
    settings = get_settings()
    files = sorted(settings.snapshots_dir.glob("*.json"))
    if not files:
        click.echo("No snapshots found. Run 'sl sync' first.")
        return
    for f in files:
        size = f.stat().st_size
        click.echo(f"  {f.stem}  ({size:,} bytes)")


@cli.command()
@click.argument("query")
def search(query: str):
    """Search learning items. Uses Qdrant if available, otherwise searches latest snapshot."""
    # Try Qdrant first (only if collection exists)
    try:
        from qdrant_client import QdrantClient
        qc = QdrantClient(url=get_settings().qdrant_url, timeout=2)
        if qc.collection_exists(get_settings().qdrant_collection):
            from .qdrant_index import search_items
            results = search_items(query)
            if results:
            click.echo(f"Qdrant results for '{query}':\n")
            for r in results:
                score = r.get("score", 0)
                payload = r.get("payload", {})
                click.echo(f"  [{score:.3f}] {payload.get('name', '?')}")
                if payload.get("module_name"):
                    click.echo(f"          Module: {payload['module_name']}")
                if payload.get("description"):
                    desc = payload["description"][:120]
                    click.echo(f"          {desc}...")
                return
    except Exception:
        pass

    # Fallback: text search in latest snapshot
    settings = get_settings()
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
            results.append(("module", m.get("id"), m.get("name"), None))

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
                results.append(("item", item.get("id"), item.get("name"), mod_name))

    if not results:
        click.echo(f"No results for '{query}'.")
        return

    click.echo(f"Found {len(results)} result(s) for '{query}':\n")
    for kind, rid, name, mod_name in results:
        prefix = "📦" if kind == "module" else "📄"
        click.echo(f"  {prefix} [{rid}] {name}")
        if mod_name and kind == "item":
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
def backlog():
    """Show your current learning backlog."""
    from .client import SugarLearningClient

    client = SugarLearningClient()
    data = client.get_backlog()
    click.echo(f"Total items: {data.get('totalItems', 0)}")
    click.echo(f"  Completed: {data.get('totalCompletedItems', 0)}")
    click.echo(f"  Outstanding: {data.get('totalOutstandingItems', 0)}")
    click.echo(f"  Blocked: {data.get('totalBlockedItems', 0)}")

    modules = data.get("modules", [])
    if modules:
        click.echo(f"\nModules ({len(modules)}):")
        for m in modules:
            name = m.get("name", "?")
            items = m.get("items", [])
            click.echo(f"  {name} ({len(items)} items)")


if __name__ == "__main__":
    cli()
