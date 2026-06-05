from typing import Any, List, Dict, Optional
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
import re
import json
import functools
from pydantic import BaseModel
import datetime

from .mcp_env import LABEL_STUDIO_URL, get_ls

# The Label Studio client is created lazily on first tool/resource call (see
# ``require_ls_connection``). Importing the heavy SDK and building the client is
# kept out of module import so the MCP ``initialize`` handshake stays fast and
# clients like Claude Desktop don't time out on startup. This module-global is
# populated by ``require_ls_connection`` before any tool body runs, so the tool
# functions below can keep referencing ``ls`` directly.
ls = None

# Initialize FastMCP server
mcp = FastMCP("label-studio-mcp")


# --- Tool registration helpers with MCP annotations ---
# MCP clients (e.g. Claude) use these annotation hints to group tools in their
# permission UI into "Read-only", "Write/delete" and "Other" categories, and to
# decide how cautious to be before invoking a tool. Use the wrapper that matches
# a tool's behaviour instead of the bare ``@mcp.tool()``.

def read_tool(**kwargs):
    """Register a read-only tool (no side effects). -> "Read-only tools"."""
    return mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), **kwargs)


def write_tool(**kwargs):
    """Register a mutating, non-destructive tool. -> "Write/delete tools"."""
    return mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
        **kwargs,
    )


def destructive_tool(**kwargs):
    """Register a destructive tool (deletes/irreversible). -> "Write/delete tools"."""
    return mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
        **kwargs,
    )

# Helper to handle potential lack of LS connection
def _summarize_error_body(body) -> str:
    """Reduce an API error body to a short, single-line string.

    Server errors sometimes return a full HTML error page; returning that verbatim
    floods the client context. Strip markup and collapse whitespace, then truncate.
    """
    if body is None:
        return ""
    if isinstance(body, (dict, list)):
        text = json.dumps(body, default=str)
    else:
        text = str(body)
        if "<html" in text.lower() or "<!doctype" in text.lower():
            # Drop HTML tags so we keep only the human-readable message.
            text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300] + ("…" if len(text) > 300 else "")


def _format_tool_error(func_name: str, exc: Exception) -> str:
    """Render an exception as a compact JSON error string for MCP clients."""
    error = {"error": True, "tool": func_name, "type": type(exc).__name__}
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        error["status_code"] = status_code
        error["message"] = _summarize_error_body(getattr(exc, "body", None)) or str(exc)
        if status_code == 404:
            error["hint"] = (
                "Endpoint returned 404. The resource may not exist, or this API "
                "may not be available on your Label Studio edition/version."
            )
    else:
        error["message"] = str(exc)[:500]
    return json.dumps(error)


def require_ls_connection(func):
    # Preserve original signature using functools.wraps
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Build (or reuse) the Label Studio client on first use and expose it as
        # the module global so the wrapped tool/resource bodies can use ``ls``.
        global ls
        ls = get_ls()
        if ls is None:
            # Make the error message more informative
            return ("Error: Label Studio client not available. "
                    "Please check server logs for initialization errors "
                    "(e.g., missing 'LABEL_STUDIO_API_KEY', invalid key, or connection issue with 'LABEL_STUDIO_URL').")
        try:
            # Execute the wrapped function (tool or resource handler)
            return func(*args, **kwargs)
        except Exception as e:
            # Return a compact, JSON-serializable error (never a full HTML page).
            return _format_tool_error(func.__name__, e)
    return wrapper

# --- JSON Serializer for Datetime Objects ---
def json_datetime_serializer(obj):
    """JSON serializer for datetime objects.
    Converts datetime objects to ISO 8601 string format.
    """
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, (datetime.date, datetime.time)):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


