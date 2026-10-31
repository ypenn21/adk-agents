---
name: migrate-adk
description: >-
  Generic skill for converting ADK 1.x agents to ADK 2.x graph-orchestrated workflows, or converting existing ADK 2.x agents from basic orchestration (single tool-heavy LlmAgent, procedural prompts, or coordinator sub_agents) to deterministic ADK 2.x graph orchestration (Workflow, Edge, @node, JoinNode, and routed edges).
  Use when: user says "migrate to ADK 2", "convert to ADK 2 graph", "should I use ADK 2", "convert to workflow", "basic to graph orchestration", "ADK migration", "upgrade ADK", "ADK 1 to 2", "improve determinism with graphs", or points to an ADK 1.x or ADK 2.x agent asking to adopt graph orchestration.
---

# ADK 1.x / 2.x to ADK 2.x Graph Orchestration Converter

Analyze any Google ADK Python codebase, detect whether it uses **ADK 1.x** or **ADK 2.x Basic Orchestration**, score the determinism and efficiency benefits of **ADK 2.x Graph Orchestration (`Workflow`)**, produce an architectural migration report/plan, and generate production-ready ADK 2.x `Workflow` graph code.

---

## Dual Operating Modes

This skill operates in one of two modes depending on the target repository's current ADK version:

| Mode | Detected State | Goal |
| :--- | :--- | :--- |
| **Mode A: ADK 1.x $\rightarrow$ ADK 2.x + Graph Orchestration** | `google-adk < 2.0.0` in `pyproject.toml` / `requirements.txt` / `uv.lock`, or legacy 1.x constructs (`SequentialAgent`, `ParallelAgent`, `LoopAgent`, `AgentTool`). | Upgrade the codebase to ADK 2.x (`google-adk>=2.0.0`), handle breaking 2.0 `Event` / session storage changes, and convert 1.x agent patterns into a deterministic ADK 2.x `Workflow` graph. |
| **Mode B: ADK 2.x Basic Orchestration $\rightarrow$ ADK 2.x Graph Orchestration** | `google-adk >= 2.0.0` already installed/configured, but agents still use basic agent-driven orchestration (e.g., standalone `Agent`/`LlmAgent` with 3+ tools and a multi-step procedural prompt, or `LlmAgent(sub_agents=[...])` / `BaseLlmAgent(mode="task")` coordinator loops). | Refactor basic LLM-decided control flow into an explicit ADK 2.x `Workflow` graph (`Workflow`, `Edge`, `@node`, `JoinNode`, `Event(route=...)`) with Pydantic state contracts (`output_schema`) and deterministic Python function nodes. |

---

## Workflow

### Phase 0: ADK Version & Orchestration Mode Detection

1. **Inspect dependency manifests**:
   - Check `pyproject.toml`, `uv.lock`, `requirements.txt`, or `setup.py` for `google-adk`.
   - Determine whether the declared version is **ADK 1.x** (`<2.0.0`) or **ADK 2.x** (`>=2.0.0`).
2. **Inspect existing imports in the target agent directory**:
   - Check for `from google.adk.workflow import Workflow, Edge, JoinNode` or `@node`.
   - Select **Mode A** (`1.x -> 2.x + Graph`) or **Mode B** (`2.x Basic -> 2.x Graph`).

---

### Phase 1: Discovery & Procedural Prompt Analysis

Scan the target agent files using file reads and grep searches for:

1. **Agent definitions**:
   - `LlmAgent`, `Agent` (`from google.adk` or `from google.adk.agents.llm_agent`)
   - `BaseLlmAgent` with `mode="task"` or `mode="single_turn"` (ADK 2.x basic task delegation)
   - `SequentialAgent`, `ParallelAgent`, `LoopAgent` (ADK 1.x workflow wrappers)
   - `BaseAgent` subclasses (custom orchestrators)
   - `AgentTool` usage (ADK 1.x hierarchical delegation)
2. **Orchestration & Tool Metadata** (extract per agent):
   - Agent name, type, and model (preserve existing model or default to `gemini-3.8-flash` / `gemini-3.7-flash`; never use models below Gemini 3.5)
   - Full system prompt / `instruction` text
   - `input_schema`, `output_schema`, and `output_key` usage
   - Attached tools: classify each tool as **Deterministic** (e.g., SQL/MCP Toolbox queries, REST lookups, date/time utilities, formatting/validation functions) or **LLM/External Reasoning** (e.g., `google_search`, sub-agent tools)
   - Callbacks (`before_agent_callback`, `after_agent_callback`, `before_model_callback`, `after_model_callback`, `before_tool_callback`, `after_tool_callback`)
   - State reads (`{var}` in instructions, `ctx.state.get(...)`) and state writes (`output_key`, `ctx.state[...] = ...`, `Event(state={...})`)
