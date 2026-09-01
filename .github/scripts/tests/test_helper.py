"""Unit Tests for Shared CI/CD Agent Helper Module (.github/scripts/helper.py).

Cites Decisions from docs/spec.md (D-1, D-4, D-5, D-6, D-7, D-8, D-10).
"""

import os
import sys
import json
import urllib.request
import urllib.error
from unittest.mock import MagicMock, patch, AsyncMock
from enum import Enum
from typing import Optional
import pytest
from pydantic import BaseModel, Field

# Ensure .github/scripts is importable
_scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import helper


# Sample Test Models
class MockFindingSeverity(str, Enum):
    BLOCKER = "BLOCKER"
    WARNING = "WARNING"
    INFO = "INFO"


class MockInlineFinding(BaseModel):
    file_path: str
    line_number: Optional[int] = None
    severity: MockFindingSeverity = MockFindingSeverity.INFO
    title: str
    details: str
    suggestion: str = ""
    pii_leak: bool = False


class MockReviewStatus(str, Enum):
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    COMMENT = "COMMENT"


class MockPRReviewReport(BaseModel):
    overall_status: MockReviewStatus
    summary: str
    findings: list[MockInlineFinding] = Field(default_factory=list)


class MockSeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MockViolationCategory(str, Enum):
    PII_LEAK = "PII_LEAK"
    SECURITY_VULNERABILITY = "SECURITY_VULNERABILITY"


class MockFailureDetail(BaseModel):
    category: MockViolationCategory
    component: str
    severity: MockSeverityLevel
    reason: str
    remediation: str


class MockQualityGateDecision(BaseModel):
    passed: bool
    summary: str
    failures: list[MockFailureDetail] = Field(default_factory=list)


# =====================================================================
# Tests: sanitize_and_validate_repo & _sanitize_and_validate_repo (D-10)
# =====================================================================

def test_sanitize_and_validate_repo_valid():
    """Sanitizes repo string with spaces, quotes, and .git extensions."""
    assert helper.sanitize_and_validate_repo("owner/repo") == ("owner", "repo")
    assert helper.sanitize_and_validate_repo("  owner/repo.git  ") == ("owner", "repo")
    assert helper.sanitize_and_validate_repo("'owner/repo'") == ("owner", "repo")
    assert helper.sanitize_and_validate_repo('"owner/repo.git"') == ("owner", "repo")


def test_sanitize_and_validate_repo_invalid():
    """Returns None for invalid repository formats."""
    assert helper.sanitize_and_validate_repo("") is None
    assert helper.sanitize_and_validate_repo("invalid-repo") is None
    assert helper.sanitize_and_validate_repo("a/b/c") is None
    assert helper.sanitize_and_validate_repo("   ") is None


# =====================================================================
# Tests: resolve_env_config (D-4)
# =====================================================================

def test_resolve_env_config_cli_priority(monkeypatch):
    """Explicit parameters take precedence over environment variables."""
    monkeypatch.setenv("PULL_REQUEST_NUMBER", "99")
    monkeypatch.setenv("GITHUB_REPOSITORY", "env/repo")
    monkeypatch.setenv("GH_TOKEN", "env-token")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "env-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-east1")
    monkeypatch.setenv("LLM_Model", "gemini-env")

    config = helper.resolve_env_config(
        pr_number="123",
        repo="cli/repo",
        token="cli-token",
        project_id="cli-project",
        location="us-west1",
        model="gemini-cli",
    )

    assert config["pr_number"] == "123"
    assert config["repo"] == "cli/repo"
    assert config["token"] == "cli-token"
    assert config["project_id"] == "cli-project"
    assert config["location"] == "us-west1"
    assert config["model"] == "gemini-cli"


def test_resolve_env_config_fallback_defaults(monkeypatch):
    """Falls back to default values when env vars and args are unset."""
    for key in ["PULL_REQUEST_NUMBER", "PR_NUMBER", "GITHUB_REPOSITORY", "REPOSITORY",
                "GH_TOKEN", "GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN",
                "GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "GOOGLE_CLOUD_LOCATION",
                "LLM_Model", "LLM_MODEL"]:
        monkeypatch.delenv(key, raising=False)

    config = helper.resolve_env_config()
    assert config["pr_number"] is None
    assert config["repo"] is None
    assert config["token"] is None
    assert config["project_id"] == "local-project"
    assert config["location"] == "us-central1"
    assert config["model"] == "gemini-3.7-flash"


# =====================================================================
# Tests: fetch_pr_modified_lines
# =====================================================================

def test_fetch_pr_modified_lines_empty_token():
    """Returns empty dict when token is missing or whitespace."""
    assert helper.fetch_pr_modified_lines("owner", "repo", 42, "") == {}
    assert helper.fetch_pr_modified_lines("owner", "repo", 42, "   ") == {}


