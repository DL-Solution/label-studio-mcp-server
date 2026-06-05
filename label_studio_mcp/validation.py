"""Span (NER) offset validation shared by the annotation and prediction tools.

Label Studio does NOT validate text-span start/end against the task text: a
mismatch is accepted silently and renders a shifted label in the UI. These
helpers verify offsets against the real task text before sending.

To support configs with multiple text inputs, a span's data field is resolved
from the project's parsed_label_config (control from_name -> inputs[].value)
rather than guessing. The parsed config is cached per project for the process.

These helpers fetch the Label Studio client via ``get_ls()`` directly (it is
cached and idempotent), so they work regardless of which tool module calls them.
"""

from typing import Any, Dict

from .mcp_env import get_ls, _log

_PARSED_CONFIG_CACHE: Dict[int, Any] = {}


def _get_parsed_label_config(project_id):
    """Return the project's parsed_label_config dict (cached per project_id)."""
    if project_id is None:
        return None
    if project_id in _PARSED_CONFIG_CACHE:
        return _PARSED_CONFIG_CACHE[project_id]
    parsed = None
    try:
        ls = get_ls()
        project = ls.projects.get(id=project_id)
        candidate = getattr(project, "parsed_label_config", None)
        if isinstance(candidate, dict):
            parsed = candidate
    except Exception:
        parsed = None
    _PARSED_CONFIG_CACHE[project_id] = parsed
    return parsed


def _resolve_task_text(task_data, to_name):
    """Legacy fallback: text field a span targets, else the first string field.

    Used only when the parsed label config is unavailable (e.g. it couldn't be
    fetched), so single-text projects keep working without precise resolution.
    """
    if not isinstance(task_data, dict):
        return None
    value = task_data.get(to_name)
    if isinstance(value, str):
        return value
    for value in task_data.values():
        if isinstance(value, str):
            return value
    return None


def _resolve_field(span: dict, parsed_config: dict) -> str:
    """Resolve which task-data field a span targets via parsed_label_config.

    Maps the span's control (from_name) to its bound input field
    (inputs[].value), cross-checking the span's to_name against the control's
    declared to_name list. Raises ValueError on an unknown control or a to_name
    not bound to that control.
    """
    from_name = span.get("from_name")
    entry = parsed_config.get(from_name)
    if entry is None:
        raise ValueError(f"unknown control from_name={from_name!r}")
    inputs = entry.get("inputs") or []
    if not inputs:
        raise ValueError(f"control {from_name!r} has no input binding")
    to_names = entry.get("to_name") or []
    span_to = span.get("to_name")
    if span_to is not None and to_names and span_to not in to_names:
        raise ValueError(
            f"to_name {span_to!r} not bound to control {from_name!r} "
            f"(expected one of {to_names})"
        )
    if len(inputs) == 1:
        return inputs[0]["value"]
    # multi-input on one control: align input by the position of to_name
    if span_to in to_names and len(to_names) == len(inputs):
        return inputs[to_names.index(span_to)]["value"]
    # last-resort fallback: first input
    _log(
        f"WARNING: could not align input for control {from_name!r} "
        f"(to_name={span_to!r}); falling back to first input"
    )
    return inputs[0]["value"]


def _validate_spans(result, parsed_config, task_data) -> None:
    """Validate text-span results before sending them to Label Studio.

    For type="labels"/"hypertextlabels" spans with integer character offsets:
      - the data field is resolved from parsed_config (control -> input). When
        parsed_config is unavailable, fall back to a best-effort text field.
      - the "text" field is REQUIRED (guardrail against silently shifted spans);
      - offsets must satisfy 0 <= start < end <= len(text) and
        text[start:end] must equal value["text"].

    Spans without integer offsets (e.g. hypertext xpath ranges) are skipped.
    """
    if not isinstance(result, list):
        return
    for r in result:
        if not isinstance(r, dict) or r.get("type") not in ("labels", "hypertextlabels"):
            continue
        v = r.get("value")
        if not isinstance(v, dict) or "start" not in v or "end" not in v:
            continue
        s, e = v["start"], v["end"]
        if not (isinstance(s, int) and isinstance(e, int)):
            continue  # non-character offsets (e.g. hypertext xpath) — can't check here
        if not (0 <= s < e):
            raise ValueError(f"invalid span offsets: start={s} end={e} (need 0 <= start < end)")
        if "text" not in v or v.get("text") is None:
            raise ValueError(
                f"span at start={s} end={e} is missing the required 'text' field; "
                "include the exact substring data[to_name][start:end] so offsets can be verified"
            )
        declared = v["text"]

        # Resolve the field this span targets.
        field = None
        if isinstance(parsed_config, dict) and parsed_config:
            field = _resolve_field(r, parsed_config)
            if not isinstance(task_data, dict) or field not in task_data:
                raise ValueError(f"field {field!r} not in task data")
            text = task_data[field]
        else:
            text = _resolve_task_text(task_data, r.get("to_name"))
            if text is None:
                continue  # text declared but task text unavailable to cross-check

        if not isinstance(text, str):
            raise ValueError(f"field {field!r} is not text (got {type(text).__name__})")
        if e > len(text):
            raise ValueError(
                f"span out of range: start={s} end={e} "
                + (f"field={field!r} " if field else "")
                + f"text_len={len(text)}"
            )
        actual = text[s:e]
        if declared != actual:
            raise ValueError(
                f"span mismatch"
                + (f" on field {field!r}" if field else "")
                + f": declared text={declared!r} but text[{s}:{e}]={actual!r}"
            )


def _fetch_task(task_id):
    """Best-effort fetch of a task object; returns None if unavailable."""
    if task_id is None:
        return None
    try:
        ls = get_ls()
        return ls.tasks.get(id=str(task_id))
    except Exception:
        return None


def _validate_result_spans(result, task_id) -> None:
    """Resolve a task's data + project config and validate any span results.

    No-op when the result has no text spans or the task can't be fetched.
    """
    if not isinstance(result, list):
        return
    if not any(
        isinstance(r, dict) and r.get("type") in ("labels", "hypertextlabels")
        for r in result
    ):
        return
    task = _fetch_task(task_id)
    if task is None:
        return
    task_data = getattr(task, "data", None)
    if not isinstance(task_data, dict):
        return
    parsed_config = _get_parsed_label_config(getattr(task, "project", None))
    _validate_spans(result, parsed_config, task_data)
