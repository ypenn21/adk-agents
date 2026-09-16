"""Pydantic schemas for the LLM Inference Evaluation Suite."""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path
from enum import Enum
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field, model_validator

# Ensure .github/scripts is on sys.path for direct module import
_scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

# Re-exporting from existing agents for seamless validation
from pr_reviewer_agent import ReviewStatus, PRFindingSeverity
from quality_gate_agent import SeverityLevel, ViolationCategory

__all__ = [
    "ExpectedFindingAssertion",
    "ExpectedReviewAssertion",
    "ExpectedGateAssertion",
    "EvalCase",
    "EvalRunMetric",
    "EvalSuiteSummary",
    "ReviewStatus",
    "PRFindingSeverity",
    "SeverityLevel",
    "ViolationCategory",
]


class ExpectedFindingAssertion(BaseModel):
    """Assertion criteria for an individual finding within PRReviewReport."""
    file_path: Optional[str] = None
    expected_severity: Optional[PRFindingSeverity] = None
    min_severity: Optional[PRFindingSeverity] = None
    keyword_in_title_or_details: Optional[str] = None
    must_detect_pii: Optional[bool] = None


class ExpectedReviewAssertion(BaseModel):
    """Expected outcome assertions for PRReviewReport."""
    expected_status: List[ReviewStatus] = Field(
        default_factory=lambda: [ReviewStatus.APPROVE]
    )
    min_findings: int = 0
    max_findings: Optional[int] = None
    has_blockers: Optional[bool] = None
    required_findings: List[ExpectedFindingAssertion] = Field(default_factory=list)


class ExpectedGateAssertion(BaseModel):
    """Expected outcome assertions for QualityGateDecision."""
    expected_passed: bool
    min_failures: int = 0
    max_failures: Optional[int] = None
    expected_failure_categories: List[ViolationCategory] = Field(default_factory=list)
    expected_severities: List[SeverityLevel] = Field(default_factory=list)
    keyword_in_summary_or_reason: Optional[str] = None


class EvalCase(BaseModel):
    """Schema representing a golden evaluation test case fixture."""
    case_id: str
    name: str
    description: str
    category: str  # "clean", "secret_leak", "vulnerability", "logic_defect", "style", "fail_closed"
    pr_number: str = "101"
    repo: str = "octocat/hello-world"
    diff_content: str
    modified_files: Dict[str, List[int]] = Field(default_factory=dict)
    file_tree: Dict[str, str] = Field(default_factory=dict)
    pii_scan_content: str = "✅ No sensitive data or PII detected by Cloud DLP."
    pr_review_content: Optional[str] = None
    expected_review: Optional[ExpectedReviewAssertion] = None
    expected_gate: Optional[ExpectedGateAssertion] = None

    @classmethod
    def from_file(cls, path: str | Path) -> "EvalCase":
        """Loads and validates an EvalCase fixture from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)

    def to_file(self, path: str | Path) -> None:
        """Saves an EvalCase fixture to a formatted JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))
            f.write("\n")


class EvalRunMetric(BaseModel):
    """Execution telemetry and assertion results for a single test case run."""
    case_id: str
    name: str
    category: str
    agent_target: str  # "pr_reviewer" or "quality_gate"
    duration_seconds: float
    schema_valid: bool
    schema_error: Optional[str] = None
    status_match: bool
    blocker_recall: Optional[float] = None
    clean_fpr: Optional[float] = None
    findings_count: int = 0
    detected_blockers: int = 0
    prompt_tokens: int = 0
    candidate_tokens: int = 0
    cached_tokens: int = 0
    thought_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    passed_all_assertions: bool
    failure_reasons: List[str] = Field(default_factory=list)


class EvalSuiteSummary(BaseModel):
    """Consolidated summary of an entire evaluation execution suite."""
    timestamp: str
    model_name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    overall_pass_rate: float
    schema_conformance_rate: float
    vulnerability_recall: float
    clean_false_positive_rate: float
    total_tokens: int
    total_cost_usd: float
    avg_latency_seconds: float
    prompt_versions: Dict[str, str] = Field(default_factory=dict)
    case_metrics: List[EvalRunMetric] = Field(default_factory=list)
