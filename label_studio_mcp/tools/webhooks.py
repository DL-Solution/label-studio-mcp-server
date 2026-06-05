"""Webhook tools."""

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
