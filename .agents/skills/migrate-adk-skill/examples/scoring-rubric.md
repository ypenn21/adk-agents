# Migration Benefit Scoring Rubric

## Score Definitions

| Score | Label | Meaning | Action |
|-------|-------|---------|--------|
| 4 | STRONG | Clear structural advantage from ADK 2.0. Measurable latency/token savings or significant maintainability improvement. | Auto-generate ADK 2.0 code. |
| 3 | MODERATE | Benefits exist. ADK 1.x works but ADK 2.0 is cleaner/more maintainable. | Auto-generate ADK 2.0 code. Recommend but don't push. |
| 2 | LOW | Minimal benefit. Migration adds complexity without clear payoff. | Report only. No code generation. |
| 1 | NOT RECOMMENDED | ADK 1.x is the better fit for this pattern. | Report only. Explain why ADK 1.x is preferred. |

## Per-Pattern Scoring

### P1: Single LlmAgent with Tools

| Sub-pattern | Default Score | Upgrade Condition | Downgrade Condition |
|------------|--------------|-------------------|-------------------|
| P1a: Simple chat | 1 (NOT REC) | Never — this is ADK 1.x's sweet spot | — |
| P1b: Tool-heavy | 3 (MODERATE) | 3+ deterministic tools → 4 (STRONG) | All tools need LLM reasoning → 2 (LOW) |
| P1c: Callback-heavy | 4 (STRONG) | 2+ callbacks with business logic → 4 | Callbacks are just logging → 2 (LOW) |

**Scoring signals for P1**:
- Count deterministic tools (no LLM call inside): each adds +0.5 to score
- Count callbacks with state manipulation: each adds +0.5
- If `before_agent_callback` returns Content (short-circuit): +1.0
- If only tool is `google_search` or similar built-in: -1.0

### P2: SequentialAgent Chain

| Sub-pattern | Default Score | Upgrade Condition | Downgrade Condition |
|------------|--------------|-------------------|-------------------|
| P2a: Pure LLM chain | 2 (LOW) | Has pre/post processing in callbacks → 3 | 2-agent chain, no callbacks → 1 |
| P2b: Mixed chain | 3 (MODERATE) | Deterministic steps between LLM agents → 4 | — |
| P2c: Nested | 4 (STRONG) | Contains Parallel or Loop sub-agents → 4 | — |

**Scoring signals for P2**:
- Number of agents in chain: 4+ agents → +1.0
- Any agent has callbacks: +0.5 per callback-heavy agent
- Any agent has deterministic-only tools: +0.5 per agent
- State flow complexity (3+ `output_key` variables): +0.5

### P3: ParallelAgent

| Sub-pattern | Default Score | Upgrade Condition | Downgrade Condition |
|------------|--------------|-------------------|-------------------|
| P3a: Independent parallel | 2 (LOW) | Custom merge logic in downstream agent → 3 | — |
| P3b: Fan-out/fan-in | 3 (MODERATE) | Complex merge/join logic → 4 | Simple state concat → 2 |

**Scoring signals for P3**:
- Downstream agent merges 3+ parallel outputs: +0.5
- Custom merge logic (not just reading state vars): +1.0
- Nested inside SequentialAgent with pre/post: +0.5

### P4: LoopAgent

| Sub-pattern | Default Score | Upgrade Condition | Downgrade Condition |
|------------|--------------|-------------------|-------------------|
| P4a: Single agent loop | 3 (MODERATE) | Exit condition could be deterministic → 4 | — |
| P4b: Multi-agent loop | 4 (STRONG) | Always strong — graph makes complexity visible | — |
| P4c: Conditional exit | 4 (STRONG) | Always strong — routing edges are explicit | — |

**Scoring signals for P4**:
- Uses `exit_loop` tool (LLM-decided exit): +1.0 (deterministic check is better)
- `max_iterations` set very high (>10): +0.5 (needs explicit exit routing)
- Loop body has callbacks: +0.5

### P5: Hierarchical AgentTool

| Sub-pattern | Default Score | Upgrade Condition | Downgrade Condition |
|------------|--------------|-------------------|-------------------|
| P5a: Single delegation | 2 (LOW) | Child is autonomous (no user interaction needed) → 3 | — |
| P5b: Multi-delegation | 3 (MODERATE) | 3+ AgentTool children (routing) → 4 | — |
| P5c: Deep hierarchy | 4 (STRONG) | Always strong — task mode provides typed contracts | — |

**Scoring signals for P5**:
- Number of AgentTool children: 3+ → +1.0
- Child agents have `output_schema`: +0.5 (already structured, easy migration)
- Nesting depth 3+: +1.0

### P6: Custom BaseAgent

| Default Score | Upgrade Condition | Downgrade Condition |
|--------------|-------------------|-------------------|
| 3 (MODERATE) | Logic maps to routing/parallel/loop → 4 | Complex async patterns, InvocationContext manipulation → 2 |

**Scoring signals for P6**:
- Contains conditional delegation (if/else on sub-agent): +1.0 (→ routing edges)
- Contains retry logic: +0.5 (→ routed edge loop)
- Directly accesses `InvocationContext` internals: -1.0 (hard to migrate)
- Complex `yield` patterns with event filtering: -1.0

### P7: Callback-Heavy Agent

| Default Score | Upgrade Condition | Downgrade Condition |
|--------------|-------------------|-------------------|
| 3 (MODERATE) | 2+ callbacks with state/logic → 4 | All callbacks are logging only → 1 |

**Scoring signals for P7**:
- `before_model_callback` modifies `LlmRequest`: +1.0
- `after_model_callback` transforms response: +1.0
- `before_agent_callback` returns Content (short-circuit): +1.0
- Callbacks only do `print()`/`logger.info()`: -2.0

### P8: Mixed/Nested

| Default Score | Upgrade Condition | Downgrade Condition |
|--------------|-------------------|-------------------|
| 4 (STRONG) | Almost always strong — graph unifies complexity | Only 2 simple patterns combined → 3 |

**Scoring signals for P8**:
- Number of distinct patterns combined: 3+ → always STRONG
- Total agent count across all nesting levels: 5+ → +1.0
- Contains both Parallel and Loop: +1.0

## Overall Codebase Score

Calculate the overall score from individual pattern scores:

1. If ANY pattern scores 4 (STRONG) → overall is **STRONG**
2. If majority (>50%) score 3+ → overall is **MODERATE**
3. If all score 2 (LOW) → overall is **LOW**
4. If all score 1 (NOT REC) → overall is **NOT RECOMMENDED**

## Score Modifiers (apply to overall)

| Modifier | Condition | Effect |
|----------|-----------|--------|
| Codebase complexity | 5+ agents total | +0.5 (graph visibility helps) |
| State complexity | 5+ state keys flowing between agents | +0.5 (explicit data flow helps) |
| Testing needs | User mentions testing/debugging pain | +0.5 (function nodes are unit-testable) |
| Production stability | User says "don't break what works" | -0.5 (migration risk) |
| Team familiarity | Team new to ADK 2.0 | -0.5 (learning curve) |
