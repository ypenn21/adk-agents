# ADK 2.0 Code Scaffolds

Ready-to-use templates for generating ADK 2.0 Workflow code from ADK 1.x patterns. Replace `[PLACEHOLDER]` values with actual agent logic.

## Scaffold: Sequential Pipeline (from P2)

```python
"""
ADK 2.0 Migration: Sequential Pipeline
Migrated from: SequentialAgent with [N] sub-agents
"""

from google.adk.agents.llm_agent import LlmAgent
from google.adk.workflow import Edge, Workflow

[AGENT_DEFINITIONS]
# Each LlmAgent preserves: name, model, instruction, output_key, tools

root_agent = Workflow(
    name="[PIPELINE_NAME]",
    description="[DESCRIPTION]",
    edges=Edge.chain("START", [AGENT_LIST]),
)
```

## Scaffold: Sequential with Function Nodes (from P2b + P7)

```python
"""
ADK 2.0 Migration: Sequential Pipeline with Function Nodes
Migrated from: SequentialAgent with callbacks/deterministic tools
Original callbacks migrated to: [LIST_OF_FUNCTION_NODES]
"""

from typing import Any
from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.workflow import Edge, Workflow


# --- Function nodes (migrated from callbacks/deterministic tools) ---

def [PRE_PROCESS_NAME](node_input: str) -> Event:
    """Migrated from: [ORIGINAL_CALLBACK_OR_TOOL_NAME]"""
    [ORIGINAL_LOGIC]
    return Event(
        data=[PROCESSED_DATA],
        state={[STATE_KEYS]},
    )


def [POST_PROCESS_NAME](node_input: Any, [STATE_PARAMS]) -> str:
    """Migrated from: [ORIGINAL_CALLBACK_OR_TOOL_NAME]"""
    [ORIGINAL_LOGIC]
    return [FORMATTED_OUTPUT]


# --- LLM agent nodes ---

[AGENT_DEFINITIONS]


root_agent = Workflow(
    name="[PIPELINE_NAME]",
    description="[DESCRIPTION]",
    edges=Edge.chain("START", [PRE_PROCESS], [AGENTS], [POST_PROCESS]),
)
```

## Scaffold: Parallel Fan-out/Fan-in (from P3)

```python
"""
ADK 2.0 Migration: Parallel Execution with JoinNode
Migrated from: ParallelAgent with [N] sub-agents
"""

from google.adk.agents.llm_agent import LlmAgent
from google.adk.workflow import Edge, Workflow, JoinNode

[PARALLEL_AGENT_DEFINITIONS]

join = JoinNode(name="[JOIN_NAME]")

[DOWNSTREAM_AGENT_DEFINITIONS]

root_agent = Workflow(
    name="[PIPELINE_NAME]",
    description="[DESCRIPTION]",
    edges=[
        ("START", ([PARALLEL_AGENTS_TUPLE])),
        (([PARALLEL_AGENTS_TUPLE]), join),
        (join, [DOWNSTREAM_AGENT]),
    ],
)
```

## Scaffold: Parallel inside Sequential (from P2c + P3)

```python
"""
ADK 2.0 Migration: Sequential pipeline with parallel stage
Migrated from: SequentialAgent containing ParallelAgent
"""

from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.workflow import Edge, Workflow, JoinNode

[PRE_AGENT_DEFINITIONS]

[PARALLEL_AGENT_DEFINITIONS]

join = JoinNode(name="merge")

[POST_AGENT_DEFINITIONS]

root_agent = Workflow(
    name="[PIPELINE_NAME]",
    description="[DESCRIPTION]",
    edges=[
        ("START", [PRE_AGENT]),
        ([PRE_AGENT], ([PARALLEL_AGENTS_TUPLE])),
        (([PARALLEL_AGENTS_TUPLE]), join),
        (join, [POST_AGENT]),
    ],
)
```

## Scaffold: Loop with Routing (from P4)

