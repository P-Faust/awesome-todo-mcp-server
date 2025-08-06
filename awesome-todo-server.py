"""A simple ToDo server implemented with the Model Context Protocol (MCP).

This module defines a FastMCP server that exposes a set of resources and tools
for managing a JSON‑backed task list. It demonstrates how to use the
``mcp`` Python SDK to build a custom server, how to organise code for
structured outputs via Pydantic models and how to persist state in an
external file. The server exposes the following features:

* A resource for listing all tasks stored in a JSON file.
* Tools to add new tasks, explain an existing task, decompose a task
  into subtasks, prioritise tasks using the Eisenhower principle and
  recommend which tasks to tackle next.

To run this server directly as an HTTP server use the ``mcp.run`` call
in the ``main`` block. By specifying ``transport="streamable-http"`` the
server will expose a stateful HTTP API that MCP clients (such as
Gemini CLI or other LLM integrations) can connect to. The port can be
configured via the ``PORT`` environment variable; if unset the SDK
defaults to port 3000.

Note: This example focuses on demonstrating the MCP server pattern. The
explain/decompose functions include placeholders where calls to a
large‑language model (LLM) could be implemented. In production you
would integrate an actual AI service (e.g. via the OpenAI API) and
provide authentication via environment variables.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import List

#from mcp.server.fastmcp import Context, FastMCP
from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

###############################################################################
# Configuration
#
# The location of the JSON file used to persist tasks can be configured via
# the ``TODO_JSON_PATH`` environment variable. When running in a container
# it's common to mount a volume under ``/data`` and set this variable to
# ``/data/todos.json`` to persist data outside the container.
###############################################################################

DATA_PATH = os.getenv("TODO_JSON_PATH", "./todos.json")
SERVER_PORT = os.getenv("SERVER_PORT", 3000)


###############################################################################
# Data model
#
# The ``Task`` model defines the structure of each todo entry. Using a
# Pydantic model here allows MCP to automatically generate schemas for
# structured responses which makes it easier for LLMs to consume the data.
###############################################################################

class Task(BaseModel):
    """Representation of a single todo item.

    Attributes:
        id: A unique identifier for the task. In a production system you
            might use UUIDs; here we stick with integers for simplicity.
        title: A short title describing the task.
        description: A more detailed description of the task.
        due: The date by which the task should be completed.
        important: Whether the task is important (Eisenhower matrix).
        urgent: Whether the task is urgent (Eisenhower matrix).
        subtasks: A list of strings representing decomposed steps. This
            field is optional – it may be empty if the task has not been
            decomposed yet.
        completed: Flag indicating whether the task has been completed.
    """

    id: int = Field(..., description="Unique identifier for the task")
    title: str = Field(..., description="Short title for the task")
    description: str = Field(..., description="Detailed description of the task")
    due: date = Field(..., description="Due date in YYYY‑MM‑DD format")
    important: bool = Field(..., description="True if the task is important")
    urgent: bool = Field(..., description="True if the task is urgent")
    subtasks: List[str] = Field(default_factory=list, description="List of subtasks")
    completed: bool = Field(default=False, description="Whether the task is completed")


# After defining the Task model, ensure Pydantic resolves all forward references
# such as the ``date`` annotation. Without this call certain environments
# (including test harnesses) may raise a ``PydanticUserError`` complaining that
# the model is not fully defined. Calling ``model_rebuild`` resolves the
# annotations in place and avoids runtime errors when instantiating the model.
Task.model_rebuild()


###############################################################################
# Utility functions
#
# A pair of helpers for loading and saving tasks to the JSON file. These
# routines centralise all file I/O to simplify error handling and ensure
# consistent data representation.
###############################################################################

def _load_tasks() -> List[dict]:
    """Load tasks from the JSON file.

    Returns:
        A list of dictionaries representing tasks. If the file does not
        exist or is empty an empty list is returned.
    """
    if not os.path.exists(DATA_PATH):
        return []
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure we always return a list of dicts
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _save_tasks(tasks: List[dict]) -> None:
    """Persist the list of tasks to disk.

    Args:
        tasks: List of task dictionaries to write.
    """
    # Ensure the directory exists
    os.makedirs(os.path.dirname(DATA_PATH) or ".", exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, default=str)


###############################################################################
# MCP server setup
#
# We create an instance of ``FastMCP`` which is our server. Tools and
# resources are defined using decorators on this instance. When run with
# ``mcp.run()`` the server will listen for requests either via stdio or an
# HTTP transport depending on the chosen transport. See the bottom of the
# file for the entry point.
###############################################################################

mcp = FastMCP(name="Todo Server")


###############################################################################
# Resources
#
# Resources act like read‑only endpoints that deliver data to the client
# without causing side effects. We expose a single resource for listing all
# tasks. The URI template ``todos://list`` follows the conventions from
# the SDK documentation: it is arbitrary but should be descriptive.
###############################################################################

# @mcp.resource("todos://list")
# def list_tasks() -> List[Task]:
#     """Return the current list of tasks.
# 
#     This resource loads the raw JSON data and converts each entry into a
#     ``Task`` model. MCP will automatically serialise the list of Pydantic
#     objects into a structured response for the LLM client.
#     """
#     raw = _load_tasks()
#     return [Task(**t) for t in raw]
#
# The following tool is a temporary replacement for the resource above to
# ensure compatibility with clients that do not yet support MCP resources,
# such as the Gemini CLI. It will be removed once resource support is
# more widely available, ensuring full compatibility with clients like
# Claude Code.
@mcp.tool()
def list_tasks() -> List[Task]:
    """Return the current list of tasks.

    This tool loads the raw JSON data and converts each entry into a
    ``Task`` model. MCP will automatically serialise the list of Pydantic
    objects into a structured response for the LLM client.
    """
    raw = _load_tasks()
    return [Task(**t) for t in raw]


