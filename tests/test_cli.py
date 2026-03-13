"""Tests for CLI helpers and commands."""

import json

from click.testing import CliRunner

from sugarlearning_tools.cli import _item_url, _module_url, _save_company_code, _slugify, cli
from sugarlearning_tools.config import get_settings


def test_slugify_basic():
    assert _slugify("Hello World") == "hello-world"


def test_slugify_special_chars():
    assert _slugify("Hello, World! #123") == "hello-world-123"


def test_slugify_multiple_spaces():
    assert _slugify("Hello   World") == "hello-world"


def test_slugify_underscores():
    assert _slugify("hello_world_test") == "hello-world-test"


def test_slugify_empty():
    assert _slugify("") == ""


def test_slugify_already_slugified():
    assert _slugify("hello-world") == "hello-world"


def test_save_company_code_creates_env(tmp_path, monkeypatch):
    monkeypatch.setattr("sugarlearning_tools.cli._CONFIG_HOME", tmp_path)
    _save_company_code("TEST")
    env_content = (tmp_path / ".env").read_text()
    assert "SL_COMPANY_CODE=TEST" in env_content


def test_save_company_code_updates_existing(tmp_path, monkeypatch):
    monkeypatch.setattr("sugarlearning_tools.cli._CONFIG_HOME", tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text("SL_COMPANY_CODE=OLD\nSL_USER_ID=jk\n")
    _save_company_code("NEW")
    env_content = env_path.read_text()
    assert "SL_COMPANY_CODE=NEW" in env_content
    assert "SL_USER_ID=jk" in env_content
    assert "OLD" not in env_content


def test_save_company_code_appends_newline(tmp_path, monkeypatch):
    monkeypatch.setattr("sugarlearning_tools.cli._CONFIG_HOME", tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text("SL_USER_ID=jk")
    _save_company_code("ZAVA")
    env_content = env_path.read_text()
    assert env_content == "SL_USER_ID=jk\nSL_COMPANY_CODE=ZAVA\n"


def test_save_company_code_resets_settings(tmp_path, monkeypatch):
    monkeypatch.setattr("sugarlearning_tools.cli._CONFIG_HOME", tmp_path)
    s1 = get_settings()
    _save_company_code("TEST")
    s2 = get_settings()
    assert s1 is not s2


def test_item_url_uses_slugified_name(monkeypatch):
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: type("S", (), {
        "base_url": "https://my.sugarlearning.com",
        "company_code": "SSW",
    })())
    assert _item_url(8291, "📋 Daily Scrum emails") == "https://my.sugarlearning.com/SSW/items/8291/daily-scrum-emails"


def test_module_url_uses_company_code(monkeypatch):
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: type("S", (), {
        "base_url": "https://my.sugarlearning.com",
        "company_code": "SSW",
    })())
    assert _module_url(6360) == "https://my.sugarlearning.com/SSW/admin/modules/6360"


def test_get_command_json(monkeypatch):
    runner = CliRunner()

    class FakeClient:
        def get_item(self, item_id, user_alias=None):
            assert item_id == 8291
            assert user_alias == "jk"
            return {
                "itemId": item_id,
                "itemName": "Daily Scrum emails",
                "moduleId": 6360,
                "moduleName": "Induction Part 3",
                "itemContentValue": "Full item body",
            }

    monkeypatch.setattr("sugarlearning_tools.client.SugarLearningClient", FakeClient)
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: type("S", (), {
        "base_url": "https://my.sugarlearning.com",
        "company_code": "SSW",
    })())

    result = runner.invoke(cli, ["get", "8291", "--user", "jk", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["itemId"] == 8291
    assert payload["itemContentValue"] == "Full item body"
    assert payload["url"] == "https://my.sugarlearning.com/SSW/items/8291/daily-scrum-emails"


def test_get_command_text_output(monkeypatch):
    runner = CliRunner()

    class FakeClient:
        def get_item(self, item_id, user_alias=None):
            return {
                "itemId": item_id,
                "itemName": "Daily Scrum emails",
                "moduleId": 6360,
                "moduleName": "Induction Part 3",
                "itemContentValue": "Full item body",
            }

    monkeypatch.setattr("sugarlearning_tools.client.SugarLearningClient", FakeClient)
    monkeypatch.setattr("sugarlearning_tools.cli.get_settings", lambda: type("S", (), {
        "base_url": "https://my.sugarlearning.com",
        "company_code": "SSW",
    })())

    result = runner.invoke(cli, ["get", "8291"])

    assert result.exit_code == 0
    assert "Daily Scrum emails [8291]" in result.output
    assert "Induction Part 3" in result.output
    assert "Full item body" in result.output
