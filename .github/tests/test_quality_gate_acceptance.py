"""Acceptance and Contract Tests for Quality Gate Decision Agent.

Cites Decisions from docs/spec.md (D-1, D-2, D-3, D-6, D-7, D-9, D-10).
"""

import os
import json
import pytest
from pydantic import ValidationError
try:
    from .github.scripts.quality_gate_agent import (
        SeverityLevel,
        ViolationCategory,
        FailureDetail,
        QualityGateDecision,
        format_text_decision,
        evaluate_quality_gate,
    )
except (ImportError, ModuleNotFoundError):
    import importlib.util
    import sys
    _spec_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "quality_gate_agent.py"))
    _spec = importlib.util.spec_from_file_location("quality_gate_agent", _spec_path)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["quality_gate_agent"] = _mod
    _spec.loader.exec_module(_mod)
    SeverityLevel = _mod.SeverityLevel
    ViolationCategory = _mod.ViolationCategory
    FailureDetail = _mod.FailureDetail
    QualityGateDecision = _mod.QualityGateDecision
    format_text_decision = _mod.format_text_decision
    evaluate_quality_gate = _mod.evaluate_quality_gate


def test_quality_gate_decision_schema_valid_pass():
    """Validates that a passed decision with no failures satisfies schema."""
    decision = QualityGateDecision(
        passed=True,  # D-3
        summary="All quality and security checks passed cleanly.",  # D-3
        failures=[],  # D-3
    )
    assert decision.passed is True  # D-3
    assert len(decision.failures) == 0  # D-3
    assert "cleanly" in decision.summary  # D-3


def test_quality_gate_decision_schema_valid_fail():
    """Validates that a failed decision with structured failures satisfies schema."""
    failure = FailureDetail(
        category=ViolationCategory.PII_LEAK,  # D-3
        component="auth/credentials.py",  # D-3
        severity=SeverityLevel.CRITICAL,  # D-3
        reason="API key detected in source code.",  # D-3
        remediation="Remove hardcoded API key and use Secret Manager.",  # D-3
    )
    decision = QualityGateDecision(
        passed=False,  # D-3
        summary="PII violations detected by Cloud DLP.",  # D-3
        failures=[failure],  # D-3
    )
    assert decision.passed is False  # D-3
    assert len(decision.failures) == 1  # D-3
    assert decision.failures[0].category == ViolationCategory.PII_LEAK  # D-3
    assert decision.failures[0].severity == SeverityLevel.CRITICAL  # D-3


def test_quality_gate_decision_invariant_passed_with_failures_raises():
    """Invariant: passed=True with non-empty failures must raise ValidationError."""
    failure = FailureDetail(
        category=ViolationCategory.SECURITY_VULNERABILITY,  # D-3
        component="server.py",  # D-3
        severity=SeverityLevel.HIGH,  # D-3
        reason="Insecure endpoint exposed.",  # D-3
        remediation="Apply authentication middleware.",  # D-3
    )
    with pytest.raises(ValidationError):
        QualityGateDecision(
            passed=True,  # D-3: Invalid state - cannot pass with failures
            summary="Invalid pass with failure.",
            failures=[failure],
        )


def test_quality_gate_decision_invariant_failed_with_empty_failures_raises():
    """Invariant: passed=False with empty failures must raise ValidationError."""
    with pytest.raises(ValidationError):
        QualityGateDecision(
            passed=False,  # D-3: Invalid state - cannot fail with empty failures
            summary="Invalid fail without failure details.",
            failures=[],
        )


def test_format_text_decision_passed():
    """Validates formatting for a passing quality gate decision."""
    decision = QualityGateDecision(
        passed=True,  # D-3
        summary="Zero security or architectural violations detected.",  # D-3
        failures=[],  # D-3
    )
    text_output = format_text_decision(decision)  # D-6
    assert text_output.startswith("GATE_PASSED\n\n")  # D-6
    assert "Zero security or architectural violations detected." in text_output  # D-6


