"""Acceptance and Contract Tests for Quality Gate Decision Agent.

Cites Decisions from docs/spec.md (D-1, D-2, D-3, D-6, D-7, D-9, D-10).
"""

import os
import sys
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pydantic import ValidationError

# Ensure .github/scripts is on sys.path for direct module import
_scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import quality_gate_agent
from quality_gate_agent import (
    SeverityLevel,
    ViolationCategory,
    FailureDetail,
    QualityGateDecision,
    format_text_decision,
    evaluate_quality_gate,
)


def test_severity_level_enum_values():
    """Validates that SeverityLevel enum contains all expected tiers."""
    assert SeverityLevel.CRITICAL.value == "CRITICAL"  # D-3
    assert SeverityLevel.HIGH.value == "HIGH"  # D-3
    assert SeverityLevel.MEDIUM.value == "MEDIUM"  # D-3
    assert SeverityLevel.LOW.value == "LOW"  # D-3


def test_violation_category_enum_values():
    """Validates that ViolationCategory enum contains all expected categories."""
    assert ViolationCategory.PII_LEAK.value == "PII_LEAK"  # D-3
    assert ViolationCategory.CREDENTIAL_LEAK.value == "CREDENTIAL_LEAK"  # D-3
    assert ViolationCategory.SECURITY_VULNERABILITY.value == "SECURITY_VULNERABILITY"  # D-3
    assert ViolationCategory.ARCHITECTURAL_DEFECT.value == "ARCHITECTURAL_DEFECT"  # D-3


def test_failure_detail_schema():
    """Validates FailureDetail instantiation and serialization."""
    detail = FailureDetail(
        category=ViolationCategory.CREDENTIAL_LEAK,  # D-3
        component="config/keys.json",  # D-3
        severity=SeverityLevel.CRITICAL,  # D-3
        reason="Private key leaked in repo.",  # D-3
        remediation="Rotate private key and use Secret Manager.",  # D-3
    )
    assert detail.category == ViolationCategory.CREDENTIAL_LEAK  # D-3
    assert detail.component == "config/keys.json"  # D-3
    assert detail.severity == SeverityLevel.CRITICAL  # D-3
    assert detail.reason == "Private key leaked in repo."  # D-3
    assert detail.remediation == "Rotate private key and use Secret Manager."  # D-3


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
    with pytest.raises(ValidationError) as exc_info:
        QualityGateDecision(
            passed=True,  # D-3: Invalid state - cannot pass with failures
            summary="Invalid pass with failure.",
            failures=[failure],
        )
    assert "QualityGateDecision cannot be passed=True with non-empty failures" in str(exc_info.value)  # D-3