# --- Generic serialization helpers ---
def _serialize(obj):
    """Best-effort conversion of SDK response objects into JSON-friendly structures.

    Handles pydantic models (model_dump / dict), datetimes, lists, dicts and
    primitive values so individual tools don't have to re-implement this logic.
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, (datetime.date, datetime.time)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_serialize(o) for o in obj]
    # Pydantic v2 models
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json")
        except Exception:
            try:
                return _serialize(obj.model_dump())
            except Exception:
                pass
    # Pydantic v1 / older models
    if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
        try:
            return _serialize(obj.dict())
        except Exception:
            pass
    return str(obj)


def _json(obj) -> str:
    """Serialize an arbitrary SDK response to a JSON string."""
    return json.dumps(_serialize(obj), default=json_datetime_serializer)


def _collect_pager(pager, limit: int = 100):
    """Materialize up to `limit` items from a SyncPager into a list of dicts."""
    items = []
    for i, item in enumerate(pager):
        if i >= limit:
            break
        items.append(_serialize(item))
    return items

# ============================================
# == Label Studio Tool Definitions          ==
# ============================================

@read_tool()
@require_ls_connection
def get_label_studio_projects_tool() -> str:
    """Lists available Label Studio projects (Tool version)."""
    # Use ls.projects.list() - returns a pager
    projects_pager = ls.projects.list()
    projects_summary = []
    projects_processed = 0
    # Iterate over the pager
    for project in projects_pager:  # <-- Iteration, no subscripting
        if projects_processed >= 100: # Limit for safety/brevity
            break
        project_data = {
            "id": project.id,
            "title": getattr(project, 'title', 'N/A'),
            "task_count": getattr(project, 'task_number', 0) # Use task_number attribute
        }
        projects_summary.append(project_data)
        projects_processed += 1

    return json.dumps(projects_summary)

@read_tool()
@require_ls_connection
def get_label_studio_project_details_tool(project_id: int) -> str:
    """Provides details for a specific Label Studio project (Tool version)."""
    project = ls.projects.get(id=project_id) 
    # Assuming the project object has model_dump or dict method
    if hasattr(project, 'model_dump'):
        project_data = project.model_dump(exclude={'created_at', 'updated_at'})
        project_data['created_at'] = project.created_at.isoformat() if project.created_at else None
        return json.dumps(project_data)
    elif hasattr(project, 'dict'):
         project_dict = project.dict()
         project_dict['created_at'] = project.created_at.isoformat() if project.created_at else None # Handle datetime if it exists
         project_dict.pop('updated_at', None)
         return json.dumps(project_dict)
    else:
        # Fallback if direct serialization is not available
        return json.dumps({"id": project.id, "title": getattr(project, 'title', 'N/A')})

@read_tool()
@require_ls_connection
def get_label_studio_project_config_tool(project_id: int) -> str:
    """Provides the XML labeling configuration for a Label Studio project (Tool version)."""
    project = ls.projects.get(id=project_id)
    return project.label_config

@read_tool()
@require_ls_connection
def list_label_studio_project_tasks_tool(project_id: int) -> str:
    """Lists tasks within a specific Label Studio project (Tool version). Fetches up to 50 tasks.
    Note: This retrieves basic task info (ID and data keys) for brevity.
    """
    # Corrected: Use ls.tasks.list - this returns a pager
    tasks_pager = ls.tasks.list(project=project_id) 
    
    task_list_summary = []
    tasks_processed = 0
    # Iterate directly over the pager object and manually limit
    for task in tasks_pager:
        if tasks_processed >= 50:
            break # Stop after processing 50 tasks
            
        task_summary = {"id": task.id}
        if hasattr(task, 'data') and isinstance(task.data, dict):
            task_summary["data_keys"] = list(task.data.keys())
        else:
            task_summary["data_keys"] = []
        task_list_summary.append(task_summary)
        tasks_processed += 1
        
    return json.dumps(task_list_summary)

@read_tool()
@require_ls_connection
def get_label_studio_task_data_tool(project_id: int, task_id: int) -> str:
    """Provides the data payload for a specific Label Studio task (Tool version)."""
    task = ls.tasks.get(id=task_id)
    # Assuming task object has a data attribute which is a dictionary
    if hasattr(task, 'data'):
        return json.dumps(task.data)
    else:
        return json.dumps({}) # Return empty dict if data attribute missing

@read_tool()
@require_ls_connection
def get_label_studio_task_annotations_tool(project_id: int, task_id: int) -> str:
    """Provides annotations for a specific Label Studio task (Tool version)."""
    task = ls.tasks.get(id=task_id)
    
    if not hasattr(task, 'get_annotations'):
        raise AttributeError(f"Task object (id: {task_id}) does not have get_annotations method.")
        
    annotations = task.get_annotations()
    # Assuming get_annotations returns a list of objects with model_dump or dict
    serialized_annotations = []
    for anno in annotations:
        if hasattr(anno, 'model_dump'):
            serialized_annotations.append(anno.model_dump())
        elif hasattr(anno, 'dict'):
            serialized_annotations.append(anno.dict())
        elif isinstance(anno, dict):
            serialized_annotations.append(anno) # If already a dict
        else:
            # Fallback for unknown annotation format
            serialized_annotations.append({"details": str(anno)})

    return json.dumps(serialized_annotations)

@write_tool()
@require_ls_connection
def create_label_studio_project_tool(
    title: str, 
    label_config: str, # Expecting XML string from the caller
    description: str | None = None,
    expert_instruction: str | None = None,
    show_instruction: bool | None = False,
    show_skip_button: bool | None = True,
    enable_empty_annotation: bool | None = True,
    show_annotation_history: bool | None = False,
    color: str | None = None,
    # Add other relevant parameters from API/SDK as needed
) -> str:
    """Creates a new Label Studio project using the SDK (Tool version).
    Returns JSON including the project details and a direct link to the project's data manager view.
    
    Args:
        title (str): The title for the new project. REQUIRED.
        label_config (str): The XML string defining the labeling interface. REQUIRED.
        description (str | None): Optional description for the project.
        expert_instruction (str | None): Optional instructions for labelers.
        # ... add descriptions for other parameters ...
        
    IMPORTANT Call Guidance:
    - For optional string parameters (like 'description', 'expert_instruction', 'color'): 
      If you do not want to provide a value, **omit the parameter entirely** from your call.
      Do not pass `null` or an empty string `""` unless you specifically intend for that value.

    Reference: https://github.com/HumanSignal/label-studio-sdk?tab=readme-ov-file#create-a-new-project
               https://api.labelstud.io/api-reference/api-reference/projects/create
    """
    kwargs = {
        "title": title, 
        "label_config": label_config, 
        "description": description,
        "expert_instruction": expert_instruction,
        "show_instruction": show_instruction,
        "show_skip_button": show_skip_button,
        "enable_empty_annotation": enable_empty_annotation,
        "show_annotation_history": show_annotation_history,
        "color": color,
    }
    # Filter out None values to avoid sending them in the request
    # This internal filtering handles cases where the parameter *was* omitted in the call
    filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None}

    # Pass the filtered keyword arguments directly to ls.projects.create
    project = ls.projects.create(**filtered_kwargs)
    
    # Construct the project URL
    project_url = f"{LABEL_STUDIO_URL}/projects/{project.id}/data"
    
    # Manually construct the response dictionary with reliable attributes
    response_data = {
        "id": project.id,
        "title": project.title,
        "project_url": project_url, # Add the URL to the response
    }
    # Attempt to add other fields common in the full API response if they exist
    for attr in ['description', 'color', 'expert_instruction', 'created_at', 'label_config']:
        if hasattr(project, attr):
            value = getattr(project, attr)
            # Handle datetime serialization
            if hasattr(value, 'isoformat'):
                response_data[attr] = value.isoformat()
            else:
                response_data[attr] = value
                
    return json.dumps(response_data)

@write_tool()
@require_ls_connection
def update_label_studio_project_config_tool(
    project_id: int,
    new_label_config: str, # The complete, updated XML config string
) -> str:
    """Updates the labeling configuration for a specific Label Studio project.
    
    Args:
        project_id (int): The ID of the project to update.
        new_label_config (str): The **complete** new XML labeling configuration string.
            This will replace the existing configuration.

    Returns:
        JSON string containing the details of the updated project, including the new 
        label config and a link to the project URL.
        
    Reference: Uses ls.projects.update from the SDK v1.0+ (assumed based on PATCH API endpoint).
    """
    try:
        # Call the update method directly on the client's projects manager
        updated_project = ls.projects.update(id=project_id, label_config=new_label_config)
        
        # Construct the project URL
        project_url = f"{LABEL_STUDIO_URL}/projects/{updated_project.id}/data"
        
        # Manually construct the response dictionary 
        # (assuming updated_project might not have reliable serialization)
        response_data = {
            "id": updated_project.id,
            "title": getattr(updated_project, 'title', 'N/A'), # Safely get attributes
            "label_config": getattr(updated_project, 'label_config', new_label_config),
            "project_url": project_url, 
            "message": "Project configuration updated successfully."
        }
        # Attempt to add other common fields if they exist
        for attr in ['description', 'color', 'expert_instruction', 'created_at']:
            if hasattr(updated_project, attr):
                value = getattr(updated_project, attr)
                if hasattr(value, 'isoformat'):
                    response_data[attr] = value.isoformat()
                else:
                    response_data[attr] = value
                    
        return json.dumps(response_data)

    except Exception as e:
        # Catch errors specifically during the update API call
        import traceback
        return f"Error during Label Studio project config update API call: {type(e).__name__} - {e}\n{traceback.format_exc()}"

@write_tool()
@require_ls_connection
def import_label_studio_project_tasks_tool(
    project_id: int,
    # Change parameter to accept a file path
    tasks_file_path: str, 
) -> str:
    """Imports tasks into a specific Label Studio project from a JSON file.
    Returns JSON including the import summary and a direct link to the project's data manager view.
    
    Args:
        project_id (int): The ID of the target Label Studio project.
        tasks_file_path (str): The path (relative to workspace or absolute) 
                             to a JSON file containing the tasks to import. 
                             The file MUST contain a valid JSON array (list) 
                             of task data dictionaries.
    
    Example file content (e.g., tasks.json):
    [
        {"data": {"text": "Sentence 1"}},
        {"data": {"text": "Sentence 2"}}
    ]

    Reference: Uses ls.projects.import_tasks from the SDK v1.0+.
               https://api.labelstud.io/api-reference/introduction/getting-started
    """
    tasks_list = None
    try:
        # Read and parse the JSON file
        with open(tasks_file_path, 'r') as f:
            tasks_list = json.load(f) # Use json.load for file handle
            
        if not isinstance(tasks_list, list):
            raise ValueError(f"JSON file '{tasks_file_path}' must contain a valid JSON array (list).")
        
        # Optional: Add validation for task format within the list if needed
        
    except FileNotFoundError:
        return f"Error: Tasks file not found at path: {tasks_file_path}"
    except PermissionError:
        return f"Error: Permission denied when trying to read file: {tasks_file_path}"
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON format in file '{tasks_file_path}' - {e}"
    except ValueError as e:
        return f"Error processing tasks file: {e}"
    except Exception as e:
        import traceback
        return f"Unexpected error reading/processing tasks file '{tasks_file_path}': {type(e).__name__} - {e}\n{traceback.format_exc()}"

    # We don't need to get the project object first for bulk import using ls.projects.import_tasks
    # project = ls.projects.get(id=project_id) # Removed

    # Construct the project URL
    project_url = f"{LABEL_STUDIO_URL}/projects/{project_id}/data"

    # Call the import method directly on the client's projects manager
    # Use 'request' parameter based on SDK v1.0+ documentation
    try:
        import_result = ls.projects.import_tasks(id=project_id, request=tasks_list)
    except Exception as e:
        # Catch errors specifically during the import API call
        import traceback
        return f"Error during Label Studio task import API call: {type(e).__name__} - {e}\n{traceback.format_exc()}"

    # Prepare the final response dictionary
    final_response = {}
    if isinstance(import_result, dict):
        final_response = import_result.copy() # Start with the SDK result
    elif hasattr(import_result, 'model_dump'):
        final_response = import_result.model_dump()
    elif hasattr(import_result, 'dict'):
        final_response = import_result.dict()
    else:
        # Basic fallback
        final_response = {"message": "Import initiated", "details": str(import_result)}
        
    # Add the project URL to the response
    final_response["project_url"] = project_url

    return json.dumps(final_response)

@write_tool()
@require_ls_connection
def import_label_studio_tasks_inline_tool(
    project_id: int,
    tasks: List[Dict[str, Any]],
) -> str:
    """Imports tasks into a Label Studio project directly from an inline array (no file).

    Use this when the tasks are available in the conversation rather than as a file on
    the server's filesystem. Pre-annotations are preserved: include ``predictions`` and/or
    ``annotations`` on each task and they are sent to Label Studio in a single request.

    Args:
        project_id (int): The ID of the target Label Studio project.
        tasks (list[dict]): A non-empty list of task objects. Each item should be shaped
            like ``{"data": {...}, "predictions"?: [...], "annotations"?: [...]}``.
            ``predictions``/``annotations`` are optional.

    Returns:
        JSON string with ``project_id``, ``imported_task_count`` and the raw Label Studio
        import summary (which includes prediction/annotation counts), plus a link to the
        project's data manager view. After calling, verify with
        ``list_label_studio_project_tasks_tool`` / ``get_label_studio_task_data_tool``
        rather than relying solely on this return value (the MCP transport may time out a
        slow call even when the import succeeded server-side).

    Reference: Uses ls.projects.import_tasks (POST /api/projects/{id}/import) from the SDK v1.0+.
    """
    # Validate input up front so the caller gets a clear message instead of an opaque API error.
    if not isinstance(tasks, list):
        return "Error: 'tasks' must be a JSON array (list) of task objects."
    if not tasks:
        return "Error: 'tasks' is empty; provide at least one task object."
    if not all(isinstance(t, dict) for t in tasks):
        return "Error: every item in 'tasks' must be an object (dict), e.g. {\"data\": {...}}."

    project_url = f"{LABEL_STUDIO_URL}/projects/{project_id}/data"

    # Single API call; predictions/annotations inside each task travel in the same request body.
    import_result = ls.projects.import_tasks(id=project_id, request=tasks)

    summary = _serialize(import_result)
    if not isinstance(summary, dict):
        summary = {"details": summary}

    # LS returns the number of created tasks as ``task_count``; surface it explicitly for easy verification.
    imported_task_count = summary.get("task_count")

    final_response = {
        "project_id": project_id,
        "imported_task_count": imported_task_count,
        "import_summary": summary,
        "project_url": project_url,
    }

    return json.dumps(final_response, ensure_ascii=False, default=str)

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
def _clean(**kwargs):
    return {k: v for k, v in kwargs.items() if v is not None}


# --- Span (NER) offset validation -----------------------------------------
# Label Studio does NOT validate text-span start/end against the task text: a
# mismatch is accepted silently and renders a shifted label in the UI. These
# helpers verify offsets against the real task text before sending.
#
# To support configs with multiple text inputs, a span's data field is resolved
# from the project's parsed_label_config (control from_name -> inputs[].value)
# rather than guessing. The parsed config is cached per project for the process.

_PARSED_CONFIG_CACHE: Dict[int, Any] = {}


def _get_parsed_label_config(project_id):
    """Return the project's parsed_label_config dict (cached per project_id)."""
    if project_id is None:
        return None
    if project_id in _PARSED_CONFIG_CACHE:
        return _PARSED_CONFIG_CACHE[project_id]
    parsed = None
    try:
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


