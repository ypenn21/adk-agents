"""Unit Tests for Shared CI/CD Agent Helper Module (.github/scripts/helper.py).

Cites Decisions from docs/spec.md (D-1, D-4, D-5, D-6, D-7, D-8, D-10).
"""

import os
import sys
import json
import urllib.request
import urllib.error
from unittest.mock import MagicMock, patch, AsyncMock
from enum import Enum
from typing import Optional
import pytest
from pydantic import BaseModel, Field

# Ensure .github/scripts is importable
_scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import helper


# Sample Test Models
class MockFindingSeverity(str, Enum):
    BLOCKER = "BLOCKER"
    WARNING = "WARNING"
    INFO = "INFO"


class MockInlineFinding(BaseModel):
    file_path: str
    line_number: Optional[int] = None
    severity: MockFindingSeverity = MockFindingSeverity.INFO
    title: str
    details: str
    suggestion: str = ""
    pii_leak: bool = False


class MockReviewStatus(str, Enum):
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    COMMENT = "COMMENT"


class MockPRReviewReport(BaseModel):
    overall_status: MockReviewStatus
    summary: str
    findings: list[MockInlineFinding] = Field(default_factory=list)


class MockSeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MockViolationCategory(str, Enum):
    PII_LEAK = "PII_LEAK"
    SECURITY_VULNERABILITY = "SECURITY_VULNERABILITY"


class MockFailureDetail(BaseModel):
    category: MockViolationCategory
    component: str
    severity: MockSeverityLevel
    reason: str
    remediation: str


class MockQualityGateDecision(BaseModel):
    passed: bool
    summary: str
    failures: list[MockFailureDetail] = Field(default_factory=list)


# =====================================================================
# Tests: sanitize_and_validate_repo & _sanitize_and_validate_repo (D-10)
# =====================================================================

def test_sanitize_and_validate_repo_valid():
    """Sanitizes repo string with spaces, quotes, and .git extensions."""
    assert helper.sanitize_and_validate_repo("owner/repo") == ("owner", "repo")
    assert helper.sanitize_and_validate_repo("  owner/repo.git  ") == ("owner", "repo")
    assert helper.sanitize_and_validate_repo("'owner/repo'") == ("owner", "repo")
    assert helper.sanitize_and_validate_repo('"owner/repo.git"') == ("owner", "repo")


def test_sanitize_and_validate_repo_invalid():
    """Returns None for invalid repository formats."""
    assert helper.sanitize_and_validate_repo("") is None
    assert helper.sanitize_and_validate_repo("invalid-repo") is None
    assert helper.sanitize_and_validate_repo("a/b/c") is None
    assert helper.sanitize_and_validate_repo("   ") is None


# =====================================================================
# Tests: resolve_env_config (D-4)
# =====================================================================

def test_resolve_env_config_cli_priority(monkeypatch):
    """Explicit parameters take precedence over environment variables."""
    monkeypatch.setenv("PULL_REQUEST_NUMBER", "99")
    monkeypatch.setenv("GITHUB_REPOSITORY", "env/repo")
    monkeypatch.setenv("GH_TOKEN", "env-token")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "env-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-east1")
    monkeypatch.setenv("LLM_Model", "gemini-env")

    config = helper.resolve_env_config(
        pr_number="123",
        repo="cli/repo",
        token="cli-token",
        project_id="cli-project",
        location="us-west1",
        model="gemini-cli",
    )

    assert config["pr_number"] == "123"
    assert config["repo"] == "cli/repo"
    assert config["token"] == "cli-token"
    assert config["project_id"] == "cli-project"
    assert config["location"] == "us-west1"
    assert config["model"] == "gemini-cli"


def test_resolve_env_config_fallback_defaults(monkeypatch):
    """Falls back to default values when env vars and args are unset."""
    for key in ["PULL_REQUEST_NUMBER", "PR_NUMBER", "GITHUB_REPOSITORY", "REPOSITORY",
                "GH_TOKEN", "GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN",
                "GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "GOOGLE_CLOUD_LOCATION",
                "LLM_Model", "LLM_MODEL"]:
        monkeypatch.delenv(key, raising=False)

    config = helper.resolve_env_config()
    assert config["pr_number"] is None
    assert config["repo"] is None
    assert config["token"] is None
    assert config["project_id"] == "local-project"
    assert config["location"] == "us-central1"
    assert config["model"] == "gemini-3.7-flash"


# =====================================================================
# Tests: fetch_pr_modified_lines
# =====================================================================

def test_fetch_pr_modified_lines_empty_token():
    """Returns empty dict when token is missing or whitespace."""
    assert helper.fetch_pr_modified_lines("owner", "repo", 42, "") == {}
    assert helper.fetch_pr_modified_lines("owner", "repo", 42, "   ") == {}


