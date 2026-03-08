"""Tests for the API client normalization logic."""

from sugarlearning_tools.client import _normalize, _to_camel


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
