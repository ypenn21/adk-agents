"""Pytest fixtures and environment configuration for .github/scripts/tests.

Provides a mock google.antigravity module in sys.modules if not already installed,
enabling unit and contract test execution in local development and offline environments
without requiring proprietary SDK packages (Spec Rule 1).
"""

import sys
import types as py_types

if "google.antigravity" not in sys.modules:
    try:
        import google.antigravity
    except ImportError:
        # Create mock module tree for google.antigravity
        if "google" not in sys.modules:
            google_mod = py_types.ModuleType("google")
            sys.modules["google"] = google_mod
        else:
            google_mod = sys.modules["google"]

        antigravity_mod = py_types.ModuleType("google.antigravity")

        class LocalAgentConfig:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        class Agent:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def chat(self, *args, **kwargs):
                pass

        class _TypesModule(py_types.ModuleType):
            class Thought:
                def __init__(self, step_index: int = 0, text: str = ""):
                    self.step_index = step_index
                    self.text = text

            class ToolCall:
                def __init__(self, name: str = "", args: dict = None):
                    self.name = name
                    self.args = args or {}

            class ToolResult:
                def __init__(self, name: str = "", result: dict = None):
                    self.name = name
                    self.result = result or {}

            class Text:
                def __init__(self, step_index: int = 0, text: str = ""):
                    self.step_index = step_index
                    self.text = text

            class McpStdioServer:
                def __init__(self, name: str = "", command: str = "", args: list = None, env: dict = None):
                    self.name = name
                    self.command = command
                    self.args = args or []
                    self.env = env or {}

            class BudgetConfig:
                def __init__(self, **kwargs):
                    for k, v in kwargs.items():
                        setattr(self, k, v)

            class StopReason:
                STOP_REASON_UNSPECIFIED = "STOP_REASON_UNSPECIFIED"
                END_OF_TURN = "END_OF_TURN"
                MAX_TOTAL_TOKENS_EXCEEDED = "MAX_TOTAL_TOKENS_EXCEEDED"
                MAX_INPUT_TOKENS_EXCEEDED = "MAX_INPUT_TOKENS_EXCEEDED"
                MAX_OUTPUT_TOKENS_EXCEEDED = "MAX_OUTPUT_TOKENS_EXCEEDED"
                MAX_MODEL_CALLS_EXCEEDED = "MAX_MODEL_CALLS_EXCEEDED"
                MAX_TOOL_CALLS_EXCEEDED = "MAX_TOOL_CALLS_EXCEEDED"

        sdk_types = _TypesModule("google.antigravity.types")

        antigravity_mod.Agent = Agent
        antigravity_mod.LocalAgentConfig = LocalAgentConfig
        antigravity_mod.types = sdk_types

        setattr(google_mod, "antigravity", antigravity_mod)
        sys.modules["google.antigravity"] = antigravity_mod
        sys.modules["google.antigravity.types"] = sdk_types
