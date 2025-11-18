import os
import sys
import vertexai
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp

# Add the project root to the Python path to allow for absolute imports
# This assumes deploy_agent_engine.py is at the project root.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from adk_bug_ticket_agent.agent import get_agent # Keep using get_agent as per user feedback

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
        "AGENT_MODE": "VertexAI",
        "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
        "MCP_TOOLBOX_URL": "https://toolbox-ttjkms4frq-uc.a.run.app",
    }
    
    adk_app = AdkApp(
        agent=get_agent(), # Use get_agent() as per user feedback
        enable_tracing=False,
    )

    remote_app = agent_engines.create(
        adk_app,
        requirements=[
            "google-cloud-aiplatform[adk,agent_engines]",
            "google-adk==1.17.0", # Pinning to current version, consider updating if issues persist
            "a2a-sdk>=0.3.11",
            "python-dotenv==1.1.0",
            "toolbox-core==0.1.0",
            "google-generativeai>=0.8.5",
            "psycopg2-binary",
            "litellm>=1.74.8",
        ],
        display_name="Software Bug Assistant Agent Engine",
        description="Remote Agent Engine for the Software Bug Assistant Django App",
        env_vars=environment_variables,
    )
    print(f"Agent Engine Remote App created: {remote_app.resource_name}")

if __name__ == "__main__":
    main()
