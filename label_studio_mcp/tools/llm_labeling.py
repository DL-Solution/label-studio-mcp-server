"""LLM-assisted labeling via OpenRouter.

These tools let a *selected* OpenRouter model produce the actual labeling, instead
of the MCP client (Claude) doing it. The flow per task is:

  1. read the task data and the project's parsed label config (the schema);
  2. ask the chosen OpenRouter model for a strict-JSON answer per control;
  3. convert that answer into a Label Studio ``result`` list;
  4. save it as a prediction (default) or a completed annotation.

OpenRouter is called over plain HTTPS with ``httpx`` (already a dependency), so no
extra packages are pulled into the bundle. Configure the key/model via the
``OPENROUTER_API_KEY`` / ``OPENROUTER_MODEL`` settings (or per-call ``model``).

Only text-oriented controls are supported: Choices (classification), Labels
(NER spans), TextArea (free text) and Rating. Other controls (e.g. image
bounding boxes) are skipped.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .. import mcp_env
from ..server import read_tool, write_tool, require_ls_connection
from ..validation import _get_parsed_label_config, _validate_spans

# Populated by ``require_ls_connection`` before each tool body runs.
ls = None

# Control types this module knows how to fill from an LLM answer.
_SUPPORTED_CONTROLS = {"choices", "labels", "textarea", "rating"}


# ============================================================
# == Schema extraction + answer parsing (network-free)      ==
# ============================================================

def _extract_controls(parsed_config: Any) -> List[Dict[str, Any]]:
    """Flatten a project's parsed_label_config into the controls we can fill."""
    controls: List[Dict[str, Any]] = []
    if not isinstance(parsed_config, dict):
        return controls
    for from_name, entry in parsed_config.items():
        if not isinstance(entry, dict):
            continue
        ctype = (entry.get("type") or "").lower()
        if ctype not in _SUPPORTED_CONTROLS:
            continue
        to_names = entry.get("to_name") or []
        inputs = entry.get("inputs") or []
        field = None
        if inputs and isinstance(inputs[0], dict):
            field = inputs[0].get("value")
        controls.append({
            "from_name": from_name,
            "type": ctype,
            "to_name": to_names[0] if to_names else None,
            "field": field,
            "labels": [str(label) for label in (entry.get("labels") or [])],
        })
    return controls


def _control_instructions(control: Dict[str, Any]) -> str:
    """One human-readable instruction line describing the expected JSON value."""
    fn = control["from_name"]
    ctype = control["type"]
    labels = control["labels"]
    if ctype == "choices":
        return (
            f'- "{fn}": an array of strings; each MUST be exactly one of '
            f'{json.dumps(labels, ensure_ascii=False)}. Pick the applicable one(s).'
        )
    if ctype == "labels":
        field = control["field"]
        return (
            f'- "{fn}": an array of objects, each {{"text": <exact substring copied '
            f'verbatim from the "{field}" field>, "label": <one of '
            f'{json.dumps(labels, ensure_ascii=False)}>}}. Only mark real spans; '
            f"copy the substring exactly so it can be located."
        )
    if ctype == "rating":
        return f'- "{fn}": a single integer rating.'
    if ctype == "textarea":
        return f'- "{fn}": a single free-text string.'
    return f'- "{fn}": (unsupported control type {ctype!r})'


