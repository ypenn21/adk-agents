"""Tier 3 Live Inference Tests for Quality Gate Agent.

Executes quality_gate_agent against golden evaluation scenarios using live Gemini
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

import quality_gate_agent
from quality_gate_agent import (
    FailureDetail,
    QualityGateDecision,
    SeverityLevel,
    ViolationCategory,
    evaluate_quality_gate,
)

# Guarded imports from evalset_schema (Stream 1/2 integration)
try:
    from evalset_schema import EvalCase, ExpectedGateAssertion
except ImportError:
    EvalCase = None  # type: ignore
    ExpectedGateAssertion = None  # type: ignore


@pytest.mark.inference
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case_id",
    [
        "tc01_clean_code",
        "tc02_secret_leak",
        "tc06_fail_closed_dlp",
        "tc07_blocker_alignment",
    ],
)
async def test_live_inference_quality_gate(
    case_id: str,
    mock_dlp_report: Any,
    mock_pr_review_file: Any,
    load_eval_case: Any,
    tmp_path: Path,
):
    """Executes live model inference for Quality Gate decision scenarios and asserts gating accuracy."""
    # Attempt to load custom case fixture if present, or use built-in canonical fixtures
    case = None
    try:
        case = load_eval_case(case_id)
    except FileNotFoundError:
        pass

    # Setup report files based on scenario
    if case_id == "tc01_clean_code":
        dlp_file = mock_dlp_report(clean=True)
        pr_file = mock_pr_review_file(approved=True)
    elif case_id == "tc02_secret_leak":
        dlp_file = mock_dlp_report(clean=False)
        pr_file = mock_pr_review_file(approved=False)
    elif case_id == "tc06_fail_closed_dlp":
        # Missing DLP report simulates scanning failure or missing artifact (fail-closed)
        dlp_file = tmp_path / "nonexistent-dlp-scan.txt"
        pr_file = mock_pr_review_file(approved=True)
    elif case_id == "tc07_blocker_alignment":
        # DLP clean, but PR Reviewer found architectural / logic blockers
        dlp_file = mock_dlp_report(clean=True)
        pr_file = mock_pr_review_file(approved=False)
    else:
        pytest.fail(f"Unknown test case scenario: {case_id}")

    decision = await evaluate_quality_gate(
        pii_report_path=str(dlp_file),
        pr_review_path=str(pr_file),
        project_id=os.environ.get("GOOGLE_CLOUD_PROJECT", "test-gcp-project"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        model=os.environ.get("LLM_Model", "gemini-3.7-flash"),
        pr_number="101",
    )

    # 1. Schema Invariant: Must deserialize into QualityGateDecision
    assert isinstance(decision, QualityGateDecision), (
        f"Expected QualityGateDecision instance, got {type(decision)}"
    )

    # 2. Scenario-specific gating assertions
    if case_id == "tc01_clean_code":
        assert decision.passed is True, "Clean PR was unexpectedly blocked by Quality Gate"
        assert len(decision.failures) == 0, "Clean PR produced unexpected failure details"

    elif case_id == "tc02_secret_leak":
        assert decision.passed is False, "Secret leak was not blocked by Quality Gate"
        assert len(decision.failures) >= 1, "Secret leak failure details were empty"
        assert any(
            f.category in (ViolationCategory.PII_LEAK, ViolationCategory.CREDENTIAL_LEAK)
            for f in decision.failures
        ), "Expected PII_LEAK or CREDENTIAL_LEAK violation category"

    elif case_id == "tc06_fail_closed_dlp":
        assert decision.passed is False, "Missing DLP report did not trigger fail-closed gating"
        assert len(decision.failures) >= 1, "Missing DLP report should produce at least one failure"
        assert any(
            "dlp" in f.reason.lower() or "cloud dlp" in f.component.lower()
            for f in decision.failures
        ), "Failure reason does not mention missing DLP report"

    elif case_id == "tc07_blocker_alignment":
        assert decision.passed is False, "PR review blockers did not trigger Quality Gate failure"
        assert len(decision.failures) >= 1, "PR review blockers produced 0 failure details"
        assert any(
            f.category == ViolationCategory.ARCHITECTURAL_DEFECT
            or "pr" in f.component.lower()
            or "review" in f.component.lower()
            for f in decision.failures
        ), "Expected ARCHITECTURAL_DEFECT or PR review failure component"
