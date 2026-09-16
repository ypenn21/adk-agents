"""Generate GitHub Actions Job Summary for Antigravity CI/CD Quality Gate.

Parses security scan reports, PR code reviews, gate decisions, token telemetry,
and prompt metadata into a structured GitHub Step Summary markdown report.
"""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any, List


def generate_status_and_failure_summary(
    gate_decision_path: Path,
    decision_txt_path: Path,
    pii_scan_path: Path,
) -> List[str]:
    """Generates the gate status header and detailed failure breakdown if failed."""
    lines: List[str] = []

    is_passed = False
    decision_data: Optional[Dict[str, Any]] = None

    if gate_decision_path.exists():
        try:
            with open(gate_decision_path, "r", encoding="utf-8") as f:
                decision_data = json.load(f)
            is_passed = bool(decision_data.get("passed", False))
        except Exception:
            is_passed = False
    elif decision_txt_path.exists():
        try:
            txt_content = decision_txt_path.read_text(encoding="utf-8")
            is_passed = "GATE_PASSED" in txt_content
        except Exception:
            is_passed = False

    if is_passed:
        lines.append("### ✅ Status: **GATE PASSED**\n")
        return lines

    lines.append("### ❌ Status: **GATE FAILED**\n")
    lines.append("### ⚠️ Failure Summary")

    if decision_data is not None:
        summary = decision_data.get("summary", "")
        failures = decision_data.get("failures", [])
        if summary:
            lines.append(f"**Reason:** {summary}\n")
        if failures:
            lines.append("**Violations:**")
            for f in failures:
                sev = f.get("severity", "CRITICAL")
                cat = f.get("category", "VIOLATION")
                comp = f.get("component", "Unknown")
                reason = f.get("reason", "")
                remediation = f.get("remediation", "")
                lines.append(f"- **[{sev}] {cat}** in `{comp}`: {reason}")
                if remediation:
                    lines.append(f"  - *Remediation*: {remediation}")
            lines.append("")
    elif decision_txt_path.exists():
        try:
            lines.append(decision_txt_path.read_text(encoding="utf-8").strip() + "\n")
        except Exception as err:
            lines.append(f"- Error reading decision text: {err}\n")
    elif pii_scan_path.exists():
        try:
            pii_text = pii_scan_path.read_text(encoding="utf-8")
            if "Total PII findings detected" in pii_text:
                lines.append(
                    "- **[CRITICAL] PII_LEAK**: Sensitive data or PII was detected during the Cloud DLP scan before the gate completed.\n"
                )
            else:
                lines.append("The quality gate evaluation halted before producing a decision artifact.\n")
        except Exception:
            lines.append("The quality gate evaluation halted before producing a decision artifact.\n")
    else:
        lines.append("The quality gate evaluation halted before producing a decision artifact.\n")

    return lines


def generate_release_decision_section(decision_txt_path: Path) -> List[str]:
    """Generates the verbatim release engineer decision block."""
    lines: List[str] = [
        "### 📋 Release Engineer Decision",
        "```",
    ]
    if decision_txt_path.exists():
        try:
            lines.append(decision_txt_path.read_text(encoding="utf-8").strip())
        except Exception as err:
            lines.append(f"Error reading decision report: {err}")
    else:
        lines.append("No decision report generated.")
    lines.extend(["```", ""])
    return lines


