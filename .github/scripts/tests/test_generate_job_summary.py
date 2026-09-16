"""Unit tests for generate_job_summary.py."""

import json
import sys
from pathlib import Path
import pytest

# Add .github/scripts to PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generate_job_summary import (
    generate_status_and_failure_summary,
    generate_release_decision_section,
    generate_token_usage_section,
    generate_prompt_audit_section,
    generate_artifacts_section,
    build_job_summary,
)


def test_status_passed(tmp_path: Path):
    gate_decision = tmp_path / "gate-decision.json"
    gate_decision.write_text(json.dumps({"passed": True, "summary": "All good", "failures": []}))
    decision_txt = tmp_path / "decision.txt"
    decision_txt.write_text("GATE_PASSED\nAll good")
    pii_scan = tmp_path / "pii-scan.txt"

    lines = generate_status_and_failure_summary(gate_decision, decision_txt, pii_scan)
    content = "\n".join(lines)
    assert "GATE PASSED" in content
    assert "GATE FAILED" not in content


def test_status_failed_with_structured_violations(tmp_path: Path):
    gate_decision = tmp_path / "gate-decision.json"
    gate_decision.write_text(
        json.dumps({
            "passed": False,
            "summary": "Quality gate failed with 1 blocking violation(s).",
            "failures": [
                {
                    "category": "PII_LEAK",
                    "component": "Cloud DLP Scan",
                    "severity": "CRITICAL",
                    "reason": "Hardcoded SECRET_KEY in web/settings.py",
                    "remediation": "Move to Secret Manager",
                }
            ],
        })
    )
    decision_txt = tmp_path / "decision.txt"
    decision_txt.write_text("GATE_FAILED")
    pii_scan = tmp_path / "pii-scan.txt"

    lines = generate_status_and_failure_summary(gate_decision, decision_txt, pii_scan)
    content = "\n".join(lines)
    assert "GATE FAILED" in content
    assert "### ⚠️ Failure Summary" in content
    assert "**[CRITICAL] PII_LEAK** in `Cloud DLP Scan`" in content
    assert "Move to Secret Manager" in content


def test_status_failed_fallback_pii(tmp_path: Path):
    gate_decision = tmp_path / "missing-gate-decision.json"
    decision_txt = tmp_path / "missing-decision.txt"
    pii_scan = tmp_path / "pii-scan.txt"
    pii_scan.write_text("❌ Total PII findings detected: 1")

    lines = generate_status_and_failure_summary(gate_decision, decision_txt, pii_scan)
    content = "\n".join(lines)
    assert "GATE FAILED" in content
    assert "PII_LEAK" in content


def test_token_usage_table(tmp_path: Path):
    token_usage = tmp_path / "token-usage.json"
    token_usage.write_text(
        json.dumps({
            "model": "gemini-3.7-flash",
            "prompt_tokens": 1000,
            "cached_tokens": 200,
            "candidate_tokens": 300,
            "thought_tokens": 150,
            "total_tokens": 1300,
            "total_cost_usd": 0.001234,
            "stop_reason": "COMPLETED",
            "budget_exceeded": False,
        })
    )

    lines = generate_token_usage_section(token_usage)
    content = "\n".join(lines)
    assert "PR Reviewer Token Usage & Estimated Spend" in content
    assert "`gemini-3.7-flash`" in content
    assert "$0.001234" in content
    assert "1,300" in content


def test_prompt_audit_section(tmp_path: Path):
    meta_dir = tmp_path / "telemetry/pr_reviewer_agent"
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta_file = meta_dir / "prompt-metadata.json"
    meta_file.write_text(
        json.dumps({
            "name": "pr_reviewer",
            "version": "1.0.0",
            "sha256": "abcdef1234567890abcdef",
            "is_fallback": False,
        })
    )

    lines = generate_prompt_audit_section(tmp_path)
    content = "\n".join(lines)
    assert "PR Reviewer Agent" in content
    assert "`1.0.0`" in content
    assert "Standard" in content


def test_artifacts_section():
    lines = generate_artifacts_section(
        project_id="test-proj",
        run_id="999",
        run_attempt="2",
    )
    content = "\n".join(lines)
    assert "gs://test-proj-scan-reports/999_2" in content


def test_build_full_job_summary(tmp_path: Path):
    gate_decision = tmp_path / "gate-decision.json"
    gate_decision.write_text(
        json.dumps({"passed": True, "summary": "All checks passed.", "failures": []})
    )
    decision_txt = tmp_path / "decision.txt"
    decision_txt.write_text("GATE_PASSED\nAll checks passed.")

    summary = build_job_summary(
        reports_dir=tmp_path,
        project_id="my-project",
        run_id="123",
        run_attempt="1",
    )

    assert "## 🛡️ Antigravity CI/CD Quality Gate Summary" in summary
    assert "GATE PASSED" in summary
    assert "gs://my-project-scan-reports/123_1" in summary
