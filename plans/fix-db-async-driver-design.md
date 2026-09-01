# Feature Implementation Plan: fix-db-async-driver

## 📋 Todo Checklist
- [x] Add `asyncpg` dependency to `pyproject.toml` and synchronize environment via `uv sync` (`pyproject.toml`, `uv.lock`)
- [x] Update `adk_bug_ticket_agent/agent.py` default `DB_URL` and add URL normalization to auto-upgrade `postgresql://` to `postgresql+asyncpg://` (`adk_bug_ticket_agent/agent.py`)
- [x] Update sample configuration in `.env.example` and deployment documentation in `README.md` (`.env.example`, `README.md`)
- [x] Create automated unit tests for `DatabaseSessionService` async engine initialization and URL normalization (`tests/test_database_session.py`)
- [x] Execute verification test suite using `uv run pytest` to ensure complete compatibility (`tests/test_database_session.py`)

---

## 🔍 Analysis & Investigation

### Codebase Structure
| File / Path | Responsibility | Current Status |
| :--- | :--- | :--- |
| `adk_bug_ticket_agent/agent.py` | Defines agent lifecycle, `ServiceManager`, and `DatabaseSessionService` initialization. | Defines `DB_URL = os.environ.get("DB_URL", "postgresql://postgres:admin@localhost:5432/tickets-db")`. |
| `pyproject.toml` | Python project configuration and dependency manifest. | Includes `google-adk[db]>=1.27.4`, `psycopg2-binary`, but lacks `asyncpg`. |
| `.env.example` | Sample environment variable file for local development. | Lacks explicit `DB_URL` specification for async PostgreSQL connection. |
| `README.md` | Deployment and local setup documentation. | References `DB_URL="postgresql://postgres:pword@internal-ip-address:5432/tickets-db"` in Cloud Run setup. |
| `tests/test_database_session.py` | Automated tests for database session initialization. | Does not exist; needs to be created. |

### Current Architecture
1. **Google ADK Session Layer**: `google.adk.sessions.DatabaseSessionService` is instantiated inside `ServiceManager._init_session_service()`.
2. **SQLAlchemy Async Engine**: Internally, ADK's `DatabaseSessionService` invokes SQLAlchemy's `create_async_engine(db_url, **engine_kwargs)`.
3. **Driver Mismatch**: When SQLAlchemy's async engine parses a URL with the `postgresql://` scheme without an explicit async DBAPI driver, it defaults to the standard synchronous PostgreSQL driver (`psycopg2`).
4. **Exception Raised**:
   ```text
   sqlalchemy.exc.InvalidRequestError: The asyncio extension requires an async driver to be used. The loaded 'psycopg2' is not async.
   ...
   ValueError: Failed to create database engine for URL 'postgresql://postgres:admin@localhost:5432/tickets-db'
   ```

### Dependencies & Integration Points
- **`asyncpg` (>=0.29.0)**: High-performance asynchronous PostgreSQL database driver for Python / asyncio, required by SQLAlchemy async engine (`postgresql+asyncpg://`).
- **`SQLAlchemy` (2.0+)**: Included via `google-adk[db]`; requires async drivers for `create_async_engine`.
- **`google-adk` (`v1.27.4+`)**: Provides `DatabaseSessionService` for session state persistence.

### Considerations & Challenges
- **Backwards Compatibility**: Users or Cloud Run deployments may supply `DB_URL` using the standard `postgresql://` format in their environment variables. If `agent.py` naively consumes `os.environ["DB_URL"]` without normalizing the dialect prefix, runtime crashes will occur in production.
- **Graceful URL Normalization**: A helper function `normalize_db_url(url: str) -> str` should automatically convert `postgresql://` to `postgresql+asyncpg://` while leaving already specified async dialects (like `postgresql+asyncpg://` or `sqlite+aiosqlite://`) intact.
- **Docker / Production Build**: The Dockerfile builds dependencies from `pyproject.toml` using `uv sync --frozen`. Updating `pyproject.toml` and locking with `uv lock` ensures container builds on Cloud Run succeed seamlessly.

---

## 📐 Technical Specification & Design

### Component Architecture
```
+-------------------------------------------------------------------------------+
|                                Django / App Layer                             |
|  views.interact_with_agent -> _service_manager.session_service               |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                     adk_bug_ticket_agent/agent.py                             |
|  1. Read DB_URL from environment                                              |
|  2. normalize_db_url(raw_url) -> "postgresql+asyncpg://..."                   |
|  3. Instantiate DatabaseSessionService(db_url=normalized_url)                 |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                      google.adk.sessions.DatabaseSessionService               |
|  create_async_engine("postgresql+asyncpg://...", pool_pre_ping=True)          |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                   asyncpg (Async DBAPI Driver) -> PostgreSQL DB               |
+-------------------------------------------------------------------------------+
```

### Mermaid Diagram
```mermaid
sequenceDiagram
    autonumber
    actor User as Client / Web UI
    participant Views as views.py (interact_with_agent)
    participant SM as ServiceManager
    participant AgentMod as agent.py (normalize_db_url)
    participant ADK as DatabaseSessionService
    participant SA as SQLAlchemy (create_async_engine)
    participant Driver as asyncpg DBAPI

    User->>Views: POST /agent/interact/
    Views->>SM: Access _service_manager.session_service
    SM->>AgentMod: normalize_db_url(DB_URL)
    AgentMod-->>SM: "postgresql+asyncpg://postgres:admin@localhost:5432/tickets-db"
    SM->>ADK: DatabaseSessionService(db_url=normalized_url)
    ADK->>SA: create_async_engine("postgresql+asyncpg://...")
    SA->>Driver: Load asyncpg dialect
    Driver-->>SA: Async driver registered
    SA-->>ADK: AsyncEngine initialized
    ADK-->>SM: DatabaseSessionService instance
    SM-->>Views: session_service ready
```

