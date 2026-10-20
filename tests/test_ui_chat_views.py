import json
import os
from unittest.mock import AsyncMock, MagicMock

import django
from django.test import AsyncClient, RequestFactory
import pytest

# Ensure DJANGO environment flag and settings are set before importing Django-dependent modules
os.environ.setdefault("DJANGO", "true")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.settings")

if not django.conf.settings.configured:
    django.setup()

from adk_bug_ticket_agent.views import interact_with_agent


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["/", "/agent/", "/agent/interact/", "/agent/chat/"])
async def test_ui_get_endpoints_render_chat_template(endpoint):
    """Verifies that GET requests across all agent and root routes return 200 OK and render interact.html."""
    client = AsyncClient()
    response = await client.get(endpoint)

    assert response.status_code == 200
    assert "text/html" in response["Content-Type"]
    content = response.content.decode("utf-8")
    assert "<!DOCTYPE html>" in content
    assert "IT Bug Assistant" in content


@pytest.mark.asyncio
async def test_ui_template_contains_all_required_elements():
    """Verifies that the rendered UI HTML contains all required elements per design specification."""
    client = AsyncClient()
    response = await client.get("/agent/interact/")
    assert response.status_code == 200
    content = response.content.decode("utf-8")

    # Anti-FOUC and themes
    assert 'data-theme="light"' in content
    assert "it_assistant_theme" in content

    # CDN dependencies
    assert "jquery-3.7.1.min.js" in content
    assert "marked.min.js" in content
    assert "fonts.googleapis.com" in content

    # UI Controls and elements
    assert 'id="chat-messages"' in content
    assert 'id="welcome-hero"' in content
    assert 'id="message-input"' in content
    assert 'id="send-button"' in content
    assert 'id="theme-toggle"' in content
    assert 'id="new-chat-button"' in content
    assert 'id="clear-chat-button"' in content

    # Typing indicator & suggestions
    assert "suggestion-chip" in content
    assert "typing-dot" in content

    # OpenAPI contract matching payload elements in client script
    assert "appName: 'AgentBugAssistant'" in content or 'appName: "AgentBugAssistant"' in content
    assert "/agent/interact/" in content
    assert "120000" in content  # 120-second AJAX timeout


@pytest.mark.asyncio
async def test_interact_post_valid_payload_mocked(monkeypatch):
    """Verifies that POST /agent/interact/ with valid OpenAPI payload returns 200 and schema-compliant response."""
    mock_session_service = AsyncMock()
    mock_session = MagicMock()
    mock_session.id = "session_test_999"
    mock_session_service.get_session.return_value = mock_session

    mock_sm = MagicMock()
    mock_sm.session_service = mock_session_service
    mock_sm.root_agent = MagicMock()
    mock_sm.memory_service = MagicMock()

    async def mock_event_stream(*args, **kwargs):
        final_event = MagicMock()
        final_event.is_final_response.return_value = True
        part = MagicMock()
        part.text = "Hello! I am the IT Bug Assistant. How can I help you today?"
        final_event.content.parts = [part]
        yield final_event

    mock_runner = MagicMock()
    mock_runner.run_async.side_effect = mock_event_stream

    monkeypatch.setattr("adk_bug_ticket_agent.views._service_manager", mock_sm)
    monkeypatch.setattr(
        "adk_bug_ticket_agent.views.Runner",
        MagicMock(return_value=mock_runner),
    )

    rf = RequestFactory()
    payload = {
        "appName": "AgentBugAssistant",
        "userId": "user_valid_123",
        "sessionId": "session_valid_456",
        "newMessage": {
            "role": "user",
            "parts": [{"text": "Hello assistant"}]
        }
    }
    request = rf.post(
        "/agent/interact/",
        data=json.dumps(payload),
        content_type="application/json",
    )

    response = await interact_with_agent(request)

    assert response.status_code == 200
    data = json.loads(response.content.decode("utf-8"))
    assert "content" in data
    assert data["content"]["role"] == "model"
    assert len(data["content"]["parts"]) > 0
    assert data["content"]["parts"][0]["text"] == "Hello! I am the IT Bug Assistant. How can I help you today?"
    assert "timestamp" in data
    assert isinstance(data["timestamp"], (int, float))


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_payload", [
    {},  # Empty object
    {"appName": "AgentBugAssistant"},  # Missing userId, sessionId, newMessage
    {"appName": "AgentBugAssistant", "userId": "u1", "sessionId": "s1"},  # Missing newMessage
    {"appName": "AgentBugAssistant", "userId": "u1", "sessionId": "s1", "newMessage": {}},  # Missing parts
    {"appName": "AgentBugAssistant", "userId": "u1", "sessionId": "s1", "newMessage": {"parts": []}},  # Empty parts
    {"appName": "AgentBugAssistant", "userId": "u1", "sessionId": "s1", "newMessage": {"parts": [{"text": ""}]}},  # Empty text
])
async def test_interact_post_invalid_payloads(invalid_payload):
    """Verifies that POST /agent/interact/ rejects malformed or incomplete payloads with HTTP 400."""
    rf = RequestFactory()
    request = rf.post(
        "/agent/interact/",
        data=json.dumps(invalid_payload),
        content_type="application/json",
    )

    response = await interact_with_agent(request)
    assert response.status_code == 400
    data = json.loads(response.content.decode("utf-8"))
    assert "error" in data


@pytest.mark.asyncio
async def test_interact_post_invalid_json():
    """Verifies that non-JSON request bodies return HTTP 400."""
    rf = RequestFactory()
    request = rf.post(
        "/agent/interact/",
        data="not a valid json string",
        content_type="application/json",
    )

    response = await interact_with_agent(request)
    assert response.status_code == 400
    data = json.loads(response.content.decode("utf-8"))
    assert "error" in data


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["put", "delete", "patch"])
async def test_interact_unsupported_methods(method):
    """Verifies that HTTP methods other than GET and POST return HTTP 405."""
    rf = RequestFactory()
    request_func = getattr(rf, method)
    request = request_func("/agent/interact/")

    response = await interact_with_agent(request)
    assert response.status_code == 405
    data = json.loads(response.content.decode("utf-8"))
    assert data["error"] == "Unsupported method"
