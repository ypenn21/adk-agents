---
name: migrate-adk
description: |
  Analyze ADK 1.x agent codebases and determine if they would benefit from migration to ADK 2.0 (graph-based Workflow). Produces a migration assessment report with per-agent scoring, and auto-generates ADK 2.0 code when migration is strongly recommended.
  Use when: user says "migrate to ADK 2", "should I use ADK 2", "convert to workflow", "ADK migration", "upgrade ADK", "ADK 1 to 2", "evaluate ADK 2", or points to an ADK 1.x codebase asking about ADK 2.0 migration.
---

# ADK 1.x to 2.0 Migration Advisor

Analyze an ADK 1.x agent codebase, score migration benefit per agent/pattern, produce a migration report, and auto-generate ADK 2.0 Workflow code when migration is recommended.

## Workflow

### Phase 1: Discovery

Ask the user to provide the agent codebase path (directory or specific files). Then scan using Glob/Grep for:

1. **Agent definitions** — search for these imports and class usages:
   - `LlmAgent`, `Agent` (from `google.adk`)
   - `SequentialAgent`, `ParallelAgent`, `LoopAgent`
   - `BaseAgent` subclasses (custom agents)
   - `AgentTool` usage (hierarchical delegation)

2. **Orchestration patterns** — for each agent found, extract:
   - Agent name, type, model assigned
   - Instruction/prompt text (full)
   - `output_key` / `output_schema` usage
   - Tools attached (list names and whether they are deterministic or LLM-dependent)
   - Callbacks: `before_agent_callback`, `after_agent_callback`, `before_model_callback`, `after_model_callback`
   - Sub-agents (for workflow agents)
   - State reads (`{var}` in instructions) and state writes (`output_key`, `ctx.state`)

3. **Pipeline mapping** — build a text diagram of agent relationships:
   - Parent-child for SequentialAgent/ParallelAgent/LoopAgent
   - Tool-delegation for AgentTool
   - State data flow (which agent writes what key, which agent reads it)

### Phase 2: Pattern Classification

Load `examples/adk1-patterns.md`. Classify each discovered agent/pattern into one of the cataloged pattern types:

| Pattern ID | ADK 1.x Pattern                           |
| ---------- | ----------------------------------------- |
| P1         | Single LlmAgent with tools                |
| P2         | SequentialAgent chain                     |
| P3         | ParallelAgent concurrent execution        |
| P4         | LoopAgent with exit condition             |
| P5         | Hierarchical via AgentTool                |
| P6         | Custom BaseAgent subclass                 |
| P7         | Callback-heavy agent (before/after logic) |
| P8         | Mixed/nested patterns                     |

For each classified pattern, note:

- Which specific agents are involved
- File paths and line numbers
- Code evidence (the actual constructor call or class definition)

### Phase 3: Migration Scoring

Load `examples/scoring-rubric.md`. Score each pattern instance:

| Score           | Meaning                                                               |
| --------------- | --------------------------------------------------------------------- |
| STRONG          | Clear, measurable benefit from ADK 2.0. Migrate.                      |
| MODERATE        | Benefits exist but ADK 1.x works. Migration optional but recommended. |
| LOW             | Minimal benefit. Keep ADK 1.x unless consolidating.                   |
| NOT RECOMMENDED | ADK 1.x is the better fit. Do not migrate.                            |

**Show scoring math transparently.** For each agent/pattern, list the base score, each signal applied (+/-), and the final rounded label. This builds trust and lets the developer challenge specific signals.

Compute an **overall migration score** for the codebase:

- If ANY pattern scores STRONG → overall is STRONG
- If majority score MODERATE → overall is MODERATE
- Otherwise → overall matches the highest individual score

### Phase 4: Report Generation

Load `resources/migration-report-template.md`. Populate the template with all findings. The report must include:

1. **Executive Summary** — Agent count, pattern breakdown, overall migration score, one-line recommendation
2. **Architecture Overview** — Text diagram of the current ADK 1.x pipeline
3. **Per-Agent Analysis** — Table with agent name, type, pattern ID, migration score, rationale. Include a **Score Breakdown** subsection showing the math per agent (base score + signals = final label)
4. **What Stays the Same** — List what is preserved unchanged: instructions, models, state keys, business logic, agent names. This reassures developers that migration is incremental, not a rewrite
5. **Migration Benefits** — What ADK 2.0 specifically enables for this codebase. For each benefit, include:
   - **Estimated savings** — Quantify token/latency savings where possible (e.g., "~500 tokens saved per removed tool-call round-trip")
   - **Before/after code snippet** — Show the most impactful change inline (5-15 lines each) so the report is self-contained
6. **What ADK 2.0 Unlocks Next** — 2-4 specific capabilities this codebase could leverage post-migration that were hard/impossible with ADK 1.x (e.g., conditional routing, HITL gates, parallel fan-out)
7. **Migration Risks** — What could break or require extra work
8. **Recommended ADK 2.0 Architecture** — Text diagram of the proposed ADK 2.0 pipeline
9. **Implementation Plan** — Ordered steps with effort estimates. Phase 3 (Validation) must include **2-3 specific test prompts** with what to verify for each, not just "run with same inputs"

Save the report as `MIGRATION_REPORT.md` in the user's working directory.

### Phase 5: Code Generation (conditional)

**Only execute this phase if the overall score is STRONG or MODERATE.**

Load `examples/adk2-mapping.md` and `resources/adk2-scaffolds.md`. For each agent/pattern:

1. Look up the ADK 2.0 equivalent in the mapping reference
2. Select the appropriate scaffold template
3. Generate the ADK 2.0 `agent.py` preserving:
   - All business logic from tools and callbacks
   - State keys and data flow
   - Model assignments
   - Agent names (for traceability)

**Output structure:**

- Create a new directory `<original_dir>_adk2/` alongside the original
- Write `agent.py` with the ADK 2.0 Workflow implementation
- Add inline comments marking where each ADK 1.x construct was migrated

**Do NOT modify the original ADK 1.x code.**

If the overall score is LOW or NOT RECOMMENDED, skip code generation and explain in the report why ADK 1.x is the better fit.

## Key Principles

- **Conservative scoring**: Default to LOW. Only score STRONG when there's a clear structural advantage (deterministic logic as function nodes, explicit routing, parallel fan-out/fan-in).
- **Preserve behavior**: Generated ADK 2.0 code must produce functionally equivalent results. Never drop tools, callbacks, or state logic during migration.
- **Explain the why**: Every score must include a rationale referencing specific ADK 2.0 features that justify (or don't justify) migration.
- **Handle complexity honestly**: Custom BaseAgent subclasses and deeply nested patterns may require manual migration. Flag these clearly rather than generating incomplete code.
