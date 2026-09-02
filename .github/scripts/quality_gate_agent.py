"""Quality Gate Decision Agent using Antigravity Python SDK with Vertex AI ADC and Pydantic.

Evaluates security scans (Cloud DLP) and automated PR reviews to determine whether
a build meets production release criteria. Reusable logic is extracted into helper.py.
"""

from __future__ import annotations

import os
import sys
import asyncio
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator
try:
    from google.antigravity import Agent, LocalAgentConfig, types
except ImportError:
    Agent = None
    class LocalAgentConfig:  # type: ignore
        def __init__(self, **kwargs: Any):
            for k, v in kwargs.items():
                setattr(self, k, v)
    from helper import types
    if "google.antigravity" in sys.modules:
        sys.modules["google.antigravity"].Agent = Agent
        sys.modules["google.antigravity"].LocalAgentConfig = LocalAgentConfig
        sys.modules["google.antigravity"].types = types

from helper import (
    format_text_decision,
    write_gate_reports,
    resolve_env_config,
    ensure_directory,
    read_text_file,
    parse_agent_structured_output,
)

__all__ = [
    "SeverityLevel",
    "ViolationCategory",
    "FailureDetail",
    "QualityGateDecision",
    "format_text_decision",
    "write_gate_reports",
    "evaluate_quality_gate",
    "build_quality_gate_prompt",
    "main",
]


class SeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ViolationCategory(str, Enum):
    PII_LEAK = "PII_LEAK"
    CREDENTIAL_LEAK = "CREDENTIAL_LEAK"
    SECURITY_VULNERABILITY = "SECURITY_VULNERABILITY"
    ARCHITECTURAL_DEFECT = "ARCHITECTURAL_DEFECT"


class FailureDetail(BaseModel):
    category: ViolationCategory
    component: str
    severity: SeverityLevel
    reason: str
    remediation: str


class QualityGateDecision(BaseModel):
    passed: bool
    summary: str
    failures: list[FailureDetail] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_failures_consistency(self) -> "QualityGateDecision":
        if self.passed and len(self.failures) > 0:
            raise ValueError(
                "QualityGateDecision cannot be passed=True with non-empty failures"
            )
        if not self.passed and len(self.failures) == 0:
            raise ValueError(
                "QualityGateDecision cannot be passed=False with empty failures"
            )
        return self


QUALITY_GATE_SYSTEM_INSTRUCTIONS = (
    "You are a Lead Release Engineer and Security Gatekeeper. "
    "Evaluate combined DLP and PR code review reports against release criteria.\n"
    "Quality Gate Criteria:\n"
    "1. ZERO PII, credential, or authentication token leaks detected by Cloud DLP.\n"
    "2. PR Code Review contains no unresolved blocking architectural or critical security failures."
)


def build_quality_gate_prompt(pii_content: str, pr_review_content: str) -> str:
    """Builds prompt for Quality Gate LLM evaluation."""
    return f"""You are the Quality Gate Decision Agent.
Evaluate the following security scans and PR code review outputs:

=== CLOUD DLP SCAN REPORT ===
{pii_content}

=== PR CODE REVIEW REPORT ===
{pr_review_content}

Evaluate if the build passes or fails release criteria.
Fail the gate if any sensitive data, credentials, or blocker review items exist.
Return a structured QualityGateDecision response.
"""