###############################################################################
# Tools
#
# Tools perform actions that may modify state or require computation. Each
# function decorated with ``@mcp.tool`` becomes invocable by the LLM. All
# tools use type annotations so that MCP can infer input schemas and return
# structured results.
###############################################################################

@mcp.tool()
def add_task(
    id: int,
    title: str,
    description: str,
    due: date,
    important: bool,
    urgent: bool,
    subtasks: List[str] | None = None,
    completed: bool = False,
) -> Task:
    """Add a new task to the list and return it.

    This version breaks out each field of the ``Task`` model into individual
    parameters. Passing a Pydantic model as an input parameter (as in the
    older version ``add_task(task: Task)``) can lead to JSON schema issues
    with some LLM clients. By using primitive types here we avoid those
    problems and still build a ``Task`` object internally.

    Args:
        id: Unique identifier for the new task.
        title: Short title describing the task.
        description: Detailed description of the task.
        due: Due date in YYYY‑MM‑DD format.
        important: Whether the task is important.
        urgent: Whether the task is urgent.
        subtasks: Optional list of subtasks (defaults to empty).
        completed: Flag indicating whether the task is already completed.

    Returns:
        The created ``Task`` instance.
    """
    # Default to an empty list if subtasks weren't provided
    if subtasks is None:
        subtasks = []
    # Construct a new Task object from the primitive parameters
    new_task = Task(
        id=id,
        title=title,
        description=description,
        due=due,
        important=important,
        urgent=urgent,
        subtasks=subtasks,
        completed=completed,
    )
    tasks = _load_tasks()
    tasks.append(new_task.model_dump())
    _save_tasks(tasks)
    return new_task


@mcp.tool()
def explain_task(task_id: int) -> str:
    """Explain the context and importance of a given task.

    This function looks up the task by its identifier and constructs a
    human‑readable explanation. In a production environment you could
    augment this explanation by calling an LLM such as OpenAI's GPT via
    their API. Here we generate a simple summary based on the task's
    attributes.

    Args:
        task_id: The identifier of the task to explain.

    Returns:
        A string explaining the task or a message if the task doesn't exist.
    """
    tasks = _load_tasks()
    task = next((t for t in tasks if t.get("id") == task_id), None)
    if task is None:
        return f"No task found with id {task_id}."
    # Build a simple explanation using the Eisenhower matrix
    importance = "important" if task.get("important") else "not important"
    urgency = "urgent" if task.get("urgent") else "not urgent"
    due = task.get("due")
    return (
        f"Task '{task.get('title')}' is {importance} and {urgency}. "
        f"It is due on {due}. Description: {task.get('description')}"
    )


@mcp.tool()
def decompose_task(task_id: int) -> List[str]:
    """Break a task down into smaller subtasks.

    For demonstration we split the description into sentences and treat each
    sentence as a subtask. In practice you would use an LLM call to
    generate a more intelligent breakdown (e.g. via OpenAI's API). The
    generated subtasks are saved back into the task's ``subtasks`` field.

    Args:
        task_id: Identifier of the task to decompose.

    Returns:
        A list of subtasks. Returns an empty list if the task is not found.
    """
    tasks = _load_tasks()
    for t in tasks:
        if t.get("id") == task_id:
            description = t.get("description", "")
            # Naive sentence splitting on periods; trim whitespace
            parts = [s.strip() for s in description.split(".") if s.strip()]
            t["subtasks"] = parts
            _save_tasks(tasks)
            return parts
    return []


@mcp.tool()
def prioritise_tasks() -> List[Task]:
    """Sort tasks by importance, urgency and due date.

    Implements the Eisenhower matrix: important & urgent tasks first,
    followed by important but not urgent, then urgent but not important,
    and finally tasks that are neither. Within each category tasks are
    sorted by their due date ascending.

    Returns:
        A sorted list of ``Task`` models.
    """
    raw_tasks = _load_tasks()
    # Define a key that reflects the Eisenhower priority order. False sorts
    # before True, so we invert booleans to prioritise True values.
    def sort_key(t: dict) -> tuple:
        return (
            not t.get("important", False),  # important tasks first (False < True)
            not t.get("urgent", False),     # urgent tasks within same importance
            t.get("due", date.max)           # earlier due dates first
        )

    sorted_tasks = sorted(raw_tasks, key=sort_key)
    return [Task(**t) for t in sorted_tasks]


