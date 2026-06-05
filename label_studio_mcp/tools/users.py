"""User management tools."""

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