def test_quality_gate_decision_invariant_failed_with_empty_failures_raises():
    """Invariant: passed=False with empty failures must raise ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        QualityGateDecision(
            passed=False,  # D-3: Invalid state - cannot fail with empty failures
            summary="Invalid fail without failure details.",
            failures=[],
        )
    assert "QualityGateDecision cannot be passed=False with empty failures" in str(exc_info.value)  # D-3


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
    """Missing reports/pii-scan.txt must fail-closed with CRITICAL severity."""
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
    assert "missing, unreadable, or empty" in decision.failures[0].reason  # D-7
    assert os.path.exists("reports/gate-decision.json")  # D-6
    assert os.path.exists("reports/decision.txt")  # D-6


@pytest.mark.asyncio
async def test_evaluate_quality_gate_empty_pii_report_fails_closed(tmp_path, monkeypatch):
    """0-byte (empty) reports/pii-scan.txt must fail-closed with CRITICAL severity."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    empty_scan = reports_dir / "pii-scan.txt"
    empty_scan.write_text("", encoding="utf-8")  # D-7: 0-byte file

    decision = await evaluate_quality_gate(
        pii_report_path=str(empty_scan),  # D-7
        pr_review_path=str(reports_dir / "pr-review.txt"),
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
    assert any(f.component == "PR Reviewer" for f in decision.failures)  # D-7


@pytest.mark.asyncio
async def test_evaluate_quality_gate_mock_agent_clean_pass(tmp_path, monkeypatch):
    """Scenario 1: Mocked Antigravity Agent returns clean passing decision."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    pii_scan = reports_dir / "pii-scan.txt"
    pii_scan.write_text("✅ No sensitive data or PII detected by Cloud DLP.\n", encoding="utf-8")
    pr_review = reports_dir / "pr-review.txt"
    pr_review.write_text("All checks passed", encoding="utf-8")

    expected_decision = QualityGateDecision(
        passed=True,
        summary="All quality and security criteria passed cleanly in automated review.",
        failures=[],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_decision)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    with patch.object(quality_gate_agent, "Agent", return_value=mock_agent_instance):
        decision = await evaluate_quality_gate(
            pii_report_path=str(pii_scan),
            pr_review_path=str(pr_review),
            project_id="test-project",
            location="us-central1",
            pr_number="10",
        )

    assert decision.passed is True  # D-3
    assert len(decision.failures) == 0  # D-3
    assert os.path.exists("reports/gate-decision.json")  # D-6
    with open("reports/gate-decision.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["passed"] is True  # D-3, D-6
    with open("reports/decision.txt", "r", encoding="utf-8") as f:
        text = f.read()
        assert text.startswith("GATE_PASSED\n\n")  # D-6


@pytest.mark.asyncio
async def test_evaluate_quality_gate_mock_agent_security_failure(tmp_path, monkeypatch):
    """Scenario 2: Mocked Antigravity Agent returns security failure decision."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    pii_scan = reports_dir / "pii-scan.txt"
    pii_scan.write_text("⚠️ [PII DETECTED] fixtures/usage.csv (1 findings)", encoding="utf-8")
    pr_review = reports_dir / "pr-review.txt"
    pr_review.write_text("Findings present", encoding="utf-8")

    expected_decision = QualityGateDecision(
        passed=False,
        summary="Security failure detected: API key in fixtures/usage.csv.",
        failures=[
            FailureDetail(
                category=ViolationCategory.PII_LEAK,
                component="fixtures/usage.csv",
                severity=SeverityLevel.CRITICAL,
                reason="Detected API_KEY in CSV fixture",
                remediation="Redact key and use mock token",
            )
        ],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_decision)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    with patch.object(quality_gate_agent, "Agent", return_value=mock_agent_instance):
        decision = await evaluate_quality_gate(
            pii_report_path=str(pii_scan),
            pr_review_path=str(pr_review),
            project_id="test-project",
            location="us-central1",
            pr_number="10",
        )

    assert decision.passed is False  # D-3
    assert len(decision.failures) == 1  # D-3
    assert decision.failures[0].category == ViolationCategory.PII_LEAK  # D-3
    assert os.path.exists("reports/gate-decision.json")  # D-6
    with open("reports/gate-decision.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["passed"] is False  # D-3, D-6
        assert len(data["failures"]) == 1  # D-3, D-6
    with open("reports/decision.txt", "r", encoding="utf-8") as f:
        text = f.read()
        assert text.startswith("GATE_FAILED\n\n")  # D-6
        assert "[CRITICAL] PII_LEAK in fixtures/usage.csv" in text  # D-6


@pytest.mark.asyncio
async def test_evaluate_quality_gate_telemetry_directory_created(tmp_path, monkeypatch):
    """Validates telemetry directory is created at reports/telemetry/quality_gate_agent."""
    monkeypatch.chdir(tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    pii_scan = reports_dir / "pii-scan.txt"
    pii_scan.write_text("No findings", encoding="utf-8")

    await evaluate_quality_gate(
        pii_report_path=str(pii_scan),
        pr_review_path=str(reports_dir / "pr-review.txt"),
        project_id="test-project",
        location="us-central1",
        pr_number=None,
    )

    assert os.path.isdir("reports/telemetry/quality_gate_agent")  # D-10


@pytest.mark.asyncio
async def test_evaluate_quality_gate_model_selection_from_env_var(tmp_path, monkeypatch):
    """Validates that evaluate_quality_gate honors LLM_Model environment variable."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_Model", "gemini-2.5-pro")
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    pii_scan = reports_dir / "pii-scan.txt"
    pii_scan.write_text("No findings", encoding="utf-8")
    (reports_dir / "pr-review.txt").write_text("Clean review", encoding="utf-8")

    expected_decision = QualityGateDecision(
        passed=True,
        summary="All quality and security criteria passed cleanly.",
        failures=[],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_decision)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    with patch.object(quality_gate_agent, "Agent", return_value=mock_agent_instance) as mock_agent_cls:
        await evaluate_quality_gate(
            pii_report_path=str(pii_scan),
            pr_review_path=str(reports_dir / "pr-review.txt"),
            project_id="test-project",
            location="us-central1",
            pr_number="10",
        )

        mock_agent_cls.assert_called_once()
        captured_config = mock_agent_cls.call_args[0][0]

    assert captured_config.model == "gemini-2.5-pro"


@pytest.mark.asyncio
async def test_evaluate_quality_gate_model_selection_explicit_arg(tmp_path, monkeypatch):
    """Validates that explicit model argument overrides LLM_Model environment variable."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_Model", "gemini-2.5-pro")
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    pii_scan = reports_dir / "pii-scan.txt"
    pii_scan.write_text("No findings", encoding="utf-8")
    (reports_dir / "pr-review.txt").write_text("Clean review", encoding="utf-8")

    expected_decision = QualityGateDecision(
        passed=True,
        summary="All quality and security criteria passed cleanly.",
        failures=[],
    )

    mock_response = MagicMock()
    mock_response.structured_output = AsyncMock(return_value=expected_decision)
    mock_agent_instance = MagicMock()
    mock_agent_instance.__aenter__ = AsyncMock(return_value=mock_agent_instance)
    mock_agent_instance.__aexit__ = AsyncMock(return_value=None)
    mock_agent_instance.chat = AsyncMock(return_value=mock_response)

    with patch.object(quality_gate_agent, "Agent", return_value=mock_agent_instance) as mock_agent_cls:
        await evaluate_quality_gate(
            pii_report_path=str(pii_scan),
            pr_review_path=str(reports_dir / "pr-review.txt"),
            project_id="test-project",
            location="us-central1",
            pr_number="10",
            model="gemini-custom-model",
        )

        mock_agent_cls.assert_called_once()
        captured_config = mock_agent_cls.call_args[0][0]

    assert captured_config.model == "gemini-custom-model"

