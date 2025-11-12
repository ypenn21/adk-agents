import os
from google.adk.agents import Agent
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from . import system_prompt
from .tools.tools import get_current_date, search_tool, toolbox_tools
from google.adk.tools import load_memory

_root_agent = None
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8000")
SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

# a2a root & subagents https://google.github.io/adk-docs/a2a/quickstart-consuming/#start-the-remote-prime-agent-server
def get_agent():
    global _root_agent
    if _root_agent is None:
        _root_agent = Agent(
            model="gemini-2.5-flash",
            name="it_bug_assistant_agent",
            instruction=system_prompt.agent_instruction,
            tools=[load_memory, get_current_date, search_tool, *toolbox_tools],
        )
        print("Root agent initialized.")  # Added for debugging cold start
    return _root_agent

capabilities = AgentCapabilities(streaming=True)
skill = AgentSkill(
    id="bug_triage_assistant",
    name="Bug Triage Assistant",
    description="Assists in triaging and debugging software issues by searching, creating, and updating bug tickets.",
    tags=["bug-tracking", "triage"],
    examples=["Create a new ticket for a login issue.", "Search for tickets related to 'database connection error'"],
)

# agent_card = AgentCard(
#     name="IT Bug Assistant Agent",
#     description="An agent to help users with bug tickets, including searching, creating, and updating them.",
#     url=f"{PUBLIC_URL}",
#     version="1.0.0",
#     defaultInputModes=SUPPORTED_CONTENT_TYPES,
#     defaultOutputModes=SUPPORTED_CONTENT_TYPES,
#     capabilities=capabilities,
#     skills=[skill],
# )

# this is only used by adk web not in the django framework.
django_env = os.environ.get("DJANGO")
if django_env is None or django_env.strip().lower() != "true":
    # Note: to_a2a() auto-generates an agent card using AgentCardBuilder
    # The custom agent_card defined above can be used with manual A2A app setup if needed
    a2a_app = to_a2a(get_agent(), port=8001)
    # root_agent = get_agent()
else:
    root_agent = None
