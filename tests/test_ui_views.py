import json
import os
import django
from django.test import TestCase, Client

os.environ.setdefault("DJANGO", "true")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.settings")
django.setup()




class TestAgentUIView(TestCase):
    def setUp(self):
        self.client = Client()

    def test_get_root_url_renders_interact_template(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>IT Bug Assistant - AI Support</title>")
        self.assertContains(response, "IT Bug Assistant")
        self.assertContains(response, "jquery-3.7.1.min.js")
        self.assertContains(response, "marked.min.js")
        self.assertContains(response, 'id="theme-toggle"')
        self.assertContains(response, 'id="new-chat-btn"')
        self.assertContains(response, 'id="chat-messages"')
        self.assertContains(response, 'id="user-input"')
        self.assertContains(response, 'id="send-btn"')

    def test_get_agent_urls_render_interact_template(self):
        agent_paths = ["/agent/", "/agent/interact/", "/agent/chat/"]
        for path in agent_paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "<title>IT Bug Assistant - AI Support</title>")
                self.assertContains(response, "IT Bug Assistant")


    def test_post_invalid_json_payload(self):
        response = self.client.post(
            "/agent/interact/",
            data="invalid json {",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "Invalid JSON in request")

    def test_post_missing_fields_payload(self):
        # Missing userId, sessionId, newMessage
        response = self.client.post(
            "/agent/interact/",
            data=json.dumps({"appName": "bug_ticket_assistant"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "Invalid payload structure.")

    def test_post_empty_message_text(self):
        payload = {
            "appName": "bug_ticket_assistant",
            "userId": "user_123",
            "sessionId": "session_456",
            "newMessage": {
                "parts": [{"text": ""}]
            }
        }
        response = self.client.post(
            "/agent/interact/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "No message provided")

    def test_unsupported_methods(self):
        for method in ["delete", "put", "patch"]:
            client_method = getattr(self.client, method)
            response = client_method("/agent/interact/")
            self.assertEqual(response.status_code, 405)
            data = response.json()
            self.assertEqual(data.get("error"), "Unsupported method")