def test_fetch_pr_modified_lines_success():
    """Parses modified lines within diff hunks correctly."""
    mock_files = json.dumps([
        {
            "filename": "app/main.py",
            "patch": "@@ -1,3 +1,4 @@\n import os\n+import sys\n def run():",
        },
        {
            "filename": "empty.py",
            "patch": "",
        }
    ]).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = mock_files
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        diff_map = helper.fetch_pr_modified_lines("owner", "repo", 42, "token")

    assert "app/main.py" in diff_map
    assert 2 in diff_map["app/main.py"]
    assert "empty.py" not in diff_map


def test_fetch_pr_modified_lines_network_error(capsys):
    """Handles network errors gracefully and logs warning."""
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Network down")):
        result = helper.fetch_pr_modified_lines("owner", "repo", 42, "token")
        assert result == {}
    captured = capsys.readouterr()
    assert "[Warning] Could not fetch PR diff hunks" in captured.out


# =====================================================================
# Tests: fetch_pr_comments (D-1)
# =====================================================================

def test_fetch_pr_comments_empty_token():
    """Returns empty list when token is empty or whitespace."""
    assert helper.fetch_pr_comments("owner", "repo", 42, "") == []
    assert helper.fetch_pr_comments("owner", "repo", 42, "   ") == []


def test_fetch_pr_comments_success():
    """Fetches comments and parses JSON list."""
    mock_data = json.dumps([{"id": 10, "path": "test.py", "line": 5, "body": "comment"}]).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = mock_data
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        comments = helper.fetch_pr_comments("owner", "repo", 42, "token")

    assert len(comments) == 1
    assert comments[0]["id"] == 10


def test_fetch_pr_comments_error(capsys):
    """Gracefully falls back to empty list on error."""
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Timeout")):
        comments = helper.fetch_pr_comments("owner", "repo", 42, "token")
        assert comments == []
    captured = capsys.readouterr()
    assert "[Warning] Could not fetch existing PR comments" in captured.out


# =====================================================================
# Tests: is_duplicate_comment & _is_duplicate_comment (D-10)
# =====================================================================

def test_is_duplicate_comment_matching():
    """Matches duplicates based on path, line, and title."""
    finding = MockInlineFinding(
        file_path="src/app.py",
        line_number=15,
        severity=MockFindingSeverity.BLOCKER,
        title="Uncaught Exception",
        details="May raise error",
    )
    comments = [
        {"path": "src/app.py", "line": 15, "body": "**[BLOCKER] Uncaught Exception**\nDetails"},
    ]
    assert helper.is_duplicate_comment(finding, comments) is True


def test_is_duplicate_comment_no_match():
    """Returns False when line or path differs."""
    finding = MockInlineFinding(
        file_path="src/app.py",
        line_number=15,
        severity=MockFindingSeverity.BLOCKER,
        title="Uncaught Exception",
        details="May raise error",
    )
    comments = [
        {"path": "src/app.py", "line": 20, "body": "**[BLOCKER] Uncaught Exception**"},
        {"path": "src/other.py", "line": 15, "body": "**[BLOCKER] Uncaught Exception**"},
    ]
    assert helper.is_duplicate_comment(finding, comments) is False


# =====================================================================
# Tests: validate_and_sanitize_findings
# =====================================================================

def test_validate_and_sanitize_findings_split():
    """Splits findings into valid inline diff hunk findings vs out-of-hunk findings."""
    f1 = MockInlineFinding(file_path="main.py", line_number=10, title="In diff", details="")
    f2 = MockInlineFinding(file_path="main.py", line_number=99, title="Out of hunk", details="")
    f3 = MockInlineFinding(file_path="other.py", line_number=5, title="File not in diff", details="")
    f4 = MockInlineFinding(file_path="main.py", line_number=None, title="No line", details="")

    diff_map = {"main.py": [10, 11, 12]}
    valid, out_of_hunk = helper.validate_and_sanitize_findings([f1, f2, f3, f4], diff_map)

    assert len(valid) == 1
    assert valid[0].title == "In diff"
    assert len(out_of_hunk) == 3


# =====================================================================
# Tests: send_github_review_sync & send_github_issue_comment_sync
# =====================================================================

