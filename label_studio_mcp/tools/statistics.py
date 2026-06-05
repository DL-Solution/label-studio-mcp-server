"""Project analytics and annotator statistics tools."""

import json
from typing import Dict

from ..server import read_tool, require_ls_connection
from ..serialization import _serialize
from ..validation import _fetch_task

# Populated by ``require_ls_connection`` before each tool body runs.
ls = None


# ============================================================
# == Project analytics / progress                           ==
# ============================================================

@read_tool()
@require_ls_connection
def get_label_studio_project_statistics_tool(project_id: int) -> str:
    """Return progress statistics for a project (counts + completion percentage).

    Reads the project's summary fields in a single API call: total tasks, tasks with
    annotations, total annotations/predictions, useful/ground-truth/skipped/finished
    counts, and a derived completion percentage.

    Args:
        project_id (int): ID of the project. REQUIRED.
    """
    project = ls.projects.get(id=project_id)

    def field(name):
        return getattr(project, name, None)

    total = field("task_number") or 0
    with_annotations = field("num_tasks_with_annotations") or 0
    stats = {
        "project_id": project_id,
        "title": getattr(project, "title", None),
        "task_number": total,
        "num_tasks_with_annotations": with_annotations,
        "total_annotations_number": field("total_annotations_number"),
        "total_predictions_number": field("total_predictions_number"),
        "useful_annotation_number": field("useful_annotation_number"),
        "ground_truth_number": field("ground_truth_number"),
        "skipped_annotations_number": field("skipped_annotations_number"),
        "finished_task_number": field("finished_task_number"),
        "completion_percentage": round(with_annotations / total * 100, 2) if total else 0.0,
    }
    return json.dumps(stats)


@read_tool()
@require_ls_connection
def get_label_studio_annotator_statistics_tool(project_id: int, max_tasks: int = 200) -> str:
    """Best-effort per-annotator breakdown of completed annotations for a project.

    Samples up to `max_tasks` tasks and tallies, per annotator (user id), how many
    annotations they completed and how many are marked ground truth. For large
    projects this is a sample, not the full total — raise `max_tasks` to widen it.
    Inter-annotator agreement requires the Label Studio Enterprise stats API and is
    not computed here.

    Args:
        project_id (int): ID of the project. REQUIRED.
        max_tasks (int): Maximum number of tasks to sample (default 200).
    """
    per_annotator: Dict[str, Dict[str, int]] = {}
    tasks_sampled = 0
    annotations_counted = 0

    for task in ls.tasks.list(project=project_id):
        if tasks_sampled >= max_tasks:
            break
        tasks_sampled += 1
        annotations = getattr(task, "annotations", None)
        if not annotations:
            fetched = _fetch_task(getattr(task, "id", None))
            annotations = getattr(fetched, "annotations", None) if fetched is not None else None
        if not isinstance(annotations, list):
            continue
        for annotation in annotations:
            if not isinstance(annotation, dict):
                annotation = _serialize(annotation)
            if not isinstance(annotation, dict):
                continue
            user = annotation.get("completed_by")
            if isinstance(user, dict):
                user = user.get("id", user.get("email"))
            key = str(user) if user is not None else "unknown"
            record = per_annotator.setdefault(key, {"annotations": 0, "ground_truth": 0})
            record["annotations"] += 1
            if annotation.get("ground_truth"):
                record["ground_truth"] += 1
            annotations_counted += 1

    return json.dumps({
        "project_id": project_id,
        "tasks_sampled": tasks_sampled,
        "annotations_counted": annotations_counted,
        "max_tasks": max_tasks,
        "per_annotator": per_annotator,
        "note": (
            "Sampled up to max_tasks; counts may be partial for large projects. "
            "Agreement metrics require Label Studio Enterprise."
        ),
    })
