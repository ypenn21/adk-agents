# ADK 2.x Workflow Graph Code Scaffolds

Ready-to-use templates for generating ADK 2.x `Workflow` graph code from either **ADK 1.x** patterns (`P1`–`P8`) or **ADK 2.x Basic Orchestration** patterns (`P1b`/`P1d`/`P9`). Default all model assignments to `gemini-3.8-flash` (or preserve existing `>=3.5` model configurations).

---

## Scaffold 1: Decomposed Procedural Agent / Multi-Branch Graph (from P1b, P1d, P9)

Use this scaffold when converting a monolithic tool-heavy `Agent`/`LlmAgent` (or basic coordinator `LlmAgent`) into a deterministic ADK 2.x `Workflow` graph with:
1. Entry context enrichment `@node`
2. Typed `output_schema` Intent Router `LlmAgent` + deterministic route dispatcher `@node`
3. Per-branch Pydantic extractor `LlmAgent` + deterministic pre-check/execution `@node`
4. Deterministic Markdown/output formatter `@node`

```python
"""
ADK 2.x Graph Orchestration Workflow
Migrated from: [ORIGINAL_AGENT_NAME] ([Mode A: ADK 1.x -> 2.x | Mode B: ADK 2.x Basic -> Graph])
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from google.adk.agents.context import Context
from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.workflow import Workflow
from google.adk.workflow.node import node


# --- 1. Typed Pydantic State & Routing Schemas ---

class WorkflowIntent(str, Enum):
    ACTION_A = "action_a"
    ACTION_B = "action_b"
    SEARCH = "search"
    EXTERNAL_SEARCH = "external_search"
    CLARIFY = "clarify"


class IntentClassificationResult(BaseModel):
    intent: WorkflowIntent
    has_required_info: bool = Field(
        default=True,
        description="False if required parameters are missing or request is ambiguous.",
    )
    clarification_question: Optional[str] = None


# --- 2. Deterministic Function Nodes (@node) ---

@node
def enrich_session_context(ctx: Context, node_input: Any) -> Event:
    """Deterministic entry node: injects runtime context (e.g., current_date) without an LLM tool call."""
    current_date = datetime.now().strftime("%Y-%m-%d")
    user_query = str(node_input) if node_input is not None else ""
    return Event(
        data=user_query,
        state={
            "current_date": current_date,
            "user_query": user_query,
        },
    )


@node
def dispatch_intent_route(ctx: Context, node_input: Any) -> Event:
    """Deterministic router reading structured output from intent_router_agent."""
    raw = ctx.state.get("intent_classification") or {}
    parsed = (
        raw
        if isinstance(raw, IntentClassificationResult)
        else IntentClassificationResult.model_validate(raw)
    )
    if not parsed.has_required_info or parsed.intent == WorkflowIntent.CLARIFY:
        return Event(data=node_input, route="clarify")
    return Event(data=node_input, route=parsed.intent.value)


@node
async def execute_action_a_with_precheck(ctx: Context, node_input: Any) -> Event:
    """Deterministic pre-check (e.g. duplicate search) + database/MCP tool execution."""
    payload = ctx.state.get("action_a_payload")
    # 1. Run deterministic pre-condition check
    # 2. Execute underlying deterministic tool
    result = {"status": "success", "payload": payload}
    return Event(data=result, state={"operation_result": result})


@node
def format_final_response(ctx: Context, node_input: Any) -> str:
    """Deterministic output formatting (e.g., Markdown table serialization)."""
    result = ctx.state.get("operation_result") or node_input
    return str(result)


# --- 3. Focused LLM Agent Nodes ---

def build_workflow(model: Any = "gemini-3.8-flash") -> Workflow:
    intent_router_agent = LlmAgent(
        name="intent_router_agent",
        model=model,
        instruction=(
            "Today is {current_date}. Classify the user's request into one of the supported intents: "
            "{user_query}"
        ),
        output_schema=IntentClassificationResult,
        output_key="intent_classification",
    )

    action_a_extractor_agent = LlmAgent(
        name="action_a_extractor_agent",
        model=model,
        instruction="Extract validated parameters for Action A from: {user_query}",
        # output_schema=ActionAPayload,
        output_key="action_a_payload",
    )

    clarification_agent = LlmAgent(
        name="clarification_agent",
        model=model,
        instruction="Ask a concise clarifying question to resolve missing details in: {user_query}",
        output_key="clarification_response",
    )

    return Workflow(
        name="[WORKFLOW_NAME]",
        description="[DESCRIPTION]",
        edges=[
            ("START", enrich_session_context),
            (enrich_session_context, intent_router_agent),
            (intent_router_agent, dispatch_intent_route),
            (dispatch_intent_route, action_a_extractor_agent, "action_a"),
            (action_a_extractor_agent, execute_action_a_with_precheck),
            (execute_action_a_with_precheck, format_final_response),
            (dispatch_intent_route, clarification_agent, "clarify"),
        ],
    )
```

