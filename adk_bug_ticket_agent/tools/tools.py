from datetime import datetime
import os
import sys

from google.adk.agents import Agent
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from toolbox_core import ToolboxSyncClient

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# ----- Example of a Function tool -----
def get_current_date() -> dict:
    """
    Get the current date in the format YYY-MM-DD
    """
    return {"current_date": datetime.now().strftime("%Y-%m-%d")}


# ----- Example of a Built-in Tool -----
search_agent = Agent(
    model="gemini-2.5-flash",
    name="search_agent",
    instruction="""
    You're a specialist in Google Search.
    """,
    tools=[google_search],
)

search_tool = AgentTool(search_agent)


# ----- Example of Google Cloud Tools (MCP Toolbox for Databases) -----
TOOLBOX_URL = os.getenv("MCP_TOOLBOX_URL", "http://127.0.0.1:5000")
_toolbox_tools_cache = None

def get_toolbox_tools():
    global _toolbox_tools_cache
    if _toolbox_tools_cache is None:
        toolbox = ToolboxSyncClient(TOOLBOX_URL)
        # This check might not be relevant in a deployed environment,
        # but keeping it for consistency with original code.
        if "collectstatic" not in sys.argv:
            _toolbox_tools_cache = toolbox.load_toolset("tickets_toolset")
        else:
            _toolbox_tools_cache = [] # Or handle appropriately
    return _toolbox_tools_cache

