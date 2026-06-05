"""Tests for span (NER) offset validation.

These helpers are the one piece of non-trivial, network-free logic in the
server: Label Studio silently accepts shifted spans, so ``_validate_spans``
guards offsets against the real task text before sending.
"""

import pytest

from label_studio_mcp.validation import _validate_spans, _resolve_field, _resolve_task_text

# control "label" bound to task-data field "text"
PARSED = {"label": {"inputs": [{"value": "text"}], "to_name": ["text"]}}
TASK = {"text": "Hello world"}


def _span(start, end, text, **extra):
    value = {"start": start, "end": end, "text": text, "labels": ["X"]}
    value.update(extra)
    return [{"type": "labels", "from_name": "label", "to_name": "text", "value": value}]


def test_valid_span_passes():
    _validate_spans(_span(0, 5, "Hello"), PARSED, TASK)  # no raise


def test_offsets_must_be_ordered():
    with pytest.raises(ValueError, match="invalid span offsets"):
        _validate_spans(_span(5, 5, ""), PARSED, TASK)
    with pytest.raises(ValueError, match="invalid span offsets"):
        _validate_spans(_span(5, 2, "x"), PARSED, TASK)


def test_missing_text_field_is_rejected():
    span = [{"type": "labels", "from_name": "label", "to_name": "text",
             "value": {"start": 0, "end": 5, "labels": ["X"]}}]
    with pytest.raises(ValueError, match="missing the required 'text'"):
        _validate_spans(span, PARSED, TASK)


def test_declared_text_mismatch_is_rejected():
    with pytest.raises(ValueError, match="span mismatch"):
        _validate_spans(_span(0, 5, "Howdy"), PARSED, TASK)


def test_offsets_out_of_range_is_rejected():
    with pytest.raises(ValueError, match="out of range"):
        _validate_spans(_span(0, 999, "Hello"), PARSED, TASK)


def test_non_integer_offsets_are_skipped():
    # hypertext xpath ranges have non-int offsets and can't be checked here
    _validate_spans(_span("/p[1]", "/p[2]", "x"), PARSED, TASK)  # no raise


def test_non_list_result_is_noop():
    _validate_spans("not-a-list", PARSED, TASK)
    _validate_spans(None, PARSED, TASK)


def test_non_span_types_are_ignored():
    result = [{"type": "choices", "value": {"choices": ["A"]}}]
    _validate_spans(result, PARSED, TASK)  # no raise


def test_fallback_resolution_without_parsed_config():
    # When parsed_config is unavailable, fall back to the first string field.
    _validate_spans(_span(0, 5, "Hello"), None, TASK)  # no raise
    with pytest.raises(ValueError, match="span mismatch"):
        _validate_spans(_span(0, 5, "Howdy"), None, TASK)


def test_resolve_field_unknown_control():
    with pytest.raises(ValueError, match="unknown control"):
        _resolve_field({"from_name": "nope"}, PARSED)


def test_resolve_field_maps_control_to_input():
    assert _resolve_field({"from_name": "label", "to_name": "text"}, PARSED) == "text"


def test_resolve_task_text_prefers_named_field():
    assert _resolve_task_text({"a": "first", "b": "second"}, "b") == "second"
    # falls back to the first string field when to_name is absent
    assert _resolve_task_text({"a": "first"}, "missing") == "first"
    assert _resolve_task_text({"n": 5}, "n") is None
