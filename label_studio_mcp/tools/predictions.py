"""Prediction CRUD tools."""

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


@write_tool()
@require_ls_connection
def create_label_studio_prediction_tool(
    task_id: int,
    result: List[Dict[str, Any]],  # Expect result as a list directly
    model_version: str = None,
    score: float = None
) -> str:
    """Creates a prediction for a specific Label Studio task.

    Args:
        task_id (int): The ID of the task to add the prediction to.
        result (List[Dict[str, Any]]): The prediction result list, containing dictionaries
                                    matching the Label Studio prediction format.
                                    Example: [{"from_name": "label", "to_name": "text",
                                             "type": "choices", "value": {"choices": ["Positive"]}}]
        model_version (str, optional): String identifying the model version.
        score (float, optional): Confidence score for the prediction (0.0 to 1.0).

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

    Returns:
        JSON string containing the details of the created prediction.

    Reference: Uses ls.predictions.create based on API endpoint /api/predictions/
               https://api.labelstud.io/api-reference/api-reference/predictions/create
    """
    # Verify text-span offsets against the real task text before sending.
    _validate_result_spans(result, task_id)

    # Prepare arguments for the SDK call, filtering out None values
    sdk_kwargs = {
        "task": task_id,  # Use 'task' instead of 'task_id' for the SDK
        "result": result,  # Already a list, no need to parse JSON
        "model_version": model_version,
        "score": score,
    }
    filtered_sdk_kwargs = {k: v for k, v in sdk_kwargs.items() if v is not None}

    try:
        # Call the create prediction method
        created_prediction = ls.predictions.create(**filtered_sdk_kwargs)
        
        # Manually construct the response dictionary with safe serialization
        response_data = {
             "message": "Prediction created successfully."
        }
        
        # Safely extract common fields and handle datetime
        for attr_name in ['id', 'task', 'model_version', 'score', 'result', 'created_at', 'updated_at']:
            if hasattr(created_prediction, attr_name):
                value = getattr(created_prediction, attr_name)
                if isinstance(value, datetime.datetime):
                    response_data[attr_name] = value.isoformat()
                elif isinstance(value, (str, int, float, list, dict, bool)) or value is None:
                    # Only include basic JSON-serializable types
                    response_data[attr_name] = value
                # else: skip other complex types
        
        # Use the basic json.dumps on the manually constructed dict
        return json.dumps(response_data)

    except Exception as e:
        # Catch errors specifically during the prediction creation API call OR manual serialization
        import traceback
        return f"Error during Label Studio prediction create/serialize: {type(e).__name__} - {e}\n{traceback.format_exc()}"


# Helper used by the tools below to drop unset/None keyword arguments so the SDK
# uses its own defaults instead of sending explicit nulls.
@read_tool()
@require_ls_connection
def list_label_studio_predictions_tool(
    task_id: Optional[int] = None,
    project_id: Optional[int] = None,
) -> str:
    """Lists predictions, optionally filtered by task and/or project.

    Args:
        task_id (int): Optional task ID to filter predictions.
        project_id (int): Optional project ID to filter predictions.
    """
    predictions = ls.predictions.list(**_clean(task=task_id, project=project_id))
    return _json(predictions)


@read_tool()
@require_ls_connection
def get_label_studio_prediction_tool(prediction_id: int) -> str:
    """Retrieves a single prediction by ID.

    Args:
        prediction_id (int): ID of the prediction. REQUIRED.
    """
    prediction = ls.predictions.get(id=prediction_id)
    return _json(prediction)


@write_tool()
@require_ls_connection
def update_label_studio_prediction_tool(
    prediction_id: int,
    result: Optional[List[Dict[str, Any]]] = None,
    task_id: Optional[int] = None,
    model_version: Optional[str] = None,
    score: Optional[float] = None,
) -> str:
    """Updates an existing prediction.

    Args:
        prediction_id (int): ID of the prediction to update. REQUIRED.
        result (List[Dict[str, Any]]): New prediction result in Label Studio format.
        task_id (int): Optionally reassign the prediction to a different task.
        model_version (str): Optional model version identifier.
        score (float): Optional confidence score (0.0 - 1.0).

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
        resolved_task_id = task_id
        if resolved_task_id is None:
            try:
                resolved_task_id = getattr(ls.predictions.get(id=prediction_id), "task", None)
            except Exception:
                resolved_task_id = None
        _validate_result_spans(result, resolved_task_id)
    prediction = ls.predictions.update(
        id=prediction_id,
        **_clean(result=result, task=task_id, model_version=model_version, score=score),
    )
    return _json(prediction)


@destructive_tool()
@require_ls_connection
def delete_label_studio_prediction_tool(prediction_id: int) -> str:
    """Deletes a prediction by ID.

    Args:
        prediction_id (int): ID of the prediction to delete. REQUIRED.
    """
    ls.predictions.delete(id=prediction_id)
    return json.dumps({"message": f"Prediction {prediction_id} deleted successfully.", "id": prediction_id})


# ============================================================
# == Users                                                  ==
# ============================================================
