from google.adk.agents import Agent
from . import system_prompt
from .tools.tools import get_current_date, search_tool, toolbox_tools
from google.adk.tools import load_memory

# this is only used by adk web not in the django framework.
def get_root_agent():
    print("Root agent initialized.")
    return Agent(
            model="gemini-2.5-flash",
            name="it_bug_assistant_agent",
            instruction=system_prompt.agent_instruction,
            tools=[load_memory, get_current_date, search_tool, *toolbox_tools],
    )


root_agent = get_root_agent()