def test_format_text_decision_failed():
    """Validates formatting for a failing quality gate decision with failure list."""
    decision = QualityGateDecision(
        passed=False,  # D-3
        summary="Critical security violations detected.",  # D-3
        failures=[
            FailureDetail(
                category=ViolationCategory.CREDENTIAL_LEAK,  # D-3
                component="config/secrets.json",  # D-3
                severity=SeverityLevel.CRITICAL,  # D-3
                reason="Private key committed to repo.",  # D-3
                remediation="Revoke key and rotate credentials immediately.",  # D-3
            )
        ],
    )
    text_output = format_text_decision(decision)  # D-6
    assert text_output.startswith("GATE_FAILED\n\n")  # D-6
    assert "Critical security violations detected." in text_output  # D-6
    assert "[CRITICAL] CREDENTIAL_LEAK in config/secrets.json" in text_output  # D-6
    assert "Remediation: Revoke key and rotate credentials immediately." in text_output  # D-6


@pytest.mark.asyncio
async def test_evaluate_quality_gate_missing_pii_report_fails_closed(tmp_path, monkeypatch):
    """Missing or 0-byte reports/pii-scan.txt must fail-closed with CRITICAL severity."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    non_existent_scan = str(tmp_path / "reports" / "pii-scan.txt")  # D-7

    decision = await evaluate_quality_gate(
        pii_report_path=non_existent_scan,  # D-7
        pr_review_path=str(tmp_path / "reports" / "pr-review.txt"),
        project_id="test-project",
        location="us-central1",
    )

    assert decision.passed is False  # D-7
    assert len(decision.failures) >= 1  # D-7
    assert decision.failures[0].category == ViolationCategory.SECURITY_VULNERABILITY  # D-7
    assert decision.failures[0].severity == SeverityLevel.CRITICAL  # D-7
    assert decision.failures[0].component == "Cloud DLP"  # D-7


@pytest.mark.asyncio
async def test_evaluate_quality_gate_non_pr_event_missing_pr_review_passes(tmp_path, monkeypatch):
    """On push/non-PR events (pr_number=None), missing pr-review.txt does not fail gate."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    pii_scan = reports_dir / "pii-scan.txt"
    pii_scan.write_text("✅ No sensitive data or PII detected by Cloud DLP.\n", encoding="utf-8")  # D-7

    non_existent_pr_review = str(reports_dir / "pr-review.txt")  # D-7

    decision = await evaluate_quality_gate(
        pii_report_path=str(pii_scan),
        pr_review_path=non_existent_pr_review,
        project_id="test-project",
        location="us-central1",
        pr_number=None,  # D-5, D-7: Push event
    )

    assert decision.passed is True  # D-7
    assert len(decision.failures) == 0  # D-3, D-7
    assert os.path.exists("reports/gate-decision.json")  # D-6
    assert os.path.exists("reports/decision.txt")  # D-6


@pytest.mark.asyncio
async def test_evaluate_quality_gate_active_pr_event_missing_pr_review_fails(tmp_path, monkeypatch):
    """On active PR events (pr_number set), missing pr-review.txt fails the gate with HIGH severity."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    pii_scan = reports_dir / "pii-scan.txt"
    pii_scan.write_text("✅ No sensitive data or PII detected by Cloud DLP.\n", encoding="utf-8")  # D-7

    non_existent_pr_review = str(reports_dir / "pr-review.txt")  # D-7

    decision = await evaluate_quality_gate(
        pii_report_path=str(pii_scan),
        pr_review_path=non_existent_pr_review,
        project_id="test-project",
        location="us-central1",
        pr_number="42",  # D-7: Active PR event
    )

    assert decision.passed is False  # D-7
    assert any(f.severity in (SeverityLevel.CRITICAL, SeverityLevel.HIGH) for f in decision.failures)  # D-7
