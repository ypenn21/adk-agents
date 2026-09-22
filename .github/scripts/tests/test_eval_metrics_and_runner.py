"""Tests for LLM Inference Evaluation schemas, metrics, and CLI summary runner."""

import os
import sys
import json
import tempfile
from pathlib import Path
import pytest

# Ensure scripts and eval directories are on sys.path
_scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_eval_dir = os.path.join(_scripts_dir, "tests", "eval")
for p in (_scripts_dir, _eval_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

from pr_reviewer_agent import ReviewStatus, PRFindingSeverity, PRReviewReport, InlineFinding
from quality_gate_agent import SeverityLevel, ViolationCategory, QualityGateDecision, FailureDetail
from evalset_schema import (
    EvalCase,
    EvalRunMetric,
    EvalSuiteSummary,
    ExpectedFindingAssertion,
    ExpectedReviewAssertion,
    ExpectedGateAssertion,
)
from metrics import (
    calculate_schema_conformance,
    calculate_vulnerability_recall,
    calculate_clean_false_positive_rate,
    calculate_total_and_average_spend,
    evaluate_case_assertions,
)
from eval_runner import (
    record_eval_metric,
    run_summary_generation,
    generate_markdown_summary,
    build_suite_summary,
    evaluate_threshold_breach,
    DEFAULT_PASS_RATE_THRESHOLD,
    DEFAULT_SCHEMA_CONFORMANCE_THRESHOLD,
    DEFAULT_VULNERABILITY_RECALL_THRESHOLD,
    DEFAULT_CLEAN_FPR_THRESHOLD,
    main,
)


def test_calculate_schema_conformance_empty_and_normal():
    # Empty list must gracefully return 1.0 (no zero division)
    assert calculate_schema_conformance([]) == 1.0

    # 3 valid, 1 invalid
    results = [
        EvalRunMetric(
            case_id=f"c{i}", name=f"c{i}", category="clean", agent_target="pr_reviewer",
            duration_seconds=1.0, schema_valid=(i != 3), status_match=True, passed_all_assertions=(i != 3)
        )
        for i in range(4)
    ]
    assert calculate_schema_conformance(results) == 0.75


def test_calculate_vulnerability_recall_empty_and_normal():
    # Empty list or clean-only must gracefully return 1.0
    assert calculate_vulnerability_recall([]) == 1.0

    clean_metric = EvalRunMetric(
        case_id="clean", name="clean", category="clean", agent_target="pr_reviewer",
        duration_seconds=1.0, schema_valid=True, status_match=True, clean_fpr=0.0, passed_all_assertions=True
    )
    assert calculate_vulnerability_recall([clean_metric]) == 1.0

    # 1 recalled defect, 1 missed defect
    defect_recalled = EvalRunMetric(
        case_id="d1", name="d1", category="secret_leak", agent_target="pr_reviewer",
        duration_seconds=1.0, schema_valid=True, status_match=True, blocker_recall=1.0, passed_all_assertions=True
    )
    defect_missed = EvalRunMetric(
        case_id="d2", name="d2", category="vulnerability", agent_target="pr_reviewer",
        duration_seconds=1.0, schema_valid=True, status_match=False, blocker_recall=0.0, passed_all_assertions=False
    )
    assert calculate_vulnerability_recall([clean_metric, defect_recalled, defect_missed]) == 0.5


def test_calculate_clean_false_positive_rate_empty_and_normal():
    # Empty list or defect-only must gracefully return 0.0
    assert calculate_clean_false_positive_rate([]) == 0.0

    defect_metric = EvalRunMetric(
        case_id="d1", name="d1", category="secret_leak", agent_target="pr_reviewer",
        duration_seconds=1.0, schema_valid=True, status_match=True, blocker_recall=1.0, passed_all_assertions=True
    )
    assert calculate_clean_false_positive_rate([defect_metric]) == 0.0

    # 1 clean pass (FPR=0.0), 1 clean false positive (FPR=1.0)
    clean_pass = EvalRunMetric(
        case_id="c1", name="c1", category="clean", agent_target="pr_reviewer",
        duration_seconds=1.0, schema_valid=True, status_match=True, clean_fpr=0.0, passed_all_assertions=True
    )
    clean_fp = EvalRunMetric(
        case_id="c2", name="c2", category="clean", agent_target="pr_reviewer",
        duration_seconds=1.0, schema_valid=True, status_match=False, clean_fpr=1.0, passed_all_assertions=False
    )
    assert calculate_clean_false_positive_rate([clean_pass, clean_fp]) == 0.5


def test_calculate_total_and_average_spend_pricing_rates():
    # Verify pricing formula:
    # prompt: $0.75/1M, cached: $0.075/1M, candidate/thought: $3.75/1M
    m1 = EvalRunMetric(
        case_id="c1", name="c1", category="clean", agent_target="pr_reviewer",
        duration_seconds=2.0, schema_valid=True, status_match=True,
        prompt_tokens=1000, cached_tokens=500, candidate_tokens=200, thought_tokens=100,
        total_tokens=1300, cost_usd=0.001538, passed_all_assertions=True
    )
    m2 = EvalRunMetric(
        case_id="c2", name="c2", category="clean", agent_target="pr_reviewer",
        duration_seconds=4.0, schema_valid=True, status_match=True,
        prompt_tokens=2000, cached_tokens=1000, candidate_tokens=400, thought_tokens=200,
        total_tokens=2600, cost_usd=0.003075, passed_all_assertions=True
    )

    spend = calculate_total_and_average_spend([m1, m2])
    assert spend["total_tokens"] == 3900.0
    assert spend["avg_tokens"] == 1950.0
    assert spend["avg_latency_seconds"] == 3.0
    assert abs(spend["total_cost_usd"] - 0.004613) < 1e-5


def test_evaluate_case_assertions_clean_pr_success():
    case = EvalCase(
        case_id="tc01_clean_code",
        name="Clean PR",
        description="Clean code",
        category="clean",
        diff_content="+ x = 1",
        expected_review=ExpectedReviewAssertion(
            expected_status=[ReviewStatus.APPROVE],
            min_findings=0,
            max_findings=0,
            has_blockers=False,
        ),
    )
    report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="No issues found",
        findings=[],
    )
    usage = {
        "prompt_tokens": 1200,
        "cached_tokens": 200,
        "candidate_tokens": 80,
        "thought_tokens": 40,
        "total_tokens": 1320,
    }

    metric = evaluate_case_assertions(case, report, duration=1.85, usage=usage)
    assert metric.schema_valid is True
    assert metric.status_match is True
    assert metric.clean_fpr == 0.0
    assert metric.passed_all_assertions is True
    assert len(metric.failure_reasons) == 0

    # Net prompt: (1200 - 200) * 0.75 / 1M = 0.00075
    # Cached: 200 * 0.075 / 1M = 0.000015
    # Candidate+Thought: (80 + 40) * 3.75 / 1M = 0.00045
    # Total = 0.001215
    assert abs(metric.cost_usd - 0.001215) < 1e-6


