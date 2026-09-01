"""Acceptance Tests for Automated PR Reviewer Agent.

Cites Decisions from docs/spec.md (D-1, D-2, D-3, D-4, D-5, D-6, D-7, D-8, D-9, D-10).
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

# Ensure .github/scripts is on sys.path for direct module import
_scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
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
    post_github_pr_review,
    run_pr_review,
    validate_and_sanitize_findings,
    format_pr_review_text,
    fetch_pr_comments,
    is_duplicate_comment,
)


@pytest.mark.asyncio
async def test_acceptance_clean_pr_posts_positive_approval_review(tmp_path, monkeypatch):
    """Scenario 1 (Decision D-1): Clean PR with zero findings submits positive approval review and creates artifacts."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "pii-scan.txt").write_text("No findings", encoding="utf-8")

    expected_report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="All changes are clean and adhere to repository guidelines.",
        findings=[],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_report)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        if "files" in req.full_url:
            mock_resp.read.return_value = b"[]"
        else:
            mock_resp.read.return_value = b'{"id": 1001, "state": "APPROVED"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch.object(pr_reviewer_agent, "Agent", return_value=mock_agent_instance), \
         patch("urllib.request.urlopen", side_effect=mock_urlopen):
        report = await run_pr_review(
            pr_number="42",
            repo="octocat/Hello-World",
            token="ghp_secret_token",
            pii_report_path=str(reports_dir / "pii-scan.txt"),
            project_id="test-proj",
            location="us-central1",
        )

    assert report is not None  # D-1
    assert report.overall_status == ReviewStatus.APPROVE  # D-1
    assert os.path.exists("reports/pr-review.json")  # D-7
    assert os.path.exists("reports/pr-review.txt")  # D-7

    review_requests = [r for r in captured_requests if "/reviews" in r.full_url]
    assert len(review_requests) == 1  # D-1
    req = review_requests[0]
    assert req.full_url == "https://api.github.com/repos/octocat/Hello-World/pulls/42/reviews"  # D-1
    assert req.headers["Authorization"] == "Bearer ghp_secret_token"  # D-1
    assert req.headers["Accept"] == "application/vnd.github+json"  # D-1

    payload = json.loads(req.data.decode("utf-8"))
    assert payload["event"] == "COMMENT"  # D-1
    assert payload["comments"] == []  # D-1
    assert "## ✅ Automated PR Review: APPROVED" in payload["body"]  # D-1
    assert "Great job! No code defects, architectural issues, or Cloud DLP security findings" in payload["body"]  # D-1


@pytest.mark.asyncio
async def test_acceptance_pr_with_findings_posts_inline_and_summary(tmp_path, monkeypatch):
    """Scenario 2 (Decisions D-2, D-3): Findings on diff lines post inline; out-of-hunk findings post in body."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "pii-scan.txt").write_text("No findings", encoding="utf-8")

    inline_finding = InlineFinding(
        file_path="scorer/usage.py",
        line_number=20,
        severity=PRFindingSeverity.BLOCKER,
        title="Division by zero potential",
        details="Denominator may evaluate to 0.",
        suggestion="if count == 0: return 0.0",
        pii_leak=False,
    )
    general_finding = InlineFinding(
        file_path="scorer/usage.py",
        line_number=500,
        severity=PRFindingSeverity.WARNING,
        title="Refactor complexity",
        details="Function exceeds cyclomatic complexity threshold.",
        suggestion="",
        pii_leak=False,
    )
    expected_report = PRReviewReport(
        overall_status=ReviewStatus.REQUEST_CHANGES,
        summary="Blocking errors and complexity warnings identified.",
        findings=[inline_finding, general_finding],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_report)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        if "comments" in req.full_url or "files" in req.full_url:
            mock_resp.read.return_value = b"[]"
        else:
            mock_resp.read.return_value = b'{"id": 1002, "state": "CHANGES_REQUESTED"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch.object(pr_reviewer_agent, "Agent", return_value=mock_agent_instance), \
         patch("urllib.request.urlopen", side_effect=mock_urlopen):
        report = await run_pr_review(
            pr_number="50",
            repo="octocat/Hello-World",
            token="ghp_token",
            pii_report_path=str(reports_dir / "pii-scan.txt"),
            modified_files_diff={"scorer/usage.py": [20]},
        )

    assert report is not None  # D-2
    assert report.overall_status == ReviewStatus.REQUEST_CHANGES  # D-2
    review_requests = [r for r in captured_requests if "/reviews" in r.full_url]
    assert len(review_requests) == 1  # D-2

    payload = json.loads(review_requests[0].data.decode("utf-8"))
    assert payload["event"] == "COMMENT"  # D-2
    assert len(payload["comments"]) == 1  # D-3
    assert payload["comments"][0]["path"] == "scorer/usage.py"  # D-3
    assert payload["comments"][0]["line"] == 20  # D-3
    assert "**[BLOCKER] Division by zero potential**" in payload["comments"][0]["body"]  # D-3
    assert "```suggestion\nif count == 0: return 0.0\n```" in payload["comments"][0]["body"]  # D-3

    # Out of hunk finding in top-level body
    assert "Refactor complexity" in payload["body"]  # D-3


@pytest.mark.asyncio
async def test_acceptance_non_pr_event_skips_cleanly():
    """Scenario 3 (Decision D-4): Push / non-PR events exit cleanly with 0 and make no network calls."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        result = await run_pr_review(pr_number=None, repo="octocat/Hello-World", token="token")
        assert result is None  # D-4
        mock_urlopen.assert_not_called()  # D-4


