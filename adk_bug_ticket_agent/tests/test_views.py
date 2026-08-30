import json
from unittest.mock import AsyncMock, MagicMock, patch
from django.test import TestCase, RequestFactory
from django.http import JsonResponse
from adk_bug_ticket_agent import views

class TestInteractWithAgent(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch('adk_bug_ticket_agent.views.get_session_service')
    @patch('adk_bug_ticket_agent.views.get_memory_service')
    @patch('adk_bug_ticket_agent.views.get_agent')
    @patch('adk_bug_ticket_agent.views.Runner')
    @patch('adk_bug_ticket_agent.views.genai_types')
    @patch('time.time')
    async def test_interact_with_agent_post_success(
        self, mock_time, mock_genai_types, mock_runner, mock_get_agent, mock_get_memory_service, mock_get_session_service
    ):
        # Arrange
        mock_time.return_value = 12345.6789
        mock_session_service = MagicMock()
        mock_session_service.get_session = AsyncMock(return_value=True)
        mock_get_session_service.return_value = mock_session_service

        mock_memory_service = MagicMock()
        mock_get_memory_service.return_value = mock_memory_service

        mock_agent = MagicMock()
        mock_get_agent.return_value = mock_agent

        mock_runner_instance = MagicMock()
        async def mock_run_async(*args, **kwargs):
            yield MagicMock(is_final_response=lambda: True, content=MagicMock(parts=[MagicMock(text="Test response")]))
        mock_runner_instance.run_async = mock_run_async
        mock_runner.return_value = mock_runner_instance

        mock_genai_types.Content.return_value = "Test Content"
        mock_genai_types.Part.from_text.return_value = "Test Part"

        request_data = {
            "appName": "TestApp",
            "userId": "testuser",
            "sessionId": "testsession",
            "newMessage": {"parts": [{"text": "Hello"}]},
        }
        request = self.factory.post('/agent/interact/', json.dumps(request_data), content_type='application/json')

        # Act
        response = await views.interact_with_agent(request)

        # Assert
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(response_data['content']['parts'][0]['text'], 'Test response')
        self.assertEqual(response_data['timestamp'], 12345.6789)

    async def test_interact_with_agent_get(self):
        # Arrange
        request = self.factory.get('/agent/interact/')

        # Act
        with patch('adk_bug_ticket_agent.views.render') as mock_render:
            await views.interact_with_agent(request)

        # Assert
        mock_render.assert_called_once_with(request, 'adk_agent/interact.html')

    async def test_interact_with_agent_invalid_method(self):
        # Arrange
        request = self.factory.put('/agent/interact/')

        # Act
        response = await views.interact_with_agent(request)

        # Assert
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(json.loads(response.content), {'error': 'Unsupported method'})

    async def test_interact_with_agent_post_invalid_json(self):
        # Arrange
        request = self.factory.post('/agent/interact/', 'invalid json', content_type='application/json')

        # Act
        response = await views.interact_with_agent(request)

        # Assert
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', json.loads(response.content))

    async def test_interact_with_agent_post_missing_data(self):
        # Arrange
        request_data = {"appName": "TestApp"}
        request = self.factory.post('/agent/interact/', json.dumps(request_data), content_type='application/json')

        # Act
        response = await views.interact_with_agent(request)

        # Assert
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content), {'error': 'Invalid payload structure.'})