async def evaluate_quality_gate(
    pii_report_path: str = "reports/pii-scan.txt",
    pr_review_path: str = "reports/pr-review.txt",
    project_id: Optional[str] = None,
    location: str = "us-central1",
    pr_number: Optional[str] = None,
    model: Optional[str] = None,
    enforce: bool = False,
) -> QualityGateDecision:
    """Evaluates combined scan and review reports against release criteria."""
    cfg = resolve_env_config(pr_number=pr_number, project_id=project_id, location=location, model=model)
    pr_num = cfg["pr_number"]
    telemetry_dir = ensure_directory("reports/telemetry/quality_gate_agent")

    # 1. Fail-Closed Check on Cloud DLP Scan Report (Decision D-7)
    if not os.path.exists(pii_report_path) or os.path.getsize(pii_report_path) == 0:
        decision = QualityGateDecision(
            passed=False,
            summary="Quality Gate Failed: Required Cloud DLP scan report is missing, unreadable, or empty.",
            failures=[
                FailureDetail(
                    category=ViolationCategory.SECURITY_VULNERABILITY,
                    component="Cloud DLP",
                    severity=SeverityLevel.CRITICAL,
                    reason="Required Cloud DLP scan report (reports/pii-scan.txt) is missing, unreadable, or empty",
                    remediation="Ensure Cloud DLP scan step executes successfully before quality gate evaluation",
                )
            ],
        )
        write_gate_reports(decision)
        return decision

    pii_content = read_text_file(pii_report_path)

    # 2. Check PR Review Report (Decision D-7)
    if not os.path.exists(pr_review_path):
        if not pr_num:
            pr_review_content = "No PR review report available (push event or non-PR)."
        else:
            decision = QualityGateDecision(
                passed=False,
                summary="Quality gate failed: PR review report is missing on an active pull request.",
                failures=[
                    FailureDetail(
                        category=ViolationCategory.SECURITY_VULNERABILITY,
                        component="PR Reviewer",
                        severity=SeverityLevel.HIGH,
                        reason="PR review report (reports/pr-review.txt) was not generated for pull request.",
                        remediation="Ensure PR Reviewer Agent runs before Quality Gate on pull requests.",
                    )
                ],
            )
            write_gate_reports(decision)
            return decision
    else:
        pr_review_content = read_text_file(pr_review_path)

    # 3. Analyze contents for violations
    pii_has_violations = (
        "PII finding" in pii_content
        or "AUTH_TOKEN" in pii_content
        or "API_KEY" in pii_content
        or "SECRET" in pii_content.upper()
        or "EMAIL_ADDRESS" in pii_content
        or "Violations detected" in pii_content
        or ("0 findings" not in pii_content and "No sensitive data" not in pii_content and "clean" not in pii_content.lower())
    )

    pr_has_blockers = (
        "REQUEST_CHANGES" in pr_review_content
        or "[BLOCKER]" in pr_review_content
    )

    failures: list[FailureDetail] = []

    if pii_has_violations and "No sensitive data" not in pii_content:
        failures.append(
            FailureDetail(
                category=ViolationCategory.PII_LEAK,
                component="Cloud DLP Scan",
                severity=SeverityLevel.CRITICAL,
                reason="Sensitive data or credential findings detected in repository files.",
                remediation="Remove sensitive data, rotate exposed secrets, and store credentials in Secret Manager.",
            )
        )

    if pr_has_blockers:
        failures.append(
            FailureDetail(
                category=ViolationCategory.ARCHITECTURAL_DEFECT,
                component="PR Code Review",
                severity=SeverityLevel.CRITICAL,
                reason="Automated PR code review requested changes with blocking findings.",
                remediation="Address line-level PR code review comments before merge.",
            )
        )

    # 4. Attempt to invoke Antigravity SDK Agent
    try:
        if Agent is None:
            raise RuntimeError("Antigravity SDK is not available")
        prompt = build_quality_gate_prompt(pii_content, pr_review_content)
        config = LocalAgentConfig(
            vertex=True,
            project=cfg["project_id"],
            location=cfg["location"],
            model=cfg["model"],
            response_schema=QualityGateDecision,
            app_data_dir=telemetry_dir,
            system_instructions=QUALITY_GATE_SYSTEM_INSTRUCTIONS,
        )
        async with Agent(config) as agent:
            response = await agent.chat(prompt)
            raw_output = await response.structured_output()
            decision = parse_agent_structured_output(raw_output, QualityGateDecision)
            write_gate_reports(decision)
            return decision
    except Exception:
        # Fallback to deterministic evaluation
        pass

    if failures:
        decision = QualityGateDecision(
            passed=False,
            summary=f"Quality gate failed with {len(failures)} blocking violation(s).",
            failures=failures,
        )
    else:
        decision = QualityGateDecision(
            passed=True,
            summary="All quality and security checks passed cleanly.",
            failures=[],
        )

    write_gate_reports(decision)
    return decision


async def main() -> None:
    """CLI entry point for Quality Gate Agent."""
    pii_report = sys.argv[1] if len(sys.argv) > 1 else "reports/pii-scan.txt"
    pr_review = sys.argv[2] if len(sys.argv) > 2 else "reports/pr-review.txt"
    pr_num = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("PULL_REQUEST_NUMBER")

    decision = await evaluate_quality_gate(
        pii_report_path=pii_report,
        pr_review_path=pr_review,
        pr_number=pr_num,
    )

    print(f"Quality Gate Status: {'PASSED' if decision.passed else 'FAILED'}")
    print(f"Summary: {decision.summary}")
    # Always exit 0 so workflow can upload telemetry (Decision D-9)
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
