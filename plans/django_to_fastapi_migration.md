# Feature Implementation Plan: Migrate Django to FastAPI

## 📋 Todo Checklist
- [ ] **Phase 1: Setup & Configuration**
    - [ ] Install FastAPI, Uvicorn, and standard dependencies.
    - [ ] Set up `pydantic-settings` for environment variable management.
- [ ] **Phase 2: Logic Migration**
    - [ ] Migrate `ServiceManager` from `adk_bug_ticket_agent/agent.py` to FastAPI dependency injection pattern.
    - [ ] Define Pydantic models for request/response payloads.
- [ ] **Phase 3: Endpoint Implementation**
    - [ ] Create FastAPI router for agent interaction (`/agent/interact`).
    - [ ] Implement the `POST` endpoint logic using `google-adk`'s `Runner`.
    - [ ] Implement the `GET` endpoint for the UI.
- [ ] **Phase 4: UI & Static Files**
    - [ ] Configure `Jinja2Templates` to serve `interact.html`.
    - [ ] Set up static file serving (if applicable, though current setup uses `whitenoise`).
- [ ] **Phase 5: Application Entrypoint**
    - [ ] Create `main.py` to assemble the app.
    - [ ] Update `Dockerfile` or run scripts to use `uvicorn`.
- [ ] **Phase 6: Verification**
    - [ ] Add unit tests for the new endpoints.
    - [ ] Verify full agent interaction flow.

## 🔍 Analysis & Investigation

### Codebase Structure
- **Current Framework**: Django 5.0.6
- **Main Logic**: Located in `adk_bug_ticket_agent/`.
- **Agent Framework**: `google-adk` (v1.17.0).
- **Database**: PostgreSQL (via `psycopg2-binary`).
- **Tools**: MCP Toolbox (via `toolbox-core`) and local function tools.
- **Frontend**: Simple HTML template served by Django.

### Current Architecture
- **Monolithic**: Django serves both the API and the HTML UI.
- **Async**: The main view `interact_with_agent` is asynchronous (`async def`), leveraging `runner.run_async`.
- **State Management**:
    - `DatabaseSessionService` for session persistence.
    - `InMemoryMemoryService` for conversation memory (context).
- **Configuration**: Environment variables loaded via `python-dotenv` and `os.environ`.

### Dependencies & Integration Points
- **Input**: JSON payload with `appName`, `userId`, `sessionId`, `newMessage`.
- **Output**: JSON payload with `content`, `role`, `timestamp`.
- **External Services**:
    - PostgreSQL Database (Sessions).
    - MCP Toolbox Server (Tools).
    - Google Gemini API (Model).

### Considerations & Challenges
- **Async Compatibility**: FastAPI is natively async, which aligns well with `google-adk`'s async runner.
- **Middleware**: Django's middleware (Security, CSRF, etc.) will need FastAPI equivalents (e.g., `CORSMiddleware`). CSRF is currently exempt (`@csrf_exempt`) so it might not be strictly needed for the API, but good practice for the UI.
- **Static Files**: Django uses `whitenoise`. FastAPI can serve static files directly or via a reverse proxy in production.
- **Tool Loading**: The lazy loading mechanism in `agent.py` should be preserved or improved using FastAPI's startup events or dependencies to avoid global state issues.

## 📝 Implementation Plan

### Prerequisites
- Python 3.10+ environment.
- Existing `.env` file.

### Step-by-Step Implementation

#### 1. Install Dependencies
- **Files to modify**: `pyproject.toml`
- **Changes needed**:
    - Add `fastapi`, `uvicorn`, `jinja2`, `pydantic-settings`.
    - Remove `django`, `whitenoise`, `gunicorn` (optional, can be kept for transition).

#### 2. Create Configuration Module
- **Files to create**: `fastapi_app/config.py`
- **Changes needed**:
    - Create a `Settings` class using `pydantic_settings.BaseSettings`.
    - Move all `os.environ` lookups (DB_URL, API keys, Agent Config) here.

#### 3. Define Pydantic Models
- **Files to create**: `fastapi_app/schemas.py`
- **Changes needed**:
    - Define `MessagePart`, `MessageContent`, `NewMessage`.
    - Define `InteractRequest` (matching current JSON body: `appName`, `userId`, `sessionId`, `newMessage`).
    - Define `InteractResponse` (matching current response).

#### 4. Refactor Agent Logic & Dependencies
- **Files to create**: `fastapi_app/dependencies.py`
- **Changes needed**:
    - Adapt `ServiceManager` logic from `adk_bug_ticket_agent/agent.py`.
    - Create dependency functions (`get_agent`, `get_session_service`, `get_memory_service`) that yield initialized instances.
    - Use `@lru_cache` or module-level singletons to maintain state where appropriate (similar to current `_service_manager`).

#### 5. Implement API Router
- **Files to create**: `fastapi_app/routers/agent.py`
- **Changes needed**:
    - Create `APIRouter`.
    - Implement `POST /interact`:
        - Use `InteractRequest` model.
        - Inject dependencies (`root_agent`, `session_service`, `memory_service`).
        - Replicate the logic from `interact_with_agent`:
            - Get/Create session.
            - Initialize `Runner`.
            - `await runner.run_async(...)`.
            - Return `InteractResponse`.
    - Implement `GET /interact` (or root `/`):
        - Return `HTMLResponse` using `Jinja2Templates`.

#### 6. Setup Main Application
- **Files to create**: `fastapi_app/main.py`
- **Changes needed**:
    - Initialize `FastAPI` app.
    - Add `CORSMiddleware`.
    - Include `agent.router`.
    - Mount `StaticFiles` (if needed for CSS/JS in templates).
    - Initialize `Jinja2Templates` pointing to `adk_bug_ticket_agent/templates`.

#### 7. Migration of Templates
- **Files to move/modify**: `adk_bug_ticket_agent/templates/adk_agent/interact.html` -> `fastapi_app/templates/interact.html`
- **Changes needed**:
    - Ensure the template is compatible (standard Django templates are mostly Jinja2 compatible, check for specific tags like `{% csrf_token %}` which might need removal/replacement).

#### 8. Update Run Configuration
- **Files to modify**: `Dockerfile` (or create `Dockerfile.fastapi`)
- **Changes needed**:
    - Change `CMD` to run `uvicorn fastapi_app.main:app --host 0.0.0.0 --port 8080`.

### Testing Strategy
1.  **Unit Tests**:
    - Use `fastapi.testclient.TestClient`.
    - Mock `google-adk` components (`Runner`, `Agent`) to test the API layer without making real LLM calls.
2.  **Integration Tests**:
    - Run the full app locally.
    - Connect to the local Postgres DB and MCP server.
    - Send a sample request to `/interact` and verify the response.

## 🎯 Success Criteria
- [ ] The FastAPI app starts successfully with `uvicorn`.
- [ ] `GET /agent/interact` serves the HTML UI.
- [ ] `POST /agent/interact` successfully processes a user message via the ADK Agent and returns a response.
- [ ] Session persistence works (conversations are saved to DB).
- [ ] Tools (Database & Search) function correctly within the agent interaction.
