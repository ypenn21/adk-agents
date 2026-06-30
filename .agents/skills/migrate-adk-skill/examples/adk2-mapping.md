# ADK 1.x to 2.0 Migration Mapping

Pattern-by-pattern mapping showing how each ADK 1.x construct translates to ADK 2.0.

## P1: Single LlmAgent with Tools

### P1a: Simple chat — NO MIGRATION

Keep as-is. ADK 1.x `LlmAgent` works unchanged in ADK 2.0. No Workflow needed.

### P1b: Tool-heavy with deterministic tools → Workflow with function nodes

**Before (ADK 1.x)**:
```python
def fetch_data(query: str) -> dict:
    """Deterministic DB lookup — no LLM needed."""
    return db.execute(query)

def format_report(data: dict) -> str:
    """Deterministic formatting — no LLM needed."""
    return tabulate(data)

agent = LlmAgent(
    name="analyst",
    model="gemini-2.5-flash",
    instruction="Analyze user questions about data...",
    tools=[fetch_data, format_report],
)
```

**After (ADK 2.0)**:
```python
from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.workflow import Edge, Workflow

def fetch_data(node_input: str) -> Event:
    """Runs deterministically — no LLM cost."""
    data = db.execute(node_input)
    return Event(data=data, state={"raw_data": data})

analyst = LlmAgent(
    name="analyst",
    model="gemini-2.5-flash",
    instruction="Analyze this data and answer the user's question:\n{raw_data}",
    output_key="analysis",
)

def format_report(analysis: str) -> str:
    """Runs deterministically — no LLM cost."""
    return tabulate(analysis)

root_agent = Workflow(
    name="analyst_pipeline",
    edges=Edge.chain("START", fetch_data, analyst, format_report),
)
```

**Benefit**: Deterministic steps skip LLM invocation entirely. Saves tokens and latency.

### P1c: Callback-heavy → Workflow with function nodes

**Before (ADK 1.x)**:
```python
async def before_model_callback(ctx, llm_request):
    ctx.state["context"] = fetch_relevant_context(ctx.state["query"])

async def after_model_callback(ctx, llm_response):
    # Filter PII from response
    filtered = remove_pii(llm_response.content.parts[0].text)
    llm_response.content.parts[0].text = filtered

agent = LlmAgent(
    name="assistant",
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
    ...
)
```

**After (ADK 2.0)**:
```python
def enrich_context(node_input: str) -> Event:
    context = fetch_relevant_context(node_input)
    return Event(data=node_input, state={"context": context})

assistant = LlmAgent(
    name="assistant",
    instruction="Answer using this context:\n{context}",
    output_key="raw_response",
)

def filter_pii(raw_response: str) -> str:
    return remove_pii(raw_response)

root_agent = Workflow(
    name="safe_assistant",
    edges=Edge.chain("START", enrich_context, assistant, filter_pii),
)
```

**Benefit**: Pre/post logic becomes explicit, testable graph nodes instead of hidden callbacks.

---

## P2: SequentialAgent Chain → Workflow with Edge.chain

**Before (ADK 1.x)**:
```python
agent_a = LlmAgent(name="a", output_key="result_a", ...)
agent_b = LlmAgent(name="b", instruction="...{result_a}...", output_key="result_b", ...)
agent_c = LlmAgent(name="c", instruction="...{result_b}...", ...)

pipeline = SequentialAgent(name="pipeline", sub_agents=[agent_a, agent_b, agent_c])
```

**After (ADK 2.0)**:
```python
from google.adk.agents.llm_agent import LlmAgent
from google.adk.workflow import Edge, Workflow

agent_a = LlmAgent(name="a", output_key="result_a", ...)
agent_b = LlmAgent(name="b", instruction="...{result_a}...", output_key="result_b", ...)
agent_c = LlmAgent(name="c", instruction="...{result_b}...", ...)

root_agent = Workflow(
    name="pipeline",
    edges=Edge.chain("START", agent_a, agent_b, agent_c),
)
```

**Benefit**: Minimal change for pure LLM chains. Real benefit comes when you can insert function nodes between LLM agents for deterministic pre/post processing.

---

## P3: ParallelAgent → Workflow with fan-out + JoinNode

