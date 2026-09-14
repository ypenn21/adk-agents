# Implementation Plan: Token Tracking and Spend Capping for PR Reviewer Agent

## Overview
Automated Pull Request code review agents powered by large language models (such as Gemini 3.7 Flash or Gemini 3.8 Flash) can encounter unbounded token consumption when analyzing large diffs, executing multi-turn tool loops via Model Context Protocol (MCP), or generating extensive chain-of-thought thinking tokens. Without token observability and budget ceilings, runaway executions risk exhausting API quotas and incurring high infrastructure costs in CI/CD pipelines.

This plan establishes a mechanism within [`.github/scripts/pr_reviewer_agent.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/pr_reviewer_agent.py) and [`.github/scripts/helper.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/helper.py) to:
1. Accurately track input, candidate output, thinking/reasoning, and total tokens across the agent session.
2. Calculate estimated monetary cost (USD) based on model pricing.
3. Enforce proactive token and spend caps via `types.BudgetConfig`.
4. Halt the agent harness automatically when token or call limits are reached, reporting the exact `StopReason` to CI logs and GitHub Actions step summaries.

---

## Research & Web Citations
* > **Ref-1:** [Google Antigravity SDK: Session Budget Limits & Stop Reasons](file:///Users/yannipeng/.gemini/config/plugins/google-antigravity-sdk/skills/google-antigravity-sdk/examples/getting_started/budget_limits.md) — Demonstrates configuring `types.BudgetConfig` (`max_total_tokens`, `max_input_tokens`, `max_output_tokens`, `max_model_calls`, `max_tool_calls`) on `LocalAgentConfig` and handling `response.stop_reason` (such as `MAX_TOTAL_TOKENS_EXCEEDED`).
* > **Ref-2:** [Google Antigravity SDK: Observability & Token Usage](file:///Users/yannipeng/.gemini/config/plugins/google-antigravity-sdk/skills/google-antigravity-sdk/references/observability.md) — Documents `agent.conversation.total_usage` returning `UsageMetadata` (`prompt_token_count`, `cached_content_token_count`, `candidates_token_count`, `thoughts_token_count`, `total_token_count`).
* > **Ref-3:** [Google Antigravity SDK: Turn Cancellation](file:///Users/yannipeng/.gemini/config/plugins/google-antigravity-sdk/skills/google-antigravity-sdk/examples/getting_started/cancellation.md) — Outlines programmatic aborts using `await response.cancel()` and handling `AntigravityCancelledError`.
* > **Ref-4:** [Google Gemini Pricing Specification](https://ai.google.dev/pricing) — Gemini 3.x Flash pricing: $0.75 / 1M prompt tokens, $3.75 / 1M candidate and thinking tokens, with 50% discount on batch/cached processing.
* > **Ref-5:** [Google Cloud Vertex AI Interactions API Reference](https://cloud.google.com/vertex-ai) — Details server-side budget limits (`max_total_tokens`), returning `status: "incomplete"` when the ceiling is triggered.

---

## Existing Codebase Analysis

### 1. Target Files & Integration Points
* **[`.github/scripts/pr_reviewer_agent.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/pr_reviewer_agent.py):**
  - Instantiates `LocalAgentConfig` at lines 193–202 without a `budget_config`.
  - Executes `response = await agent.chat(prompt)` at line 206.
  - Currently parses structured output without checking `response.stop_reason` or reading `agent.conversation.total_usage`.
  - On uncaught exceptions, falls back to deterministic rule-based review generation (lines 245–289).
* **[`.github/scripts/helper.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/helper.py):**
  - Contains `resolve_env_config()` which parses CLI args and environment variables. Currently does not resolve token budget variables (`MAX_TOTAL_TOKENS`, `MAX_SPEND_USD`, `MAX_MODEL_CALLS`, `MAX_TOOL_CALLS`).
  - Contains report writers (`write_pr_reports()`). Can be augmented to persist token usage telemetry in `reports/token-usage.json` and in PR review summary tables.
* **[`.github/workflows/source-code-pii-review.yml`](file:///Users/yannipeng/git-projects/adk-agents/.github/workflows/source-code-pii-review.yml):**
  - Invokes `python .github/scripts/pr_reviewer_agent.py` in line 137.
  - Can supply optional workflow environment variables for spend caps (e.g., `MAX_TOTAL_TOKENS: 100000`, `MAX_SPEND_USD: 0.10`).

### 2. Architectural Design & Constraints
* The code runs as an automated GitHub Actions step using Vertex AI ADC or API keys.
* The agent uses `gemini-3.7-flash` (or `gemini-3.8-flash`), which incorporates extended reasoning (thoughts tokens). Thinking tokens can equal or exceed prompt token count, making `thoughts_token_count` tracking mandatory.
* Any harness halt must exit gracefully: write telemetry reports, log explicit warnings indicating why the agent halted, and avoid corrupting the downstream Quality Gate decision.

---

## 📋 Checklist
- [ ] Step 1: Update `resolve_env_config` in `helper.py` to parse token budget and spend cap settings from environment variables (`MAX_TOTAL_TOKENS`, `MAX_INPUT_TOKENS`, `MAX_OUTPUT_TOKENS`, `MAX_MODEL_CALLS`, `MAX_TOOL_CALLS`, `MAX_SPEND_USD`).
- [ ] Step 2: Implement token calculation and cost estimation utility `calculate_token_spend(usage, model)` in `helper.py`.
- [ ] Step 3: Implement `write_token_usage_report(usage, cost_info, stop_reason)` in `helper.py` to persist telemetry to `reports/token-usage.json`.
- [ ] Step 4: Configure `budget_config=types.BudgetConfig(...)` in `pr_reviewer_agent.py` within `LocalAgentConfig`.
- [ ] Step 5: Add post-generation inspection in `pr_reviewer_agent.py` for `response.stop_reason` (`MAX_TOTAL_TOKENS_EXCEEDED`, `MAX_INPUT_TOKENS_EXCEEDED`, `MAX_OUTPUT_TOKENS_EXCEEDED`, `MAX_MODEL_CALLS_EXCEEDED`, `MAX_TOOL_CALLS_EXCEEDED`).
- [ ] Step 6: On budget halt, log diagnostic metrics, record the budget exhaustion event in the PR report, and stop further agent operations safely.
- [ ] Step 7: Add unit and contract tests in [`.github/scripts/tests/test_pr_reviewer_agent.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/tests/test_pr_reviewer_agent.py) covering budget enforcement, stop reason triggers, and cost calculation.

---

## Proposed Changes

### 1. File: [`.github/scripts/helper.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/helper.py)

#### Change Description:
Add budget environment variable resolution to `resolve_env_config()`. Add cost calculation and token telemetry persistence functions.

#### Sample Code:
```python
# Rate card per 1,000,000 tokens (Gemini Flash defaults)
MODEL_PRICING = {
    "gemini-3.7-flash": {"input_per_m": 0.75, "output_per_m": 3.75, "cached_per_m": 0.075},
    "gemini-3.8-flash": {"input_per_m": 0.75, "output_per_m": 3.75, "cached_per_m": 0.075},
    "gemini-2.5-flash": {"input_per_m": 0.30, "output_per_m": 2.50, "cached_per_m": 0.03},
    "default": {"input_per_m": 0.75, "output_per_m": 3.75, "cached_per_m": 0.075},
}


def calculate_token_spend(usage: Any, model_name: str = "gemini-3.7-flash") -> dict[str, Any]:
    """Calculates approximate spend in USD from SDK UsageMetadata."""
    rates = MODEL_PRICING.get(model_name, MODEL_PRICING["default"])
    prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
    cached_tokens = getattr(usage, "cached_content_token_count", 0) or 0
    candidate_tokens = getattr(usage, "candidates_token_count", 0) or 0
    thought_tokens = getattr(usage, "thoughts_token_count", 0) or 0
    total_tokens = getattr(usage, "total_token_count", 0) or (prompt_tokens + candidate_tokens + thought_tokens)

    # Net uncached input tokens
    net_input = max(0, prompt_tokens - cached_tokens)
    cost_input = (net_input / 1_000_000) * rates["input_per_m"]
    cost_cached = (cached_tokens / 1_000_000) * rates["cached_per_m"]
    cost_output = ((candidate_tokens + thought_tokens) / 1_000_000) * rates["output_per_m"]
    total_cost_usd = cost_input + cost_cached + cost_output

    return {
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "candidate_tokens": candidate_tokens,
        "thought_tokens": thought_tokens,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost_usd, 6),
    }


def write_token_usage_report(
    usage_data: dict[str, Any],
    stop_reason: Optional[str] = None,
    output_path: str = "reports/token-usage.json",
) -> None:
    """Persists token usage and cost metrics to reports directory."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **usage_data,
        "stop_reason": stop_reason or "COMPLETED",
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
```

---

### 2. File: [`.github/scripts/pr_reviewer_agent.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/pr_reviewer_agent.py)

#### Change Description:
1. Configure `types.BudgetConfig` in `LocalAgentConfig` using values resolved from environment variables (`MAX_TOTAL_TOKENS`, `MAX_INPUT_TOKENS`, `MAX_OUTPUT_TOKENS`, `MAX_MODEL_CALLS`, `MAX_TOOL_CALLS`).
2. If `MAX_SPEND_USD` is set, convert it to a conservative total token budget ceiling if `MAX_TOTAL_TOKENS` is not explicitly set.
3. Inspect `response.stop_reason` following generation. If a budget limit halted the harness, log the event, generate a graceful budget-halt report, record the telemetry, and stop further operations.
4. Extract `agent.conversation.total_usage`, format the token summary table in the logs, and persist `reports/token-usage.json`.

#### Sample Code:
```python
        # 1. Resolve budget limits from configuration / environment
        max_total_tokens = int(cfg.get("max_total_tokens") or os.environ.get("MAX_TOTAL_TOKENS", 120_000))
        max_input_tokens = int(cfg.get("max_input_tokens") or os.environ.get("MAX_INPUT_TOKENS", 100_000))
        max_output_tokens = int(cfg.get("max_output_tokens") or os.environ.get("MAX_OUTPUT_TOKENS", 25_000))
        max_model_calls = int(cfg.get("max_model_calls") or os.environ.get("MAX_MODEL_CALLS", 10))
        max_tool_calls = int(cfg.get("max_tool_calls") or os.environ.get("MAX_TOOL_CALLS", 25))

        # Support optional dollar spend cap conversion (e.g. MAX_SPEND_USD=0.25)
        max_spend_usd = os.environ.get("MAX_SPEND_USD")
        if max_spend_usd:
            # Conservative bound: assumed $3.75 / 1M tokens upper rate
            spend_derived_tokens = int((float(max_spend_usd) / 3.75) * 1_000_000)
            max_total_tokens = min(max_total_tokens, spend_derived_tokens)

        budget_config = types.BudgetConfig(
            max_total_tokens=max_total_tokens,
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
            max_model_calls=max_model_calls,
            max_tool_calls=max_tool_calls,
        )

        config = LocalAgentConfig(
            vertex=True,
            project=cfg["project_id"],
            location=cfg["location"],
            model=cfg["model"],
            budget_config=budget_config,
            response_schema=PRReviewReport,
            mcp_servers=[mcp_server] if mcp_server else [],
            app_data_dir=telemetry_dir,
            system_instructions=SYSTEM_INSTRUCTIONS,
        )

        async with Agent(config) as agent:
            response = await agent.chat(prompt)

            # Check if harness was halted due to budget ceiling
            stop_reason = getattr(response, "stop_reason", None)
            budget_halted = stop_reason in (
                types.StopReason.MAX_TOTAL_TOKENS_EXCEEDED,
                types.StopReason.MAX_INPUT_TOKENS_EXCEEDED,
                types.StopReason.MAX_OUTPUT_TOKENS_EXCEEDED,
                types.StopReason.MAX_MODEL_CALLS_EXCEEDED,
                types.StopReason.MAX_TOOL_CALLS_EXCEEDED,
            )

            # Record token telemetry
            usage = getattr(agent.conversation, "total_usage", None)
            usage_stats = calculate_token_spend(usage, cfg["model"] or "gemini-3.7-flash")
            write_token_usage_report(usage_stats, stop_reason=str(stop_reason))

            print("\n📊 TOKEN USAGE & ESTIMATED SPEND:")
            print(f"  • Prompt Tokens:     {usage_stats['prompt_tokens']:,}")
            print(f"  • Cached Tokens:     {usage_stats['cached_tokens']:,}")
            print(f"  • Candidate Tokens:  {usage_stats['candidate_tokens']:,}")
            print(f"  • Thought Tokens:    {usage_stats['thought_tokens']:,}")
            print(f"  • Total Tokens:      {usage_stats['total_tokens']:,} (Cap: {max_total_tokens:,})")
            print(f"  • Estimated Cost:    ${usage_stats['total_cost_usd']:.6f} USD")

            if budget_halted:
                print(f"\n🛑 [BUDGET CAP TRIGGERED] Agent harness halted early. StopReason: {stop_reason}")
                report = PRReviewReport(
                    overall_status=ReviewStatus.COMMENT,
                    summary=(
                        f"⚠️ PR review halted early: Model execution exceeded token/budget limit "
                        f"({stop_reason}). Processed {usage_stats['total_tokens']:,} tokens "
                        f"(${usage_stats['total_cost_usd']:.4f} USD)."
                    ),
                    findings=[],
                )
                write_pr_reports(report)
                return report

            # Normal path: parse structured output
            raw_output = await response.structured_output()
            report = parse_agent_structured_output(raw_output, PRReviewReport)
            ...
```

---

## Trade-offs & Considerations

1. **Proactive `BudgetConfig` vs. Reactive Turn Cancellation:**
   - *Proactive `BudgetConfig` (Recommended):* The SDK enforces checks directly in the invocation engine before token counts run wild. Stops both infinite tool calls and token explosions at the root.
   - *Reactive `response.cancel()` (Supplemental):* Useful if a timeout or stream chunk monitoring threshold is breached, but requires external concurrency monitors.
2. **Hard Capping vs. Partial Reviews:**
   - When the token cap is hit, the structured JSON payload might be truncated or empty. Setting `overall_status=ReviewStatus.COMMENT` prevents false APPROVEs or false BLOCKERs while notifying the pull request author.
3. **Thinking Tokens Impact:**
   - Reasoning models (Gemini 3.7 / 3.8 Flash) emit thinking tokens that count toward output budget. Setting `max_output_tokens` too low (e.g. < 4,000) could cause premature halts before code review findings are composed. A recommended default is `max_output_tokens=25_000` and `max_total_tokens=120_000`.

---

## Next Steps
1. Review the plan and approve token budget thresholds and cost rates.
2. Delegate implementation to the Software Engineer subagent according to the Multi-Agent Development Workflow.
3. Run test verification and validate against `.github/scripts/tests/test_pr_reviewer_agent.py`.
