"""Shared Helper Utilities for GitHub Actions Antigravity Agents.

Provides reusable utilities for GitHub REST API calls, report serialization,
environment variable resolution, response streaming, formatting, and MCP configuration.

Cites Decisions from docs/spec.md (D-1, D-4, D-5, D-6, D-7, D-10).
"""

from __future__ import annotations

import os
import sys
import json
import re
import asyncio
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Union, Any, TypeVar
from pydantic import BaseModel

try:
    from google.antigravity import types
except ImportError:
    class DummyLocalAgentConfig:
        def __init__(self, **kwargs: Any):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class DummyTypes:
        class Thought:
            def __init__(self, step_index: int = 0, text: str = ""):
                self.step_index = step_index
                self.text = text
        class ToolCall:
            def __init__(self, name: str = "", args: Any = None):
                self.name = name
                self.args = args or {}
            def __str__(self) -> str:
                return f"{self.name}({self.args})"
        class ToolResult:
            def __init__(self, name: str = "", result: Any = None):
                self.name = name
                self.result = result
            def __str__(self) -> str:
                return str(self.result)
        class Text:
            def __init__(self, step_index: int = 0, text: str = ""):
                self.step_index = step_index
                self.text = text
        class McpStdioServer:
            def __init__(self, name: str, command: str, args: list[str], env: dict[str, str]):
                self.name = name
                self.command = command
                self.args = args
                self.env = env

    types = DummyTypes
    import types as _py_types
    if "google.antigravity" not in sys.modules:
        _antigravity_mod = _py_types.ModuleType("google.antigravity")
        _antigravity_mod.Agent = None
        _antigravity_mod.LocalAgentConfig = DummyLocalAgentConfig
        _antigravity_mod.types = types
        sys.modules["google.antigravity"] = _antigravity_mod

T = TypeVar("T", bound=BaseModel)

POSITIVE_APPROVAL_TEMPLATE = (
    "## ✅ Automated PR Review: APPROVED\n\n"
    "Great job! No code defects, architectural issues, or Cloud DLP security "
    "findings were detected in this pull request. All changes look clean and ready to merge."
)


# =====================================================================
# Environment and Configuration Helpers (D-4)
# =====================================================================

def resolve_env_config(
    pr_number: Optional[str] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    project_id: Optional[str] = None,
    location: str = "us-central1",
    model: Optional[str] = None,
) -> dict[str, Any]:
    """Resolves configuration from CLI parameters, environment variables, and defaults."""
    resolved_pr = pr_number or os.environ.get("PULL_REQUEST_NUMBER") or os.environ.get("PR_NUMBER")
    if resolved_pr is not None:
        resolved_pr = str(resolved_pr).strip()
        if not resolved_pr:
            resolved_pr = None

    resolved_repo = (
        repo
        or os.environ.get("GITHUB_REPOSITORY")
        or os.environ.get("REPOSITORY")
    )
    if resolved_repo is not None:
        resolved_repo = resolved_repo.strip()
        if not resolved_repo:
            resolved_repo = None

    resolved_token = (
        token
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    )
    if resolved_token is not None:
        resolved_token = resolved_token.strip()
        if not resolved_token:
            resolved_token = None

    resolved_project = (
        project_id
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCP_PROJECT")
        or "local-project"
    )

    resolved_location = (
        location
        if location != "us-central1"
        else os.environ.get("GOOGLE_CLOUD_LOCATION", location)
    )

    resolved_model = (
        model
        or os.environ.get("LLM_Model")
        or os.environ.get("LLM_MODEL")
        or "gemini-3.7-flash"
    )

    return {
        "pr_number": resolved_pr,
        "repo": resolved_repo,
        "token": resolved_token,
        "project_id": resolved_project,
        "location": resolved_location,
        "model": resolved_model,
    }


def ensure_directory(path: str) -> str:
    """Ensures that the directory for the given path exists and returns the path string."""
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return str(dir_path.resolve())


def read_text_file(path: str, default: str = "") -> str:
    """Safely reads text from a file, returning default if file does not exist or fails."""
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return default
    try:
        return file_path.read_text(encoding="utf-8")
    except Exception:
        return default


