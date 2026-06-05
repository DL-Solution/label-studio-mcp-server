"""Tests for the JSON serialization helpers."""

import datetime
import json

from label_studio_mcp.serialization import _serialize, _json, _clean


def test_serialize_passes_primitives_through():
    assert _serialize(None) is None
    assert _serialize("x") == "x"
    assert _serialize(3) == 3
    assert _serialize(1.5) == 1.5
    assert _serialize(True) is True


def test_serialize_datetime_to_isoformat():
    dt = datetime.datetime(2024, 1, 2, 3, 4, 5)
    assert _serialize(dt) == "2024-01-02T03:04:05"
    assert _serialize(datetime.date(2024, 1, 2)) == "2024-01-02"


def test_serialize_recurses_into_containers():
    dt = datetime.datetime(2024, 1, 2, 3, 4, 5)
    assert _serialize({"a": dt, "b": [1, dt]}) == {
        "a": "2024-01-02T03:04:05",
        "b": [1, "2024-01-02T03:04:05"],
    }
    # tuples and sets become lists
    assert _serialize((1, 2)) == [1, 2]


def test_serialize_uses_pydantic_model_dump():
    class Model:
        def model_dump(self, mode=None):
            assert mode == "json"
            return {"id": 7}

    assert _serialize(Model()) == {"id": 7}


def test_serialize_falls_back_to_str():
    class Weird:
        def __str__(self):
            return "weird-repr"

    assert _serialize(Weird()) == "weird-repr"


def test_json_returns_valid_json_string():
    dt = datetime.datetime(2024, 1, 2, 3, 4, 5)
    assert json.loads(_json({"when": dt})) == {"when": "2024-01-02T03:04:05"}


def test_clean_drops_none_but_keeps_falsy():
    assert _clean(a=1, b=None, c=0, d="", e=False) == {
        "a": 1,
        "c": 0,
        "d": "",
        "e": False,
    }
