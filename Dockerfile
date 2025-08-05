# Use an official Python runtime as a parent image. The slim variant
# provides a small footprint while still including pip.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Set working directory inside the container
WORKDIR /app

# Copy requirements file and install dependencies. Separating
# dependency installation from copying the rest of the code allows
# Docker to cache the installed packages when the code changes.
COPY uv.lock pyproject.toml ./
RUN uv sync --locked

# Copy the application code
COPY awesome-todo-server.py .

# Environment variables: set the path for the JSON file. When using
# docker run you can override this value and mount a host volume to
# ``/data`` to persist task data across container restarts.
ENV TODO_JSON_PATH=/data/todos.json
ENV SERVER_PORT=3000


# Default command to run the MCP server. The ``python`` command
# executes the module directly and calls ``mcp.run`` in the main
# block. You can set the ``transport`` argument in the code to
# ``streamable-http`` or override at runtime via an environment
# variable if desired.
CMD ["uv", "run", "awesome-todo-server.py"]