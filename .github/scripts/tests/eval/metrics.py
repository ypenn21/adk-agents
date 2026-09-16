"""Metric Calculation Functions & Assertion Evaluator for LLM Inference Testing.

Provides pure scoring and evaluation functions:
- calculate_schema_conformance
- calculate_vulnerability_recall
- calculate_clean_false_positive_rate
- calculate_total_and_average_spend
- evaluate_case_assertions
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure .github/scripts is on sys.path
_scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

# Ensure .github/scripts/tests/eval is on sys.path
_eval_dir = os.path.abspath(os.path.dirname(__file__))
if _eval_dir not in sys.path:
    sys.path.insert(0, _eval_dir)

from pr_reviewer_agent import ReviewStatus, PRFindingSeverity, PRReviewReport, InlineFinding
from quality_gate_agent import SeverityLevel, ViolationCategory, QualityGateDecision
from evalset_schema import (
    EvalCase,
    EvalRunMetric,
    ExpectedFindingAssertion,
    ExpectedReviewAssertion,
    ExpectedGateAssertion,
)

__all__ = [
    "PROMPT_COST_PER_MILLION",
    "CACHED_COST_PER_MILLION",
    "OUTPUT_COST_PER_MILLION",
    "calculate_schema_conformance",
    "calculate_vulnerability_recall",
    "calculate_clean_false_positive_rate",
    "calculate_total_and_average_spend",
    "evaluate_case_assertions",
]

# Standard pricing for Gemini 3.7/3.8 Flash ($/1M tokens)
PROMPT_COST_PER_MILLION: float = 0.75
CACHED_COST_PER_MILLION: float = 0.075
OUTPUT_COST_PER_MILLION: float = 3.75


def calculate_schema_conformance(results: List[EvalRunMetric]) -> float:
    """Calculates the proportion of evaluation runs adhering to the Pydantic schema.

    Returns 1.0 if results is empty (graceful zero-division handling).
    """
    if not results:
        return 1.0
    valid_count = sum(1 for r in results if r.schema_valid)
    return round(valid_count / len(results), 4)


def calculate_vulnerability_recall(results: List[EvalRunMetric]) -> float:
    """Calculates vulnerability & blocker recall rate across defect cases (Y=1).

    Target is 1.0 (100% recall). Returns 1.0 if no defect cases are present.
    """
    defect_results = [
        r
        for r in results
        if r.blocker_recall is not None
        or r.category.lower()
        in {
            "secret_leak",
            "vulnerability",
            "sql_injection",
            "logic_defect",
            "fail_closed",
            "blocker_alignment",
            "defect",
        }
    ]
    if not defect_results:
        return 1.0

    recalled_sum = 0.0
    for r in defect_results:
        if r.blocker_recall is not None:
            recalled_sum += float(r.blocker_recall)
        else:
            # Fallback if blocker_recall was not explicitly computed
            is_recalled = r.status_match and (r.detected_blockers > 0 or not r.passed_all_assertions)
            recalled_sum += 1.0 if is_recalled else 0.0

    return round(recalled_sum / len(defect_results), 4)


def calculate_clean_false_positive_rate(results: List[EvalRunMetric]) -> float:
    """Calculates clean false positive rate across clean test cases (Y=0).

    Target is < 0.05 (<5% FPR). Returns 0.0 if no clean cases are present.
    """
    clean_results = [
        r for r in results if r.clean_fpr is not None or r.category.lower() == "clean"
    ]
    if not clean_results:
        return 0.0

    fpr_sum = 0.0
    for r in clean_results:
        if r.clean_fpr is not None:
            fpr_sum += float(r.clean_fpr)
        else:
            is_fp = not r.status_match or r.detected_blockers > 0
            fpr_sum += 1.0 if is_fp else 0.0

    return round(fpr_sum / len(clean_results), 4)


def calculate_total_and_average_spend(results: List[EvalRunMetric]) -> Dict[str, float]:
    """Calculates total and average token consumption, dollar cost, and latency.

    Pricing matches Gemini 3.7/3.8 Flash rates:
      - Prompt tokens: $0.75 / 1M
      - Cached content tokens: $0.075 / 1M
      - Candidate / thought tokens: $3.75 / 1M
    """
    if not results:
        return {
            "total_cost_usd": 0.0,
            "avg_cost_usd": 0.0,
            "total_prompt_tokens": 0.0,
            "total_candidate_tokens": 0.0,
            "total_cached_tokens": 0.0,
            "total_thought_tokens": 0.0,
            "total_tokens": 0.0,
            "avg_tokens": 0.0,
            "avg_latency_seconds": 0.0,
        }

    n = len(results)
    total_prompt = sum(r.prompt_tokens for r in results)
    total_candidate = sum(r.candidate_tokens for r in results)
    total_cached = sum(r.cached_tokens for r in results)
    total_thought = sum(r.thought_tokens for r in results)
    total_tokens = sum(r.total_tokens for r in results)
    total_cost = sum(r.cost_usd for r in results)
    total_latency = sum(r.duration_seconds for r in results)

    return {
        "total_cost_usd": round(total_cost, 6),
        "avg_cost_usd": round(total_cost / n, 6),
        "total_prompt_tokens": float(total_prompt),
        "total_candidate_tokens": float(total_candidate),
        "total_cached_tokens": float(total_cached),
        "total_thought_tokens": float(total_thought),
        "total_tokens": float(total_tokens),
        "avg_tokens": round(total_tokens / n, 2),
        "avg_latency_seconds": round(total_latency / n, 3),
    }


def _extract_token_val(data: Any, *keys: str) -> int:
    """Helper to extract integer token counts from dict or object."""
    for k in keys:
        if isinstance(data, dict):
            val = data.get(k)
        else:
            val = getattr(data, k, None)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return 0


def evaluate_case_assertions(
    case: EvalCase,
    report_or_decision: Any,
    duration: float,
    usage: Dict[str, Any],
) -> EvalRunMetric:
    """Evaluates output assertions for a single golden evaluation case.

    Validates schema conformance, verifies expected status and finding criteria,
    computes blocker recall or false positive rates, and records token spend.
    """
    # 1. Determine agent target
    if isinstance(report_or_decision, PRReviewReport) or (
        isinstance(report_or_decision, dict) and "overall_status" in report_or_decision
    ):
        agent_target = "pr_reviewer"
    elif isinstance(report_or_decision, QualityGateDecision) or (
        isinstance(report_or_decision, dict)
        and "passed" in report_or_decision
        and "failures" in report_or_decision
    ):
        agent_target = "quality_gate"
    elif case.expected_gate is not None and case.expected_review is None:
        agent_target = "quality_gate"
    else:
        agent_target = "pr_reviewer"

    schema_valid = False
    schema_error: Optional[str] = None
    parsed_report: Optional[PRReviewReport] = None
    parsed_decision: Optional[QualityGateDecision] = None

    # 2. Schema Deserialization and Invariant Validation
    if report_or_decision is None:
        schema_valid = False
        schema_error = "Response object is None"
    elif agent_target == "pr_reviewer":
        if isinstance(report_or_decision, PRReviewReport):
            parsed_report = report_or_decision
            schema_valid = True
        elif isinstance(report_or_decision, dict):
            try:
                parsed_report = PRReviewReport.model_validate(report_or_decision)
                schema_valid = True
            except Exception as exc:
                schema_valid = False
                schema_error = f"PRReviewReport validation failed: {exc}"
        else:
            schema_valid = False
            schema_error = f"Expected PRReviewReport or dict, got {type(report_or_decision).__name__}"
    else:  # quality_gate
        if isinstance(report_or_decision, QualityGateDecision):
            parsed_decision = report_or_decision
            schema_valid = True
        elif isinstance(report_or_decision, dict):
            try:
                parsed_decision = QualityGateDecision.model_validate(report_or_decision)
                schema_valid = True
            except Exception as exc:
                schema_valid = False
                schema_error = f"QualityGateDecision validation failed: {exc}"
        else:
            schema_valid = False
            schema_error = f"Expected QualityGateDecision or dict, got {type(report_or_decision).__name__}"

    failure_reasons: List[str] = []
    status_match = False
    findings_count = 0
    detected_blockers = 0

    # 3. Assertions Evaluation
    if not schema_valid:
        failure_reasons.append(schema_error or "Unknown schema error")
        status_match = False
    elif agent_target == "pr_reviewer" and parsed_report is not None:
        findings_count = len(parsed_report.findings)
        detected_blockers = sum(
            1
            for f in parsed_report.findings
            if f.severity == PRFindingSeverity.BLOCKER or f.pii_leak
        )

        if case.expected_review:
            er = case.expected_review

            # Status assertion
            if er.expected_status:
                status_match = parsed_report.overall_status in er.expected_status
                if not status_match:
                    expected_names = [
                        s.value if hasattr(s, "value") else str(s)
                        for s in er.expected_status
                    ]
                    actual_name = (
                        parsed_report.overall_status.value
                        if hasattr(parsed_report.overall_status, "value")
                        else str(parsed_report.overall_status)
                    )
                    failure_reasons.append(
                        f"Overall status '{actual_name}' not in expected {expected_names}"
                    )
            else:
                status_match = True

            # Findings count bounds
            if findings_count < er.min_findings:
                failure_reasons.append(
                    f"Findings count {findings_count} < min_findings {er.min_findings}"
                )
            if er.max_findings is not None and findings_count > er.max_findings:
                failure_reasons.append(
                    f"Findings count {findings_count} > max_findings {er.max_findings}"
                )

            # Blockers assertion
            actual_has_blockers = detected_blockers > 0
            if er.has_blockers is not None and actual_has_blockers != er.has_blockers:
                failure_reasons.append(
                    f"Expected has_blockers={er.has_blockers}, got {actual_has_blockers}"
                )

            # Required specific findings criteria
            severity_order = {
                PRFindingSeverity.INFO: 1,
                PRFindingSeverity.SUGGESTION: 2,
                PRFindingSeverity.WARNING: 3,
                PRFindingSeverity.BLOCKER: 4,
            }

            for idx, rf in enumerate(er.required_findings):
                found_match = False
                for f in parsed_report.findings:
                    if rf.file_path and rf.file_path.lower() not in f.file_path.lower():
                        continue
                    if rf.expected_severity and f.severity != rf.expected_severity:
                        continue
                    if rf.min_severity and severity_order.get(f.severity, 0) < severity_order.get(rf.min_severity, 0):
                        continue
                    if rf.keyword_in_title_or_details:
                        kw = rf.keyword_in_title_or_details.lower()
                        if kw not in f.title.lower() and kw not in f.details.lower():
                            continue
                    if rf.must_detect_pii is not None and f.pii_leak != rf.must_detect_pii:
                        continue
                    found_match = True
                    break

                if not found_match:
                    failure_reasons.append(
                        f"Required finding #{idx + 1} not met: {rf.model_dump(exclude_none=True)}"
                    )
        else:
            status_match = True

    elif agent_target == "quality_gate" and parsed_decision is not None:
        findings_count = len(parsed_decision.failures)
        detected_blockers = sum(
            1
            for f in parsed_decision.failures
            if f.severity in (SeverityLevel.CRITICAL, SeverityLevel.HIGH)
        )

        if case.expected_gate:
            eg = case.expected_gate
            status_match = parsed_decision.passed == eg.expected_passed
            if not status_match:
                failure_reasons.append(
                    f"Expected gate passed={eg.expected_passed}, got {parsed_decision.passed}"
                )

            if findings_count < eg.min_failures:
                failure_reasons.append(
                    f"Gate failure count {findings_count} < min_failures {eg.min_failures}"
                )
            if eg.max_failures is not None and findings_count > eg.max_failures:
                failure_reasons.append(
                    f"Gate failure count {findings_count} > max_failures {eg.max_failures}"
                )

            if eg.expected_failure_categories:
                actual_cats = {f.category for f in parsed_decision.failures}
                for cat in eg.expected_failure_categories:
                    if cat not in actual_cats:
                        failure_reasons.append(
                            f"Expected failure category '{cat}' not found in {actual_cats}"
                        )

            if eg.expected_severities:
                actual_sevs = {f.severity for f in parsed_decision.failures}
                for sev in eg.expected_severities:
                    if sev not in actual_sevs:
                        failure_reasons.append(
                            f"Expected failure severity '{sev}' not found in {actual_sevs}"
                        )

            if eg.keyword_in_summary_or_reason:
                kw = eg.keyword_in_summary_or_reason.lower()
                in_summary = kw in parsed_decision.summary.lower()
                in_failures = any(
                    kw in f.reason.lower() or kw in f.remediation.lower()
                    for f in parsed_decision.failures
                )
                if not (in_summary or in_failures):
                    failure_reasons.append(
                        f"Keyword '{eg.keyword_in_summary_or_reason}' not found in summary or failure reasons"
                    )
        else:
            status_match = True

    # 4. Blocker Recall & Clean False Positive Rate
    cat_lower = case.category.lower()
    blocker_recall: Optional[float] = None
    clean_fpr: Optional[float] = None

    if cat_lower == "clean":
        is_clean_pass = status_match and detected_blockers == 0 and len(failure_reasons) == 0
        clean_fpr = 0.0 if is_clean_pass else 1.0
        blocker_recall = None
    elif cat_lower in {
        "secret_leak",
        "vulnerability",
        "sql_injection",
        "logic_defect",
        "fail_closed",
        "blocker_alignment",
        "defect",
    }:
        clean_fpr = None
        if agent_target == "pr_reviewer":
            # Recall achieved if changes were requested and blocker/pii was flagged
            is_recalled = (
                schema_valid
                and status_match
                and (
                    detected_blockers > 0
                    or (parsed_report and parsed_report.overall_status == ReviewStatus.REQUEST_CHANGES)
                )
            )
            blocker_recall = 1.0 if is_recalled else 0.0
        else:  # quality_gate
            is_recalled = schema_valid and status_match and (parsed_decision and not parsed_decision.passed)
            blocker_recall = 1.0 if is_recalled else 0.0
    else:
        # Style, cosmetic or non-blocking cases
        clean_fpr = None
        blocker_recall = None

    # 5. Token and Cost Telemetry
    prompt_tokens = _extract_token_val(usage, "prompt_tokens", "prompt_token_count")
    cached_tokens = _extract_token_val(usage, "cached_tokens", "cached_content_token_count")
    candidate_tokens = _extract_token_val(usage, "candidate_tokens", "candidates_token_count")
    thought_tokens = _extract_token_val(usage, "thought_tokens", "thoughts_token_count")
    total_tokens = _extract_token_val(usage, "total_tokens", "total_token_count")

    if total_tokens == 0:
        total_tokens = prompt_tokens + candidate_tokens + thought_tokens

    # Compute USD cost using Gemini 3.7/3.8 Flash pricing rates
    net_prompt = max(0, prompt_tokens - cached_tokens)
    cost_usd = round(
        (net_prompt * (PROMPT_COST_PER_MILLION / 1_000_000.0))
        + (cached_tokens * (CACHED_COST_PER_MILLION / 1_000_000.0))
        + ((candidate_tokens + thought_tokens) * (OUTPUT_COST_PER_MILLION / 1_000_000.0)),
        6,
    )

    passed_all_assertions = schema_valid and len(failure_reasons) == 0

    return EvalRunMetric(
        case_id=case.case_id,
        name=case.name,
        category=case.category,
        agent_target=agent_target,
        duration_seconds=round(max(0.0, float(duration)), 3),
        schema_valid=schema_valid,
        schema_error=schema_error,
        status_match=status_match,
        blocker_recall=blocker_recall,
        clean_fpr=clean_fpr,
        findings_count=findings_count,
        detected_blockers=detected_blockers,
        prompt_tokens=prompt_tokens,
        candidate_tokens=candidate_tokens,
        cached_tokens=cached_tokens,
        thought_tokens=thought_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        passed_all_assertions=passed_all_assertions,
        failure_reasons=failure_reasons,
    )