@pytest.mark.asyncio
async def test_acceptance_422_unprocessable_entity_recovers_via_body_fallback(tmp_path, monkeypatch, capsys):
    """Scenario 5 (Decision D-6): 422 line coordinate error automatically retries with consolidated body comments."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "pii-scan.txt").write_text("No findings", encoding="utf-8")

    inline_finding = InlineFinding(
        file_path="scorer/usage.py",
        line_number=35,
        severity=PRFindingSeverity.WARNING,
        title="Stale hunk line",
        details="Diff hunk shifted.",
        suggestion="refactor()",
    )
    expected_report = PRReviewReport(
        overall_status=ReviewStatus.COMMENT,
        summary="Comment on shifted hunk.",
        findings=[inline_finding],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_report)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    captured_requests = []
    attempt = 0

    def mock_urlopen(req, timeout=None):
        nonlocal attempt
        captured_requests.append(req)
        if "comments" in req.full_url or "files" in req.full_url:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b"[]"
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.__exit__.return_value = None
            return mock_resp

        attempt += 1
        if attempt == 1:
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=422,
                msg="Unprocessable Entity",
                hdrs={},
                fp=BytesIO(b'{"message": "Line not in diff hunk"}'),
            )
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"id": 1003, "state": "COMMENTED"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch.object(pr_reviewer_agent, "Agent", return_value=mock_agent_instance), \
         patch("urllib.request.urlopen", side_effect=mock_urlopen):
        report = await run_pr_review(
            pr_number="60",
            repo="octocat/Hello-World",
            token="ghp_token",
            pii_report_path=str(reports_dir / "pii-scan.txt"),
            modified_files_diff={"scorer/usage.py": [35]},
        )

    assert report is not None  # D-6
    review_requests = [r for r in captured_requests if "/reviews" in r.full_url]
    assert len(review_requests) == 2  # D-6: Initial + 1 Fallback retry
    fallback_payload = json.loads(review_requests[1].data.decode("utf-8"))
    assert fallback_payload["comments"] == []  # D-6
    assert "Stale hunk line" in fallback_payload["body"]  # D-6

    captured = capsys.readouterr()
    assert "Successfully posted fallback PR review" in captured.out  # D-6


@pytest.mark.asyncio
async def test_acceptance_api_network_failure_is_non_fatal(tmp_path, monkeypatch, capsys):
    """Scenario 4 (Decision D-5): Network error logs warning and does not raise exception or crash."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "pii-scan.txt").write_text("No findings", encoding="utf-8")

    expected_report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="Clean PR.",
        findings=[],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_report)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    with patch.object(pr_reviewer_agent, "Agent", return_value=mock_agent_instance), \
         patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection reset")):
        report = await run_pr_review(
            pr_number="70",
            repo="octocat/Hello-World",
            token="ghp_token",
            pii_report_path=str(reports_dir / "pii-scan.txt"),
        )

    assert report is not None  # D-5
    assert os.path.exists("reports/pr-review.json")  # D-7
    assert os.path.exists("reports/pr-review.txt")  # D-7

    captured = capsys.readouterr()
    assert "[Warning] Failed to post PR review to GitHub" in captured.out  # D-5


# =====================================================================
# Milestone Acceptance Tests: Deduplication across Re-runs and Commits
# =====================================================================

