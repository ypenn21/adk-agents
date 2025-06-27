# Use a Python image with uv pre-installed
# Stage 1: Builder - Installs dependencies and collects static files
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

# Install the project into `/app`
WORKDIR /app

# Set environment variables for uv and Python
ENV UV_LINK_MODE=copy
ENV PYTHONUNBUFFERED=1

# Copy only dependency management files first to leverage Docker cache
COPY pyproject.toml ./
# If you use uv.lock for reproducible builds, uncomment the line below.
# Otherwise, `uv lock` will generate one if it doesn't exist.
# COPY uv.lock ./

# Generate a fresh lock file and install dependencies. This avoids using a
# potentially stale local uv.lock and improves caching.
RUN uv lock && \
    uv sync --frozen --no-install-project --no-dev

# Copy the rest of the application source code.
# Ensure you have a .dockerignore file to exclude unnecessary files (e.g., .git, tests, docs).
COPY . .

# Install the project itself.
RUN uv sync --frozen --no-dev

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Collect static files
RUN python manage.py collectstatic --noinput # This command typically outputs to a directory like 'staticfiles'

# Stage 2: Final image - A smaller runtime image
FROM python:3.13-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1

# Copy only the necessary artifacts from the builder stage
COPY --from=builder /app/.venv /app/.venv 
COPY --from=builder /app/staticfiles /app/staticfiles
COPY --from=builder /app/web_ui /app/web_ui
COPY --from=builder /app/adk_bug_ticket_agent /app/adk_bug_ticket_agent
COPY --from=builder /app/manage.py /app/manage.py
COPY --from=builder /app/gunicorn.conf.py /app/gunicorn.conf.py
# Add any other application-specific directories/files needed at runtime

# Set the PATH to include the virtual environment's bin directory
ENV PATH="/app/.venv/bin:$PATH"

# Create a non-root user and group for security best practices
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup appuser && chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Expose the port
EXPOSE 8080

# Run Gunicorn as the production server
ENTRYPOINT ["gunicorn", "web_ui.wsgi:application", "--bind", "0.0.0.0:8080"]