3. **Procedural Prompt Decomposition (Critical for P1b / P1d / P9)**:
   - Inspect monolithic system prompts for hidden state machines or numbered multi-step instructions (e.g., *"Step 1: Clarify -> Step 2: Check Date/Memory -> Step 3: Route by Intent -> Step 4: Validate Enums / Check Duplicates -> Step 5: Call Database Tool -> Step 6: Format Markdown Table"*).
   - Identify every step in the prompt that can be extracted out of LLM guesswork and turned into:
     - **Entry Context Enrichment `@node`**: Deterministic pre-fetching (current date, user profile, session defaults) injected via `Event(state={...})` at `"START"`.
     - **Typed Intent Router (`LlmAgent` + `output_schema`) + Deterministic Route Dispatcher `@node`**: Classifying user intent into a strict Pydantic `Enum` and emitting `Event(route=...)` so downstream branches only expose relevant schemas/tools.
     - **Focused Parameter Extractor `LlmAgent` (`output_schema`)**: Extracting validated Pydantic payloads (enforcing enums, field constraints, and cross-field validators in code).
     - **Deterministic Pre-Check & Execution `@node`**: Enforcing pre-conditions (such as duplicate detection search before record creation) and invoking deterministic tools (MCP/SQL/API) directly in Python without extra LLM tool-call round-trips.
     - **Deterministic Post-Processing / Formatter `@node`**: Formatting structured records into standardized Markdown tables or payloads without an extra LLM synthesis call.

---

### Phase 2: Pattern Classification

Load [examples/adk1-patterns.md](./examples/adk1-patterns.md). Classify each discovered agent/pattern into one or more cataloged pattern types:

| Pattern ID | Source Pattern (ADK 1.x or ADK 2.x Basic) | Target ADK 2.x Graph Construct |
| :--- | :--- | :--- |
| **P1a** | Simple conversational `LlmAgent` (1–2 tools, no procedural steps) | Keep as standalone `LlmAgent` (or single node) |
| **P1b** | Tool-heavy `LlmAgent` (3+ deterministic tools) | `Workflow` chaining deterministic `@node` functions and focused `LlmAgent`s |
| **P1c** | Callback-heavy `LlmAgent` (`before_*` / `after_*` business logic) | `Workflow` with pre/post deterministic `@node` functions |
| **P1d** | Monolithic Procedural `LlmAgent` (multi-step prompt + multi-category tools) | Multi-branch routed `Workflow` (Context `@node` $\rightarrow$ Router `LlmAgent` $\rightarrow$ Branch Extractors $\rightarrow$ Deterministic Execution `@node`s $\rightarrow$ Formatter `@node`) |
| **P2** | `SequentialAgent` chain | `Workflow` with `Edge.chain("START", ...)` + intermediate `@node`s |
| **P3** | `ParallelAgent` concurrent execution | `Workflow` with tuple fan-out `(a, b, c)` + `JoinNode` fan-in |
| **P4** | `LoopAgent` with `exit_loop` / `max_iterations` | `Workflow` cycle with deterministic exit-check `@node` (`Event(route="continue"\|"done")`) |
| **P5** | Hierarchical delegation via `AgentTool` | Routed `Workflow` branch or ADK 2.x `BaseLlmAgent(mode="task"\|"single_turn")` node |
| **P6** | Custom `BaseAgent` subclass (`_run_async_impl`) | Declarative `Workflow` with routed edges, retries, and `@node` state transforms |
| **P7** | Callback-heavy pipeline | Explicit pre/post `@node` functions in `Workflow` |
| **P8** | Mixed / nested container agents | Flattened single `Workflow` graph combining fan-out, routing, and loops |
| **P9** | ADK 2.x Basic Orchestration (`LlmAgent` with `sub_agents` / `mode="task"` or basic tool loop) | Deterministic `Workflow` graph replacing LLM-decided coordinator hops with typed `output_schema` routers and `@node` edges |

---

### Phase 3: Migration & Determinism Scoring

Load [examples/scoring-rubric.md](./examples/scoring-rubric.md). Score each pattern instance (`STRONG (4)`, `MODERATE (3)`, `LOW (2)`, `NOT RECOMMENDED (1)`):

- **Show scoring math transparently**: List the base score, each signal applied (`+`/`-`), and the final label.
- Compute the **overall migration score**:
  - If ANY pattern scores `STRONG` $\rightarrow$ overall is `STRONG`
  - If majority score `MODERATE` $\rightarrow$ overall is `MODERATE`
  - Otherwise $\rightarrow$ overall matches the highest individual score

---

### Phase 3.5: Interactive Clarification & Design Alignment (`/grill-me`)

**Before finalizing the migration plan or writing any ADK 2.x graph code**, align with the user on key architectural decisions:

