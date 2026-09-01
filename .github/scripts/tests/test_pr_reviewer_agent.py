"""Acceptance and Contract Tests for PR Reviewer Agent.

Cites Decisions from docs/spec.md (D-1, D-2, D-3, D-4, D-5, D-6, D-7, D-8, D-9, D-10, D-11, D-12).
"""

import os
import sys
import json
import asyncio
import urllib.request
import urllib.error
import pytest
from io import BytesIO
from unittest.mock import AsyncMock, patch, MagicMock
from pydantic import ValidationError

# Ensure .github/scripts is on sys.path for direct module import
_scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import pr_reviewer_agent
from pr_reviewer_agent import (
    PRFindingSeverity,
    ReviewSeverity,
    ReviewStatus,
    InlineFinding,
    PRReviewReport,
    POSITIVE_APPROVAL_TEMPLATE,
    sanitize_and_validate_repo,
    send_github_review_sync,
    post_github_pr_review,
    validate_and_sanitize_findings,
    format_pr_review_text,
    run_pr_review,
    fetch_pr_modified_lines,
    fetch_pr_comments,
    is_duplicate_comment,
)


def test_pr_finding_severity_alias_compatibility():
    """Validates that ReviewSeverity is an alias of PRFindingSeverity (Decision D-4)."""
    assert ReviewSeverity is PRFindingSeverity  # D-4
    assert PRFindingSeverity.BLOCKER.value == "BLOCKER"  # D-4
    assert PRFindingSeverity.WARNING.value == "WARNING"  # D-4
    assert PRFindingSeverity.SUGGESTION.value == "SUGGESTION"  # D-4
    assert PRFindingSeverity.INFO.value == "INFO"  # D-4


def test_review_status_enum_values():
    """Validates that ReviewStatus enum contains expected values (Decision D-4)."""
    assert ReviewStatus.APPROVE.value == "APPROVE"  # D-4
    assert ReviewStatus.REQUEST_CHANGES.value == "REQUEST_CHANGES"  # D-4
    assert ReviewStatus.COMMENT.value == "COMMENT"  # D-4


def test_inline_finding_schema_and_defaults():
    """Validates InlineFinding instantiation and default field values (Decision D-4)."""
    finding = InlineFinding(
        file_path="scorer/usage.py",  # D-4
        line_number=15,  # D-4
        severity=PRFindingSeverity.WARNING,  # D-4
        title="Missing type annotation",  # D-4
        details="Function parameter lacks type hint.",  # D-4
    )
    assert finding.file_path == "scorer/usage.py"  # D-4
    assert finding.line_number == 15  # D-4
    assert finding.severity == PRFindingSeverity.WARNING  # D-4
    assert finding.suggestion == ""  # D-4: default empty string
    assert finding.pii_leak is False  # D-4: default False


def test_pr_review_report_schema_approve():
    """Validates PRReviewReport with APPROVE status (Decision D-4)."""
    report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,  # D-4
        summary="Code looks clean, well-tested, and adheres to standards.",  # D-4
        findings=[],  # D-4
    )
    assert report.overall_status == ReviewStatus.APPROVE  # D-4
    assert len(report.findings) == 0  # D-4


def test_pr_review_report_schema_request_changes():
    """Validates PRReviewReport with REQUEST_CHANGES status and structured findings (Decision D-4)."""
    finding = InlineFinding(
        file_path="scorer/usage.py",  # D-4
        line_number=42,  # D-4
        severity=PRFindingSeverity.BLOCKER,  # D-4
        title="Uncaught ZeroDivisionError",  # D-4
        details="Division by zero occurs when active_months is 0.",  # D-4
        suggestion="Add guard condition: if active_months == 0: return 0.0",  # D-4
        pii_leak=False,  # D-4
    )
    report = PRReviewReport(
        overall_status=ReviewStatus.REQUEST_CHANGES,  # D-4
        summary="Blocking errors detected requiring remediation.",  # D-4
        findings=[finding],  # D-4
    )
    assert report.overall_status == ReviewStatus.REQUEST_CHANGES  # D-4
    assert len(report.findings) == 1  # D-4
    assert report.findings[0].severity == PRFindingSeverity.BLOCKER  # D-4


def test_pr_review_report_invariant_blocker_enforces_request_changes():
    """Invariant: if any finding has BLOCKER severity, overall_status is coerced to REQUEST_CHANGES (Decision D-4)."""
    finding = InlineFinding(
        file_path="scorer/usage.py",
        line_number=10,
        severity=PRFindingSeverity.BLOCKER,  # D-4
        title="Fatal issue",
        details="Critical error.",
    )
    report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,  # D-4: initially passed APPROVE
        summary="Initial review summary",
        findings=[finding],
    )
    assert report.overall_status == ReviewStatus.REQUEST_CHANGES  # D-4: enforced


def test_pr_review_report_invariant_pii_leak_enforces_request_changes():
    """Invariant: if any finding has pii_leak=True, overall_status is coerced to REQUEST_CHANGES (Decision D-4)."""
    finding = InlineFinding(
        file_path="config/keys.py",
        line_number=1,
        severity=PRFindingSeverity.WARNING,
        title="Key leak",
        details="Secret exposed.",
        pii_leak=True,  # D-4
    )
    report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,  # D-4: initially passed APPROVE
        summary="Initial review summary",
        findings=[finding],
    )
    assert report.overall_status == ReviewStatus.REQUEST_CHANGES  # D-4: enforced


