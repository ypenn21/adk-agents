import os
import pytest

# Ensure DJANGO environment flag is set so agent.py does not attempt to build A2AStarletteApplication
os.environ.setdefault("DJANGO", "true")

from google.adk.sessions import DatabaseSessionService
from adk_bug_ticket_agent.agent import normalize_db_url, ServiceManager, DEFAULT_DB_URL


def test_normalize_db_url():
    """Verifies that normalize_db_url correctly upgrades PostgreSQL schemes to postgresql+asyncpg://."""
    # Standard postgresql:// scheme
    raw_url = "postgresql://postgres:admin@localhost:5432/tickets-db"
    assert normalize_db_url(raw_url) == "postgresql+asyncpg://postgres:admin@localhost:5432/tickets-db"

    # Short postgres:// scheme
    raw_url_short = "postgres://postgres:admin@localhost:5432/tickets-db"
    assert normalize_db_url(raw_url_short) == "postgresql+asyncpg://postgres:admin@localhost:5432/tickets-db"

    # Already normalized postgresql+asyncpg:// scheme
    async_url = "postgresql+asyncpg://postgres:admin@localhost:5432/tickets-db"
    assert normalize_db_url(async_url) == "postgresql+asyncpg://postgres:admin@localhost:5432/tickets-db"

    # Non-PostgreSQL scheme (e.g., sqlite+aiosqlite://)
    sqlite_url = "sqlite+aiosqlite:///app.db"
    assert normalize_db_url(sqlite_url) == "sqlite+aiosqlite:///app.db"


def test_database_session_service_initialization():
    """Verifies that DatabaseSessionService initializes an AsyncEngine using the asyncpg driver without error."""
    async_url = "postgresql+asyncpg://postgres:admin@localhost:5432/tickets-db"
    service = DatabaseSessionService(db_url=async_url)
    
    assert service.db_engine is not None
    assert service.db_engine.dialect.name == "postgresql"
    assert service.db_engine.dialect.driver == "asyncpg"


def test_database_session_service_with_normalized_url():
    """Verifies that normalized postgresql:// URL successfully creates an async engine with DatabaseSessionService."""
    raw_url = "postgresql://postgres:admin@localhost:5432/tickets-db"
    normalized_url = normalize_db_url(raw_url)
    service = DatabaseSessionService(db_url=normalized_url)
    
    assert service.db_engine is not None
    assert service.db_engine.dialect.name == "postgresql"
    assert service.db_engine.dialect.driver == "asyncpg"


def test_service_manager_session_service_lazy_load():
    """Verifies that ServiceManager lazily loads DatabaseSessionService and caches the instance."""
    sm = ServiceManager()
    assert sm._session_service is None
    
    session_service = sm.session_service
    assert session_service is not None
    assert isinstance(session_service, DatabaseSessionService)
    assert sm._session_service is session_service
    
    # Second access returns the cached singleton
    assert sm.session_service is session_service


def test_cross_event_loop_session_service(tmp_path):
    """Verifies that DatabaseSessionService with NullPool can be used across multiple event loops (as in Django WSGI)."""
    from asgiref.sync import async_to_sync
    from sqlalchemy.pool import NullPool

    db_path = tmp_path / "cross_loop_test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    service = DatabaseSessionService(db_url=db_url, poolclass=NullPool)

    @async_to_sync
    async def request_one():
        return await service.create_session(app_name="test_app", user_id="user_1", session_id="sess_1")

    @async_to_sync
    async def request_two():
        return await service.get_session(app_name="test_app", user_id="user_1", session_id="sess_1")

    # Request 1 runs in Loop 1
    session_created = request_one()
    assert session_created.id == "sess_1"

    # Request 2 runs in Loop 2 (Loop 1 is closed)
    session_fetched = request_two()
    assert session_fetched is not None
    assert session_fetched.id == "sess_1"