def test_send_github_review_sync():
    """Sends POST request to review API and returns status & body."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"id": 123}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        status, body = helper.send_github_review_sync("owner", "repo", 42, "token", {"event": "APPROVE"})
        assert status == 200
        assert "123" in body


def test_send_github_issue_comment_sync():
    """Sends POST request to issue comments API and returns status & body."""
    mock_resp = MagicMock()
    mock_resp.status = 201
    mock_resp.read.return_value = b'{"id": 456}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        status, body = helper.send_github_issue_comment_sync("owner", "repo", 42, "token", "Comment body")
        assert status == 201
        assert "456" in body


# =====================================================================
# Tests: post_github_pr_review
# =====================================================================

@pytest.mark.asyncio
async def test_post_github_pr_review_clean_approve():
    """Clean PR submits APPROVE review."""
    report = MockPRReviewReport(
        overall_status=MockReviewStatus.APPROVE,
        summary="Clean PR",
        findings=[],
    )
    with patch("helper.send_github_review_sync", return_value=(200, '{"id": 1}')) as mock_send:
        result = await helper.post_github_pr_review(report, "42", "owner/repo", "token")
        assert result is True
        mock_send.assert_called_once()
        payload = mock_send.call_args[0][4]
        assert payload["event"] == "COMMENT"
        assert payload["comments"] == []


@pytest.mark.asyncio
async def test_post_github_pr_review_422_fallback():
    """HTTP 422 triggers fallback to issue comment."""
    f1 = MockInlineFinding(file_path="main.py", line_number=10, title="Finding", details="details")
    report = MockPRReviewReport(
        overall_status=MockReviewStatus.REQUEST_CHANGES,
        summary="Issues found",
        findings=[f1],
    )
    diff_map = {"main.py": [10]}

    with patch("helper.send_github_review_sync", side_effect=[
        (422, "Unprocessable Entity"),
        (200, '{"id": 2}')
    ]), patch("helper.send_github_issue_comment_sync", return_value=(201, '{"id": 3}')):
        result = await helper.post_github_pr_review(report, "42", "owner/repo", "token", modified_files_diff=diff_map)
        assert result is True


# =====================================================================
# Tests: format_pr_review_text & format_text_decision
# =====================================================================

def test_format_pr_review_text():
    """Formats PR review report into text."""
    f1 = MockInlineFinding(file_path="a.py", line_number=1, title="T1", details="D1")
    report = MockPRReviewReport(
        overall_status=MockReviewStatus.REQUEST_CHANGES,
        summary="Summary text",
        findings=[f1],
    )
    text = helper.format_pr_review_text(report)
    assert "### Status: REQUEST_CHANGES" in text
    assert "Summary text" in text
    assert "1. [INFO] a.py:1 - T1" in text


def test_format_text_decision_pass_and_fail():
    """Formats QualityGateDecision into GATE_PASSED or GATE_FAILED text."""
    pass_decision = MockQualityGateDecision(passed=True, summary="All good", failures=[])
    pass_text = helper.format_text_decision(pass_decision)
    assert pass_text.startswith("GATE_PASSED\n\n")

    fail_detail = MockFailureDetail(
        category=MockViolationCategory.PII_LEAK,
        component="file.txt",
        severity=MockSeverityLevel.CRITICAL,
        reason="Found secret",
        remediation="Remove secret",
    )
    fail_decision = MockQualityGateDecision(passed=False, summary="Violations", failures=[fail_detail])
    fail_text = helper.format_text_decision(fail_decision)
    assert fail_text.startswith("GATE_FAILED\n\n")
    assert "[CRITICAL] PII_LEAK in file.txt" in fail_text


# =====================================================================
# Tests: write_json_and_text_reports, write_pr_reports, write_gate_reports (D-5)
# =====================================================================

def test_write_reports(tmp_path, monkeypatch):
    """Writes JSON and text report artifacts to disk."""
    monkeypatch.chdir(tmp_path)
    report = MockPRReviewReport(
        overall_status=MockReviewStatus.APPROVE,
        summary="Clean",
        findings=[],
    )
    helper.write_pr_reports(report)
    assert os.path.exists("reports/pr-review.json")
    assert os.path.exists("reports/pr-review.txt")

    decision = MockQualityGateDecision(
        passed=True,
        summary="Pass",
        failures=[],
    )
    helper.write_gate_reports(decision)
    assert os.path.exists("reports/gate-decision.json")
    assert os.path.exists("reports/decision.txt")


# =====================================================================
# Tests: parse_agent_structured_output (D-7)
# =====================================================================

def test_parse_agent_structured_output_from_model():
    """Returns model instance directly if already parsed."""
    report = MockPRReviewReport(overall_status=MockReviewStatus.APPROVE, summary="Clean", findings=[])
    parsed = helper.parse_agent_structured_output(report, MockPRReviewReport)
    assert parsed == report


def test_parse_agent_structured_output_from_dict():
    """Coerces dict into target Pydantic model."""
    data = {"overall_status": "APPROVE", "summary": "Clean", "findings": []}
    parsed = helper.parse_agent_structured_output(data, MockPRReviewReport)
    assert parsed.overall_status == MockReviewStatus.APPROVE


def test_parse_agent_structured_output_from_json_str():
    """Parses JSON string into target Pydantic model."""
    data_str = '{"overall_status": "REQUEST_CHANGES", "summary": "Issues", "findings": []}'
    parsed = helper.parse_agent_structured_output(data_str, MockPRReviewReport)
    assert parsed.overall_status == MockReviewStatus.REQUEST_CHANGES


# =====================================================================
# Tests: read_text_file & ensure_directory
# =====================================================================

def test_read_text_file(tmp_path):
    """Safely reads file if existing or returns default."""
    test_file = tmp_path / "test.txt"
    assert helper.read_text_file(str(test_file), default="default") == "default"
    test_file.write_text("hello world", encoding="utf-8")
    assert helper.read_text_file(str(test_file)) == "hello world"
    
def test_ensure_directory(tmp_path):
    """Ensures directory exists and returns path."""
    target_dir = tmp_path / "sub" / "dir"
    res = helper.ensure_directory(str(target_dir))
    assert os.path.exists(res)


# =====================================================================
# Tests: calculate_token_spend & write_token_usage_report (D-13, D-14)
# =====================================================================

class MockUsageMetadata:
    """Mock object mimicking Google Antigravity / Gemini UsageMetadata."""
    def __init__(
        self,
        prompt_token_count: int = 0,
        cached_content_token_count: int = 0,
        candidates_token_count: int = 0,
        thoughts_token_count: int = 0,
        total_token_count: int = 0,
    ):
        self.prompt_token_count = prompt_token_count
        self.cached_content_token_count = cached_content_token_count
        self.candidates_token_count = candidates_token_count
        self.thoughts_token_count = thoughts_token_count
        self.total_token_count = total_token_count


def test_calculate_token_spend_standard_usage():
    """Decision D-13: Verifies exact token spend calculation with caching and thinking tokens."""
    # 120k prompt tokens (20k cached, 100k net uncached) -> 100k * 0.75 / 1M = 0.075
    # 20k cached prompt tokens -> 20k * 0.075 / 1M = 0.0015
    # 10k candidate + 10k thought tokens -> 20k * 3.75 / 1M = 0.075
    # Total spend = 0.075 + 0.0015 + 0.075 = 0.1515
    usage = MockUsageMetadata(
        prompt_token_count=120_000,
        cached_content_token_count=20_000,
        candidates_token_count=10_000,
        thoughts_token_count=10_000,
        total_token_count=140_000,
    )

    stats = helper.calculate_token_spend(usage, "gemini-3.7-flash")
    assert stats["prompt_tokens"] == 120_000
    assert stats["cached_tokens"] == 20_000
    assert stats["candidate_tokens"] == 10_000
    assert stats["thought_tokens"] == 10_000
    assert stats["total_tokens"] == 140_000
    assert stats["total_cost_usd"] == 0.1515

    # Dict input format
    usage_dict = {
        "prompt_token_count": 120_000,
        "cached_content_token_count": 20_000,
        "candidates_token_count": 10_000,
        "thoughts_token_count": 10_000,
        "total_token_count": 140_000,
    }
    stats_dict = helper.calculate_token_spend(usage_dict, "gemini-3.8-flash")
    assert stats_dict["total_cost_usd"] == 0.1515


def test_calculate_token_spend_empty_or_none():
    """Decision D-13: Safely handles None or empty usage objects with 0 costs."""
    stats_none = helper.calculate_token_spend(None)
    assert stats_none["total_tokens"] == 0
    assert stats_none["total_cost_usd"] == 0.0
    assert stats_none["prompt_tokens"] == 0

    stats_empty = helper.calculate_token_spend({})
    assert stats_empty["total_tokens"] == 0
    assert stats_empty["total_cost_usd"] == 0.0


def test_resolve_env_config_budget_defaults_and_env(monkeypatch):
    """Decision D-13: Verifies default budget values and environment variable overrides."""
    # Clear env vars
    for var in [
        "MAX_TOTAL_TOKENS",
        "MAX_INPUT_TOKENS",
        "MAX_OUTPUT_TOKENS",
        "MAX_MODEL_CALLS",
        "MAX_TOOL_CALLS",
        "MAX_SPEND_USD",
    ]:
        monkeypatch.delenv(var, raising=False)

    cfg_default = helper.resolve_env_config()
    assert cfg_default["max_total_tokens"] == 1_100_000
    assert cfg_default["max_input_tokens"] == 800_000
    assert cfg_default["max_output_tokens"] == 200_000
    assert cfg_default["max_model_calls"] == 100
    assert cfg_default["max_tool_calls"] == 50
    assert cfg_default["max_spend_usd"] is None

    # Set env vars
    monkeypatch.setenv("MAX_TOTAL_TOKENS", "50000")
    monkeypatch.setenv("MAX_INPUT_TOKENS", "40000")
    monkeypatch.setenv("MAX_OUTPUT_TOKENS", "10000")
    monkeypatch.setenv("MAX_MODEL_CALLS", "5")
    monkeypatch.setenv("MAX_TOOL_CALLS", "12")
    monkeypatch.setenv("MAX_SPEND_USD", "0.50")

    cfg_env = helper.resolve_env_config()
    assert cfg_env["max_input_tokens"] == 40_000
    assert cfg_env["max_output_tokens"] == 10_000
    assert cfg_env["max_model_calls"] == 5
    assert cfg_env["max_tool_calls"] == 12
    assert cfg_env["max_spend_usd"] == 0.50
    # $0.50 / $3.75 * 1M = 133,333 -> min(50_000, 133_333) = 50_000
    assert cfg_env["max_total_tokens"] == 50_000

    # CLI arg overrides env var
    cfg_cli = helper.resolve_env_config(max_total_tokens=60_000, max_spend_usd=0.80)
    assert cfg_cli["max_spend_usd"] == 0.80
    assert cfg_cli["max_total_tokens"] == 60_000


def test_resolve_env_config_max_spend_usd_derived_ceiling(monkeypatch):
    """Decision D-13: Verifies MAX_SPEND_USD=0.375 caps max_total_tokens to 100_000."""
    monkeypatch.delenv("MAX_TOTAL_TOKENS", raising=False)
    monkeypatch.setenv("MAX_SPEND_USD", "0.375")

    # (0.375 / 3.75) * 1,000,000 = 100,000 tokens
    # Default max_total_tokens is 1_100_000, capped to min(1_100_000, 100_000) = 100_000
    cfg = helper.resolve_env_config()
    assert cfg["max_total_tokens"] == 100_000
    assert cfg["max_spend_usd"] == 0.375


def test_write_token_usage_report_file_generation(tmp_path):
    """Decision D-14: Verifies structured schema and file persistence of token usage report."""
    report_file = tmp_path / "reports" / "token-usage.json"
    usage_data = {
        "prompt_tokens": 120_000,
        "cached_tokens": 20_000,
        "candidate_tokens": 10_000,
        "thought_tokens": 10_000,
        "total_tokens": 140_000,
        "total_cost_usd": 0.1515,
    }
    budget_limits = {
        "max_total_tokens": 120_000,
        "max_input_tokens": 100_000,
        "max_output_tokens": 25_000,
        "max_model_calls": 10,
        "max_tool_calls": 25,
        "max_spend_usd": None,
    }

    helper.write_token_usage_report(
        usage_data=usage_data,
        stop_reason="MAX_TOTAL_TOKENS_EXCEEDED",
        output_path=str(report_file),
        model="gemini-3.7-flash",
        budget_limits=budget_limits,
    )

    assert report_file.exists()
    with open(report_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["model"] == "gemini-3.7-flash"
    assert data["stop_reason"] == "MAX_TOTAL_TOKENS_EXCEEDED"
    assert data["budget_exceeded"] is True
    assert data["prompt_tokens"] == 120_000
    assert data["cached_tokens"] == 20_000
    assert data["candidate_tokens"] == 10_000
    assert data["thought_tokens"] == 10_000
    assert data["total_tokens"] == 140_000
    assert data["total_cost_usd"] == 0.1515
    assert data["budget_limits"]["max_total_tokens"] == 120_000


# =====================================================================
# Tests: Batch & Triage Schemas (Decision D-15, D-16)
# =====================================================================

def test_batch_schemas_instantiation():
    """Validates instantiation and default values for batch schemas."""
    item = helper.FileDiffItem(filename="app/main.py")
    assert item.filename == "app/main.py"
    assert item.status == "modified"
    assert item.additions == 0
    assert item.deletions == 0
    assert item.changes == 0
    assert item.patch == ""
    assert item.estimated_tokens == 0
    assert item.pii_flagged is False
    assert item.risk_score == 0

    batch = helper.ReviewBatch(
        batch_index=1,
        total_batches=2,
        files=[item],
        total_estimated_tokens=50,
    )
    assert batch.batch_index == 1
    assert batch.total_batches == 2
    assert len(batch.files) == 1
    assert batch.total_estimated_tokens == 50

    summary = helper.PRTriageSummary(
        total_files_in_pr=100,
        reviewable_files_count=80,
        excluded_files_count=20,
        triaged_files_count=50,
        skipped_files_count=30,
        batches_executed=0,
        triage_applied=True,
    )
    assert summary.total_files_in_pr == 100
    assert summary.reviewable_files_count == 80
    assert summary.excluded_files_count == 20
    assert summary.triaged_files_count == 50
    assert summary.skipped_files_count == 30
    assert summary.batches_executed == 0
    assert summary.triage_applied is True


# =====================================================================
# Tests: fetch_all_pr_modified_files (D-15)
# =====================================================================

def test_fetch_all_pr_modified_files_empty_token():
    """Returns empty list when token is empty or whitespace."""
    assert helper.fetch_all_pr_modified_files("owner", "repo", 42, "") == []
    assert helper.fetch_all_pr_modified_files("owner", "repo", 42, "   ") == []


def test_fetch_all_pr_modified_files_single_page():
    """Fetches a single page of files and halts when < 100 items returned."""
    mock_files = json.dumps([
        {"filename": "app/a.py", "patch": "@@ -1 +1 @@"},
        {"filename": "app/b.py", "patch": "@@ -1 +1 @@"},
    ]).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = mock_files
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        files = helper.fetch_all_pr_modified_files("owner", "repo", 42, "dummy-token")
        assert len(files) == 2
        assert files[0]["filename"] == "app/a.py"
        assert files[1]["filename"] == "app/b.py"
        assert mock_urlopen.call_count == 1
        req = mock_urlopen.call_args[0][0]
        assert "per_page=100&page=1" in req.full_url
        assert req.headers["Authorization"] == "Bearer dummy-token"


def test_fetch_all_pr_modified_files_pagination_multi_page():
    """Paginates across multiple pages until a page with < 100 files is reached."""
    page_1_data = json.dumps([{"filename": f"file_{i}.py", "patch": "+line"} for i in range(100)]).encode("utf-8")
    page_2_data = json.dumps([{"filename": f"file_{100 + i}.py", "patch": "+line"} for i in range(45)]).encode("utf-8")

    resp_1 = MagicMock()
    resp_1.status = 200
    resp_1.read.return_value = page_1_data
    resp_1.__enter__.return_value = resp_1
    resp_1.__exit__.return_value = None

    resp_2 = MagicMock()
    resp_2.status = 200
    resp_2.read.return_value = page_2_data
    resp_2.__enter__.return_value = resp_2
    resp_2.__exit__.return_value = None

    with patch("urllib.request.urlopen", side_effect=[resp_1, resp_2]) as mock_urlopen:
        all_files = helper.fetch_all_pr_modified_files("owner", "repo", 99, "token-xyz")
        assert len(all_files) == 145
        assert all_files[0]["filename"] == "file_0.py"
        assert all_files[99]["filename"] == "file_99.py"
        assert all_files[100]["filename"] == "file_100.py"
        assert all_files[144]["filename"] == "file_144.py"
        assert mock_urlopen.call_count == 2
        call_urls = [call[0][0].full_url for call in mock_urlopen.call_args_list]
        assert "page=1" in call_urls[0]
        assert "page=2" in call_urls[1]


def test_fetch_all_pr_modified_files_network_error(capsys):
    """Gracefully handles network errors during pagination and returns partial results."""
    page_1_data = json.dumps([{"filename": f"file_{i}.py"} for i in range(100)]).encode("utf-8")
    resp_1 = MagicMock()
    resp_1.status = 200
    resp_1.read.return_value = page_1_data
    resp_1.__enter__.return_value = resp_1
    resp_1.__exit__.return_value = None

    with patch("urllib.request.urlopen", side_effect=[resp_1, urllib.error.URLError("Connection reset")]):
        files = helper.fetch_all_pr_modified_files("owner", "repo", 101, "tok")
        assert len(files) == 100
    captured = capsys.readouterr()
    assert "[Warning] Could not fetch PR diff hunks from GitHub API" in captured.out


# =====================================================================
# Tests: EXCLUDED_FILE_PATTERNS & is_excluded_file (D-16)
# =====================================================================

def test_is_excluded_file_patterns():
    """Matches lockfiles, minified files, map files, binaries, and vendor directories."""
    # Lockfiles
    assert helper.is_excluded_file("package-lock.json") is True
    assert helper.is_excluded_file("frontend/package-lock.json") is True
    assert helper.is_excluded_file("yarn.lock") is True
    assert helper.is_excluded_file("pnpm-lock.yaml") is True
    assert helper.is_excluded_file("poetry.lock") is True
    assert helper.is_excluded_file("Pipfile.lock") is True
    assert helper.is_excluded_file("composer.lock") is True
    assert helper.is_excluded_file("go.sum") is True

    # Minified assets and maps
    assert helper.is_excluded_file("static/bundle.min.js") is True
    assert helper.is_excluded_file("dist/styles.min.css") is True
    assert helper.is_excluded_file("dist/bundle.js.map") is True

    # Binary media and documents
    assert helper.is_excluded_file("assets/logo.png") is True
    assert helper.is_excluded_file("images/banner.jpg") is True
    assert helper.is_excluded_file("icons/favicon.ico") is True
    assert helper.is_excluded_file("docs/manual.pdf") is True
    assert helper.is_excluded_file("build/archive.zip") is True
    assert helper.is_excluded_file("fonts/inter.woff2") is True

    # Vendor and node_modules
    assert helper.is_excluded_file("vendor/autoload.php") is True
    assert helper.is_excluded_file("src/vendor/lib.py") is True
    assert helper.is_excluded_file("node_modules/axios/index.js") is True
    assert helper.is_excluded_file("web/node_modules/package.json") is True

    # Non-excluded standard files
    assert helper.is_excluded_file("app/main.py") is False
    assert helper.is_excluded_file("src/routes/api.ts") is False
    assert helper.is_excluded_file("Dockerfile") is False
    assert helper.is_excluded_file("README.md") is False
    assert helper.is_excluded_file("tests/test_helper.py") is False
    assert helper.is_excluded_file("") is False


# =====================================================================
# Tests: calculate_file_risk_score (D-16)
# =====================================================================

def test_calculate_file_risk_score_pii_context():
    """Flags PII and awards +100 risk score when file is cited in DLP scan."""
    risk, pii_flag = helper.calculate_file_risk_score(
        filename="src/user_service.py",
        pii_context="Found email leak in src/user_service.py: line 42",
        additions=0,
        changes=0,
    )
    assert pii_flag is True
    assert risk >= 100


def test_calculate_file_risk_score_security_and_api_and_size():
    """Awards +50 for security paths, +30 for API routes, and caps size contribution at 20."""
    risk, pii_flag = helper.calculate_file_risk_score(
        filename="api/v1/auth/tokens.py",
        pii_context="",
        additions=150,
        changes=150,
    )
    assert pii_flag is False
    # +50 (auth/token) + 30 (api) + min(20, 150 // 10) = 50 + 30 + 15 = 95
    assert risk == 95

    # Size cap at 20
    risk_large, _ = helper.calculate_file_risk_score(
        filename="api/routes.py",
        pii_context="",
        additions=500,
        changes=500,
    )
    # 0 security + 30 api + min(20, 500 // 10) = 30 + 20 = 50
    assert risk_large == 50


def test_calculate_file_risk_score_empty_and_neutral():
    """Returns 0 risk score and False for neutral files and empty names."""
    assert helper.calculate_file_risk_score("") == (0, False)
    risk, pii_flag = helper.calculate_file_risk_score(
        filename="docs/readme.txt",
        pii_context="",
        additions=5,
        changes=5,
    )
    assert risk == 0
    assert pii_flag is False


# =====================================================================
# Tests: triage_and_filter_files (D-16)
# =====================================================================

def test_triage_and_filter_files_exclusions():
    """Filters excluded files and accurately computes triage summary."""
    files = [
        {"filename": "app/routes.py", "patch": "@@ -1 +1 @@\n+line", "additions": 1, "changes": 1},
        {"filename": "package-lock.json", "patch": "@@ -1 +1 @@", "additions": 1000, "changes": 1000},
        {"filename": "assets/logo.png", "patch": "", "additions": 0, "changes": 0},
        {"filename": "vendor/bundle.js", "patch": "@@ -1 +1 @@", "additions": 500, "changes": 500},
        {"filename": "app/auth.py", "patch": "@@ -1 +1 @@\n+auth", "additions": 2, "changes": 2},
    ]

    filtered, summary = helper.triage_and_filter_files(files, max_cap=200)
    assert len(filtered) == 2
    assert summary.total_files_in_pr == 5
    assert summary.reviewable_files_count == 2
    assert summary.excluded_files_count == 3
    assert summary.triaged_files_count == 2
    assert summary.skipped_files_count == 0
    assert summary.triage_applied is False
    assert {f.filename for f in filtered} == {"app/routes.py", "app/auth.py"}


def test_triage_and_filter_files_capping():
    """Capping at max_cap sorts by risk score descending and retains highest risk files."""
    files = []
    # 10 security/auth files (risk >= 50)
    for i in range(10):
        files.append({
            "filename": f"src/auth/service_{i}.py",
            "patch": "@@ -1,5 +1,10 @@\n" + "\n".join(f"+line {j}" for j in range(200)),
            "additions": 200,
            "changes": 200,
        })
    # 90 neutral utility files (risk 0)
    for i in range(90):
        files.append({
            "filename": f"src/utils/tool_{i}.py",
            "patch": "@@ -1 +1 @@\n+minor",
            "additions": 1,
            "changes": 1,
        })

    capped, summary = helper.triage_and_filter_files(files, max_cap=50)
    assert len(capped) == 50
    assert summary.total_files_in_pr == 100
    assert summary.reviewable_files_count == 100
    assert summary.excluded_files_count == 0
    assert summary.triaged_files_count == 50
    assert summary.skipped_files_count == 50
    assert summary.triage_applied is True

    # High-risk security files must all be retained
    retained_filenames = {f.filename for f in capped}
    for i in range(10):
        assert f"src/auth/service_{i}.py" in retained_filenames


# =====================================================================
# Tests: partition_files_into_batches (D-16)
# =====================================================================

def test_partition_files_into_batches_empty():
    """Empty list returns empty batch list."""
    assert helper.partition_files_into_batches([]) == []


def test_partition_files_into_batches_file_count():
    """Groups files respecting max_files_per_batch constraint."""
    files = [
        helper.FileDiffItem(filename=f"file_{i}.py", estimated_tokens=100)
        for i in range(60)
    ]

    batches = helper.partition_files_into_batches(files, max_files_per_batch=25, max_tokens_per_batch=60_000)
    assert len(batches) == 3
    assert batches[0].batch_index == 1
    assert batches[0].total_batches == 3
    assert len(batches[0].files) == 25
    assert batches[0].total_estimated_tokens == 2500

    assert batches[1].batch_index == 2
    assert batches[1].total_batches == 3
    assert len(batches[1].files) == 25
    assert batches[1].total_estimated_tokens == 2500

    assert batches[2].batch_index == 3
    assert batches[2].total_batches == 3
    assert len(batches[2].files) == 10
    assert batches[2].total_estimated_tokens == 1000


def test_partition_files_into_batches_token_budget():
    """Groups files respecting max_tokens_per_batch constraint."""
    files = [
        helper.FileDiffItem(filename="heavy_1.py", estimated_tokens=35_000),
        helper.FileDiffItem(filename="heavy_2.py", estimated_tokens=35_000),
        helper.FileDiffItem(filename="heavy_3.py", estimated_tokens=35_000),
    ]

    batches = helper.partition_files_into_batches(files, max_files_per_batch=25, max_tokens_per_batch=60_000)
    assert len(batches) == 3
    for idx, b in enumerate(batches, start=1):
        assert b.batch_index == idx
        assert b.total_batches == 3
        assert len(b.files) == 1
        assert b.total_estimated_tokens == 35_000


def test_partition_files_into_batches_oversized_solo_file():
    """Places single files that exceed max_tokens_per_batch in their own solo batch."""
    files = [
        helper.FileDiffItem(filename="file_1.py", estimated_tokens=10_000),
        helper.FileDiffItem(filename="huge_file.py", estimated_tokens=75_000),
        helper.FileDiffItem(filename="file_2.py", estimated_tokens=15_000),
    ]

    batches = helper.partition_files_into_batches(files, max_files_per_batch=25, max_tokens_per_batch=60_000)
    assert len(batches) == 3
    assert len(batches[0].files) == 1
    assert batches[0].files[0].filename == "file_1.py"

    assert len(batches[1].files) == 1
    assert batches[1].files[0].filename == "huge_file.py"
    assert batches[1].total_estimated_tokens == 75_000

    assert len(batches[2].files) == 1
    assert batches[2].files[0].filename == "file_2.py"


# =====================================================================
# Tests: resolve_env_config with Batch Configurations (D-15, D-16)
# =====================================================================

def test_resolve_env_config_batch_defaults(monkeypatch):
    """Verifies default batch thresholds when environment variables are unset."""
    for var in ["BATCH_MAX_FILES", "BATCH_MAX_TOKENS", "MAX_REVIEW_FILES_CAP"]:
        monkeypatch.delenv(var, raising=False)

    cfg = helper.resolve_env_config()
    assert cfg["batch_max_files"] == 25
    assert cfg["batch_max_tokens"] == 60_000
    assert cfg["max_review_files_cap"] == 200


def test_resolve_env_config_batch_env_vars(monkeypatch):
    """Verifies environment variable overrides for batch parameters."""
    monkeypatch.setenv("BATCH_MAX_FILES", "15")
    monkeypatch.setenv("BATCH_MAX_TOKENS", "45000")
    monkeypatch.setenv("MAX_REVIEW_FILES_CAP", "120")

    cfg = helper.resolve_env_config()
    assert cfg["batch_max_files"] == 15
    assert cfg["batch_max_tokens"] == 45_000
    assert cfg["max_review_files_cap"] == 120


def test_resolve_env_config_batch_cli_priority(monkeypatch):
    """Verifies CLI argument priority over environment variables for batch parameters."""
    monkeypatch.setenv("BATCH_MAX_FILES", "15")
    monkeypatch.setenv("BATCH_MAX_TOKENS", "45000")
    monkeypatch.setenv("MAX_REVIEW_FILES_CAP", "120")

    cfg = helper.resolve_env_config(
        batch_max_files=10,
        batch_max_tokens=30_000,
        max_review_files_cap=50,
    )
    assert cfg["batch_max_files"] == 10
    assert cfg["batch_max_tokens"] == 30_000
    assert cfg["max_review_files_cap"] == 50


