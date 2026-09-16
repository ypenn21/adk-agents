import os
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Ensure DJANGO environment flags are set before importing Django modules
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.settings")
os.environ.setdefault("DJANGO", "true")

import django
django.setup()

from django.test import AsyncClient
from google.genai import types as genai_types


@pytest.mark.asyncio
async def test_get_root_url_renders_ui():
    """Verifies that GET / renders the full chat UI template."""
    client = AsyncClient()
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response["Content-Type"]
    content = response.content.decode("utf-8")
    assert "<title>IT Bug Assistant - AI Support</title>" in content
    assert "id=\"chat-input\"" in content
    assert "id=\"send-btn\"" in content
    assert "id=\"messages-list\"" in content
    assert "id=\"btn-theme-toggle\"" in content
    assert "jquery-3.7.1.min.js" in content
    assert "marked.min.js" in content


@pytest.mark.asyncio
async def test_get_all_chat_routes_render_ui():
    """Verifies that all aliased chat routes serve the UI."""
    client = AsyncClient()
    for route in ["/", "/agent/", "/agent/interact/", "/agent/chat/"]:
        response = await client.get(route)
        assert response.status_code == 200
        assert "text/html" in response["Content-Type"]


@pytest.mark.asyncio
async def test_post_empty_body_returns_400():
    """Verifies that an empty JSON payload returns HTTP 400."""
    client = AsyncClient()
    response = await client.post(
        "/agent/interact/",
        data=json.dumps({}),
        content_type="application/json"
    )
    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "Invalid payload structure."


@pytest.mark.asyncio
async def test_post_empty_query_text_returns_400():
    """Verifies that empty message text returns HTTP 400."""
    client = AsyncClient()
    payload = {
        "appName": "adk_agent",
        "userId": "user_test_123",
        "sessionId": "session_test_123",
        "newMessage": {"parts": [{"text": ""}]}
    }
    response = await client.post(
        "/agent/interact/",
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "No message provided"


@pytest.mark.asyncio
async def test_post_invalid_json_returns_400():
    """Verifies that malformed JSON returns HTTP 400."""
    client = AsyncClient()
    response = await client.post(
        "/agent/interact/",
        data="not-a-json-string",
        content_type="application/json"
    )
    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "Invalid JSON in request"


@pytest.mark.asyncio
async def test_unsupported_methods_return_405():
    """Verifies that DELETE and PUT methods return HTTP 405."""
    client = AsyncClient()
    for method in [client.delete, client.put]:
        response = await method("/agent/interact/")
        assert response.status_code == 405
        assert response.json()["error"] == "Unsupported method"


@pytest.mark.asyncio
async def test_post_valid_chat_mocked_runner():
    """Verifies that a valid chat POST returns the expected response contract."""
    mock_event = MagicMock()
    mock_event.is_final_response.return_value = True
    mock_part = MagicMock()
    mock_part.text = "Hello! I am your IT Bug Assistant."
    mock_event.content.parts = [mock_part]

    async def mock_run_async(*args, **kwargs):
        yield mock_event

    with patch("adk_bug_ticket_agent.views.Runner") as mock_runner_cls, \
         patch("adk_bug_ticket_agent.views._service_manager") as mock_sm:
        
        mock_session_service = MagicMock()
        mock_session_service.get_session = AsyncMock(return_value=None)
        mock_session_service.create_session = AsyncMock(return_value=MagicMock())
        mock_sm.session_service = mock_session_service
        mock_sm.memory_service = MagicMock()
        mock_sm.root_agent = MagicMock()

        mock_runner_instance = MagicMock()
        mock_runner_instance.run_async = mock_run_async
        mock_runner_cls.return_value = mock_runner_instance

        client = AsyncClient()
        payload = {
            "appName": "adk_agent",
            "userId": "user_test_999",
            "sessionId": "session_test_999",
            "newMessage": {"parts": [{"text": "Hello assistant"}]}
        }
        response = await client.post(
            "/agent/interact/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert data["content"]["role"] == "model"
        assert data["content"]["parts"][0]["text"] == "Hello! I am your IT Bug Assistant."
        assert "timestamp" in data