def test_evaluate_case_assertions_clean_pr_comment_status_success():
    case = EvalCase(
        case_id="tc01_clean_code",
        name="Clean PR with Non-blocking Comments",
        description="Clean code with stylistic suggestion",
        category="clean",
        diff_content="+ def health_check(): pass",
        expected_review=ExpectedReviewAssertion(
            expected_status=[ReviewStatus.APPROVE, ReviewStatus.COMMENT],
            min_findings=0,
            has_blockers=False,
        ),
    )
    report = PRReviewReport(
        overall_status=ReviewStatus.COMMENT,
        summary="Clean implementation with non-blocking suggestion.",
        findings=[
            InlineFinding(
                file_path="web_ui/views.py",
                line_number=12,
                severity=PRFindingSeverity.SUGGESTION,
                title="Restrict to GET requests",
                details="Use @require_GET decorator",
                suggestion="@require_GET",
                pii_leak=False,
            )
        ],
    )
    usage = {
        "prompt_tokens": 1000,
        "candidate_tokens": 100,
        "cached_tokens": 0,
        "thought_tokens": 0,
        "total_tokens": 1100,
    }

    metric = evaluate_case_assertions(case, report, duration=2.0, usage=usage)
    assert metric.schema_valid is True
    assert metric.status_match is True
    assert metric.clean_fpr == 0.0
    assert metric.detected_blockers == 0
    assert metric.passed_all_assertions is True
    assert len(metric.failure_reasons) == 0