**Before (ADK 1.x)**:
```python
researcher_a = LlmAgent(name="a", output_key="findings_a", ...)
researcher_b = LlmAgent(name="b", output_key="findings_b", ...)
researcher_c = LlmAgent(name="c", output_key="findings_c", ...)

parallel = ParallelAgent(name="research", sub_agents=[researcher_a, researcher_b, researcher_c])

synthesizer = LlmAgent(
    name="synthesizer",
    instruction="Combine: {findings_a}, {findings_b}, {findings_c}",
)

pipeline = SequentialAgent(name="pipeline", sub_agents=[parallel, synthesizer])
```

**After (ADK 2.0)**:
```python
from google.adk.agents.llm_agent import LlmAgent
from google.adk.workflow import Edge, Workflow, JoinNode

researcher_a = LlmAgent(name="a", output_key="findings_a", ...)
researcher_b = LlmAgent(name="b", output_key="findings_b", ...)
researcher_c = LlmAgent(name="c", output_key="findings_c", ...)

join = JoinNode(name="collect")

synthesizer = LlmAgent(
    name="synthesizer",
    instruction="Combine: {findings_a}, {findings_b}, {findings_c}",
)

root_agent = Workflow(
    name="pipeline",
    edges=[
        ("START", (researcher_a, researcher_b, researcher_c)),  # Fan-out
        ((researcher_a, researcher_b, researcher_c), join),      # Fan-in
        (join, synthesizer),
    ],
)
```

**Benefit**: Explicit fan-out/fan-in. JoinNode provides structured merge. Can add function nodes between fan-in and synthesizer.

**Important**: LLM agents feeding into JoinNode should use `output_schema` to avoid serialization errors with database session services.

---

## P4: LoopAgent → Workflow with routed edges (cycle)

**Before (ADK 1.x)**:
```python
from google.adk.tools import exit_loop

refiner = LlmAgent(
    name="refiner",
    instruction="Improve the draft. Call exit_loop when quality is sufficient.",
    tools=[exit_loop],
    output_key="draft",
)

loop = LoopAgent(name="refine_loop", sub_agents=[refiner], max_iterations=5)
```

**After (ADK 2.0)**:
```python
from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.workflow import Workflow

refiner = LlmAgent(
    name="refiner",
    instruction="Improve the draft:\n{draft}",
    output_key="draft",
)

iteration_count = 0

def check_quality(node_input, draft: str) -> Event:
    global iteration_count
    iteration_count += 1
    if iteration_count >= 5 or meets_quality_threshold(draft):
        return Event(data=draft, route="done")
    return Event(data=draft, route="continue")

def finalize(node_input) -> str:
    return str(node_input)

root_agent = Workflow(
    name="refine_loop",
    edges=[
        ("START", refiner),
        (refiner, check_quality),
        (check_quality, refiner, "continue"),   # Loop back
        (check_quality, finalize, "done"),       # Exit
    ],
)
```

**Benefit**: Exit condition is deterministic (function node), not LLM-decided. Explicit routing makes the loop visible in the graph. Can add validation/transformation nodes within the cycle.

**Note**: Graph cycles require at least one routed edge. Always include a route condition.

---

## P5: Hierarchical AgentTool → Task Mode or Nested Workflow

### P5a/P5b: Delegation → Task Mode

**Before (ADK 1.x)**:
```python
specialist = LlmAgent(name="specialist", ...)
parent = LlmAgent(name="coordinator", tools=[AgentTool(specialist)])
```

**After (ADK 2.0)**:
```python
from google.adk.workflow.agents.base_llm_agent import BaseLlmAgent
from google.adk.workflow.agents.llm_agent import LlmAgent
from pydantic import BaseModel

class TaskInput(BaseModel):
    query: str

class TaskOutput(BaseModel):
    result: str

specialist = BaseLlmAgent(
    name="specialist",
    mode="task",  # or "single_turn" for autonomous
    input_schema=TaskInput,
    output_schema=TaskOutput,
    instruction="Process the query and call finish_task with results.",
    description="Handles specialized queries.",
)

root_agent = LlmAgent(
    name="coordinator",
    model="gemini-2.5-flash",
    sub_agents=[specialist],
    instruction="Delegate specialized queries via request_task_specialist.",
)
```