# ============================================================
# == Projects (additional CRUD)                             ==
# ============================================================

@write_tool()
@require_ls_connection
def update_label_studio_project_tool(
    project_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    label_config: Optional[str] = None,
    expert_instruction: Optional[str] = None,
    show_instruction: Optional[bool] = None,
    show_skip_button: Optional[bool] = None,
    enable_empty_annotation: Optional[bool] = None,
    show_annotation_history: Optional[bool] = None,
    reveal_preannotations_interactively: Optional[bool] = None,
    show_collab_predictions: Optional[bool] = None,
    maximum_annotations: Optional[int] = None,
    color: Optional[str] = None,
    workspace: Optional[int] = None,
    model_version: Optional[str] = None,
) -> str:
    """Updates settings for an existing Label Studio project.

    Only the parameters you pass are changed; omit any you don't want to modify.
    Use `update_label_studio_project_config_tool` if you only need to change the
    labeling configuration XML.

    Args:
        project_id (int): ID of the project to update. REQUIRED.
        title, description, label_config, ... : Optional fields to update.
    """
    updated = ls.projects.update(
        id=project_id,
        **_clean(
            title=title,
            description=description,
            label_config=label_config,
            expert_instruction=expert_instruction,
            show_instruction=show_instruction,
            show_skip_button=show_skip_button,
            enable_empty_annotation=enable_empty_annotation,
            show_annotation_history=show_annotation_history,
            reveal_preannotations_interactively=reveal_preannotations_interactively,
            show_collab_predictions=show_collab_predictions,
            maximum_annotations=maximum_annotations,
            color=color,
            workspace=workspace,
            model_version=model_version,
        ),
    )
    return _json(updated)