def test_evaluate_case_assertions_vulnerability_pr_success():
    case = EvalCase(
        case_id="tc02_secret_leak",
        name="Secret Leak",
        description="Hardcoded credentials",
        category="secret_leak",
        diff_content="+ api_key = 'sk-12345'",
        expected_review=ExpectedReviewAssertion(
            expected_status=[ReviewStatus.REQUEST_CHANGES],
            min_findings=1,
            has_blockers=True,
            required_findings=[
                ExpectedFindingAssertion(
                    expected_severity=PRFindingSeverity.BLOCKER,
                    keyword_in_title_or_details="credential",
                )
            ],
        ),
    )
    report = PRReviewReport(
        overall_status=ReviewStatus.REQUEST_CHANGES,
        summary="Detected hardcoded secret",
        findings=[
            InlineFinding(
                file_path="config.py",
                line_number=10,
                severity=PRFindingSeverity.BLOCKER,
                title="Exposed API credential",
                details="Hardcoded key discovered in diff.",
                suggestion="Use environment variables.",
            )
        ],
    )
    metric = evaluate_case_assertions(case, report, duration=2.5, usage={})
    assert metric.schema_valid is True
    assert metric.status_match is True
    assert metric.blocker_recall == 1.0
    assert metric.detected_blockers == 1
    assert metric.passed_all_assertions is True


def test_evaluate_case_assertions_status_mismatch():
    case = EvalCase(
        case_id="tc03_sql_injection",
        name="SQL Injection",
        description="SQL injection vulnerability",
        category="vulnerability",
        diff_content="+ query = f'SELECT * FROM users WHERE id = {user_id}'",
        expected_review=ExpectedReviewAssertion(
            expected_status=[ReviewStatus.REQUEST_CHANGES],
            min_findings=1,
            has_blockers=True,
        ),
    )
    # Model incorrectly approved the PR
    report = PRReviewReport(
        overall_status=ReviewStatus.APPROVE,
        summary="Approved with minor comments",
        findings=[
            InlineFinding(
                file_path="db.py",
                line_number=5,
                severity=PRFindingSeverity.WARNING,
                title="SQL Query formatting",
                details="Consider using parameterized queries.",
            )
        ],
    )
    metric = evaluate_case_assertions(case, report, duration=3.0, usage={})
    assert metric.schema_valid is True
    assert metric.status_match is False
    assert metric.blocker_recall == 0.0
    assert metric.passed_all_assertions is False
    assert any("Overall status 'APPROVE' not in expected" in r for r in metric.failure_reasons)


def test_evaluate_case_assertions_quality_gate():
    case = EvalCase(
        case_id="tc06_fail_closed_dlp",
        name="Missing DLP Report Fail-Closed",
        description="DLP scan missing triggers fail-closed rule",
        category="fail_closed",
        diff_content="",
        expected_gate=ExpectedGateAssertion(
            expected_passed=False,
            min_failures=1,
            expected_failure_categories=[ViolationCategory.SECURITY_VULNERABILITY],
            expected_severities=[SeverityLevel.CRITICAL],
            keyword_in_summary_or_reason="Cloud DLP",
        ),
    )
    decision = QualityGateDecision(
        passed=False,
        summary="Cloud DLP scan report is missing. Gate failed closed.",
        failures=[
            FailureDetail(
                category=ViolationCategory.SECURITY_VULNERABILITY,
                component="Cloud DLP",
                severity=SeverityLevel.CRITICAL,
                reason="Cloud DLP scan output missing or unreadable.",
                remediation="Ensure DLP scan step finishes successfully.",
            )
        ],
    )
    metric = evaluate_case_assertions(case, decision, duration=0.5, usage={})
    assert metric.agent_target == "quality_gate"
    assert metric.schema_valid is True
    assert metric.status_match is True
    assert metric.blocker_recall == 1.0
    assert metric.passed_all_assertions is True


def test_evaluate_case_assertions_invalid_schema():
    case = EvalCase(
        case_id="tc_bad",
        name="Bad Schema",
        description="Malformed",
        category="clean",
        diff_content="",
    )
    # Invalid report object (string instead of dict/model)
    metric = evaluate_case_assertions(case, "invalid string response", duration=0.1, usage={})
    assert metric.schema_valid is False
    assert metric.schema_error is not None
    assert metric.passed_all_assertions is False