@pytest.mark.asyncio
async def test_acceptance_initial_run_with_findings_posts_all_comments(tmp_path, monkeypatch):
    """Scenario 1 (Decision D-1, D-3): Initial run with no prior review comments posts all inline comments."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "pii-scan.txt").write_text("No findings", encoding="utf-8")

    f1 = InlineFinding(
        file_path="scorer/usage.py",
        line_number=20,
        severity=PRFindingSeverity.BLOCKER,
        title="Division by zero",
        details="Potential zero denominator.",
        suggestion="if total == 0: return 0",
    )
    expected_report = PRReviewReport(
        overall_status=ReviewStatus.REQUEST_CHANGES,
        summary="Found 1 blocking issue.",
        findings=[f1],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_report)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        if "comments" in req.full_url:
            mock_resp.read.return_value = b"[]"
        elif "files" in req.full_url:
            mock_resp.read.return_value = b"[]"
        else:
            mock_resp.read.return_value = b'{"id": 2001, "state": "CHANGES_REQUESTED"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch.object(pr_reviewer_agent, "Agent", return_value=mock_agent_instance), \
         patch("urllib.request.urlopen", side_effect=mock_urlopen):
        report = await run_pr_review(
            pr_number="101",
            repo="octocat/Hello-World",
            token="ghp_token",
            pii_report_path=str(reports_dir / "pii-scan.txt"),
            modified_files_diff={"scorer/usage.py": [20]},
        )

    assert report is not None  # D-1
    review_requests = [r for r in captured_requests if "/reviews" in r.full_url]
    assert len(review_requests) == 1  # D-1
    payload = json.loads(review_requests[0].data.decode("utf-8"))
    assert len(payload["comments"]) == 1  # D-3
    assert payload["comments"][0]["path"] == "scorer/usage.py"  # D-3
    assert payload["comments"][0]["line"] == 20  # D-3
    assert "Division by zero" in payload["comments"][0]["body"]  # D-3


@pytest.mark.asyncio
async def test_acceptance_clean_pr_posts_positive_approval(tmp_path, monkeypatch):
    """Scenario 2 (Decision D-5): Clean PR with zero findings posts positive approval review."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "pii-scan.txt").write_text("No findings", encoding="utf-8")

    expected_report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="",
        findings=[],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_report)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        if "comments" in req.full_url:
            mock_resp.read.return_value = b"[]"
        elif "files" in req.full_url:
            mock_resp.read.return_value = b"[]"
        else:
            mock_resp.read.return_value = b'{"id": 2002, "state": "APPROVED"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch.object(pr_reviewer_agent, "Agent", return_value=mock_agent_instance), \
         patch("urllib.request.urlopen", side_effect=mock_urlopen):
        report = await run_pr_review(
            pr_number="102",
            repo="octocat/Hello-World",
            token="ghp_token",
            pii_report_path=str(reports_dir / "pii-scan.txt"),
        )

    assert report is not None  # D-5
    review_requests = [r for r in captured_requests if "/reviews" in r.full_url]
    assert len(review_requests) == 1  # D-5
    payload = json.loads(review_requests[0].data.decode("utf-8"))
    assert payload["comments"] == []  # D-5
    assert POSITIVE_APPROVAL_TEMPLATE in payload["body"]  # D-5


