# Feature Implementation Plan: Migrate Django to FastAPI

## 📋 Todo Checklist
- [ ] Update `pyproject.toml` dependencies (remove Django, add FastAPI/Uvicorn).
- [ ] Create `main.py` as the new application entry point.
- [ ] Port `interact_with_agent` view logic to FastAPI endpoints.
- [ ] Update HTML template to use Jinja2 syntax.
- [ ] Integrate existing A2A agent application.
- [ ] Update `Dockerfile` for FastAPI/Uvicorn.
- [ ] Remove obsolete Django files (`manage.py`, `web/`, `gunicorn.conf.py`).
- [ ] Final Review and Testing.

## 🔍 Analysis & Investigation

### Codebase Structure
- **`adk_bug_ticket_agent/`**: Contains the core agent logic (`agent.py`), tools (`tools/`), and UI views (`views.py`).
- **`web/`**: Django project configuration (settings, urls, wsgi). This will be retired.
- **`pyproject.toml`**: Manages dependencies.
- **`Dockerfile`**: Builds the image using `gunicorn` and `manage.py`.

### Current Architecture
- **Monolithic Django**: Serves both the Web UI (HTML/JSON) and the Agent logic.
- **Agent Logic**: `agent.py` defines the ADK agent and tools. It also conditionally creates a Starlette app for A2A (Agent-to-Agent) communication when not in Django mode.
- **Web UI**: `views.py` handles the chat interface, managing sessions and invoking the `Runner` to execute the agent.

### Dependencies & Integration Points
- **Dependencies**: Currently relies on `django`, `whitenoise`, `gunicorn`. These will be replaced by `fastapi`, `uvicorn`, `jinja2`, `python-multipart`.
- **Database**: Uses `psycopg2-binary` for `google-adk`'s `DatabaseSessionService`. This dependency remains.
- **Agent**: The `_service_manager` in `agent.py` is a singleton managing the agent and services. This can be directly imported and used in FastAPI.

### Considerations & Challenges
- **Template Tags**: Django templates use `{% url %}` which differs slightly from Jinja2's `{{ url_for() }}`.
- **Static Files**: Need to ensure static files (if any) are served correctly, though the current project seems to rely mostly on inline styles or external assets.
- **A2A Integration**: `agent.py` already builds a Starlette app for A2A. We should mount this or use it as a base to ensure the agent remains accessible via A2A protocols.

## 📝 Implementation Plan

### Prerequisites
- Ensure `uv` is installed and the virtual environment is active.

### Step-by-Step Implementation

1.  **Step 1**: Update Dependencies
    -   Files to modify: `pyproject.toml`
    -   Changes needed:
        -   Remove: `django`, `whitenoise`, `gunicorn`.
        -   Add: `fastapi`, `uvicorn`, `jinja2`, `python-multipart`.

2.  **Step 2**: Create FastAPI Entry Point
    -   Files to modify: Create `main.py` (in project root).
    -   Changes needed:
        -   Initialize `FastAPI` app.
        -   Setup `StaticFiles` (mount `/static` to a static directory if needed, or create an empty one).
        -   Setup `Jinja2Templates` pointing to `adk_bug_ticket_agent/templates`.
        -   Import `app` (the A2A app) from `adk_bug_ticket_agent.agent` and mount it (e.g., under `/a2a` or merge routes if appropriate). *Self-correction: The A2A app might expect to be the root. We can mount the UI routes onto the FastAPI app and mount the A2A app separately, or keep them distinct.*

3.  **Step 3**: Port Web UI Logic
    -   Files to modify: `main.py`
    -   Changes needed:
        -   Define Pydantic models for the chat request (matching `views.py` JSON parsing).
        -   Create `GET /agent/interact/` endpoint: Renders `adk_agent/interact.html`.
        -   Create `POST /agent/interact/` endpoint:
            -   Accepts JSON payload.
            -   Uses `_service_manager` to get session and runner.
            -   Executes agent asynchronously.
            -   Returns JSON response.

4.  **Step 4**: Update Template
    -   Files to modify: `adk_bug_ticket_agent/templates/adk_agent/interact.html`
    -   Changes needed:
        -   Replace `{% url "interact_with_agent" %}` with `{{ url_for('interact_with_agent') }}`.
        -   Ensure any other Django-specific tags are converted to Jinja2.

5.  **Step 5**: Update Dockerfile
    -   Files to modify: `Dockerfile`
    -   Changes needed:
        -   Update base image or steps to install new dependencies.
        -   Remove `collectstatic` step.
        -   Change `ENTRYPOINT` to run `uvicorn main:app --host 0.0.0.0 --port 8080`.

6.  **Step 6**: Cleanup
    -   Files to modify: Delete `manage.py`, `web/` directory, `gunicorn.conf.py`, `adk_bug_ticket_agent/urls.py`, `adk_bug_ticket_agent/views.py` (after porting).
    -   Changes needed: Remove these files as they are no longer needed.

### Testing Strategy
-   **Local Run**: Run `uvicorn main:app --reload` and access `http://localhost:8000/agent/interact/`.
-   **Chat Functionality**: Verify that the chat interface loads and messages can be sent/received.
-   **A2A Check**: Verify that A2A endpoints (if mounted) are accessible.

## 🎯 Success Criteria
-   Application starts successfully with `uvicorn`.
-   Web UI at `/agent/interact/` is fully functional (chat works).
-   Docker image builds and runs.
-   No Django dependencies remain in the environment.