@destructive_tool()
@require_ls_connection
def delete_label_studio_project_tool(project_id: int) -> str:
    """Permanently deletes a Label Studio project and all of its tasks/annotations.

    Args:
        project_id (int): ID of the project to delete. REQUIRED.
    """
    ls.projects.delete(id=project_id)
    return json.dumps({"message": f"Project {project_id} deleted successfully.", "id": project_id})


@read_tool()
@require_ls_connection
def validate_label_studio_project_config_tool(project_id: int, label_config: str) -> str:
    """Validates an XML labeling configuration against a project without saving it.

    Args:
        project_id (int): ID of the project to validate against. REQUIRED.
        label_config (str): The XML labeling configuration string to validate. REQUIRED.
    """
    result = ls.projects.validate_config(id=project_id, label_config=label_config)
    return _json(result)


# ============================================================
# == Tasks (additional CRUD)                                ==
# ============================================================

@write_tool()
@require_ls_connection
def create_label_studio_task_tool(project_id: int, data: Dict[str, Any]) -> str:
    """Creates a single task in a Label Studio project.

    Args:
        project_id (int): ID of the target project. REQUIRED.
        data (Dict[str, Any]): The task data payload, e.g. {"text": "Hello world"}. REQUIRED.
    """
    task = ls.tasks.create(project=project_id, data=data)
    return _json(task)


@write_tool()
@require_ls_connection
def update_label_studio_task_tool(
    task_id: int,
    data: Optional[Dict[str, Any]] = None,
    project: Optional[int] = None,
) -> str:
    """Updates the data payload of an existing task.

    Args:
        task_id (int): ID of the task to update. REQUIRED.
        data (Dict[str, Any]): New data payload for the task.
        project (int): Optionally move the task to a different project.
    """
    task = ls.tasks.update(id=str(task_id), **_clean(data=data, project=project))
    return _json(task)


@destructive_tool()
@require_ls_connection
def delete_label_studio_task_tool(task_id: int) -> str:
    """Deletes a single task (and its annotations) by ID.

    Args:
        task_id (int): ID of the task to delete. REQUIRED.
    """
    ls.tasks.delete(id=str(task_id))
    return json.dumps({"message": f"Task {task_id} deleted successfully.", "id": task_id})


@destructive_tool()
@require_ls_connection
def delete_all_label_studio_project_tasks_tool(project_id: int) -> str:
    """Deletes ALL tasks (and their annotations) from a project. Irreversible.

    Args:
        project_id (int): ID of the project whose tasks should be deleted. REQUIRED.
    """
    ls.tasks.delete_all_tasks(id=project_id)
    return json.dumps({"message": f"All tasks deleted from project {project_id}.", "project_id": project_id})


# ============================================================
# == Annotations                                            ==
# ============================================================

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

@read_tool()
@require_ls_connection
def list_label_studio_users_tool() -> str:
    """Lists all users in the Label Studio instance."""
    users = ls.users.list()
    return _json(users)


@read_tool()
@require_ls_connection
def get_label_studio_user_tool(user_id: int) -> str:
    """Retrieves a single user by ID.

    Args:
        user_id (int): ID of the user. REQUIRED.
    """
    user = ls.users.get(id=user_id)
    return _json(user)


@read_tool()
@require_ls_connection
def get_label_studio_current_user_tool() -> str:
    """Returns the currently authenticated user (whoami)."""
    user = ls.users.whoami()
    return _json(user)


@write_tool()
@require_ls_connection
def create_label_studio_user_tool(
    email: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    username: Optional[str] = None,
    phone: Optional[str] = None,
) -> str:
    """Creates a new user.

    Args:
        email (str): Email address for the new user. REQUIRED.
        first_name, last_name, username, phone: Optional profile fields.
    """
    user = ls.users.create(
        email=email,
        **_clean(first_name=first_name, last_name=last_name, username=username, phone=phone),
    )
    return _json(user)


