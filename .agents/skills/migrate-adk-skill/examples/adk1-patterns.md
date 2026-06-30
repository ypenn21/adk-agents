# ADK 1.x Pattern Detection Guide

8 cataloged patterns with detection rules, code signatures, and examples.

## P1: Single LlmAgent with Tools

**Detection**: `LlmAgent(` or `Agent(` with `tools=[...]`, no parent `SequentialAgent`/`ParallelAgent`.

**Code signature**:
```python
from google.adk.agents.llm_agent import Agent  # or LlmAgent
root_agent = Agent(name="...", model="...", instruction="...", tools=[...])
```

**Characteristics**:
- Standalone chat agent
- Tools extend its capabilities
- May have callbacks but no sub-agents
- Typically the `root_agent` directly

**Sub-variants**:
- P1a: Simple chat (few tools, short instruction) — pure conversational
- P1b: Tool-heavy (3+ tools, some deterministic) — candidate for function nodes
- P1c: Callback-heavy (before/after model callbacks doing transformation) — candidate for function nodes

---

## P2: SequentialAgent Chain

**Detection**: `SequentialAgent(` with `sub_agents=[agent1, agent2, ...]`.

**Code signature**:
```python
from google.adk.agents import SequentialAgent, LlmAgent

agent_a = LlmAgent(name="a", ..., output_key="result_a")
agent_b = LlmAgent(name="b", ..., instruction="...{result_a}...")
pipeline = SequentialAgent(name="pipeline", sub_agents=[agent_a, agent_b])
```

**Characteristics**:
- Agents run in list order
- State passed via `output_key` → `{var}` templates
- No conditional branching (always runs all agents)
- May contain non-LLM sub-agents (nested Sequential/Parallel)

**Sub-variants**:
- P2a: Pure LLM chain — all sub-agents are LlmAgent
- P2b: Mixed chain — contains function tools that do pre/post processing
- P2c: Nested — contains ParallelAgent or LoopAgent as sub-agents

---

## P3: ParallelAgent Concurrent Execution

**Detection**: `ParallelAgent(` with `sub_agents=[...]`.

**Code signature**:
```python
from google.adk.agents import ParallelAgent, LlmAgent

parallel = ParallelAgent(name="research", sub_agents=[agent_a, agent_b, agent_c])
```

**Characteristics**:
- All sub-agents run concurrently
- Each writes to its own `output_key`
- No built-in join/merge logic — downstream agent reads all keys from state
- Often wrapped inside a SequentialAgent for pre/post processing

**Sub-variants**:
- P3a: Independent parallel — sub-agents don't share state
- P3b: Fan-out/fan-in — a downstream agent merges parallel results

---

## P4: LoopAgent with Exit Condition

**Detection**: `LoopAgent(` with `sub_agents=[...]` and `max_iterations=`.

**Code signature**:
```python
from google.adk.agents import LoopAgent, LlmAgent
from google.adk.tools import exit_loop

agent = LlmAgent(name="refiner", tools=[exit_loop], ...)
loop = LoopAgent(name="refine_loop", sub_agents=[agent], max_iterations=5)
```

**Characteristics**:
- Runs sub-agents repeatedly until `exit_loop` tool is called or max iterations reached
- Exit condition is LLM-decided (non-deterministic)
- State accumulates across iterations
- Often used for iterative refinement patterns

**Sub-variants**:
- P4a: Single agent loop — one LlmAgent refining its own output
- P4b: Multi-agent loop — Sequential/Parallel inside the loop
- P4c: Conditional exit — custom exit logic in callbacks

---

## P5: Hierarchical via AgentTool

**Detection**: `AgentTool(` wrapping a sub-agent, attached to a parent agent's `tools=`.

**Code signature**:
```python
from google.adk.tools import AgentTool

child = LlmAgent(name="specialist", ...)
parent = LlmAgent(name="coordinator", tools=[AgentTool(child)])
```

**Characteristics**:
- Parent LLM decides when to delegate to child
- Child runs as a tool call (full LLM invocation)
- Parent gets child's response as tool result
- Can be nested (child has its own AgentTool children)

**Sub-variants**:
- P5a: Single delegation — one AgentTool child
- P5b: Multi-delegation — parent chooses among multiple AgentTool children (routing)
- P5c: Deep hierarchy — 3+ levels of AgentTool nesting

---

## P6: Custom BaseAgent Subclass

**Detection**: Class inheriting from `BaseAgent` with `_run_async_impl` method.

**Code signature**:
```python
from google.adk.agents import BaseAgent

class MyAgent(BaseAgent):
    async def _run_async_impl(self, ctx):
        # Custom orchestration logic
        async for event in self.sub_agent.run(ctx):
            yield event
```

**Characteristics**:
- Full custom control flow
- May implement conditional routing, loops, state manipulation
- Often used when Sequential/Parallel/Loop don't fit
- Hardest to auto-migrate — requires understanding the custom logic

**Sub-variants**:
- P6a: Simple wrapper — delegates to sub-agents with minimal logic
- P6b: Custom orchestrator — implements branching/routing/retry logic
- P6c: Stateful controller — maintains complex state across sub-agent calls

---

## P7: Callback-Heavy Agent

**Detection**: Agent with 2+ callbacks defined: `before_agent_callback`, `after_agent_callback`, `before_model_callback`, `after_model_callback`, `before_tool_callback`, `after_tool_callback`.

**Code signature**:
```python
agent = LlmAgent(
    name="guarded",
    before_agent_callback=validate_input,
    before_model_callback=inject_context,
    after_model_callback=filter_output,
    after_agent_callback=log_and_store,
    ...
)
```

**Characteristics**:
- Callbacks perform pre/post processing that could be deterministic function nodes
- `before_model_callback` often injects dynamic context (state manipulation)
- `after_model_callback` often filters/transforms LLM output
- `before_agent_callback` may short-circuit (return Content to skip LLM)

**Key question**: Is the callback logic deterministic (no LLM needed)? If yes, strong candidate for function nodes in ADK 2.0.

---

## P8: Mixed/Nested Patterns

**Detection**: Combination of 2+ patterns above in a single codebase.

**Examples**:
- SequentialAgent containing a ParallelAgent (P2 + P3)
- LoopAgent inside a SequentialAgent with AgentTool children (P4 + P2 + P5)
- Custom BaseAgent orchestrating Sequential and Parallel sub-flows (P6 + P2 + P3)

**Characteristics**:
- Most complex to analyze — must decompose into individual patterns
- Migration benefit is the sum of individual pattern benefits
- Often the strongest candidates for ADK 2.0 (explicit graph makes complexity visible)

## Detection Grep Commands

Quick-reference search patterns:

```bash
# Agent types
grep -rn "SequentialAgent\|ParallelAgent\|LoopAgent" --include="*.py"
grep -rn "class.*BaseAgent" --include="*.py"
grep -rn "AgentTool(" --include="*.py"

# State flow
grep -rn "output_key=" --include="*.py"
grep -rn "output_schema=" --include="*.py"
grep -rn "ctx.state\|session.state" --include="*.py"

# Callbacks
grep -rn "before_agent_callback\|after_agent_callback\|before_model_callback\|after_model_callback\|before_tool_callback\|after_tool_callback" --include="*.py"

# Tools
grep -rn "FunctionTool\|BaseTool\|AgentTool\|tools=" --include="*.py"

# Exit/transfer
grep -rn "exit_loop\|transfer_to_agent" --include="*.py"
```
