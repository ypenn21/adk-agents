# ADK 1.x & ADK 2.x Basic Orchestration Pattern Detection Guide

9 cataloged patterns (covering both **ADK 1.x** agents and **ADK 2.x Basic Orchestration** agents) with detection rules, code signatures, and decomposition strategies.

---

## Phase 0 Check: Detecting ADK 1.x vs. ADK 2.x Basic Orchestration

Before classifying patterns, inspect the project's dependency manifests and imports:

```bash
# 1. Check declared google-adk version
grep -rn "google-adk" pyproject.toml requirements*.txt uv.lock 2>/dev/null

# 2. Check if ADK 2.x Workflow graphs are already used
grep -rn "from google.adk.workflow" --include="*.py"
```

- **Mode A (ADK 1.x $\rightarrow$ ADK 2.x + Graph)**: `google-adk` is `< 2.0.0` or uses `SequentialAgent`, `ParallelAgent`, `LoopAgent`, or `AgentTool`.
- **Mode B (ADK 2.x Basic $\rightarrow$ ADK 2.x Graph)**: `google-adk` is `>= 2.0.0`, `Workflow` is not yet used (or only partially used), and orchestration relies on standalone `Agent`/`LlmAgent` tool loops (`P1b`/`P1d`) or coordinator `LlmAgent(sub_agents=[...])` / `BaseLlmAgent(mode="task")` (`P9`).

---

## P1: Single `LlmAgent` / `Agent` with Tools

**Detection**: `LlmAgent(` or `Agent(` with `tools=[...]`, no parent `Workflow`/`SequentialAgent`/`ParallelAgent`.

**Code signature**:
```python
from google.adk.agents import Agent  # or from google.adk.agents.llm_agent import LlmAgent

root_agent = Agent(
    name="...",
    model="gemini-3.8-flash",
    instruction="...",
    tools=[...],
)
```

**Sub-variants**:
- **P1a: Simple chat** (1–2 LLM-appropriate tools, short conversational instruction) — keep as standalone `LlmAgent`.
- **P1b: Tool-heavy** (3+ deterministic tools such as SQL queries, REST endpoints, or date/context lookups) — prime candidate for deterministic `@node` functions in an ADK 2.x `Workflow`.
- **P1c: Callback-heavy** (`before_model_callback`, `after_model_callback`, etc. performing context injection or output filtering) — prime candidate for pre/post `@node` functions.
- **P1d: Monolithic Procedural Prompt + Multi-Category Tools** — a single `LlmAgent` with 5+ tools (e.g., create, update, search, date lookup, web search) and a multi-step numbered prompt (`1. Clarify -> 2. Context -> 3. Select Tool -> 4. Validate -> 5. Execute -> 6. Format`). **Strongest single-agent candidate for decomposition into a multi-branch routed `Workflow` graph.**

### How to Decompose Pattern P1d into a Graph:
1. **Context Enrichment `@node` (`"START"`)**: Extract deterministic context tools (e.g., `get_current_date()`) into an entry Python node that populates `ctx.state`.
2. **Intent Router `LlmAgent` + Dispatcher `@node`**: Replace ad-hoc tool selection across 10+ tools with a classifier `LlmAgent(output_schema=IntentSchema)` followed by a deterministic router function emitting `Event(route=...)`.
3. **Branch Extractor `LlmAgent` + Deterministic Execution `@node`**: For each branch (e.g., `create`, `update`, `search`), pair a focused `LlmAgent(output_schema=PayloadSchema)` with a deterministic Python `@node` that enforces pre-conditions (e.g., duplicate checks) and calls the underlying database/MCP/API tool directly.
4. **Formatter `@node`**: Convert structured database/API results into Markdown tables or formatted text deterministically in Python.

---

## P2: `SequentialAgent` Chain (ADK 1.x)

**Detection**: `SequentialAgent(` with `sub_agents=[agent1, agent2, ...]`.

**Code signature**:
```python
from google.adk.agents import SequentialAgent, LlmAgent

agent_a = LlmAgent(name="a", model="gemini-3.8-flash", output_key="result_a")
agent_b = LlmAgent(name="b", model="gemini-3.8-flash", instruction="...{result_a}...")
pipeline = SequentialAgent(name="pipeline", sub_agents=[agent_a, agent_b])
```

**Sub-variants**:
- **P2a: Pure LLM chain** — all sub-agents are `LlmAgent`.
- **P2b: Mixed chain** — contains deterministic tools/callbacks between LLM steps.
- **P2c: Nested** — contains `ParallelAgent` or `LoopAgent` as sub-agents.

---

## P3: `ParallelAgent` Concurrent Execution (ADK 1.x)

**Detection**: `ParallelAgent(` with `sub_agents=[...]`.

**Code signature**:
```python
from google.adk.agents import ParallelAgent, LlmAgent

parallel = ParallelAgent(name="research", sub_agents=[agent_a, agent_b, agent_c])
```

**Sub-variants**:
- **P3a: Independent parallel** — sub-agents do not merge state downstream.
- **P3b: Fan-out/fan-in** — a downstream agent merges parallel outputs (maps to ADK 2.x tuple fan-out + `JoinNode`).

---

## P4: `LoopAgent` with Exit Condition (ADK 1.x)

**Detection**: `LoopAgent(` with `sub_agents=[...]` and `max_iterations=`.

