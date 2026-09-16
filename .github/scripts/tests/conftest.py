"""Pytest fixtures and environment configuration for .github/scripts/tests.

Provides a mock google.antigravity module in sys.modules if not already installed,
enabling unit and contract test execution in local development and offline environments
without requiring proprietary SDK packages (Spec Rule 1).

Adds --run-inference CLI option, @pytest.mark.inference marker management,
and shared evaluation fixtures (eval_cases_dir, load_eval_case, mock_dlp_report, mock_pr_review_file).
"""

from __future__ import annotations

import json
import os
import sys
import types as py_types
from pathlib import Path
from typing import Any, Callable

import pytest

# Ensure .github/scripts and .github/scripts/tests/eval are added to sys.path
_tests_dir = os.path.abspath(os.path.dirname(__file__))
_scripts_dir = os.path.abspath(os.path.join(_tests_dir, ".."))
_eval_dir = os.path.abspath(os.path.join(_tests_dir, "eval"))

for path_to_add in (_scripts_dir, _eval_dir):
    if path_to_add not in sys.path:
        sys.path.insert(0, path_to_add)

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

                def __repr__(self):
                    return f"Thought(step_index={self.step_index}, text={self.text!r})"

                def __str__(self):
                    return self.text

            class ToolCall:
                def __init__(self, name: str = "", args: dict = None):
                    self.name = name
                    self.args = args or {}

                def __repr__(self):
                    return f"ToolCall(name={self.name!r}, args={self.args!r})"

                def __str__(self):
                    return f"{self.name}({self.args})"

            class ToolResult:
                def __init__(self, name: str = "", result: dict = None):
                    self.name = name
                    self.result = result or {}

                def __repr__(self):
                    return f"ToolResult(name={self.name!r}, result={self.result!r})"

                def __str__(self):
                    return f"{self.name}: {self.result}"

            class Text:
                def __init__(self, step_index: int = 0, text: str = ""):
                    self.step_index = step_index
                    self.text = text

                def __repr__(self):
                    return f"Text(step_index={self.step_index}, text={self.text!r})"

                def __str__(self):
                    return self.text

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


# =====================================================================
# Pytest CLI Options & Marker Hooks (Task 7)
# =====================================================================


def pytest_addoption(parser: pytest.Parser) -> None:
    """Registers --run-inference CLI option for running live Gemini evaluations."""
    parser.addoption(
        "--run-inference",
        action="store_true",
        default=False,
        help="Run live LLM inference evaluation tests against Vertex AI",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Registers the inference marker in pytest."""
    config.addinivalue_line(
        "markers",
        "inference: mark test as requiring live LLM inference (Vertex AI)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Automatically skips tests marked with @pytest.mark.inference if --run-inference is NOT provided."""
    if not config.getoption("--run-inference", default=False):
        skip_inference = pytest.mark.skip(
            reason="Pass --run-inference to execute live Vertex AI tests"
        )
        for item in items:
            if "inference" in item.keywords:
                item.add_marker(skip_inference)


# =====================================================================
# Shared Evaluation Fixtures (Task 7)
# =====================================================================


@pytest.fixture
def eval_cases_dir() -> Path:
    """Returns the Path to .github/scripts/tests/eval/cases directory."""
    return Path(__file__).parent / "eval" / "cases"


@pytest.fixture
def load_eval_case(eval_cases_dir: Path) -> Callable[[str], Any]:
    """Callable fixture loading a golden EvalCase by case_id from JSON."""
    def _loader(case_id: str) -> Any:
        filename = case_id if case_id.endswith(".json") else f"{case_id}.json"
        case_path = eval_cases_dir / filename
        if not case_path.exists():
            raise FileNotFoundError(f"Evaluation case fixture file not found: {case_path}")

        with open(case_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        try:
            from evalset_schema import EvalCase
            return EvalCase.model_validate(data)
        except (ImportError, Exception):
            return data

    return _loader


@pytest.fixture
def mock_dlp_report(tmp_path: Path) -> Callable[..., Path]:
    """Fixture returning a callable that creates a temporary clean or infected DLP report file."""
    def _factory(clean: bool = True, custom_content: str | None = None) -> Path:
        report_file = tmp_path / "pii-scan.txt"
        if custom_content:
            content = custom_content
        elif clean:
            content = "✅ No sensitive data or PII detected by Cloud DLP.\n0 findings across 5 files."
        else:
            content = "🚨 Cloud DLP Violations detected: High-confidence AUTH_TOKEN / API_KEY found in settings.py:42."
        report_file.write_text(content, encoding="utf-8")
        return report_file

    return _factory


@pytest.fixture
def mock_pr_review_file(tmp_path: Path) -> Callable[..., Path]:
    """Fixture returning a callable that creates a temporary approved or changes-requested PR review report."""
    def _factory(approved: bool = True, custom_content: str | None = None) -> Path:
        review_file = tmp_path / "pr-review.txt"
        if custom_content:
            content = custom_content
        elif approved:
            content = (
                "Overall Status: APPROVE\n\n"
                "Summary: All clean. Verified code changes and passing test cases.\n"
                "Findings: 0 blockers, 0 warnings."
            )
        else:
            content = (
                "Overall Status: REQUEST_CHANGES\n\n"
                "Summary: Blocking security defect detected.\n"
                "- [BLOCKER] Hardcoded AWS secret key detected in settings.py line 42.\n"
                "Findings: 1 blocker, 0 warnings."
            )
        review_file.write_text(content, encoding="utf-8")
        return review_file

    return _factory
