"""Tests for labeling-config XML generation."""

import json

import pytest

from label_studio_mcp.tools.config_gen import (
    _build_label_config,
    generate_label_studio_label_config_tool,
)


def test_text_choices_config():
    xml = _build_label_config("text", "choices", labels=["Positive", "Negative"])
    assert '<Text name="text" value="$text"/>' in xml
    assert '<Choices name="choices" toName="text" choice="single">' in xml
    assert '<Choice value="Positive"/>' in xml
    assert '<Choice value="Negative"/>' in xml
    assert xml.startswith("<View>") and xml.rstrip().endswith("</View>")


def test_choice_multiple():
    xml = _build_label_config("text", "choices", labels=["A"], choice="multiple")
    assert 'choice="multiple"' in xml


def test_labelless_control_needs_no_labels():
    xml = _build_label_config("text", "textarea")
    assert "<TextArea" in xml
    assert "<Label" not in xml and "<Choice" not in xml


def test_custom_field_and_control_name():
    xml = _build_label_config(
        "text", "labels", labels=["PER"], field_name="content", from_name="ner"
    )
    assert '<Text name="content" value="$content"/>' in xml
    assert '<Labels name="ner" toName="content">' in xml


def test_xml_escaping_of_labels():
    xml = _build_label_config("text", "choices", labels=["A & B"])
    assert '<Choice value="A &amp; B"/>' in xml


def test_rectanglelabels_requires_image():
    with pytest.raises(ValueError, match="rectanglelabels"):
        _build_label_config("text", "rectanglelabels", labels=["box"])


def test_labels_requires_text_or_hypertext():
    with pytest.raises(ValueError, match="text spans"):
        _build_label_config("image", "labels", labels=["x"])


def test_choices_requires_non_empty_labels():
    with pytest.raises(ValueError, match="non-empty 'labels'"):
        _build_label_config("text", "choices", labels=[])


def test_unsupported_types():
    with pytest.raises(ValueError, match="Unsupported data_type"):
        _build_label_config("video", "choices", labels=["a"])
    with pytest.raises(ValueError, match="Unsupported control_type"):
        _build_label_config("text", "dropdown", labels=["a"])


def test_generate_tool_returns_validated_config():
    out = json.loads(
        generate_label_studio_label_config_tool("text", "choices", labels=["Yes", "No"])
    )
    assert out["validated"] is True
    assert "<Choices" in out["label_config"]


def test_generate_tool_reports_value_error_as_json():
    out = json.loads(
        generate_label_studio_label_config_tool("video", "choices", labels=["a"])
    )
    assert out["error"] is True
    assert out["type"] == "ValueError"
