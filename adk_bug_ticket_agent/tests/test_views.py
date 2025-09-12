
import json
from unittest.mock import MagicMock, patch, AsyncMock

from django.test import TestCase, RequestFactory
from django.http import JsonResponse, HttpResponse

from adk_bug_ticket_agent import views

class InteractWithAgentTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("adk_bug_ticket_agent.views.get_session_service")
    @patch("adk_bug_ticket_agent.views.get_memory_service")
    @patch("adk_bug_ticket_agent.views.get_agent")
    @patch("adk_bug_ticket_agent.views.Runner")
    @patch("adk_bug_ticket_agent.views.genai_types")
    async def test_interact_with_agent_post_new_session(
        self,
        mock_genai_types,
        mock_runner,
        mock_get_agent,
        mock_get_memory_service,
        mock_get_session_service,
    ):
        # Arrange
        mock_session_service = AsyncMock()
        mock_session_service.get_session.return_value = None
        mock_session_service.create_session.return_value = "new_session"
        mock_get_session_service.return_value = mock_session_service

        mock_memory_service = MagicMock()
        mock_get_memory_service.return_value = mock_memory_service

        mock_agent = MagicMock()
        mock_get_agent.return_value = mock_agent

        async def mock_events():
            event = MagicMock()
            event.is_final_response.return_value = True
            event.content.parts = [MagicMock()]
            event.content.parts[0].text = "Test response"
            yield event

        mock_runner_instance = MagicMock()
        mock_runner_instance.run_async.return_value = mock_events()
        mock_runner.return_value = mock_runner_instance

        mock_genai_types.Content.return_value = "user_message_content"

        data = {
            "appName": "test_app",
            "userId": "test_user",
            "sessionId": "test_session",
            "newMessage": {"parts": [{"text": "Hello"}]},
        }
        request = self.factory.post(
            "/agent/interact/",
            data=json.dumps(data),
            content_type="application/json",
        )

        # Act
        response = await views.interact_with_agent(request)

        # Assert
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(response_data["content"]["parts"][0]["text"], "Test response")

        mock_get_session_service.assert_called_once()
        mock_session_service.get_session.assert_called_once_with(
            app_name="test_app", user_id="test_user", session_id="test_session"
        )
        mock_session_service.create_session.assert_called_once_with(
            app_name="test_app", user_id="test_user", session_id="test_session"
        )
        mock_runner.assert_called_once_with(
            app_name="test_app",
            agent=mock_agent,
            session_service=mock_session_service,
            memory_service=mock_memory_service,
        )
        mock_runner_instance.run_async.assert_called_once_with(
            user_id="test_user",
            session_id="test_session",
            new_message="user_message_content",
        )

    @patch("adk_bug_ticket_agent.views.get_session_service")
    @patch("adk_bug_ticket_agent.views.get_memory_service")
    @patch("adk_bug_ticket_agent.views.get_agent")
    @patch("adk_bug_ticket_agent.views.Runner")
    @patch("adk_bug_ticket_agent.views.genai_types")
    async def test_interact_with_agent_post_existing_session(
        self,
        mock_genai_types,
        mock_runner,
        mock_get_agent,
        mock_get_memory_service,
        mock_get_session_service,
    ):
        # Arrange
        mock_session_service = AsyncMock()
        mock_session_service.get_session.return_value = "existing_session"
        mock_get_session_service.return_value = mock_session_service

        mock_memory_service = MagicMock()
        mock_get_memory_service.return_value = mock_memory_service

        mock_agent = MagicMock()
        mock_get_agent.return_value = mock_agent

        async def mock_events():
            event = MagicMock()
            event.is_final_response.return_value = True
            event.content.parts = [MagicMock()]
            event.content.parts[0].text = "Test response"
            yield event

        mock_runner_instance = MagicMock()
        mock_runner_instance.run_async.return_value = mock_events()
        mock_runner.return_value = mock_runner_instance

        mock_genai_types.Content.return_value = "user_message_content"

        data = {
            "appName": "test_app",
            "userId": "test_user",
            "sessionId": "test_session",
            "newMessage": {"parts": [{"text": "Hello"}]},
        }
        request = self.factory.post(
            "/agent/interact/",
            data=json.dumps(data),
            content_type="application/json",
        )

        # Act
        response = await views.interact_with_agent(request)

        # Assert
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 200)
        mock_session_service.create_session.assert_not_called()

    async def test_interact_with_agent_post_invalid_payload(self):
        # Arrange
        request = self.factory.post(
            "/agent/interact/",
            data=json.dumps({}),
            content_type="application/json",
        )

        # Act
        response = await views.interact_with_agent(request)

        # Assert
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)
        self.assertEqual(response_data["error"], "Invalid payload structure.")

    async def test_interact_with_agent_post_no_message(self):
        # Arrange
        data = {
            "appName": "test_app",
            "userId": "test_user",
            "sessionId": "test_session",
            "newMessage": {"parts": [{"text": ""}]},
        }
        request = self.factory.post(
            "/agent/interact/",
            data=json.dumps(data),
            content_type="application/json",
        )

        # Act
        response = await views.interact_with_agent(request)

        # Assert
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)
        self.assertEqual(response_data["error"], "No message provided")

    @patch("adk_bug_ticket_agent.views.render")
    async def test_interact_with_agent_get(self, mock_render):
        # Arrange
        mock_render.return_value = HttpResponse()
        request = self.factory.get("/agent/interact/")

        # Act
        response = await views.interact_with_agent(request)

        # Assert
        self.assertIsInstance(response, HttpResponse)
        mock_render.assert_called_once_with(request, "adk_agent/interact.html")

    async def test_interact_with_agent_unsupported_method(self):
        # Arrange
        request = self.factory.put("/agent/interact/")

        # Act
        response = await views.interact_with_agent(request)

        # Assert
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 405)
        response_data = json.loads(response.content)
        self.assertEqual(response_data["error"], "Unsupported method")
