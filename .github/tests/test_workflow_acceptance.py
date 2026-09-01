"""Acceptance and Contract Tests for GitHub Actions Workflow Configuration.

Cites Decisions from docs/spec.md (D-1, D-8, D-9, D-10).
"""

import os
import yaml
import pytest

WORKFLOW_PATH = ".github/workflows/source-code-pii-review.yml"


@pytest.fixture
def workflow_content():
    assert os.path.exists(WORKFLOW_PATH), f"Workflow file missing: {WORKFLOW_PATH}"
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def workflow_yaml(workflow_content):
    return yaml.safe_load(workflow_content)


def test_workflow_does_not_contain_legacy_cli_install(workflow_content):
    """Workflow must eliminate curl | bash installation of agy CLI."""
    assert "curl -fsSL https://antigravity.google/cli/install.sh" not in workflow_content  # D-8
    assert "agy --version" not in workflow_content  # D-8
    assert "agy -p" not in workflow_content  # D-8


def test_workflow_configures_python_setup_and_sdk_dependencies(workflow_content):
    """Workflow must configure Python 3.11 and pip install google-antigravity pydantic."""
    assert "actions/setup-python@v5" in workflow_content  # D-8
    assert "python-version: '3.11'" in workflow_content or 'python-version: "3.11"' in workflow_content  # D-8
    assert "pip install google-antigravity" in workflow_content  # D-8
    assert "pydantic" in workflow_content  # D-8


def test_workflow_runs_python_agent_scripts(workflow_content):
    """Workflow must execute Python scripts for quality gate and PR review."""
    assert "python .github/scripts/pr_reviewer_agent.py" in workflow_content  # D-5, D-6
    assert "python .github/scripts/quality_gate_agent.py" in workflow_content  # D-6, D-9


def test_workflow_enforces_gate_via_json_artifact(workflow_content):
    """Workflow enforcement step must evaluate reports/gate-decision.json."""
    assert "reports/gate-decision.json" in workflow_content  # D-3, D-9
    assert "Enforce Quality Gate" in workflow_content  # D-9


def test_workflow_archives_telemetry_to_gcs(workflow_content):
    """Workflow must upload reports directory including telemetry to GCS."""
    assert "upload-cloud-storage" in workflow_content  # D-10
    assert "path: 'reports'" in workflow_content or 'path: "reports"' in workflow_content  # D-10


def test_workflow_configures_llm_model_env(workflow_content, workflow_yaml):
    """Workflow must configure LLM_Model env var with fallback to gemini-3.7-flash."""
    assert "LLM_Model" in workflow_content
    assert "gemini-3.7-flash" in workflow_content
    env = workflow_yaml.get("env", {})
    assert "LLM_Model" in env
    assert "gemini-3.7-flash" in env["LLM_Model"]

