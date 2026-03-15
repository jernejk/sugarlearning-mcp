"""Tests for CLI commands using Click's CliRunner.

All API calls are mocked — no real network access needed.
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from sugarlearning_tools.cli import cli


# --- Fixtures ---

FAKE_SNAPSHOT = {
    "timestamp": "2025-01-01T00-00-00",
    "modules": [
        {"id": 1, "name": "Induction", "description": "New starter induction"},
        {"id": 2, "name": "Security Training", "description": "Annual security"},
    ],
    "module_users": {"1": [{"userId": "u1", "emailAddress": "alice@test.com"}]},
    "module_groups": {"1": [{"id": 10, "name": "Devs", "userCount": 5}]},
    "module_items": {
        "1": [
            {"id": 100, "name": "Read the handbook", "description": "Employee handbook"},
            {"id": 101, "name": "Complete training", "description": "Finish all modules"},
        ],
        "2": [
            {"id": 200, "name": "Security awareness", "description": "Security basics"},
        ],
    },
}

FAKE_DIFF = {
    "from": "2025-01-01T00-00-00",
    "to": "2025-01-02T00-00-00",
    "modules": {
        "added": [{"name": "New Module", "id": 99}],
        "removed": [],
        "changed": [],
    },
    "user_assignments": {},
    "group_assignments": {},
    "items": {},
}

FAKE_WATCH_SNAP = {
    "timestamp": "2025-01-01T00-00-00",
    "module_id": 6307,
    "module": {"id": 6307, "name": "Spec Reviews"},
    "users": [
        {"userId": "u1", "emailAddress": "alice@test.com", "progressPercentage": 50},
        {"userId": "u2", "emailAddress": "bob@test.com", "progressPercentage": 100},
    ],
    "groups": [{"id": 10, "name": "Devs", "userCount": 5}],
    "items": [{"id": 300, "name": "Review checklist"}],
}

FAKE_BACKLOG = {
    "totalItems": 5,
    "totalCompletedItems": 2,
    "totalOutstandingItems": 2,
    "totalBlockedItems": 1,
    "modules": [
        {
            "id": 1,
            "name": "Induction",
            "items": [
                {"itemId": 100, "itemName": "Read handbook", "state": "Completed"},
                {"itemId": 101, "itemName": "Setup dev env", "state": "Assigned"},
            ],
        },
        {
            "id": 2,
            "name": "Security",
            "items": [
                {"itemId": 200, "itemName": "Security training", "state": "Assigned"},
                {"itemId": 201, "itemName": "Phishing quiz", "state": "Completed"},
                {"itemId": 202, "itemName": "Access review", "state": "Blocked"},
            ],
        },
    ],
}


def _setup_snapshots(tmp_path: Path) -> Path:
    """Write a fake snapshot file and return its directory."""
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(parents=True)
    snap_file = snap_dir / "2025-01-01T00-00-00.json"
    snap_file.write_text(json.dumps(FAKE_SNAPSHOT))
    return snap_dir


def _setup_diffs(tmp_path: Path) -> Path:
    """Write a fake diff file and return its directory."""
    diff_dir = tmp_path / "diffs"
    diff_dir.mkdir(parents=True)
    diff_file = diff_dir / "2025-01-02T00-00-00.json"
    diff_file.write_text(json.dumps(FAKE_DIFF))
    return diff_dir


# --- diff command ---


def test_diff_no_diffs(tmp_path, monkeypatch):
    """diff with no diffs should show a message."""
    settings = MagicMock()
    settings.diffs_dir = tmp_path / "empty"
    settings.diffs_dir.mkdir()
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: settings)

    runner = CliRunner()
    result = runner.invoke(cli, ["diff"])
    assert result.exit_code == 0
    assert "No diffs found" in result.output


def test_diff_shows_latest(tmp_path, monkeypatch):
    """diff should show the latest diff."""
    diff_dir = _setup_diffs(tmp_path)
    settings = MagicMock()
    settings.diffs_dir = diff_dir
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: settings)

    runner = CliRunner()
    result = runner.invoke(cli, ["diff"])
    assert result.exit_code == 0
    assert "New Module" in result.output


def test_diff_json_output(tmp_path, monkeypatch):
    """diff --json should output valid JSON."""
    diff_dir = _setup_diffs(tmp_path)
    settings = MagicMock()
    settings.diffs_dir = diff_dir
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: settings)

    runner = CliRunner()
    result = runner.invoke(cli, ["diff", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["modules"]["added"][0]["name"] == "New Module"


# --- history command ---


def test_history_no_snapshots(tmp_path, monkeypatch):
    settings = MagicMock()
    settings.snapshots_dir = tmp_path / "empty"
    settings.snapshots_dir.mkdir()
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: settings)

    runner = CliRunner()
    result = runner.invoke(cli, ["history"])
    assert result.exit_code == 0
    assert "No snapshots found" in result.output


def test_history_lists_snapshots(tmp_path, monkeypatch):
    snap_dir = _setup_snapshots(tmp_path)
    settings = MagicMock()
    settings.snapshots_dir = snap_dir
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: settings)

    runner = CliRunner()
    result = runner.invoke(cli, ["history"])
    assert result.exit_code == 0
    assert "2025-01-01T00-00-00" in result.output


def test_history_json(tmp_path, monkeypatch):
    snap_dir = _setup_snapshots(tmp_path)
    settings = MagicMock()
    settings.snapshots_dir = snap_dir
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: settings)

    runner = CliRunner()
    result = runner.invoke(cli, ["history", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["name"] == "2025-01-01T00-00-00"


def test_history_limit(tmp_path, monkeypatch):
    """--limit should restrict output."""
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(parents=True)
    for i in range(5):
        (snap_dir / f"snap-{i}.json").write_text("{}")
    settings = MagicMock()
    settings.snapshots_dir = snap_dir
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: settings)

    runner = CliRunner()
    result = runner.invoke(cli, ["history", "--limit", "2", "--json"])
    data = json.loads(result.output)
    assert len(data) == 2


# --- search command (snapshot fallback) ---


def test_search_no_snapshots(tmp_path, monkeypatch):
    settings = MagicMock()
    settings.snapshots_dir = tmp_path / "empty"
    settings.snapshots_dir.mkdir()
    settings.qdrant_url = "http://localhost:6333"
    settings.qdrant_collection = "test"
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: settings)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "anything"])
    assert result.exit_code == 0
    assert "No snapshots found" in result.output


def test_search_finds_modules(tmp_path, monkeypatch):
    snap_dir = _setup_snapshots(tmp_path)
    settings = MagicMock()
    settings.snapshots_dir = snap_dir
    settings.qdrant_url = "http://localhost:6333"
    settings.qdrant_collection = "test"
    settings.base_url = "https://my.sugarlearning.com"
    settings.company_code = "Zava"
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: settings)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "induction"])
    assert result.exit_code == 0
    assert "Induction" in result.output


def test_search_finds_items(tmp_path, monkeypatch):
    snap_dir = _setup_snapshots(tmp_path)
    settings = MagicMock()
    settings.snapshots_dir = snap_dir
    settings.qdrant_url = "http://localhost:6333"
    settings.qdrant_collection = "test"
    settings.base_url = "https://my.sugarlearning.com"
    settings.company_code = "Zava"
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: settings)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "handbook"])
    assert result.exit_code == 0
    assert "Read the handbook" in result.output


def test_search_json_output(tmp_path, monkeypatch):
    snap_dir = _setup_snapshots(tmp_path)
    settings = MagicMock()
    settings.snapshots_dir = snap_dir
    settings.qdrant_url = "http://localhost:6333"
    settings.qdrant_collection = "test"
    settings.base_url = "https://my.sugarlearning.com"
    settings.company_code = "Zava"
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: settings)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "security", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) >= 1
    assert any(r["name"] == "Security Training" for r in data)


def test_search_no_results(tmp_path, monkeypatch):
    snap_dir = _setup_snapshots(tmp_path)
    settings = MagicMock()
    settings.snapshots_dir = snap_dir
    settings.qdrant_url = "http://localhost:6333"
    settings.qdrant_collection = "test"
    settings.base_url = "https://my.sugarlearning.com"
    settings.company_code = "Zava"
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: settings)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "xyznonexistent"])
    assert result.exit_code == 0
    assert "No results" in result.output


def test_search_limit(tmp_path, monkeypatch):
    snap_dir = _setup_snapshots(tmp_path)
    settings = MagicMock()
    settings.snapshots_dir = snap_dir
    settings.qdrant_url = "http://localhost:6333"
    settings.qdrant_collection = "test"
    settings.base_url = "https://my.sugarlearning.com"
    settings.company_code = "Zava"
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: settings)

    runner = CliRunner()
    # "training" matches both "Security Training" module and "Complete training" item
    result = runner.invoke(cli, ["search", "training", "--limit", "1", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1


# --- watch command ---


def test_watch_first_run(monkeypatch):
    """First watch should show 'First watch' message."""
    monkeypatch.setattr(
        "sugarlearning_tools.cli.get_settings",
        lambda: MagicMock(base_url="https://my.sugarlearning.com", company_code="Zava"),
    )

    with patch("sugarlearning_tools.sync.fetch_module_snapshot", return_value=FAKE_WATCH_SNAP), \
         patch("sugarlearning_tools.sync.load_watch_snap", return_value=None), \
         patch("sugarlearning_tools.sync.save_watch_snap"):
        runner = CliRunner()
        result = runner.invoke(cli, ["watch", "6307"])
        assert result.exit_code == 0
        assert "Spec Reviews" in result.output
        assert "First watch" in result.output


def test_watch_json_output(monkeypatch):
    monkeypatch.setattr(
        "sugarlearning_tools.cli.get_settings",
        lambda: MagicMock(base_url="https://my.sugarlearning.com", company_code="Zava"),
    )

    with patch("sugarlearning_tools.sync.fetch_module_snapshot", return_value=FAKE_WATCH_SNAP), \
         patch("sugarlearning_tools.sync.load_watch_snap", return_value=None), \
         patch("sugarlearning_tools.sync.save_watch_snap"):
        runner = CliRunner()
        result = runner.invoke(cli, ["watch", "6307", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["module"]["name"] == "Spec Reviews"
        assert data["first_watch"] is True
        assert len(data["users"]) == 2


def test_watch_quiet_no_changes(monkeypatch):
    """--quiet with no changes should produce no output."""
    monkeypatch.setattr(
        "sugarlearning_tools.cli.get_settings",
        lambda: MagicMock(base_url="https://my.sugarlearning.com", company_code="Zava"),
    )

    # Same snap as previous = no changes
    with patch("sugarlearning_tools.sync.fetch_module_snapshot", return_value=FAKE_WATCH_SNAP), \
         patch("sugarlearning_tools.sync.load_watch_snap", return_value=FAKE_WATCH_SNAP), \
         patch("sugarlearning_tools.sync.save_watch_snap"):
        runner = CliRunner()
        result = runner.invoke(cli, ["watch", "6307", "--quiet"])
        assert result.exit_code == 0
        assert result.output.strip() == ""


def test_watch_shows_changes(monkeypatch):
    """Watch should show changes when users are added."""
    monkeypatch.setattr(
        "sugarlearning_tools.cli.get_settings",
        lambda: MagicMock(base_url="https://my.sugarlearning.com", company_code="Zava"),
    )

    old_snap = {
        **FAKE_WATCH_SNAP,
        "users": [{"userId": "u1", "emailAddress": "alice@test.com", "progressPercentage": 50}],
    }

    with patch("sugarlearning_tools.sync.fetch_module_snapshot", return_value=FAKE_WATCH_SNAP), \
         patch("sugarlearning_tools.sync.load_watch_snap", return_value=old_snap), \
         patch("sugarlearning_tools.sync.save_watch_snap"):
        runner = CliRunner()
        result = runner.invoke(cli, ["watch", "6307"])
        assert result.exit_code == 0
        assert "+ User: bob@test.com" in result.output


# --- backlog command ---


def test_backlog_output(monkeypatch):
    with patch("sugarlearning_tools.client.SugarLearningClient") as MockClient:
        MockClient.return_value.get_backlog.return_value = FAKE_BACKLOG
        monkeypatch.setattr(
            "sugarlearning_tools.cli.get_settings",
            lambda: MagicMock(base_url="https://my.sugarlearning.com", company_code="Zava"),
        )
        runner = CliRunner()
        result = runner.invoke(cli, ["backlog"])
        assert result.exit_code == 0
        assert "Total items: 5" in result.output
        assert "Induction" in result.output


def test_backlog_json(monkeypatch):
    with patch("sugarlearning_tools.client.SugarLearningClient") as MockClient:
        MockClient.return_value.get_backlog.return_value = FAKE_BACKLOG
        monkeypatch.setattr(
            "sugarlearning_tools.cli.get_settings",
            lambda: MagicMock(base_url="https://my.sugarlearning.com", company_code="Zava"),
        )
        runner = CliRunner()
        result = runner.invoke(cli, ["backlog", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["totalItems"] == 5
        assert len(data["modules"]) == 2


def test_backlog_status_filter(monkeypatch):
    with patch("sugarlearning_tools.client.SugarLearningClient") as MockClient:
        MockClient.return_value.get_backlog.return_value = FAKE_BACKLOG
        monkeypatch.setattr(
            "sugarlearning_tools.cli.get_settings",
            lambda: MagicMock(base_url="https://my.sugarlearning.com", company_code="Zava"),
        )
        runner = CliRunner()
        result = runner.invoke(cli, ["backlog", "--status", "outstanding", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status_filter"] == "outstanding"
        # Should only have outstanding items
        for mod in data["modules"]:
            for item in mod["items"]:
                assert item["state"] in ("Assigned", "Outstanding")


def test_backlog_limit_and_skip(monkeypatch):
    with patch("sugarlearning_tools.client.SugarLearningClient") as MockClient:
        MockClient.return_value.get_backlog.return_value = FAKE_BACKLOG
        monkeypatch.setattr(
            "sugarlearning_tools.cli.get_settings",
            lambda: MagicMock(base_url="https://my.sugarlearning.com", company_code="Zava"),
        )
        runner = CliRunner()
        result = runner.invoke(cli, ["backlog", "--limit", "1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["modules"]) == 1


# --- login command ---


def test_login_with_token_flag(monkeypatch):
    with patch("sugarlearning_tools.auth.login_with_token") as mock_login:
        mock_login.return_value = {"access_token": "test"}
        runner = CliRunner()
        result = runner.invoke(cli, ["login", "-t", "fake-token"])
        assert result.exit_code == 0
        mock_login.assert_called_once_with("fake-token")


def test_login_company_flag(tmp_path, monkeypatch):
    monkeypatch.setattr("sugarlearning_tools.cli._CONFIG_HOME", tmp_path)
    with patch("sugarlearning_tools.auth.login_with_token") as mock_login:
        mock_login.return_value = {"access_token": "test"}
        runner = CliRunner()
        result = runner.invoke(cli, ["login", "--company", "TEST", "-t", "fake-token"])
        assert result.exit_code == 0
        assert "Company code set: TEST" in result.output
        env_content = (tmp_path / ".env").read_text()
        assert "SL_COMPANY_CODE=TEST" in env_content


# --- sync command ---


def test_sync_first_run(monkeypatch):
    with patch("sugarlearning_tools.sync.sync") as mock_sync:
        mock_sync.return_value = (Path("/fake/snapshot.json"), None)
        runner = CliRunner()
        result = runner.invoke(cli, ["sync"])
        assert result.exit_code == 0
        # No diff on first run, so no output
        mock_sync.assert_called_once()


def test_sync_with_changes(tmp_path, monkeypatch):
    diff_path = tmp_path / "diff.json"
    diff_path.write_text(json.dumps(FAKE_DIFF))

    with patch("sugarlearning_tools.sync.sync") as mock_sync:
        mock_sync.return_value = (Path("/fake/snapshot.json"), diff_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["sync"])
        assert result.exit_code == 0
        assert "New Module" in result.output


def test_sync_json(tmp_path, monkeypatch):
    diff_path = tmp_path / "diff.json"
    diff_path.write_text(json.dumps(FAKE_DIFF))

    with patch("sugarlearning_tools.sync.sync") as mock_sync:
        mock_sync.return_value = (Path("/fake/snapshot.json"), diff_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["sync", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["modules"]["added"][0]["name"] == "New Module"


# --- Fixtures for new features ---

FAKE_LEADERBOARD = [
    {
        "position": 1, "fullName": "Alice Smith", "userNameAlias": "alice",
        "totalAssigned": 50, "totalCompleted": 50, "totalPoints": 500,
        "totalPointsEarned": 500, "percentageOfPointEarned": 100,
        "totalBadges": 10, "joinedDateTime": "2022-01-01T00:00:00",
        "lastCompletedDateTime": "2026-03-01T00:00:00",
        "groupNames": ["Developers", "Managers"],
    },
    {
        "position": 2, "fullName": "Bob Jones", "userNameAlias": "bob",
        "totalAssigned": 50, "totalCompleted": 40, "totalPoints": 500,
        "totalPointsEarned": 400, "percentageOfPointEarned": 80,
        "totalBadges": 5, "joinedDateTime": "2023-01-01T00:00:00",
        "lastCompletedDateTime": "2026-02-28T00:00:00",
        "groupNames": ["Developers"],
    },
    {
        "position": 3, "fullName": "Zero User", "userNameAlias": "zero",
        "totalAssigned": 50, "totalCompleted": 0, "totalPoints": 500,
        "totalPointsEarned": 0, "percentageOfPointEarned": 0,
        "totalBadges": 0, "joinedDateTime": "2024-01-01T00:00:00",
        "lastCompletedDateTime": None,
        "groupNames": [],
    },
]

FAKE_PROFILE = {
    "userId": "u1",
    "userNameAlias": "alice",
    "firstName": "Alice",
    "lastName": "Smith",
    "badges": [
        {"moduleName": "Induction", "grantedText": "2 months ago", "grantedDateTimeText": "2026-01-01"},
        {"moduleName": "Security", "grantedText": "1 month ago", "grantedDateTimeText": "2026-02-01"},
    ],
    "companies": [{"companyId": 1, "companyName": "Zava"}],
}


# --- leaderboard command ---


def test_leaderboard_output(monkeypatch):
    with patch("sugarlearning_tools.client.SugarLearningClient") as MockClient:
        MockClient.return_value.get_leaderboard.return_value = FAKE_LEADERBOARD
        runner = CliRunner()
        result = runner.invoke(cli, ["leaderboard"])
        assert result.exit_code == 0
        assert "Alice Smith" in result.output
        assert "Bob Jones" in result.output
        # Zero User should be hidden by default (0% progress)
        assert "Zero User" not in result.output


def test_leaderboard_json(monkeypatch):
    with patch("sugarlearning_tools.client.SugarLearningClient") as MockClient:
        MockClient.return_value.get_leaderboard.return_value = FAKE_LEADERBOARD
        runner = CliRunner()
        result = runner.invoke(cli, ["leaderboard", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Should exclude 0% user
        assert len(data) == 2
        assert data[0]["fullName"] == "Alice Smith"


def test_leaderboard_limit(monkeypatch):
    with patch("sugarlearning_tools.client.SugarLearningClient") as MockClient:
        MockClient.return_value.get_leaderboard.return_value = FAKE_LEADERBOARD
        runner = CliRunner()
        result = runner.invoke(cli, ["leaderboard", "--limit", "1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1


def test_leaderboard_show_all(monkeypatch):
    """--all should include 0% progress users."""
    with patch("sugarlearning_tools.client.SugarLearningClient") as MockClient:
        MockClient.return_value.get_leaderboard.return_value = FAKE_LEADERBOARD
        runner = CliRunner()
        result = runner.invoke(cli, ["leaderboard", "--all", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 3
        assert any(u["userNameAlias"] == "zero" for u in data)


# --- badges command ---


def test_badges_output(monkeypatch):
    with patch("sugarlearning_tools.client.SugarLearningClient") as MockClient:
        MockClient.return_value.get_my_profile.return_value = FAKE_PROFILE
        runner = CliRunner()
        result = runner.invoke(cli, ["badges"])
        assert result.exit_code == 0
        assert "Induction" in result.output
        assert "Security" in result.output
        assert "2 total" in result.output


def test_badges_json(monkeypatch):
    with patch("sugarlearning_tools.client.SugarLearningClient") as MockClient:
        MockClient.return_value.get_my_profile.return_value = FAKE_PROFILE
        runner = CliRunner()
        result = runner.invoke(cli, ["badges", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["moduleName"] == "Induction"


def test_badges_other_user(monkeypatch):
    with patch("sugarlearning_tools.client.SugarLearningClient") as MockClient:
        MockClient.return_value.get_user_profile.return_value = FAKE_PROFILE
        runner = CliRunner()
        result = runner.invoke(cli, ["badges", "alice"])
        assert result.exit_code == 0
        assert "Alice Smith" in result.output
        MockClient.return_value.get_user_profile.assert_called_once_with("alice")


def test_badges_no_badges(monkeypatch):
    empty_profile = {**FAKE_PROFILE, "badges": []}
    with patch("sugarlearning_tools.client.SugarLearningClient") as MockClient:
        MockClient.return_value.get_my_profile.return_value = empty_profile
        runner = CliRunner()
        result = runner.invoke(cli, ["badges"])
        assert result.exit_code == 0
        assert "no badges" in result.output


# --- profile command ---


def test_profile_output(monkeypatch):
    with patch("sugarlearning_tools.client.SugarLearningClient") as MockClient:
        MockClient.return_value.get_my_profile.return_value = FAKE_PROFILE
        MockClient.return_value.get_leaderboard.return_value = FAKE_LEADERBOARD
        runner = CliRunner()
        result = runner.invoke(cli, ["profile"])
        assert result.exit_code == 0
        assert "Alice Smith" in result.output
        assert "#1" in result.output
        assert "100%" in result.output


def test_profile_json(monkeypatch):
    with patch("sugarlearning_tools.client.SugarLearningClient") as MockClient:
        MockClient.return_value.get_my_profile.return_value = FAKE_PROFILE
        MockClient.return_value.get_leaderboard.return_value = FAKE_LEADERBOARD
        runner = CliRunner()
        result = runner.invoke(cli, ["profile", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["alias"] == "alice"
        assert data["leaderboard"]["position"] == 1
        assert len(data["badges"]) == 2


def test_profile_other_user(monkeypatch):
    with patch("sugarlearning_tools.client.SugarLearningClient") as MockClient:
        MockClient.return_value.get_user_profile.return_value = FAKE_PROFILE
        MockClient.return_value.get_leaderboard.return_value = FAKE_LEADERBOARD
        runner = CliRunner()
        result = runner.invoke(cli, ["profile", "alice"])
        assert result.exit_code == 0
        MockClient.return_value.get_user_profile.assert_called_once_with("alice")
