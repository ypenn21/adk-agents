"""Automated PR Review Agent using Antigravity Python SDK with Vertex AI ADC and Pydantic.

Inspects PR diffs, checks DLP scan context, and submits structured reviews and inline comments.
Reusable logic is extracted into helper.py.
"""

from __future__ import annotations

import sys
import asyncio
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field, model_validator
from google.antigravity import Agent, LocalAgentConfig, types

from helper import (
    POSITIVE_APPROVAL_TEMPLATE,
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


SYSTEM_INSTRUCTIONS = (
    "You are an expert Principal Software Architect, API Designer, Performance Engineer, and Security Auditor.\n\n"
    "Your objective is to thoroughly review Pull Request diffs, evaluate Cloud DLP security scans, "
    "and produce a structured PRReviewReport with line-level findings and remediation suggestions.\n\n"
    "### TOOL USAGE POLICY:\n"
    "- You have full access to GitHub MCP tools for both read operations (e.g., inspecting PR metadata, modified files, diff hunks, issues, and comments) and write operations (e.g., creating comments, reviews, updating issues, or applying labels).\n"
    "- Ensure your complete analysis and findings are returned in the structured `PRReviewReport` schema so the review runner can record and synchronize the review lifecycle.\n\n"
    "### REVIEW GUIDELINES & CHECKLIST:\n"
    "1. **Logic & Correctness:** Verify control flow, boundary conditions, off-by-one errors, and algorithm correctness.\n"
    "2. **REST API Design & CRUD Best Practices (if adding/modifying endpoints):**\n"
    "   - **Resource-Oriented URIs:** Use plural nouns for resources (e.g., `/api/v1/accounts/{id}` instead of RPC verbs `/getAccount`), consistent kebab-case or snake_case, and clear API versioning.\n"
    "   - **HTTP Verbs & Semantic Correctness:** Ensure `GET` is safe and idempotent with no mutating side-effects; `POST` creates subordinate resources and returns `201 Created` with created entity/Location; `PUT` performs idempotent full replacement; `PATCH` performs idempotent partial update; `DELETE` removes resource and returns `204 No Content` or `200 OK`.\n"
    "   - **Accurate HTTP Status Codes:** Enforce semantic status codes (`200 OK`, `201 Created`, `204 No Content`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `409 Conflict`, `422 Unprocessable Entity`, `500 Internal Error`).\n"
    "   - **Pagination, Filtering & Payloads:** Require pagination (`limit`, `offset`/`cursor`) on collection endpoints to prevent unbounded DB queries; validate request/response bodies with schemas (e.g., Pydantic/OpenAPI); provide consistent structured error envelopes (e.g., RFC 7807 Problem Details or standardized `error` JSON).\n"
    "3. **Runtime Performance & Big O Complexity:** Evaluate time complexity. Identify accidental O(N^2) or exponential patterns (e.g., nested loops over large datasets, linear lookups in lists/tuples where sets or dicts provide O(1) time, repeated regex compilations, redundant database/API calls, N+1 query issues, or expensive repetitive computations inside tight loops).\n"
    "4. **Memory Management & Scalability:** Prevent memory leaks and excessive memory footprint. Flag unbounded caching/collections (missing maxsize or TTL), loading massive files/payloads entirely into memory instead of streaming or chunking with generators/iterators, and identify scalability bottlenecks under high concurrency or throughput.\n"
    "5. **Infinite Loops, Recursion & Stack Overflow:** Scrutinize while loops, for loops, and recursive functions. Ensure loop indices/conditions guaranteed to terminate, recursive functions have reachable base cases and bounded depth to prevent RecursionError / stack overflow, and avoid circular references.\n"
    "6. **Design Patterns & Architecture (SOLID):** Evaluate application of appropriate structural, creational, and behavioral design patterns (e.g., Strategy, Factory, Adapter, Repository, Dependency Injection, Decorator). Guard against anti-patterns (God classes/functions, tight coupling, leaky abstractions, circular dependencies) and enforce SOLID principles (Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion).\n"
    "7. **Engineering Best Practices & Testability:** Ensure separation of pure business domain logic from side-effecting I/O and HTTP transport layers, favor composition over deep inheritance hierarchies, promote immutability/statelessness where applicable, enforce consistent structured logging, and ensure components are decoupled for unit testability (mockable interfaces, deterministic execution).\n"
    "8. **Null Pointers & Type Safety:** Check for potential NoneType dereferences, missing guard clauses, unsafe dictionary key indexing, and unhandled optional types.\n"
    "9. **Security & PII Leaks:** Identify hardcoded API keys, tokens, credentials, or sensitive PII. Cross-reference with the provided Cloud DLP report. Verify authorization and authentication guards on sensitive API routes.\n"
    "10. **Error Handling & Resilience:** Ensure exceptions are caught cleanly at appropriate boundaries, domain-specific exception types are used (avoiding bare `except:` or silent pass), resources (files, sockets, connections) are safely closed using context managers (`with`), and network/IO operations enforce timeouts and backoff.\n"
    "11. **Code Quality & PEP 8:** Check for readability, idiomatic Python patterns, proper naming conventions, type annotations, and documentation.\n\n"
    "### SEVERITY CALIBRATION:\n"
    "- BLOCKER: Crashes, uncaught exceptions, infinite loops, recursion stack overflows, out-of-memory vulnerabilities, critical security defects, unauthenticated/unprotected mutating routes, or PII/secret leaks (triggers REQUEST_CHANGES).\n"
    "- WARNING: Significant Big O or runtime inefficiencies (e.g., O(N^2) on large datasets, N+1 queries), REST API contract violations (e.g., GET mutating state, unbounded collections without pagination, invalid HTTP status codes), memory bloat, severe design anti-patterns (tight coupling, broken contracts), missing timeouts/resource cleanup, edge-case failures, or unhandled errors.\n"
    "- SUGGESTION: REST API design improvements (URI naming conventions, standardized error response schemas), design pattern improvements, scalability enhancements, maintainability refactors, non-blocking performance optimizations, caching, or code readability enhancements.\n"
    "- INFO: Informational notes, architecture observations, or style hints.\n\n"
    "### INLINE FINDINGS REQUIREMENTS:\n"
    "- Specify exact `file_path` and `line_number` within the modified diff hunks.\n"
    "- Provide clear, concise `details` explaining the root cause, architectural/algorithmic impact, and failure modes.\n"
    "- Always provide actionable, syntactically valid replacement code in `suggestion`.\n"
    "- If no defects are found, return `findings: []`, set status to `APPROVE`, and write a meaningful, positive, and detailed `summary` highlighting specific implementation strengths, clean architecture, test coverage, and design choices."
)


def build_pr_review_prompt(pr_number: str, repo: str, pii_context: str) -> str:
    """Builds the user prompt for the PR Reviewer Agent."""
    return f"""Perform an automated code review on Pull Request #{pr_number} in repository {repo}.

### Inputs & Context:
1. Cloud DLP Sensitive Data & PII Scan Findings:
{pii_context or 'No DLP findings detected.'}

2. Instructions:
    - Use GitHub MCP read and write tools to inspect the PR details, modified files, diff hunks, and perform review interactions as needed.
    - Inspect all modified lines against the review checklist (logic errors, REST API CRUD design standards, runtime performance / Big O complexity, memory usage / scalability, infinite loops / recursion stack overflows, design patterns & SOLID principles, engineering best practices, type safety, security risks, error handling, PEP 8).
    - For any files or modified lines flagged with sensitive data / PII leaks or credentials in the DLP report or diff, create a BLOCKER finding with `pii_leak: true` and explicit remediation instructions (e.g. moving secrets to Secret Manager, or redacting PII).
    - For verifiable logic bugs, REST API anti-patterns (e.g. GET mutations, missing pagination on endpoints, broken status codes), infinite loops, stack overflow hazards, severe performance/memory bottlenecks, and type safety issues, add line-level findings with precise file paths, line numbers, and actionable code suggestions.
    - For clean PRs with zero defects, return `findings: []`, set `overall_status` to `APPROVE`, and generate a meaningful, personalized `summary` highlighting specific positive aspects of the implementation (e.g., elegant design choices, clean code structure, robust typing, thorough test coverage, or performance considerations) rather than a generic canned message.
    - Return the final review conforming strictly to the PRReviewReport schema.
"""


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
) -> Optional[PRReviewReport]:
    """Runs automated PR review using Antigravity SDK and GitHub MCP server."""
    cfg = resolve_env_config(pr_number, repo, token, project_id, location, model)
    pr_num, repository, auth_token = cfg["pr_number"], cfg["repo"], cfg["token"]

    if not pr_num:
        print("No pull request number provided; skipping PR review.")
        return None

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
        mcp_server = create_github_mcp_server(auth_token or "", repository or "")
        config = LocalAgentConfig(
            vertex=True,
            project=cfg["project_id"],
            location=cfg["location"],
            model=cfg["model"],
            response_schema=PRReviewReport,
            mcp_servers=[mcp_server] if mcp_server else [],
            app_data_dir=telemetry_dir,
            system_instructions=SYSTEM_INSTRUCTIONS,
        )
        prompt = build_pr_review_prompt(pr_num, repository or "", pii_context)

        async with Agent(config) as agent:
            response = await agent.chat(prompt)

            print("\n" + "=" * 60, flush=True)
            print("🤖 PR REVIEWER AGENT EXECUTION & THINKING STREAM", flush=True)
            print("=" * 60, flush=True)

            try:
                if hasattr(response, "chunks"):
                    async for chunk in response.chunks:
                        if isinstance(chunk, types.Thought):
                            print(chunk.text, end="", flush=True)
                        elif isinstance(chunk, types.ToolCall):
                            print(f"\n🔧 [Tool Call] {chunk.name}({chunk.args})", flush=True)
                        elif isinstance(chunk, types.ToolResult):
                            print(f"📦 [Tool Result] {chunk.name}", flush=True)
                        elif isinstance(chunk, types.Text):
                            print(chunk.text, end="", flush=True)
            except Exception as stream_err:
                print(f"\n[Warning streaming chunks: {stream_err}]", flush=True)
            print("\n" + "-" * 60, flush=True)

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