```python
"""
ADK 2.0 Migration: Loop with deterministic exit condition
Migrated from: LoopAgent with max_iterations=[N]
Original exit: exit_loop tool (LLM-decided) -> now deterministic function node
"""

from typing import Any
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.adk.workflow import Workflow

[LOOP_BODY_AGENT_DEFINITIONS]


def check_exit(ctx: Context, node_input: Any, [STATE_PARAMS]) -> Event:
    """Migrated from: exit_loop tool / max_iterations=[N]"""
    iteration = ctx.state.get("_iteration_count", 0) + 1
    # [ORIGINAL_EXIT_CONDITION or max iteration check]
    if iteration >= [MAX_ITERATIONS] or [EXIT_CONDITION]:
        return Event(data=node_input, route="done", state={"_iteration_count": iteration})
    return Event(data=node_input, route="continue", state={"_iteration_count": iteration})


def finalize(node_input: Any) -> str:
    """Final output after loop completes."""
    return str(node_input)


root_agent = Workflow(
    name="[LOOP_NAME]",
    description="[DESCRIPTION]",
    edges=[
        ("START", [LOOP_BODY_AGENT]),
        ([LOOP_BODY_AGENT], check_exit),
        (check_exit, [LOOP_BODY_AGENT], "continue"),
        (check_exit, finalize, "done"),
    ],
)
```

## Scaffold: Routing / Conditional Branching (from P5b or P6)

```python
"""
ADK 2.0 Migration: Conditional routing
Migrated from: [AgentTool multi-delegation / Custom BaseAgent with conditionals]
"""

from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.workflow import Workflow


def classify(node_input: str) -> Event:
    """Migrated from: [ORIGINAL_ROUTING_LOGIC]"""
    [CLASSIFICATION_LOGIC]
    if [CONDITION_A]:
        return Event(data=node_input, route="[ROUTE_A]")
    elif [CONDITION_B]:
        return Event(data=node_input, route="[ROUTE_B]")
    return Event(data=node_input, route="default")


[BRANCH_AGENT_DEFINITIONS]


root_agent = Workflow(
    name="[ROUTER_NAME]",
    description="[DESCRIPTION]",
    edges=[
        ("START", classify),
        (classify, [AGENT_A], "[ROUTE_A]"),
        (classify, [AGENT_B], "[ROUTE_B]"),
        (classify, [DEFAULT_AGENT], "__DEFAULT__"),
    ],
)
```

## Scaffold: Task Mode Delegation (from P5)

```python
"""
ADK 2.0 Migration: Task mode delegation
Migrated from: AgentTool hierarchy
"""

from pydantic import BaseModel
from google.adk.workflow.agents.base_llm_agent import BaseLlmAgent
from google.adk.workflow.agents.llm_agent import LlmAgent


class [TASK_INPUT_NAME](BaseModel):
    [INPUT_FIELDS]


class [TASK_OUTPUT_NAME](BaseModel):
    [OUTPUT_FIELDS]


[TASK_AGENT_NAME] = BaseLlmAgent(
    name="[AGENT_NAME]",
    mode="[task_or_single_turn]",
    input_schema=[TASK_INPUT_NAME],
    output_schema=[TASK_OUTPUT_NAME],
    instruction="[INSTRUCTION]. Call finish_task with results when done.",
    description="[DESCRIPTION]",
    tools=[[TOOLS]],
)

root_agent = LlmAgent(
    name="[COORDINATOR_NAME]",
    model="[MODEL]",
    sub_agents=[[TASK_AGENTS]],
    instruction="[COORDINATOR_INSTRUCTION]",
)
```

## Scaffold: Mixed/Nested (from P8)

```python
"""
ADK 2.0 Migration: Complex nested workflow
Migrated from: [DESCRIBE_ORIGINAL_NESTING]
All nesting levels flattened into a single Workflow graph.
"""

from typing import Any
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.adk.workflow import Workflow, JoinNode

# --- Function nodes ---
[FUNCTION_NODE_DEFINITIONS]

# --- LLM agent nodes ---
[LLM_AGENT_DEFINITIONS]

# --- Join nodes ---
[JOIN_NODE_DEFINITIONS]

root_agent = Workflow(
    name="[WORKFLOW_NAME]",
    description="[DESCRIPTION]",
    edges=[
        [EDGE_DEFINITIONS]
    ],
)
```

## Common Code Snippets

### Function node receiving LLM output (no output_schema)

```python
from typing import Any
from google.genai import types

def process_llm_output(node_input: Any) -> str:
    """Handle LlmAgentNode output which is types.Content, not str."""
    if isinstance(node_input, types.Content):
        return "".join(p.text for p in (node_input.parts or []) if p.text)
    return str(node_input) if node_input is not None else ""
```

### Function node with state persistence

```python
from google.adk.events.event import Event

def persist_data(node_input: str) -> Event:
    """Use Event(state=...) for replayable state changes."""
    return Event(
        data=node_input,
        state={"key": "value", "nested": {"a": 1}},
    )
```

### Function node reading state via auto-resolved params

```python
def uses_state(node_input: str, user_name: str, settings: dict) -> str:
    """user_name and settings auto-resolved from ctx.state."""
    return f"{user_name}: {node_input}"
```
