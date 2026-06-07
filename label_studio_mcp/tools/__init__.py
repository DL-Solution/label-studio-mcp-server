"""Tool, resource and prompt modules for the Label Studio MCP server.

Importing this package registers every tool/resource/prompt on the shared
``FastMCP`` instance (each submodule applies the registration decorators at
import time) and re-exports the public tool functions so existing imports such
as ``from label_studio_mcp.mcp_server import get_label_studio_projects_tool``
keep working.
"""

from .projects import *  # noqa: F401,F403
from .tasks import *  # noqa: F401,F403
from .annotations import *  # noqa: F401,F403
from .predictions import *  # noqa: F401,F403
from .users import *  # noqa: F401,F403
from .workspaces import *  # noqa: F401,F403
from .views import *  # noqa: F401,F403
from .comments import *  # noqa: F401,F403
from .webhooks import *  # noqa: F401,F403
from .ml_backends import *  # noqa: F401,F403
from .actions import *  # noqa: F401,F403
from .config_gen import *  # noqa: F401,F403
from .statistics import *  # noqa: F401,F403
from .llm_labeling import *  # noqa: F401,F403
from .resources import *  # noqa: F401,F403
