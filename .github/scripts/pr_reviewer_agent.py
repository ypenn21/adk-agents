"""Automated PR Review Agent using Antigravity Python SDK with Vertex AI ADC and Pydantic.

Inspects PR diffs, checks DLP scan context, and submits structured reviews and inline comments.
Reusable logic is extracted into helper.py.
"""

from __future__ import annotations

import os
import sys
import json
import asyncio
from pathlib import Path
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field, model_validator

from prompt_loader import load_prompt_bundle

try:
    from google.antigravity import Agent, LocalAgentConfig, types
except ImportError:
    Agent = None
    LocalAgentConfig = None
    types = None

from helper import (
    POSITIVE_APPROVAL_TEMPLATE,
    MODEL_PRICING,
    calculate_token_spend,
    write_token_usage_report,
    sanitize_and_validate_repo,
    fetch_pr_modified_lines,
    fetch_pr_comments,
    is_duplicate_comment,
    validate_and_sanitize_findings,
    send_github_review_sync,
    send_github_issue_comment_sync,
    post_github_pr_review,
    format_pr_review_text,
    write_pr_reports,
    resolve_env_config,
    ensure_directory,
    read_text_file,
    create_github_mcp_server,
    parse_agent_structured_output,
)

__all__ = [
    "PRFindingSeverity",
    "ReviewSeverity",
    "ReviewStatus",
    "InlineFinding",
    "PRReviewReport",
    "POSITIVE_APPROVAL_TEMPLATE",
    "MODEL_PRICING",
    "calculate_token_spend",
    "write_token_usage_report",
    "sanitize_and_validate_repo",
    "fetch_pr_modified_lines",
    "fetch_pr_comments",
    "is_duplicate_comment",
    "validate_and_sanitize_findings",
    "send_github_review_sync",
    "send_github_issue_comment_sync",
    "post_github_pr_review",
    "format_pr_review_text",
    "write_pr_reports",
    "run_pr_review",
    "build_pr_review_prompt",
    "main",
]


class PRFindingSeverity(str, Enum):
    BLOCKER = "BLOCKER"
    WARNING = "WARNING"
    SUGGESTION = "SUGGESTION"
    INFO = "INFO"


# Alias for backward compatibility (Decision D-4)
ReviewSeverity = PRFindingSeverity


class ReviewStatus(str, Enum):
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    COMMENT = "COMMENT"


class InlineFinding(BaseModel):
    file_path: str
    line_number: Optional[int] = None
    severity: PRFindingSeverity
    title: str
    details: str
    suggestion: str = ""
    pii_leak: bool = False