@write_tool()
@require_ls_connection
def update_label_studio_user_tool(
    user_id: int,
    email: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    username: Optional[str] = None,
    phone: Optional[str] = None,
) -> str:
    """Updates an existing user's profile.

    Args:
        user_id (int): ID of the user to update. REQUIRED.
        email, first_name, last_name, username, phone: Optional fields to update.
    """
    user = ls.users.update(
        id=user_id,
        **_clean(email=email, first_name=first_name, last_name=last_name, username=username, phone=phone),
    )
    return _json(user)


@destructive_tool()
@require_ls_connection
def delete_label_studio_user_tool(user_id: int) -> str:
    """Deletes a user by ID.

    Args:
        user_id (int): ID of the user to delete. REQUIRED.
    """
    ls.users.delete(id=user_id)
    return json.dumps({"message": f"User {user_id} deleted successfully.", "id": user_id})


# ============================================================
# == Workspaces                                             ==
# ============================================================

@read_tool()
@require_ls_connection
def list_label_studio_workspaces_tool() -> str:
    """Lists all workspaces."""
    workspaces = ls.workspaces.list()
    return _json(workspaces)


@read_tool()
@require_ls_connection
def get_label_studio_workspace_tool(workspace_id: int) -> str:
    """Retrieves a single workspace by ID.

    Args:
        workspace_id (int): ID of the workspace. REQUIRED.
    """
    workspace = ls.workspaces.get(id=workspace_id)
    return _json(workspace)


@write_tool()
@require_ls_connection
def create_label_studio_workspace_tool(
    title: str,
    description: Optional[str] = None,
    color: Optional[str] = None,
    is_public: Optional[bool] = None,
) -> str:
    """Creates a new workspace.

    Args:
        title (str): Title of the workspace. REQUIRED.
        description (str): Optional description.
        color (str): Optional hex color for the workspace.
        is_public (bool): Optionally mark the workspace as public.
    """
    workspace = ls.workspaces.create(
        title=title,
        **_clean(description=description, color=color, is_public=is_public),
    )
    return _json(workspace)


@write_tool()
@require_ls_connection
def update_label_studio_workspace_tool(
    workspace_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    color: Optional[str] = None,
    is_public: Optional[bool] = None,
    is_archived: Optional[bool] = None,
) -> str:
    """Updates an existing workspace.

    Args:
        workspace_id (int): ID of the workspace to update. REQUIRED.
        title, description, color, is_public, is_archived: Optional fields to update.
    """
    workspace = ls.workspaces.update(
        id=workspace_id,
        **_clean(title=title, description=description, color=color, is_public=is_public, is_archived=is_archived),
    )
    return _json(workspace)


@destructive_tool()
@require_ls_connection
def delete_label_studio_workspace_tool(workspace_id: int) -> str:
    """Deletes a workspace by ID.

    Args:
        workspace_id (int): ID of the workspace to delete. REQUIRED.
    """
    ls.workspaces.delete(id=workspace_id)
    return json.dumps({"message": f"Workspace {workspace_id} deleted successfully.", "id": workspace_id})


# ============================================================
# == Views (Data Manager tabs)                              ==
# ============================================================

@read_tool()
@require_ls_connection
def list_label_studio_views_tool(project_id: Optional[int] = None) -> str:
    """Lists Data Manager views (tabs), optionally filtered by project.

    Args:
        project_id (int): Optional project ID to filter the views.
    """
    views = ls.views.list(**_clean(project=project_id))
    return _json(views)


@read_tool()
@require_ls_connection
def get_label_studio_view_tool(view_id: int) -> str:
    """Retrieves a single Data Manager view by ID.

    Args:
        view_id (int): ID of the view. REQUIRED.
    """
    view = ls.views.get(id=str(view_id))
    return _json(view)


@write_tool()
@require_ls_connection
def create_label_studio_view_tool(project_id: int, data: Optional[Dict[str, Any]] = None) -> str:
    """Creates a Data Manager view (tab) for a project.

    Args:
        project_id (int): ID of the project the view belongs to. REQUIRED.
        data (Dict[str, Any]): Optional view configuration (filters, ordering,
            title, etc.), e.g. {"title": "My Tab", "filters": {...}}.
    """
    view = ls.views.create(project=project_id, **_clean(data=data))
    return _json(view)


@write_tool()
@require_ls_connection
def update_label_studio_view_tool(
    view_id: int,
    data: Optional[Dict[str, Any]] = None,
    project_id: Optional[int] = None,
) -> str:
    """Updates a Data Manager view.

    Args:
        view_id (int): ID of the view to update. REQUIRED.
        data (Dict[str, Any]): New view configuration (filters, ordering, title, etc.).
        project_id (int): Optional project association.
    """
    view = ls.views.update(id=str(view_id), **_clean(data=data, project=project_id))
    return _json(view)


@destructive_tool()
@require_ls_connection
def delete_label_studio_view_tool(view_id: int) -> str:
    """Deletes a Data Manager view by ID.

    Args:
        view_id (int): ID of the view to delete. REQUIRED.
    """
    ls.views.delete(id=str(view_id))
    return json.dumps({"message": f"View {view_id} deleted successfully.", "id": view_id})


# ============================================================
# == Comments                                               ==
# ============================================================

@read_tool()
@require_ls_connection
def list_label_studio_comments_tool(
    project_id: Optional[int] = None,
    annotation_id: Optional[int] = None,
) -> str:
    """Lists comments, optionally filtered by project and/or annotation.

    Args:
        project_id (int): Optional project ID filter.
        annotation_id (int): Optional annotation ID filter.
    """
    comments = ls.comments.list(**_clean(project=project_id, annotation=annotation_id))
    return _json(comments)


@read_tool()
@require_ls_connection
def get_label_studio_comment_tool(comment_id: int) -> str:
    """Retrieves a single comment by ID.

    Args:
        comment_id (int): ID of the comment. REQUIRED.
    """
    comment = ls.comments.get(id=comment_id)
    return _json(comment)


