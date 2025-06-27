from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import time
import uuid
import os

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import DatabaseSessionService
from google.genai import types as genai_types  # Aliased to avoid conflict if Django has a 'types'
from . import prompt
from .tools.tools import get_current_date, search_tool, toolbox_tools
from google.adk.tools import load_memory


# --- Global Initializations ---
# For SQLite, make sure the directory for the DB file is writable by the Django process.
# Using an absolute path or ensuring BASE_DIR is correctly set for Django is important.
# For simplicity, placing it in the project root.
DB_URL = f"sqlite:///{(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'adk_sessions.db'))}"

# Lazy initialization for session_service
_session_service_instance = None
def get_session_service():
    global _session_service_instance
    if _session_service_instance is None:
        _session_service_instance = DatabaseSessionService(db_url=DB_URL)
        print(f"ADK Database URL: {DB_URL}")
    return _session_service_instance

# try:
#     session_service = DatabaseSessionService(db_url=DB_URL)
#     print("Database session service initialized successfully.")
# except Exception as e:
#     print(f"Database session service initialization failed: {e}")
#     session_service = None

# adding memory https://google.github.io/adk-docs/sessions/memory/#how-memory-works-in-practice
# ToDO utilize VertexAiRagMemoryService from from google.adk.memory import VertexAiRagMemoryService
# The RAG Corpus name or ID
# RAG_CORPUS_RESOURCE_NAME = "projects/your-gcp-project-id/locations/us-central1/ragCorpora/your-corpus-id"
# ptional configuration for retrieval
# SIMILARITY_TOP_K = 5
# VECTOR_DISTANCE_THRESHOLD = 0.7
# memory_service = VertexAiRagMemoryService(
#     rag_corpus=RAG_CORPUS_RESOURCE_NAME,
#     similarity_top_k=SIMILARITY_TOP_K,
#     vector_distance_threshold=VECTOR_DISTANCE_THRESHOLD
# )

memory_service = InMemoryMemoryService()

# Lazy initialization for root_agent
_root_agent_instance = None

def get_root_agent():
    global _root_agent_instance
    if _root_agent_instance is None:
        _root_agent_instance = Agent(
            model="gemini-2.5-flash",
            name="software_assistant_agent",
            instruction=prompt.agent_instruction,
            tools=[load_memory, get_current_date, search_tool, *toolbox_tools],
        )
        print("Root agent initialized.") # Added for debugging cold start
    return _root_agent_instance
# --- End Global Initializations ---

@csrf_exempt
async def interact_with_agent(request): # Removed the initial check for session_service and memory_service
    # Ensure memory_service is initialized (it's lightweight, so global is fine)
    # If memory_service was also lazy-loaded, you'd call get_memory_service() here.
    
    if request.method == 'POST':
        try:
            print("Database session service initialized successfully.")
            print(f"Database session service initialization failed: {e}")
            data = json.loads(request.body.decode('utf-8'))
            app_name = data.get('appName')
            user_id = data.get('userId')
            session_id = data.get('sessionId')
            new_message_data = data.get('newMessage')

            if not all([app_name, user_id, session_id, new_message_data, new_message_data.get('parts')]):
                return JsonResponse({'error': 'Invalid payload structure.'}, status=400)

            user_query = new_message_data['parts'][0].get('text')

            if not user_query:
                return JsonResponse({'error': 'No message provided'}, status=400)

            # The client now manages the session ID. We get the session if it
            # exists, or create a new one. This allows for a persistent
            # conversation history within a single browser session.
            current_session_service = get_session_service() # Get the lazy-loaded instance
            current_session = await session_service.get_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
            if not current_session:
                current_session = await current_session_service.create_session(
                    app_name=app_name, user_id=user_id, session_id=session_id
                )

            runner = Runner(
                app_name=app_name,
                agent=get_root_agent(), # Use the lazy-loaded agent
                session_service=current_session_service, # Use the lazy-loaded instance
                memory_service=memory_service,
            )

            user_message_content = genai_types.Content(
                role="user", parts=[genai_types.Part.from_text(text=user_query)]
            )
            
            events = runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=user_message_content,
            )

            final_response_text = None
            async for event in events:
                if event.is_final_response():
                    if event.content and event.content.parts and event.content.parts[0].text:
                        final_response_text = event.content.parts[0].text
                        break
            
            if final_response_text is None:
                final_response_text = "Agent did not provide a clear text response."

            response_payload = {
                "content": {
                    "parts": [
                        {
                            "text": final_response_text.strip()
                        }
                    ],
                    "role": "model"
                },
                "timestamp": time.time()
            }
            return JsonResponse(response_payload)

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON in request'}, status=400)
        except Exception as e:
            import traceback
            print("---------- EXCEPTION IN interact_with_agent ----------")
            traceback.print_exc()
            print("----------------------------------------------------")
            return JsonResponse({'error': str(e), 'traceback': traceback.format_exc()}, status=500)

    elif request.method == 'GET':
        return render(request, 'adk_agent/interact.html')
    
    return JsonResponse({'error': 'Unsupported method'}, status=405)
