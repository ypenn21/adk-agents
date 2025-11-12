#!/bin/bash

PAYLOAD=$(cat <<'EOF'
{
  "name": "adk-a2a-agent-bug-assist",
  "displayName": "Soft Micro Bug Agent",
  "description": "The Bug Assistant is a sample agent hosted on django designed to help IT Support and Software Developers triage, manage, and resolve software issues. This agent uses ADK Python, PostgreSQL database, Gemini, MCP server, RAG, and Google Search to assist IT in triaging.",
  "icon": {
    "content": "data:image/png;base64,iVBORw="
  },
  "a2aAgentDefinition": {
    "jsonAgentCard": "{\"capabilities\":{\"streaming\":true},\"defaultInputModes\":[\"text\",\"text/plain\"],\"defaultOutputModes\":[\"text\",\"text/plain\"],\"description\":\"An agent to help users with bug tickets, including searching, creating, and updating them.\",\"name\":\"IT Bug Assistant Agent\",\"preferredTransport\":\"JSONRPC\",\"protocolVersion\":\"0.3.0\",\"skills\":[{\"description\":\"Assists in triaging and debugging software issues by searching, creating, and updating bug tickets.\",\"examples\":[\"Create a new ticket for a login issue.\",\"Search for tickets related to 'database connection error'\"],\"id\":\"bug_triage_assistant\",\"name\":\"Bug Triage Assistant\",\"tags\":[\"bug-tracking\",\"triage\"]}],\"url\":\"https://adk-a2a-agent-bug-assist-803095609412.us-central1.run.app\",\"version\":\"1.0.0\"}"
  }
}
EOF
)

curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  https://discoveryengine.googleapis.com/v1alpha/projects/genai-apps-25/locations/global/collections/default_collection/engines/gemini-enterprise-17628189_1762818964034/assistants/default_assistant/agents