@write_tool()
@require_ls_connection
def create_label_studio_comment_tool(
    annotation_id: int,
    text: str,
    project_id: Optional[int] = None,
    is_resolved: Optional[bool] = None,
) -> str:
    """Creates a comment on an annotation.

    Args:
        annotation_id (int): ID of the annotation to comment on. REQUIRED.
        text (str): The comment text. REQUIRED.
        project_id (int): Optional project ID. Some Label Studio configurations
            require the project to be supplied alongside the annotation.
        is_resolved (bool): Optionally mark the comment as resolved.

    Note: the comments API is not available on every Label Studio edition/version.
    A 404 response usually means commenting isn't enabled on your instance rather
    than a problem with the annotation ID.
    """
    comment = ls.comments.create(
        annotation=annotation_id,
        text=text,
        **_clean(project=project_id, is_resolved=is_resolved),
    )
    return _json(comment)


@write_tool()
@require_ls_connection
def update_label_studio_comment_tool(
    comment_id: int,
    text: Optional[str] = None,
    is_resolved: Optional[bool] = None,
) -> str:
    """Updates a comment.

    Args:
        comment_id (int): ID of the comment to update. REQUIRED.
        text (str): Optional new comment text.
        is_resolved (bool): Optionally toggle the resolved flag.
    """
    comment = ls.comments.update(id=comment_id, **_clean(text=text, is_resolved=is_resolved))
    return _json(comment)


@destructive_tool()
@require_ls_connection
def delete_label_studio_comment_tool(comment_id: int) -> str:
    """Deletes a comment by ID.

    Args:
        comment_id (int): ID of the comment to delete. REQUIRED.
    """
    ls.comments.delete(id=comment_id)
    return json.dumps({"message": f"Comment {comment_id} deleted successfully.", "id": comment_id})


# ============================================================
# == Webhooks                                               ==
# ============================================================

@read_tool()
@require_ls_connection
def list_label_studio_webhooks_tool(project_id: Optional[int] = None) -> str:
    """Lists webhooks, optionally filtered by project.

    Args:
        project_id (int): Optional project ID filter.
    """
    webhooks = ls.webhooks.list(**_clean(project=str(project_id) if project_id is not None else None))
    return _json(webhooks)


@read_tool()
@require_ls_connection
def get_label_studio_webhook_tool(webhook_id: int) -> str:
    """Retrieves a single webhook by ID.

    Args:
        webhook_id (int): ID of the webhook. REQUIRED.
    """
    webhook = ls.webhooks.get(id=webhook_id)
    return _json(webhook)


@write_tool()
@require_ls_connection
def create_label_studio_webhook_tool(
    url: str,
    project: Optional[int] = None,
    send_payload: Optional[bool] = None,
    send_for_all_actions: Optional[bool] = None,
    is_active: Optional[bool] = None,
    actions: Optional[List[str]] = None,
    headers: Optional[Dict[str, Any]] = None,
) -> str:
    """Creates a webhook.

    Args:
        url (str): Destination URL that will receive webhook events. REQUIRED.
        project (int): Optional project to scope the webhook to (omit for org-wide).
        send_payload (bool): Whether to include the payload in the request body.
        send_for_all_actions (bool): Trigger for all actions instead of a subset.
        is_active (bool): Whether the webhook is active.
        actions (List[str]): Specific actions to subscribe to, e.g.
            ["TASKS_CREATED", "ANNOTATION_CREATED"].
        headers (Dict[str, Any]): Optional custom HTTP headers to send.
    """
    webhook = ls.webhooks.create(
        url=url,
        **_clean(
            project=project,
            send_payload=send_payload,
            send_for_all_actions=send_for_all_actions,
            is_active=is_active,
            actions=actions,
            headers=headers,
        ),
    )
    return _json(webhook)


@write_tool()
@require_ls_connection
def update_label_studio_webhook_tool(
    webhook_id: int,
    url: str,
    send_payload: Optional[bool] = None,
    send_for_all_actions: Optional[bool] = None,
    is_active: Optional[bool] = None,
    actions: Optional[List[str]] = None,
) -> str:
    """Updates an existing webhook.

    Args:
        webhook_id (int): ID of the webhook to update. REQUIRED.
        url (str): Destination URL for the webhook. REQUIRED.
        send_payload (bool): Whether to include the payload in the request body.
        send_for_all_actions (bool): Trigger for all actions instead of a subset.
        is_active (bool): Whether the webhook is active.
        actions (List[str]): Specific actions to subscribe to.
    """
    webhook = ls.webhooks.update(
        id_=webhook_id,
        url=url,
        webhook_serializer_for_update_url=url,
        **_clean(
            send_payload=send_payload,
            send_for_all_actions=send_for_all_actions,
            is_active=is_active,
            actions=actions,
        ),
    )
    return _json(webhook)


@destructive_tool()
@require_ls_connection
def delete_label_studio_webhook_tool(webhook_id: int) -> str:
    """Deletes a webhook by ID.

    Args:
        webhook_id (int): ID of the webhook to delete. REQUIRED.
    """
    ls.webhooks.delete(id=webhook_id)
    return json.dumps({"message": f"Webhook {webhook_id} deleted successfully.", "id": webhook_id})


@read_tool()
@require_ls_connection
def get_label_studio_webhook_actions_tool() -> str:
    """Returns the list of available webhook actions/events and their metadata."""
    return _json(ls.webhooks.info())


# ============================================================
# == ML Backends                                            ==
# ============================================================

@read_tool()
@require_ls_connection
def list_label_studio_ml_backends_tool(project_id: Optional[int] = None) -> str:
    """Lists connected ML backends, optionally filtered by project.

    Args:
        project_id (int): Optional project ID filter.
    """
    backends = ls.ml.list(**_clean(project=project_id))
    return _json(backends)


@read_tool()
@require_ls_connection
def get_label_studio_ml_backend_tool(ml_backend_id: int) -> str:
    """Retrieves a single ML backend by ID.

    Args:
        ml_backend_id (int): ID of the ML backend. REQUIRED.
    """
    backend = ls.ml.get(id=ml_backend_id)
    return _json(backend)