def test_validate_and_sanitize_findings_separates_inline_and_general():
    """Separates findings with valid diff line coordinates from invalid/out-of-hunk ones (Decision D-3, D-12)."""
    diff_hunks = {
        "scorer/usage.py": [10, 11, 12, 40, 41, 42],  # D-12
        "scripts/ci/agent.py": [1, 2, 3],  # D-12
    }

    valid_inline = InlineFinding(
        file_path="scorer/usage.py",  # D-12
        line_number=42,  # D-12: Line exists in diff hunks
        severity=PRFindingSeverity.WARNING,
        title="Type annotation warning",
        details="Missing return type annotation.",
        suggestion="def score() -> int:",
    )

    out_of_hunk_line = InlineFinding(
        file_path="scorer/usage.py",  # D-12
        line_number=999,  # D-12: Line does NOT exist in diff hunks
        severity=PRFindingSeverity.INFO,
        title="General observation",
        details="Consider refactoring helper function.",
        suggestion="",
    )

    unmodified_file = InlineFinding(
        file_path="README.md",  # D-12: File not in diff
        line_number=5,
        severity=PRFindingSeverity.SUGGESTION,
        title="Typo in documentation",
        details="Typo on line 5.",
        suggestion="",
    )

    none_line_finding = InlineFinding(
        file_path="scorer/usage.py",  # D-12
        line_number=None,  # D-12: No specific line
        severity=PRFindingSeverity.SUGGESTION,
        title="File-level architecture suggestion",
        details="Split module into two files.",
        suggestion="",
    )

    inline_findings, general_findings = validate_and_sanitize_findings(
        findings=[valid_inline, out_of_hunk_line, unmodified_file, none_line_finding],
        modified_files_diff=diff_hunks,
    )

    assert len(inline_findings) == 1  # D-12: Only valid_inline meets coordinates
    assert inline_findings[0].title == "Type annotation warning"  # D-12
    assert len(general_findings) == 3  # D-12: Fallback to top-level review comment body
    assert any(f.title == "General observation" for f in general_findings)  # D-12
    assert any(f.title == "Typo in documentation" for f in general_findings)  # D-12
    assert any(f.title == "File-level architecture suggestion" for f in general_findings)  # D-12


def test_format_pr_review_text():
    """Validates formatted markdown representation of PRReviewReport (Decision D-6, D-7)."""
    finding = InlineFinding(
        file_path="auth.py",  # D-6
        line_number=18,  # D-6
        severity=PRFindingSeverity.BLOCKER,  # D-6
        title="Exposed API secret key",  # D-6
        details="Hardcoded credential found.",  # D-6
        suggestion="os.environ['API_KEY']",  # D-6
        pii_leak=True,  # D-4, D-6
    )
    report = PRReviewReport(
        overall_status=ReviewStatus.REQUEST_CHANGES,  # D-4, D-6
        summary="Security blocker detected in auth.py.",  # D-6
        findings=[finding],  # D-6
    )
    text = format_pr_review_text(report)  # D-6
    assert "### Status: REQUEST_CHANGES" in text  # D-6
    assert "Security blocker detected in auth.py." in text  # D-6
    assert "[BLOCKER] auth.py:18 - Exposed API secret key" in text  # D-6
    assert "Suggestion: os.environ['API_KEY']" in text  # D-6


def test_post_github_pr_review_async_signature():
    """Validates that post_github_pr_review is an async coroutine function (Decision D-10, Scenario 8)."""
    assert asyncio.iscoroutinefunction(post_github_pr_review)  # D-10


@pytest.mark.asyncio
async def test_run_pr_review_non_pr_event_early_exit():
    """When pr_number is None or empty, run_pr_review skips execution and returns None with exit 0 (Decision D-4, Scenario 3)."""
    result = await run_pr_review(
        pr_number=None,  # D-4
        repo="owner/repo",
        token="mock-token",
    )
    assert result is None  # D-4