1. **Recommend `/grill-me`**: Suggest the `/grill-me` slash command to the user (e.g., *"You can use the `/grill-me` command to walk through an interactive interview and resolve the graph design decisions before starting the migration"*) and ask targeted clarifying questions based on the Phase 1–3 findings.
2. **Core Clarification Topics to Cover**:
   - **Rollout Strategy**: Should the ADK 2.x `Workflow` graph live side-by-side in `<agent_dir>_adk2/`, sit behind a feature flag in `ServiceManager` (e.g., `USE_ADK2_WORKFLOW=true|false`), or directly replace the existing agent in-place?
   - **Deterministic Pre-Condition & Validation Enforcement**: For rules currently buried in prompts (e.g., duplicate checks before record creation, strict enum normalization, required field checks), should failed checks block execution deterministically, auto-correct, or route to a clarification node?
   - **Branch & Fallback Behavior**: When an internal deterministic tool (e.g., database/MCP search) returns zero results, should the graph automatically route to an external fallback node (e.g., `google_search`) or return an empty-result message immediately?
   - **Human-in-the-Loop (HITL) Gates**: Should high-impact operations (e.g., `P0 - Critical` priority changes, record deletion/closure) pause at an ADK 2.x `RequestInput` confirmation gate before executing?
   - **Session Storage Compatibility (Mode A only)**: Does the application use a custom `BaseSessionService` with rigid SQL columns that needs migration for ADK 2.0 `Event` fields (`node_info`, `output`, `route`, `isolationScope`)?
3. **Wait for User Confirmation**: Do not proceed to Phase 4/5 code changes until the user answers the clarifying questions or confirms the defaults.

---

### Phase 4: Report / Design Plan Generation

Load [resources/migration-report-template.md](./resources/migration-report-template.md). Produce the assessment and implementation blueprint (either as `MIGRATION_REPORT.md` or `plans/<feature-name>-design.md` depending on project conventions). Include:

1. **Executive Summary & Detected Mode** (`Mode A: ADK 1.x -> 2.x + Graph` vs `Mode B: ADK 2.x Basic -> Graph`).
2. **Current Architecture Diagram & Non-Determinism Root Causes**.
3. **Per-Agent Analysis & Transparent Score Breakdown**.
4. **What Stays the Same** (models, database/MCP toolsets, session services, external entrypoints).
5. **Quantified Determinism & Efficiency Benefits** (token savings, round-trip latency reductions, hard schema/pre-condition enforcement, before/after snippets).
6. **What ADK 2.x Graph Orchestration Unlocks Next** (e.g., HITL `RequestInput` gates, `JoinNode` parallel fan-out, deterministic retry loops).
7. **Migration Risks & Mitigations** (e.g., ADK 2.0 `Event` schema changes for custom `BaseSessionService`, `output_schema` JSON serializability, lazy tool loading for pickling).
8. **Proposed ADK 2.x `Workflow` Graph Architecture** (Mermaid and/or text diagram showing `@node` functions, `LlmAgent` nodes, `output_schema` contracts, and `Event(route=...)` edges).
9. **Step-by-Step Implementation & Validation Plan** (including concrete test prompts and trajectory verification).

---

### Phase 5: Code Generation (When Score is STRONG or MODERATE and Implementation is Requested)

Load [examples/adk2-mapping.md](./examples/adk2-mapping.md) and [resources/adk2-scaffolds.md](./resources/adk2-scaffolds.md).

1. **Structure Selection**:
   - **Single-File Scaffold (`<original_dir>_adk2/agent.py`)**: Best for self-contained agents; keeps the original code untouched for side-by-side comparison.
   - **Modular Graph Package (`schemas.py`, `nodes.py`, `sub_agents.py`, `workflow_graph.py`)**: Best for complex P1d/P8/P9 agents with multiple routed branches and database/MCP tools. Wire into the existing `ServiceManager` or entrypoint with an optional feature flag (`USE_ADK2_WORKFLOW=true|false`) so backwards compatibility is preserved.
2. **Strict Preservation Rules**:
   - Preserve all business logic, domain validations, session/memory services, and lazy tool wrappers.
   - Default new or upgraded model references to `gemini-3.8-flash` (or `gemini-3.7-flash`); never downgrade to models below Gemini 3.5.
   - Ensure all `LlmAgent` nodes that feed into routing functions or `JoinNode`s use Pydantic `output_schema` with JSON-serializable primitives.

---

## Key Principles

- **Deterministic by Default**: Any step that does not require semantic LLM reasoning (date/context injection, enum normalization, pre-write duplicate checks, parameterized SQL/API calls, Markdown table formatting) belongs in a deterministic Python `@node` function, not an LLM tool-call loop.
- **Narrow LLM Scope**: Decompose overloaded 10+ tool agents into focused `LlmAgent` nodes that either classify/extract structured Pydantic schemas (`output_schema`) or invoke a single specialized tool (`google_search`).
- **Zero Regression**: Keep external interfaces (`Runner.run_async`, `ServiceManager`, A2A executors, web views) intact so callers interact with the new `Workflow` graph identically to the original agent.