@write_tool()
@require_ls_connection
def create_label_studio_ml_backend_tool(
    url: str,
    project: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    is_interactive: Optional[bool] = None,
) -> str:
    """Connects a new ML backend to a project.

    Args:
        url (str): URL of the ML backend server. REQUIRED.
        project (int): ID of the project to attach the backend to. REQUIRED.
        title (str): Optional display title.
        description (str): Optional description.
        is_interactive (bool): Whether the backend supports interactive pre-annotation.
    """
    backend = ls.ml.create(
        url=url,
        project=project,
        **_clean(title=title, description=description, is_interactive=is_interactive),
    )
    return _json(backend)


@write_tool()
@require_ls_connection
def update_label_studio_ml_backend_tool(
    ml_backend_id: int,
    url: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    is_interactive: Optional[bool] = None,
) -> str:
    """Updates an existing ML backend.

    Args:
        ml_backend_id (int): ID of the ML backend to update. REQUIRED.
        url, title, description, is_interactive: Optional fields to update.
    """
    backend = ls.ml.update(
        id=ml_backend_id,
        **_clean(url=url, title=title, description=description, is_interactive=is_interactive),
    )
    return _json(backend)


@destructive_tool()
@require_ls_connection
def delete_label_studio_ml_backend_tool(ml_backend_id: int) -> str:
    """Deletes (disconnects) an ML backend by ID.

    Args:
        ml_backend_id (int): ID of the ML backend to delete. REQUIRED.
    """
    ls.ml.delete(id=ml_backend_id)
    return json.dumps({"message": f"ML backend {ml_backend_id} deleted successfully.", "id": ml_backend_id})


@write_tool()
@require_ls_connection
def train_label_studio_ml_backend_tool(ml_backend_id: int, use_ground_truth: Optional[bool] = None) -> str:
    """Triggers a training run on an ML backend.

    Args:
        ml_backend_id (int): ID of the ML backend to train. REQUIRED.
        use_ground_truth (bool): Whether to train only on ground-truth annotations.
    """
    ls.ml.train(id=ml_backend_id, **_clean(use_ground_truth=use_ground_truth))
    return json.dumps({"message": f"Training triggered for ML backend {ml_backend_id}.", "id": ml_backend_id})


# ============================================================
# == Data Manager Actions (bulk operations)                 ==
# ============================================================

@destructive_tool()
@require_ls_connection
def run_label_studio_action_tool(
    action_id: str,
    project_id: int,
    view_id: Optional[int] = None,
    selected_task_ids: Optional[List[int]] = None,
    all_tasks: Optional[bool] = None,
) -> str:
    """Runs a Data Manager bulk action on a project's tasks.

    Args:
        action_id (str): Action to run. One of: 'retrieve_tasks_predictions',
            'predictions_to_annotations', 'remove_duplicates', 'delete_tasks',
            'delete_ground_truths', 'delete_tasks_annotations',
            'delete_tasks_reviews', 'delete_tasks_predictions',
            'delete_reviewers', 'delete_annotators'. REQUIRED.
        project_id (int): ID of the target project. REQUIRED.
        view_id (int): Optional Data Manager view (tab) ID to scope the action.
        selected_task_ids (List[int]): Specific task IDs to act on. If provided,
            only these tasks are included.
        all_tasks (bool): If True, apply the action to all tasks (excluding none).
    """
    kwargs = {"id": action_id, "project": project_id}
    if view_id is not None:
        kwargs["view"] = view_id
    if selected_task_ids is not None:
        kwargs["selected_items"] = {"all": False, "included": selected_task_ids}
    elif all_tasks:
        kwargs["selected_items"] = {"all": True, "excluded": []}
    response = {
        "message": f"Action '{action_id}' executed on project {project_id}.",
        "action_id": action_id,
        "project_id": project_id,
    }

    # The SDK's actions.create discards the response body, but Label Studio often
    # returns a count of affected items (e.g. {"processed_items": N}). Issue the
    # request through the SDK's already-configured HTTP client so we can surface
    # those metrics. The action is executed exactly once: we only fall back to the
    # plain SDK call when the SDK internals are unavailable (i.e. before any request
    # is sent), never after a request that may have already mutated data.
    http_client = getattr(getattr(ls, "_client_wrapper", None), "httpx_client", None)
    if http_client is None:
        ls.actions.create(**kwargs)
        return json.dumps(response)

    raw = http_client.request(
        "api/dm/actions/",
        method="POST",
        params={"id": action_id, "project": project_id, "view": view_id},
        json={"selectedItems": kwargs.get("selected_items")},
        headers={"content-type": "application/json"},
    )
    if not (200 <= raw.status_code < 300):
        return json.dumps({
            "error": True,
            "tool": "run_label_studio_action_tool",
            "status_code": raw.status_code,
            "message": _summarize_error_body(raw.text),
        })

    try:
        body = raw.json()
    except Exception:
        body = None
    if isinstance(body, dict):
        response["result"] = body
        for key in ("processed_items", "processed", "count", "reannotated_count", "detail"):
            if key in body:
                response["processed_count"] = body[key]
                break

    return json.dumps(_serialize(response))


# ============================================================
# == Exports                                                ==
# ============================================================

@read_tool()
@require_ls_connection
def export_label_studio_project_tasks_tool(project_id: int) -> str:
    """Exports a project's tasks and annotations as JSON.

    Returns the exported data (list of tasks with their annotations) as a JSON string.

    Args:
        project_id (int): ID of the project to export. REQUIRED.
    """
    exported = ls.projects.exports.as_json(project_id)
    return _json(exported)


@read_tool()
@require_ls_connection
def list_label_studio_export_formats_tool(project_id: int) -> str:
    """Lists the export formats available for a project.

    Args:
        project_id (int): ID of the project. REQUIRED.
    """
    return _json(ls.projects.exports.list_formats(project_id))


# ============================================================
# == Instance / version info                                ==
# ============================================================

@read_tool()
@require_ls_connection
def get_label_studio_version_tool() -> str:
    """Returns version and build information for the Label Studio instance."""
    return _json(ls.versions.get())


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


# ============================================================
# == Project analytics / progress                           ==
# ============================================================