@pytest.mark.asyncio
async def test_run_pr_review_mock_agent_approve(tmp_path, monkeypatch):
    """Scenario: Mocked Antigravity Agent returns clean APPROVE PR review and calls review posting."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    pii_scan = reports_dir / "pii-scan.txt"
    pii_scan.write_text("No findings", encoding="utf-8")

    expected_report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="All PR changes look clean and well-structured.",
        findings=[],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_report)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    with patch.object(pr_reviewer_agent, "Agent", return_value=mock_agent_instance), \
         patch.object(pr_reviewer_agent, "post_github_pr_review", new_callable=AsyncMock) as mock_post_review:
        mock_post_review.return_value = True
        report = await run_pr_review(
            pr_number="123",  # D-5
            repo="owner/repo",
            token="ghp_testtoken",
            pii_report_path=str(pii_scan),
            project_id="test-project",
            location="us-central1",
        )

    assert report is not None  # D-5
    assert report.overall_status == ReviewStatus.APPROVE  # D-4
    assert os.path.exists("reports/pr-review.json")  # D-6, D-7
    assert os.path.exists("reports/pr-review.txt")  # D-6, D-7
    with open("reports/pr-review.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["overall_status"] == "APPROVE"  # D-4, D-6


@pytest.mark.asyncio
async def test_run_pr_review_mock_agent_config_and_telemetry(tmp_path, monkeypatch):
    """Validates LocalAgentConfig parameters, MCP server setup, and telemetry dir."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    expected_report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="PR approved.",
        findings=[],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_report)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    with patch.object(pr_reviewer_agent, "Agent", return_value=mock_agent_instance) as mock_agent_cls, \
         patch.object(pr_reviewer_agent, "post_github_pr_review", new_callable=AsyncMock) as mock_post_review:
        mock_post_review.return_value = True
        await run_pr_review(
            pr_number="99",
            repo="my-org/my-repo",
            token="test-token",
            pii_report_path=str(reports_dir / "pii-scan.txt"),
            project_id="test-proj",
            location="us-central1",
        )

        mock_agent_cls.assert_called_once()
        captured_config = mock_agent_cls.call_args[0][0]

    assert captured_config is not None
    assert captured_config.model == "gemini-3.7-flash"  # D-2
    assert captured_config.vertex is True  # D-2
    assert captured_config.project == "test-proj"  # D-2
    assert len(captured_config.mcp_servers) == 1  # D-11
    mcp = captured_config.mcp_servers[0]
    assert mcp.command == "docker"  # D-11
    assert "ghcr.io/github/github-mcp-server:v0.27.0" in mcp.args  # D-11
    assert os.path.isdir("reports/telemetry/pr_review_agent")  # D-10


@pytest.mark.asyncio
async def test_run_pr_review_streams_thinking_and_output(tmp_path, monkeypatch, capsys):
    """Scenario: Validates streaming of Thought, ToolCall, ToolResult, and Text chunks."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    expected_report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="PR approved with streaming logs.",
        findings=[],
    )

    from google.antigravity import types

    async def mock_chunks_gen():
        yield types.Thought(step_index=0, text="Deep thinking about PR #42 security posture...")
        yield types.ToolCall(name="get_pull_request", args={"pr": 42})
        yield types.ToolResult(name="get_pull_request", result={"title": "Fix bug"})
        yield types.Text(step_index=0, text="PR analysis complete.")

    mock_response = MagicMock()
    mock_response.chunks = mock_chunks_gen()
    mock_response.structured_output = AsyncMock(return_value=expected_report)

    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    with patch.object(pr_reviewer_agent, "Agent", return_value=mock_agent_instance), \
         patch.object(pr_reviewer_agent, "post_github_pr_review", new_callable=AsyncMock) as mock_post_review:
        mock_post_review.return_value = True
        report = await run_pr_review(
            pr_number="42",
            repo="owner/repo",
            token="ghp_token",
            pii_report_path=str(reports_dir / "pii-scan.txt"),
            project_id="test-proj",
            location="us-central1",
        )

    assert report is not None
    assert report.overall_status == ReviewStatus.APPROVE
    captured = capsys.readouterr()
    assert "Deep thinking about PR #42 security posture..." in captured.out
    assert "get_pull_request" in captured.out
    assert "Structured LLM Output" in captured.out


# --- Task 1.A New Unit & Contract Tests ---

@pytest.mark.asyncio
async def test_post_github_pr_review_positive_approval_clean_pr():
    """Decision D-1, Scenario 1: Clean PR with APPROVE status posts canonical positive template with empty comments."""
    report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="Clean PR without issues.",
        findings=[],
    )
    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"id": 1, "state": "APPROVED"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        result = await post_github_pr_review(
            report=report,
            pr_number="42",
            repo="owner/repo",
            token="mock-token",
        )

    assert result is True  # D-1
    assert len(captured_requests) == 1  # D-1
    req = captured_requests[0]
    assert req.full_url == "https://api.github.com/repos/owner/repo/pulls/42/reviews"  # D-1
    assert req.headers["Authorization"] == "Bearer mock-token"  # D-1
    assert req.headers["Accept"] == "application/vnd.github+json"  # D-1
    assert req.headers.get("User-agent") == "automated-pr-reviewer/1.0" or req.headers.get("User-Agent") == "automated-pr-reviewer/1.0"  # D-1
    assert req.headers.get("X-github-api-version") == "2022-11-28" or req.headers.get("X-GitHub-Api-Version") == "2022-11-28"  # D-1

    payload = json.loads(req.data.decode("utf-8"))
    assert payload["event"] == "COMMENT"  # D-1: Always uses COMMENT event to support self-reviews & third-party PRs
    assert payload["comments"] == []  # D-1
    expected_positive_body = (
        f"{POSITIVE_APPROVAL_TEMPLATE}\n\n"
        "### Summary & Implementation Highlights:\n"
        "Clean PR without issues."
    )
    assert payload["body"] == expected_positive_body  # D-1


@pytest.mark.asyncio
async def test_post_github_pr_review_zero_findings_non_approve():
    """Decision D-9, Scenario 1b: Zero findings with COMMENT or REQUEST_CHANGES submits summary without positive template."""
    report_comment = PRReviewReport(
        overall_status=ReviewStatus.COMMENT,
        summary="General questions on PR design.",
        findings=[],
    )
    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"id": 2, "state": "COMMENTED"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        result = await post_github_pr_review(
            report=report_comment,
            pr_number=101,
            repo="owner/repo",
            token="mock-token",
        )

    assert result is True  # D-9
    assert len(captured_requests) == 1  # D-9
    payload = json.loads(captured_requests[0].data.decode("utf-8"))
    assert payload["event"] == "COMMENT"  # D-9
    assert payload["comments"] == []  # D-9
    assert payload["body"] == "General questions on PR design."  # D-9
    assert "Great job!" not in payload["body"]  # D-9


@pytest.mark.asyncio
async def test_post_github_pr_review_structured_inline_comments():
    """Decisions D-2, D-3, Scenario 2: Findings on diff lines are formatted as inline comments; others in body."""
    inline_finding = InlineFinding(
        file_path="scorer/usage.py",
        line_number=15,
        severity=PRFindingSeverity.BLOCKER,
        title="Division by zero",
        details="Denominator can be 0.",
        suggestion="if count == 0: return 0",
        pii_leak=False,
    )
    out_of_hunk_finding = InlineFinding(
        file_path="scorer/usage.py",
        line_number=999,
        severity=PRFindingSeverity.WARNING,
        title="Unused import",
        details="Clean up unused import.",
        suggestion="",
        pii_leak=False,
    )
    report = PRReviewReport(
        overall_status=ReviewStatus.REQUEST_CHANGES,
        summary="Found blocking error and out-of-hunk issue.",
        findings=[inline_finding, out_of_hunk_finding],
    )
    diff_hunks = {"scorer/usage.py": [10, 15, 20]}

    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"id": 3, "state": "CHANGES_REQUESTED"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        result = await post_github_pr_review(
            report=report,
            pr_number="55",
            repo="owner/repo",
            token="mock-token",
            modified_files_diff=diff_hunks,
        )

    assert result is True  # D-2
    assert len(captured_requests) == 1  # D-2
    payload = json.loads(captured_requests[0].data.decode("utf-8"))
    assert payload["event"] == "COMMENT"  # D-2: Uses COMMENT event for PR review submission
    assert len(payload["comments"]) == 1  # D-3: Only the in-hunk finding is placed inline
    comment = payload["comments"][0]
    assert comment["path"] == "scorer/usage.py"  # D-3
    assert comment["line"] == 15  # D-3
    assert "**[BLOCKER] Division by zero**" in comment["body"]  # D-3
    assert "```suggestion\nif count == 0: return 0\n```" in comment["body"]  # D-3

    # Check top-level body contains general / out-of-hunk finding
    assert "Status: REQUEST_CHANGES" in payload["body"]  # D-3
    assert "Unused import" in payload["body"]  # D-3


@pytest.mark.asyncio
async def test_run_pr_review_non_pr_skip_no_api_calls(capsys):
    """Decision D-4, Scenario 3: When PR number is unset or empty, skips without network calls."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        result = await run_pr_review(pr_number="", repo="owner/repo", token="mock-token")
        assert result is None  # D-4
        mock_urlopen.assert_not_called()  # D-4

    captured = capsys.readouterr()
    assert "No pull request number provided; skipping PR review." in captured.out  # D-4