---

## Scaffold 2: Sequential Pipeline with Function Nodes (from P2b + P7)

```python
from typing import Any
from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.workflow import Edge, Workflow
from google.adk.workflow.node import node


@node
def pre_process_node(node_input: str) -> Event:
    """Migrated from: [ORIGINAL_CALLBACK_OR_TOOL_NAME]"""
    return Event(
        data=node_input,
        state={"enriched_context": "..."},
    )


@node
def post_process_node(node_input: Any) -> str:
    """Migrated from: [ORIGINAL_CALLBACK_OR_TOOL_NAME]"""
    return str(node_input)


primary_agent = LlmAgent(
    name="[AGENT_NAME]",
    model="gemini-3.8-flash",
    instruction="[INSTRUCTION_USING_{enriched_context}]",
    output_key="agent_output",
)

root_agent = Workflow(
    name="[PIPELINE_NAME]",
    description="[DESCRIPTION]",
    edges=Edge.chain("START", pre_process_node, primary_agent, post_process_node),
)
```

---

## Scaffold 3: Parallel Fan-Out / Fan-In with `JoinNode` (from P3)

```python
from google.adk.agents.llm_agent import LlmAgent
from google.adk.workflow import Workflow, JoinNode

[PARALLEL_AGENT_DEFINITIONS]  # Use output_schema on each parallel LlmAgent

join = JoinNode(name="[JOIN_NAME]")

[SYNTHESIZER_AGENT_DEFINITION]

root_agent = Workflow(
    name="[PIPELINE_NAME]",
    description="[DESCRIPTION]",
    edges=[
        ("START", ([PARALLEL_AGENTS_TUPLE])),
        (([PARALLEL_AGENTS_TUPLE]), join),
        (join, [SYNTHESIZER_AGENT]),
    ],
)
```

---

## Scaffold 4: Loop with Deterministic Exit Condition (from P4)

```python
from typing import Any
from google.adk.agents.context import Context
from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.workflow import Workflow
from google.adk.workflow.node import node

[LOOP_BODY_AGENT_DEFINITION]


@node
def check_exit(ctx: Context, node_input: Any) -> Event:
    """Deterministic exit check replacing LLM-invoked exit_loop tool."""
    iteration = ctx.state.get("_iteration_count", 0) + 1
    if iteration >= [MAX_ITERATIONS] or [EXIT_CONDITION]:
        return Event(data=node_input, route="done", state={"_iteration_count": iteration})
    return Event(data=node_input, route="continue", state={"_iteration_count": iteration})


@node
def finalize(node_input: Any) -> str:
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

---

## Common Helper Snippets

### Extracting text safely from `types.Content` in a function node
```python
from typing import Any
from google.genai import types

def extract_text(node_input: Any) -> str:
    if isinstance(node_input, types.Content):
        return "".join(p.text for p in (node_input.parts or []) if p.text)
    return str(node_input) if node_input is not None else ""
```
