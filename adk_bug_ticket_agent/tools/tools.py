import asyncio
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime
import inspect
import os
import sys
from typing import Any

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
    model="gemini-3.7-flash",
    name="search_agent",
    instruction="""
    You're a specialist in Google Search.
    """,
    tools=[google_search],
)

search_tool = AgentTool(search_agent)


# ----- Example of Google Cloud Tools (MCP Toolbox for Databases) -----
TOOLBOX_URL = os.getenv("MCP_TOOLBOX_URL", "http://127.0.0.1:5000")
TOOLBOX_TIMEOUT = float(os.getenv("MCP_TOOLBOX_TIMEOUT", "30"))

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
    """Lazy-loading, picklable wrapper around ToolboxSyncTool with timeout protection."""

    def __init__(
        self,
        name: str,
        toolset_name: str,
        original_tool: ToolboxSyncTool | None = None,
        timeout: float = TOOLBOX_TIMEOUT,
    ) -> None:
        self.name = name
        self.toolset_name = toolset_name
        self.timeout = timeout
        self._tool: ToolboxSyncTool | None = original_tool
        self._cached_doc: str | None = (
            getattr(original_tool, "__doc__", None) if original_tool is not None else None
        )
        self._cached_sig: inspect.Signature | None = (
            getattr(original_tool, "__signature__", None) if original_tool is not None else None
        )
        self._cached_annotations: dict[str, Any] | None = (
            dict(original_tool.__annotations__)
            if original_tool is not None and hasattr(original_tool, "__annotations__") and original_tool.__annotations__ is not None
            else None
        )

    def __getstate__(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "toolset_name": self.toolset_name,
            "timeout": self.timeout,
            "_cached_doc": self._cached_doc,
            "_cached_sig": self._cached_sig,
            "_cached_annotations": self._cached_annotations,
        }

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.name = state["name"]
        self.toolset_name = state["toolset_name"]
        self.timeout = state.get("timeout", TOOLBOX_TIMEOUT)
        self._cached_doc = state.get("_cached_doc")
        self._cached_sig = state.get("_cached_sig")
        self._cached_annotations = state.get("_cached_annotations")
        self._tool = None

    def _ensure_tool(self) -> None:
        if self._tool is None:
            tools = load_toolset_cached(self.toolset_name)
            for t in tools:
                if t.__name__ == self.name:
                    self._tool = t
                    break
            if self._tool is None:
                raise RuntimeError(f"Tool {self.name} not found in toolset {self.toolset_name}")
            if self._cached_doc is None:
                self._cached_doc = getattr(self._tool, "__doc__", None)
            if self._cached_sig is None:
                self._cached_sig = getattr(self._tool, "__signature__", None)
            if self._cached_annotations is None:
                ann = getattr(self._tool, "__annotations__", None)
                self._cached_annotations = dict(ann) if ann is not None else None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self._ensure_tool()
        async_tool = getattr(self._tool, "_ToolboxSyncTool__async_tool", None)
        loop = getattr(self._tool, "_ToolboxSyncTool__loop", None)
        if async_tool is not None and loop is not None:
            coro = async_tool(*args, **kwargs)
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            try:
                return future.result(timeout=self.timeout)
            except FuturesTimeoutError:
                future.cancel()
                return {
                    "error": (
                        f"Tool '{self.name}' timed out after {self.timeout}s "
                        "while communicating with MCP Toolbox."
                    )
                }
            except Exception as e:
                return {"error": f"Tool '{self.name}' execution failed: {e}"}
        return self._tool(*args, **kwargs)

    @property
    def __name__(self) -> str:
        return self.name

    @property
    def __doc__(self) -> str:
        if self._cached_doc is not None:
            return self._cached_doc
        try:
            self._ensure_tool()
            if self._cached_doc is not None:
                return self._cached_doc
            if self._tool is not None:
                return self._tool.__doc__ or ""
        except Exception:
            pass
        return ""

    @property
    def __signature__(self) -> Any:
        if self._cached_sig is not None:
            return self._cached_sig
        try:
            self._ensure_tool()
            if self._cached_sig is not None:
                return self._cached_sig
            if self._tool is not None and hasattr(self._tool, "__signature__"):
                return self._tool.__signature__
        except Exception:
            pass
        try:
            return inspect.signature(self.__call__)
        except Exception:
            return None

    @property
    def __annotations__(self) -> dict[str, Any]:
        if self._cached_annotations is not None:
            return self._cached_annotations
        try:
            self._ensure_tool()
            if self._cached_annotations is not None:
                return self._cached_annotations
            if self._tool is not None and hasattr(self._tool, "__annotations__"):
                return dict(self._tool.__annotations__)
        except Exception:
            pass
        return {}

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        try:
            self._ensure_tool()
        except Exception as e:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'") from e
        return getattr(self._tool, name)

_toolbox_tools_cache = None

def get_toolbox_tools():
    global _toolbox_tools_cache
    if _toolbox_tools_cache is None:
        if "collectstatic" not in sys.argv:
            try:
                # Load tools initially to get names and create wrappers
                real_tools = load_toolset_cached("tickets_toolset")
                _toolbox_tools_cache = [
                    LazyToolboxTool(t.__name__, "tickets_toolset", t, timeout=TOOLBOX_TIMEOUT)
                    for t in real_tools
                ]
            except Exception as e:
                print(f"Warning: Could not connect to MCP Toolbox server: {e}")
                _toolbox_tools_cache = []
        else:
            _toolbox_tools_cache = []
    return _toolbox_tools_cache