@pytest.mark.asyncio
async def test_post_github_pr_review_network_error_resilience(capsys):
    """Decision D-5, Scenario 4: Network connection errors and timeouts log warnings without raising exceptions."""
    report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="Clean PR.",
        findings=[],
    )

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        result = await post_github_pr_review(
            report=report,
            pr_number="42",
            repo="owner/repo",
            token="mock-token",
        )

    assert result is False  # D-5: Non-fatal failure
    captured = capsys.readouterr()
    assert "[Warning] Failed to post PR review to GitHub" in captured.out  # D-5


@pytest.mark.asyncio
async def test_post_github_pr_review_auth_error_resilience(capsys):
    """Decision D-5, Scenario 4: HTTP 401/403 authorization errors log warnings and return False."""
    report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="Clean PR.",
        findings=[],
    )
    http_err = urllib.error.HTTPError(
        url="https://api.github.com/repos/owner/repo/pulls/42/reviews",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=BytesIO(b'{"message": "Bad credentials"}'),
    )

    with patch("urllib.request.urlopen", side_effect=http_err):
        result = await post_github_pr_review(
            report=report,
            pr_number="42",
            repo="owner/repo",
            token="invalid-token",
        )

    assert result is False  # D-5
    captured = capsys.readouterr()
    assert "[Warning] Failed to post PR review to GitHub (HTTP 401" in captured.out  # D-5


@pytest.mark.asyncio
async def test_post_github_pr_review_422_fallback_retry_success(capsys):
    """Decision D-6, Scenario 5: HTTP 422 with inline comments triggers exactly 1 fallback retry with empty comments."""
    inline_finding = InlineFinding(
        file_path="scorer/usage.py",
        line_number=25,
        severity=PRFindingSeverity.WARNING,
        title="Style warning",
        details="Too many lines.",
        suggestion="",
    )
    report = PRReviewReport(
        overall_status=ReviewStatus.COMMENT,
        summary="Review with inline comment that fails placement.",
        findings=[inline_finding],
    )
    diff_hunks = {"scorer/usage.py": [25]}

    captured_requests = []
    first_call = True

    def mock_urlopen(req, timeout=None):
        nonlocal first_call
        captured_requests.append(req)
        if first_call:
            first_call = False
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=422,
                msg="Unprocessable Entity",
                hdrs={},
                fp=BytesIO(b'{"message": "Line not in hunk"}'),
            )
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"id": 4, "state": "COMMENTED"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        result = await post_github_pr_review(
            report=report,
            pr_number="77",
            repo="owner/repo",
            token="mock-token",
            modified_files_diff=diff_hunks,
        )

    assert result is True  # D-6: Fallback succeeded
    assert len(captured_requests) == 2  # D-6: Exactly 1 initial + 1 fallback retry
    # First payload had inline comments
    first_payload = json.loads(captured_requests[0].data.decode("utf-8"))
    assert len(first_payload["comments"]) == 1  # D-6
    # Fallback payload has empty comments and consolidated body
    fallback_payload = json.loads(captured_requests[1].data.decode("utf-8"))
    assert fallback_payload["comments"] == []  # D-6
    assert "Style warning" in fallback_payload["body"]  # D-6

    captured = capsys.readouterr()
    assert "Retrying with consolidated body comments" in captured.out  # D-6
    assert "Successfully posted fallback PR review" in captured.out  # D-6