def test_eval_runner_full_cycle_and_step_summary():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)

        m1 = EvalRunMetric(
            case_id="tc01_clean_code",
            name="Clean Code",
            category="clean",
            agent_target="pr_reviewer",
            duration_seconds=2.1,
            schema_valid=True,
            status_match=True,
            clean_fpr=0.0,
            prompt_tokens=1000,
            cached_tokens=200,
            candidate_tokens=100,
            thought_tokens=50,
            total_tokens=1150,
            cost_usd=0.001178,
            passed_all_assertions=True,
        )
        m2 = EvalRunMetric(
            case_id="tc02_secret_leak",
            name="Secret Leak",
            category="secret_leak",
            agent_target="pr_reviewer",
            duration_seconds=3.4,
            schema_valid=True,
            status_match=True,
            blocker_recall=1.0,
            detected_blockers=1,
            prompt_tokens=1500,
            cached_tokens=300,
            candidate_tokens=200,
            thought_tokens=80,
            total_tokens=1780,
            cost_usd=0.001973,
            passed_all_assertions=True,
        )

        record_eval_metric(m1, output_dir=out_dir)
        record_eval_metric(m2, output_dir=out_dir)

        # Mock GITHUB_STEP_SUMMARY file
        summary_env_file = out_dir / "step_summary.md"
        os.environ["GITHUB_STEP_SUMMARY"] = str(summary_env_file)

        try:
            summary = run_summary_generation(
                output_dir=out_dir,
                model_name="gemini-3.7-flash",
            )

            assert summary.total_cases == 2
            assert summary.passed_cases == 2
            assert summary.failed_cases == 0
            assert summary.overall_pass_rate == 1.0
            assert summary.schema_conformance_rate == 1.0
            assert summary.vulnerability_recall == 1.0
            assert summary.clean_false_positive_rate == 0.0

            # Verify eval-summary.json
            with open(out_dir / "eval-summary.json", "r", encoding="utf-8") as f:
                json_data = json.load(f)
                assert json_data["model_name"] == "gemini-3.7-flash"
                assert len(json_data["case_metrics"]) == 2

            # Verify eval-summary.md
            with open(out_dir / "eval-summary.md", "r", encoding="utf-8") as f:
                md_content = f.read()
                assert "# 🧪 LLM Inference Evaluation Summary" in md_content
                assert "ALL EVALUATION ASSERTIONS PASSED" in md_content
                assert "tc01_clean_code" in md_content
                assert "tc02_secret_leak" in md_content

            # Verify GITHUB_STEP_SUMMARY write
            assert summary_env_file.exists()
            assert "LLM Inference Evaluation Summary" in summary_env_file.read_text(encoding="utf-8")

        finally:
            os.environ.pop("GITHUB_STEP_SUMMARY", None)


def test_generate_markdown_summary_with_default_and_custom_thresholds():
    summary = EvalSuiteSummary(
        timestamp="2026-09-21T12:00:00Z",
        model_name="gemini-3.7-flash",
        total_cases=9,
        passed_cases=8,
        failed_cases=1,
        overall_pass_rate=round(8 / 9, 4),  # 0.8889 -> 88.9%
        schema_conformance_rate=round(8 / 9, 4),  # 0.8889 -> 88.9%
        vulnerability_recall=round(6 / 7, 4),  # 0.8571 -> 85.7%
        clean_false_positive_rate=0.0,
        total_tokens=10000,
        total_cost_usd=0.015,
        avg_latency_seconds=3.5,
        case_metrics=[],
    )

    # 1. Default thresholds (85.0% targets)
    md_default = generate_markdown_summary(summary)
    assert "| **Overall Pass Rate** | `85.0%` | `88.9%` (8/9) | ✅ PASS |" in md_default
    assert "| **Schema Conformance** | `85.0%` | `88.9%` | ✅ PASS |" in md_default
    assert "| **Vulnerability Recall** | `85.0%` | `85.7%` | ✅ PASS |" in md_default
    assert "| **Clean False Positive Rate** | `< 5.0%` | `0.0%` | ✅ PASS |" in md_default
    assert "### ✅ Status: **ALL EVALUATION ASSERTIONS PASSED**" in md_default

    # 2. Custom thresholds (90.0% targets): 88.9% and 85.7% appropriately marked as ❌ FAIL
    md_custom = generate_markdown_summary(
        summary,
        pass_threshold=0.90,
        schema_threshold=0.90,
        recall_threshold=0.90,
        fpr_threshold=0.05,
    )
    assert "| **Overall Pass Rate** | `90.0%` | `88.9%` (8/9) | ❌ FAIL |" in md_custom
    assert "| **Schema Conformance** | `90.0%` | `88.9%` | ❌ FAIL |" in md_custom
    assert "| **Vulnerability Recall** | `90.0%` | `85.7%` | ❌ FAIL |" in md_custom
    assert "| **Clean False Positive Rate** | `< 5.0%` | `0.0%` | ✅ PASS |" in md_custom
    assert "### ❌ Status: **EVALUATION FAILED / THRESHOLD BREACHED**" in md_custom


