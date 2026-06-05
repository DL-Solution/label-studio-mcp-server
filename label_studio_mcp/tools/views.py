"""Data-manager view tools."""

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