def _build_messages(
    task_data: Any,
    controls: List[Dict[str, Any]],
    extra_instructions: Optional[str],
) -> List[Dict[str, str]]:
    """Build the OpenRouter chat messages for one task."""
    lines = [_control_instructions(c) for c in controls]
    keys = ", ".join(f'"{c["from_name"]}"' for c in controls)
    system = (
        "You are a precise data-labeling assistant. You read a task and return "
        "labels strictly following the schema. Respond with ONLY a single JSON "
        "object and nothing else — no prose, no code fences."
    )
    user = (
        "Task data (JSON):\n"
        f"{json.dumps(task_data, ensure_ascii=False, indent=2)}\n\n"
        "Produce a JSON object with exactly these keys: "
        f"{keys}.\n"
        "Value formats:\n" + "\n".join(lines) + "\n"
    )
    if extra_instructions:
        user += f"\nAdditional instructions:\n{extra_instructions}\n"
    user += "\nReturn only the JSON object."
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _extract_json(text: str) -> Dict[str, Any]:
    """Parse a JSON object from a model response, tolerating fences/extra prose."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty model response")
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(s[start:end + 1])
    raise ValueError(f"could not parse JSON from model response: {s[:200]!r}")


def _build_results(
    llm_obj: Dict[str, Any],
    controls: List[Dict[str, Any]],
    task_data: Any,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Convert the model's JSON answer into a Label Studio ``result`` list."""
    results: List[Dict[str, Any]] = []
    warnings: List[str] = []
    if not isinstance(llm_obj, dict):
        return results, ["model response was not a JSON object"]

    for control in controls:
        fn = control["from_name"]
        ctype = control["type"]
        to_name = control["to_name"]
        allowed = set(control["labels"])
        if fn not in llm_obj:
            warnings.append(f"control {fn!r}: no value returned by the model")
            continue
        value = llm_obj[fn]

        if ctype == "choices":
            chosen = [str(v) for v in (value if isinstance(value, list) else [value])]
            if allowed:
                chosen = [v for v in chosen if v in allowed]
            if not chosen:
                warnings.append(f"control {fn!r}: no valid choice in {value!r}")
                continue
            results.append({
                "from_name": fn, "to_name": to_name, "type": "choices",
                "value": {"choices": chosen},
            })

        elif ctype == "rating":
            try:
                rating = int(value)
            except (TypeError, ValueError):
                warnings.append(f"control {fn!r}: rating not an integer ({value!r})")
                continue
            results.append({
                "from_name": fn, "to_name": to_name, "type": "rating",
                "value": {"rating": rating},
            })

        elif ctype == "textarea":
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            results.append({
                "from_name": fn, "to_name": to_name, "type": "textarea",
                "value": {"text": [text]},
            })

        elif ctype == "labels":
            field = control["field"]
            field_text = task_data.get(field) if isinstance(task_data, dict) else None
            if not isinstance(field_text, str):
                warnings.append(f"control {fn!r}: field {field!r} is not text; spans skipped")
                continue
            cursor = 0
            for span in (value if isinstance(value, list) else []):
                if not isinstance(span, dict):
                    continue
                text = span.get("text")
                label = span.get("label", span.get("labels"))
                if isinstance(label, list):
                    label = label[0] if label else None
                if not isinstance(text, str) or not text or label is None:
                    warnings.append(f"control {fn!r}: malformed span {span!r}")
                    continue
                if allowed and str(label) not in allowed:
                    warnings.append(f"control {fn!r}: label {label!r} not allowed")
                    continue
                idx = field_text.find(text, cursor)
                if idx == -1:
                    idx = field_text.find(text)
                if idx == -1:
                    warnings.append(f"control {fn!r}: span text {text!r} not found in field")
                    continue
                start, end = idx, idx + len(text)
                cursor = end
                results.append({
                    "from_name": fn, "to_name": to_name, "type": "labels",
                    "value": {"start": start, "end": end, "text": text, "labels": [str(label)]},
                })

    return results, warnings


# ============================================================
# == OpenRouter call                                        ==
# ============================================================

def _resolve_model(model: Optional[str]) -> str:
    return (model or mcp_env.OPENROUTER_MODEL or "").strip()


