import os
from google.adk.agents import Agent
from . import system_prompt
from .tools.tools import get_current_date, search_tool, toolbox_tools
from google.adk.tools import load_memory

_root_agent = None

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

# this is only used by adk web not in the django framework.
django_env = os.environ.get("DJANGO")
if django_env is None or django_env.strip().lower() != "true":
    root_agent = get_agent()
else:
    root_agent = None