def generate_token_usage_section(token_usage_path: Path) -> List[str]:
    """Generates the PR Reviewer token consumption and spend table."""
    if not token_usage_path.exists():
        return []

    try:
        with open(token_usage_path, "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return []

    model = d.get("model", "gemini-3.7-flash")
    prompt = d.get("prompt_tokens", 0)
    cached = d.get("cached_tokens", 0)
    candidate = d.get("candidate_tokens", 0)
    thought = d.get("thought_tokens", 0)
    total = d.get("total_tokens", 0)
    cost = d.get("total_cost_usd", 0.0)
    stop = d.get("stop_reason", "COMPLETED")
    halted = "⚠️ **BUDGET EXCEEDED**" if d.get("budget_exceeded") else "✅ Normal"

    return [
        "### 📊 PR Reviewer Token Usage & Estimated Spend",
        "| Metric | Value |",
        "| :--- | :--- |",
        f"| **Model** | `{model}` |",
        f"| **Execution Status** | {halted} (`{stop}`) |",
        f"| **Prompt Tokens (Uncached)** | {max(0, prompt - cached):,} |",
        f"| **Cached Prompt Tokens** | {cached:,} |",
        f"| **Candidate Generation Tokens** | {candidate:,} |",
        f"| **Reasoning / Thought Tokens** | {thought:,} |",
        f"| **Total Tokens Billed** | **{total:,}** |",
        f"| **Estimated Spend (USD)** | **${cost:.6f}** |",
        "",
    ]


def generate_prompt_audit_section(reports_dir: Path) -> List[str]:
    """Generates the prompt template version, checksum, and mode audit table."""
    rows: List[str] = []
    agent_configs = [
        (
            "PR Reviewer Agent",
            [
                reports_dir / "telemetry/pr_reviewer_agent/prompt-metadata.json",
                reports_dir / "telemetry/pr_review_agent/prompt-metadata.json",
            ],
        ),
        (
            "Quality Gate Agent",
            [
                reports_dir / "telemetry/quality_gate_agent/prompt-metadata.json",
            ],
        ),
    ]

    for agent, paths in agent_configs:
        meta: Optional[Dict[str, Any]] = None
        for p in paths:
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    break
                except Exception:
                    pass
        if meta:
            ver = meta.get("version", "unknown")
            sha = meta.get("sha256", "none")
            sha_short = sha[:12] + "..." if len(sha) > 12 else sha
            mode = "Fallback (Built-in)" if meta.get("is_fallback") else "Standard"
            rows.append(f"| **{agent}** | `{ver}` | `{sha_short}` | {mode} |")

    lines: List[str] = ["### 📝 Prompt Template Audit"]
    if rows:
        lines.extend([
            "| Agent | Version | Checksum (SHA256) | Mode |",
            "| :--- | :--- | :--- | :--- |",
            *rows,
        ])
    else:
        lines.append("_No prompt metadata recorded for this run._")
    lines.append("")
    return lines


def generate_artifacts_section(
    project_id: Optional[str] = None,
    run_id: Optional[str] = None,
    run_attempt: Optional[str] = None,
) -> List[str]:
    """Generates the archived telemetry and report destination info."""
    if not project_id:
        return []

    r_id = run_id or "local"
    r_att = run_attempt or "1"
    destination = f"gs://{project_id}-scan-reports/{r_id}_{r_att}"
    return [
        "### 📦 Archived Artifacts",
        f"GCS Destination: `{destination}`",
        "",
    ]


def build_job_summary(
    reports_dir: Path | str = "reports",
    project_id: Optional[str] = None,
    run_id: Optional[str] = None,
    run_attempt: Optional[str] = None,
) -> str:
    """Builds the complete Markdown GitHub Actions Job Summary string."""
    rep_path = Path(reports_dir)
    gate_decision_path = rep_path / "gate-decision.json"
    decision_txt_path = rep_path / "decision.txt"
    pii_scan_path = rep_path / "pii-scan.txt"
    token_usage_path = rep_path / "token-usage.json"

    sections: List[str] = [
        "## 🛡️ Antigravity CI/CD Quality Gate Summary\n",
        *generate_status_and_failure_summary(
            gate_decision_path, decision_txt_path, pii_scan_path
        ),
        *generate_release_decision_section(decision_txt_path),
        *generate_token_usage_section(token_usage_path),
        *generate_prompt_audit_section(rep_path),
        *generate_artifacts_section(project_id, run_id, run_attempt),
    ]

    return "\n".join(sections).strip() + "\n"


def main() -> None:
    """CLI entrypoint: renders summary and writes to GITHUB_STEP_SUMMARY or prints."""
    reports_dir = os.environ.get("REPORTS_DIR", "reports")
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID")
    run_id = os.environ.get("GITHUB_RUN_ID")
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT")

    summary_content = build_job_summary(
        reports_dir=reports_dir,
        project_id=project_id,
        run_id=run_id,
        run_attempt=run_attempt,
    )

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(summary_content)
        print("✅ Successfully appended summary to GITHUB_STEP_SUMMARY.")
    else:
        print(summary_content)


if __name__ == "__main__":
    main()
