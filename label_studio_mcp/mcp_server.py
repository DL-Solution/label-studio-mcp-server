"""Backwards-compatible facade for the Label Studio MCP server.

The implementation was split out of this module into focused modules:

  - ``server``        — the ``FastMCP`` instance + tool-registration decorators
  - ``errors``        — error rendering helpers
  - ``serialization`` — JSON serialization helpers
  - ``validation``    — span (NER) offset validation
  - ``tools/*``        — the tool / resource / prompt definitions, by resource

Importing this module still exposes ``mcp`` and every tool function by name, so
``from label_studio_mcp.mcp_server import mcp`` (used by ``main``) and the
re-exports in ``label_studio_mcp/__init__.py`` keep working unchanged.
"""

from .server import (  # noqa: F401
    mcp,
    read_tool,
    write_tool,
    destructive_tool,
    require_ls_connection,
)
from .errors import _summarize_error_body, _format_tool_error  # noqa: F401
from .serialization import (  # noqa: F401
    json_datetime_serializer,
    _serialize,
    _json,
    _collect_pager,
    _clean,
)
from .validation import (  # noqa: F401
    _get_parsed_label_config,
    _resolve_task_text,
    _resolve_field,
    _validate_spans,
    _fetch_task,
    _validate_result_spans,
)
from .tools import *  # noqa: F401,F403
