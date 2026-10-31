# ADK 1.x & ADK 2.x Basic to ADK 2.x Graph Orchestration Mapping

Pattern-by-pattern mapping showing how each ADK 1.x construct or ADK 2.x basic orchestration construct translates to an ADK 2.x `Workflow` graph.

---

## P1: Single `LlmAgent` with Tools

### P1a: Simple chat — NO MIGRATION
Keep as-is. Standalone `LlmAgent` works natively in ADK 2.x when no deterministic steps or multi-branch routing exist.

### P1b: Tool-heavy with deterministic tools $\rightarrow$ `Workflow` with function nodes

**Before (ADK 1.x or ADK 2.x Basic)**:
```python
def fetch_data(query: str) -> dict:
    """Deterministic DB lookup — no LLM needed."""
    return db.execute(query)

def format_report(data: dict) -> str:
    """Deterministic formatting — no LLM needed."""
    return tabulate(data)

agent = LlmAgent(
    name="analyst",
    model="gemini-3.8-flash",
    instruction="Analyze user questions about data...",
    tools=[fetch_data, format_report],
)
```

**After (ADK 2.x Graph `Workflow`)**:
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
    model="gemini-3.8-flash",
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

---

### P1c: Callback-heavy $\rightarrow$ `Workflow` with function nodes

**Before**:
```python
async def before_model_callback(ctx, llm_request):
    ctx.state["context"] = fetch_relevant_context(ctx.state["query"])

async def after_model_callback(ctx, llm_response):
    filtered = remove_pii(llm_response.content.parts[0].text)
    llm_response.content.parts[0].text = filtered

agent = LlmAgent(
    name="assistant",
    model="gemini-3.8-flash",
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)
```

**After (ADK 2.x Graph `Workflow`)**:
```python
def enrich_context(node_input: str) -> Event:
    context = fetch_relevant_context(node_input)
    return Event(data=node_input, state={"context": context})

assistant = LlmAgent(
    name="assistant",
    model="gemini-3.8-flash",
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

---

### P1d: Monolithic Procedural `LlmAgent` with Multi-Category Tools $\rightarrow$ Multi-Branch Routed `Workflow` Graph

When a single `LlmAgent` has a multi-step procedural prompt (e.g., clarify, get date, route between create/update/search/external web search, validate enums, check duplicates, format Markdown table) and 5+ tools attached:

**Before (ADK 1.x or ADK 2.x Basic Single Agent)**:
```python
root_agent = Agent(
    model="gemini-3.8-flash",
    name="monolithic_assistant",
    instruction="1. Clarify... 2. Get date... 3. Search before create... 4. Format table...",
    tools=[load_memory, get_current_date, web_search_tool, *get_db_crud_tools()],
)
```

**After (ADK 2.x Multi-Branch `Workflow` Graph)**:
```python
from datetime import datetime
from enum import Enum
from pydantic import BaseModel
from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.workflow import Workflow
from google.adk.workflow.node import node

class IntentType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    SEARCH = "search"
    EXTERNAL_SEARCH = "external_search"
    CLARIFY = "clarify"

class IntentClassification(BaseModel):
    intent: IntentType
    has_required_fields: bool
    missing_fields_prompt: str = ""

@node
def enrich_session_context(node_input: str) -> Event:
    """Deterministic entry node: injects current_date without an LLM tool-call round-trip."""
    return Event(
        data=node_input,
        state={
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "user_query": str(node_input),
        },
    )

intent_router_agent = LlmAgent(
    name="intent_router_agent",
    model="gemini-3.8-flash",
    instruction="Classify the user request for date {current_date}: {user_query}",
    output_schema=IntentClassification,
    output_key="intent_classification",
)

@node
def dispatch_intent_route(node_input, intent_classification: dict) -> Event:
    parsed = IntentClassification.model_validate(intent_classification)
    if not parsed.has_required_fields or parsed.intent == IntentType.CLARIFY:
        return Event(data=node_input, route="clarify")
    return Event(data=node_input, route=parsed.intent.value)

root_agent = Workflow(
    name="decomposed_workflow_agent",
    edges=[
        ("START", enrich_session_context),
        (enrich_session_context, intent_router_agent),
        (intent_router_agent, dispatch_intent_route),
        (dispatch_intent_route, create_extractor_agent, "create"),
        (create_extractor_agent, execute_create_with_precheck_node),
        (execute_create_with_precheck_node, format_response_node),
        (dispatch_intent_route, update_extractor_agent, "update"),
        (update_extractor_agent, execute_update_node),
        (execute_update_node, format_response_node),
        (dispatch_intent_route, search_extractor_agent, "search"),
        (search_extractor_agent, execute_search_node),
        (execute_search_node, format_response_node, "has_results"),
        (execute_search_node, external_web_search_agent, "fallback_web_search"),
        (dispatch_intent_route, external_web_search_agent, "external_search"),
        (external_web_search_agent, format_response_node),
        (dispatch_intent_route, clarification_agent, "clarify"),
    ],
)
```

---

## P2: `SequentialAgent` Chain $\rightarrow$ `Workflow` with `Edge.chain`

```python
from google.adk.agents.llm_agent import LlmAgent
from google.adk.workflow import Edge, Workflow

