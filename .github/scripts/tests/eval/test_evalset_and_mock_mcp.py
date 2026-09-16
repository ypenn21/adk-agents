"""Tests for EvalSet Schema, Golden Fixtures, and Mock MCP Server (Stream 1)."""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Ensure .github/scripts and .github/scripts/tests/eval are on sys.path
_scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
_eval_dir = os.path.abspath(os.path.dirname(__file__))
for d in (_scripts_dir, _eval_dir):
    if d not in sys.path:
        sys.path.insert(0, d)

from evalset_schema import (
    EvalCase,
    EvalRunMetric,
    EvalSuiteSummary,
    ExpectedFindingAssertion,
    ExpectedGateAssertion,
    ExpectedReviewAssertion,
    PRFindingSeverity,
    ReviewStatus,
    SeverityLevel,
    ViolationCategory,
)
from mock_mcp_server import (
    MockGitHubMcpServer,
    create_mock_github_mcp_server,
    create_mock_mcp_config,
)


def test_evalset_schema_model_instantiation():
    """Tests programmatic creation of EvalCase and assertion models."""
    finding_assertion = ExpectedFindingAssertion(
        file_path="main.py",
        expected_severity=PRFindingSeverity.BLOCKER,
        keyword_in_title_or_details="secret",
    )
    review_assertion = ExpectedReviewAssertion(
        expected_status=[ReviewStatus.REQUEST_CHANGES],
        min_findings=1,
        has_blockers=True,
        required_findings=[finding_assertion],
    )
    gate_assertion = ExpectedGateAssertion(
        expected_passed=False,
        min_failures=1,
        expected_failure_categories=[ViolationCategory.CREDENTIAL_LEAK],
        expected_severities=[SeverityLevel.CRITICAL],
    )

    case = EvalCase(
        case_id="tc_custom",
        name="Custom Test Case",
        description="A custom test case for validation",
        category="secret_leak",
        diff_content="diff --git a/foo.py b/foo.py\n+KEY=123\n",
        modified_files={"foo.py": [1]},
        file_tree={"foo.py": "KEY=123\n"},
        expected_review=review_assertion,
        expected_gate=gate_assertion,
    )

    assert case.case_id == "tc_custom"
    assert case.category == "secret_leak"
    assert case.expected_review.has_blockers is True
    assert case.expected_gate.expected_passed is False


def test_all_golden_test_case_fixtures_valid(tmp_path: Path):
    """Loads and validates all 7 golden test case fixtures against EvalCase."""
    cases_dir = Path(_eval_dir) / "cases"
    fixture_files = sorted(cases_dir.glob("*.json"))
    assert len(fixture_files) == 7, f"Expected 7 fixtures in {cases_dir}, found {len(fixture_files)}"

    expected_ids = {
        "tc01_clean_code",
        "tc02_secret_leak",
        "tc03_sql_injection",
        "tc04_zero_division",
        "tc05_style_suggestion",
        "tc06_fail_closed_dlp",
        "tc07_blocker_alignment",
    }

    found_ids = set()
    for fixture_path in fixture_files:
        case = EvalCase.from_file(fixture_path)
        assert case.case_id, f"Missing case_id in {fixture_path}"
        assert case.name, f"Missing name in {fixture_path}"
        assert case.description, f"Missing description in {fixture_path}"
        assert case.category, f"Missing category in {fixture_path}"
        found_ids.add(case.case_id)

        # Test round-trip serialization
        temp_out = tmp_path / f"roundtrip_{case.case_id}.json"
        case.to_file(temp_out)
        reloaded = EvalCase.from_file(temp_out)
        assert reloaded.case_id == case.case_id
        assert reloaded.category == case.category
        assert reloaded.expected_review == case.expected_review
        assert reloaded.expected_gate == case.expected_gate

    assert found_ids == expected_ids, f"Fixture case_ids mismatch: {found_ids} vs {expected_ids}"


def test_mock_mcp_server_initialize():
    """Verifies MockGitHubMcpServer handles initialize request correctly."""
    fixture_path = str(Path(_eval_dir) / "cases" / "tc01_clean_code.json")
    server = MockGitHubMcpServer(fixture_path)

    res = server.handle_initialize(request_id=42, params={})
    assert res["jsonrpc"] == "2.0"
    assert res["id"] == 42
    assert "capabilities" in res["result"]
    assert res["result"]["serverInfo"]["name"] == "mock-github-mcp"
    assert res["result"]["serverInfo"]["version"] == "1.0.0"


