from datetime import datetime
import os
import sys

from google.adk.agents import Agent
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from toolbox_core import ToolboxSyncClient
from toolbox_core.sync_tool import ToolboxSyncTool

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

_toolbox_client = None
_loaded_toolsets = {}

def get_toolbox_client():
    global _toolbox_client
    if _toolbox_client is None:
        _toolbox_client = ToolboxSyncClient(TOOLBOX_URL)
    return _toolbox_client

def load_toolset_cached(toolset_name):
    if toolset_name not in _loaded_toolsets:
        client = get_toolbox_client()
        _loaded_toolsets[toolset_name] = client.load_toolset(toolset_name)
    return _loaded_toolsets[toolset_name]

class LazyToolboxTool:
    def __init__(self, name: str, toolset_name: str, original_tool: ToolboxSyncTool = None):
        self.name = name
        self.toolset_name = toolset_name
        self._tool = original_tool
        
    def __getstate__(self):
        return {
            "name": self.name,
            "toolset_name": self.toolset_name
        }

    def __setstate__(self, state):
        self.name = state["name"]
        self.toolset_name = state["toolset_name"]
        self._tool = None

    def _ensure_tool(self):
        if self._tool is None:
            tools = load_toolset_cached(self.toolset_name)
            for t in tools:
                if t.__name__ == self.name:
                    self._tool = t
                    break
            if self._tool is None:
                raise RuntimeError(f"Tool {self.name} not found in toolset {self.toolset_name}")

    def __call__(self, *args, **kwargs):
        self._ensure_tool()
        return self._tool(*args, **kwargs)

    @property
    def __name__(self):
        if self._tool:
            return self._tool.__name__
        self._ensure_tool()
        return self._tool.__name__

    @property
    def __doc__(self):
        self._ensure_tool()
        return self._tool.__doc__

    @property
    def __signature__(self):
        self._ensure_tool()
        return self._tool.__signature__
        
    @property
    def __annotations__(self):
        self._ensure_tool()
        return self._tool.__annotations__
        
    def __getattr__(self, name):
        self._ensure_tool()
        return getattr(self._tool, name)

_toolbox_tools_cache = None

def get_toolbox_tools():
    global _toolbox_tools_cache
    if _toolbox_tools_cache is None:
        if "collectstatic" not in sys.argv:
            # Load tools initially to get names and create wrappers
            real_tools = load_toolset_cached("tickets_toolset")
            _toolbox_tools_cache = [
                LazyToolboxTool(t.__name__, "tickets_toolset", t) 
                for t in real_tools
            ]
        else:
            _toolbox_tools_cache = []
    return _toolbox_tools_cache