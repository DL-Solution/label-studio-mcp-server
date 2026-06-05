"""Data-manager actions, export and version tools."""

import json
from typing import Any, Dict, List, Optional

from ..server import (
    read_tool,
    write_tool,
    destructive_tool,
    require_ls_connection,
)
from ..serialization import _json, _serialize, _clean

# Populated by ``require_ls_connection`` before each tool body runs.
ls = None


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
