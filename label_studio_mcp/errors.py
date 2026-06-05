"""Error rendering helpers shared by all MCP tools.

Tool bodies raise ordinary exceptions; ``require_ls_connection`` catches them and
renders a compact, JSON-serializable string via ``_format_tool_error`` so MCP
clients never receive a full HTML error page in their context window.
"""

import json
import re


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