def test_fetch_pr_modified_lines_success():
    """Parses modified lines within diff hunks correctly."""
    mock_files = json.dumps([
        {
            "filename": "app/main.py",
            "patch": "@@ -1,3 +1,4 @@\n import os\n+import sys\n def run():",
        },
        {
            "filename": "empty.py",
            "patch": "",
        }
    ]).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = mock_files
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        diff_map = helper.fetch_pr_modified_lines("owner", "repo", 42, "token")

    assert "app/main.py" in diff_map
    assert 2 in diff_map["app/main.py"]
    assert "empty.py" not in diff_map


def test_fetch_pr_modified_lines_network_error(capsys):
    """Handles network errors gracefully and logs warning."""
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Network down")):
        result = helper.fetch_pr_modified_lines("owner", "repo", 42, "token")
        assert result == {}
    captured = capsys.readouterr()
    assert "[Warning] Could not fetch PR diff hunks" in captured.out


# =====================================================================
# Tests: fetch_pr_comments (D-1)
# =====================================================================

def test_fetch_pr_comments_empty_token():
    """Returns empty list when token is empty or whitespace."""
    assert helper.fetch_pr_comments("owner", "repo", 42, "") == []
    assert helper.fetch_pr_comments("owner", "repo", 42, "   ") == []


def test_fetch_pr_comments_success():
    """Fetches comments and parses JSON list."""
    mock_data = json.dumps([{"id": 10, "path": "test.py", "line": 5, "body": "comment"}]).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = mock_data
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        comments = helper.fetch_pr_comments("owner", "repo", 42, "token")

    assert len(comments) == 1
    assert comments[0]["id"] == 10


def test_fetch_pr_comments_error(capsys):
    """Gracefully falls back to empty list on error."""
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Timeout")):
        comments = helper.fetch_pr_comments("owner", "repo", 42, "token")
        assert comments == []
    captured = capsys.readouterr()
    assert "[Warning] Could not fetch existing PR comments" in captured.out


# =====================================================================
# Tests: is_duplicate_comment & _is_duplicate_comment (D-10)
# =====================================================================

def test_is_duplicate_comment_matching():
    """Matches duplicates based on path, line, and title."""
    finding = MockInlineFinding(
        file_path="src/app.py",
        line_number=15,
        severity=MockFindingSeverity.BLOCKER,
        title="Uncaught Exception",
        details="May raise error",
    )
    comments = [
        {"path": "src/app.py", "line": 15, "body": "**[BLOCKER] Uncaught Exception**\nDetails"},
    ]
    assert helper.is_duplicate_comment(finding, comments) is True


def test_is_duplicate_comment_no_match():
    """Returns False when line or path differs."""
    finding = MockInlineFinding(
        file_path="src/app.py",
        line_number=15,
        severity=MockFindingSeverity.BLOCKER,
        title="Uncaught Exception",
        details="May raise error",
    )
    comments = [
        {"path": "src/app.py", "line": 20, "body": "**[BLOCKER] Uncaught Exception**"},
        {"path": "src/other.py", "line": 15, "body": "**[BLOCKER] Uncaught Exception**"},
    ]
    assert helper.is_duplicate_comment(finding, comments) is False


# =====================================================================
# Tests: validate_and_sanitize_findings
# =====================================================================

def test_validate_and_sanitize_findings_split():
    """Splits findings into valid inline diff hunk findings vs out-of-hunk findings."""
    f1 = MockInlineFinding(file_path="main.py", line_number=10, title="In diff", details="")
    f2 = MockInlineFinding(file_path="main.py", line_number=99, title="Out of hunk", details="")
    f3 = MockInlineFinding(file_path="other.py", line_number=5, title="File not in diff", details="")
    f4 = MockInlineFinding(file_path="main.py", line_number=None, title="No line", details="")

    diff_map = {"main.py": [10, 11, 12]}
    valid, out_of_hunk = helper.validate_and_sanitize_findings([f1, f2, f3, f4], diff_map)

    assert len(valid) == 1
    assert valid[0].title == "In diff"
    assert len(out_of_hunk) == 3


# =====================================================================
# Tests: send_github_review_sync & send_github_issue_comment_sync
# =====================================================================

