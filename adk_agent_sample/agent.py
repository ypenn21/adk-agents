from google.adk.agents import Agent

from .prompt import agent_instruction
from .tools.tools import get_current_date, search_tool, toolbox_tools


# The root_agent is now initialized and managed within the Django app (adk_agent/views.py).
# This file can be kept for defining agent-related configurations if needed elsewhere,
# or parts of it (like prompt and tool imports if they are not directly used by Django views)
# could be refactored or removed if no longer necessary in this specific file.

# For example, you might still want to define a function here to get a configured agent
# if you need to use it in other non-Django contexts:

# def get_root_agent():
#     return Agent(
#         model="gemini-2.0-flash",
#         name="software_assistant",
#         instruction=agent_instruction,
#         tools=[get_current_date, search_tool, *toolbox_tools],
#     )