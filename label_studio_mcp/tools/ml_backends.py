"""ML backend tools."""

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
