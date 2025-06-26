from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
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
APP_NAME = "SoftwareBugAssistant"
# For SQLite, make sure the directory for the DB file is writable by the Django process.
# Using an absolute path or ensuring BASE_DIR is correctly set for Django is important.
# For simplicity, placing it in the project root.
DB_URL = f"sqlite:///{(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'adk_sessions.db'))}"
print(f"ADK Database URL: {DB_URL}")

try:
    session_service = DatabaseSessionService(db_url=DB_URL)
    print("Database session service initialized successfully.")
except Exception as e:
    print(f"Database session service initialization failed: {e}")
    session_service = None

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

root_agent = Agent(
    model="gemini-2.5-flash",
    name="software_assistant_agent",
    instruction=prompt.agent_instruction,
    tools=[load_memory, get_current_date, search_tool, *toolbox_tools],
)
# --- End Global Initializations ---

@csrf_exempt
async def interact_with_agent(request):
    if not session_service or not memory_service:
        return JsonResponse({"error": "Service not initialized"}, status=500)

    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            user_query = data.get('message')

            if not user_query:
                return JsonResponse({'error': 'No message provided'}, status=400)

            # A persistent user_id is needed for MemoryService to recall context
            # across different requests. In a real app, this would come from
            # user authentication. For this example, we'll use a static ID.
            user_id = "static_user_for_demo"

            # This is a deliberate architectural decision that leverages the distinction between the ADK SessionService and MemoryService to manage the conversation's history.

            # Here’s a breakdown of why it's implemented this way:

            # Atomic Turns as Sessions: The current design treats each user-agent interaction (a single "turn") as a self-contained, atomic Session. The SessionService is used
            #  to manage the state for just that one turn.

            # MemoryService for Long-Term Context: The InMemoryMemoryService acts as the long-term memory for the agent. After each turn is complete, the entire session (containing 
            # the user's query and the agent's response) is saved to the MemoryService using memory_service.add_session_to_memory(completed_session).

            # Persistent user_id Links Turns: While the session_id is ephemeral and changes with every turn, the user_id is static ("static_user_for_demo"). This static user_id is
            #  the crucial link that allows the MemoryService to group all the individual turn-sessions together for a single user.

            # Agent-Driven Recall: When the agent needs to remember something from a previous turn (e.g., "what is my name?"), it doesn't rely on a long-running session. Instead,
            #  as instructed in your prompt.py, it uses the load_memory tool. This tool queries the MemoryService for all past sessions associated with the user_id, effectively 
            # searching the entire conversation history to find the answer.

            # In Summary
            # This approach makes your web backend stateless regarding the active conversation. It doesn't need to manage and persist a single session_id for a user across multiple
            # requests. Instead, it treats each request as a new unit of work that gets recorded in a long-term, searchable memory. This is a powerful pattern, especially for
            # agents that need to recall information over very long periods or even across different conversations with the same user.
            session_id = str(uuid.uuid4()) # A new session for each turn

            current_session = await session_service.create_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )

            runner = Runner(
                app_name=APP_NAME,
                agent=root_agent,
                session_service=session_service,
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

            # After processing, add the completed session to memory for future recall.
            completed_session = await session_service.get_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )
            if completed_session:
                await memory_service.add_session_to_memory(completed_session)

            return JsonResponse({'reply': final_response_text.strip()})

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
