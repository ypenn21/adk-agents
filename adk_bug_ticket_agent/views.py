from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import time
import os
from google.adk.runners import Runner
from google.genai import types as genai_types  # Aliased to avoid conflict if Django has a 'types'
from . import system_prompt
from .agent import _service_manager

# Using an absolute path or ensuring BASE_DIR is correctly set for Django is important.
@csrf_exempt
async def interact_with_agent(request): # Removed the initial check for session_service and memory_service
    # Ensure memory_service is initialized (it's lightweight, so global is fine)
    # If memory_service was also lazy-loaded, you'd call get_memory_service() here.
    
    if request.method == 'POST':
        try:
            print("interact_with_agent POST request received.")
            data = json.loads(request.body.decode('utf-8'))
            app_name = data.get('appName')
            user_id = data.get('userId')
            session_id = data.get('sessionId')
            new_message_data = data.get('newMessage')

            if not all([app_name, user_id, session_id, new_message_data]) or not new_message_data.get('parts'):
                return JsonResponse({'error': 'Invalid payload structure.'}, status=400)

            user_query = new_message_data['parts'][0].get('text')

            if not user_query:
                return JsonResponse({'error': 'No message provided'}, status=400)

            # The client now manages the session ID. We get the session if it
            # exists, or create a new one. This allows for a persistent
            # conversation history within a single browser session.
            current_session_service = _service_manager.session_service # Get the lazy-loaded instance
            current_session = await current_session_service.get_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )

            if not current_session:
                print(f"Creating new session for app: {app_name}, user: {user_id}, session: {session_id} is {current_session}")
                current_session = await current_session_service.create_session(
                    app_name=app_name, user_id=user_id, session_id=session_id
                )
            else:
                print(f"Existing session for app: {app_name}, user: {user_id}, session: {session_id}")
            runner = Runner(
                app_name=app_name,
                agent=_service_manager.root_agent, # Use the lazy-loaded agent
                session_service=current_session_service,
                memory_service=_service_manager.memory_service, # Use the lazy-loaded instance
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

