from django.apps import AppConfig

from vertexai import agent_engines
from .views import get_root_agent

REMOTE_AGENT_ENGINE_RESOURCE_NAME = None
LOCATION = "us-central1"
PROJECT_NUMBER = "genai-playground24"  # Replace with your actual project number


class AdkAgentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "adk_bug_ticket_agent"


def create_agent_engine_remote_app():
    """
    Creates and initializes a remote agent engine application.

    Args:
        agent_instance: The agent object (e.g., google.adk.agents.Agent instance)
                        to be used as the agent_engine for the remote app.

    Returns:
        The created remote_app instance.
    """
    print("Attempting to create/get Agent Engine Remote App...")
    remote_app = agent_engines.create(
        agent_engine=get_root_agent(),
        requirements=[
            "google-cloud-aiplatform[adk,agent_engines]",
        ],
        display_name="Software Bug Assistant Agent Engine",  # Give it a descriptive name
        description="Remote Agent Engine for the Software Bug Assistant Django App",
    )
    global REMOTE_AGENT_ENGINE_RESOURCE_NAME
    REMOTE_AGENT_ENGINE_RESOURCE_NAME = remote_app.resource_name
    print(f"Agent Engine Remote App created: {REMOTE_AGENT_ENGINE_RESOURCE_NAME}")
    return remote_app