@pytest.mark.asyncio
async def test_post_github_pr_review_422_no_retry_when_comments_empty(capsys):
    """Decision D-6, Scenario 5: HTTP 422 when comments is already empty does not attempt redundant retry on generic errors."""
    report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="Clean PR.",
        findings=[],
    )
    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        raise urllib.error.HTTPError(
            url=req.full_url,
            code=422,
            msg="Unprocessable Entity",
            hdrs={},
            fp=BytesIO(b'{"message": "Generic unprocessable entity"}'),
        )

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        result = await post_github_pr_review(
            report=report,
            pr_number="10",
            repo="owner/repo",
            token="mock-token",
        )

    assert result is False  # D-6
    assert len(captured_requests) == 1  # D-6: Exactly 1 attempt, no redundant retry
    captured = capsys.readouterr()
    assert "[Warning] GitHub PR review rejected (HTTP 422" in captured.out  # D-6


@pytest.mark.asyncio
async def test_post_github_pr_review_422_self_review_fallback_success(capsys):
    """Decision D-6: When GitHub returns 422 on review API, falls back to issue comments API and succeeds."""
    report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="Clean PR without issues.",
        findings=[],
    )
    captured_requests = []
    first_call = True

    def mock_urlopen(req, timeout=None):
        nonlocal first_call
        captured_requests.append(req)
        if first_call:
            first_call = False
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=422,
                msg="Unprocessable Entity",
                hdrs={},
                fp=BytesIO(b'{"message":"Unprocessable Entity","errors":["Review Can not approve your own pull request"]}'),
            )
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"id": 99, "body": "posted"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        result = await post_github_pr_review(
            report=report,
            pr_number="4",
            repo="owner/repo",
            token="mock-token",
        )

    assert result is True
    assert len(captured_requests) >= 2
    # First request was review API with COMMENT event
    first_payload = json.loads(captured_requests[0].data.decode("utf-8"))
    assert first_payload["event"] == "COMMENT"

    captured = capsys.readouterr()
    assert "PR review rejected due to GitHub self-review restrictions" in captured.out


@pytest.mark.asyncio
async def test_post_github_pr_review_422_fallback_retry_failure(capsys):
    """Decision D-6, Scenario 5: When both initial and retry return HTTP 422, returns False after 2 attempts."""
    inline_finding = InlineFinding(
        file_path="scorer/usage.py",
        line_number=30,
        severity=PRFindingSeverity.WARNING,
        title="Warning",
        details="Details",
    )
    report = PRReviewReport(
        overall_status=ReviewStatus.COMMENT,
        summary="Comment review.",
        findings=[inline_finding],
    )
    diff_hunks = {"scorer/usage.py": [30]}

    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        raise urllib.error.HTTPError(
            url=req.full_url,
            code=422,
            msg="Unprocessable Entity",
            hdrs={},
            fp=BytesIO(b'{"message": "Still unprocessable"}'),
        )

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        result = await post_github_pr_review(
            report=report,
            pr_number="88",
            repo="owner/repo",
            token="mock-token",
            modified_files_diff=diff_hunks,
        )

    assert result is False  # D-6
    assert len(captured_requests) == 2  # D-6: Max 1 retry attempt
    captured = capsys.readouterr()
    assert "[Warning] Fallback PR review submission failed (HTTP 422" in captured.out  # D-6


