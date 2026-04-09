# AI Agent Guidelines for sugarlearning-mcp

## Project Overview

Unofficial community-built CLI + MCP server for [SugarLearning](https://my.sugarlearning.com). Python 3.12+, uses `uv` for package management, Click for the CLI, FastMCP for the MCP server, and Playwright for browser-based login.

## Architecture

- `src/sugarlearning_tools/`
  - `auth.py` — OAuth PKCE, browser login (Playwright), token storage
  - `cli.py` — Click CLI entry point (`sl` command)
  - `client.py` — SugarLearning HTTP API client
  - `config.py` — Pydantic settings (env + `.env`)
  - `mcp_server.py` — FastMCP server exposing MCP tools
  - `models.py` — Pydantic models for API responses
  - `sync.py` — Snapshot + diff engine
  - `qdrant_index.py` — Optional Qdrant vector index
- `tests/` — pytest suite

## Key Patterns

- **Login flow**: `sl login` defaults to `login_with_browser` (Playwright), with `--manual`, `-t/--token`, `-r/--refresh-token` and `--oauth` fallbacks. `browser` is an optional dep group so the base install stays lightweight.
- **Config precedence**: CLI flags → `~/.config/sugarlearning/config.json` → environment (`SL_*`) → `.env`.
- **MCP tools**: defined in `mcp_server.py`, mirror the CLI command semantics.

## Documentation & Examples

**⚠️ Never use real client, project, or repo names in documentation, READMEs, example commands, tests, or commit messages.** The only fictional placeholder allowed in this repo is **Northwind** (the canonical sample dataset).

Examples of what **not** to write:
- Real SugarLearning company codes (e.g. actual customer tenants)
- Real user IDs or email addresses from your organization
- Real GitHub owner/repo slugs that belong to customer work
- Real module or learning item titles scraped from a live tenant

Use these placeholders instead:
- Company code: `YourCompany` or `NWIND`
- User alias: `jk` (the repo owner's own alias is fine as an example)
- Module ID: any small integer (e.g. `6307`)
- Item ID: any small integer (e.g. `8291`, `15108`)
- Example titles: "Spec Reviews", "training", "security" — generic topics

Before committing docs, grep the working tree for telltale strings:

```bash
git grep -i -E 'real-customer-name|real-company-code' -- ':!AGENTS.md'
```

## Development

```bash
# Install dev + browser extras
uv pip install -e '.[dev,browser]'
playwright install chromium

# Run tests
uv run --extra dev pytest

# Run the CLI during development
uv run sl --help
uv run sl login
uv run sl sync
```

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/)-ish style — short imperative subject lines. Follow existing commit history for tone. Never reference customer-specific context in commit messages.