@pytest.mark.asyncio
async def test_acceptance_rerun_all_duplicates_skips_inline_comments(tmp_path, monkeypatch, capsys):
    """Scenario 3 (Decision D-3, D-4): Re-run where all findings are duplicates skips inline comments and posts full summary."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "pii-scan.txt").write_text("No findings", encoding="utf-8")

    f1 = InlineFinding(
        file_path="scorer/usage.py",
        line_number=20,
        severity=PRFindingSeverity.BLOCKER,
        title="Division by zero",
        details="Potential zero denominator.",
    )
    expected_report = PRReviewReport(
        overall_status=ReviewStatus.REQUEST_CHANGES,
        summary="Found 1 blocking issue.",
        findings=[f1],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_report)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    existing_comments = [
        {
            "id": 501,
            "path": "scorer/usage.py",
            "line": 20,
            "original_line": 20,
            "body": "**[BLOCKER] Division by zero**\n\nPotential zero denominator.",
        }
    ]

    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        if "comments" in req.full_url:
            mock_resp.read.return_value = json.dumps(existing_comments).encode("utf-8")
        elif "files" in req.full_url:
            mock_resp.read.return_value = b"[]"
        else:
            mock_resp.read.return_value = b'{"id": 2003, "state": "CHANGES_REQUESTED"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch.object(pr_reviewer_agent, "Agent", return_value=mock_agent_instance), \
         patch("urllib.request.urlopen", side_effect=mock_urlopen):
        report = await run_pr_review(
            pr_number="103",
            repo="octocat/Hello-World",
            token="ghp_token",
            pii_report_path=str(reports_dir / "pii-scan.txt"),
            modified_files_diff={"scorer/usage.py": [20]},
        )

    assert report is not None  # D-3
    review_requests = [r for r in captured_requests if "/reviews" in r.full_url]
    assert len(review_requests) == 1  # D-3
    payload = json.loads(review_requests[0].data.decode("utf-8"))
    assert payload["comments"] == []  # D-3
    assert payload["event"] == "COMMENT"  # D-3
    assert "Found 1 blocking issue." in payload["body"]  # D-4
    assert "Status: REQUEST_CHANGES" in payload["body"]  # D-4

    captured = capsys.readouterr()
    assert "Skipped 1 duplicate inline review comment" in captured.out  # D-3


@pytest.mark.asyncio
async def test_acceptance_incremental_commit_posts_only_new_finding(tmp_path, monkeypatch, capsys):
    """Scenario 4 (Decision D-3, D-4): Subsequent commit posts only newly introduced inline findings."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "pii-scan.txt").write_text("No findings", encoding="utf-8")

    f1 = InlineFinding(
        file_path="scorer/usage.py",
        line_number=20,
        severity=PRFindingSeverity.BLOCKER,
        title="Division by zero",
        details="Potential zero denominator.",
    )
    f2 = InlineFinding(
        file_path="scorer/usage.py",
        line_number=45,
        severity=PRFindingSeverity.WARNING,
        title="Unchecked None parameter",
        details="Parameter data might be None.",
        suggestion="if data is None: return",
    )
    expected_report = PRReviewReport(
        overall_status=ReviewStatus.REQUEST_CHANGES,
        summary="Found 1 blocker and 1 warning.",
        findings=[f1, f2],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_report)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    existing_comments = [
        {
            "id": 501,
            "path": "scorer/usage.py",
            "line": 20,
            "original_line": 20,
            "body": "**[BLOCKER] Division by zero**\n\nPotential zero denominator.",
        }
    ]

    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        if "comments" in req.full_url:
            mock_resp.read.return_value = json.dumps(existing_comments).encode("utf-8")
        elif "files" in req.full_url:
            mock_resp.read.return_value = b"[]"
        else:
            mock_resp.read.return_value = b'{"id": 2004, "state": "CHANGES_REQUESTED"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch.object(pr_reviewer_agent, "Agent", return_value=mock_agent_instance), \
         patch("urllib.request.urlopen", side_effect=mock_urlopen):
        report = await run_pr_review(
            pr_number="104",
            repo="octocat/Hello-World",
            token="ghp_token",
            pii_report_path=str(reports_dir / "pii-scan.txt"),
            modified_files_diff={"scorer/usage.py": [20, 45]},
        )

    assert report is not None  # D-3
    review_requests = [r for r in captured_requests if "/reviews" in r.full_url]
    assert len(review_requests) == 1  # D-3
    payload = json.loads(review_requests[0].data.decode("utf-8"))
    assert len(payload["comments"]) == 1  # D-3: only f2
    assert payload["comments"][0]["path"] == "scorer/usage.py"  # D-3
    assert payload["comments"][0]["line"] == 45  # D-3
    assert "Unchecked None parameter" in payload["comments"][0]["body"]  # D-3
    assert "Found 1 blocker and 1 warning." in payload["body"]  # D-4


@pytest.mark.asyncio
async def test_acceptance_comment_fetch_network_error_falls_back_gracefully(tmp_path, monkeypatch, capsys):
    """Scenario 6 (Decision D-6): Comment fetch network error logs warning, falls back to empty comments, and proceeds."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "pii-scan.txt").write_text("No findings", encoding="utf-8")

    f1 = InlineFinding(
        file_path="scorer/usage.py",
        line_number=20,
        severity=PRFindingSeverity.BLOCKER,
        title="Division by zero",
        details="Potential zero denominator.",
    )
    expected_report = PRReviewReport(
        overall_status=ReviewStatus.REQUEST_CHANGES,
        summary="Found issue under network degradation.",
        findings=[f1],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_report)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        if "comments" in req.full_url:
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=500,
                msg="Internal Server Error",
                hdrs={},
                fp=BytesIO(b'{"message": "API rate limited or server error"}'),
            )
        mock_resp = MagicMock()
        mock_resp.status = 200
        if "files" in req.full_url:
            mock_resp.read.return_value = b"[]"
        else:
            mock_resp.read.return_value = b'{"id": 2005, "state": "CHANGES_REQUESTED"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    with patch.object(pr_reviewer_agent, "Agent", return_value=mock_agent_instance), \
         patch("urllib.request.urlopen", side_effect=mock_urlopen):
        report = await run_pr_review(
            pr_number="105",
            repo="octocat/Hello-World",
            token="ghp_token",
            pii_report_path=str(reports_dir / "pii-scan.txt"),
            modified_files_diff={"scorer/usage.py": [20]},
        )

    assert report is not None  # D-6
    review_requests = [r for r in captured_requests if "/reviews" in r.full_url]
    assert len(review_requests) == 1  # D-6
    captured = capsys.readouterr()
    assert "[Warning] Could not fetch existing PR comments from GitHub API" in captured.out  # D-6


