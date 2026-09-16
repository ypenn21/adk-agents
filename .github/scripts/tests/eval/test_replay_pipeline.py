"""Tier 2 Recorded Cassette Replay Engine and Offline Replay Tests.

Simulates the Antigravity Agent event loop, streaming chunk iteration
(Thought, ToolCall, ToolResult, Text), budget exhaustion halt handling,
and Pydantic structured output deserialization with 0 cloud network calls.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional, Union
from unittest.mock import patch

import pytest

# Ensure .github/scripts is on sys.path
_scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from google.antigravity import types
import pr_reviewer_agent
from pr_reviewer_agent import (
    BatchReviewResult,
    FileDiffItem,
    PRFindingSeverity,
    PRReviewReport,
    PRTriageSummary,
    ReviewBatch,
    ReviewStatus,
    review_batch_with_isolated_context,
    synthesize_final_review_report,
)
import quality_gate_agent
from quality_gate_agent import (
    QualityGateDecision,
    SeverityLevel,
    ViolationCategory,
    evaluate_quality_gate,
)
from helper import calculate_token_spend, stream_agent_response

CASSETTES_DIR = Path(__file__).parent / "cassettes"


class CassetteChunkStream:
    """Simulates an asynchronous iterable of SDK response chunks."""

    def __init__(self, chunks_data: list[dict[str, Any]]):
        self.chunks_data = chunks_data

    def __aiter__(self):
        self._iter = iter(self.chunks_data)
        self._index = 0
        return self

    async def __anext__(self):
        try:
            chunk = next(self._iter)
        except StopIteration:
            raise StopAsyncIteration

        c_type = chunk.get("type", "")
        self._index += 1

        if c_type == "Thought":
            if hasattr(types, "Thought"):
                return types.Thought(step_index=self._index, text=chunk.get("content", ""))
            return chunk.get("content", "")
        elif c_type == "ToolCall":
            if hasattr(types, "ToolCall"):
                return types.ToolCall(name=chunk.get("name", ""), args=chunk.get("args", {}))
            return chunk
        elif c_type == "ToolResult":
            if hasattr(types, "ToolResult"):
                return types.ToolResult(name=chunk.get("name", ""), result=chunk.get("result", {}))
            return chunk
        elif c_type == "Text":
            if hasattr(types, "Text"):
                return types.Text(step_index=self._index, text=chunk.get("content", ""))
            return chunk.get("content", "")
        return chunk


class CassetteResponse:
    """Mock agent response loaded from a recorded JSON cassette."""

    def __init__(
        self,
        cassette: dict[str, Any],
        budget_halt: bool = False,
        structured_output_spy: Optional[Any] = None,
    ):
        self.cassette = cassette
        self.budget_halt = budget_halt
        self._structured_output_spy = structured_output_spy
        self.usage_metadata = cassette.get("usage_metadata", {})

        if budget_halt:
            if hasattr(types, "StopReason"):
                self.stop_reason = getattr(
                    types.StopReason,
                    "MAX_TOTAL_TOKENS_EXCEEDED",
                    "MAX_TOTAL_TOKENS_EXCEEDED",
                )
            else:
                self.stop_reason = "MAX_TOTAL_TOKENS_EXCEEDED"
        else:
            sr = cassette.get("stop_reason", "STOP")
            if hasattr(types, "StopReason"):
                self.stop_reason = getattr(
                    types.StopReason,
                    sr,
                    getattr(types.StopReason, "END_OF_TURN", sr),
                )
            else:
                self.stop_reason = sr

    @property
    def chunks(self):
        return CassetteChunkStream(self.cassette.get("chunks", []))

    async def structured_output(self) -> Any:
        if self._structured_output_spy is not None:
            self._structured_output_spy()
        return self.cassette.get("raw_structured_output", {})


class CassetteReplayAgent:
    """Simulates the Antigravity Agent context manager, replaying recorded cassette frames."""

    def __init__(
        self,
        cassette_source: Union[str, Path, dict[str, Any]],
        budget_halt: bool = False,
    ):
        if isinstance(cassette_source, (str, Path)):
            with open(cassette_source, "r", encoding="utf-8") as f:
                self.cassette = json.load(f)
        else:
            self.cassette = cassette_source
        self.budget_halt = budget_halt
        self.chat_called = False
        self.structured_output_called = False

    def _structured_output_called_tracker(self):
        self.structured_output_called = True

    def __call__(self, *args, **kwargs):
        """Allows CassetteReplayAgent to act as the Agent class factory Agent(config)."""
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def chat(self, prompt: str) -> CassetteResponse:
        self.chat_called = True
        return CassetteResponse(
            self.cassette,
            budget_halt=self.budget_halt,
            structured_output_spy=self._structured_output_called_tracker,
        )


# =====================================================================
# Tests: Cassette Format & Replay Verification
# =====================================================================


def test_cassette_files_valid_structure():
    """Validates that all recorded cassette files adhere to the cassette schema."""
    cassette_names = [
        "pr_reviewer_clean.json",
        "pr_reviewer_secret_leak.json",
        "quality_gate_pass.json",
        "quality_gate_fail.json",
    ]

    for name in cassette_names:
        path = CASSETTES_DIR / name
        assert path.exists(), f"Missing required cassette file: {path}"

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "case_id" in data
        assert "model" in data
        assert "usage_metadata" in data
        assert "stop_reason" in data
        assert "chunks" in data
        assert "raw_structured_output" in data

        usage = data["usage_metadata"]
        assert usage.get("prompt_token_count", 0) > 0
        assert usage.get("total_token_count", 0) > 0

        chunks = data["chunks"]
        assert isinstance(chunks, list)
        assert len(chunks) > 0
        for chunk in chunks:
            assert "type" in chunk
            assert chunk["type"] in ("Thought", "ToolCall", "ToolResult", "Text")


@pytest.mark.asyncio
async def test_cassette_chunk_streaming_helper():
    """Verifies that chunk streaming through stream_agent_response extracts all chunks correctly."""
    clean_cassette_path = CASSETTES_DIR / "pr_reviewer_clean.json"
    replayer = CassetteReplayAgent(clean_cassette_path)

    async with replayer as agent:
        response = await agent.chat("Review prompt")
        thoughts, tool_calls, tool_results, text_chunks = await stream_agent_response(
            response, header_title="TEST REPLAY STREAM"
        )

    assert len(thoughts) == 1
    assert "Django view" in thoughts[0]
    assert len(tool_calls) == 1
    assert "list_pull_request_files" in tool_calls[0]
    assert len(tool_results) == 1
    assert len(text_chunks) == 1
    assert "Clean implementation" in text_chunks[0]


@pytest.mark.asyncio
async def test_pr_reviewer_replay_clean_code(tmp_path):
    """Replays clean code cassette through PR reviewer agent and verifies APPROVE outcome."""
    cassette_path = CASSETTES_DIR / "pr_reviewer_clean.json"
    replayer = CassetteReplayAgent(cassette_path)

    batch = ReviewBatch(
        batch_index=1,
        total_batches=1,
        files=[
            FileDiffItem(
                filename="adk_bug_ticket_agent/views.py",
                status="modified",
                additions=15,
                deletions=2,
                changes=17,
                patch="@@ -1,5 +1,10 @@",
                risk_score=1.0,
                estimated_tokens=50,
            )
        ],
        total_estimated_tokens=50,
    )

    cfg = {
        "project_id": "test-project",
        "location": "us-central1",
        "model": "gemini-3.7-flash",
        "pr_number": "101",
        "repo": "octocat/hello-world",
        "token": "mock-token",
        "max_total_tokens": 150000,
        "max_input_tokens": 100000,
        "max_output_tokens": 8000,
        "max_model_calls": 5,
        "max_tool_calls": 10,
    }

    with patch.object(pr_reviewer_agent, "Agent", replayer):
        result, usage_stats, stop_reason, stop_reason_str = await review_batch_with_isolated_context(
            batch=batch,
            cfg=cfg,
            pii_context_subset="",
            telemetry_dir=str(tmp_path),
        )

    assert isinstance(result, BatchReviewResult)
    assert result.batch_index == 1
    assert len(result.findings) == 0
    assert "Clean implementation" in result.batch_summary

    # Verify token spend calculation from cassette metadata
    assert usage_stats["prompt_tokens"] == 1200
    assert usage_stats["candidate_tokens"] == 180
    assert usage_stats["total_tokens"] == 1444
    assert usage_stats["total_cost_usd"] > 0.0

    # Verify report synthesis
    triage = PRTriageSummary(
        total_files_in_pr=1,
        reviewable_files_count=1,
        excluded_files_count=0,
        triaged_files_count=1,
        skipped_files_count=0,
        batches_executed=1,
        triage_applied=False,
    )
    report = synthesize_final_review_report([result], triage)
    assert isinstance(report, PRReviewReport)
    assert report.overall_status == ReviewStatus.APPROVE
    assert len(report.findings) == 0


@pytest.mark.asyncio
async def test_pr_reviewer_replay_secret_leak(tmp_path):
    """Replays secret leak cassette through PR reviewer agent and verifies REQUEST_CHANGES with BLOCKER."""
    cassette_path = CASSETTES_DIR / "pr_reviewer_secret_leak.json"
    replayer = CassetteReplayAgent(cassette_path)

    batch = ReviewBatch(
        batch_index=1,
        total_batches=1,
        files=[
            FileDiffItem(
                filename="settings.py",
                status="modified",
                additions=1,
                deletions=0,
                changes=1,
                patch="@@ -40,3 +40,4 @@\n+AWS_SECRET_ACCESS_KEY = 'AKIAIOSFODNN7EXAMPLE'",
                risk_score=2.0,
                estimated_tokens=20,
            )
        ],
        total_estimated_tokens=20,
    )

    cfg = {
        "project_id": "test-project",
        "location": "us-central1",
        "model": "gemini-3.7-flash",
        "pr_number": "101",
        "repo": "octocat/hello-world",
        "token": "mock-token",
        "max_total_tokens": 150000,
        "max_input_tokens": 100000,
        "max_output_tokens": 8000,
        "max_model_calls": 5,
        "max_tool_calls": 10,
    }

    with patch.object(pr_reviewer_agent, "Agent", replayer):
        result, usage_stats, stop_reason, stop_reason_str = await review_batch_with_isolated_context(
            batch=batch,
            cfg=cfg,
            pii_context_subset="Potential AWS key found",
            telemetry_dir=str(tmp_path),
        )

    assert isinstance(result, BatchReviewResult)
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.file_path == "settings.py"
    assert finding.severity == PRFindingSeverity.BLOCKER
    assert finding.pii_leak is True
    assert "Secret Key" in finding.title

    # Verify report synthesis enforces REQUEST_CHANGES on BLOCKER findings (Decision D-4)
    triage = PRTriageSummary(
        total_files_in_pr=1,
        reviewable_files_count=1,
        excluded_files_count=0,
        triaged_files_count=1,
        skipped_files_count=0,
        batches_executed=1,
        triage_applied=False,
    )
    report = synthesize_final_review_report([result], triage)
    assert isinstance(report, PRReviewReport)
    assert report.overall_status == ReviewStatus.REQUEST_CHANGES


@pytest.mark.asyncio
async def test_budget_limit_early_halt_no_structured_output(tmp_path):
    """Verifies that when StopReason signals budget exhaustion, execution halts without calling structured_output()."""
    cassette_path = CASSETTES_DIR / "pr_reviewer_clean.json"
    replayer = CassetteReplayAgent(cassette_path, budget_halt=True)

    batch = ReviewBatch(
        batch_index=1,
        total_batches=1,
        files=[
            FileDiffItem(
                filename="main.py",
                status="modified",
                additions=5,
                deletions=0,
                changes=5,
                patch="@@ -1,1 +1,5 @@",
                risk_score=1.0,
                estimated_tokens=10,
            )
        ],
        total_estimated_tokens=10,
    )

    cfg = {
        "project_id": "test-project",
        "location": "us-central1",
        "model": "gemini-3.7-flash",
        "pr_number": "101",
        "repo": "octocat/hello-world",
        "token": "mock-token",
        "max_total_tokens": 150000,
        "max_input_tokens": 100000,
        "max_output_tokens": 8000,
        "max_model_calls": 5,
        "max_tool_calls": 10,
    }

    with patch.object(pr_reviewer_agent, "Agent", replayer):
        result, usage_stats, stop_reason, stop_reason_str = await review_batch_with_isolated_context(
            batch=batch,
            cfg=cfg,
            pii_context_subset="",
            telemetry_dir=str(tmp_path),
        )

    # Must NOT call structured_output when budget limit is reached
    assert replayer.structured_output_called is False
    assert "budget limit exceeded" in result.batch_summary
    assert len(result.findings) == 0


@pytest.mark.asyncio
async def test_quality_gate_replay_pass(tmp_path):
    """Replays quality gate pass cassette and validates QualityGateDecision passed=True."""
    cassette_path = CASSETTES_DIR / "quality_gate_pass.json"
    replayer = CassetteReplayAgent(cassette_path)

    pii_file = tmp_path / "pii-scan.txt"
    pii_file.write_text("✅ No sensitive data or PII detected by Cloud DLP.", encoding="utf-8")

    pr_file = tmp_path / "pr-review.txt"
    pr_file.write_text("Overall Status: APPROVE\nSummary: All clean.", encoding="utf-8")

    with patch.object(quality_gate_agent, "Agent", replayer):
        decision = await evaluate_quality_gate(
            pii_report_path=str(pii_file),
            pr_review_path=str(pr_file),
            project_id="test-project",
            location="us-central1",
            model="gemini-3.7-flash",
            pr_number="101",
        )

    assert isinstance(decision, QualityGateDecision)
    assert decision.passed is True
    assert len(decision.failures) == 0
    assert "passed cleanly" in decision.summary


@pytest.mark.asyncio
async def test_quality_gate_replay_fail(tmp_path):
    """Replays quality gate fail cassette and validates QualityGateDecision passed=False with failures."""
    cassette_path = CASSETTES_DIR / "quality_gate_fail.json"
    replayer = CassetteReplayAgent(cassette_path)

    pii_file = tmp_path / "pii-scan.txt"
    pii_file.write_text("✅ No sensitive data or PII detected by Cloud DLP.", encoding="utf-8")

    pr_file = tmp_path / "pr-review.txt"
    pr_file.write_text("Overall Status: REQUEST_CHANGES\n[BLOCKER] Secret leak in settings.py", encoding="utf-8")

    with patch.object(quality_gate_agent, "Agent", replayer):
        decision = await evaluate_quality_gate(
            pii_report_path=str(pii_file),
            pr_review_path=str(pr_file),
            project_id="test-project",
            location="us-central1",
            model="gemini-3.7-flash",
            pr_number="101",
        )

    assert isinstance(decision, QualityGateDecision)
    assert decision.passed is False
    assert len(decision.failures) == 1
    failure = decision.failures[0]
    assert failure.category == ViolationCategory.PII_LEAK
    assert failure.severity == SeverityLevel.CRITICAL
    assert "settings.py" in failure.reason


def test_offline_token_spend_calculation_zero_network():
    """Verifies that token spend calculation operates purely offline and correctly applies pricing models."""
    cassette_path = CASSETTES_DIR / "pr_reviewer_secret_leak.json"
    with open(cassette_path, "r", encoding="utf-8") as f:
        cassette = json.load(f)

    usage = cassette["usage_metadata"]
    stats = calculate_token_spend(usage, model_name="gemini-3.7-flash")

    assert stats["prompt_tokens"] == 1420
    assert stats["candidate_tokens"] == 315
    assert stats["thought_tokens"] == 128
    assert stats["total_tokens"] == 1863

    # Expected: (1420 * 0.75 / 1e6) + ((315 + 128) * 3.75 / 1e6)
    expected_cost = (1420 * 0.75 / 1_000_000.0) + ((315 + 128) * 3.75 / 1_000_000.0)
    assert abs(stats["total_cost_usd"] - expected_cost) < 1e-6