@read_tool()
@require_ls_connection
def get_label_studio_project_statistics_tool(project_id: int) -> str:
    """Return progress statistics for a project (counts + completion percentage).

    Reads the project's summary fields in a single API call: total tasks, tasks with
    annotations, total annotations/predictions, useful/ground-truth/skipped/finished
    counts, and a derived completion percentage.

    Args:
        project_id (int): ID of the project. REQUIRED.
    """
    project = ls.projects.get(id=project_id)

    def field(name):
        return getattr(project, name, None)

    total = field("task_number") or 0
    with_annotations = field("num_tasks_with_annotations") or 0
    stats = {
        "project_id": project_id,
        "title": getattr(project, "title", None),
        "task_number": total,
        "num_tasks_with_annotations": with_annotations,
        "total_annotations_number": field("total_annotations_number"),
        "total_predictions_number": field("total_predictions_number"),
        "useful_annotation_number": field("useful_annotation_number"),
        "ground_truth_number": field("ground_truth_number"),
        "skipped_annotations_number": field("skipped_annotations_number"),
        "finished_task_number": field("finished_task_number"),
        "completion_percentage": round(with_annotations / total * 100, 2) if total else 0.0,
    }
    return json.dumps(stats)


@read_tool()
@require_ls_connection
def get_label_studio_annotator_statistics_tool(project_id: int, max_tasks: int = 200) -> str:
    """Best-effort per-annotator breakdown of completed annotations for a project.

    Samples up to `max_tasks` tasks and tallies, per annotator (user id), how many
    annotations they completed and how many are marked ground truth. For large
    projects this is a sample, not the full total — raise `max_tasks` to widen it.
    Inter-annotator agreement requires the Label Studio Enterprise stats API and is
    not computed here.

    Args:
        project_id (int): ID of the project. REQUIRED.
        max_tasks (int): Maximum number of tasks to sample (default 200).
    """
    per_annotator: Dict[str, Dict[str, int]] = {}
    tasks_sampled = 0
    annotations_counted = 0

    for task in ls.tasks.list(project=project_id):
        if tasks_sampled >= max_tasks:
            break
        tasks_sampled += 1
        annotations = getattr(task, "annotations", None)
        if not annotations:
            fetched = _fetch_task(getattr(task, "id", None))
            annotations = getattr(fetched, "annotations", None) if fetched is not None else None
        if not isinstance(annotations, list):
            continue
        for annotation in annotations:
            if not isinstance(annotation, dict):
                annotation = _serialize(annotation)
            if not isinstance(annotation, dict):
                continue
            user = annotation.get("completed_by")
            if isinstance(user, dict):
                user = user.get("id", user.get("email"))
            key = str(user) if user is not None else "unknown"
            record = per_annotator.setdefault(key, {"annotations": 0, "ground_truth": 0})
            record["annotations"] += 1
            if annotation.get("ground_truth"):
                record["ground_truth"] += 1
            annotations_counted += 1

    return json.dumps({
        "project_id": project_id,
        "tasks_sampled": tasks_sampled,
        "annotations_counted": annotations_counted,
        "max_tasks": max_tasks,
        "per_annotator": per_annotator,
        "note": (
            "Sampled up to max_tasks; counts may be partial for large projects. "
            "Agreement metrics require Label Studio Enterprise."
        ),
    })


# ============================================================
# == MCP Resources (browsable read-only context)           ==
# ============================================================
# Expose read-only Label Studio data as MCP resources so clients can attach it as
# context (e.g. @-mention a project's config) without an explicit tool call.

@mcp.resource("labelstudio://projects")
@require_ls_connection
def projects_resource() -> str:
    """All Label Studio projects (id, title, task_count) as a JSON list."""
    projects = []
    for index, project in enumerate(ls.projects.list()):
        if index >= 100:
            break
        projects.append({
            "id": project.id,
            "title": getattr(project, "title", "N/A"),
            "task_count": getattr(project, "task_number", 0),
        })
    return json.dumps(projects)


@mcp.resource("labelstudio://project/{project_id}/config")
@require_ls_connection
def project_config_resource(project_id: str) -> str:
    """The XML labeling configuration for a single project."""
    return ls.projects.get(id=int(project_id)).label_config


@mcp.resource("labelstudio://project/{project_id}/summary")
@require_ls_connection
def project_summary_resource(project_id: str) -> str:
    """Progress statistics for a single project as JSON."""
    return get_label_studio_project_statistics_tool(int(project_id))


# ============================================================
# == MCP Prompts (guided workflows)                         ==
# ============================================================

@mcp.prompt()
def setup_labeling_project(description: str) -> str:
    """Guided workflow: create a Label Studio project for a described task."""
    return (
        "You are setting up a Label Studio project.\n\n"
        f"Task description from the user:\n{description}\n\n"
        "Steps:\n"
        "1. Choose the data type (text/hypertext/image/audio) and control "
        "(choices/labels/rectanglelabels/rating/textarea) that fit the task.\n"
        "2. Call generate_label_studio_label_config_tool to build a valid XML config.\n"
        "3. Review the XML with the user, then call create_label_studio_project_tool "
        "with a clear title and that label_config.\n"
        "4. Report the new project id and its data-manager URL."
    )


@mcp.prompt()
def assess_annotation_quality(project_id: str) -> str:
    """Guided workflow: review annotation progress and quality for a project."""
    return (
        f"Assess annotation progress and quality for Label Studio project {project_id}.\n\n"
        "Steps:\n"
        "1. Call get_label_studio_project_statistics_tool for totals and completion %.\n"
        "2. Call get_label_studio_annotator_statistics_tool for the per-annotator breakdown.\n"
        "3. Summarise progress, workload balance across annotators and ground-truth "
        "coverage, and flag annotators/tasks that look like outliers.\n"
        "4. Recommend next actions (add reviewers, rebalance workload, set ground truth)."
    )


@mcp.prompt()
def generate_predictions_plan(project_id: str) -> str:
    """Guided workflow: plan adding model predictions to a project's tasks."""
    return (
        f"Plan generating model predictions for Label Studio project {project_id}.\n\n"
        "Steps:\n"
        "1. Call get_label_studio_project_config_tool to learn the labeling schema "
        "(control names, labels, the data field).\n"
        "2. Call list_label_studio_project_tasks_tool to find tasks that need predictions.\n"
        "3. For each task, build a prediction 'result' matching the schema (for text "
        "spans include the exact text and character offsets), then call "
        "create_label_studio_prediction_tool.\n"
        "4. Report how many predictions were created and any tasks skipped."
    )