"""Unit and contract tests for prompt_loader and versioned prompt template management (Decision D-19)."""

import os
import sys
import json
import pytest
from pathlib import Path

# Add .github/scripts to PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prompt_loader import (
    PromptLoader,
    PromptMetadata,
    PromptBundle,
    load_prompt_bundle,
    BUILTIN_PROMPTS,
)
from helper import (
    resolve_env_config,
    write_gate_reports,
    write_token_usage_report,
)
import pr_reviewer_agent
import quality_gate_agent


def test_load_pr_reviewer_bundle_from_file():
    """Verify loading v1.0.0 PR reviewer prompt bundle from disk."""
    bundle = load_prompt_bundle("pr_reviewer", version="1.0.0")
    assert bundle is not None
    assert bundle.metadata.name == "pr_reviewer"
    assert bundle.metadata.version == "1.0.0"
    assert bundle.metadata.is_fallback is False
    assert len(bundle.metadata.sha256) == 64
    assert int(bundle.metadata.sha256, 16) > 0  # Valid hex
    assert "REST API Design" in bundle.system_instructions
    assert "SOLID" in bundle.system_instructions
    assert "${pr_number}" in bundle.user_prompt_template


def test_load_quality_gate_bundle_from_file():
    """Verify loading v1.0.0 Quality Gate prompt bundle from disk."""
    bundle = load_prompt_bundle("quality_gate", version="1.0.0")
    assert bundle is not None
    assert bundle.metadata.name == "quality_gate"
    assert bundle.metadata.version == "1.0.0"
    assert bundle.metadata.is_fallback is False
    assert len(bundle.metadata.sha256) == 64
    assert "Lead Release Engineer" in bundle.system_instructions
    assert "${pii_content}" in bundle.user_prompt_template


def test_render_user_prompt_variable_substitution():
    """Verify variable substitution using ${var} and preservation of literal {id}."""
    bundle = load_prompt_bundle("pr_reviewer", version="1.0.0")
    rendered = bundle.render_user_prompt(
        pr_number="42",
        repo="octocat/Hello-World",
        pii_context="No sensitive findings.",
    )
    assert "Pull Request #42" in rendered
    assert "octocat/Hello-World" in rendered
    assert "No sensitive findings." in rendered


def test_render_user_prompt_preserves_literal_curly_braces():
    """Verify literal curly braces like /api/v1/accounts/{id} are not stripped or mangled."""
    bundle = PromptBundle(
        metadata=PromptMetadata(
            name="test_agent",
            version="1.0.0",
            sha256="abc",
            required_variables=["resource_id"],
        ),
        system_instructions="Check endpoint /accounts/{id}",
        user_template="Target resource: ${resource_id} with path /items/{item_id}",
    )
    rendered = bundle.render_user_prompt(resource_id="123")
    assert "Target resource: 123 with path /items/{item_id}" == rendered


def test_render_user_prompt_missing_required_variable_raises():
    """Verify ValueError is raised when a required variable is missing or None."""
    bundle = load_prompt_bundle("pr_reviewer", version="1.0.0")
    with pytest.raises(ValueError, match="Missing required prompt variable: 'repo'"):
        bundle.render_user_prompt(pr_number="100", repo="", pii_context="clean")

    with pytest.raises(ValueError, match="Missing required prompt variable: 'pr_number'"):
        bundle.render_user_prompt(repo="owner/repo", pii_context="clean")


def test_fallback_on_nonexistent_version():
    """Verify graceful fallback to built-in prompt when non-existent version is requested."""
    bundle = load_prompt_bundle("pr_reviewer", version="99.99.99")
    assert bundle.metadata.is_fallback is True
    assert bundle.metadata.version.startswith("1.0.0")
    assert len(bundle.system_instructions) > 100
    assert "${pr_number}" in bundle.user_prompt_template