def test_send_github_review_sync():
    """Sends POST request to review API and returns status & body."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"id": 123}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        status, body = helper.send_github_review_sync("owner", "repo", 42, "token", {"event": "APPROVE"})
        assert status == 200
        assert "123" in body


def test_send_github_issue_comment_sync():
    """Sends POST request to issue comments API and returns status & body."""
    mock_resp = MagicMock()
    mock_resp.status = 201
    mock_resp.read.return_value = b'{"id": 456}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        status, body = helper.send_github_issue_comment_sync("owner", "repo", 42, "token", "Comment body")
        assert status == 201
        assert "456" in body


# =====================================================================
# Tests: post_github_pr_review
# =====================================================================

@pytest.mark.asyncio
async def test_post_github_pr_review_clean_approve():
    """Clean PR submits APPROVE review."""
    report = MockPRReviewReport(
        overall_status=MockReviewStatus.APPROVE,
        summary="Clean PR",
        findings=[],
    )
    with patch("helper.send_github_review_sync", return_value=(200, '{"id": 1}')) as mock_send:
        result = await helper.post_github_pr_review(report, "42", "owner/repo", "token")
        assert result is True
        mock_send.assert_called_once()
        payload = mock_send.call_args[0][4]
        assert payload["event"] == "COMMENT"
        assert payload["comments"] == []


@pytest.mark.asyncio
async def test_post_github_pr_review_422_fallback():
    """HTTP 422 triggers fallback to issue comment."""
    f1 = MockInlineFinding(file_path="main.py", line_number=10, title="Finding", details="details")
    report = MockPRReviewReport(
        overall_status=MockReviewStatus.REQUEST_CHANGES,
        summary="Issues found",
        findings=[f1],
    )
    diff_map = {"main.py": [10]}

    with patch("helper.send_github_review_sync", side_effect=[
        (422, "Unprocessable Entity"),
        (200, '{"id": 2}')
    ]), patch("helper.send_github_issue_comment_sync", return_value=(201, '{"id": 3}')):
        result = await helper.post_github_pr_review(report, "42", "owner/repo", "token", modified_files_diff=diff_map)
        assert result is True


# =====================================================================
# Tests: format_pr_review_text & format_text_decision
# =====================================================================

def test_format_pr_review_text():
    """Formats PR review report into text."""
    f1 = MockInlineFinding(file_path="a.py", line_number=1, title="T1", details="D1")
    report = MockPRReviewReport(
        overall_status=MockReviewStatus.REQUEST_CHANGES,
        summary="Summary text",
        findings=[f1],
    )
    text = helper.format_pr_review_text(report)
    assert "### Status: REQUEST_CHANGES" in text
    assert "Summary text" in text
    assert "1. [INFO] a.py:1 - T1" in text


def test_format_text_decision_pass_and_fail():
    """Formats QualityGateDecision into GATE_PASSED or GATE_FAILED text."""
    pass_decision = MockQualityGateDecision(passed=True, summary="All good", failures=[])
    pass_text = helper.format_text_decision(pass_decision)
    assert pass_text.startswith("GATE_PASSED\n\n")

    fail_detail = MockFailureDetail(
        category=MockViolationCategory.PII_LEAK,
        component="file.txt",
        severity=MockSeverityLevel.CRITICAL,
        reason="Found secret",
        remediation="Remove secret",
    )
    fail_decision = MockQualityGateDecision(passed=False, summary="Violations", failures=[fail_detail])
    fail_text = helper.format_text_decision(fail_decision)
    assert fail_text.startswith("GATE_FAILED\n\n")
    assert "[CRITICAL] PII_LEAK in file.txt" in fail_text


# =====================================================================
# Tests: write_json_and_text_reports, write_pr_reports, write_gate_reports (D-5)
# =====================================================================

def test_write_reports(tmp_path, monkeypatch):
    """Writes JSON and text report artifacts to disk."""
    monkeypatch.chdir(tmp_path)
    report = MockPRReviewReport(
        overall_status=MockReviewStatus.APPROVE,
        summary="Clean",
        findings=[],
    )
    helper.write_pr_reports(report)
    assert os.path.exists("reports/pr-review.json")
    assert os.path.exists("reports/pr-review.txt")

    decision = MockQualityGateDecision(
        passed=True,
        summary="Pass",
        failures=[],
    )
    helper.write_gate_reports(decision)
    assert os.path.exists("reports/gate-decision.json")
    assert os.path.exists("reports/decision.txt")


# =====================================================================
# Tests: parse_agent_structured_output (D-7)
# =====================================================================

def test_parse_agent_structured_output_from_model():
    """Returns model instance directly if already parsed."""
    report = MockPRReviewReport(overall_status=MockReviewStatus.APPROVE, summary="Clean", findings=[])
    parsed = helper.parse_agent_structured_output(report, MockPRReviewReport)
    assert parsed == report


def test_parse_agent_structured_output_from_dict():
    """Coerces dict into target Pydantic model."""
    data = {"overall_status": "APPROVE", "summary": "Clean", "findings": []}
    parsed = helper.parse_agent_structured_output(data, MockPRReviewReport)
    assert parsed.overall_status == MockReviewStatus.APPROVE


def test_parse_agent_structured_output_from_json_str():
    """Parses JSON string into target Pydantic model."""
    data_str = '{"overall_status": "REQUEST_CHANGES", "summary": "Issues", "findings": []}'
    parsed = helper.parse_agent_structured_output(data_str, MockPRReviewReport)
    assert parsed.overall_status == MockReviewStatus.REQUEST_CHANGES


# =====================================================================
# Tests: read_text_file & ensure_directory
# =====================================================================

def test_read_text_file(tmp_path):
    """Safely reads file if existing or returns default."""
    test_file = tmp_path / "test.txt"
    assert helper.read_text_file(str(test_file), default="default") == "default"
    test_file.write_text("hello world", encoding="utf-8")
    assert helper.read_text_file(str(test_file)) == "hello world"
    
def test_ensure_directory(tmp_path):
    """Ensures directory exists and returns path."""
    target_dir = tmp_path / "sub" / "dir"
    res = helper.ensure_directory(str(target_dir))
    assert os.path.exists(res)