def _openrouter_chat(
    messages: List[Dict[str, str]],
    model: str,
    temperature: float = 0.0,
    max_tokens: int = 2000,
) -> str:
    """Call OpenRouter's chat-completions API and return the message content."""
    import httpx

    api_key = mcp_env.OPENROUTER_API_KEY
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set; configure it in the extension settings."
        )
    if not model:
        raise RuntimeError(
            "No OpenRouter model specified; pass `model` or set OPENROUTER_MODEL."
        )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # Optional attribution headers recommended by OpenRouter.
        "HTTP-Referer": "https://github.com/DL-Solution/label-studio-mcp-server",
        "X-Title": "label-studio-mcp",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    with httpx.Client(timeout=httpx.Timeout(120.0)) as client:
        resp = client.post(
            f"{mcp_env.OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"Unexpected OpenRouter response: {json.dumps(data)[:300]}")


# ============================================================
# == Core: label one task                                   ==
# ============================================================

def _label_one_task(
    task_id: int,
    model: str,
    as_annotation: bool,
    extra_instructions: Optional[str],
) -> Dict[str, Any]:
    """Run the LLM on a single task and save the result. Returns a summary dict."""
    task = ls.tasks.get(id=task_id)
    project_id = getattr(task, "project", None)
    task_data = getattr(task, "data", None)

    parsed_config = _get_parsed_label_config(project_id)
    controls = _extract_controls(parsed_config)
    if not controls:
        return {
            "task_id": task_id,
            "saved": False,
            "error": "no supported (text) controls found in the project's label config",
        }

    messages = _build_messages(task_data, controls, extra_instructions)
    content = _openrouter_chat(messages, model)
    llm_obj = _extract_json(content)
    results, warnings = _build_results(llm_obj, controls, task_data)

    if not results:
        return {
            "task_id": task_id,
            "saved": False,
            "model": model,
            "warnings": warnings,
            "error": "model produced no usable labels",
        }

    # Verify any text-span offsets against the real task text before saving.
    _validate_spans(results, parsed_config, task_data)

    if as_annotation:
        created = ls.annotations.create(id=task_id, result=results)
        target = "annotation"
    else:
        created = ls.predictions.create(
            task=task_id, result=results, model_version=f"openrouter:{model}"
        )
        target = "prediction"

    return {
        "task_id": task_id,
        "saved": True,
        "target": target,
        "saved_id": getattr(created, "id", None),
        "model": model,
        "result": results,
        "warnings": warnings,
    }


# ============================================================
# == Tools                                                  ==
# ============================================================

@write_tool()
@require_ls_connection
def label_task_with_llm_tool(
    task_id: int,
    model: Optional[str] = None,
    as_annotation: bool = False,
    extra_instructions: Optional[str] = None,
) -> str:
    """Label a single task using a selected OpenRouter LLM (not the MCP client).

    Reads the task data and the project's labeling schema, asks the chosen model
    to produce labels, converts them to a Label Studio result and saves it.
    Supports text-oriented controls: Choices, Labels (NER spans), TextArea, Rating.

    Args:
        task_id (int): ID of the task to label. REQUIRED.
        model (str | None): OpenRouter model id (e.g. "openai/gpt-4o-mini").
            Defaults to the OPENROUTER_MODEL setting.
        as_annotation (bool): Save as a completed annotation instead of a
            prediction (default False -> prediction / ML pre-annotation).
        extra_instructions (str | None): Optional extra guidance for the model
            (e.g. domain rules, label definitions).
    """
    resolved = _resolve_model(model)
    summary = _label_one_task(task_id, resolved, as_annotation, extra_instructions)
    return json.dumps(summary, ensure_ascii=False)


@write_tool()
@require_ls_connection
def label_project_with_llm_tool(
    project_id: int,
    max_tasks: int = 20,
    model: Optional[str] = None,
    as_annotation: bool = False,
    skip_already_predicted: bool = True,
    extra_instructions: Optional[str] = None,
) -> str:
    """Batch-label tasks in a project using a selected OpenRouter LLM.

    Iterates up to `max_tasks` tasks and labels each one (see
    label_task_with_llm_tool). Keep `max_tasks` modest: every task is a separate
    OpenRouter call.

    Args:
        project_id (int): ID of the project. REQUIRED.
        max_tasks (int): Maximum number of tasks to process (default 20).
        model (str | None): OpenRouter model id; defaults to OPENROUTER_MODEL.
        as_annotation (bool): Save annotations instead of predictions (default False).
        skip_already_predicted (bool): Skip tasks that already have predictions
            (default True). Ignored when as_annotation is True.
        extra_instructions (str | None): Optional extra guidance for the model.
    """
    resolved = _resolve_model(model)
    processed: List[Dict[str, Any]] = []
    saved = 0
    skipped = 0
    failed = 0

    for task in ls.tasks.list(project=project_id):
        if len(processed) + skipped >= max_tasks:
            break
        task_id = getattr(task, "id", None)
        if task_id is None:
            continue
        if skip_already_predicted and not as_annotation:
            existing = getattr(task, "predictions", None)
            total = getattr(task, "total_predictions", None)
            if existing or total:
                skipped += 1
                continue
        try:
            summary = _label_one_task(task_id, resolved, as_annotation, extra_instructions)
        except Exception as exc:  # one bad task shouldn't abort the whole batch
            summary = {"task_id": task_id, "saved": False, "error": f"{type(exc).__name__}: {exc}"}
        if summary.get("saved"):
            saved += 1
        else:
            failed += 1
        # Drop the bulky per-task result from the batch summary to stay compact.
        summary.pop("result", None)
        processed.append(summary)

    return json.dumps({
        "project_id": project_id,
        "model": resolved,
        "target": "annotation" if as_annotation else "prediction",
        "tasks_processed": len(processed),
        "saved": saved,
        "failed": failed,
        "skipped_already_predicted": skipped,
        "tasks": processed,
    }, ensure_ascii=False)
