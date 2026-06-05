"""MCP resources (browsable read-only context) and guided prompts."""

import json

from ..server import mcp, require_ls_connection
from .statistics import get_label_studio_project_statistics_tool

# Populated by ``require_ls_connection`` before each tool body runs.
ls = None


# ============================================================
# == MCP Resources (browsable read-only context)           ==
# ============================================================
# Expose read-only Label Studio data as MCP resources so clients can attach it as
# context (e.g. @-mention a project's config) without an explicit tool call.

@mcp.resource("labelstudio://projects")
@require_ls_connection
def projects_resource() -> str:
    """All Label Studio projects (id, title, task_count) as a JSON list."""
    projects = []
    for index, project in enumerate(ls.projects.list()):
        if index >= 100:
            break
        projects.append({
            "id": project.id,
            "title": getattr(project, "title", "N/A"),
            "task_count": getattr(project, "task_number", 0),
        })
    return json.dumps(projects)


@mcp.resource("labelstudio://project/{project_id}/config")
@require_ls_connection
def project_config_resource(project_id: str) -> str:
    """The XML labeling configuration for a single project."""
    return ls.projects.get(id=int(project_id)).label_config


@mcp.resource("labelstudio://project/{project_id}/summary")
@require_ls_connection
def project_summary_resource(project_id: str) -> str:
    """Progress statistics for a single project as JSON."""
    return get_label_studio_project_statistics_tool(int(project_id))


# ============================================================
# == MCP Prompts (guided workflows)                         ==
# ============================================================

@mcp.prompt()
def setup_labeling_project(description: str) -> str:
    """Guided workflow: create a Label Studio project for a described task."""
    return (
        "You are setting up a Label Studio project.\n\n"
        f"Task description from the user:\n{description}\n\n"
        "Steps:\n"
        "1. Choose the data type (text/hypertext/image/audio) and control "
        "(choices/labels/rectanglelabels/rating/textarea) that fit the task.\n"
        "2. Call generate_label_studio_label_config_tool to build a valid XML config.\n"
        "3. Review the XML with the user, then call create_label_studio_project_tool "
        "with a clear title and that label_config.\n"
        "4. Report the new project id and its data-manager URL."
    )


@mcp.prompt()
def assess_annotation_quality(project_id: str) -> str:
    """Guided workflow: review annotation progress and quality for a project."""
    return (
        f"Assess annotation progress and quality for Label Studio project {project_id}.\n\n"
        "Steps:\n"
        "1. Call get_label_studio_project_statistics_tool for totals and completion %.\n"
        "2. Call get_label_studio_annotator_statistics_tool for the per-annotator breakdown.\n"
        "3. Summarise progress, workload balance across annotators and ground-truth "
        "coverage, and flag annotators/tasks that look like outliers.\n"
        "4. Recommend next actions (add reviewers, rebalance workload, set ground truth)."
    )


@mcp.prompt()
def generate_predictions_plan(project_id: str) -> str:
    """Guided workflow: plan adding model predictions to a project's tasks."""
    return (
        f"Plan generating model predictions for Label Studio project {project_id}.\n\n"
        "Steps:\n"
        "1. Call get_label_studio_project_config_tool to learn the labeling schema "
        "(control names, labels, the data field).\n"
        "2. Call list_label_studio_project_tasks_tool to find tasks that need predictions.\n"
        "3. For each task, build a prediction 'result' matching the schema (for text "
        "spans include the exact text and character offsets), then call "
        "create_label_studio_prediction_tool.\n"
        "4. Report how many predictions were created and any tasks skipped."
    )
