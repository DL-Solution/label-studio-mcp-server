"""Annotation CRUD tools."""

import json
from typing import Any, Dict, List, Optional

from ..server import (
    read_tool,
    write_tool,
    destructive_tool,
    require_ls_connection,
)
from ..serialization import _json, _serialize, _clean
from ..validation import _validate_result_spans

# Populated by ``require_ls_connection`` before each tool body runs.
ls = None


@read_tool()
@require_ls_connection
def list_label_studio_task_annotations_tool(task_id: int) -> str:
    """Lists all annotations for a specific task (Annotations API).

    Args:
        task_id (int): ID of the task. REQUIRED.
    """
    annotations = ls.annotations.list(id=task_id)
    return _json(annotations)


@read_tool()
@require_ls_connection
def get_label_studio_annotation_tool(annotation_id: int) -> str:
    """Retrieves a single annotation by its ID.

    Args:
        annotation_id (int): ID of the annotation. REQUIRED.
    """
    annotation = ls.annotations.get(id=annotation_id)
    return _json(annotation)


@write_tool()
@require_ls_connection
def create_label_studio_annotation_tool(
    task_id: int,
    result: List[Dict[str, Any]],
    completed_by: Optional[int] = None,
    ground_truth: Optional[bool] = None,
    was_cancelled: Optional[bool] = None,
    lead_time: Optional[float] = None,
) -> str:
    """Creates an annotation for a task.

    Args:
        task_id (int): ID of the task to annotate. REQUIRED.
        result (List[Dict[str, Any]]): Annotation result in Label Studio format. REQUIRED.
        completed_by (int): Optional user ID that produced the annotation.
        ground_truth (bool): Optionally mark the annotation as ground truth.
        was_cancelled (bool): Optionally mark the annotation as skipped/cancelled.
        lead_time (float): Optional time spent (seconds) producing the annotation.

    Text spans (type "labels"/"hypertextlabels"): start/end in value are CHARACTER
    indices (0-based, end-exclusive), NOT bytes — count by characters for
    Cyrillic/UTF-8. ALWAYS include "text" in value equal to the exact substring
    data[<to_name>][start:end]. Label Studio does NOT validate start/end against
    the supplied text — a mismatch is accepted silently and renders a shifted span.
    Compute offsets programmatically (str.find + len), never by hand, and ensure
    text[start:end] == value["text"]. This tool additionally verifies offsets
    against the task text and rejects mismatches.
    Correct span:
        {"from_name": "label", "to_name": "text", "type": "labels",
         "value": {"start": 15, "end": 27, "text": "Winston Blue", "labels": ["PRODUCT"]}}
    """
    _validate_result_spans(result, task_id)
    annotation = ls.annotations.create(
        id=task_id,
        result=result,
        **_clean(
            completed_by=completed_by,
            ground_truth=ground_truth,
            was_cancelled=was_cancelled,
            lead_time=lead_time,
        ),
    )
    return _json(annotation)


@write_tool()
@require_ls_connection
def update_label_studio_annotation_tool(
    annotation_id: int,
    result: Optional[List[Dict[str, Any]]] = None,
    ground_truth: Optional[bool] = None,
    was_cancelled: Optional[bool] = None,
    lead_time: Optional[float] = None,
) -> str:
    """Updates an existing annotation.

    Args:
        annotation_id (int): ID of the annotation to update. REQUIRED.
        result (List[Dict[str, Any]]): New annotation result in Label Studio format.
        ground_truth (bool): Optionally toggle ground-truth flag.
        was_cancelled (bool): Optionally toggle the skipped/cancelled flag.
        lead_time (float): Optional time spent (seconds) producing the annotation.

    Text spans (type "labels"/"hypertextlabels"): start/end in value are CHARACTER
    indices (0-based, end-exclusive), NOT bytes — count by characters for
    Cyrillic/UTF-8. ALWAYS include "text" in value equal to the exact substring
    data[<to_name>][start:end]. Label Studio does NOT validate start/end against
    the supplied text — a mismatch is accepted silently and renders a shifted span.
    Compute offsets programmatically (str.find + len), never by hand, and ensure
    text[start:end] == value["text"]. This tool additionally verifies offsets
    against the task text and rejects mismatches.
    Correct span:
        {"from_name": "label", "to_name": "text", "type": "labels",
         "value": {"start": 15, "end": 27, "text": "Winston Blue", "labels": ["PRODUCT"]}}
    """
    if result is not None:
        task_id = None
        try:
            task_id = getattr(ls.annotations.get(id=annotation_id), "task", None)
        except Exception:
            task_id = None
        _validate_result_spans(result, task_id)
    annotation = ls.annotations.update(
        id=annotation_id,
        **_clean(
            result=result,
            ground_truth=ground_truth,
            was_cancelled=was_cancelled,
            lead_time=lead_time,
        ),
    )
    return _json(annotation)


@destructive_tool()
@require_ls_connection
def delete_label_studio_annotation_tool(annotation_id: int) -> str:
    """Deletes an annotation by ID.

    Args:
        annotation_id (int): ID of the annotation to delete. REQUIRED.
    """
    ls.annotations.delete(id=annotation_id)
    return json.dumps({"message": f"Annotation {annotation_id} deleted successfully.", "id": annotation_id})


# ============================================================
# == Predictions (additional CRUD)                          ==
# ============================================================
