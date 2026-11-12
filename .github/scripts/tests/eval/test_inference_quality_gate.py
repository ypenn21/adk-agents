"""Tier 3 Live Inference Tests for Quality Gate Agent.

Executes quality_gate_agent against golden evaluation scenarios using live Gemini
models on Vertex AI. Gated behind the --run-inference pytest CLI flag.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

import pytest

# Ensure .github/scripts is on sys.path
_scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

# Ensure .github/scripts/tests/eval is on sys.path
_eval_dir = os.path.abspath(os.path.dirname(__file__))
if _eval_dir not in sys.path:
    sys.path.insert(0, _eval_dir)

import quality_gate_agent
from quality_gate_agent import (
    FailureDetail,
    QualityGateDecision,
    SeverityLevel,
    ViolationCategory,
    evaluate_quality_gate,
)

# Guarded imports from evalset_schema and eval_runner (Stream 1/2 integration)
try:
    from evalset_schema import EvalCase, ExpectedGateAssertion, EvalRunMetric
except ImportError:
    EvalCase = None  # type: ignore
    ExpectedGateAssertion = None  # type: ignore
    EvalRunMetric = None  # type: ignore

try:
    from eval_runner import record_eval_metric
except ImportError:
    record_eval_metric = None  # type: ignore


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

    # Unlink stale quality gate token usage files (primary and fallback paths)
    qg_usage_path = Path("reports/quality-gate-token-usage.json")
    qg_telemetry_path = Path("reports/telemetry/quality_gate_agent/token-usage.json")
    qg_usage_path.unlink(missing_ok=True)
    qg_telemetry_path.unlink(missing_ok=True)
    start_time = time.monotonic()

    decision = await evaluate_quality_gate(
        pii_report_path=str(dlp_file),
        pr_review_path=str(pr_file),
        project_id=os.environ.get("GOOGLE_CLOUD_PROJECT", "test-gcp-project"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        model=os.environ.get("LLM_Model", "gemini-3.7-flash"),
        pr_number="101",
    )

    duration = round(max(0.0, time.monotonic() - start_time), 3)

    # Read token telemetry report written by quality_gate_agent
    usage_data: dict[str, Any] = {}
    if qg_usage_path.exists():
        try:
            with open(qg_usage_path, "r", encoding="utf-8") as f:
                usage_data = json.load(f)
        except Exception:
            usage_data = {}
    elif qg_telemetry_path.exists():
        try:
            with open(qg_telemetry_path, "r", encoding="utf-8") as f:
                usage_data = json.load(f)
        except Exception:
            usage_data = {}

    schema_valid = isinstance(decision, QualityGateDecision)
    schema_error = (
        None
        if schema_valid
        else (f"Expected QualityGateDecision instance, got {type(decision)}" if decision is not None else "Quality gate agent returned None")
    )
    findings_count = len(decision.failures) if isinstance(decision, QualityGateDecision) else 0
    detected_blockers = findings_count

    status_match = False
    clean_fpr: Optional[float] = None
    blocker_recall: Optional[float] = None

    if case_id == "tc01_clean_code":
        status_match = isinstance(decision, QualityGateDecision) and decision.passed is True
        clean_fpr = 0.0 if status_match else 1.0
    else:
        status_match = isinstance(decision, QualityGateDecision) and decision.passed is False
        blocker_recall = 1.0 if status_match else 0.0

    passed_all_assertions = False
    failure_reasons: list[str] = []

    try:
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

        passed_all_assertions = True
    except Exception as exc:
        passed_all_assertions = False
        failure_reasons.append(str(exc))
        raise
    finally:
        if EvalRunMetric is not None and record_eval_metric is not None:
            try:
                category = (
                    getattr(case, "category", case.get("category", "") if isinstance(case, dict) else "")
                    if case is not None
                    else ("clean" if "clean" in case_id else "vulnerability")
                )
                metric = EvalRunMetric(
                    case_id=case_id,
                    name=getattr(case, "name", case.get("name", case_id) if isinstance(case, dict) else case_id) if case is not None else case_id,
                    category=category or ("clean" if "clean" in case_id else "vulnerability"),
                    agent_target="quality_gate",
                    duration_seconds=duration,
                    schema_valid=schema_valid,
                    schema_error=schema_error,
                    status_match=status_match,
                    blocker_recall=blocker_recall,
                    clean_fpr=clean_fpr,
                    findings_count=findings_count,
                    detected_blockers=detected_blockers,
                    prompt_tokens=int(usage_data.get("prompt_tokens", 0)),
                    candidate_tokens=int(usage_data.get("candidate_tokens", 0)),
                    cached_tokens=int(usage_data.get("cached_tokens", 0)),
                    thought_tokens=int(usage_data.get("thought_tokens", 0)),
                    total_tokens=int(usage_data.get("total_tokens", 0)),
                    cost_usd=float(usage_data.get("total_cost_usd", usage_data.get("cost_usd", 0.0))),
                    passed_all_assertions=passed_all_assertions,
                    failure_reasons=failure_reasons,
                )
                record_eval_metric(metric, output_dir="reports")
            except Exception as metric_exc:
                print(
                    f"[WARNING] Failed to record eval metric for {case_id} (quality_gate): {metric_exc}",
                    file=sys.stderr,
                )