def test_fallback_on_nonexistent_file_path():
    """Verify graceful fallback when invalid explicit prompt_path is given."""
    bundle = load_prompt_bundle("quality_gate", prompt_path="/invalid/nonexistent/prompt.md")
    assert bundle.metadata.is_fallback is True
    assert bundle.metadata.version.startswith("1.0.0")
    assert "Lead Release Engineer" in bundle.system_instructions


def test_fallback_on_corrupted_file(tmp_path):
    """Verify graceful fallback when prompt markdown file is corrupted."""
    corrupted_file = tmp_path / "corrupted.md"
    corrupted_file.write_text("No frontmatter here at all", encoding="utf-8")

    bundle = load_prompt_bundle("pr_reviewer", prompt_path=str(corrupted_file))
    assert bundle.metadata.is_fallback is True
    assert "REST API" in bundle.system_instructions


def test_sha256_checksum_reproducibility():
    """Verify SHA256 checksum calculation is deterministic and reproducible."""
    loader = PromptLoader()
    bundle1 = loader.load("pr_reviewer", version="1.0.0")
    bundle2 = loader.load("pr_reviewer", version="1.0.0")
    assert bundle1.metadata.sha256 == bundle2.metadata.sha256
    assert len(bundle1.metadata.sha256) == 64


def test_semver_resolution_variants():
    """Verify semver resolution handles 1.0.0, v1.0.0, and latest."""
    loader = PromptLoader()
    b1 = loader.load("pr_reviewer", version="1.0.0")
    b2 = loader.load("pr_reviewer", version="v1.0.0")
    b3 = loader.load("pr_reviewer", version="latest")
    assert b1.metadata.sha256 == b2.metadata.sha256
    assert b1.metadata.sha256 == b3.metadata.sha256
    assert b1.metadata.is_fallback is False


def test_audit_dict_format():
    """Verify PromptBundle.to_audit_dict returns expected structure."""
    bundle = load_prompt_bundle("pr_reviewer", version="1.0.0")
    audit = bundle.to_audit_dict()
    assert audit["version"] == "1.0.0"
    assert audit["sha256"] == bundle.metadata.sha256
    assert audit["is_fallback"] is False
    assert "loaded_at" in audit


def test_backward_compatibility_module_constants():
    """Verify SYSTEM_INSTRUCTIONS and QUALITY_GATE_SYSTEM_INSTRUCTIONS module constants exist."""
    assert hasattr(pr_reviewer_agent, "SYSTEM_INSTRUCTIONS")
    assert isinstance(pr_reviewer_agent.SYSTEM_INSTRUCTIONS, str)
    assert len(pr_reviewer_agent.SYSTEM_INSTRUCTIONS) > 0
    assert "REST API Design" in pr_reviewer_agent.SYSTEM_INSTRUCTIONS

    assert hasattr(quality_gate_agent, "QUALITY_GATE_SYSTEM_INSTRUCTIONS")
    assert isinstance(quality_gate_agent.QUALITY_GATE_SYSTEM_INSTRUCTIONS, str)
    assert len(quality_gate_agent.QUALITY_GATE_SYSTEM_INSTRUCTIONS) > 0
    assert "Lead Release Engineer" in quality_gate_agent.QUALITY_GATE_SYSTEM_INSTRUCTIONS


def test_backward_compatibility_prompt_builders():
    """Verify build_pr_review_prompt and build_quality_gate_prompt work with original positional args."""
    pr_prompt = pr_reviewer_agent.build_pr_review_prompt(
        pr_number="99",
        repo="my-org/my-repo",
        pii_context="No PII detected.",
    )
    assert "Pull Request #99" in pr_prompt
    assert "my-org/my-repo" in pr_prompt

    qg_prompt = quality_gate_agent.build_quality_gate_prompt(
        pii_content="0 findings",
        pr_review_content="STATUS: APPROVE",
    )
    assert "=== CLOUD DLP SCAN REPORT ===" in qg_prompt
    assert "=== PR CODE REVIEW REPORT ===" in qg_prompt