**Benefit**: Typed input/output schemas. Coordinator gets structured results. `single_turn` mode eliminates unnecessary conversation turns.

### P5b: Multi-delegation routing → Task Mode with multiple sub-agents

**Before (ADK 1.x)**:
```python
parent = LlmAgent(
    name="router",
    tools=[AgentTool(agent_a), AgentTool(agent_b), AgentTool(agent_c)],
    instruction="Route queries to the right specialist...",
)
```

**After (ADK 2.0)**:
```python
root_agent = LlmAgent(
    name="router",
    model="gemini-2.5-flash",
    sub_agents=[task_agent_a, task_agent_b, task_agent_c],
    instruction="Route queries to the right specialist...",
)
```

**Benefit**: Each sub-agent has typed schemas. Coordinator gets structured results to work with.

---

## P6: Custom BaseAgent → Workflow (partial auto-migration)

Custom BaseAgent subclasses require manual analysis. Common sub-patterns that CAN be auto-migrated:

| Custom logic | ADK 2.0 equivalent |
|-------------|-------------------|
| Sequential delegation with conditionals | Workflow with routing edges |
| Retry logic around sub-agent calls | Function node with retry + routed edge |
| State accumulation across sub-agent calls | Function nodes with `Event(state={...})` |
| Custom fan-out/fan-in | Workflow fan-out tuples + JoinNode |

**Flag for manual review** when:
- Custom async generator logic (complex `yield` patterns)
- Direct manipulation of `InvocationContext` internals
- Custom event filtering or transformation

---

## P7: Callback-Heavy → Function Nodes

See P1c mapping above. General rule:

| Callback | ADK 2.0 equivalent |
|----------|-------------------|
| `before_agent_callback` (validation/short-circuit) | Function node BEFORE the LLM agent node |
| `before_model_callback` (context injection) | Function node with `Event(state={...})` before LLM |
| `after_model_callback` (output filtering) | Function node AFTER the LLM agent node |
| `after_agent_callback` (logging/storage) | Function node at the end of the chain |
| `before_tool_callback` (audit) | Keep as callback (ADK 2.0 still supports these) |
| `after_tool_callback` (validation) | Keep as callback (ADK 2.0 still supports these) |

**Note**: Tool-level callbacks (`before_tool_callback`, `after_tool_callback`) should generally stay as callbacks even in ADK 2.0 since they operate within an LLM agent node.

---

## P8: Mixed/Nested → Decompose and map individually

Break the nested structure into individual patterns, map each one, then compose in a single Workflow:

**Before (ADK 1.x)**:
```python
parallel = ParallelAgent(sub_agents=[a, b])
pipeline = SequentialAgent(sub_agents=[preprocess, parallel, postprocess])
loop = LoopAgent(sub_agents=[pipeline], max_iterations=3)
```

**After (ADK 2.0)**:
```python
join = JoinNode(name="merge")

root_agent = Workflow(
    name="complex_pipeline",
    edges=[
        ("START", preprocess_fn),              # P7: callback → function node
        (preprocess_fn, (a, b)),               # P3: fan-out
        ((a, b), join),                        # P3: fan-in
        (join, postprocess_fn),                # P7: callback → function node
        (postprocess_fn, check_done),          # P4: loop exit check
        (check_done, preprocess_fn, "again"),  # P4: loop back
        (check_done, finalize, "done"),        # P4: exit
    ],
)
```

**Benefit**: Entire complex orchestration visible as one graph. No nested agent types.

## Import Reference

ADK 2.0 imports for generated code:

```python
# Workflow core
from google.adk.workflow import Workflow, Edge
from google.adk.workflow import JoinNode

# LLM agent as workflow node (IMPORTANT: use this import, not workflow.agents)
from google.adk.agents.llm_agent import LlmAgent

# Events and state
from google.adk.events.event import Event
from google.adk.agents.context import Context

# Task mode (for hierarchical/delegation patterns)
from google.adk.workflow.agents.base_llm_agent import BaseLlmAgent
from google.adk.workflow.agents.llm_agent import LlmAgent as CoordinatorLlmAgent

# Parallel workers
from google.adk.workflow.node import node  # @node(parallel_worker=True)
```
