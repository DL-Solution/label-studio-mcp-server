"""Comment tools."""

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
