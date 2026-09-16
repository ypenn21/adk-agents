"""Unit tests for dlp_scan.py."""

import json
import sys
from pathlib import Path
import pytest

# Add .github/scripts to PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dlp_scan import (
    discover_files,
    parse_dlp_json,
    scan_secrets_regex,
    run_dlp_scan,
    parse_pii_report,
)


def test_discover_files_filtering(tmp_path: Path):
    # Included files
    (tmp_path / "app.py").write_text("print('hello')")
    (tmp_path / "Dockerfile").write_text("FROM python:3.11")
    (tmp_path / ".env.local").write_text("PORT=8000")

    # Excluded files / folders
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config.txt").write_text("git config")

    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    (venv_dir / "lib.py").write_text("venv lib")

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "pii-scan.txt").write_text("report")

    (tmp_path / "image.png").write_text("binary content")
    (tmp_path / "empty.py").write_text("")  # 0 bytes

    discovered = discover_files(tmp_path)
    discovered_names = [f.name for f in discovered]

    assert "app.py" in discovered_names
    assert "Dockerfile" in discovered_names
    assert ".env.local" in discovered_names

    assert "config.txt" not in discovered_names
    assert "lib.py" not in discovered_names
    assert "pii-scan.txt" not in discovered_names
    assert "image.png" not in discovered_names
    assert "empty.py" not in discovered_names


def test_parse_dlp_json_direct_and_nested():
    direct_json = json.dumps({
        "findings": [
            {
                "infoType": {"name": "EMAIL_ADDRESS"},
                "likelihood": "LIKELY",
                "quote": "dev@example.com",
            }
        ]
    })
    findings = parse_dlp_json(direct_json)
    assert len(findings) == 1
    assert findings[0]["info_type"] == "EMAIL_ADDRESS"
    assert findings[0]["likelihood"] == "LIKELY"
    assert findings[0]["quote"] == "dev@example.com"

    nested_json = json.dumps({
        "result": {
            "findings": [
                {
                    "infoType": {"name": "PHONE_NUMBER"},
                    "likelihood": "VERY_LIKELY",
                    "quote": "555-0199",
                }
            ]
        }
    })
    nested_findings = parse_dlp_json(nested_json)
    assert len(nested_findings) == 1
    assert nested_findings[0]["info_type"] == "PHONE_NUMBER"

    assert parse_dlp_json("invalid json") == []
    assert parse_dlp_json("{}") == []


def test_scan_secrets_regex(tmp_path: Path):
    target_file = tmp_path / "settings.py"
    target_file.write_text(
        '# SECRET_KEY = "ignore-this-comment-1234567890"\n'
        'SECRET_KEY = "django-insecure-m6(8z&svd8&5z=f3(9v9dcgp(ti2kja12i%*g0-bj37cha)_vd"\n'
        'GEMINI_API_KEY = "AIzaSyD-sample-key-123456789012345678"\n'
        'DEBUG = True\n'
    )

    findings = scan_secrets_regex(target_file)
    assert len(findings) == 2

    finding_types = [f["info_type"] for f in findings]
    assert all("AUTH_TOKEN / API_KEY" in t for t in finding_types)
    line_numbers = [f["line_number"] for f in findings]
    assert line_numbers == [2, 3]


def test_run_dlp_scan_clean(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('Clean code')\n")
    out_dir = tmp_path / "reports"

    report = run_dlp_scan(root_dir=src_dir, output_dir=out_dir, enable_dlp=False)

    assert report["summary"]["total_findings"] == 0
    assert report["summary"]["has_violations"] is False

    txt_content = (out_dir / "pii-scan.txt").read_text()
    assert "✅ No sensitive data or PII detected by Cloud DLP." in txt_content

    json_content = json.loads((out_dir / "pii-scan.json").read_text())
    assert json_content["summary"]["total_findings"] == 0


def test_run_dlp_scan_with_findings(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "config.py").write_text(
        'SECRET_KEY = "django-insecure-abcdefghijklmnop"\n'
    )
    out_dir = tmp_path / "reports"

    report = run_dlp_scan(root_dir=src_dir, output_dir=out_dir, enable_dlp=False)

    assert report["summary"]["total_findings"] == 1
    assert report["summary"]["has_violations"] is True
    assert len(report["findings"]) == 1

    txt_content = (out_dir / "pii-scan.txt").read_text()
    assert "⚠️ [PII DETECTED]" in txt_content
    assert "❌ Total PII findings detected: 1" in txt_content


def test_parse_pii_report(tmp_path: Path):
    txt_report = tmp_path / "pii-scan.txt"
    txt_report.write_text(
        "### PII SCAN RESULTS ###\n"
        "Inspecting ./web/settings.py...\n"
        "⚠️ [PII DETECTED] ./web/settings.py (1 secret findings via pattern match)\n"
        "  - Type: AUTH_TOKEN / API_KEY (Pattern Match) | 23:SECRET_KEY = 'secret1234567890'\n"
        "❌ Total PII findings detected: 1\n"
    )

    parsed = parse_pii_report(txt_report)
    assert parsed["summary"]["total_findings"] == 1
    assert parsed["summary"]["has_violations"] is True
    assert "./web/settings.py" in parsed["detected_files"]
