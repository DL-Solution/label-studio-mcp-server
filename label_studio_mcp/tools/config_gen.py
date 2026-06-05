"""Labeling-config generation tools."""

import json
from typing import List, Optional

from ..server import read_tool


# ============================================================
# == Labeling config generation                             ==
# ============================================================
# Building a valid labeling-config XML by hand is the most error-prone step for
# users. This generates (and locally validates) the XML from a high-level spec so
# the LLM can hand the result straight to the create/update project tools.

from xml.sax.saxutils import escape as _xml_escape

# data (object) tag + default task-data field for each supported input type
_OBJECT_TAGS = {
    "text": ("Text", "text"),
    "hypertext": ("HyperText", "html"),
    "image": ("Image", "image"),
    "audio": ("Audio", "audio"),
}

# labeling control tag for each supported control type
_CONTROL_TAGS = {
    "choices": "Choices",
    "labels": "Labels",
    "rectanglelabels": "RectangleLabels",
    "rating": "Rating",
    "textarea": "TextArea",
}

# controls that do not take a list of <Label>/<Choice> children
_LABELLESS_CONTROLS = {"rating", "textarea"}


def _build_label_config(
    data_type: str,
    control_type: str,
    labels=None,
    field_name: Optional[str] = None,
    from_name: Optional[str] = None,
    choice: str = "single",
) -> str:
    """Build a labeling-config XML string from a high-level spec (no API calls)."""
    data_type = (data_type or "").strip().lower()
    control_type = (control_type or "").strip().lower()
    if data_type not in _OBJECT_TAGS:
        raise ValueError(
            f"Unsupported data_type {data_type!r}. Supported: {sorted(_OBJECT_TAGS)}."
        )
    if control_type not in _CONTROL_TAGS:
        raise ValueError(
            f"Unsupported control_type {control_type!r}. Supported: {sorted(_CONTROL_TAGS)}."
        )
    if control_type == "rectanglelabels" and data_type != "image":
        raise ValueError("control_type 'rectanglelabels' requires data_type 'image'.")
    if control_type == "labels" and data_type not in ("text", "hypertext"):
        raise ValueError(
            "control_type 'labels' (text spans) requires data_type 'text' or 'hypertext'."
        )
    labels = [str(label) for label in (labels or []) if str(label).strip()]
    if control_type not in _LABELLESS_CONTROLS and not labels:
        raise ValueError(
            f"control_type {control_type!r} requires a non-empty 'labels' list."
        )

    obj_tag, default_field = _OBJECT_TAGS[data_type]
    field = (field_name or default_field).strip()
    obj_name = field
    ctrl_tag = _CONTROL_TAGS[control_type]
    ctrl_name = (from_name or control_type).strip()

    obj_line = f'  <{obj_tag} name="{_xml_escape(obj_name)}" value="${_xml_escape(field)}"/>'

    attrs = f'name="{_xml_escape(ctrl_name)}" toName="{_xml_escape(obj_name)}"'
    if control_type == "choices":
        ch = "multiple" if str(choice).strip().lower() in ("multiple", "multi") else "single"
        attrs += f' choice="{ch}"'
    if control_type in _LABELLESS_CONTROLS:
        ctrl_block = f'  <{ctrl_tag} {attrs}/>'
    else:
        child = "Choice" if control_type == "choices" else "Label"
        items = "\n".join(
            f'    <{child} value="{_xml_escape(label)}"/>' for label in labels
        )
        ctrl_block = f'  <{ctrl_tag} {attrs}>\n{items}\n  </{ctrl_tag}>'

    return f"<View>\n{obj_line}\n{ctrl_block}\n</View>"


@read_tool()
def generate_label_studio_label_config_tool(
    data_type: str,
    control_type: str,
    labels: Optional[List[str]] = None,
    field_name: Optional[str] = None,
    from_name: Optional[str] = None,
    choice: str = "single",
) -> str:
    """Generate a valid Label Studio XML labeling configuration from a high-level spec.

    Does NOT call Label Studio — it builds and locally validates the XML so you can
    pass the result to create_label_studio_project_tool or the update-config tools.

    Args:
        data_type (str): Input media type — one of: text, hypertext, image, audio. REQUIRED.
        control_type (str): Labeling control — one of: choices, labels, rectanglelabels,
            rating, textarea. ('labels' = text spans/NER; 'rectanglelabels' = image boxes.) REQUIRED.
        labels (List[str] | None): Label/choice values, e.g. ["Positive", "Negative"].
            Required for choices/labels/rectanglelabels; ignored for rating/textarea.
        field_name (str | None): Task-data key for the input (default: text/html/image/audio
            depending on data_type).
        from_name (str | None): Name of the control tag (default: the control_type).
        choice (str): For control_type 'choices' — 'single' or 'multiple' (default 'single').
    """
    try:
        config = _build_label_config(
            data_type, control_type, labels, field_name, from_name, choice
        )
    except ValueError as exc:
        return json.dumps({"error": True, "type": "ValueError", "message": str(exc)})

    result = {"label_config": config, "validated": True}
    try:
        from label_studio_sdk.label_interface import LabelInterface

        LabelInterface(config)
    except Exception as exc:  # generated XML should parse; report if it somehow doesn't
        result["validated"] = False
        result["validation_error"] = str(exc)[:300]
    return json.dumps(result)