def test_resolve_env_config_extracts_prompt_template_parameters(monkeypatch):
    """Verify resolve_env_config extracts prompt versions and paths from env or kwargs."""
    monkeypatch.setenv("PR_REVIEW_PROMPT_VERSION", "2.1.0")
    monkeypatch.setenv("QUALITY_GATE_PROMPT_VERSION", "3.0.0")
    cfg = resolve_env_config()
    assert cfg["pr_review_prompt_version"] == "2.1.0"
    assert cfg["quality_gate_prompt_version"] == "3.0.0"

    cfg_override = resolve_env_config(
        pr_review_prompt_version="1.0.0",
        quality_gate_prompt_version="1.0.0",
    )
    assert cfg_override["pr_review_prompt_version"] == "1.0.0"
    assert cfg_override["quality_gate_prompt_version"] == "1.0.0"


def test_write_gate_reports_persists_prompt_metadata(tmp_path, monkeypatch):
    """Verify write_gate_reports persists prompt-metadata.json in telemetry directory."""
    monkeypatch.chdir(tmp_path)
    decision = quality_gate_agent.QualityGateDecision(
        passed=True,
        summary="Clean build",
        failures=[],
    )
    mock_audit = {
        "version": "1.0.0",
        "sha256": "abcdef123456",
        "is_fallback": False,
        "loaded_at": "2026-09-15T12:00:00Z",
    }
    write_gate_reports(decision, prompt_metadata=mock_audit)

    meta_file = Path("reports/telemetry/quality_gate_agent/prompt-metadata.json")
    assert meta_file.exists()
    saved_meta = json.loads(meta_file.read_text(encoding="utf-8"))
    assert saved_meta["version"] == "1.0.0"
    assert saved_meta["sha256"] == "abcdef123456"
    assert saved_meta["is_fallback"] is False


def test_write_token_usage_report_includes_prompt_metadata(tmp_path, monkeypatch):
    """Verify write_token_usage_report embeds prompt_template in token-usage.json."""
    monkeypatch.chdir(tmp_path)
    usage = {
        "prompt_tokens": 100,
        "cached_tokens": 10,
        "candidate_tokens": 50,
        "thought_tokens": 0,
        "total_tokens": 150,
        "total_cost_usd": 0.0002,
    }
    mock_audit = {
        "version": "1.0.0",
        "sha256": "feedface0987",
        "is_fallback": False,
        "loaded_at": "2026-09-15T12:00:00Z",
    }
    write_token_usage_report(
        usage_data=usage,
        stop_reason="COMPLETED",
        output_path="reports/token-usage.json",
        prompt_metadata=mock_audit,
    )

    report_file = Path("reports/token-usage.json")
    assert report_file.exists()
    report_data = json.loads(report_file.read_text(encoding="utf-8"))
    assert report_data["prompt_template"] == mock_audit


def test_load_batch_pr_reviewer_bundle_from_file():
    """Verify batch_pr_reviewer v1.0.0 loads from markdown file with valid frontmatter."""
    bundle = load_prompt_bundle("batch_pr_reviewer", version="1.0.0")
    assert bundle.metadata.name == "batch_pr_reviewer"
    assert bundle.metadata.version == "1.0.0"
    assert bundle.metadata.is_fallback is False
    assert len(bundle.metadata.sha256) == 64
    assert len(bundle.metadata.required_variables) == 8
    expected_vars = [
        "pr_number",
        "repo",
        "batch_index",
        "total_batches",
        "files_count",
        "total_estimated_tokens",
        "pii_context_subset",
        "diffs_text",
    ]
    assert bundle.metadata.required_variables == expected_vars
    assert "### REVIEW GUIDELINES & CHECKLIST:" in bundle.system_instructions