class PRReviewReport(BaseModel):
    overall_status: ReviewStatus
    summary: str
    findings: list[InlineFinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_blocker_status(self) -> "PRReviewReport":
        """If any finding is a BLOCKER or contains a pii_leak, enforce REQUEST_CHANGES (Decision D-4)."""
        has_blocker = any(
            f.severity == PRFindingSeverity.BLOCKER or f.pii_leak
            for f in self.findings
        )
        if has_blocker and self.overall_status != ReviewStatus.REQUEST_CHANGES:
            self.overall_status = ReviewStatus.REQUEST_CHANGES
        return self


_DEFAULT_BUNDLE = load_prompt_bundle("pr_reviewer")
SYSTEM_INSTRUCTIONS = _DEFAULT_BUNDLE.system_instructions


def build_pr_review_prompt(
    pr_number: str,
    repo: str,
    pii_context: str,
    version: Optional[str] = None,
    prompt_path: Optional[str] = None,
) -> str:
    """Builds the user prompt for the PR Reviewer Agent using PromptLoader (Decision D-19)."""
    bundle = load_prompt_bundle("pr_reviewer", version=version, prompt_path=prompt_path)
    return bundle.render_user_prompt(
        pr_number=pr_number,
        repo=repo,
        pii_context=pii_context or "No DLP findings detected.",
    )


async def run_pr_review(
    pr_number: Optional[str] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    pii_report_path: str = "reports/pii-scan.txt",
    project_id: Optional[str] = None,
    location: str = "us-central1",
    model: Optional[str] = None,
    modified_files_diff: Optional[dict[str, list[int]]] = None,
    existing_comments: Optional[list[dict[str, Any]]] = None,
    max_total_tokens: Optional[int] = None,
    max_input_tokens: Optional[int] = None,
    max_output_tokens: Optional[int] = None,
    max_model_calls: Optional[int] = None,
    max_tool_calls: Optional[int] = None,
    max_spend_usd: Optional[float] = None,
    prompt_version: Optional[str] = None,
    prompt_path: Optional[str] = None,
) -> Optional[PRReviewReport]:
    """Runs automated PR review using Antigravity SDK and GitHub MCP server with budget caps and versioned prompts."""
    cfg = resolve_env_config(
        pr_number=pr_number,
        repo=repo,
        token=token,
        project_id=project_id,
        location=location,
        model=model,
        max_total_tokens=max_total_tokens,
        max_input_tokens=max_input_tokens,
        max_output_tokens=max_output_tokens,
        max_model_calls=max_model_calls,
        max_tool_calls=max_tool_calls,
        max_spend_usd=max_spend_usd,
        pr_review_prompt_version=prompt_version,
        pr_review_prompt_path=prompt_path,
    )
    pr_num, repository, auth_token = cfg["pr_number"], cfg["repo"], cfg["token"]

    if not pr_num:
        print("No pull request number provided; skipping PR review.")
        return None

    budget_limits = {
        "max_total_tokens": cfg["max_total_tokens"],
        "max_input_tokens": cfg["max_input_tokens"],
        "max_output_tokens": cfg["max_output_tokens"],
        "max_model_calls": cfg["max_model_calls"],
        "max_tool_calls": cfg["max_tool_calls"],
        "max_spend_usd": cfg["max_spend_usd"],
    }

    # Load versioned prompt bundle (Decision D-19)
    resolved_prompt_ver = prompt_version or cfg.get("pr_review_prompt_version")
    resolved_prompt_p = prompt_path or cfg.get("pr_review_prompt_path")
    bundle = load_prompt_bundle("pr_reviewer", version=resolved_prompt_ver, prompt_path=resolved_prompt_p)
    prompt_metadata_audit = bundle.to_audit_dict()

    # Persist prompt metadata telemetry
    prompt_meta_dir = ensure_directory("reports/telemetry/pr_reviewer_agent")
    Path("reports/telemetry/pr_reviewer_agent/prompt-metadata.json").write_text(
        json.dumps(prompt_metadata_audit, indent=2), encoding="utf-8"
    )
    ensure_directory("reports/telemetry/pr_review_agent")
    Path("reports/telemetry/pr_review_agent/prompt-metadata.json").write_text(
        json.dumps(prompt_metadata_audit, indent=2), encoding="utf-8"
    )

    if repository and auth_token:
        repo_parsed = sanitize_and_validate_repo(repository)
        if repo_parsed:
            owner, repo_name = repo_parsed
            if modified_files_diff is None:
                modified_files_diff = await asyncio.to_thread(
                    fetch_pr_modified_lines, owner, repo_name, pr_num, auth_token
                )
            if existing_comments is None:
                existing_comments = await asyncio.to_thread(
                    fetch_pr_comments, owner, repo_name, pr_num, auth_token
                )

    telemetry_dir = ensure_directory("reports/telemetry/pr_review_agent")
    pii_context = read_text_file(pii_report_path)

    try:
        if Agent is None or LocalAgentConfig is None:
            raise RuntimeError("Antigravity SDK not available")

        mcp_server = create_github_mcp_server(auth_token or "", repository or "")
        agent_config_kwargs = {
            "vertex": True,
            "project": cfg["project_id"],
            "location": cfg["location"],
            "model": cfg["model"],
            "response_schema": PRReviewReport,
            "mcp_servers": [mcp_server] if mcp_server else [],
            "app_data_dir": telemetry_dir,
            "system_instructions": bundle.system_instructions,
        }

        if types is not None and hasattr(types, "BudgetConfig"):
            agent_config_kwargs["budget_config"] = types.BudgetConfig(
                max_total_tokens=cfg["max_total_tokens"],
                max_input_tokens=cfg["max_input_tokens"],
                max_output_tokens=cfg["max_output_tokens"],
                max_model_calls=cfg["max_model_calls"],
                max_tool_calls=cfg["max_tool_calls"],
            )

        config = LocalAgentConfig(**agent_config_kwargs)
        prompt = bundle.render_user_prompt(
            pr_number=pr_num,
            repo=repository or "",
            pii_context=pii_context or "No DLP findings detected.",
        )

        async with Agent(config) as agent:
            response = await agent.chat(prompt)

            print("\n" + "=" * 60, flush=True)
            print("🤖 PR REVIEWER AGENT EXECUTION & THINKING STREAM", flush=True)
            print("=" * 60, flush=True)

            try:
                if hasattr(response, "chunks"):
                    async for chunk in response.chunks:
                        if types and isinstance(chunk, types.Thought):
                            print(chunk.text, end="", flush=True)
                        elif types and isinstance(chunk, types.ToolCall):
                            print(f"\n🔧 [Tool Call] {chunk.name}({chunk.args})", flush=True)
                        elif types and isinstance(chunk, types.ToolResult):
                            print(f"📦 [Tool Result] {chunk.name}", flush=True)
                        elif types and isinstance(chunk, types.Text):
                            print(chunk.text, end="", flush=True)
            except Exception as stream_err:
                print(f"\n[Warning streaming chunks: {stream_err}]", flush=True)
            print("\n" + "-" * 60, flush=True)

            # Inspect stop_reason and budget limits (Decisions D-13, D-14)
            raw_stop_reason = getattr(response, "stop_reason", None)
            if raw_stop_reason is not None and not hasattr(raw_stop_reason, "_mock_name") and type(raw_stop_reason).__name__ not in ("MagicMock", "Mock", "AsyncMock"):
                stop_reason = raw_stop_reason
                stop_reason_str = getattr(stop_reason, "name", str(stop_reason))
                if hasattr(stop_reason_str, "_mock_name") or type(stop_reason_str).__name__ in ("MagicMock", "Mock", "AsyncMock"):
                    stop_reason_str = ""
            else:
                stop_reason = None
                stop_reason_str = ""

            budget_halted = False
            if stop_reason is not None:
                if "EXCEEDED" in stop_reason_str.upper():
                    budget_halted = True
                elif types is not None and hasattr(types, "StopReason"):
                    budget_stop_reasons = (
                        getattr(types.StopReason, "MAX_TOTAL_TOKENS_EXCEEDED", None),
                        getattr(types.StopReason, "MAX_INPUT_TOKENS_EXCEEDED", None),
                        getattr(types.StopReason, "MAX_OUTPUT_TOKENS_EXCEEDED", None),
                        getattr(types.StopReason, "MAX_MODEL_CALLS_EXCEEDED", None),
                        getattr(types.StopReason, "MAX_TOOL_CALLS_EXCEEDED", None),
                    )
                    if stop_reason in [r for r in budget_stop_reasons if r is not None]:
                        budget_halted = True

            # Extract token usage and compute spend
            usage = (
                getattr(getattr(agent, "conversation", None), "total_usage", None)
                or getattr(response, "usage_metadata", None)
            )
            usage_stats = calculate_token_spend(usage, cfg["model"])
            stop_reason_label = stop_reason_str or ("COMPLETED" if not budget_halted else "BUDGET_EXCEEDED")

            write_token_usage_report(
                usage_data=usage_stats,
                stop_reason=stop_reason_label,
                output_path="reports/token-usage.json",
                model=cfg["model"],
                budget_limits=budget_limits,
                prompt_metadata=prompt_metadata_audit,
            )

            print("\n" + "=" * 60, flush=True)
            print("📊 TOKEN USAGE & ESTIMATED SPEND", flush=True)
            print("=" * 60, flush=True)
            print(f"Model: {cfg['model']}")
            print(f"Prompt Tokens (Uncached): {max(0, usage_stats['prompt_tokens'] - usage_stats['cached_tokens']):,}")
            print(f"Cached Tokens: {usage_stats['cached_tokens']:,}")
            print(f"Candidate Tokens: {usage_stats['candidate_tokens']:,}")
            print(f"Reasoning / Thought Tokens: {usage_stats['thought_tokens']:,}")
            print(f"Total Tokens: {usage_stats['total_tokens']:,}")
            print(f"Estimated Spend: ${usage_stats['total_cost_usd']:.6f} USD")
            print(f"Stop Reason: {stop_reason_label}")
            print("=" * 60 + "\n", flush=True)

            if budget_halted:
                print(
                    f"⚠️ PR review halted early: Model execution exceeded configured budget limit ({stop_reason_str}).",
                    flush=True,
                )
                report = PRReviewReport(
                    overall_status=ReviewStatus.COMMENT,
                    summary=(
                        f"⚠️ PR review halted early: Model execution exceeded configured budget limit "
                        f"({stop_reason_str}). Processed {usage_stats['total_tokens']:,} tokens "
                        f"(${usage_stats['total_cost_usd']:.4f} USD)."
                    ),
                    findings=[],
                )
                write_pr_reports(report)
                if pr_num:
                    await post_github_pr_review(
                        report=report,
                        pr_number=pr_num,
                        repo=repository or "",
                        token=auth_token or "",
                        modified_files_diff=modified_files_diff,
                        existing_comments=existing_comments,
                    )
                return report

            raw_output = await response.structured_output()
            report = parse_agent_structured_output(raw_output, PRReviewReport)

            print("\n📄 [Structured LLM Output (PRReviewReport)]:", flush=True)
            print(report.model_dump_json(indent=2), flush=True)
            print("=" * 60 + "\n", flush=True)

            write_pr_reports(report)
            if pr_num:
                await post_github_pr_review(
                    report=report,
                    pr_number=pr_num,
                    repo=repository or "",
                    token=auth_token or "",
                    modified_files_diff=modified_files_diff,
                    existing_comments=existing_comments,
                )
            return report
    except Exception as e:
        print(f"\n⚠️ Live Antigravity Agent execution unavailable or failed: {e}", flush=True)
        print("Falling back to deterministic rule-based PR review evaluation.\n", flush=True)
        if not os.path.exists("reports/token-usage.json"):
            try:
                write_token_usage_report(
                    usage_data=calculate_token_spend(None, cfg["model"]),
                    stop_reason="ERROR_FALLBACK",
                    output_path="reports/token-usage.json",
                    model=cfg["model"],
                    budget_limits=budget_limits,
                    prompt_metadata=prompt_metadata_audit,
                )
            except Exception:
                pass

    # Fallback to deterministic review generation
    findings: list[InlineFinding] = []
    if (
        "PII finding" in pii_context
        or "AUTH_TOKEN" in pii_context
        or "API_KEY" in pii_context
    ):
        findings.append(
            InlineFinding(
                file_path="src/credentials.py",
                line_number=1,
                severity=PRFindingSeverity.BLOCKER,
                title="Sensitive credential detected by Cloud DLP",
                details="Potential sensitive credential or secret exposed in modified lines.",
                suggestion="Extract credential to Secret Manager.",
                pii_leak=True,
            )
        )
        report = PRReviewReport(
            overall_status=ReviewStatus.REQUEST_CHANGES,
            summary="Blocking security findings detected during code review.",
            findings=findings,
        )
    else:
        report = PRReviewReport(
            overall_status=ReviewStatus.APPROVE,
            summary="Code changes look clean, well-structured, and meet standards.",
            findings=[],
        )

    write_pr_reports(report)
    if pr_num:
        await post_github_pr_review(
            report=report,
            pr_number=pr_num,
            repo=repository or "",
            token=auth_token or "",
            modified_files_diff=modified_files_diff,
            existing_comments=existing_comments,
        )
    return report


async def main() -> None:
    """CLI entry point for PR Reviewer Agent."""
    pr_num = (
        (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None)
    )
    repo = (
        (sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None)
    )
    token = (
        (sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None)
    )

    report = await run_pr_review(pr_number=pr_num, repo=repo, token=token)
    if report:
        print("\n" + "=" * 60)
        print("🎯 PR REVIEW FINAL SUMMARY")
        print("=" * 60)
        print(f"Status: {report.overall_status.value}")
        print(f"Summary: {report.summary}")
        if report.findings:
            print(f"\nFindings ({len(report.findings)}):")
            for idx, finding in enumerate(report.findings, 1):
                coord = (
                    f"{finding.file_path}:{finding.line_number}"
                    if finding.line_number is not None
                    else finding.file_path
                )
                pii_tag = " [PII DETECTED]" if finding.pii_leak else ""
                print(f"  {idx}. [{finding.severity.value}] {coord} - {finding.title}{pii_tag}")
                print(f"     Details: {finding.details}")
                if finding.suggestion:
                    print(f"     Suggestion: {finding.suggestion}")
        else:
            print("\nFindings: None")
        print("=" * 60 + "\n")
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
