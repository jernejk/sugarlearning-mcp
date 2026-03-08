"""Tests for config module."""

from sugarlearning_tools.config import get_settings, reset_settings


def test_get_settings_returns_settings():
    reset_settings()
    s = get_settings()
    assert s.base_url == "https://my.sugarlearning.com"
    assert s.qdrant_collection == "sugarlearning"


def test_get_settings_singleton():
    reset_settings()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_reset_settings_clears_cache():
    s1 = get_settings()
    reset_settings()
    s2 = get_settings()
    assert s1 is not s2


def test_settings_token_path():
    reset_settings()
    s = get_settings()
    assert s.token_path.name == "tokens.json"
    assert "sugarlearning-tools" in str(s.token_path)


def test_settings_dirs_exist():
    reset_settings()
    s = get_settings()
    assert s.data_dir.exists()
    assert s.snapshots_dir.exists()
    assert s.diffs_dir.exists()
