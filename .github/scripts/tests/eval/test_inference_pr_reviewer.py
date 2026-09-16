"""Tier 3 Live Inference Tests for PR Reviewer Agent.

Executes pr_reviewer_agent against golden evaluation cases using live Gemini
models on Vertex AI. Gated behind the --run-inference pytest CLI flag.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Ensure .github/scripts is on sys.path
_scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import pr_reviewer_agent
from pr_reviewer_agent import (
    BatchReviewResult,
    FileDiffItem,
    PRFindingSeverity,
    PRReviewReport,
    PRTriageSummary,
    ReviewBatch,
    ReviewStatus,
    run_pr_review,
)

# Guarded imports from evalset_schema and mock_mcp_server (Stream 1/2 integration)
try:
    from evalset_schema import EvalCase, ExpectedReviewAssertion
except ImportError:
    EvalCase = None  # type: ignore
    ExpectedReviewAssertion = None  # type: ignore

try:
    from mock_mcp_server import create_mock_github_mcp_server
except ImportError:
    create_mock_github_mcp_server = None  # type: ignore


@pytest.mark.inference
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case_id",
    [
        "tc01_clean_code",
        "tc02_secret_leak",
        "tc03_sql_injection",
        "tc04_zero_division",
        "tc05_style_suggestion",
    ],
)
async def test_live_inference_pr_reviewer(
    case_id: str,
    load_eval_case: Any,
    eval_cases_dir: Path,
    mock_dlp_report: Any,
    tmp_path: Path,
):
    """Executes live model inference for a golden test case and asserts review accuracy."""
    try:
        case = load_eval_case(case_id)
    except FileNotFoundError:
        pytest.skip(f"Test case fixture {case_id}.json not yet populated on disk")

    # Extract case attributes safely whether case is EvalCase model or raw dict
    if hasattr(case, "diff_content"):
        diff_content = case.diff_content
        modified_files = case.modified_files
        category = case.category
        pii_scan = case.pii_scan_content
        expected_review = case.expected_review
    else:
        diff_content = case.get("diff_content", "")
        modified_files = case.get("modified_files", {})
        category = case.get("category", "")
        pii_scan = case.get("pii_scan_content", "✅ No sensitive data or PII detected.")
        expected_review = case.get("expected_review")

    dlp_path = mock_dlp_report(
        clean=("secret" not in category and "pii" not in category),
        custom_content=pii_scan,
    )

    # Prepare raw files diff representation
    raw_files = [
        {
            "filename": fn,
            "status": "modified",
            "patch": diff_content,
            "changes": len(lines) if isinstance(lines, list) else 10,
            "additions": len(lines) if isinstance(lines, list) else 10,
        }
        for fn, lines in (modified_files.items() if modified_files else {"main.py": [1]})
    ]

    # Wire mock MCP server if available
    fixture_file = eval_cases_dir / f"{case_id}.json"
    mcp_server = None
    if create_mock_github_mcp_server is not None and fixture_file.exists():
        mcp_server = create_mock_github_mcp_server(str(fixture_file))

    mcp_patcher = (
        patch("pr_reviewer_agent.create_github_mcp_server", return_value=mcp_server)
        if mcp_server is not None
        else patch("pr_reviewer_agent.create_github_mcp_server", return_value=None)
    )

    with (
        mcp_patcher,
        patch("pr_reviewer_agent.fetch_all_pr_modified_files", return_value=raw_files),
        patch("pr_reviewer_agent.fetch_pr_comments", return_value=[]),
        patch("pr_reviewer_agent.send_github_review_sync", return_value={"id": 1}),
        patch("pr_reviewer_agent.send_github_issue_comment_sync", return_value={"id": 1}),
    ):
        report = await run_pr_review(
            pr_number="101",
            repo="octocat/hello-world",
            token="ghp_mock_token_for_inference",
            pii_report_path=str(dlp_path),
            project_id=os.environ.get("GOOGLE_CLOUD_PROJECT", "test-gcp-project"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
            model=os.environ.get("LLM_Model", "gemini-3.7-flash"),
            modified_files_diff=modified_files,
            max_total_tokens=150000,
            max_model_calls=5,
            max_tool_calls=10,
        )

    # 1. Schema Invariant: LLM output must successfully deserialize into PRReviewReport
    assert report is not None, "PR reviewer agent returned None"
    assert isinstance(report, PRReviewReport), f"Expected PRReviewReport instance, got {type(report)}"

    # 2. Case-specific assertions
    if case_id == "tc01_clean_code":
        assert report.overall_status == ReviewStatus.APPROVE, (
            f"Clean code was rejected with status {report.overall_status}"
        )
        assert not any(f.severity == PRFindingSeverity.BLOCKER for f in report.findings), (
            "Clean code produced unexpected BLOCKER findings"
        )

    elif case_id == "tc02_secret_leak":
        assert report.overall_status == ReviewStatus.REQUEST_CHANGES, (
            "Secret leak did not trigger REQUEST_CHANGES"
        )
        blockers = [f for f in report.findings if f.severity == PRFindingSeverity.BLOCKER]
        assert len(blockers) >= 1, "Secret leak produced 0 BLOCKER findings"
        assert any(f.pii_leak for f in blockers), "Expected at least one finding with pii_leak=True"

    elif case_id == "tc03_sql_injection":
        assert report.overall_status == ReviewStatus.REQUEST_CHANGES, (
            "SQL injection did not trigger REQUEST_CHANGES"
        )
        blockers = [f for f in report.findings if f.severity == PRFindingSeverity.BLOCKER]
        assert len(blockers) >= 1, "SQL injection produced 0 BLOCKER findings"

    elif case_id == "tc04_zero_division":
        # Zero division defect should be flagged as BLOCKER or WARNING
        assert len(report.findings) >= 1, "Zero division defect went undetected"
        finding_texts = " ".join(f"{f.title} {f.details}" for f in report.findings).lower()
        assert any(
            kw in finding_texts
            for kw in ("zero", "division", "zerodivisionerror", "divide", "divisionbyzero")
        ), "Finding details do not mention division by zero"

    elif case_id == "tc05_style_suggestion":
        # Style suggestion should not block PR
        assert report.overall_status in (ReviewStatus.APPROVE, ReviewStatus.COMMENT), (
            f"Style suggestion caused unexpected blocking status {report.overall_status}"
        )
        assert not any(f.severity == PRFindingSeverity.BLOCKER for f in report.findings), (
            "Style suggestions should never produce BLOCKER findings"
        )
