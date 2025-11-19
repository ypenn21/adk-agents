import os
import sys
import vertexai
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp

# Add the project root to the Python path to allow for absolute imports
# This assumes deploy_agent_engine.py is at the project root.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from adk_bug_ticket_agent.agent import get_agent
from adk_bug_ticket_agent.agent import ServiceManager

def main():
    project_id = os.environ.get("PROJECT_ID", "genai-apps-25")
    location = "us-central1" # Assuming this is the desired location
    staging_bucket = os.environ.get("STAGING_BUCKET", f"gs://{project_id}-adk-staging")

    if not project_id:
        print("Error: PROJECT_ID environment variable not set.")
        sys.exit(1)

    vertexai.init(project=project_id, location=location, staging_bucket=staging_bucket)

    print("Attempting to create/get Agent Engine Remote App...")
    environment_variables = {
        "VERTEX_AI_ENDPOINT_ID": "2527670579629129728",
        "AGENT_MODE": "Gemini",
        "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
        "MCP_TOOLBOX_URL": "https://toolbox-ttjkms4frq-uc.a.run.app",
    }
    _service_manager = ServiceManager()
    root_agent = _service_manager._init_vertexai_agent

    adk_app = AdkApp(
        agent=root_agent, # Use get_agent() as per user feedback
        enable_tracing=True,
    )

    # Create the agent engine
    # We need to pass the adk_bug_ticket_agent package so that the remote environment
    # has access to the LazyToolboxTool class definition.
    remote_app = agent_engines.create(
        adk_app,
        requirements=[
            "google-cloud-aiplatform[adk,agent_engines]",
            "google-adk==1.17.0",
            "a2a-sdk>=0.3.11",
            "python-dotenv==1.1.0",
            "toolbox-core==0.5.2",
            "google-generativeai>=0.8.5",
            "psycopg2-binary",
            "litellm>=1.74.8",
            "cloudpickle==3.1.2",
            "pydantic==2.12.4",
        ],
        extra_packages=["adk_bug_ticket_agent"],
        display_name="Software Bug Assistant ADK CR Open Gemma Model",
        description="Remote Agent for the Software Bug Assistant build with adk, and fintuned gemma model running on managed vertexai endpoint",
        env_vars=environment_variables,
    )
    print(f"Agent Engine Remote App created: {remote_app.resource_name}")

if __name__ == "__main__":
    main()