@pytest.mark.asyncio
async def test_run_pr_review_writes_artifacts_before_posting(tmp_path, monkeypatch):
    """Decision D-7, Scenario 6: Artifacts reports/pr-review.json and .txt are written before network posting."""
    monkeypatch.chdir(tmp_path)

    # Trigger deterministic fallback path with PII finding
    pii_file = tmp_path / "reports" / "pii-scan.txt"
    pii_file.parent.mkdir(parents=True, exist_ok=True)
    pii_file.write_text("Found AUTH_TOKEN leak in config.", encoding="utf-8")

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Network down")):
        report = await run_pr_review(
            pr_number="12",
            repo="owner/repo",
            token="test-token",
            pii_report_path=str(pii_file),
        )

    assert report is not None  # D-7
    assert os.path.exists("reports/pr-review.json")  # D-7
    assert os.path.exists("reports/pr-review.txt")  # D-7
    with open("reports/pr-review.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["overall_status"] == "REQUEST_CHANGES"  # D-7


def test_post_github_pr_review_repo_sanitization():
    """Decision D-8, Scenario 7: Repo strings with whitespace, quotes, and .git suffix are correctly sanitized."""
    assert sanitize_and_validate_repo(" org/repo.git ") == ("org", "repo")  # D-8
    assert sanitize_and_validate_repo("'owner/my-repo'") == ("owner", "my-repo")  # D-8
    assert sanitize_and_validate_repo('"owner/my-repo.git"') == ("owner", "my-repo")  # D-8
    assert sanitize_and_validate_repo("simple-owner/simple-repo") == ("simple-owner", "simple-repo")  # D-8


@pytest.mark.asyncio
async def test_post_github_pr_review_invalid_repo_skips(capsys):
    """Decision D-8, Scenario 7: Invalid repository format logs warning and returns False without network calls."""
    report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="Clean PR.",
        findings=[],
    )
    for invalid_repo in ["invalid-repo-without-slash", "", "a/b/c", "   "]:
        with patch("urllib.request.urlopen") as mock_urlopen:
            result = await post_github_pr_review(
                report=report,
                pr_number="42",
                repo=invalid_repo,
                token="mock-token",
            )
            assert result is False  # D-8
            mock_urlopen.assert_not_called()  # D-8


@pytest.mark.asyncio
async def test_post_github_pr_review_missing_token_skips(capsys):
    """Decision D-5, Scenario 4: Missing token logs warning and returns False without network calls."""
    report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="Clean PR.",
        findings=[],
    )
    with patch("urllib.request.urlopen") as mock_urlopen:
        result = await post_github_pr_review(
            report=report,
            pr_number="42",
            repo="owner/repo",
            token="",
        )
        assert result is False  # D-5
        mock_urlopen.assert_not_called()  # D-5
    captured = capsys.readouterr()
    assert "[Warning] No GitHub token provided; skipping PR review submission." in captured.out  # D-5


def test_fetch_pr_modified_lines_empty_token():
    """Returns empty dict when token is empty or whitespace."""
    assert fetch_pr_modified_lines("owner", "repo", 1, "") == {}
    assert fetch_pr_modified_lines("owner", "repo", 1, "   ") == {}


def test_fetch_pr_modified_lines_success_parses_hunks():
    """Parses modified lines within unified diff hunks correctly."""
    mock_files_json = json.dumps([
        {
            "filename": "scorer/usage.py",
            "patch": "@@ -1,4 +1,5 @@\n import os\n+import csv\n def parse():\n@@ -40,3 +41,4 @@\n x = 1\n+y = 2\n z = 3",
        },
        {
            "filename": "README.md",
            "patch": "@@ -10,3 +10,3 @@\n-old line\n+new line\n context",
        },
        {
            "filename": "deleted.py",
            "patch": "",
        },
    ]).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = mock_files_json
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        diff_map = fetch_pr_modified_lines("owner", "repo", 42, "mock-token")

    assert "scorer/usage.py" in diff_map
    # First hunk: 1 (context), 2 (+import csv), 3 (context)
    # Second hunk: 41 (context), 42 (+y = 2), 43 (context)
    assert 2 in diff_map["scorer/usage.py"]
    assert 42 in diff_map["scorer/usage.py"]

    assert "README.md" in diff_map
    # Hunk: 10 (+new line), 11 (context)
    assert 10 in diff_map["README.md"]
    assert "deleted.py" not in diff_map


def test_fetch_pr_modified_lines_handles_network_error(capsys):
    """Gracefully catches network errors and returns empty dict."""
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Network unreachable")):
        diff_map = fetch_pr_modified_lines("owner", "repo", 42, "mock-token")
    assert diff_map == {}
    captured = capsys.readouterr()
    assert "[Warning] Could not fetch PR diff hunks from GitHub API" in captured.out


@pytest.mark.asyncio
async def test_run_pr_review_model_selection_from_env_var(tmp_path, monkeypatch):
    """Validates that run_pr_review honors LLM_Model environment variable."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_Model", "gemini-2.5-pro")
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    expected_report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="PR approved.",
        findings=[],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_report)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    with patch.object(pr_reviewer_agent, "Agent", return_value=mock_agent_instance) as mock_agent_cls, \
         patch.object(pr_reviewer_agent, "post_github_pr_review", new_callable=AsyncMock) as mock_post_review:
        mock_post_review.return_value = True
        await run_pr_review(
            pr_number="100",
            repo="org/repo",
            token="test-token",
            pii_report_path=str(reports_dir / "pii-scan.txt"),
            project_id="test-proj",
            location="us-central1",
        )

        mock_agent_cls.assert_called_once()
        captured_config = mock_agent_cls.call_args[0][0]

    assert captured_config.model == "gemini-2.5-pro"


@pytest.mark.asyncio
async def test_run_pr_review_model_selection_explicit_arg(tmp_path, monkeypatch):
    """Validates that explicit model argument overrides LLM_Model environment variable."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_Model", "gemini-2.5-pro")
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    expected_report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="PR approved.",
        findings=[],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_report)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    with patch.object(pr_reviewer_agent, "Agent", return_value=mock_agent_instance) as mock_agent_cls, \
         patch.object(pr_reviewer_agent, "post_github_pr_review", new_callable=AsyncMock) as mock_post_review:
        mock_post_review.return_value = True
        await run_pr_review(
            pr_number="100",
            repo="org/repo",
            token="test-token",
            pii_report_path=str(reports_dir / "pii-scan.txt"),
            project_id="test-proj",
            location="us-central1",
            model="gemini-custom-model",
        )

        mock_agent_cls.assert_called_once()
        captured_config = mock_agent_cls.call_args[0][0]

    assert captured_config.model == "gemini-custom-model"