**Code signature**:
```python
from google.adk.agents import LoopAgent, LlmAgent
from google.adk.tools import exit_loop

agent = LlmAgent(name="refiner", model="gemini-3.8-flash", tools=[exit_loop])
loop = LoopAgent(name="refine_loop", sub_agents=[agent], max_iterations=5)
```

**Sub-variants**:
- **P4a: Single agent loop** — one `LlmAgent` refining its own output.
- **P4b: Multi-agent loop** — `SequentialAgent`/`ParallelAgent` inside the loop.
- **P4c: Conditional exit** — custom exit logic in callbacks or `exit_loop` tool (maps to deterministic check `@node` with `Event(route="continue"|"done")`).

---

## P5: Hierarchical Delegation via `AgentTool` (ADK 1.x)

**Detection**: `AgentTool(` wrapping a sub-agent, attached to a parent agent's `tools=`.

**Code signature**:
```python
from google.adk.tools import AgentTool

child = LlmAgent(name="specialist", model="gemini-3.8-flash", ...)
parent = LlmAgent(name="coordinator", model="gemini-3.8-flash", tools=[AgentTool(child)])
```

**Sub-variants**:
- **P5a: Single delegation** — one `AgentTool` child (e.g., a `search_agent` wrapping `google_search` attached to a DB agent). In a `Workflow` graph, this becomes a dedicated routed branch node (e.g., `route="external_search"` or `route="fallback_web_search"`).
- **P5b: Multi-delegation** — parent chooses among multiple `AgentTool` children (maps to routed `Workflow` edges).
- **P5c: Deep hierarchy** — 3+ levels of `AgentTool` nesting.

---

## P6: Custom `BaseAgent` Subclass

**Detection**: Class inheriting from `BaseAgent` with `_run_async_impl` method.

**Code signature**:
```python
from google.adk.agents import BaseAgent

class MyOrchestrator(BaseAgent):
    async def _run_async_impl(self, ctx):
        async for event in self.sub_agent.run(ctx):
            yield event
```

**Sub-variants**:
- **P6a: Simple wrapper** — delegates to sub-agents with minimal logic.
- **P6b: Custom orchestrator** — implements branching/routing/retry logic in imperative Python (maps directly to `Workflow` routed edges).
- **P6c: Stateful controller** — maintains state across sub-agent calls (maps to `@node` functions returning `Event(state={...})`).

---

## P7: Callback-Heavy Agent

**Detection**: Agent with 2+ callbacks (`before_agent_callback`, `after_agent_callback`, `before_model_callback`, `after_model_callback`, `before_tool_callback`, `after_tool_callback`).

---

## P8: Mixed / Nested Patterns

**Detection**: Combination of 2+ patterns above in a single codebase (e.g., `SequentialAgent` + `ParallelAgent`, or `P1d` + `P5a`).

---

## P9: ADK 2.x Basic Orchestration $\rightarrow$ ADK 2.x Graph Orchestration

**Detection**: Project already uses `google-adk >= 2.0.0`, and agents are orchestrated without `Workflow` graphs using one of:
1. **P9a: Coordinator `LlmAgent` with `sub_agents=[...]` / `BaseLlmAgent(mode="task"|"single_turn")`**:
   ```python
   from google.adk.workflow.agents.base_llm_agent import BaseLlmAgent
   from google.adk.workflow.agents.llm_agent import LlmAgent

   specialist_a = BaseLlmAgent(name="a", mode="single_turn", input_schema=InA, output_schema=OutA, ...)
   specialist_b = BaseLlmAgent(name="b", mode="single_turn", input_schema=InB, output_schema=OutB, ...)
   root_agent = LlmAgent(name="coordinator", model="gemini-3.8-flash", sub_agents=[specialist_a, specialist_b])
   ```
   *Why convert to Graph (`Workflow`)*: The coordinator LLM currently runs before and after every sub-agent call to decide routing and synthesize output. Replacing the coordinator loop with an explicit `Workflow` graph (Intent Router `LlmAgent(output_schema=...)` $\rightarrow$ deterministic `Event(route=...)` $\rightarrow$ specialist branch $\rightarrow$ deterministic formatter `@node`) eliminates the post-delegation coordinator LLM turn and makes routing 100% deterministic and inspectable.
2. **P9b: ADK 2.x Single `LlmAgent` with Procedural Prompt & Deterministic Tools** (same structure as `P1b`/`P1d`, running on ADK 2.x runtime without `Workflow`).

---

## Detection Grep Commands

```bash
# 1. ADK version & existing Workflow usage
grep -rn "google-adk" pyproject.toml requirements*.txt uv.lock 2>/dev/null
grep -rn "Workflow\|JoinNode\|Edge\.chain" --include="*.py"

# 2. Agent types (1.x and 2.x basic)
grep -rn "LlmAgent(\|Agent(\|BaseLlmAgent(" --include="*.py"
grep -rn "SequentialAgent\|ParallelAgent\|LoopAgent" --include="*.py"
grep -rn "class.*BaseAgent" --include="*.py"
grep -rn "AgentTool(\|sub_agents=" --include="*.py"

# 3. State flow & schemas
grep -rn "output_key=\|output_schema=\|input_schema=" --include="*.py"
grep -rn "ctx.state\|session.state" --include="*.py"

# 4. Callbacks & Tools
grep -rn "before_agent_callback\|after_agent_callback\|before_model_callback\|after_model_callback" --include="*.py"
grep -rn "FunctionTool\|BaseTool\|AgentTool\|tools=" --include="*.py"
```
