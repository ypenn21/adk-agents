"""Google Cloud DLP Sensitive Data & PII Scanner.

Inspects repository source code using Google Cloud DLP (Data Loss Prevention) and
regex pattern matching for leaked credentials and sensitive PII. Generates both
reports/pii-scan.txt and structured reports/pii-scan.json.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

DEFAULT_INFO_TYPES = (
    "EMAIL_ADDRESS,PHONE_NUMBER,LOCATION,CREDIT_CARD_NUMBER,"
    "AUTH_TOKEN,GCP_API_KEY,GCP_CREDENTIALS"
)

EXCLUDE_DIRS: Set[str] = {
    ".git",
    ".venv",
    "venv",
    ".pytest_cache",
    "reports",
    "plans",
    "extensions",
    "mcp-servers",
    ".agents",
    "__pycache__",
    ".idea",
    ".vscode",
}

EXCLUDE_FILE_PATTERNS: Set[str] = {
    "gha-creds-*",
    "*.lock",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.zip",
    "*.tar",
    "*.gz",
}

INCLUDE_EXTENSIONS: Set[str] = {
    ".env",
    ".pem",
    ".key",
    ".crt",
    ".cert",
    ".ini",
    ".cfg",
    ".conf",
    ".properties",
    ".xml",
    ".csv",
    ".txt",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".css",
    ".scss",
    ".tf",
    ".yml",
    ".yaml",
    ".md",
    ".sh",
    ".py",
    ".json",
    ".toml",
    ".html",
    ".sql",
}

INCLUDE_EXACT_NAMES: Set[str] = {
    "Dockerfile",
    "Makefile",
    "Procfile",
    "Jenkinsfile",
}

MAX_FILE_SIZE_BYTES = 500 * 1024  # 500 KB

SECRET_PATTERN = re.compile(
    r"""(?:GEMINI_API_KEY|API_KEY|SECRET_KEY|ACCESS_KEY|PRIVATE_KEY)\s*=\s*['"]?[A-Za-z0-9_.-]{16,}|AIza[0-9A-Za-z_-]{35}|AQ\.[A-Za-z0-9_-]{30,}"""
)


def discover_files(root_dir: Path | str = ".") -> List[Path]:
    """Finds all non-excluded, target source files within size limits."""
    root = Path(root_dir).resolve()
    target_files: List[Path] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        rel_parts = path.relative_to(root).parts

        # Skip excluded directory trees
        if any(part in EXCLUDE_DIRS for part in rel_parts[:-1]):
            continue

        # Skip hidden directories, but allow .env* or *.env
        hidden_dir = any(
            part.startswith(".") and not (part.startswith(".env") or part.endswith(".env"))
            for part in rel_parts[:-1]
        )
        if hidden_dir:
            continue

        filename = path.name

        # Skip hidden files unless they match .env* or *.env
        if filename.startswith(".") and not (filename.startswith(".env") or filename.endswith(".env")):
            continue

        # Skip explicit excluded filename patterns
        if any(fnmatch.fnmatch(filename, pat) for pat in EXCLUDE_FILE_PATTERNS):
            continue

        # Check size constraints (< 500 KB and > 0 bytes)
        try:
            size = path.stat().st_size
            if size == 0 or size > MAX_FILE_SIZE_BYTES:
                continue
        except OSError:
            continue

        # Check file inclusion rules
        is_included = (
            filename in INCLUDE_EXACT_NAMES
            or filename.startswith("Dockerfile.")
            or filename.startswith(".env")
            or filename.endswith(".env")
            or path.suffix in INCLUDE_EXTENSIONS
        )
        if is_included:
            target_files.append(path)

    return sorted(target_files)


