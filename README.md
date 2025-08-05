# Awesome ToDo MCP Server

This project is a simple-but-mighty ToDo list server built on the Model Context Protocol (MCP). It acts as a backend for LLM clients (think Gemini or Claude Code/Desktop), giving them a clean, well-defined API to read and update a persistent task list.

Full disclosure: I totally yolo vibe-coded this to poke at MCP servers and see what happened. Somehow, between coffee, curiosity, and a few “it compiles, ship it” moments, it turned into something I actually really like—so I’m sharing it. If you spot any overly enthusiastic variable names, just know they’re part of the vibe. 😄

Enjoy, and PRs welcome (especially the ones that turn “vibe” into “design”).

The server is built with Python using the `fastmcp` library and manages its dependencies with `uv`. It can be run directly or as a Docker container.

## Features

The server exposes a set of tools and resources for managing a ToDo list, which is stored in a JSON file.

- **List Tasks**: Retrieve all tasks in a structured format.
- **Add Task**: Create a new task with a title, description, due date, and priority.
- **Explain Task**: Get a human-readable summary of a task's context and importance.
- **Decompose Task**: Break down a complex task into smaller, manageable subtasks.
- **Prioritise Tasks**: Sort tasks based on the Eisenhower matrix (importance and urgency).
- **Recommend Tasks**: Get a list of the most relevant tasks to work on for the current day.
- **Mark as Completed**: Mark a task as done.

## Getting Started

### Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) (a fast Python package installer and resolver)

### Installation

1.  **Clone the repository:**

    ```bash
    git clone <repository-url>
    cd awesome_todo_mcp_server
    ```

2.  **Create a virtual environment and install dependencies:**
    `uv` will automatically create a virtual environment in the current directory and install all the packages listed in `pyproject.toml`.
    ```bash
    uv sync --locked
    ```

### Running the Server

Once the dependencies are installed, you can start the server:

```bash
uv run awesome-todo-server.py
```

The server will start on `http://0.0.0.0:3000` by default. You can configure the port by setting the `SERVER_PORT` environment variable.

## Docker Deployment

The project includes a `Dockerfile` and `docker-compose.yml` for easy containerization and deployment.

### Building the Docker Image

To build the image directly from the `Dockerfile`:

```bash
docker build -t awesome-todo-mcp .
```

### Running with Docker Compose

The `docker-compose.yml` file simplifies running the server in a container and managing data persistence.

1.  **Configure the Volume:**
    Before starting, you need to edit the `docker-compose.yml` file to specify a host path for your ToDo list data. Replace `path/to/your/todo/json` with an actual path on your local machine where you want to store the `todos.json` file.

    ```yaml
    services:
      awesome-todo-mcp:
        build: .
        environment:
          - SERVER_PORT=3000 # Port used by Server inside container
        ports:
          - "3000:3000" # Hostport:SERVER_PORT
        volumes:
          - /your/local/path:/data # <-- CHANGE THIS
    ```

2.  **Start the container:**
    ```bash
    docker-compose up -d
    ```

This starts the service in detached mode (building the image first if it doesn’t already exist). The API will be available by default at `http://localhost:3000`. Task data is persisted on the host in the directory you mapped to `/data` (that’s where `todos.json` is written).

Rebuilds after code changes: Because the application code is baked into the image (see `COPY awesome-todo-server.py` in the `Dockerfile`), you must rebuild the image whenever the code or dependencies change before starting again:

```bash
docker-compose up --build -d
# or
docker-compose build && docker-compose up -d
```

If you change the internal server port, adjust `SERVER_PORT` and the port mapping accordingly in `docker-compose.yml`. Data persistence is unaffected by container restarts as long as the host path bound to `/data` remains the same.

## Connecting with Gemini CLI

To connect the Gemini CLI to your running ToDo server, you need to add a server configuration to your `~/.gemini/settings.json` file. Add the following block inside the `mcpServers` object:

```json
"awesome-todo-mcp": {
  "httpUrl": "http://127.0.0.1:3000/mcp/"
}
```

Your `mcpServers` configuration should look something like this (you might have other servers listed as well):

```json
{
  "mcpServers": {
    "awesome-todo-mcp": {
      "httpUrl": "http://127.0.0.1:3000/mcp/"
    }
  }
}
```

After saving the changes, you can interact with your ToDo list through the Gemini CLI.
