import os
from google.adk.agents import Agent
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from . import system_prompt
from .agent_executor import AdkAgentToA2AExecutor
from .tools.tools import get_current_date, search_tool, toolbox_tools
from google.adk.tools import load_memory

_root_agent = None
AGENT_PORT = os.environ.get("AGENT_PORT", "8000")
AGENT_URL = os.environ.get("AGENT_URL", f"http://127.0.0.1:{AGENT_PORT}")
SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

# a2a root & subagents https://google.github.io/adk-docs/a2a/quickstart-consuming/#start-the-remote-prime-agent-server
def get_agent():
    global _root_agent
    if _root_agent is None:
        _root_agent = Agent(
            model="gemini-2.5-flash",
            name="it_bug_assistant_agent",
            description="An agent to help users with bug tickets, including searching, creating, and updating them.",
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

agent_card = AgentCard(
    name="IT Bug Assistant Agent",
    description="An agent to help users with bug tickets, including searching, creating, and updating them.",
    url=f"{AGENT_URL}",
    version="1.0.0",
    defaultInputModes=SUPPORTED_CONTENT_TYPES,
    defaultOutputModes=SUPPORTED_CONTENT_TYPES,
    capabilities=capabilities,
    skills=[skill],
)

# 1. Create the AgentCard, RequestHandler, and App at the global scope.
#    This is more efficient as it's done only once when the function instance starts.

# this is only used by adk web not in the django framework.
django_env = os.environ.get("DJANGO")
if django_env is None or django_env.strip().lower() != "true":
    # Note: to_a2a() auto-generates an agent card using AgentCardBuilder
    # The agent card uses the agent's name and description properties
    # Skills are auto-generated from the agent's tools
    root_agent = get_agent()
    a2a_app = to_a2a(root_agent, port=AGENT_PORT)

    request_handler = DefaultRequestHandler(
        agent_executor=AdkAgentToA2AExecutor(root_agent),
        task_store=InMemoryTaskStore(),
    )

    # 2. The Functions Framework will automatically look for this 'app' variable.
    app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    ).build()
    
else:
    root_agent = None
