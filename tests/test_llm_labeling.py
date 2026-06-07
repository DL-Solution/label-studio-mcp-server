"""Tests for the network-free parts of LLM-assisted labeling."""

import pytest

from label_studio_mcp.tools.llm_labeling import (
    _extract_controls,
    _extract_json,
    _build_results,
    _resolve_model,
)
from label_studio_mcp import mcp_env


# A parsed_label_config covering each supported control type plus one unsupported.
PARSED_CONFIG = {
    "sentiment": {
        "type": "Choices",
        "to_name": ["text"],
        "inputs": [{"type": "Text", "value": "text"}],
        "labels": ["Positive", "Negative", "Neutral"],
    },
    "entities": {
        "type": "Labels",
        "to_name": ["text"],
        "inputs": [{"type": "Text", "value": "text"}],
        "labels": ["PER", "ORG"],
    },
    "summary": {
        "type": "TextArea",
        "to_name": ["text"],
        "inputs": [{"type": "Text", "value": "text"}],
        "labels": [],
    },
    "stars": {
        "type": "Rating",
        "to_name": ["text"],
        "inputs": [{"type": "Text", "value": "text"}],
        "labels": [],
    },
    "box": {  # unsupported control type — must be ignored
        "type": "RectangleLabels",
        "to_name": ["image"],
        "inputs": [{"type": "Image", "value": "image"}],
        "labels": ["Car"],
    },
}


def test_extract_controls_filters_unsupported():
    controls = _extract_controls(PARSED_CONFIG)
    by_name = {c["from_name"]: c for c in controls}
    assert set(by_name) == {"sentiment", "entities", "summary", "stars"}
    assert by_name["sentiment"]["type"] == "choices"
    assert by_name["entities"]["field"] == "text"
    assert by_name["sentiment"]["labels"] == ["Positive", "Negative", "Neutral"]


def test_extract_json_plain_fenced_and_prose():
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('Here you go:\n{"a": 1}\nThanks') == {"a": 1}


def test_extract_json_invalid_raises():
    with pytest.raises(ValueError):
        _extract_json("no json here")


def test_build_results_choices_rating_textarea():
    controls = _extract_controls(PARSED_CONFIG)
    task_data = {"text": "Great product"}
    llm = {
        "sentiment": ["Positive"],
        "stars": 5,
        "summary": "A happy review",
        "entities": [],
    }
    results, warnings = _build_results(llm, controls, task_data)
    by_type = {r["type"]: r for r in results}
    assert by_type["choices"]["value"]["choices"] == ["Positive"]
    assert by_type["rating"]["value"]["rating"] == 5
    assert by_type["textarea"]["value"]["text"] == ["A happy review"]


def test_build_results_ner_offsets_computed():
    controls = _extract_controls(PARSED_CONFIG)
    task_data = {"text": "Steve Jobs founded Apple"}
    llm = {"entities": [
        {"text": "Steve Jobs", "label": "PER"},
        {"text": "Apple", "label": "ORG"},
    ]}
    results, warnings = _build_results(llm, controls, task_data)
    spans = [r for r in results if r["type"] == "labels"]
    assert {"start": 0, "end": 10, "text": "Steve Jobs", "labels": ["PER"]} == spans[0]["value"]
    apple = spans[1]["value"]
    assert task_data["text"][apple["start"]:apple["end"]] == "Apple"
    assert apple["labels"] == ["ORG"]


def test_build_results_disallowed_label_and_missing_text_warn():
    controls = _extract_controls(PARSED_CONFIG)
    task_data = {"text": "hello world"}
    llm = {
        "sentiment": ["Bogus"],  # not in allowed labels
        "entities": [{"text": "nowhere", "label": "PER"}],  # not in text
    }
    results, warnings = _build_results(llm, controls, task_data)
    assert results == []
    assert any("sentiment" in w for w in warnings)
    assert any("not found" in w for w in warnings)


def test_resolve_model_defaults(monkeypatch):
    monkeypatch.setattr(mcp_env, "OPENROUTER_MODEL", "openai/gpt-4o-mini")
    assert _resolve_model(None) == "openai/gpt-4o-mini"
    assert _resolve_model("google/gemini-2.0-flash") == "google/gemini-2.0-flash"
