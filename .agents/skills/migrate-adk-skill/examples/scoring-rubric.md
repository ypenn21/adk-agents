# Migration & Graph Conversion Scoring Rubric

## Score Definitions

| Score | Label | Meaning | Action |
|-------|-------|---------|--------|
| 4 | STRONG | Clear structural advantage from ADK 2.x `Workflow` graph. Measurable latency/token savings, hard determinism guarantees, or major maintainability improvement. | Generate ADK 2.x `Workflow` graph plan & code. |
| 3 | MODERATE | Benefits exist. Basic orchestration works, but an ADK 2.x `Workflow` graph is cleaner, more testable, and more deterministic. | Generate ADK 2.x `Workflow` graph plan & code. |
| 2 | LOW | Minimal benefit. Graph orchestration adds structure without a major determinism or token payoff. | Report only (unless user explicitly requests graph conversion). |
| 1 | NOT RECOMMENDED | Standalone `LlmAgent` is the better fit (e.g., pure open-ended chat with no deterministic steps). | Report only and explain why standalone `LlmAgent` is preferred. |

---

## Per-Pattern Scoring

### P1: Single `LlmAgent` with Tools (ADK 1.x or ADK 2.x Basic)

| Sub-pattern | Default Score | Upgrade Condition | Downgrade Condition |
|------------|--------------|-------------------|-------------------|
| P1a: Simple chat | 1 (NOT REC) | Never — standalone `LlmAgent` is ideal here | — |
| P1b: Tool-heavy | 3 (MODERATE) | 3+ deterministic tools $\rightarrow$ 4 (STRONG) | All tools require open-ended LLM reasoning $\rightarrow$ 2 (LOW) |
| P1c: Callback-heavy | 4 (STRONG) | 2+ callbacks with business logic $\rightarrow$ 4 | Callbacks are logging only $\rightarrow$ 2 (LOW) |
| P1d: Monolithic Procedural Prompt | 4 (STRONG) | Multi-step numbered prompt + 4+ tools across distinct intents $\rightarrow$ 4 (STRONG) | — |

**Scoring signals for P1**:
- Each deterministic tool (SQL/MCP query, REST call, date/time utility, formatter): `+0.5`
- Procedural prompt containing 3+ numbered/ordered workflow steps: `+1.0`
- Pre-condition rule in prompt (e.g., *"Always search for duplicates before creating"* or *"Always call get_current_date first"*): `+1.0`
- Strict enum/field validation rules in prompt (e.g., priority/status enums): `+0.5`
- Each callback with state manipulation: `+0.5`
- Only tool is `google_search` or a single built-in tool: `-1.0`

### P2: `SequentialAgent` Chain (ADK 1.x)

| Sub-pattern | Default Score | Upgrade Condition | Downgrade Condition |
|------------|--------------|-------------------|-------------------|
| P2a: Pure LLM chain | 2 (LOW) | Has pre/post processing in callbacks $\rightarrow$ 3 | 2-agent chain, no callbacks $\rightarrow$ 1 |
| P2b: Mixed chain | 3 (MODERATE) | Deterministic steps between LLM agents $\rightarrow$ 4 | — |
| P2c: Nested | 4 (STRONG) | Contains Parallel or Loop sub-agents $\rightarrow$ 4 | — |

### P3: `ParallelAgent` (ADK 1.x)

| Sub-pattern | Default Score | Upgrade Condition | Downgrade Condition |
|------------|--------------|-------------------|-------------------|
| P3a: Independent parallel | 2 (LOW) | Custom merge logic in downstream agent $\rightarrow$ 3 | — |
| P3b: Fan-out/fan-in | 3 (MODERATE) | Complex merge/join logic $\rightarrow$ 4 | Simple state concat $\rightarrow$ 2 |

### P4: `LoopAgent` (ADK 1.x)

| Sub-pattern | Default Score | Upgrade Condition | Downgrade Condition |
|------------|--------------|-------------------|-------------------|
| P4a: Single agent loop | 3 (MODERATE) | Exit condition can be deterministic $\rightarrow$ 4 | — |
| P4b: Multi-agent loop | 4 (STRONG) | Always strong — graph makes cycle visible | — |
| P4c: Conditional exit | 4 (STRONG) | Always strong — routing edges are explicit | — |

### P5: Hierarchical `AgentTool` (ADK 1.x)

| Sub-pattern | Default Score | Upgrade Condition | Downgrade Condition |
|------------|--------------|-------------------|-------------------|
| P5a: Single delegation | 2 (LOW) | Child is autonomous single-turn specialist or fallback branch $\rightarrow$ 3 | — |
| P5b: Multi-delegation | 3 (MODERATE) | 3+ `AgentTool` children (routing) $\rightarrow$ 4 | — |
| P5c: Deep hierarchy | 4 (STRONG) | Always strong — graph routing + typed schemas | — |

### P6: Custom `BaseAgent`

| Default Score | Upgrade Condition | Downgrade Condition |
|--------------|-------------------|-------------------|
| 3 (MODERATE) | Logic maps to routing/parallel/loop $\rightarrow$ 4 | Complex custom event streaming manipulation $\rightarrow$ 2 |

### P7: Callback-Heavy Agent

| Default Score | Upgrade Condition | Downgrade Condition |
|--------------|-------------------|-------------------|
| 3 (MODERATE) | 2+ callbacks with state/logic $\rightarrow$ 4 | All callbacks are logging only $\rightarrow$ 1 |

### P8: Mixed / Nested

| Default Score | Upgrade Condition | Downgrade Condition |
|--------------|-------------------|-------------------|
| 4 (STRONG) | Almost always strong — `Workflow` graph unifies complexity | Only 2 simple patterns combined $\rightarrow$ 3 |

### P9: ADK 2.x Basic Orchestration $\rightarrow$ ADK 2.x Graph Orchestration

| Sub-pattern | Default Score | Upgrade Condition | Downgrade Condition |
|------------|--------------|-------------------|-------------------|
| P9a: Coordinator `LlmAgent(sub_agents=[...])` | 3 (MODERATE) | Routing can be classified via `output_schema` + pre/post deterministic steps exist $\rightarrow$ 4 (STRONG) | Requires multi-turn conversational back-and-forth between coordinator and sub-agent $\rightarrow$ 2 (LOW) |
| P9b: ADK 2.x Single `LlmAgent` with deterministic tools / procedural prompt | 4 (STRONG) | 3+ deterministic tools or multi-step procedural prompt $\rightarrow$ 4 (STRONG) | 1–2 non-deterministic tools $\rightarrow$ 1 (NOT REC) |

---

## Overall Codebase Score

1. If ANY pattern scores `4 (STRONG)` $\rightarrow$ overall is **STRONG**
2. If majority (`>50%`) score `3+` $\rightarrow$ overall is **MODERATE**
3. If all score `2 (LOW)` $\rightarrow$ overall is **LOW**
4. If all score `1 (NOT REC)` $\rightarrow$ overall is **NOT RECOMMENDED**

## Score Modifiers (apply to overall)

| Modifier | Condition | Effect |
|----------|-----------|--------|
| Determinism requirement | User explicitly requests improved determinism / predictability | `+0.5` |
| Codebase complexity | 5+ agents or 8+ tools total | `+0.5` |
| State complexity | 5+ state keys flowing between steps | `+0.5` |
| Testing needs | Need unit-testable function nodes independent of LLM calls | `+0.5` |
| Production stability | User requests zero breaking changes to callers | Keep `ServiceManager` / `Runner` interface compatible |
