import os
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Ensure DJANGO environment flag is set
os.environ.setdefault("DJANGO", "true")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.settings")

import django
django.setup()

from django.test import AsyncClient, Client
from django.urls import reverse


def test_urls_reverse():
    """Verify that named URL routes reverse to expected endpoints."""
    assert reverse("root") == "/"
    assert reverse("interact_root") == "/agent/"
    assert reverse("interact_with_agent") == "/agent/interact/"
    assert reverse("chat") == "/agent/chat/"


def test_get_root_and_agent_interact_renders_template():
    """Verify GET requests return status 200 and include crucial UI and DOM elements."""
    client = Client()

    for path in ["/", "/agent/", "/agent/interact/", "/agent/chat/"]:
        response = client.get(path)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        
        # Verify template and key DOM IDs
        assert "IT Bug Assistant" in content
        assert 'id="conversation"' in content
        assert 'id="messageInput"' in content
        assert 'id="sendButton"' in content
        assert 'id="themeToggle"' in content
        assert 'id="pendingIndicator"' in content

        # Verify libraries and CDNs
        assert "jquery-3.7.1.min.js" in content
        assert "marked.min.js" in content
        assert "fonts.googleapis.com" in content

        # Verify dark mode toggle attributes
        assert 'data-theme="light"' in content or 'data-theme' in content
        assert "adk_theme" in content


def test_post_invalid_json():
    """Verify POST request with malformed JSON body returns 400."""
    client = Client()
    response = client.post(
        "/agent/interact/",
        data="not-a-valid-json-string",
        content_type="application/json"
    )
    assert response.status_code == 400
    data = response.json()
    assert "Invalid JSON in request" in data.get("error", "")


def test_post_missing_fields():
    """Verify POST request with missing required ADK fields returns 400."""
    client = Client()
    # Missing required keys (empty payload)
    response = client.post(
        "/agent/interact/",
        data=json.dumps({}),
        content_type="application/json"
    )
    assert response.status_code == 400
    assert response.json().get("error") == "Invalid payload structure."

    # Missing parts in newMessage
    partial_payload = {
        "appName": "AgentBugAssistant",
        "userId": "user_123",
        "sessionId": "some-session",
        "newMessage": {}
    }
    response = client.post(
        "/agent/interact/",
        data=json.dumps(partial_payload),
        content_type="application/json"
    )
    assert response.status_code == 400
    assert response.json().get("error") == "Invalid payload structure."


def test_post_empty_message_text():
    """Verify POST request with empty text returns 400."""
    client = Client()
    payload = {
        "appName": "AgentBugAssistant",
        "userId": "user_123",
        "sessionId": "some-session",
        "newMessage": {
            "parts": [{"text": ""}]
        }
    }
    response = client.post(
        "/agent/interact/",
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert response.status_code == 400
    assert response.json().get("error") == "No message provided"


def test_unsupported_http_method():
    """Verify unsupported methods like PUT or DELETE return 405."""
    client = Client()
    put_response = client.put("/agent/interact/")
    assert put_response.status_code == 405
    assert put_response.json().get("error") == "Unsupported method"

    delete_response = client.delete("/agent/interact/")
    assert delete_response.status_code == 405
    assert delete_response.json().get("error") == "Unsupported method"


def test_post_valid_chat_interaction_mocked():
    """Verify POST request with valid payload triggers ADK runner and returns structured JSON."""
    import asyncio

    async def run_test():
        client = AsyncClient()
        payload = {
            "appName": "AgentBugAssistant",
            "userId": "user_test_456",
            "sessionId": "session_test_789",
            "newMessage": {
                "role": "user",
                "parts": [{"text": "Hello assistant"}]
            },
            "streaming": False
        }

        mock_session = MagicMock()
        mock_session_service = AsyncMock()
        mock_session_service.get_session.return_value = mock_session

        mock_event = MagicMock()
        mock_event.is_final_response.return_value = True
        mock_event.content.parts = [MagicMock(text="I am ready to help you triage bugs.")]

        async def mock_events(*args, **kwargs):
            yield mock_event

        with patch("adk_bug_ticket_agent.views._service_manager") as mock_sm, \
             patch("adk_bug_ticket_agent.views.Runner") as mock_runner_cls:
            
            mock_sm.session_service = mock_session_service
            mock_sm.root_agent = MagicMock()
            mock_sm.memory_service = MagicMock()

            mock_runner_instance = MagicMock()
            mock_runner_instance.run_async = mock_events
            mock_runner_cls.return_value = mock_runner_instance

            response = await client.post(
                "/agent/interact/",
                data=json.dumps(payload),
                content_type="application/json"
            )

            assert response.status_code == 200
            data = response.json()
            assert "content" in data
            assert data["content"]["role"] == "model"
            assert data["content"]["parts"][0]["text"] == "I am ready to help you triage bugs."
            assert "timestamp" in data

    asyncio.run(run_test())
