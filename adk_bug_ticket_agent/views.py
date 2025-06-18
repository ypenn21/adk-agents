from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import uuid
import re
import os # Added for DB_URL
import asyncio # For running async code in sync view if needed, though view will be async

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types as genai_types # Aliased to avoid conflict if Django has a 'types'
from . import prompt
from .tools.tools import get_current_date, search_tool, toolbox_tools

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
    session_service = None # Set to None if init fails

root_agent = Agent(
    model="gemini-2.5-flash",
    name="software_assistant_agent", # Changed name slightly to avoid potential conflicts
    instruction=prompt.agent_instruction,
    tools=[get_current_date, search_tool, *toolbox_tools],
)
# --- End Global Initializations ---

@csrf_exempt
async def interact_with_agent(request): # Made the view asynchronous
    if not session_service:
        return JsonResponse({"error": "DatabaseSessionService not initialized"}, status=500)

    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8')) # Ensure body is decoded
            user_query = data.get('message')

            if not user_query:
                return JsonResponse({'error': 'No message provided'}, status=400)

            # Generate unique IDs for this processing session
            # In a real app, user_id might come from auth, session_id from Django session
            session_id = str(uuid.uuid4())
            user_id = str(uuid.uuid4()) # Or link to request.user if authenticated

            current_session = None
            try:
                # Check if get_session is async, if not, adapt
                current_session = await session_service.get_session(
                    app_name=APP_NAME,
                    user_id=user_id,
                    session_id=session_id,
                )
            except Exception as e:
                print(f"Existing Session retrieval failed for session_id='{session_id}' "
                      f"and user_id='{user_id}': {e}")
            
            if current_session is None:
                current_session = await session_service.create_session(
                    app_name=APP_NAME,
                    user_id=user_id,
                    session_id=session_id,
                )
            else:
                print(f"Existing session '{session_id}' has been found. Resuming session.")

            runner = Runner(
                app_name=APP_NAME,
                agent=root_agent, # Your globally defined agent
                session_service=session_service,
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
                    if event.content and event.content.parts:
                        # Assuming the first part of the final response contains the text
                        final_response_text = event.content.parts[0].text
                        break # Exit after getting the first final response part
            
            if final_response_text is None:
                # Fallback or if agent didn't produce a text part in final response
                # Check if the event itself has a direct text attribute if parts are empty
                # This part needs to align with how your specific agent structures its final response.
                # The example parsed JSON, here we are looking for text.
                # If the agent is supposed to return structured JSON, you'd parse it here.
                # For now, we assume a direct text reply or "no text response".
                final_response_text = "Agent did not provide a clear text response in the final event."


            # The example cleaned markdown and parsed JSON. If your agent returns plain text, this is simpler.
            # If it returns markdown with JSON:
            # cleaned_response = re.sub(r"^```(?:json)?\n|```$", "", final_response_text.strip(), flags=re.IGNORECASE)
            # try:
            #     response_data = json.loads(cleaned_response)
            #     # Then extract what you need from response_data
            #     reply_to_user = response_data.get("suggested_response", "Could not parse agent JSON response.")
            # except json.JSONDecodeError:
            #     reply_to_user = "Agent response was not valid JSON after cleanup."
            # else:
            # For now, assume final_response_text is the direct reply.
            reply_to_user = final_response_text.strip()

            return JsonResponse({'reply': reply_to_user})

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