def test_threshold_breach_evaluation_at_85_percent():
    summary = EvalSuiteSummary(
        timestamp="2026-09-21T12:00:00Z",
        model_name="gemini-3.7-flash",
        total_cases=9,
        passed_cases=8,
        failed_cases=1,
        overall_pass_rate=round(8 / 9, 4),  # 0.8889 (88.9%)
        schema_conformance_rate=round(8 / 9, 4),  # 0.8889 (88.9%)
        vulnerability_recall=round(6 / 7, 4),  # 0.8571 (85.7%)
        clean_false_positive_rate=0.0,
        total_tokens=10000,
        total_cost_usd=0.015,
        avg_latency_seconds=3.5,
        case_metrics=[],
    )

    # 1. At 85% target: does NOT breach thresholds
    breached, reasons = evaluate_threshold_breach(
        summary,
        pass_threshold=0.85,
        schema_threshold=0.85,
        recall_threshold=0.85,
        fpr_threshold=0.05,
    )
    assert breached is False
    assert len(reasons) == 0

    # 2. At 90% target: DOES breach thresholds
    breached_90, reasons_90 = evaluate_threshold_breach(
        summary,
        pass_threshold=0.90,
        schema_threshold=0.90,
        recall_threshold=0.90,
        fpr_threshold=0.05,
    )
    assert breached_90 is True
    assert len(reasons_90) == 3
    assert any("Overall pass rate" in r for r in reasons_90)
    assert any("Schema conformance" in r for r in reasons_90)
    assert any("Vulnerability recall" in r for r in reasons_90)

    # 3. At 100% strict target: DOES breach thresholds
    breached_100, reasons_100 = evaluate_threshold_breach(
        summary,
        pass_threshold=1.0,
        schema_threshold=1.0,
        recall_threshold=1.0,
        fpr_threshold=0.05,
    )
    assert breached_100 is True
    assert len(reasons_100) == 3


def test_eval_runner_cli_threshold_flags(monkeypatch, tmp_path):
    metrics = []
    for i in range(8):
        metrics.append(
            EvalRunMetric(
                case_id=f"tc0{i+1}",
                name=f"case_{i+1}",
                category="clean" if i == 0 else "vulnerability",
                agent_target="pr_reviewer",
                duration_seconds=1.0,
                schema_valid=True,
                status_match=True,
                blocker_recall=1.0 if i > 0 else None,
                clean_fpr=0.0 if i == 0 else None,
                passed_all_assertions=True,
            )
        )
    metrics.append(
        EvalRunMetric(
            case_id="tc09_defect",
            name="case_9",
            category="vulnerability",
            agent_target="quality_gate",
            duration_seconds=1.0,
            schema_valid=True,
            status_match=False,
            blocker_recall=0.0,
            passed_all_assertions=False,
            failure_reasons=["Component mismatch"],
        )
    )
    # Total: 8/9 passed (88.9%), schema 9/9 valid (100%), recall 7/8 = 87.5%
    metrics_file = tmp_path / "eval-metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump([m.model_dump(mode="json") for m in metrics], f)

    # Under default 85% thresholds, CLI exits cleanly (exit code 0 / no sys.exit(1))
    monkeypatch.setattr(
        sys, "argv",
        ["eval_runner.py", "--output-dir", str(tmp_path), "--fail-on-threshold-breach"]
    )
    main()

    # Under 90% pass rate threshold, CLI exits with sys.exit(1)
    monkeypatch.setattr(
        sys, "argv",
        [
            "eval_runner.py",
            "--output-dir", str(tmp_path),
            "--fail-on-threshold-breach",
            "--pass-rate-threshold", "0.90",
        ]
    )
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
