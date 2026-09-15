"""Prompt Loader and Template Management Engine.

Loads, parses, validates, and renders externalized versioned markdown prompt
templates with YAML frontmatter for Antigravity AI agents (Decision D-19).
"""

from __future__ import annotations

import os
import re
import hashlib
import logging
import datetime
from pathlib import Path
from string import Template
from typing import Optional, Dict, Any, List, Union

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    import yaml
except ImportError:
    yaml = None


class PromptMetadata(BaseModel):
    """Structured metadata parsed from prompt template YAML frontmatter."""

    name: str
    version: str
    description: str = ""
    author: Optional[str] = None
    created_at: Optional[str] = None
    model_compatibility: List[str] = Field(default_factory=list)
    required_variables: List[str] = Field(default_factory=list)
    optional_variables: List[str] = Field(default_factory=list)
    changelog: List[Dict[str, Any]] = Field(default_factory=list)
    sha256: str = ""
    file_path: Optional[str] = None
    is_fallback: bool = False


class PromptBundle(BaseModel):
    """Encapsulates system instructions, user prompt template, and rendering engine."""

    metadata: PromptMetadata
    system_instructions: str
    user_template: str
    raw_content: str = ""

    @property
    def user_prompt_template(self) -> str:
        """Alias for user_template to support multiple naming conventions."""
        return self.user_template

    def render_user_prompt(self, **kwargs: Any) -> str:
        """Validates required variables and safely substitutes ${var} placeholders."""
        # 1. Validate required variables
        missing = [
            var
            for var in self.metadata.required_variables
            if var not in kwargs or kwargs[var] is None or kwargs[var] == ""
        ]
        if missing:
            raise ValueError(
                f"Missing required prompt variable: '{missing[0]}'"
            )

        # 2. Convert all values to strings (substituting empty string for None)
        substitutions = {
            k: ("" if v is None else str(v))
            for k, v in kwargs.items()
        }

        # 3. Substitute using string.Template to preserve literal braces {id}
        template = Template(self.user_template)
        return template.safe_substitute(substitutions)

    def to_audit_dict(self) -> Dict[str, Any]:
        """Returns JSON-serializable dictionary for audit reports and telemetry."""
        return {
            "name": self.metadata.name,
            "version": self.metadata.version,
            "sha256": self.metadata.sha256,
            "is_fallback": self.metadata.is_fallback,
            "file_path": self.metadata.file_path,
            "loaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }


# =====================================================================
# Built-In Fail-Safe Prompts (Decision D-19)
# =====================================================================

BUILTIN_PROMPTS: Dict[str, Dict[str, Any]] = {
    "pr_reviewer": {
        "metadata": {
            "name": "pr_reviewer",
            "version": "1.0.0-builtin",
            "description": "Built-in fallback PR Reviewer prompt bundle",
            "author": "Antigravity Fallback System",
            "required_variables": ["pr_number", "repo", "pii_context"],
            "optional_variables": ["additional_guidelines"],
            "is_fallback": True,
        },
        "system_instructions": (
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
        ),
        "user_template": (
            "Perform an automated code review on Pull Request #${pr_number} in repository ${repo}.\n\n"
            "### Inputs & Context:\n"
            "1. Cloud DLP Sensitive Data & PII Scan Findings:\n"
            "${pii_context}\n\n"
            "2. Instructions:\n"
            "    - Use GitHub MCP read and write tools to inspect the PR details, modified files, diff hunks, and perform review interactions as needed.\n"
            "    - Inspect all modified lines against the review checklist (logic errors, REST API CRUD design standards, runtime performance / Big O complexity, memory usage / scalability, infinite loops / recursion stack overflows, design patterns & SOLID principles, engineering best practices, type safety, security risks, error handling, PEP 8).\n"
            "    - For any files or modified lines flagged with sensitive data / PII leaks or credentials in the DLP report or diff, create a BLOCKER finding with `pii_leak: true` and explicit remediation instructions (e.g. moving secrets to Secret Manager, or redacting PII).\n"
            "    - For verifiable logic bugs, REST API anti-patterns (e.g. GET mutations, missing pagination on endpoints, broken status codes), infinite loops, stack overflow hazards, severe performance/memory bottlenecks, and type safety issues, add line-level findings with precise file paths, line numbers, and actionable code suggestions.\n"
            "    - For clean PRs with zero defects, return `findings: []`, set `overall_status` to `APPROVE`, and generate a meaningful, personalized `summary` highlighting specific positive aspects of the implementation (e.g., elegant design choices, clean code structure, robust typing, thorough test coverage, or performance considerations) rather than a generic canned message.\n"
            "    - Return the final review conforming strictly to the PRReviewReport schema."
        ),
    },
    "quality_gate": {
        "metadata": {
            "name": "quality_gate",
            "version": "1.0.0-builtin",
            "description": "Built-in fallback Quality Gate prompt bundle",
            "author": "Antigravity Fallback System",
            "required_variables": ["pii_content", "pr_review_content"],
            "optional_variables": ["release_notes"],
            "is_fallback": True,
        },
        "system_instructions": (
            "You are a Lead Release Engineer and Security Gatekeeper. Evaluate combined DLP and PR code review reports against release criteria.\n"
            "Quality Gate Criteria:\n"
            "1. ZERO PII, credential, or authentication token leaks detected by Cloud DLP.\n"
            "2. PR Code Review contains no unresolved blocking architectural or critical security failures."
        ),
        "user_template": (
            "You are the Quality Gate Decision Agent.\n"
            "Evaluate the following security scans and PR code review outputs:\n\n"
            "=== CLOUD DLP SCAN REPORT ===\n"
            "${pii_content}\n\n"
            "=== PR CODE REVIEW REPORT ===\n"
            "${pr_review_content}\n\n"
            "Evaluate if the build passes or fails release criteria.\n"
            "Fail the gate if any sensitive data, credentials, or blocker review items exist.\n"
            "Return a structured QualityGateDecision response."
        ),
    },
}


def _fallback_yaml_parse(fm_text: str) -> Dict[str, Any]:
    """Lightweight fallback parser for YAML frontmatter if PyYAML is unavailable."""
    data: Dict[str, Any] = {}
    current_list_key: Optional[str] = None

    for line in fm_text.splitlines():
        line = line.rstrip()
        if not line or line.strip().startswith("#"):
            continue

        list_match = re.match(r"^\s*-\s+(.*)$", line)
        if list_match and current_list_key:
            val = list_match.group(1).strip().strip("'\"")
            if isinstance(data.get(current_list_key), list):
                data[current_list_key].append(val)
            continue

        kv_match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if kv_match:
            key, val = kv_match.group(1).strip(), kv_match.group(2).strip()
            if not val:
                data[key] = []
                current_list_key = key
            else:
                current_list_key = None
                val = val.strip("'\"")
                if val.lower() == "true":
                    data[key] = True
                elif val.lower() == "false":
                    data[key] = False
                else:
                    data[key] = val
    return data


def _extract_frontmatter_and_body(content: str) -> tuple[Dict[str, Any], str]:
    """Extracts YAML frontmatter dictionary and remaining markdown body."""
    stripped = content.strip()
    if stripped.startswith("---"):
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", stripped, flags=re.DOTALL)
        if match:
            fm_text, body = match.group(1), match.group(2)
            meta_dict = None
            if yaml is not None:
                try:
                    meta_dict = yaml.safe_load(fm_text)
                except Exception:
                    meta_dict = None
            if not isinstance(meta_dict, dict):
                meta_dict = _fallback_yaml_parse(fm_text)
            return meta_dict, body
    return {}, content


def _parse_sections(body: str) -> tuple[str, str]:
    """Splits markdown body into system instructions and user prompt template."""
    sys_match = re.search(
        r"^##\s+System Instructions\s*$", body, flags=re.MULTILINE | re.IGNORECASE
    )
    user_match = re.search(
        r"^##\s+User Prompt\s*$", body, flags=re.MULTILINE | re.IGNORECASE
    )

    if sys_match and user_match:
        if sys_match.start() < user_match.start():
            system_instructions = body[sys_match.end() : user_match.start()].strip()
            user_template = body[user_match.end() :].strip()
        else:
            user_template = body[user_match.end() : sys_match.start()].strip()
            system_instructions = body[sys_match.end() :].strip()
    elif sys_match and not user_match:
        system_instructions = body[sys_match.end() :].strip()
        user_template = ""
    elif user_match and not sys_match:
        system_instructions = ""
        user_template = body[user_match.end() :].strip()
    else:
        system_instructions = body.strip()
        user_template = ""

    return system_instructions, user_template


def _parse_semver(v: str) -> tuple[int, ...]:
    """Parses a version string into a tuple of integers for semantic sorting."""
    clean = v.lstrip("v").strip()
    if clean.endswith(".md"):
        clean = clean[:-3]
    parts: List[int] = []
    for p in clean.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


class PromptLoader:
    """Manages loading, parsing, and caching of prompt templates."""

    _instance: Optional["PromptLoader"] = None

    def __init__(self, base_prompts_dir: Optional[Union[str, Path]] = None) -> None:
        self.base_prompts_dir = Path(base_prompts_dir) if base_prompts_dir else None

    @classmethod
    def get_instance(cls) -> "PromptLoader":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def compute_sha256(content: str) -> str:
        """Calculates SHA256 checksum of raw template string."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get_builtin_fallback(self, name: str) -> PromptBundle:
        """Retrieves embedded default prompt bundle for fail-safe resilience."""
        raw_bundle = BUILTIN_PROMPTS.get(name)
        if not raw_bundle:
            # Fallback for unrecognized agent names
            raw_bundle = {
                "metadata": {
                    "name": name,
                    "version": "1.0.0-builtin",
                    "description": f"Generic built-in fallback for {name}",
                    "is_fallback": True,
                },
                "system_instructions": f"You are the {name} agent.",
                "user_template": "${prompt}",
            }

        meta_dict = dict(raw_bundle["metadata"])
        sys_ins = raw_bundle["system_instructions"]
        usr_tpl = raw_bundle["user_template"]
        raw_repr = f"## System Instructions\n{sys_ins}\n\n## User Prompt\n{usr_tpl}"
        sha = self.compute_sha256(raw_repr)
        meta_dict["sha256"] = sha
        meta_dict["is_fallback"] = True

        metadata = PromptMetadata(**meta_dict)
        return PromptBundle(
            metadata=metadata,
            system_instructions=sys_ins,
            user_template=usr_tpl,
            raw_content=raw_repr,
        )

    def parse_template_content(
        self, content: str, file_path: Optional[str] = None
    ) -> PromptBundle:
        """Parses frontmatter, system instructions, and user prompt from markdown content."""
        sha = self.compute_sha256(content)
        meta_dict, body = _extract_frontmatter_and_body(content)
        if not meta_dict:
            raise ValueError("Prompt template missing valid YAML frontmatter")
        sys_ins, usr_tpl = _parse_sections(body)
        if not sys_ins:
            raise ValueError("Prompt template missing '## System Instructions' section")

        meta_dict["sha256"] = sha
        if file_path:
            meta_dict["file_path"] = str(file_path)
        meta_dict["is_fallback"] = False

        if "name" not in meta_dict and file_path:
            meta_dict["name"] = Path(file_path).parent.name
        elif "name" not in meta_dict:
            meta_dict["name"] = "unknown"

        if "version" not in meta_dict and file_path:
            meta_dict["version"] = Path(file_path).stem.lstrip("v")
        elif "version" not in meta_dict:
            meta_dict["version"] = "1.0.0"

        metadata = PromptMetadata(**meta_dict)
        return PromptBundle(
            metadata=metadata,
            system_instructions=sys_ins,
            user_template=usr_tpl,
            raw_content=content,
        )

    def resolve_version_path(
        self, name: str, version: Optional[str] = None
    ) -> Optional[Path]:
        """Resolves target template file path using version conventions."""
        search_dirs: List[Path] = []
        if self.base_prompts_dir:
            search_dirs.append(self.base_prompts_dir / name)
        search_dirs.extend([
            Path.cwd() / ".github" / "prompts" / name,
            Path(__file__).resolve().parent.parent / "prompts" / name,
            Path(".github/prompts") / name,
        ])

        target_dir: Optional[Path] = None
        for d in search_dirs:
            if d.exists() and d.is_dir():
                target_dir = d
                break

        if not target_dir:
            return None

        ver = (version or "1.0.0").strip()
        if not ver or ver.lower() == "default":
            ver = "1.0.0"

        # Check for 'latest'
        if ver.lower() == "latest":
            md_files = [
                f
                for f in target_dir.glob("*.md")
                if f.name.lower() != "readme.md" and not f.name.startswith(".")
            ]
            if md_files:
                md_files.sort(key=lambda f: _parse_semver(f.stem))
                return md_files[-1]
            return None

        clean_ver = ver.lstrip("v")
        candidates = [
            f"v{clean_ver}.md",
            f"{clean_ver}.md",
            f"{ver}.md",
        ]

        for cand in candidates:
            cand_path = target_dir / cand
            if cand_path.is_file():
                return cand_path

        # If partial version e.g. "1" or "v1", find highest matching semver
        matching = [
            f
            for f in target_dir.glob(f"*{clean_ver}*.md")
            if f.name.lower() != "readme.md" and not f.name.startswith(".")
        ]
        if matching:
            matching.sort(key=lambda f: _parse_semver(f.stem))
            return matching[-1]

        return None

    def load(
        self,
        name: str,
        version: Optional[str] = None,
        prompt_path: Optional[str] = None,
    ) -> PromptBundle:
        """Loads prompt template bundle from explicit path, resolved version, or fallback."""
        if prompt_path:
            p = Path(prompt_path)
            if p.is_file():
                try:
                    content = p.read_text(encoding="utf-8")
                    return self.parse_template_content(content, file_path=str(p))
                except Exception as err:
                    print(
                        f"[Warning] Failed to parse prompt file {p}: {err}. Falling back to built-in prompt.",
                        flush=True,
                    )
                    return self.get_builtin_fallback(name)
            else:
                print(
                    f"[Warning] Specified prompt path does not exist: {prompt_path}. Using fallback.",
                    flush=True,
                )
                return self.get_builtin_fallback(name)

        target_file = self.resolve_version_path(name, version=version)

        if target_file is not None and target_file.is_file():
            try:
                content = target_file.read_text(encoding="utf-8")
                return self.parse_template_content(content, file_path=str(target_file))
            except Exception as err:
                print(
                    f"[Warning] Failed to parse prompt file {target_file}: {err}. Falling back to built-in prompt.",
                    flush=True,
                )

        print(
            f"[Warning] Could not find prompt template for '{name}' (version={version}, prompt_path={prompt_path}). "
            f"Using embedded built-in fallback.",
            flush=True,
        )
        return self.get_builtin_fallback(name)


def load_prompt_bundle(
    name: str,
    version: Optional[str] = None,
    prompt_path: Optional[str] = None,
) -> PromptBundle:
    """Convenience helper function to load a prompt bundle via PromptLoader."""
    return PromptLoader.get_instance().load(
        name=name, version=version, prompt_path=prompt_path
    )