@mcp.tool()
def recommend_tasks_for_today(ctx: Context) -> List[Task]:
    """Recommend the next tasks to work on.

    This tool uses the current date to filter and sort tasks. It selects
    incomplete tasks and orders them using the same priority rules as
    ``prioritise_tasks``. Optionally, the LLM client could provide a date
    argument; here we always use the server's date (Europe/Berlin timezone
    applies because the user is based in Neunkirchen). Only the top
    five tasks are returned to keep the list manageable.

    Args:
        ctx: The MCP context (unused here but included for extensibility).

    Returns:
        A list of up to five ``Task`` objects representing the most
        appropriate tasks to tackle today.
    """
    today = date.today()
    raw_tasks = _load_tasks()
    # Filter out completed tasks
    candidates = [t for t in raw_tasks if not t.get("completed", False)]
    # Sort using the same Eisenhower logic as above
    def sort_key(t: dict) -> tuple:
        return (
            not t.get("important", False),
            not t.get("urgent", False),
            t.get("due", date.max)
        )
    sorted_candidates = sorted(candidates, key=sort_key)
    # Return the first five tasks
    top_tasks = sorted_candidates[:5]
    return [Task(**t) for t in top_tasks]


@mcp.tool()
def mark_task_completed(task_id: int) -> str:
    """Mark a task as completed.

    This helper illustrates how to update a field on a task. The function
    searches for the task by ID, sets its ``completed`` flag to ``True`` and
    saves the changes. It returns a confirmation message or an error.

    Args:
        task_id: Identifier of the task to mark complete.

    Returns:
        A human‑readable message describing the outcome.
    """
    tasks = _load_tasks()
    for t in tasks:
        if t.get("id") == task_id:
            t["completed"] = True
            _save_tasks(tasks)
            return f"Task {task_id} marked as completed."
    return f"Task {task_id} not found."


@mcp.tool()
def archive_completed_tasks() -> str:
    """Archive all completed tasks.

    This tool moves all tasks marked as 'completed' from the active
    todos.json file to a separate todo_archiv.json file. This helps
    to keep the active task list clean and focused on pending items.

    Returns:
        A string confirming the number of tasks that were archived.
    """
    tasks = _load_tasks()
    completed_tasks = [t for t in tasks if t.get("completed")]
    incomplete_tasks = [t for t in tasks if not t.get("completed")]

    if not completed_tasks:
        return "No completed tasks to archive."

    # Save the incomplete tasks back to the main file
    _save_tasks(incomplete_tasks)

    # Append completed tasks to the archive file
    archive_path = os.path.join(os.path.dirname(DATA_PATH), "todo_archive.json")
    archived_tasks = []
    if os.path.exists(archive_path):
        with open(archive_path, "r", encoding="utf-8") as f:
            try:
                archived_tasks = json.load(f)
            except json.JSONDecodeError:
                archived_tasks = []

    archived_tasks.extend(completed_tasks)

    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(archived_tasks, f, indent=2, default=str)

    return f"Archived {len(completed_tasks)} completed tasks."


@mcp.tool()
def view_archived_tasks() -> List[Task]:
    """View all archived tasks.

    This tool reads the archived tasks from the `todo_archive.json` file
    and returns them as a list.

    Returns:
        A list of ``Task`` models representing the archived tasks.
    """
    archive_path = os.path.join(os.path.dirname(DATA_PATH), "todo_archive.json")
    if not os.path.exists(archive_path):
        return []
    try:
        with open(archive_path, "r", encoding="utf-8") as f:
            archived_tasks = json.load(f)
        if isinstance(archived_tasks, list):
            return [Task(**t) for t in archived_tasks]
        return []
    except (json.JSONDecodeError, FileNotFoundError):
        return []


###############################################################################
# Entry point
#
# When executed directly this module will start the MCP server. The transport
# is configured for streamable HTTP, which is recommended for new deployments
# (according to the SDK documentation, SSE is being phased out【987358258832706†L1103-L1123】). When
# run in a container the port will default to 3000 unless overridden by the
# ``PORT`` environment variable recognised by the SDK.
###############################################################################

def main() -> None:
    """Start the MCP server.

    The ``transport`` parameter controls how clients connect to the server.
    ``streamable-http`` provides an HTTP API with Server‑Sent Events (SSE)
    streaming for responses, which many LLM clients support. Other options
    include ``stdio`` for direct process communication and ``sse`` for
    legacy SSE transport. See the SDK documentation for details【987358258832706†L1080-L1098】.
    """
    mcp.run(transport="http", host="0.0.0.0", port=int(SERVER_PORT))

if __name__ == "__main__":
    main()
