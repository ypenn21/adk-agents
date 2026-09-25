import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DJANGO", "true")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.settings")

import django
django.setup()

from django.test import AsyncClient, Client
from django.urls import reverse
from adk_bug_ticket_agent import views



@pytest.mark.asyncio
async def test_ui_get_root_status_and_content():
    """Validates that GET / renders interact.html with 200 OK and essential UI elements."""
    client = AsyncClient()
    response = await client.get("/")

    assert response.status_code == 200
    content = response.content.decode("utf-8")

    # Branding & Structure
    assert "IT Bug Assistant" in content
    assert "Online" in content
    assert 'id="conversation"' in content
    assert 'id="messageInput"' in content
    assert 'id="sendButton"' in content
    assert 'id="loadingIndicator"' in content
    assert 'id="themeToggle"' in content

    # CSS Variables / Themes
    assert 'data-theme="light"' in content
    assert ":root[data-theme=\"light\"]" in content
    assert ":root[data-theme=\"dark\"]" in content

    # Dependencies / CDNs
    assert "jquery-3.7.1" in content
    assert "marked.min.js" in content
    assert "fonts.googleapis.com" in content


@pytest.mark.asyncio
async def test_ui_get_agent_interact_status_and_content():
    """Validates that GET /agent/interact/ returns 200 with the interaction page."""
    client = AsyncClient()
    response = await client.get("/agent/interact/")

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "IT Bug Assistant" in content
    assert 'id="chatForm"' in content


@pytest.mark.asyncio
async def test_ui_get_agent_chat_route():
    """Validates that GET /agent/chat/ routes to the interaction page."""
    client = AsyncClient()
    response = await client.get("/agent/chat/")

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "IT Bug Assistant" in content


@pytest.mark.asyncio
async def test_post_invalid_json():
    """Validates that sending invalid JSON to /agent/interact/ returns HTTP 400."""
    client = AsyncClient()
    response = await client.post(
        "/agent/interact/",
        data="not a valid json {",
        content_type="application/json"
    )

    assert response.status_code == 400
    data = json.loads(response.content.decode("utf-8"))
    assert data.get("error") == "Invalid JSON in request"


@pytest.mark.asyncio
async def test_post_missing_payload_structure():
    """Validates that missing required fields in payload returns HTTP 400."""
    client = AsyncClient()

    # Empty object
    response = await client.post(
        "/agent/interact/",
        data=json.dumps({}),
        content_type="application/json"
    )
    assert response.status_code == 400
    data = json.loads(response.content.decode("utf-8"))
    assert data.get("error") == "Invalid payload structure."

    # Missing parts
    response = await client.post(
        "/agent/interact/",
        data=json.dumps({
            "appName": "AgentBugAssistant",
            "userId": "user1",
            "sessionId": "sess1",
            "newMessage": {"role": "user", "parts": []}
        }),
        content_type="application/json"
    )
    assert response.status_code == 400
    data = json.loads(response.content.decode("utf-8"))
    assert data.get("error") == "Invalid payload structure."


@pytest.mark.asyncio
async def test_post_empty_message_text():
    """Validates that providing an empty text part returns HTTP 400."""
    client = AsyncClient()
    payload = {
        "appName": "AgentBugAssistant",
        "userId": "user1",
        "sessionId": "sess1",
        "newMessage": {
            "role": "user",
            "parts": [{"text": ""}]
        }
    }
    response = await client.post(
        "/agent/interact/",
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert response.status_code == 400
    data = json.loads(response.content.decode("utf-8"))
    assert data.get("error") == "No message provided"


@pytest.mark.asyncio
async def test_unsupported_methods():
    """Validates that unsupported HTTP methods return HTTP 405."""
    client = AsyncClient()

    put_response = await client.put("/agent/interact/")
    assert put_response.status_code == 405

    delete_response = await client.delete("/agent/interact/")
    assert delete_response.status_code == 405


def test_url_reversals():
    """Validates that named URLs reverse correctly."""
    assert reverse("root") == "/"
    assert reverse("interact_root") == "/agent/"
    assert reverse("interact_with_agent") == "/agent/interact/"
    assert reverse("chat") == "/agent/chat/"


@pytest.mark.asyncio
async def test_post_chat_mocked_success():
    """Validates that a valid POST request to /agent/interact/ returns 200 with model response."""
    client = AsyncClient()
    payload = {
        "appName": "AgentBugAssistant",
        "userId": "user_test",
        "sessionId": "session_test_123",
        "newMessage": {
            "role": "user",
            "parts": [{"text": "Show me open bugs"}]
        },
        "streaming": False
    }

    from unittest.mock import PropertyMock

    mock_session = MagicMock()
    mock_session_service = AsyncMock()
    mock_session_service.get_session.return_value = mock_session

    mock_event = MagicMock()
    mock_event.is_final_response.return_value = True
    mock_event.content.parts = [MagicMock(text="Here are the open bugs: BUG-1")]

    async def mock_run_async(*args, **kwargs):
        yield mock_event

    with patch.object(type(views._service_manager), "session_service", new_callable=PropertyMock, return_value=mock_session_service), \
         patch("adk_bug_ticket_agent.views.Runner") as mock_runner_class:
        mock_runner_instance = MagicMock()
        mock_runner_instance.run_async = mock_run_async
        mock_runner_class.return_value = mock_runner_instance

        response = await client.post(
            "/agent/interact/",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 200
        data = json.loads(response.content.decode("utf-8"))
        assert "content" in data
        assert data["content"]["role"] == "model"
        assert len(data["content"]["parts"]) == 1
        assert data["content"]["parts"][0]["text"] == "Here are the open bugs: BUG-1"
        assert "timestamp" in data

