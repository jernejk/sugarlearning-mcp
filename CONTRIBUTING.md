# Contributing

Thanks for your interest in contributing to SugarLearning MCP!

## Development Setup

1. Clone the repo and install with dev dependencies:

```bash
git clone https://github.com/jernejk/sugarlearning-mcp.git
cd sugarlearning-mcp
uv sync --extra dev
```

2. Copy the example config:

```bash
cp .env.example .env
# Edit .env with your SugarLearning credentials
```

## Running Tests

```bash
uv run --extra dev pytest -v
```

Tests cover the core logic (diff computation, API response normalization, JWT handling) without requiring network access or authentication.

## Code Style

- Python 3.12+ with type hints
- Use `from __future__ import annotations` for forward references
- Keep modules focused and small
- Prefer simple, readable code over abstractions

## Adding New CLI Commands

1. Add the command function in `src/sugarlearning_tools/cli.py`
2. Use Click decorators (`@cli.command()`, `@click.argument()`, `@click.option()`)
3. Import heavy dependencies inside the function body (lazy imports)

## Adding New MCP Tools

1. Add the tool function in `src/sugarlearning_tools/mcp_server.py`
2. Use the `@mcp.tool` decorator
3. Write clear docstrings — they become the tool description visible to AI agents
4. Return JSON-serializable data (dicts/lists)

## Adding New API Endpoints

1. Add the method in `src/sugarlearning_tools/client.py`
2. Use `self._get()` or `self._post()` — they handle auth and response normalization automatically
3. The API returns PascalCase keys which are auto-converted to camelCase

## Pull Requests

- Keep PRs focused on a single change
- Include tests for new functionality
- Update the README if adding new commands or tools
- Run `uv run --extra dev pytest` before submitting
