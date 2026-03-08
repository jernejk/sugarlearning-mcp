# Unofficial SugarLearning CLI + MCP

> **Unofficial** community-built CLI tools, change tracker, and MCP server for [SugarLearning](https://my.sugarlearning.com).
>
> This project is not affiliated with or endorsed by SugarLearning. It uses the existing SugarLearning API with your own credentials.

SugarLearning is a learning management system for tracking employee training modules and learning items.

## What it does

- **MCP Server** — Exposes SugarLearning data to AI agents (Claude Code, VS Code Copilot, Codex, LM Studio) via the [Model Context Protocol](https://modelcontextprotocol.io/)
- **Change Tracking** — Takes periodic snapshots of modules, items, and assignments, then computes diffs to detect changes over time
- **Module Monitoring** — Watch specific modules for assignment changes (who was added/removed)
- **Semantic Search** — Optional Qdrant vector index for natural language search across all learning content

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- A SugarLearning account with admin access
- (Optional) [Docker](https://www.docker.com/) for Qdrant vector search

## Quick Start

### 1. Install globally (Recommended)

```bash
git clone https://github.com/jernejk/sugarlearning-mcp.git
cd sugarlearning-mcp
uv tool install .
```

This makes the `sl` command available system-wide — run it from any directory.

To update after pulling new changes:

```bash
cd sugarlearning-mcp
git pull
uv tool install --force --reinstall .
```

To uninstall:

```bash
uv tool uninstall sugarlearning-tools
```

<details>
<summary>Alternative: Run from project directory without global install</summary>

```bash
git clone https://github.com/jernejk/sugarlearning-mcp.git
cd sugarlearning-mcp
uv sync
```

Then prefix all commands with `uv run`:

```bash
uv run sl login
uv run sl sync
uv run sl search "training"
```

</details>

### 2. Authenticate

The easiest way is to set your company code and paste a Bearer token in one step:

```bash
sl login --company YourCompany
```

This sets your company code and prompts you to paste an access token. Your user ID is auto-detected from the token. To get a token:
1. Open https://my.sugarlearning.com and log in
2. Open Chrome DevTools (F12) > Network tab
3. Find any API request to `my.sugarlearning.com`
4. Copy the `Authorization` header value

For **auto-renewal** (recommended), provide a refresh token:

```bash
sl login --company YourCompany -r YOUR_REFRESH_TOKEN
```

To get your refresh token from the browser:
1. Open Chrome DevTools > Application > Local Storage > `https://my.sugarlearning.com`
2. Find the `refresh_token` key and copy its value

Refresh tokens last much longer than access tokens and will auto-renew your session.

> **Advanced:** You can also configure via `.env` file — see [Configuration](#configuration).

### 3. First sync

```bash
sl sync
```

This fetches all modules, items, and assignments, then saves a snapshot. Run it again later to detect changes.

## CLI Reference

| Command | Description |
|---------|-------------|
| `sl login --company CODE` | Set company code and authenticate (paste Bearer token) |
| `sl login -r TOKEN` | Authenticate with refresh token (auto-renewal) |
| `sl login --oauth` | OAuth PKCE flow (requires registered redirect URI) |
| `sl <command> --json` | Output as JSON instead of human-readable text |
| `sl sync` | Fetch data, create snapshot, show changes since last sync |
| `sl diff` | Show the most recent diff |
| `sl watch MODULE_ID` | Show current assignments and change history for a module |
| `sl history` | List all saved snapshots |
| `sl backlog` | Show your learning backlog |
| `sl search QUERY` | Search modules and items (Qdrant or text fallback) |
| `sl leaderboard` | Show company leaderboard rankings |
| `sl badges [USER]` | Show badges earned by a user |
| `sl profile [USER]` | Show user profile with rank and stats |
| `sl index` | Build/rebuild Qdrant vector index |
| `sl mcp` | Start the MCP server (stdio) |

Most commands support `--limit N` and `--skip N` for pagination:

```bash
sl search "training" --limit 5
sl backlog --limit 10 --skip 5
sl watch 6307 --limit 20
sl history --limit 5
```

### Status Filtering

Filter your backlog by completion status:

```bash
sl backlog --status outstanding    # Items you still need to do
sl backlog --status completed      # Items you've finished
sl backlog --status blocked        # Items that are blocked
```

Combine status filtering with search to find specific items in your backlog:

```bash
sl search "training" --status completed     # Completed training items
sl search "security" --status outstanding   # Outstanding security items
```

### Leaderboard, Badges & Profile

See how you and your team are tracking:

```bash
sl leaderboard                    # Company rankings (hides 0% users)
sl leaderboard --all              # Include users with 0% progress
sl leaderboard --group 5 --limit 10  # Top 10 in a specific group

sl badges                         # Your earned badges
sl badges jk                     # Another user's badges

sl profile                        # Your profile with rank & stats
sl profile jk                    # Another user's profile
```

### JSON Output

Add `--json` to any command for machine-readable output:

```bash
sl backlog --status outstanding --json
sl search "training" --json
sl watch 6307 --json
sl diff --json
sl leaderboard --json
sl profile --json
```

### Examples

Watch for assignment changes on the "Spec Reviews" module:

```bash
sl watch 6307
```

Search for training-related content (includes clickable URLs for each result):

```bash
sl search "training conferences"
```

Show your outstanding backlog items with URLs:

```bash
sl backlog --status outstanding --limit 10
```

## MCP Server

The MCP server exposes SugarLearning data to AI agents via stdio transport. It provides these tools:

| Tool | Description |
|------|-------------|
| `list_modules` | List all learning modules with metadata |
| `get_module` | Get detailed info about a specific module |
| `get_module_users` | Get users assigned to a module with progress |
| `get_module_groups` | Get groups assigned to a module |
| `get_module_items` | Get learning items within a module |
| `get_backlog` | Get a user's learning backlog |
| `get_recent_changes` | Get recent change diffs from local tracking |
| `search_learning` | Semantic search across learning content |
| `get_module_list` | Get module list (employee view) |
| `get_leaderboard` | Get company leaderboard rankings |
| `get_user_profile` | Get a user's profile with badges |
| `get_user_badges` | Get badges earned by a user |

### Claude Code

Add to your Claude Code MCP settings (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "sugarlearning": {
      "command": "sl",
      "args": ["mcp"]
    }
  }
}
```

> **Note:** This requires the global install (`uv tool install .`). If using `uv run` instead, use `"command": "uv", "args": ["run", "--directory", "/path/to/sugarlearning-mcp", "sl", "mcp"]`.

Then ask Claude things like:
- "What modules are available in SugarLearning?"
- "Who is assigned to the Spec Reviews module?"
- "What's in my learning backlog?"
- "Have there been any recent changes to learning modules?"
- "Who's leading the company leaderboard?"
- "What badges has jk earned?"
- "Show me my SugarLearning profile and rank"

### VS Code (Copilot / Continue)

Add to your VS Code settings (`.vscode/settings.json` or user settings):

```json
{
  "mcp": {
    "servers": {
      "sugarlearning": {
        "command": "sl",
        "args": ["mcp"]
      }
    }
  }
}
```

### Codex (OpenAI CLI)

Codex supports MCP servers via its config. Add to your Codex config:

```json
{
  "mcpServers": {
    "sugarlearning": {
      "command": "sl",
      "args": ["mcp"]
    }
  }
}
```

### LM Studio

LM Studio supports MCP servers in its agent mode. Configure a new MCP server:

- **Name**: SugarLearning
- **Command**: `sl`
- **Arguments**: `mcp`
- **Transport**: stdio

## Qdrant Vector Search (Optional)

For semantic search across all learning content:

### 1. Start Qdrant

```bash
docker run -p 6333:6333 qdrant/qdrant
```

### 2. Build the index

```bash
sl index
```

This embeds all module names, descriptions, and learning items using `all-MiniLM-L6-v2` (runs locally, no API key needed).

### 3. Search

```bash
sl search "training conferences"
```

The MCP server's `search_learning` tool will also use Qdrant when available, falling back to text matching otherwise.

## Change Tracking

Each `sl sync` creates a timestamped JSON snapshot in `data/snapshots/`. When a previous snapshot exists, it computes a diff detecting:

- New/removed modules
- Changed module properties (name, description, manager, etc.)
- User assignment changes (who was added/removed from each module)
- Group assignment changes
- Learning item additions/removals/changes

Diffs are saved to `data/diffs/` and can be reviewed with `sl diff` or accessed via the MCP `get_recent_changes` tool.

### Automated syncing

Set up a cron job or scheduled task to run `sl sync` periodically:

```bash
# Every hour
0 * * * * cd /path/to/sugarlearning-mcp && sl sync >> /tmp/sl-sync.log 2>&1
```

## Project Structure

```
sugarlearning-mcp/
├── src/sugarlearning_tools/
│   ├── auth.py           # OAuth PKCE + token management
│   ├── cli.py            # Click CLI entry point
│   ├── client.py         # SugarLearning API client
│   ├── config.py         # Pydantic settings (.env)
│   ├── mcp_server.py     # FastMCP server
│   ├── models.py         # Pydantic models
│   ├── qdrant_index.py   # Qdrant vector indexing
│   └── sync.py           # Snapshot + diff engine
├── tests/                # pytest test suite
├── data/
│   ├── snapshots/        # JSON snapshots (gitignored)
│   └── diffs/            # Change diffs (gitignored)
├── .env.example          # Configuration template
└── pyproject.toml        # Project definition
```

## Configuration

All settings use the `SL_` prefix and can be set via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `SL_COMPANY_CODE` | *(required)* | Your SugarLearning company/tenant code |
| `SL_USER_ID` | *(auto-detected)* | Your user identifier (extracted from login token if not set) |
| `SL_BASE_URL` | `https://my.sugarlearning.com` | SugarLearning API base URL |
| `SL_IDENTITY_AUTHORITY` | `https://identity.ssw.com.au` | OAuth identity server |
| `SL_CLIENT_ID` | `ssw-sugarlearning-client` | OAuth client ID |
| `SL_QDRANT_URL` | `http://localhost:6333` | Qdrant server URL |
| `SL_QDRANT_COLLECTION` | `sugarlearning` | Qdrant collection name |

## Running Tests

```bash
uv run --extra dev pytest
```

## License

MIT