# =====================================================================
# GitHub REST API Operations & Helpers (D-1, D-10)
# =====================================================================

def sanitize_and_validate_repo(repo: str) -> Optional[tuple[str, str]]:
    """Sanitizes repository string and validates owner/repo format."""
    if not repo:
        return None
    cleaned = repo.strip().strip("'\"")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    cleaned = cleaned.strip("/")
    parts = cleaned.split("/")
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0], parts[1]
    return None



def fetch_pr_modified_lines(
    owner: str,
    repo_name: str,
    pr_number: Union[str, int],
    token: str,
    timeout: int = 10,
) -> dict[str, list[int]]:
    """Queries GitHub REST API to get modified files and their modified/added line numbers."""
    if not token or not token.strip():
        return {}

    url = f"https://api.github.com/repos/{owner}/{repo_name}/pulls/{pr_number}/files?per_page=100"
    req = urllib.request.Request(
        url=url,
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "automated-pr-reviewer/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )

    diff_map: dict[str, list[int]] = {}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            files_data = json.loads(resp.read().decode("utf-8"))
            for file_info in files_data:
                filename = file_info.get("filename")
                patch = file_info.get("patch", "")
                if not filename or not patch:
                    continue

                lines: list[int] = []
                current_line = 0
                for line in patch.splitlines():
                    hunk_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
                    if hunk_match:
                        current_line = int(hunk_match.group(1))
                    elif line.startswith("+") and not line.startswith("+++"):
                        lines.append(current_line)
                        current_line += 1
                    elif line.startswith(" "):
                        lines.append(current_line)
                        current_line += 1
                diff_map[filename] = lines
    except Exception as e:
        print(f"[Warning] Could not fetch PR diff hunks from GitHub API: {e}", flush=True)

    return diff_map


def fetch_pr_comments(
    owner: str,
    repo_name: str,
    pr_number: Union[str, int],
    token: str,
    timeout: int = 10,
) -> list[dict[str, Any]]:
    """Queries GitHub REST API to fetch all existing review comments on a pull request."""
    if not token or not token.strip():
        return []

    url = f"https://api.github.com/repos/{owner}/{repo_name}/pulls/{pr_number}/comments?per_page=100"
    req = urllib.request.Request(
        url=url,
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "automated-pr-reviewer/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            parsed = json.loads(data)
            if isinstance(parsed, list):
                return [c for c in parsed if isinstance(c, dict)]
            return []
    except Exception as e:
        print(f"[Warning] Could not fetch existing PR comments from GitHub API: {e}", flush=True)
        return []


def is_duplicate_comment(
    finding: Any,
    existing_comments: list[dict[str, Any]],
) -> bool:
    """Checks if a candidate inline finding has already been posted in prior PR comments."""
    if not isinstance(existing_comments, list):
        return False

    finding_title_lower = getattr(finding, "title", "").strip().lower()
    file_path = getattr(finding, "file_path", "")
    line_number = getattr(finding, "line_number", None)

    for comment in existing_comments:
        if not isinstance(comment, dict):
            continue
        comment_path = comment.get("path")
        if comment_path != file_path:
            continue
        comment_line = comment.get("line") or comment.get("original_line")
        if comment_line != line_number:
            continue
        comment_body = comment.get("body", "").lower()
        if finding_title_lower and finding_title_lower in comment_body:
            return True

    return False



def validate_and_sanitize_findings(
    findings: list[Any],
    modified_files_diff: dict[str, list[int]],
) -> tuple[list[Any], list[Any]]:
    """Splits findings into valid inline diff hunk findings vs out-of-hunk general findings."""
    inline_findings: list[Any] = []
    general_findings: list[Any] = []

    for finding in findings:
        file_path = getattr(finding, "file_path", "")
        line_num = getattr(finding, "line_number", None)

        if not file_path or line_num is None:
            general_findings.append(finding)
            continue

        if file_path not in modified_files_diff:
            general_findings.append(finding)
            continue

        valid_lines = modified_files_diff[file_path]
        if line_num not in valid_lines:
            general_findings.append(finding)
        else:
            inline_findings.append(finding)

    return inline_findings, general_findings


def send_github_review_sync(
    owner: str,
    repo_name: str,
    pr_number: Union[str, int],
    token: str,
    payload: dict[str, Any],
    timeout: int = 10,
) -> tuple[int, str]:
    """Sends review request payload to GitHub REST API synchronously."""
    url = f"https://api.github.com/repos/{owner}/{repo_name}/pulls/{pr_number}/reviews"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "automated-pr-reviewer/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except Exception as e:
        print(f"[Warning] Failed to post PR review to GitHub: {e}", flush=True)
        return 0, str(e)


def send_github_issue_comment_sync(
    owner: str,
    repo_name: str,
    pr_number: Union[str, int],
    token: str,
    body: str,
    timeout: int = 10,
) -> tuple[int, str]:
    """Sends issue comment fallback payload to GitHub REST API synchronously."""
    url = f"https://api.github.com/repos/{owner}/{repo_name}/issues/{pr_number}/comments"
    data = json.dumps({"body": body}).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "automated-pr-reviewer/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except Exception as e:
        print(f"[Warning] Failed to post PR comment fallback: {e}", flush=True)
        return 0, str(e)


async def post_github_pr_review(
    report: Any,
    pr_number: Union[str, int],
    repo: str,
    token: str,
    modified_files_diff: Optional[dict[str, list[int]]] = None,
    existing_comments: Optional[list[dict[str, Any]]] = None,
) -> bool:
    """Posts a structured review to GitHub Pull Request Review API with deduplication & 422 fallback."""
    if not token or not token.strip():
        print("[Warning] No GitHub token provided; skipping PR review submission.", flush=True)
        return False

    repo_parsed = sanitize_and_validate_repo(repo)
    if not repo_parsed:
        print(f"[Warning] Invalid repository '{repo}'; skipping PR review submission.", flush=True)
        return False

    owner, repo_name = repo_parsed
    event = "COMMENT"
    comments: list[dict[str, Any]] = []
    comments_to_check = existing_comments or []

    findings = getattr(report, "findings", [])
    overall_status = getattr(report, "overall_status", None)
    status_val = getattr(overall_status, "value", str(overall_status))
    summary_val = getattr(report, "summary", "")

    if not findings:
        if status_val == "APPROVE":
            if summary_val and summary_val.strip():
                body = f"{POSITIVE_APPROVAL_TEMPLATE}\n\n### Summary & Implementation Highlights:\n{summary_val.strip()}"
            else:
                body = POSITIVE_APPROVAL_TEMPLATE
        else:
            body = summary_val
    else:
        inline_findings, general_findings = validate_and_sanitize_findings(
            findings, modified_files_diff or {}
        )

        skipped_duplicates_count = 0
        for finding in inline_findings:
            if is_duplicate_comment(finding, comments_to_check):
                skipped_duplicates_count += 1
                continue
            line_num = getattr(finding, "line_number", None)
            if line_num is not None:
                sev_val = getattr(getattr(finding, "severity", None), "value", "INFO")
                title_val = getattr(finding, "title", "")
                pii_leak = getattr(finding, "pii_leak", False)
                details_val = getattr(finding, "details", "")
                suggestion_val = getattr(finding, "suggestion", "")

                comment_body = (
                    f"**[{sev_val}] {title_val}**"
                    + (" [PII DETECTED]" if pii_leak else "")
                    + f"\n\n{details_val}"
                )
                if suggestion_val:
                    comment_body += f"\n\n```suggestion\n{suggestion_val}\n```"
                comments.append(
                    {
                        "path": getattr(finding, "file_path", ""),
                        "line": line_num,
                        "body": comment_body,
                    }
                )

        if skipped_duplicates_count > 0:
            print(
                f"ℹ️ Skipped {skipped_duplicates_count} duplicate inline review comment(s) already present on PR.",
                flush=True,
            )

        body_lines = [
            f"### Status: {status_val}",
            f"Summary: {summary_val}\n",
        ]
        if general_findings:
            body_lines.append("### General & Out-of-Hunk Findings:")
            for idx, gf in enumerate(general_findings, 1):
                gf_line = getattr(gf, "line_number", None)
                gf_path = getattr(gf, "file_path", "")
                coord = f"{gf_path}:{gf_line}" if gf_line is not None else gf_path
                pii_tag = " [PII DETECTED]" if getattr(gf, "pii_leak", False) else ""
                gf_sev = getattr(getattr(gf, "severity", None), "value", "INFO")
                gf_title = getattr(gf, "title", "")
                gf_details = getattr(gf, "details", "")
                gf_sugg = getattr(gf, "suggestion", "")

                body_lines.append(f"{idx}. [{gf_sev}] {coord} - {gf_title}{pii_tag}")
                body_lines.append(f"   Details: {gf_details}")
                if gf_sugg:
                    body_lines.append(f"   Suggestion: {gf_sugg}")
                body_lines.append("")
        body = "\n".join(body_lines)

    payload = {
        "body": body,
        "event": event,
        "comments": comments,
    }

    try:
        status_code, resp_body = await asyncio.to_thread(
            send_github_review_sync, owner, repo_name, pr_number, token, payload, 10
        )
        if status_code in (200, 201):
            print(f"✅ Successfully posted GitHub PR review ({status_val}) to {owner}/{repo_name}#{pr_number}.")
            return True

        if status_code == 422:
            is_self_review = (
                "own pull request" in resp_body.lower()
                or "cannot approve" in resp_body.lower()
                or "can not approve" in resp_body.lower()
            )
            if is_self_review:
                print(
                    "[Notice] PR review rejected due to GitHub self-review restrictions. Retrying with event 'COMMENT'...",
                    flush=True,
                )
                comment_payload = {
                    "body": body,
                    "event": "COMMENT",
                    "comments": comments,
                }
                retry_status, retry_body = await asyncio.to_thread(
                    send_github_review_sync, owner, repo_name, pr_number, token, comment_payload, 10
                )
                if retry_status in (200, 201):
                    print(f"✅ Successfully posted GitHub PR review (COMMENT fallback) to {owner}/{repo_name}#{pr_number}.")
                    return True

                print("[Notice] Retrying comment submission via PR conversation comment API...", flush=True)
                issue_status, issue_body = await asyncio.to_thread(
                    send_github_issue_comment_sync, owner, repo_name, pr_number, token, format_pr_review_text(report), 10
                )
                if issue_status in (200, 201):
                    print(f"✅ Successfully posted PR comment via issue comment API to {owner}/{repo_name}#{pr_number}.")
                    return True
                else:
                    print(f"[Warning] Failed to post PR comment fallback (HTTP {issue_status}: {issue_body}).")
                    return False

            if len(comments) > 0:
                print(f"[Warning] Initial review submission with inline comments failed (HTTP 422: {resp_body}). Retrying with consolidated body comments.")
                fallback_body = format_pr_review_text(report)
                fallback_payload = {
                    "body": fallback_body,
                    "event": event,
                    "comments": [],
                }
                retry_status, retry_body = await asyncio.to_thread(
                    send_github_review_sync, owner, repo_name, pr_number, token, fallback_payload, 10
                )
                if retry_status in (200, 201):
                    print(f"✅ Successfully posted fallback PR review ({event}) to {owner}/{repo_name}#{pr_number}.")
                    return True
                elif retry_status == 422 and ("own pull request" in retry_body.lower() or "approve" in retry_body.lower()):
                    fallback_payload["event"] = "COMMENT"
                    retry_comment_status, _ = await asyncio.to_thread(
                        send_github_review_sync, owner, repo_name, pr_number, token, fallback_payload, 10
                    )
                    if retry_comment_status in (200, 201):
                        print(f"✅ Successfully posted fallback PR review (COMMENT) to {owner}/{repo_name}#{pr_number}.")
                        return True
                    issue_status, _ = await asyncio.to_thread(
                        send_github_issue_comment_sync, owner, repo_name, pr_number, token, fallback_body, 10
                    )
                    if issue_status in (200, 201):
                        print(f"✅ Successfully posted fallback PR issue comment to {owner}/{repo_name}#{pr_number}.")
                        return True

                print(f"[Warning] Fallback PR review submission failed (HTTP {retry_status}: {retry_body}).")
                return False
            else:
                print(f"[Warning] GitHub PR review rejected (HTTP 422: {resp_body}).")
                return False

        print(f"[Warning] Failed to post PR review to GitHub (HTTP {status_code}: {resp_body}).")
        return False
    except Exception as e:
        print(f"[Warning] Failed to post PR review to GitHub: {e}")
        return False


# =====================================================================
# Formatting & Report Serialization Utilities (D-5)
# =====================================================================

def format_pr_review_text(report: Any) -> str:
    """Formats a PRReviewReport into human-readable text."""
    overall_status = getattr(report, "overall_status", None)
    status_str = getattr(overall_status, "value", str(overall_status))
    summary_str = getattr(report, "summary", "")
    findings = getattr(report, "findings", [])

    lines = [
        f"### Status: {status_str}",
        f"Summary: {summary_str}",
    ]
    if findings:
        lines.append("\n### Findings:")
        for idx, finding in enumerate(findings, 1):
            coord = (
                f"{getattr(finding, 'file_path', '')}:{getattr(finding, 'line_number', '')}"
                if getattr(finding, "line_number", None) is not None
                else getattr(finding, "file_path", "")
            )
            pii_tag = " [PII DETECTED]" if getattr(finding, "pii_leak", False) else ""
            sev_str = getattr(getattr(finding, "severity", None), "value", "INFO")
            title_str = getattr(finding, "title", "")
            details_str = getattr(finding, "details", "")
            suggestion_str = getattr(finding, "suggestion", "")

            lines.append(f"{idx}. [{sev_str}] {coord} - {title_str}{pii_tag}")
            lines.append(f"   Details: {details_str}")
            if suggestion_str:
                lines.append(f"   Suggestion: {suggestion_str}")

    return "\n".join(lines) + "\n"


def format_text_decision(decision: Any) -> str:
    """Formats QualityGateDecision into deterministic text starting with GATE_PASSED or GATE_FAILED."""
    passed = getattr(decision, "passed", False)
    summary = getattr(decision, "summary", "")
    failures = getattr(decision, "failures", [])

    if passed:
        return f"GATE_PASSED\n\n{summary}"

    lines: list[str] = [
        "GATE_FAILED\n",
        f"Summary: {summary}\n",
        "Failures Detected:",
    ]
    for idx, failure in enumerate(failures, 1):
        sev = getattr(getattr(failure, "severity", None), "value", "HIGH")
        cat = getattr(getattr(failure, "category", None), "value", "VIOLATION")
        comp = getattr(failure, "component", "unknown")
        reason = getattr(failure, "reason", "")
        remediation = getattr(failure, "remediation", "")
        lines.append(f"{idx}. [{sev}] {cat} in {comp}: {reason}")
        lines.append(f"   Remediation: {remediation}")

    return "\n".join(lines)


def write_json_and_text_reports(
    json_path: str,
    json_data: Any,
    text_path: str,
    text_content: str,
) -> None:
    """Writes structured JSON and text artifacts to disk."""
    json_file = Path(json_path)
    text_file = Path(text_path)

    json_file.parent.mkdir(parents=True, exist_ok=True)
    text_file.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(json_data, "model_dump_json"):
        json_str = json_data.model_dump_json(indent=2)
    elif hasattr(json_data, "json"):
        json_str = json_data.json(indent=2)
    elif isinstance(json_data, dict):
        json_str = json.dumps(json_data, indent=2)
    else:
        json_str = str(json_data)

    json_file.write_text(json_str, encoding="utf-8")
    text_file.write_text(text_content, encoding="utf-8")


def write_pr_reports(report: Any) -> None:
    """Writes reports/pr-review.json and reports/pr-review.txt."""
    text_content = format_pr_review_text(report)
    write_json_and_text_reports(
        json_path="reports/pr-review.json",
        json_data=report,
        text_path="reports/pr-review.txt",
        text_content=text_content,
    )


def write_gate_reports(decision: Any) -> None:
    """Writes reports/gate-decision.json and reports/decision.txt."""
    text_content = format_text_decision(decision)
    write_json_and_text_reports(
        json_path="reports/gate-decision.json",
        json_data=decision,
        text_path="reports/decision.txt",
        text_content=text_content,
    )


# =====================================================================
# Agent SDK, Streaming, and Structured Output Parsing (D-6, D-7)
# =====================================================================

def create_github_mcp_server(token: str, repo: str) -> Any:
    """Constructs a types.McpStdioServer configured for GitHub MCP container."""
    server_cls = getattr(types, "McpStdioServer", None) if types else None
    if server_cls is None:
        class DummyMcpStdioServer:
            def __init__(self, name: str, command: str, args: list[str], env: dict[str, str]):
                self.name = name
                self.command = command
                self.args = args
                self.env = env
        server_cls = DummyMcpStdioServer

    return server_cls(
        name="github",
        command="docker",
        args=[
            "run",
            "-i",
            "--rm",
            "-e",
            "GITHUB_PERSONAL_ACCESS_TOKEN",
            "-e",
            "GITHUB_REPOSITORY",
            "ghcr.io/github/github-mcp-server:v0.27.0",
        ],
        env={
            "GITHUB_PERSONAL_ACCESS_TOKEN": token or "",
            "GITHUB_REPOSITORY": repo or "",
        },
    )


async def stream_agent_response(
    response: Any,
    header_title: str = "AGENT EXECUTION & THINKING STREAM",
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Streams and logs Thought, ToolCall, ToolResult, and Text chunks from Agent chat response."""
    print("=" * 80)
    print(f"📡 {header_title}")
    print("=" * 80)
    thoughts: list[str] = []
    tool_calls: list[str] = []
    tool_results: list[str] = []
    text_chunks: list[str] = []

    if hasattr(response, "chunks"):
        async for chunk in response.chunks:
            if types and isinstance(chunk, types.Thought):
                thoughts.append(chunk.text)
                print(chunk.text, end="", flush=True)
            elif types and isinstance(chunk, types.ToolCall):
                tool_calls.append(str(chunk))
                print(f"\n🔧 [Tool Call] {chunk.name}({chunk.args})", flush=True)
            elif types and isinstance(chunk, types.ToolResult):
                tool_results.append(str(chunk))
                print(f"📦 [Tool Result] {chunk.name}", flush=True)
            elif types and isinstance(chunk, types.Text):
                text_chunks.append(chunk.text)
                print(chunk.text, end="", flush=True)
    elif hasattr(response, "__aiter__"):
        async for chunk in response:
            if types and isinstance(chunk, types.Thought):
                thoughts.append(chunk.thought if hasattr(chunk, "thought") else chunk.text)
                print(f"💭 [Thought]: {getattr(chunk, 'thought', getattr(chunk, 'text', ''))}")
            elif types and isinstance(chunk, types.ToolCall):
                tool_calls.append(str(chunk))
                print(f"🛠️ [ToolCall]: {getattr(chunk, 'name', getattr(chunk, 'tool_name', 'tool'))}")
            elif types and isinstance(chunk, types.ToolResult):
                tool_results.append(str(chunk))
                print(f"📊 [ToolResult]: {getattr(chunk, 'name', getattr(chunk, 'tool_name', 'tool'))}")
            elif types and isinstance(chunk, types.Text):
                text_chunks.append(chunk.text)
                print(chunk.text, end="", flush=True)

    print("\n" + "=" * 80)
    return thoughts, tool_calls, tool_results, text_chunks


def parse_agent_structured_output(raw_output: Any, schema_cls: type[T]) -> T:
    """Validates and coerces structured output from Agent into target Pydantic schema."""
    if isinstance(raw_output, schema_cls):
        return raw_output
    if isinstance(raw_output, dict):
        return schema_cls.model_validate(raw_output)
    if isinstance(raw_output, str):
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return schema_cls.model_validate(data)
        except Exception:
            pass
        return schema_cls.model_validate_json(raw_output)
    return schema_cls.model_validate(raw_output)