def test_render_batch_pr_reviewer_user_prompt():
    """Verify render_user_prompt substitutes all 8 variables and preserves literal braces."""
    bundle = load_prompt_bundle("batch_pr_reviewer", version="1.0.0")
    rendered = bundle.render_user_prompt(
        pr_number="123",
        repo="test-owner/test-repo",
        batch_index=1,
        total_batches=3,
        files_count=4,
        total_estimated_tokens=5000,
        pii_context_subset="No DLP findings detected.",
        diffs_text="diff --git a/main.py b/main.py\n+def handler(): return {'status': 200}",
    )
    assert "Pull Request #123" in rendered
    assert "repository test-owner/test-repo" in rendered
    assert "Review Batch 1 of 3" in rendered
    assert "(4 files, ~5000 tokens)" in rendered
    assert "No DLP findings detected." in rendered
    assert "def handler(): return {'status': 200}" in rendered
    # Ensure literal curly braces are preserved without corruption
    assert "{'status': 200}" in rendered
    # Ensure no unresolved template variables remain
    assert "${" not in rendered


def test_render_batch_pr_reviewer_missing_variable_raises():
    """Verify render_user_prompt raises ValueError if required variable is missing."""
    bundle = load_prompt_bundle("batch_pr_reviewer", version="1.0.0")
    with pytest.raises(ValueError, match="Missing required prompt variable: 'diffs_text'"):
        bundle.render_user_prompt(
            pr_number="123",
            repo="test-owner/test-repo",
            batch_index=1,
            total_batches=3,
            files_count=4,
            total_estimated_tokens=5000,
            pii_context_subset="No DLP findings detected.",
            # diffs_text omitted
        )


def test_fallback_batch_pr_reviewer_builtin():
    """Verify fallback to built-in bundle when requested file does not exist."""
    bundle = load_prompt_bundle("batch_pr_reviewer", version="99.99.99")
    assert bundle.metadata.name == "batch_pr_reviewer"
    assert bundle.metadata.version == "1.0.0-builtin"
    assert bundle.metadata.is_fallback is True
    assert len(bundle.metadata.required_variables) == 8
    assert "batch_index" in bundle.metadata.required_variables
    assert "### REVIEW GUIDELINES & CHECKLIST:" in bundle.system_instructions


def test_batch_system_instructions_module_constant():
    """Verify BATCH_SYSTEM_INSTRUCTIONS module constant exists in pr_reviewer_agent."""
    assert hasattr(pr_reviewer_agent, "BATCH_SYSTEM_INSTRUCTIONS")
    assert isinstance(pr_reviewer_agent.BATCH_SYSTEM_INSTRUCTIONS, str)
    assert len(pr_reviewer_agent.BATCH_SYSTEM_INSTRUCTIONS) > 0
    assert "REST API Design" in pr_reviewer_agent.BATCH_SYSTEM_INSTRUCTIONS
    assert "BatchReviewResult" in pr_reviewer_agent.BATCH_SYSTEM_INSTRUCTIONS


def test_resolve_env_config_batch_prompt_parameters(monkeypatch):
    """Verify resolve_env_config extracts batch prompt version and path."""
    monkeypatch.setenv("BATCH_PR_REVIEW_PROMPT_VERSION", "2.0.0")
    monkeypatch.setenv("BATCH_PR_REVIEW_PROMPT_PATH", "/custom/path/batch.md")
    cfg = resolve_env_config()
    assert cfg["batch_pr_review_prompt_version"] == "2.0.0"
    assert cfg["batch_pr_review_prompt_path"] == "/custom/path/batch.md"

    cfg_direct = resolve_env_config(
        batch_pr_review_prompt_version="1.0.0",
        batch_pr_review_prompt_path="/other/batch.md",
    )
    assert cfg_direct["batch_pr_review_prompt_version"] == "1.0.0"
    assert cfg_direct["batch_pr_review_prompt_path"] == "/other/batch.md"

