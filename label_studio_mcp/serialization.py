"""JSON serialization helpers shared by all MCP tools.

The Label Studio SDK returns pydantic models, datetimes and pagers. These helpers
convert those into JSON-friendly structures so individual tools don't have to
re-implement the logic.
"""

import datetime
import json


def json_datetime_serializer(obj):
    """JSON serializer for datetime objects.
    Converts datetime objects to ISO 8601 string format.
    """
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, (datetime.date, datetime.time)):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


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


def _clean(**kwargs):
    """Drop keys whose value is None, for building request payloads from optionals."""
    return {k: v for k, v in kwargs.items() if v is not None}