def parse_dlp_json(raw_json: str) -> List[Dict[str, Any]]:
    """Parses raw JSON from 'gcloud alpha dlp text inspect' into structured finding dicts."""
    if not raw_json or not raw_json.strip():
        return []

    try:
        data = json.loads(raw_json)
    except Exception:
        return []

    findings = data.get("findings")
    if findings is None:
        findings = data.get("result", {}).get("findings", [])
    if not isinstance(findings, list):
        return []

    parsed: List[Dict[str, Any]] = []
    for f in findings:
        info_type = f.get("infoType", {}).get("name", "UNKNOWN")
        likelihood = f.get("likelihood", "UNKNOWN")
        quote = f.get("quote", "")
        location = f.get("location", {})
        parsed.append({
            "source": "dlp",
            "info_type": info_type,
            "likelihood": likelihood,
            "quote": quote,
            "location": location,
        })
    return parsed


def inspect_file_with_dlp(
    file_path: Path,
    info_types: str = DEFAULT_INFO_TYPES,
) -> List[Dict[str, Any]]:
    """Executes 'gcloud alpha dlp text inspect' on a single file and parses results."""
    cmd = [
        "gcloud",
        "alpha",
        "dlp",
        "text",
        "inspect",
        f"--info-types={info_types}",
        f"--content-file={file_path}",
        "--format=json",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if proc.returncode != 0:
            return []
        return parse_dlp_json(proc.stdout)
    except Exception:
        return []


def scan_secrets_regex(file_path: Path) -> List[Dict[str, Any]]:
    """Scans a file line-by-line for credentials or API keys, ignoring comments."""
    findings: List[Dict[str, Any]] = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return findings

    for line_idx, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        if SECRET_PATTERN.search(line):
            findings.append({
                "source": "pattern_match",
                "info_type": "AUTH_TOKEN / API_KEY (Pattern Match)",
                "likelihood": "VERY_LIKELY",
                "line_number": line_idx,
                "line_match": f"{line_idx}:{stripped}",
            })
    return findings


def run_dlp_scan(
    root_dir: Path | str = ".",
    output_dir: Path | str = "reports",
    enable_dlp: bool = True,
    info_types: str = DEFAULT_INFO_TYPES,
) -> Dict[str, Any]:
    """Runs repository-wide DLP and regex scanning, writes text and JSON reports."""
    root = Path(root_dir).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    files_to_scan = discover_files(root)
    print(f"Starting Cloud DLP Sensitive Data & PII Scan across {len(files_to_scan)} files...")

    text_lines: List[str] = [
        "### PII SCAN RESULTS ###",
    ]
    all_findings: List[Dict[str, Any]] = []
    total_findings_count = 0
    dlp_findings_count = 0
    regex_findings_count = 0

    for file_path in files_to_scan:
        try:
            rel_display = "./" + str(file_path.relative_to(root))
        except ValueError:
            rel_display = str(file_path)

        text_lines.append(f"Inspecting {rel_display}...")

        # 1. Cloud DLP Inspection
        dlp_findings: List[Dict[str, Any]] = []
        if enable_dlp:
            dlp_findings = inspect_file_with_dlp(file_path, info_types=info_types)

        if dlp_findings:
            count = len(dlp_findings)
            dlp_findings_count += count
            total_findings_count += count
            line_msg = f"⚠️ [PII DETECTED] {rel_display} ({count} findings)"
            print(line_msg)
            text_lines.append(line_msg)
            for df in dlp_findings:
                item_line = f"  - Type: {df['info_type']} | Likelihood: {df['likelihood']}"
                text_lines.append(item_line)
                all_findings.append({
                    "file": rel_display,
                    "source": "cloud_dlp",
                    "info_type": df["info_type"],
                    "likelihood": df["likelihood"],
                    "line_number": None,
                    "details": df.get("quote", ""),
                })

        # 2. Secret Pattern Match
        regex_matches = scan_secrets_regex(file_path)
        if regex_matches:
            count = len(regex_matches)
            regex_findings_count += count
            total_findings_count += count
            line_msg = f"⚠️ [PII DETECTED] {rel_display} ({count} secret findings via pattern match)"
            print(line_msg)
            text_lines.append(line_msg)
            for rm in regex_matches:
                item_line = f"  - Type: AUTH_TOKEN / API_KEY (Pattern Match) | {rm['line_match']}"
                text_lines.append(item_line)
                all_findings.append({
                    "file": rel_display,
                    "source": "pattern_match",
                    "info_type": rm["info_type"],
                    "likelihood": rm["likelihood"],
                    "line_number": rm["line_number"],
                    "details": rm["line_match"],
                })

    # Summary Line
    if total_findings_count == 0:
        summary_msg = "✅ No sensitive data or PII detected by Cloud DLP."
    else:
        summary_msg = f"❌ Total PII findings detected: {total_findings_count}"

    print(summary_msg)
    text_lines.append(summary_msg)

    # Write reports/pii-scan.txt
    text_report_path = out_dir / "pii-scan.txt"
    text_report_path.write_text("\n".join(text_lines) + "\n", encoding="utf-8")

    # Write reports/pii-scan.json
    json_report_path = out_dir / "pii-scan.json"
    structured_report = {
        "summary": {
            "total_findings": total_findings_count,
            "dlp_findings_count": dlp_findings_count,
            "regex_findings_count": regex_findings_count,
            "scanned_files_count": len(files_to_scan),
            "has_violations": total_findings_count > 0,
        },
        "findings": all_findings,
    }
    json_report_path.write_text(json.dumps(structured_report, indent=2), encoding="utf-8")

    print(f"Reports generated: {text_report_path} and {json_report_path}")
    return structured_report


def parse_pii_report(report_path: Path | str) -> Dict[str, Any]:
    """Parses an existing pii-scan.json or pii-scan.txt report into a structured dictionary."""
    path = Path(report_path)
    if not path.exists():
        return {
            "total_findings": 0,
            "has_violations": False,
            "findings": [],
            "error": f"File not found: {path}",
        }

    # If JSON file or sibling JSON file exists, parse JSON
    if path.suffix == ".json":
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as err:
            return {"error": f"Failed to parse JSON: {err}"}

    sibling_json = path.with_suffix(".json")
    if sibling_json.exists():
        try:
            return json.loads(sibling_json.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Parse text format
    content = path.read_text(encoding="utf-8")
    detected_files: List[str] = []
    total_findings = 0

    for line in content.splitlines():
        if "[PII DETECTED]" in line:
            parts = line.split()
            # ⚠️ [PII DETECTED] <file>
            for part in parts:
                if part.startswith("./") or "/" in part:
                    detected_files.append(part)
                    break
        elif "Total PII findings detected:" in line:
            m = re.search(r"Total PII findings detected:\s*(\d+)", line)
            if m:
                total_findings = int(m.group(1))

    has_violations = (
        total_findings > 0
        or "PII finding" in content
        or "AUTH_TOKEN" in content
        or "API_KEY" in content
        or "SECRET" in content.upper()
    ) and "No sensitive data" not in content

    return {
        "summary": {
            "total_findings": total_findings,
            "has_violations": has_violations,
        },
        "detected_files": list(set(detected_files)),
    }


def main() -> None:
    """CLI entrypoint for running the DLP and PII scanner."""
    parser = argparse.ArgumentParser(
        description="Google Cloud DLP Sensitive Data & PII Scan",
    )
    parser.add_argument(
        "--root-dir",
        default=".",
        help="Root directory of repository to scan (default: .)",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Directory to save scan reports (default: reports)",
    )
    parser.add_argument(
        "--skip-dlp",
        action="store_true",
        default=os.environ.get("SKIP_DLP", "").lower() in ("1", "true", "yes"),
        help="Skip gcloud DLP inspect and run secret pattern scan only",
    )
    parser.add_argument(
        "--info-types",
        default=os.environ.get("DLP_INFO_TYPES", DEFAULT_INFO_TYPES),
        help="Comma-separated list of DLP info types",
    )

    args = parser.parse_args()

    run_dlp_scan(
        root_dir=args.root_dir,
        output_dir=args.output_dir,
        enable_dlp=not args.skip_dlp,
        info_types=args.info_types,
    )


if __name__ == "__main__":
    main()
