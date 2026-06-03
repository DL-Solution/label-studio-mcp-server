# Label Studio MCP Server

## Overview

This project provides a Model Context Protocol (MCP) server that allows interaction with a [Label Studio](https://labelstud.io/) instance using the `label-studio-sdk`. It enables programmatic management of labeling projects, tasks, and predictions via natural language or structured calls from MCP clients. Using this MCP Server, you can make requests like: 

* "Create a project in label studio with this data ..." 
* "How many tasks are labeled in my RAG review project?" 
* "Add predictions for my tasks." 
* "Update my labeling template to include a comment box." 

<img src="./static/example.png" alt="Example usage of Label Studio MCP Server" width="600">

## Features

The server exposes the full Label Studio REST API surface as MCP tools:

*   **Project Management**: Create, update, delete, list, validate configs, view details/configurations, and export projects.
*   **Task Management**: Create, update, delete, import, and list tasks; bulk-delete all tasks in a project.
*   **Annotation Management**: Create, read, update, delete, and list annotations for tasks.
*   **Prediction Integration**: Create, read, update, delete, and list model predictions.
*   **User Management**: Create, read, update, delete, list users, and resolve the current user (whoami).
*   **Workspace Management**: Create, read, update, delete, and list workspaces.
*   **Data Manager Views**: Create, read, update, delete, and list views (tabs), plus run bulk Data Manager actions.
*   **Comments**: Create, read, update, delete, and list annotation comments.
*   **Webhooks**: Create, read, update, delete, and list webhooks and inspect available webhook actions.
*   **ML Backends**: Connect, read, update, delete, list, and trigger training on ML backends.
*   **Instance Info**: Retrieve Label Studio version/build information.
*   **SDK Integration**: Leverages the official `label-studio-sdk` for communication.

## Prerequisites

1.  **Running Label Studio Instance:** You need a running instance of Label Studio accessible from where this MCP server will run.
2.  **API Key:** Obtain an API key from your user account settings in Label Studio.

## Configuration

The MCP server requires [the URL and API key for your Label Studio instance](https://labelstud.io/guide/access_tokens). If launching the server via an MCP client configuration file, you can specify the environment variables directly within the server definition. This is often preferred for client-managed servers.

Add the following JSON entry to your `claude_desktop_config.json` file or Cursor MCP settings:

```json
{
    "mcpServers": {
        "label-studio": {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/HumanSignal/label-studio-mcp-server",
                "mcp-label-studio"
            ],
            "env": {
                "LABEL_STUDIO_API_KEY": "your_actual_api_key_here", // <-- Your API key
                "LABEL_STUDIO_URL": "http://localhost:8080"
            }
        }
    }
}
```
<!-- 
## Installation
Follow these instructions to install the server. 
```bash
git clone https://github.com/HumanSignal/label-studio-mcp-server.git 
cd label-studio-mcp-server

# Install dependencies using uv
uv venv
source .venv/bin/activate 
uv sync
```


    ```json
    {
      "mcpServers": {
        "label-studio": {
            "command": "uv",
            "args": [
                "--directory",
                "/path/to/your/label-studio-mcp-server", // <-- Update this path
                "run",
                "label-studio-mcp.py"
            ],
            "env": {
                "LABEL_STUDIO_API_KEY": "your_actual_api_key_here", // <-- Your API key
                "LABEL_STUDIO_URL": "http://localhost:8080"
            }
        }
      }
    }
    ```
    When configured this way, the `env` block injects the variables into the server process environment, and the script's `os.getenv()` calls will pick them up. -->

## Tools

The MCP server exposes the following tools:

### Project Management

*   **`get_label_studio_projects_tool()`**: Lists available projects (ID, title, task count).
*   **`get_label_studio_project_details_tool(project_id: int)`**: Retrieves detailed information for a specific project.
*   **`get_label_studio_project_config_tool(project_id: int)`**: Fetches the XML labeling configuration for a project.
*   **`create_label_studio_project_tool(title: str, label_config: str, ...)`**: Creates a new project with a title, XML config, and optional settings. Returns project details including a URL.
*   **`update_label_studio_project_tool(project_id: int, ...)`**: Updates project settings (title, description, config, annotation options, workspace, etc.). Only passed fields change.
*   **`update_label_studio_project_config_tool(project_id: int, new_label_config: str)`**: Updates the XML labeling configuration for an existing project.
*   **`validate_label_studio_project_config_tool(project_id: int, label_config: str)`**: Validates an XML config against a project without saving it.
*   **`delete_label_studio_project_tool(project_id: int)`**: Permanently deletes a project and all of its data.
*   **`export_label_studio_project_tasks_tool(project_id: int)`**: Exports the project's tasks and annotations as JSON.
*   **`list_label_studio_export_formats_tool(project_id: int)`**: Lists the export formats available for a project.

### Task Management

*   **`list_label_studio_project_tasks_tool(project_id: int)`**: Lists task IDs within a project (up to 50).
*   **`get_label_studio_task_data_tool(project_id: int, task_id: int)`**: Retrieves the data payload for a specific task.
*   **`get_label_studio_task_annotations_tool(project_id: int, task_id: int)`**: Fetches existing annotations for a specific task.
*   **`import_label_studio_project_tasks_tool(project_id: int, tasks_file_path: str)`**: Imports tasks from a JSON file (containing a list of task objects) into a project. Returns import summary and project URL.
*   **`create_label_studio_task_tool(project_id: int, data: Dict[str, Any])`**: Creates a single task with the given data payload.
*   **`update_label_studio_task_tool(task_id: int, data: Dict[str, Any], ...)`**: Updates a task's data payload (and optionally its project).
*   **`delete_label_studio_task_tool(task_id: int)`**: Deletes a single task and its annotations.
*   **`delete_all_label_studio_project_tasks_tool(project_id: int)`**: Deletes ALL tasks in a project (irreversible).

### Annotations

*   **`list_label_studio_task_annotations_tool(task_id: int)`**: Lists all annotations for a task (Annotations API).
*   **`get_label_studio_annotation_tool(annotation_id: int)`**: Retrieves a single annotation.
*   **`create_label_studio_annotation_tool(task_id: int, result: List[Dict[str, Any]], ...)`**: Creates an annotation for a task.
*   **`update_label_studio_annotation_tool(annotation_id: int, ...)`**: Updates an existing annotation.
*   **`delete_label_studio_annotation_tool(annotation_id: int)`**: Deletes an annotation.

### Predictions

*   **`create_label_studio_prediction_tool(task_id: int, result: List[Dict[str, Any]], ...)`**: Creates a prediction for a specific task. Requires the prediction result as a list of dictionaries matching the Label Studio format. Optional `model_version` and `score`.
*   **`list_label_studio_predictions_tool(task_id: int = None, project_id: int = None)`**: Lists predictions, optionally filtered by task and/or project.
*   **`get_label_studio_prediction_tool(prediction_id: int)`**: Retrieves a single prediction.
*   **`update_label_studio_prediction_tool(prediction_id: int, ...)`**: Updates an existing prediction.
*   **`delete_label_studio_prediction_tool(prediction_id: int)`**: Deletes a prediction.

### Users

*   **`list_label_studio_users_tool()`**: Lists all users.
*   **`get_label_studio_user_tool(user_id: int)`**: Retrieves a single user.
*   **`get_label_studio_current_user_tool()`**: Returns the currently authenticated user (whoami).
*   **`create_label_studio_user_tool(email: str, ...)`**: Creates a new user.
*   **`update_label_studio_user_tool(user_id: int, ...)`**: Updates a user's profile.
*   **`delete_label_studio_user_tool(user_id: int)`**: Deletes a user.

### Workspaces

*   **`list_label_studio_workspaces_tool()`**: Lists all workspaces.
*   **`get_label_studio_workspace_tool(workspace_id: int)`**: Retrieves a single workspace.
*   **`create_label_studio_workspace_tool(title: str, ...)`**: Creates a workspace.
*   **`update_label_studio_workspace_tool(workspace_id: int, ...)`**: Updates a workspace.
*   **`delete_label_studio_workspace_tool(workspace_id: int)`**: Deletes a workspace.

### Data Manager Views & Actions

*   **`list_label_studio_views_tool(project_id: int = None)`**: Lists Data Manager views (tabs).
*   **`get_label_studio_view_tool(view_id: int)`**: Retrieves a single view.
*   **`create_label_studio_view_tool(project_id: int, data: Dict[str, Any] = None)`**: Creates a view with optional filters/ordering.
*   **`update_label_studio_view_tool(view_id: int, ...)`**: Updates a view.
*   **`delete_label_studio_view_tool(view_id: int)`**: Deletes a view.
*   **`run_label_studio_action_tool(action_id: str, project_id: int, ...)`**: Runs a bulk Data Manager action (e.g. `delete_tasks`, `predictions_to_annotations`, `remove_duplicates`).

### Comments

*   **`list_label_studio_comments_tool(project_id: int = None, annotation_id: int = None)`**: Lists comments.
*   **`get_label_studio_comment_tool(comment_id: int)`**: Retrieves a single comment.
*   **`create_label_studio_comment_tool(annotation_id: int, text: str, ...)`**: Creates a comment on an annotation.
*   **`update_label_studio_comment_tool(comment_id: int, ...)`**: Updates a comment.
*   **`delete_label_studio_comment_tool(comment_id: int)`**: Deletes a comment.

### Webhooks

*   **`list_label_studio_webhooks_tool(project_id: int = None)`**: Lists webhooks.
*   **`get_label_studio_webhook_tool(webhook_id: int)`**: Retrieves a single webhook.
*   **`create_label_studio_webhook_tool(url: str, ...)`**: Creates a webhook.
*   **`update_label_studio_webhook_tool(webhook_id: int, url: str, ...)`**: Updates a webhook.
*   **`delete_label_studio_webhook_tool(webhook_id: int)`**: Deletes a webhook.
*   **`get_label_studio_webhook_actions_tool()`**: Lists the available webhook actions/events.

### ML Backends

*   **`list_label_studio_ml_backends_tool(project_id: int = None)`**: Lists connected ML backends.
*   **`get_label_studio_ml_backend_tool(ml_backend_id: int)`**: Retrieves a single ML backend.
*   **`create_label_studio_ml_backend_tool(url: str, project: int, ...)`**: Connects a new ML backend to a project.
*   **`update_label_studio_ml_backend_tool(ml_backend_id: int, ...)`**: Updates an ML backend.
*   **`delete_label_studio_ml_backend_tool(ml_backend_id: int)`**: Disconnects an ML backend.
*   **`train_label_studio_ml_backend_tool(ml_backend_id: int, ...)`**: Triggers a training run on an ML backend.

### Instance Info

*   **`get_label_studio_version_tool()`**: Returns version/build information for the Label Studio instance.

## Example Use Case

1.  Create a new project using `create_label_studio_project_tool`.
2.  Prepare a JSON file (`tasks.json`) with task data.
3.  Import tasks using `import_label_studio_project_tasks_tool`, providing the project ID from step 1 and the path to `tasks.json`.
4.  List task IDs using `list_label_studio_project_tasks_tool`.
5.  Get data for a specific task using `get_label_studio_task_data_tool`.
6.  Generate a prediction result structure (list of dicts).
7.  Add the prediction using `create_label_studio_prediction_tool`.



## Contact

For questions or support, reach out via [GitHub Issues](https://github.com/HumanSignal/label-studio-mcp-server/issues).
