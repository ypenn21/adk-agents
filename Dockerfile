# Use a Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Install the project into `/app`
WORKDIR /app

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml ./

# Generate a fresh lock file and install dependencies. This avoids using a
# potentially stale local uv.lock and improves caching.
RUN uv lock && \
    uv sync --frozen --no-install-project --no-dev

# Copy the rest of the application source code.
COPY . .
# Install the project itself.
RUN uv sync --frozen --no-dev

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Collect static files
RUN python manage.py collectstatic --noinput

# Create a non-root user and group
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup appuser

# Change ownership of the /app directory
RUN chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Expose the port
EXPOSE 8080

# Run Gunicorn as the production server
ENTRYPOINT ["gunicorn", "web_ui.wsgi:application", "--bind", "0.0.0.0:8080"]:
