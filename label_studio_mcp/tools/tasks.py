"""Task CRUD and import tools."""

import json
from typing import Any, Dict, List, Optional

from ..server import (
    read_tool,
    write_tool,
    destructive_tool,
    require_ls_connection,
)
from ..serialization import _json, _serialize, _clean
from ..mcp_env import LABEL_STUDIO_URL

# Populated by ``require_ls_connection`` before each tool body runs.
ls = None


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
