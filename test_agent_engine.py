import os
import vertexai
import random
import asyncio
from vertexai import agent_engines

# Resource name from the deployment output (newly deployed with fixes)
RESOURCE_NAME = "projects/803095609412/locations/us-central1/reasoningEngines/344960778098442240"

async def main():
    project_id = os.environ.get("PROJECT_ID", "genai-apps-25")
    location = "us-central1"
    staging_bucket = os.environ.get("STAGING_BUCKET", f"gs://{project_id}-adk-staging")

    vertexai.init(project=project_id, location=location, staging_bucket=staging_bucket)

    print(f"Getting Agent Engine: {RESOURCE_NAME}")
    agent_engine = agent_engines.get(RESOURCE_NAME)

    # Generate a user_id for this test session
    user_id = f"test-user_{random.randint(1000, 9999)}"
    print(f"Using user_id: {user_id}")

    try:
        # Try a simple query first
        query = "Hello, who are you?"
        print(f"\nSending query: {query}")

        print("Response:")
        async for event in agent_engine.async_stream_query(
            user_id=user_id,
            message=query
        ):
            print(event, end="")
        print()

        # Try the tool query with session
        # First create a session to maintain conversation context
        print("\nCreating session for multi-turn conversation...")
        session = agent_engine.create_session(user_id=user_id)
        session_id = session['id']
        print(f"Session created with ID: {session_id}")

        query = "Show me all the tickets with status Open"
        print(f"\nSending query: {query}")

        print("Response:")
        async for event in agent_engine.async_stream_query(
            user_id=user_id,
            session_id=session_id,
            message=query
        ):
            print(event, end="")
        print()

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