# =====================================================================
# Decision D-1, D-6: Comment Fetching via GitHub REST API (fetch_pr_comments)
# =====================================================================

def test_fetch_pr_comments_empty_token_returns_empty_list():
    """Decision D-1: When token is missing or empty/whitespace, returns empty list without making network calls."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        assert fetch_pr_comments("owner", "repo", 42, "") == []  # D-1
        assert fetch_pr_comments("owner", "repo", 42, "   ") == []  # D-1
        mock_urlopen.assert_not_called()  # D-1


def test_fetch_pr_comments_success_parses_comments():
    """Decision D-1: Fetches existing PR review comments and parses JSON array with expected headers and query param."""
    mock_comments = [
        {
            "id": 1,
            "path": "scorer/usage.py",
            "line": 20,
            "original_line": 20,
            "body": "**[BLOCKER] Division by zero**\n\nFix",
        }
    ]
    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_comments).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        comments = fetch_pr_comments("owner", "repo", 42, "mock-token")

    assert len(comments) == 1  # D-1
    assert comments[0]["path"] == "scorer/usage.py"  # D-1
    assert len(captured_requests) == 1  # D-1
    req = captured_requests[0]
    assert req.full_url == "https://api.github.com/repos/owner/repo/pulls/42/comments?per_page=100"  # D-1
    assert req.headers["Authorization"] == "Bearer mock-token"  # D-1
    assert req.headers["Accept"] == "application/vnd.github+json"  # D-1
    assert req.headers.get("User-agent") == "automated-pr-reviewer/1.0" or req.headers.get("User-Agent") == "automated-pr-reviewer/1.0"  # D-1
    assert req.headers.get("X-github-api-version") == "2022-11-28" or req.headers.get("X-GitHub-Api-Version") == "2022-11-28"  # D-1


def test_fetch_pr_comments_network_error_fallback_empty_list(capsys):
    """Decision D-6: Network error or HTTP error during comment fetch logs a warning and returns empty list gracefully."""
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        comments = fetch_pr_comments("owner", "repo", 42, "mock-token")
        assert comments == []  # D-6

    captured = capsys.readouterr()
    assert "[Warning] Could not fetch existing PR comments from GitHub API" in captured.out  # D-6


# =====================================================================
# Decision D-2: Finding Fingerprint & Duplicate Comment Matching (is_duplicate_comment)
# =====================================================================

def test_is_duplicate_comment_exact_match():
    """Decision D-2: Matches comment on identical file path, line number, and title."""
    finding = InlineFinding(
        file_path="scorer/usage.py",
        line_number=20,
        severity=PRFindingSeverity.BLOCKER,
        title="Division by zero",
        details="Potential zero denominator.",
    )
    existing_comments = [
        {
            "path": "scorer/usage.py",
            "line": 20,
            "original_line": 20,
            "body": "**[BLOCKER] Division by zero**\n\nDetails...",
        }
    ]
    assert is_duplicate_comment(finding, existing_comments) is True  # D-2


def test_is_duplicate_comment_original_line_match():
    """Decision D-2: Matches comment on original_line when active line shifted or is None."""
    finding = InlineFinding(
        file_path="scorer/usage.py",
        line_number=20,
        severity=PRFindingSeverity.BLOCKER,
        title="Division by zero",
        details="Potential zero denominator.",
    )
    existing_comments = [
        {
            "path": "scorer/usage.py",
            "line": None,
            "original_line": 20,
            "body": "**[BLOCKER] Division by zero**",
        }
    ]
    assert is_duplicate_comment(finding, existing_comments) is True  # D-2


def test_is_duplicate_comment_different_line_or_path_returns_false():
    """Decision D-2: Returns False when file path or line number differs."""
    finding = InlineFinding(
        file_path="scorer/usage.py",
        line_number=20,
        severity=PRFindingSeverity.BLOCKER,
        title="Division by zero",
        details="Potential zero denominator.",
    )
    diff_path_comments = [
        {
            "path": "scorer/other.py",
            "line": 20,
            "body": "**[BLOCKER] Division by zero**",
        }
    ]
    diff_line_comments = [
        {
            "path": "scorer/usage.py",
            "line": 99,
            "body": "**[BLOCKER] Division by zero**",
        }
    ]
    assert is_duplicate_comment(finding, diff_path_comments) is False  # D-2
    assert is_duplicate_comment(finding, diff_line_comments) is False  # D-2


def test_is_duplicate_comment_different_title_on_same_line_returns_false():
    """Decision D-2: Returns False when line matches but defect title/type is completely different."""
    finding = InlineFinding(
        file_path="scorer/usage.py",
        line_number=20,
        severity=PRFindingSeverity.BLOCKER,
        title="Division by zero",
        details="Potential zero denominator.",
    )
    other_defect_comments = [
        {
            "path": "scorer/usage.py",
            "line": 20,
            "body": "**[WARNING] Unused import**\n\nUnused os module.",
        }
    ]
    assert is_duplicate_comment(finding, other_defect_comments) is False  # D-2


def test_is_duplicate_comment_case_and_whitespace_insensitivity():
    """Decision D-2: Matches finding title regardless of casing and markdown whitespace variations."""
    finding = InlineFinding(
        file_path="scorer/usage.py",
        line_number=20,
        severity=PRFindingSeverity.BLOCKER,
        title="Division by zero",
        details="Details",
    )
    comments = [
        {
            "path": "scorer/usage.py",
            "line": 20,
            "body": "  **[blocker] division by zero**  \n\nExtra context",
        }
    ]
    assert is_duplicate_comment(finding, comments) is True  # D-2


# =====================================================================
# Decision D-3, D-4, D-5: Deduplicated Review Posting (post_github_pr_review)
# =====================================================================

@pytest.mark.asyncio
async def test_post_github_pr_review_skips_duplicate_inline_comments(capsys):
    """Decision D-3, D-4: Only newly introduced findings are posted inline, while full summary details all findings."""
    f1 = InlineFinding(
        file_path="scorer/usage.py",
        line_number=20,
        severity=PRFindingSeverity.BLOCKER,
        title="Division by zero",
        details="Zero denominator.",
    )
    f2 = InlineFinding(
        file_path="scorer/usage.py",
        line_number=40,
        severity=PRFindingSeverity.WARNING,
        title="Unchecked None",
        details="Variable may be None.",
    )
    report = PRReviewReport(
        overall_status=ReviewStatus.REQUEST_CHANGES,
        summary="Found 2 issues.",
        findings=[f1, f2],
    )
    existing_comments = [
        {
            "path": "scorer/usage.py",
            "line": 20,
            "body": "**[BLOCKER] Division by zero**",
        }
    ]
    diff_hunks = {"scorer/usage.py": [20, 40]}

    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"id": 1, "state": "CHANGES_REQUESTED"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        result = await post_github_pr_review(
            report=report,
            pr_number="42",
            repo="owner/repo",
            token="mock-token",
            modified_files_diff=diff_hunks,
            existing_comments=existing_comments,
        )

    assert result is True  # D-3
    assert len(captured_requests) == 1  # D-3
    payload = json.loads(captured_requests[0].data.decode("utf-8"))
    assert len(payload["comments"]) == 1  # D-3: Only f2 is new
    assert payload["comments"][0]["line"] == 40  # D-3
    assert "Unchecked None" in payload["comments"][0]["body"]  # D-3
    assert "Found 2 issues." in payload["body"]  # D-4
    captured = capsys.readouterr()
    assert "Skipped 1 duplicate inline review comment" in captured.out  # D-3


@pytest.mark.asyncio
async def test_post_github_pr_review_all_duplicates_submits_empty_comments_with_full_summary():
    """Decision D-3, D-4: When all inline findings already exist, submits review with empty comments list and full summary."""
    f1 = InlineFinding(
        file_path="scorer/usage.py",
        line_number=20,
        severity=PRFindingSeverity.BLOCKER,
        title="Division by zero",
        details="Zero denominator.",
    )
    report = PRReviewReport(
        overall_status=ReviewStatus.REQUEST_CHANGES,
        summary="All open findings are duplicates.",
        findings=[f1],
    )
    existing_comments = [
        {
            "path": "scorer/usage.py",
            "line": 20,
            "body": "**[BLOCKER] Division by zero**",
        }
    ]
    diff_hunks = {"scorer/usage.py": [20]}

    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"id": 2, "state": "CHANGES_REQUESTED"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        result = await post_github_pr_review(
            report=report,
            pr_number="42",
            repo="owner/repo",
            token="mock-token",
            modified_files_diff=diff_hunks,
            existing_comments=existing_comments,
        )

    assert result is True  # D-3
    assert len(captured_requests) == 1  # D-3
    payload = json.loads(captured_requests[0].data.decode("utf-8"))
    assert payload["comments"] == []  # D-3: No new inline comments
    assert payload["event"] == "COMMENT"  # D-3
    assert "All open findings are duplicates." in payload["body"]  # D-4
    assert "Status: REQUEST_CHANGES" in payload["body"]  # D-4


@pytest.mark.asyncio
async def test_run_pr_review_auto_fetches_comments_if_omitted():
    """Decision D-1, D-3: When existing_comments is None, run_pr_review calls fetch_pr_comments internally."""
    mock_report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="Clean PR.",
        findings=[],
    )
    mock_agent_response = MagicMock()
    mock_agent_response.structured_output = AsyncMock(return_value=mock_report)
    mock_agent = MagicMock()
    mock_agent.__aenter__ = AsyncMock(return_value=mock_agent)
    mock_agent.__aexit__ = AsyncMock(return_value=None)
    mock_agent.chat = AsyncMock(return_value=mock_agent_response)

    with patch.object(pr_reviewer_agent, "Agent", return_value=mock_agent), \
         patch("pr_reviewer_agent.fetch_pr_comments", return_value=[]) as mock_fetch, \
         patch("pr_reviewer_agent.send_github_review_sync", return_value=(200, "{}")) as mock_send, \
         patch("pr_reviewer_agent.fetch_pr_modified_lines", return_value={}):
        report = await run_pr_review(
            pr_number="42",
            repo="owner/repo",
            token="mock-token",
            existing_comments=None,
        )

    assert report is not None  # D-1
    mock_fetch.assert_called_once_with("owner", "repo", "42", "mock-token")  # D-1