def test_mock_mcp_server_tools_list():
    """Verifies tools/list exposes get_file_contents and list_pull_request_files."""
    fixture_path = str(Path(_eval_dir) / "cases" / "tc01_clean_code.json")
    server = MockGitHubMcpServer(fixture_path)

    res = server.handle_tools_list(request_id=10)
    assert res["id"] == 10
    tool_names = [t["name"] for t in res["result"]["tools"]]
    assert "list_pull_request_files" in tool_names
    assert "get_file_contents" in tool_names


def test_mock_mcp_server_tools_call():
    """Verifies tools/call executes get_file_contents and list_pull_request_files."""
    fixture_path = str(Path(_eval_dir) / "cases" / "tc01_clean_code.json")
    server = MockGitHubMcpServer(fixture_path)

    # 1. list_pull_request_files
    res_list = server.handle_tools_call(1, "list_pull_request_files", {})
    assert res_list["id"] == 1
    files_data = json.loads(res_list["result"]["content"][0]["text"])
    filenames = [f["filename"] for f in files_data]
    assert "web_ui/views.py" in filenames
    assert "web_ui/tests.py" in filenames

    # 2. get_file_contents (existing)
    res_get = server.handle_tools_call(2, "get_file_contents", {"path": "web_ui/views.py"})
    assert res_get["id"] == 2
    assert "def health_check" in res_get["result"]["content"][0]["text"]

    # 3. get_file_contents (nonexistent)
    res_empty = server.handle_tools_call(3, "get_file_contents", {"path": "nonexistent.py"})
    assert res_empty["result"]["content"][0]["text"] == ""

    # 4. Unknown tool
    res_err = server.handle_tools_call(4, "unknown_tool", {})
    assert "error" in res_err
    assert res_err["error"]["code"] == -32601


def test_mock_mcp_server_notifications_and_dispatch():
    """Verifies notification requests emit no response and ping responds with empty dict."""
    fixture_path = str(Path(_eval_dir) / "cases" / "tc01_clean_code.json")
    server = MockGitHubMcpServer(fixture_path)

    # Notification has no id
    notify_resp = server.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert notify_resp is None

    # Ping with id returns result
    ping_resp = server.handle_request({"jsonrpc": "2.0", "id": 99, "method": "ping"})
    assert ping_resp == {"jsonrpc": "2.0", "id": 99, "result": {}}

    # Unknown method returns error
    unk_resp = server.handle_request({"jsonrpc": "2.0", "id": 100, "method": "unknown_method"})
    assert unk_resp["error"]["code"] == -32601


def test_mock_mcp_server_stdio_process():
    """Launches Mock MCP Server in a separate subprocess and exercises stdio pipe protocol."""
    fixture_path = str(Path(_eval_dir) / "cases" / "tc02_secret_leak.json")
    server_script = str(Path(_eval_dir) / "mock_mcp_server.py")

    proc = subprocess.Popen(
        [sys.executable, server_script, "--fixture", fixture_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Request 1: initialize
        req1 = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        proc.stdin.write(json.dumps(req1) + "\n")
        proc.stdin.flush()
        line1 = proc.stdout.readline()
        r1 = json.loads(line1)
        assert r1["id"] == 1
        assert r1["result"]["serverInfo"]["name"] == "mock-github-mcp"

        # Request 2: tools/call list_pull_request_files
        req2 = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "list_pull_request_files", "arguments": {}},
        }
        proc.stdin.write(json.dumps(req2) + "\n")
        proc.stdin.flush()
        line2 = proc.stdout.readline()
        r2 = json.loads(line2)
        assert r2["id"] == 2
        files_data = json.loads(r2["result"]["content"][0]["text"])
        assert any(f["filename"] == "web_ui/settings.py" for f in files_data)

    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=2)


def test_create_mock_github_mcp_server_factory():
    """Tests create_mock_github_mcp_server factory function."""
    fixture_path = str(Path(_eval_dir) / "cases" / "tc03_sql_injection.json")
    server = create_mock_github_mcp_server(fixture_path)
    assert server.name == "github"
    assert server.command == sys.executable
    assert "--fixture" in server.args
    assert fixture_path in server.args

    # Check alias
    server2 = create_mock_mcp_config(fixture_path)
    assert server2.name == "github"
