#!/bin/bash

# To register a new agent with Gemini EnterpriseAgentspace, run the following curl command:

# Source .env file if it exists.. Use .env.example to create a new .env
if [ -f .env ]; then
  source .env
fi

# Set Discovery Engine location and endpoint
LOCATION="${GEMINI_LOCATION:-global}"
if [ "$LOCATION" == "global" ]; then
  ENDPOINT="discoveryengine.googleapis.com"
else
  ENDPOINT="${LOCATION}-discoveryengine.googleapis.com"
fi

PAYLOAD=$(cat <<EOF
{
  "displayName": "$DISPLAY_NAME",
  "description": "$DESCRIPTION",
  "icon": {
     "uri": "$ICON_URI"
   },
  "adkAgentDefinition": {
    "toolSettings": {
      "toolDescription": "$TOOL_DESCRIPTION"
    },
    "provisionedReasoningEngine": {
      "reasoningEngine": "$AGENT_AGENT_ID"
    }
  }
}
EOF
)

curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  -d "$PAYLOAD" \
  "https://$ENDPOINT/v1alpha/projects/$PROJECT_ID/locations/$LOCATION/collections/default_collection/engines/$GEMINI_ENTERPRISE/assistants/default_assistant/agents"

# Please note that the "authorizations" tag is optional; it is only needed if the Agent needs to act on behalf of the users (when it needs OAuth 2.0 support, see Authorize your agents). 
# PROJECT_ID: the ID of your Google Cloud project.
# APP_ID: the ID of the Gemini EnterpriseAgentspace app.
# DISPLAY_NAME: the display name of the agent.
# DESCRIPTION: the description of the agent, displayed on the frontend; it is only for the user’s benefit. 
# ICON_URI: The public URI of the icon to display near the name of the agent. Alternatively you can pass Base64-encoded image file contents, but in that case you have to use icon.content instead of icon.uri.
# TOOL_DESCRIPTION: the description / prompt of the agent used by the LLM to route requests to the agent. Must properly describe what the agent does. Never shown to the user.
# ADK_DEPLOYMENT_ID: the ID of the reasoning engine endpoint where the ADK agent is deployed.
# REASONING_ENGINE_LOCATION: The cloud location of the reasoning engine depending on which location you are creating an agent at. See Reasoning Engine Location
# AUTH_ID: the IDs of the authorization resources; can be omitted, can be one or can be more than one. See Authorize your agents on how to create such a resource.
