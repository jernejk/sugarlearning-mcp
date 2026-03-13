"""Tests for the API client normalization logic."""

import httpx

from sugarlearning_tools.client import SugarLearningClient, _normalize, _to_camel


def test_to_camel_basic():
    assert _to_camel("EmailAddress") == "emailAddress"
    assert _to_camel("Id") == "id"
    assert _to_camel("Name") == "name"


def test_to_camel_already_lowercase():
    assert _to_camel("name") == "name"
    assert _to_camel("id") == "id"


def test_to_camel_empty():
    assert _to_camel("") == ""


def test_to_camel_single_char():
    assert _to_camel("X") == "x"


def test_normalize_flat_dict():
    data = {"Id": 1, "Name": "Test", "EmailAddress": "test@example.com"}
    result = _normalize(data)
    assert result == {"id": 1, "name": "Test", "emailAddress": "test@example.com"}


def test_normalize_nested_dict():
    data = {"Module": {"Id": 1, "Name": "Test"}}
    result = _normalize(data)
    assert result == {"module": {"id": 1, "name": "Test"}}


def test_normalize_list_of_dicts():
    data = [{"Id": 1, "Name": "A"}, {"Id": 2, "Name": "B"}]
    result = _normalize(data)
    assert result == [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]


def test_normalize_dict_with_list():
    data = {"Items": [{"Id": 1}, {"Id": 2}]}
    result = _normalize(data)
    assert result == {"items": [{"id": 1}, {"id": 2}]}


def test_normalize_primitive():
    assert _normalize("hello") == "hello"
    assert _normalize(42) == 42
    assert _normalize(None) is None


def test_get_item_uses_company_user_item_endpoint(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = kwargs.get("params")
        return httpx.Response(
            200,
            json={
                "ItemId": 8291,
                "ItemName": "Daily Scrum emails",
                "ItemContentValue": "Full item body",
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("sugarlearning_tools.client.get_token", lambda: "test-token")
    monkeypatch.setattr(httpx, "get", fake_get)

    client = SugarLearningClient(company_code="SSW")
    result = client.get_item(8291, user_alias="jk", timezone_offset_minutes=600, visit_source="cli")

    assert captured["url"] == "https://my.sugarlearning.com/api/v2/company/SSW/user/jk/item/8291"
    assert captured["params"] == {
        "timeZoneOffsetInMinutes": 600,
        "visitSource": "cli",
    }
    assert captured["headers"]["Authorization"] == "Bearer test-token"
    assert result["itemId"] == 8291
    assert result["itemName"] == "Daily Scrum emails"
    assert result["itemContentValue"] == "Full item body"
