"""Workspace management tools."""

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
