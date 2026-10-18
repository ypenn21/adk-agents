import asyncio
import inspect
import json
import os
from pathlib import Path
import pickle
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import django
from django.test import RequestFactory
import pytest
import yaml

# Ensure DJANGO environment flag and settings are set before importing Django-dependent modules
os.environ.setdefault("DJANGO", "true")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.settings")

if not django.conf.settings.configured:
    django.setup()

from google.adk.tools.function_tool import FunctionTool

from adk_bug_ticket_agent.agent import ServiceManager
from adk_bug_ticket_agent.tools.tools import LazyToolboxTool
from adk_bug_ticket_agent.views import interact_with_agent


def test_tools_yaml_search_tickets_uses_local_postgres_fts():
    """Verifies that search-tickets in tools.yaml uses local PostgreSQL FTS instead of vector embeddings."""
    yaml_path = (
        Path(__file__).resolve().parent.parent
        / "mcp-servers"
        / "mcp-toolbox"
        / "tools.yaml"
    )
    assert yaml_path.exists(), f"tools.yaml not found at {yaml_path}"

    with open(yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert "tools" in config, "tools section missing in tools.yaml"
    assert "search-tickets" in config["tools"], "search-tickets missing from tools.yaml"

    tool_def = config["tools"]["search-tickets"]
    statement = tool_def.get("statement", "")

    # Active SQL statement must use full-text search functions compatible with local PostgreSQL
    assert "to_tsvector" in statement, (
        "search-tickets statement should use to_tsvector for full-text search"
    )
    assert "websearch_to_tsquery" in statement, (
        "search-tickets statement should use websearch_to_tsquery"
    )
    # Active SQL statement must NOT reference the embedding column which does not exist in local PostgreSQL
    assert "embedding" not in statement, (
        "search-tickets active SQL statement must not query non-existent 'embedding' column"
    )


def test_lazy_toolbox_tool_signature_and_pickle_preservation():
    """Verifies that LazyToolboxTool preserves inspect.signature, FunctionTool spec, and metadata across pickling."""

    class MockSyncTool:
        """Mock synchronous tool mimicking ToolboxSyncTool."""

        def __init__(self):
            self.__name__ = "get_tickets_by_status"
            self.__doc__ = "Retrieve bug tickets filtered by status and priority."
            self.__annotations__ = {"status": str, "priority": str, "return": str}
            self.__signature__ = inspect.Signature(
                parameters=[
                    inspect.Parameter(
                        "status",
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=str,
                    ),
                    inspect.Parameter(
                        "priority",
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        default="P3 - Low",
                        annotation=str,
                    ),
                ],
                return_annotation=str,
            )

        def __call__(self, status: str, priority: str = "P3 - Low") -> str:
            return f"tickets: {status}, {priority}"

    mock_tool = MockSyncTool()
    lazy_tool = LazyToolboxTool(
        name="get_tickets_by_status",
        toolset_name="tickets_toolset",
        original_tool=mock_tool,
    )

    # 1. Verify inspect.signature resolves parameters ['status', 'priority']
    sig = inspect.signature(lazy_tool)
    assert list(sig.parameters.keys()) == ["status", "priority"]
    assert sig.parameters["priority"].default == "P3 - Low"

    # 2. Verify FunctionTool(lazy_tool) resolves parameter declarations without error
    ft = FunctionTool(lazy_tool)
    assert list(ft._spec.signature.parameters.keys()) == ["status", "priority"]

    # 3. Pickle and unpickle lazy_tool
    pickled = pickle.dumps(lazy_tool)
    unpickled: LazyToolboxTool = pickle.loads(pickled)

    # Verify unpickled attributes are preserved without requiring a network call to load_toolset_cached
    with patch(
        "adk_bug_ticket_agent.tools.tools.load_toolset_cached"
    ) as mock_load:
        unpickled_sig = unpickled.__signature__
        assert list(unpickled_sig.parameters.keys()) == ["status", "priority"]
        assert unpickled_sig.parameters["priority"].default == "P3 - Low"

        assert (
            unpickled.__doc__
            == "Retrieve bug tickets filtered by status and priority."
        )
        assert unpickled.__annotations__ == {
            "status": str,
            "priority": str,
            "return": str,
        }

        # FunctionTool wrapping unpickled tool should also succeed without network call
        unpickled_ft = FunctionTool(unpickled)
        assert list(unpickled_ft._spec.signature.parameters.keys()) == [
            "status",
            "priority",
        ]

        mock_load.assert_not_called()


def test_lazy_toolbox_tool_timeout_handling():
    """Verifies that LazyToolboxTool catches FuturesTimeoutError and returns structured error dict within timeout."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    try:

        async def slow_async_tool(*args, **kwargs):
            await asyncio.sleep(5.0)
            return "completed"

        mock_tool = MagicMock()
        mock_tool.__name__ = "mock_slow_tool"
        mock_tool.__doc__ = "A slow tool for testing timeouts."
        mock_tool._ToolboxSyncTool__async_tool = slow_async_tool
        mock_tool._ToolboxSyncTool__loop = loop

        lazy_tool = LazyToolboxTool(
            name="mock_slow_tool",
            toolset_name="test_toolset",
            original_tool=mock_tool,
            timeout=0.1,
        )

        start_time = time.time()
        result = lazy_tool(query="test_timeout")
        elapsed = time.time() - start_time

        # Must return in under 1 second without blocking indefinitely
        assert elapsed < 1.0
        assert isinstance(result, dict)
        assert "error" in result
        assert "timed out" in result["error"].lower()
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=1.0)


@pytest.mark.asyncio
async def test_interact_with_agent_drains_all_events_without_early_break(
    monkeypatch,
):
    """Verifies that interact_with_agent drains all events in runner.run_async to completion without early break."""
    mock_session_service = AsyncMock()
    mock_session = MagicMock()
    mock_session.id = "session_test_123"
    mock_session_service.get_session.return_value = mock_session

    mock_sm = MagicMock()
    mock_sm.session_service = mock_session_service
    mock_sm.root_agent = MagicMock()
    mock_sm.memory_service = MagicMock()

    generator_completed_naturally = False

    async def mock_event_stream(*args, **kwargs):
        nonlocal generator_completed_naturally
        # Emit final response event
        final_event = MagicMock()
        final_event.is_final_response.return_value = True
        part = MagicMock()
        part.text = "All bug tickets have been successfully retrieved."
        final_event.content.parts = [part]
        yield final_event

        # Code after final response (e.g. done sentinel, cleanup)
        generator_completed_naturally = True

    mock_runner = MagicMock()
    mock_runner.run_async.side_effect = mock_event_stream

    monkeypatch.setattr("adk_bug_ticket_agent.views._service_manager", mock_sm)
    monkeypatch.setattr(
        "adk_bug_ticket_agent.views.Runner",
        MagicMock(return_value=mock_runner),
    )

    rf = RequestFactory()
    payload = {
        "appName": "it_bug_assistant_agent",
        "userId": "user_test",
        "sessionId": "session_test_123",
        "newMessage": {"parts": [{"text": "Show tickets"}]},
    }
    request = rf.post(
        "/agent/interact/",
        data=json.dumps(payload),
        content_type="application/json",
    )

    response = await interact_with_agent(request)

    assert response.status_code == 200
    data = json.loads(response.content.decode("utf-8"))
    assert (
        data["content"]["parts"][0]["text"]
        == "All bug tickets have been successfully retrieved."
    )
    # Crucial assertion: the event generator must not have been broken out of early
    assert generator_completed_naturally is True


@pytest.mark.asyncio
async def test_interact_with_agent_timeout_returns_504(monkeypatch):
    """Verifies that interact_with_agent enforces execution timeout, returns HTTP 504, and closes generator."""
    mock_session_service = AsyncMock()
    mock_session = MagicMock()
    mock_session.id = "session_test_timeout"
    mock_session_service.get_session.return_value = mock_session

    mock_sm = MagicMock()
    mock_sm.session_service = mock_session_service
    mock_sm.root_agent = MagicMock()
    mock_sm.memory_service = MagicMock()

    generator_closed = False

    async def slow_event_stream(*args, **kwargs):
        nonlocal generator_closed
        try:
            await asyncio.sleep(2.0)
            event = MagicMock()
            event.is_final_response.return_value = True
            yield event
        except (asyncio.CancelledError, GeneratorExit):
            generator_closed = True
            raise
        finally:
            generator_closed = True

    mock_runner = MagicMock()
    mock_runner.run_async.side_effect = slow_event_stream

    # Patch AGENT_INTERACTION_TIMEOUT to 0.05 seconds for fast test execution
    monkeypatch.setenv("AGENT_INTERACTION_TIMEOUT", "0.05")
    monkeypatch.setattr(
        "adk_bug_ticket_agent.views.AGENT_INTERACTION_TIMEOUT",
        0.05,
        raising=False,
    )
    monkeypatch.setattr("adk_bug_ticket_agent.views._service_manager", mock_sm)
    monkeypatch.setattr(
        "adk_bug_ticket_agent.views.Runner",
        MagicMock(return_value=mock_runner),
    )

    rf = RequestFactory()
    payload = {
        "appName": "it_bug_assistant_agent",
        "userId": "user_test",
        "sessionId": "session_test_timeout",
        "newMessage": {"parts": [{"text": "Long running query"}]},
    }
    request = rf.post(
        "/agent/interact/",
        data=json.dumps(payload),
        content_type="application/json",
    )

    response = await interact_with_agent(request)

    assert response.status_code == 504
    data = json.loads(response.content.decode("utf-8"))
    assert "error" in data
    assert "timed out" in data["error"].lower()
    # Generator should be closed cleanly by aclosing
    assert generator_closed is True


def test_service_manager_default_model_fallback(monkeypatch):
    """Verifies that ServiceManager defaults to gemini-3.8-flash when MODEL_NAME is unset."""
    monkeypatch.delenv("MODEL_NAME", raising=False)
    # Prevent network calls during agent initialization
    monkeypatch.setattr(
        "adk_bug_ticket_agent.agent.get_toolbox_tools", lambda: []
    )

    sm = ServiceManager()
    agent = sm._init_agent()
    assert agent.model == "gemini-3.8-flash"

    # Also verify custom MODEL_NAME override is respected
    monkeypatch.setenv("MODEL_NAME", "gemini-3.7-flash")
    agent_custom = sm._init_agent()
    assert agent_custom.model == "gemini-3.7-flash"