root_agent = Workflow(
    name="pipeline",
    edges=Edge.chain("START", agent_a, deterministic_transform_node, agent_b),
)
```

---

## P3: `ParallelAgent` $\rightarrow$ `Workflow` with Fan-Out + `JoinNode`

```python
from google.adk.agents.llm_agent import LlmAgent
from google.adk.workflow import Workflow, JoinNode

join = JoinNode(name="collect")

root_agent = Workflow(
    name="pipeline",
    edges=[
        ("START", (researcher_a, researcher_b, researcher_c)),  # Fan-out
        ((researcher_a, researcher_b, researcher_c), join),      # Fan-in
        (join, synthesizer),
    ],
)
```
**Important**: LLM agents feeding into `JoinNode` should use `output_schema` with JSON-serializable fields to avoid serialization issues with database session services.

---

## P4: `LoopAgent` $\rightarrow$ `Workflow` with Routed Edges (Cycle)

```python
from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.adk.workflow import Workflow

def check_quality(ctx: Context, node_input, draft: str) -> Event:
    iteration = ctx.state.get("_iteration_count", 0) + 1
    if iteration >= 5 or meets_quality_threshold(draft):
        return Event(data=draft, route="done", state={"_iteration_count": iteration})
    return Event(data=draft, route="continue", state={"_iteration_count": iteration})

root_agent = Workflow(
    name="refine_loop",
    edges=[
        ("START", refiner),
        (refiner, check_quality),
        (check_quality, refiner, "continue"),
        (check_quality, finalize, "done"),
    ],
)
```

---

## P5 & P9: Hierarchical `AgentTool` (ADK 1.x) or Coordinator `sub_agents` / Task Mode (ADK 2.x Basic) $\rightarrow$ Routed `Workflow` Graph

When an agent uses ADK 1.x `AgentTool(specialist)` (`P5`) or ADK 2.x Basic Orchestration `LlmAgent(sub_agents=[specialist_a, specialist_b])` (`P9a`), converting to an ADK 2.x `Workflow` graph replaces the open-ended coordinator LLM loop with a structured router + direct routed edges:

**Before (ADK 2.x Basic Coordinator Orchestration - P9a)**:
```python
from google.adk.workflow.agents.base_llm_agent import BaseLlmAgent
from google.adk.workflow.agents.llm_agent import LlmAgent

billing_agent = BaseLlmAgent(name="billing", mode="single_turn", ...)
support_agent = BaseLlmAgent(name="support", mode="single_turn", ...)

# Basic orchestration: LLM coordinator runs before AND after sub-agent invocation
root_agent = LlmAgent(
    name="coordinator",
    model="gemini-3.8-flash",
    sub_agents=[billing_agent, support_agent],
    instruction="Route user queries to billing or support.",
)
```

**After (ADK 2.x Graph Orchestration - `Workflow`)**:
```python
from enum import Enum
from pydantic import BaseModel
from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.workflow import Workflow

class RouteTarget(str, Enum):
    BILLING = "billing"
    SUPPORT = "support"

class RoutingDecision(BaseModel):
    target: RouteTarget

router_agent = LlmAgent(
    name="router_agent",
    model="gemini-3.8-flash",
    instruction="Classify whether the request belongs to billing or support.",
    output_schema=RoutingDecision,
    output_key="routing_decision",
)

def route_dispatcher(node_input, routing_decision: dict) -> Event:
    decision = RoutingDecision.model_validate(routing_decision)
    return Event(data=node_input, route=decision.target.value)

root_agent = Workflow(
    name="routed_coordinator_workflow",
    edges=[
        ("START", router_agent),
        (router_agent, route_dispatcher),
        (route_dispatcher, billing_agent, "billing"),
        (route_dispatcher, support_agent, "support"),
    ],
)
```
**Benefit**: Eliminates the redundant post-delegation coordinator LLM turn, enforces routing via a Pydantic schema, and allows inserting deterministic validation or database `@node`s before or after each specialist branch.

---

## Import Reference for ADK 2.x Graph Orchestration

```python
# Workflow graph primitives
from google.adk.workflow import Workflow, Edge, JoinNode
from google.adk.workflow.node import node  # @node or @node(parallel_worker=True)

# LLM agent node inside a Workflow graph
from google.adk.agents.llm_agent import LlmAgent

# Events and execution context
from google.adk.events.event import Event
from google.adk.agents.context import Context
```