### Schemas & Models
No database schema migrations or table modifications are required. The session state tables managed by ADK (`adk_sessions`, `adk_app_states`, `adk_user_states`, `adk_events`) will automatically initialize when sessions are created by `DatabaseSessionService`.

### API & Code Signatures

#### 1. URL Normalization Helper (`adk_bug_ticket_agent/agent.py`)
```python
def normalize_db_url(url: str) -> str:
    """
    Ensures database URLs for PostgreSQL use the asyncpg dialect required by SQLAlchemy async engine.
    
    Args:
        url: Raw database connection URL.
        
    Returns:
        Normalized database connection URL starting with postgresql+asyncpg:// if PostgreSQL.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url
```

#### 2. Service Manager Session Initialization (`adk_bug_ticket_agent/agent.py`)
```python
DEFAULT_DB_URL = "postgresql+asyncpg://postgres:admin@localhost:5432/tickets-db"
DB_URL = normalize_db_url(os.environ.get("DB_URL", DEFAULT_DB_URL))

class ServiceManager:
    ...
    def _init_session_service(self):
        """Initializes the database session service with normalized async DB URL."""
        print("Initializing DatabaseSessionService...")
        service = DatabaseSessionService(db_url=DB_URL)
        print(f"ADK Database URL: {DB_URL}")
        return service
```

---

## 📝 Step-by-Step Implementation Steps

### Step 1: Add `asyncpg` dependency to `pyproject.toml`
- **Files to modify**: `pyproject.toml`
- **Changes needed**:
  Add `"asyncpg>=0.29.0"` to the `dependencies` list in `pyproject.toml`.
  Execute `uv lock && uv sync` to regenerate `uv.lock` and install `asyncpg` in `.venv`.
- **Implementation Pattern**:
  ```toml
  dependencies = [
      "google-adk[db]>=1.27.4",
      "a2a-sdk>=0.3.22",
      "python-dotenv==1.1.0",
      "toolbox-core==0.5.2",
      "gunicorn",
      "whitenoise[brotli]",
      "django>=5.0,<5.3",
      "google-generativeai>=0.8.5",
      "psycopg2-binary",
      "asyncpg>=0.29.0",
      "litellm>=1.81.4",
  ]
  ```
- **Status**: `- [x]`

### Step 2: Update `adk_bug_ticket_agent/agent.py`
- **Files to modify**: `adk_bug_ticket_agent/agent.py`
- **Changes needed**:
  1. Define `normalize_db_url(url: str) -> str` function to automatically upgrade `postgresql://` and `postgres://` to `postgresql+asyncpg://`.
  2. Set default connection string to `"postgresql+asyncpg://postgres:admin@localhost:5432/tickets-db"`.
  3. Ensure `DB_URL` is parsed through `normalize_db_url()`.
- **Status**: `- [x]`

### Step 3: Update `.env.example` and `README.md`
- **Files to modify**: `.env.example`, `README.md`
- **Changes needed**:
  1. In `.env.example`, document `export DB_URL="postgresql+asyncpg://postgres:admin@localhost:5432/tickets-db"`.
  2. In `README.md`, update sections 14 (`Cloud Run deployment`) from `DB_URL="postgresql://..."` to `DB_URL="postgresql+asyncpg://..."`.
- **Status**: `- [x]`

### Step 4: Add Unit Tests for Database Session Initialization
- **Files to create**: `tests/test_database_session.py`
- **Changes needed**:
  Create test cases covering:
  1. `test_normalize_db_url`: Verifies standard `postgresql://`, `postgres://`, `postgresql+asyncpg://`, and `sqlite+aiosqlite://` handling.
  2. `test_database_session_service_initialization`: Verifies that `DatabaseSessionService(db_url="postgresql+asyncpg://...")` instantiates its `AsyncEngine` without raising `ValueError` or `InvalidRequestError`.
  3. `test_service_manager_session_service_lazy_load`: Verifies that `_service_manager.session_service` lazy loads properly.
- **Status**: `- [x]`

---

## 🧪 Verification & Testing Strategy

### Unit / Integration Tests
- Execute pytest targeting the newly added test suite:
  ```bash
  uv run pytest tests/test_database_session.py -v
  ```

### Shell Verification Commands
1. **Dependency Verification**:
   ```bash
   uv run python -c "import asyncpg; print('asyncpg version:', asyncpg.__version__)"
   ```
2. **Engine Creation Smoke Test**:
   ```bash
   uv run python -c "from google.adk.sessions import DatabaseSessionService; s = DatabaseSessionService('postgresql+asyncpg://postgres:admin@localhost:5432/tickets-db'); print('DB Engine dialect:', s.db_engine.dialect.name, 'driver:', s.db_engine.dialect.driver)"
   ```
   **Expected Output**:
   ```text
   DB Engine dialect: postgresql driver: asyncpg
   ```
3. **URL Normalization Verification**:
   ```bash
   uv run python -c "from adk_bug_ticket_agent.agent import normalize_db_url; assert normalize_db_url('postgresql://user:pass@localhost:5432/db') == 'postgresql+asyncpg://user:pass@localhost:5432/db'"
   ```

---

## 🎯 Success Criteria
1. `asyncpg` is declared in `pyproject.toml` and installed in the virtual environment.
2. `adk_bug_ticket_agent/agent.py` defaults to `postgresql+asyncpg://` and transparently normalizes any provided `postgresql://` URLs to `postgresql+asyncpg://`.
3. `DatabaseSessionService(db_url=DB_URL)` initializes cleanly without `ValueError` or `InvalidRequestError`.
4. Automated unit tests in `tests/test_database_session.py` pass with 100% success rate.
