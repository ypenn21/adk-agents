# Feature Implementation Plan: adk2-graph-migration

## 📋 Todo Checklist
- [ ] Task 1: Upgrade/Verify ADK 2.0 dependencies (`google-adk>=2.0.0`) in `pyproject.toml` and create the parallel `adk_bug_ticket_agent_adk2/` package (or feature-flagged graph module `adk_bug_ticket_agent/workflow_graph.py`) per the `migrate-adk` side-by-side protocol.
- [ ] Task 2: Define Pydantic state, routing, and structured output schemas (`TicketIntent`, `TicketClassificationResult`, `TicketCreatePayload`, `TicketUpdatePayload`, `TicketSearchQuery`, `WorkflowState`) in `adk_bug_ticket_agent/schemas.py`.
- [ ] Task 3: Extract deterministic pre-processing and MCP database execution nodes (`enrich_session_context`, `pre_create_duplicate_check`, `execute_ticket_create`, `execute_ticket_update`, `execute_ticket_query`, `format_ticket_response`) in `adk_bug_ticket_agent/nodes.py`.
- [ ] Task 4: Define focused, single-responsibility `LlmAgent` nodes (`intent_router_agent`, `ticket_create_extractor_agent`, `ticket_update_extractor_agent`, `ticket_search_extractor_agent`, `external_web_research_agent`, `clarification_agent`) using `gemini-3.8-flash` in `adk_bug_ticket_agent/sub_agents.py`.
- [ ] Task 5: Assemble the ADK 2.0 `Workflow` graph (`bug_ticket_workflow`) with explicit `Edge` chains and conditional routing (`Event(route=...)`) in `adk_bug_ticket_agent/workflow_graph.py` and wire it into `ServiceManager` in `adk_bug_ticket_agent/agent.py`.
- [ ] Task 6: Write unit and integration tests for deterministic function nodes, routing edges, and workflow execution trajectories in `tests/test_adk2_workflow_graph.py`.

---

## 🔍 Analysis & Investigation

### Codebase Structure

| File | Physical Location | Current Responsibility |
| :--- | :--- | :--- |
| `agent.py` | `adk_bug_ticket_agent/agent.py` | Defines `ServiceManager` (singleton lazy-loader for `DatabaseSessionService`, `InMemoryMemoryService`, `root_agent`, and `A2aAgentExecutor`), A2A `agent_card`, and module-level `to_a2a` ASGI app. Instantiates a single monolithic `Agent` (`it_bug_assistant_agent`) with 12 tools attached. |
| `system_prompt.py` | `adk_bug_ticket_agent/system_prompt.py` | Holds `agent_instruction`, a monolithic 6-step procedural prompt instructing a single LLM to clarify requests, load memory, select among 12 tools, validate ticket parameters (`P0-P3`, `Open`), format markdown tables, and conclude. |
| `tools.py` | `adk_bug_ticket_agent/tools/tools.py` | Defines `get_current_date()` (deterministic Python function), `search_agent` + `search_tool` (`AgentTool` wrapping a secondary `Agent` using `google_search` on `gemini-3.7-flash`), and `LazyToolboxTool` / `get_toolbox_tools()` wrapping 9 synchronous/async PostgreSQL MCP Toolbox tools. |
| `views.py` | `adk_bug_ticket_agent/views.py` | Django async view `interact_with_agent(request)` handling `POST /agent/interact/`. Lazily resolves `_service_manager.session_service`, `_service_manager.root_agent`, and `_service_manager.memory_service`, runs `Runner.run_async`, and drains all events with `aclosing(events)`. |
| `agent_executor.py` | `adk_bug_ticket_agent/agent_executor.py` | Backwards-compatible wrapper `AdkAgentToA2AExecutor(A2aAgentExecutor)` for A2A protocol execution. |
| `tools.yaml` | `mcp-servers/mcp-toolbox/tools.yaml` | Configures the `tickets_toolset` backed by PostgreSQL (`tickets-db`) with 9 SQL tools: `search-tickets`, `get-ticket-by-id`, `get-tickets-by-assignee`, `get-tickets-by-status`, `get-tickets-by-priority`, `get-tickets-by-date-range`, `update-ticket-priority`, `update-ticket-status`, and `create-new-ticket`. |
| `test_agent_timeout_and_tools.py` | `tests/test_agent_timeout_and_tools.py` | Tests `LazyToolboxTool` pickling/timeout, `tools.yaml` FTS configuration, `interact_with_agent` event draining/timeout, and `ServiceManager` model fallback (`gemini-3.8-flash`). |
| `test_a2a_integration.py` | `tests/test_a2a_integration.py` | Tests A2A `agent_card` validity, `DJANGO=true` import isolation, and `AdkAgentToA2AExecutor`. |

---

### Current Architecture (ADK 1.x) & Non-Determinism Root Cause Analysis

Currently, `adk_bug_ticket_agent` implements a **Monolithic Single `LlmAgent` with 12 Tools (`P1b: Tool-heavy`) combined with Hierarchical Delegation via `AgentTool` (`P5a: Single delegation`)**:

```text
User Query (POST /agent/interact/)
  │
  ▼
Runner.run_async()
  │
  ▼
it_bug_assistant_agent (LlmAgent, model="gemini-3.8-flash")
  ├── Instruction: system_prompt.agent_instruction (6-step procedural prompt)
  ├── Built-in / Function Tools:
  │     ├── load_memory (ADK built-in memory lookup)
  │     └── get_current_date() -> {"current_date": "YYYY-MM-DD"} [Deterministic]
  ├── AgentTool Delegation (P5a):
  │     └── search_tool -> search_agent (LlmAgent, model="gemini-3.7-flash", tools=[google_search])
  └── MCP Toolbox SQL Tools (9 deterministic SQL queries wrapped in LazyToolboxTool):
        ├── search-tickets(query)
        ├── get-ticket-by-id(ticket_id)
        ├── get-tickets-by-assignee(assignee)
        ├── get-tickets-by-status(status)
        ├── get-tickets-by-priority(priority)
        ├── get-tickets-by-date-range(start_date, end_date, date_field)
        ├── update-ticket-priority(priority, ticket_id)
        ├── update-ticket-status(status, ticket_id)
        └── create-new-ticket(title, description, assignee, priority, status)
```

#### Why the Monolithic P1 + P5a Architecture Suffers from Non-Determinism

1. **Prompt-Driven Procedural Control Flow**: `system_prompt.py` embeds a 6-step state machine (`1. Clarify -> 2. Remember -> 3. Select Tools -> 4. Validate Parameters -> 5. Execute & Report -> 6. Conclude`) inside natural-language instructions. The LLM alone decides whether to call `get_current_date` before `get-tickets-by-date-range`, whether to check for duplicate tickets via `search-tickets` before calling `create-new-ticket`, and whether to invoke `load_memory`.
2. **Unnecessary Tool-Call Round-Trips for Deterministic Context**: Every date-relative query (e.g., *"Show tickets created this week"*) requires an extra LLM tool-call turn just to invoke `get_current_date()`, burning ~450–600 tokens and ~0.8–1.5s of latency for a `datetime.now().strftime("%Y-%m-%d")` string that can be deterministically injected in <1ms at workflow entry.
3. **Unenforced Pre-Creation Duplicate Check & Parameter Validation**: The prompt states *"For new tickets, ensure Title and Description are distinct, and set Priority (P0-P3) and a default 'Open' status"* and mentions `search-tickets` similarity, but nothing in the execution graph enforces that `search-tickets` runs *before* `create-new-ticket`, nor does a Pydantic schema enforce valid enum values (`'P0 - Critical'`, `'P1 - High'`, `'P2 - Medium'`, `'P3 - Low'` and `'Open'`, `'In Progress'`, `'Closed'`, `'Resolved'`) before hitting PostgreSQL.
4. **Tool Selection Confusion Across 12 Attached Tools**: Presenting 12 overlapping tools simultaneously to a single `LlmAgent` causes non-deterministic tool selection (e.g., calling `search-tickets` instead of `get-tickets-by-status`, or calling `search_agent` for internal bugs).
5. **Non-Deterministic Output Formatting**: Markdown table formatting for multi-row SQL results is left to the LLM instead of a deterministic post-processing function node, resulting in inconsistent column ordering and extra output generation latency.

---

### 📊 ADK 1.x to 2.0 Migration Assessment & Scoring Breakdown (`migrate-adk` Rubric)

Following the `migrate-adk` skill rubric (`examples/scoring-rubric.md` and `resources/migration-report-template.md`):

#### Executive Summary

| Metric | Value |
| :--- | :--- |
| **Total agents discovered** | 2 (`it_bug_assistant_agent`, `search_agent`) |
| **LLM agents (`Agent` / `LlmAgent`)** | 2 |
| **Workflow agents (`Sequential`/`Parallel`/`Loop`)** | 0 (implicit workflow embedded in `system_prompt.py`) |
| **Custom agents (`BaseAgent` subclasses)** | 0 |
| **Callbacks detected** | 0 |
| **Deterministic tools (migration candidates)** | 10 (`get_current_date` + 9 MCP Toolbox SQL CRUD/query tools) |
| **State keys in data flow** | 0 explicit (all implicit in conversation history; 7 explicit state keys proposed in ADK 2.0) |
| **Overall Migration Score** | **STRONG (4.0 / 4.0)** |

**Recommendation:** **Migrate to ADK 2.0 `Workflow` Graph** — decomposing the overloaded 12-tool monolithic agent into deterministic function `@node`s, a Pydantic-typed intent router, and specialized task branches eliminates 1–2 LLM round-trips per request (~600–1,200 tokens and ~1.2–2.5s latency saved) while guaranteeing deterministic date injection, pre-create duplicate detection, strict enum validation, and consistent Markdown table formatting.

#### Per-Agent & Pattern Analysis

| Agent / Component | Type | Pattern ID | Current Model | Tools | Callbacks | `output_key` | Migration Score | Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `it_bug_assistant_agent` | `Agent` (`LlmAgent`) | **P1b** (Tool-heavy Single Agent) + implicit multi-branch routing | `gemini-3.8-flash` (` LiteLlm` in Vertex/GKE modes) | 12 (`load_memory`, `get_current_date`, `search_tool`, 9 MCP SQL tools) | 0 | None | **STRONG (4.0)** | 10 of 12 tools are deterministic (`get_current_date` + 9 parameterized SQL queries). Implicit multi-step procedure in prompt maps directly to ADK 2.0 `Workflow` with function nodes and routed edges. |
| `search_agent` (wrapped in `search_tool`) | `AgentTool(Agent)` | **P5a** (Hierarchical Single Delegation) | `gemini-3.7-flash` | 1 (`google_search`) | 0 | None | **MODERATE (3.0)** | Autonomous single-turn web search specialist; becomes a dedicated routed branch node in the `Workflow` graph (invoked only when route is `EXTERNAL_WEB_SEARCH` or when internal DB search returns 0 results), eliminating the nested `AgentTool` wrapper overhead. |

#### Transparent Score Math Breakdown

```text
1. it_bug_assistant_agent (Pattern P1b: Tool-heavy Single LlmAgent):
   Base score: 3.0 (P1b: Tool-heavy default = 3 MODERATE)
   + Upgrade condition (3+ deterministic tools: get_current_date + 9 SQL tools): +1.0 -> 4.0 (STRONG)
   + Deterministic tool signal (10 deterministic tools * +0.5, capped at rubric max 4.0): +1.0
   + Testing/determinism modifier (explicit user requirement to improve determinism & unit testability): +0.5
   = Final Score: 4.0 -> STRONG

2. search_agent via AgentTool (Pattern P5a: Single Delegation):
   Base score: 2.0 (P5a: Single delegation default = 2 LOW)
   + Upgrade condition (Child is autonomous single-turn web search specialist, no multi-turn user interaction needed): +1.0 -> 3.0 (MODERATE)
   = Final Score: 3.0 -> MODERATE

Overall Codebase Migration Score:
   Rule: "If ANY pattern scores 4 (STRONG) -> overall is STRONG"
   = Overall Score: STRONG (4.0)
```

#### What Stays the Same
- **Models**: `DEFAULT_MODEL_NAME = "gemini-3.8-flash"` for primary reasoning/routing/extraction nodes and `gemini-3.7-flash` (or `gemini-3.8-flash`) for external web search, plus full preservation of `AgentMode.GEMINI`, `AgentMode.VERTEXAI`, and `AgentMode.GKE` `LiteLlm` model resolution inside `ServiceManager`.
- **MCP Toolbox Infrastructure**: `LazyToolboxTool`, `get_toolbox_tools()`, `load_toolset_cached()`, and `mcp-servers/mcp-toolbox/tools.yaml` remain 100% intact, preserving picklability and timeout protection (`TOOLBOX_TIMEOUT = 30.0s`).
- **Django Web UI & A2A Integration**: `views.py` (`interact_with_agent`), `agent_executor.py` (`AdkAgentToA2AExecutor`), `DatabaseSessionService` (`NullPool`), and `agent_card` remain backwards-compatible because ADK 2.0 `Workflow` is executable by `Runner.run_async()`.
- **Core Business Domain Rules**: Priority levels (`P0 - Critical` to `P3 - Low`), Status values (`Open`, `In Progress`, `Closed`, `Resolved`), cosine/FTS duplicate checks, and Markdown table reporting are preserved and upgraded from soft prompt suggestions to hard code invariants.

#### Quantified Migration Benefits

1. **Deterministic Context Enrichment (`get_current_date` -> Entry Function Node)**:
   - *Before (ADK 1.x)*: `get_current_date` is registered as an LLM tool. The model must decide to emit a `function_call: get_current_date()`, wait for execution, and run a second LLM inference turn to compute `start_date`/`end_date`.
   - *After (ADK 2.0)*: `enrich_session_context` runs as the first deterministic function node (`"START" -> enrich_session_context`), injecting `current_date` (`YYYY-MM-DD`) directly into `ctx.state` before any LLM call.
   - *Estimated Savings*: **~450–600 tokens and ~0.8–1.2s latency saved** on every date-aware request; **100% determinism** (the model never hallucinates the year or forgets to call `get_current_date`).

2. **Structured Intent Classification & Conditional Graph Routing (`Route` / Routed `Edge`s)**:
   - *Before (ADK 1.x)*: One LLM agent inspects 12 tools simultaneously and decides ad-hoc what to do.
   - *After (ADK 2.0)*: `intent_router_agent` uses `output_schema=TicketClassificationResult` to classify the user's request into a strict `TicketIntent` enum (`CREATE_TICKET`, `UPDATE_TICKET`, `SEARCH_TICKETS`, `EXTERNAL_SEARCH`, `CLARIFY`), and a deterministic router function `route_by_intent` emits `Event(route=...)` to activate *only* the relevant subgraph.
   - *Estimated Savings*: **~800–1,100 input tokens saved per turn** by not sending 12 tool declarations to every LLM call; **zero cross-tool hallucination** (e.g., an update request cannot accidentally invoke `create-new-ticket`).

3. **Guaranteed Pre-Creation Duplicate Check & Deterministic SQL Execution**:
   - *Before (ADK 1.x)*: When asked to create a ticket, the LLM frequently calls `create-new-ticket` immediately without checking `search-tickets` first, or passes invalid priority strings (e.g. `"High"` instead of `"P1 - High"`).
   - *After (ADK 2.0)*: In the `CREATE_TICKET` branch, `ticket_create_extractor_agent` extracts a validated `TicketCreatePayload` (enforcing `TicketPriority` and `TicketStatus` Pydantic enums and `title != description`), followed by a deterministic function node `pre_create_duplicate_check_and_insert` that calls `search-tickets` first and only executes `create-new-ticket` if no exact/high-similarity duplicate blocks creation (or attaches duplicate warnings deterministically).
   - *Estimated Savings*: **~500–700 tokens and ~1.0–1.5s latency saved** by executing the duplicate check and SQL insert inside a deterministic Python function node rather than chaining multiple LLM tool-call round-trips.

4. **Deterministic Markdown Table Post-Processing**:
   - *Before (ADK 1.x)*: Raw JSON/dict rows from MCP Toolbox are fed back into the LLM to synthesize a Markdown table token-by-token.
   - *After (ADK 2.0)*: The deterministic node `format_ticket_response` formats multi-ticket query results into a standardized Markdown table in <1ms without an extra LLM generation pass when structured rows are returned.

#### Key Change (Before vs. After Snippet)

```python
# BEFORE (ADK 1.x - adk_bug_ticket_agent/agent.py)
return Agent(
    model=MODEL_NAME,
    name="it_bug_assistant_agent",
    description="An agent to help users with bug tickets, including searching, creating, and updating them.",
    instruction=system_prompt.agent_instruction,
    tools=[load_memory, get_current_date, search_tool, *get_toolbox_tools()],
)
```

```python
# AFTER (ADK 2.0 - adk_bug_ticket_agent/workflow_graph.py)
root_agent = Workflow(
    name="it_bug_assistant_agent",
    description="An agent to help users with bug tickets, including searching, creating, and updating them.",
    edges=[
        ("START", enrich_session_context),
        (enrich_session_context, intent_router_agent),
        (intent_router_agent, dispatch_intent_route),
        (dispatch_intent_route, create_ticket_extractor_agent, "create"),
        (create_ticket_extractor_agent, execute_create_with_dedup),
        (execute_create_with_dedup, format_final_response),
        (dispatch_intent_route, update_ticket_extractor_agent, "update"),
        (update_ticket_extractor_agent, execute_ticket_update),
        (execute_ticket_update, format_final_response),
        (dispatch_intent_route, search_ticket_extractor_agent, "search"),
        (search_ticket_extractor_agent, execute_ticket_query),
        (execute_ticket_query, external_web_search_agent, "fallback_web_search"),
        (execute_ticket_query, format_final_response, "has_results"),
        (dispatch_intent_route, external_web_search_agent, "external_search"),
        (external_web_search_agent, format_final_response),
        (dispatch_intent_route, clarification_agent, "clarify"),
    ],
)
```

#### What ADK 2.0 Unlocks Next
- **Human-in-the-Loop (HITL) Approval Gates (`RequestInput`)**: Before executing a `P0 - Critical` priority escalation or closing a production ticket, the graph can pause at a confirmation node and resume cleanly upon user approval.
- **Parallel Fan-Out/Fan-In (`JoinNode`) for Hybrid Triage**: On complex bug reports (e.g., stack traces mentioning CVEs or third-party libraries), the workflow can fan out concurrently to `execute_ticket_query` (internal PostgreSQL FTS/vector search) and `external_web_search_agent` (Google Search for CVEs) and merge both via `JoinNode` into a unified triage synthesis.
- **Deterministic Retry/Self-Healing Loops**: If an MCP Toolbox query times out or returns a transient connection error, a routed edge cycle can retry with exponential backoff deterministically without invoking the LLM.

#### Migration Risks & Mitigations

| Risk | Severity | Mitigation |
| :--- | :--- | :--- |
| **ADK Version Compatibility in Environment (`google-adk` 1.x vs 2.0)** | **HIGH** | `pyproject.toml` currently pins `google-adk[db]>=1.39.1`. Provide a compatibility layer in `workflow_graph.py` that uses `google.adk.workflow` (`Workflow`, `Edge`, `@node`, `Event`) when ADK 2.0 is installed, or falls back / provides an explicit `Workflow` shim for incremental validation so existing pytest suites never break during transition. |
| **DatabaseSessionService JSON Serialization of `output_schema` State** | **MEDIUM** | When `LlmAgent` uses `output_schema` (Pydantic `BaseModel`), ADK stores the structured result in `ctx.state[output_key]`. Ensure all Pydantic models use JSON-serializable primitives (`str`, `int`, `float`, `bool`, `list`, `dict`, `str`-based `Enum`) so `DatabaseSessionService` (`postgresql+asyncpg`) serializes session state cleanly. |
| **Vertex AI / Cloud Run Pickling & Lazy Loading** | **MEDIUM** | Never import Django modules inside `agent.py`, `workflow_graph.py`, `nodes.py`, or `schemas.py`. Access MCP Toolbox tools inside deterministic function nodes exclusively via `get_toolbox_tool_by_name(name)` wrapping `get_toolbox_tools()` lazily at call time, never at module import time. |
| **`Runner.run_async` Final Response Event Detection in `views.py`** | **LOW** | `views.py` inspects `if event.is_final_response():` and reads `event.content.parts[0].text`. Ensure terminal nodes in the `Workflow` return either `str` or `Event` with populated text content so `Runner.run_async` emits a standard final response event compatible with `views.py`. |

---

### Dependencies & Integration Points
1. **Google ADK (`google-adk`)**:
   - ADK 2.0 Graph primitives: `Workflow`, `Edge`, `JoinNode` (`from google.adk.workflow import Workflow, Edge, JoinNode`), `@node` (`from google.adk.workflow.node import node`), `LlmAgent` (`from google.adk.agents.llm_agent import LlmAgent`), `Event` (`from google.adk.events.event import Event`), `Context` (`from google.adk.agents.context import Context`).
   - Built-in tools: `load_memory` (`from google.adk.tools import load_memory`), `google_search` (`from google.adk.tools import google_search`).
2. **Pydantic (`pydantic>=2.0`)**:
   - Used for strict state contracts, routing decisions (`TicketClassificationResult`), and tool payload extraction (`TicketCreatePayload`, `TicketUpdatePayload`, `TicketSearchQuery`).
3. **MCP Toolbox (`toolbox-core==0.5.2`)**:
   - Accessed lazily via `LazyToolboxTool` instances from `adk_bug_ticket_agent/tools/tools.py` (`search-tickets`, `get-ticket-by-id`, `get-tickets-by-assignee`, `get-tickets-by-status`, `get-tickets-by-priority`, `get-tickets-by-date-range`, `update-ticket-priority`, `update-ticket-status`, `create-new-ticket`).
4. **LiteLlm (`litellm>=1.81.4`)**:
   - Supports `AgentMode.GEMINI` (`gemini-3.8-flash`), `AgentMode.VERTEXAI` (`LiteLlm(model=f"vertex_ai/openai/{endpoint_id}")`), and `AgentMode.GKE` (`LiteLlm(model=MODEL_NAME, api_base=api_base_url)`).

---

### Considerations & Challenges
1. **Strict Separation Between Django and ADK**:
   - Per project rules, no Django ORM or `django.*` imports may appear in `adk_bug_ticket_agent/agent.py`, `schemas.py`, `nodes.py`, `sub_agents.py`, or `workflow_graph.py`.
2. **Zero Network Calls at Import Time (`collectstatic` & Unit Tests)**:
   - `get_toolbox_tools()` connects to `http://127.0.0.1:5000` when invoked. In the ADK 2.0 design, deterministic function nodes (`execute_create_with_dedup`, `execute_ticket_update`, `execute_ticket_query`) look up the required `LazyToolboxTool` **at node execution time**, meaning constructing the `Workflow` graph makes **zero** network calls to MCP Toolbox at startup or during `python manage.py collectstatic`.
3. **Preserving `ServiceManager` Public Contract**:
   - `views.py`, `agent_executor.py`, `test_agent_timeout_and_tools.py`, and `test_a2a_integration.py` rely on `ServiceManager`, `_service_manager.root_agent`, `sm._init_agent()`, and `agent.model`. Ensure `ServiceManager` exposes `build_workflow_agent(model)` and preserves `.model` attribute inspection (or supports toggling/inspecting the root workflow and its underlying model) so all existing unit tests in `tests/test_agent_timeout_and_tools.py` and `tests/test_a2a_integration.py` continue to pass.

---

## 📐 Technical Specification & Design

### Component Architecture

The monolithic `it_bug_assistant_agent` is decomposed into a modular 4-layer architecture inside `adk_bug_ticket_agent/` (and mirrored in `adk_bug_ticket_agent_adk2/` per `migrate-adk` skill convention):

1. **`adk_bug_ticket_agent/schemas.py` (Typed State & Routing Contracts)**:
   - Defines `str`-backed `Enum`s (`TicketIntent`, `TicketPriority`, `TicketStatus`, `TicketQueryMode`, `DateFilterField`) and Pydantic `BaseModel` schemas (`TicketClassificationResult`, `TicketCreatePayload`, `TicketUpdatePayload`, `TicketSearchQuery`) with field validators that normalize inputs (e.g., mapping `"P1"` -> `"P1 - High"`, verifying `title.strip().lower() != description.strip().lower()`).
2. **`adk_bug_ticket_agent/nodes.py` (Deterministic Function `@node`s)**:
   - **`enrich_session_context`**: Runs at `"START"`. Injects `current_date` (`YYYY-MM-DD`) and initializes default state keys in `ctx.state` via `Event(data=..., state={...})`.
   - **`dispatch_intent_route`**: Reads `intent_classification` from `ctx.state`, validates completeness, and emits `Event(data=..., route=...)` (`"create"`, `"update"`, `"search"`, `"external_search"`, or `"clarify"`).
   - **`execute_create_with_dedup`**: Deterministically runs MCP `search-tickets(query=payload.title)` first. If a high-confidence duplicate is found (exact title match or distance <= 0.3 / rank >= threshold), records duplicate metadata; otherwise (or alongside warning) executes `create-new-ticket` with validated enum values (`priority`, `status="Open"`) and stores `db_operation_result` in `ctx.state`.
   - **`execute_ticket_update`**: Deterministically executes `update-ticket-status` and/or `update-ticket-priority` via MCP Toolbox based on `TicketUpdatePayload`, then fetches the updated ticket via `get-ticket-by-id` to confirm the state transition.
   - **`execute_ticket_query`**: Deterministically dispatches to the exact MCP Toolbox SQL tool matching `TicketSearchQuery.query_mode` (`BY_ID` -> `get-ticket-by-id`, `BY_ASSIGNEE` -> `get-tickets-by-assignee`, `BY_STATUS` -> `get-tickets-by-status`, `BY_PRIORITY` -> `get-tickets-by-priority`, `BY_DATE_RANGE` -> `get-tickets-by-date-range`, `SEMANTIC_SEARCH` -> `search-tickets`). Emits `route="fallback_web_search"` if `allow_web_fallback` is true and 0 internal tickets matched, else `route="has_results"`.
   - **`format_final_response`**: Deterministically formats ticket lists into a clean Markdown table (`| Ticket ID | Title | Priority | Status | Assignee |`) and appends a polite closing prompt, avoiding an extra LLM call.
3. **`adk_bug_ticket_agent/sub_agents.py` (Focused `LlmAgent` Nodes)**:
   - **`intent_router_agent`**: Uses `gemini-3.8-flash`, `tools=[load_memory]`, and `output_schema=TicketClassificationResult` (`output_key="intent_classification"`).
   - **`create_ticket_extractor_agent`**: Uses `gemini-3.8-flash` and `output_schema=TicketCreatePayload` (`output_key="create_payload"`).
   - **`update_ticket_extractor_agent`**: Uses `gemini-3.8-flash` and `output_schema=TicketUpdatePayload` (`output_key="update_payload"`).
   - **`search_ticket_extractor_agent`**: Uses `gemini-3.8-flash` (reading `{current_date}` from state) and `output_schema=TicketSearchQuery` (`output_key="search_query"`).
   - **`external_web_search_agent`**: Uses `gemini-3.8-flash` with `tools=[google_search]` (`output_key="web_search_result"`), replacing the nested `AgentTool(search_agent)`.
   - **`clarification_agent`**: Uses `gemini-3.8-flash` (`output_key="clarification_response"`) to ask concise clarifying questions when user input is ambiguous or missing required parameters (e.g., missing `ticket_id` on an update request).
4. **`adk_bug_ticket_agent/workflow_graph.py` (ADK 2.0 `Workflow` Builder)**:
   - Factory function `build_bug_ticket_workflow(model: Any = "gemini-3.8-flash") -> Workflow` assembling all nodes, edges, and routes into a cohesive graph.

---

### Mermaid Diagram

```mermaid
flowchart TD
    Start(["START (User Message)"]) --> Enrich["[fn] enrich_session_context<br/>Injects current_date (YYYY-MM-DD) & user_query into ctx.state"]
    Enrich --> RouterLLM["[llm] intent_router_agent (gemini-3.8-flash)<br/>tools=[load_memory]<br/>output_schema=TicketClassificationResult<br/>output_key='intent_classification'"]
    RouterLLM --> Dispatch["[fn] dispatch_intent_route<br/>Evaluates intent_classification & required fields"]

    Dispatch -- "route = 'clarify'" --> ClarifyLLM["[llm] clarification_agent (gemini-3.8-flash)<br/>Asks user for missing ticket_id / details"]
    ClarifyLLM --> EndNode(["END (Final Response)"])

    Dispatch -- "route = 'create'" --> CreateExtractLLM["[llm] create_ticket_extractor_agent (gemini-3.8-flash)<br/>output_schema=TicketCreatePayload<br/>output_key='create_payload'"]
    CreateExtractLLM --> ExecCreate["[fn] execute_create_with_dedup<br/>1. Calls MCP 'search-tickets' for duplicates<br/>2. Calls MCP 'create-new-ticket' if unique<br/>state={'db_operation_result': ...}"]
    ExecCreate --> FormatNode["[fn] format_final_response<br/>Deterministic Markdown Table & Summary Formatter"]

    Dispatch -- "route = 'update'" --> UpdateExtractLLM["[llm] update_ticket_extractor_agent (gemini-3.8-flash)<br/>output_schema=TicketUpdatePayload<br/>output_key='update_payload'"]
    UpdateExtractLLM --> ExecUpdate["[fn] execute_ticket_update<br/>1. Calls MCP 'update-ticket-status' / 'update-ticket-priority'<br/>2. Calls MCP 'get-ticket-by-id' to verify<br/>state={'db_operation_result': ...}"]
    ExecUpdate --> FormatNode

    Dispatch -- "route = 'search'" --> SearchExtractLLM["[llm] search_ticket_extractor_agent (gemini-3.8-flash)<br/>Reads {current_date} from state<br/>output_schema=TicketSearchQuery<br/>output_key='search_query'"]
    SearchExtractLLM --> ExecSearch["[fn] execute_ticket_query<br/>Dispatches exact MCP SQL tool:<br/>get-ticket-by-id | get-tickets-by-status |<br/>get-tickets-by-priority | get-tickets-by-assignee |<br/>get-tickets-by-date-range | search-tickets"]

    ExecSearch -- "route = 'has_results'" --> FormatNode
    ExecSearch -- "route = 'fallback_web_search'" --> WebSearchLLM["[llm] external_web_search_agent (gemini-3.8-flash)<br/>tools=[google_search]<br/>output_key='web_search_result'"]

    Dispatch -- "route = 'external_search'" --> WebSearchLLM
    WebSearchLLM --> FormatNode
    FormatNode --> EndNode
```

---

### Schemas & Models (`adk_bug_ticket_agent/schemas.py`)

```python
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class TicketIntent(str, Enum):
    """Supported top-level intents for the Bug Ticket Workflow."""
    CREATE_TICKET = "create"
    UPDATE_TICKET = "update"
    SEARCH_TICKETS = "search"
    EXTERNAL_SEARCH = "external_search"
    CLARIFY = "clarify"


class TicketPriority(str, Enum):
    """Canonical ticket priorities enforced by PostgreSQL / MCP Toolbox."""
    P0 = "P0 - Critical"
    P1 = "P1 - High"
    P2 = "P2 - Medium"
    P3 = "P3 - Low"


class TicketStatus(str, Enum):
    """Canonical ticket statuses enforced by PostgreSQL / MCP Toolbox."""
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    CLOSED = "Closed"
    RESOLVED = "Resolved"


class TicketQueryMode(str, Enum):
    """Deterministic dispatch target for ticket retrieval operations."""
    BY_ID = "by_id"
    BY_ASSIGNEE = "by_assignee"
    BY_STATUS = "by_status"
    BY_PRIORITY = "by_priority"
    BY_DATE_RANGE = "by_date_range"
    SEMANTIC_SEARCH = "semantic_search"


class DateFilterField(str, Enum):
    """Allowed date columns in tools.yaml get-tickets-by-date-range."""
    CREATION_TIME = "creation_time"
    UPDATED_TIME = "updated_time"


def normalize_priority(value: Optional[str]) -> Optional[TicketPriority]:
    """Deterministically normalizes shorthand priority inputs (e.g. 'P0', 'Critical') to canonical enum."""
    if value is None:
        return None
    cleaned = value.strip().upper()
    mapping = {
        "P0": TicketPriority.P0,
        "CRITICAL": TicketPriority.P0,
        "P0 - CRITICAL": TicketPriority.P0,
        "P1": TicketPriority.P1,
        "HIGH": TicketPriority.P1,
        "P1 - HIGH": TicketPriority.P1,
        "P2": TicketPriority.P2,
        "MEDIUM": TicketPriority.P2,
        "P2 - MEDIUM": TicketPriority.P2,
        "P3": TicketPriority.P3,
        "LOW": TicketPriority.P3,
        "P3 - LOW": TicketPriority.P3,
    }
    if cleaned in mapping:
        return mapping[cleaned]
    return TicketPriority(value)


def normalize_status(value: Optional[str]) -> Optional[TicketStatus]:
    """Deterministically normalizes status strings to canonical TicketStatus enum."""
    if value is None:
        return None
    cleaned = value.strip().lower()
    mapping = {
        "open": TicketStatus.OPEN,
        "in progress": TicketStatus.IN_PROGRESS,
        "in_progress": TicketStatus.IN_PROGRESS,
        "in-progress": TicketStatus.IN_PROGRESS,
        "closed": TicketStatus.CLOSED,
        "resolved": TicketStatus.RESOLVED,
    }
    if cleaned in mapping:
        return mapping[cleaned]
    return TicketStatus(value)


class TicketClassificationResult(BaseModel):
    """Structured output produced by intent_router_agent."""
    intent: TicketIntent = Field(
        description="The primary intent classified from the user's message and conversation memory."
    )
    reasoning: str = Field(
        description="Brief explanation of why this intent route was selected."
    )
    missing_information: Optional[str] = Field(
        default=None,
        description="If intent is 'clarify', specify what required details are missing from the user's request."
    )


class TicketCreatePayload(BaseModel):
    """Validated schema for creating a new bug ticket."""
    title: str = Field(min_length=3, description="Concise, distinct title of the bug ticket.")
    description: str = Field(min_length=5, description="Detailed description of the software bug or issue.")
    assignee: Optional[str] = Field(default=None, description="Optional assignee email address.")
    priority: TicketPriority = Field(
        default=TicketPriority.P3,
        description="Ticket priority ('P0 - Critical', 'P1 - High', 'P2 - Medium', 'P3 - Low')."
    )
    status: TicketStatus = Field(
        default=TicketStatus.OPEN,
        description="Initial status of the new ticket. Defaults to 'Open'."
    )
    skip_duplicate_check: bool = Field(
        default=False,
        description="Set to True only if the user explicitly confirmed creating the ticket despite duplicates."
    )

    @field_validator("priority", mode="before")
    @classmethod
    def _validate_priority(cls, v: Any) -> TicketPriority:
        return normalize_priority(v) or TicketPriority.P3

    @field_validator("status", mode="before")
    @classmethod
    def _validate_status(cls, v: Any) -> TicketStatus:
        return normalize_status(v) or TicketStatus.OPEN

    @model_validator(mode="after")
    def _ensure_title_and_description_distinct(self) -> "TicketCreatePayload":
        if self.title.strip().lower() == self.description.strip().lower():
            self.description = f"{self.description.strip()} (Reported issue details pending further triage)"
        return self


class TicketUpdatePayload(BaseModel):
    """Validated schema for updating an existing ticket's status and/or priority."""
    ticket_id: str = Field(min_length=1, description="The unique ID of the ticket to update.")
    new_status: Optional[TicketStatus] = Field(
        default=None,
        description="Optional new status ('Open', 'In Progress', 'Closed', 'Resolved')."
    )
    new_priority: Optional[TicketPriority] = Field(
        default=None,
        description="Optional new priority ('P0 - Critical', 'P1 - High', 'P2 - Medium', 'P3 - Low')."
    )

    @field_validator("new_priority", mode="before")
    @classmethod
    def _validate_new_priority(cls, v: Any) -> Optional[TicketPriority]:
        return normalize_priority(v) if v else None

    @field_validator("new_status", mode="before")
    @classmethod
    def _validate_new_status(cls, v: Any) -> Optional[TicketStatus]:
        return normalize_status(v) if v else None


class TicketSearchQuery(BaseModel):
    """Validated schema for querying internal bug tickets via MCP Toolbox."""
    query_mode: TicketQueryMode = Field(
        description="Which specific lookup method to use based on the user's filter criteria."
    )
    ticket_id: Optional[str] = Field(default=None, description="Ticket ID when query_mode is 'by_id'.")
    assignee: Optional[str] = Field(default=None, description="Assignee email/name when query_mode is 'by_assignee'.")
    status: Optional[TicketStatus] = Field(default=None, description="Status filter when query_mode is 'by_status'.")
    priority: Optional[TicketPriority] = Field(default=None, description="Priority filter when query_mode is 'by_priority'.")
    start_date: Optional[str] = Field(default=None, description="Start date YYYY-MM-DD when query_mode is 'by_date_range'.")
    end_date: Optional[str] = Field(default=None, description="End date YYYY-MM-DD when query_mode is 'by_date_range'.")
    date_field: DateFilterField = Field(
        default=DateFilterField.CREATION_TIME,
        description="Date column ('creation_time' or 'updated_time') for date range queries."
    )
    search_text: Optional[str] = Field(
        default=None,
        description="Search keywords or issue description when query_mode is 'semantic_search'."
    )
    allow_web_fallback: bool = Field(
        default=False,
        description="True if external web search (CVEs, docs) should run when internal DB returns 0 results."
    )

    @field_validator("priority", mode="before")
    @classmethod
    def _validate_priority(cls, v: Any) -> Optional[TicketPriority]:
        return normalize_priority(v) if v else None

    @field_validator("status", mode="before")
    @classmethod
    def _validate_status(cls, v: Any) -> Optional[TicketStatus]:
        return normalize_status(v) if v else None
```

---

### API & Code Signatures

#### 1. Tool Lookup Helper (`adk_bug_ticket_agent/tools/tools.py`)
Add a deterministic lookup function in `adk_bug_ticket_agent/tools/tools.py` so function nodes can invoke individual MCP tools by name lazily without LLM tool-calling overhead:

```python
def get_toolbox_tool_by_name(tool_name: str) -> LazyToolboxTool | None:
    """
    Lazily retrieves a specific LazyToolboxTool by its MCP tool name (e.g., 'search-tickets').
    Returns None if the MCP Toolbox server is unreachable or tool is not found.
    """
    tools = get_toolbox_tools()
    for tool in tools:
        if getattr(tool, "__name__", None) == tool_name or getattr(tool, "name", None) == tool_name:
            return tool
    return None
```

#### 2. Deterministic Function Nodes (`adk_bug_ticket_agent/nodes.py`)

```python
from datetime import datetime
from typing import Any
from google.adk.events.event import Event
from google.adk.agents.context import Context

def enrich_session_context(node_input: Any) -> Event:
    """
    Migrated from: get_current_date() tool call.
    Runs deterministically at workflow START with zero LLM cost.
    Injects 'current_date' (YYYY-MM-DD) and 'user_query' into workflow state.
    """
    ...

def dispatch_intent_route(node_input: Any, intent_classification: dict[str, Any] | Any = None) -> Event:
    """
    Deterministic router node. Evaluates the structured output from intent_router_agent
    and returns Event(data=..., route=<route_name>) matching the Workflow edges:
    'create', 'update', 'search', 'external_search', or 'clarify'.
    """
    ...

def execute_create_with_dedup(node_input: Any, create_payload: dict[str, Any] | Any = None) -> Event:
    """
    Deterministic ticket creation pipeline:
    1. Validates create_payload via TicketCreatePayload.
    2. Invokes MCP 'search-tickets' with payload.title to check for existing duplicates.
    3. If exact title duplicate exists and not skip_duplicate_check, halts creation and returns duplicate warning.
    4. Otherwise invokes MCP 'create-new-ticket' and stores result in state['db_operation_result'].
    """
    ...

def execute_ticket_update(node_input: Any, update_payload: dict[str, Any] | Any = None) -> Event:
    """
    Deterministic ticket update pipeline:
    1. Validates update_payload via TicketUpdatePayload.
    2. Calls 'update-ticket-status' if new_status is provided.
    3. Calls 'update-ticket-priority' if new_priority is provided.
    4. Calls 'get-ticket-by-id' to fetch updated record and stores in state['db_operation_result'].
    """
    ...

def execute_ticket_query(node_input: Any, search_query: dict[str, Any] | Any = None) -> Event:
    """
    Deterministic SQL tool dispatcher:
    Maps TicketSearchQuery.query_mode to the exact MCP Toolbox tool:
      - BY_ID -> 'get-ticket-by-id'
      - BY_ASSIGNEE -> 'get-tickets-by-assignee'
      - BY_STATUS -> 'get-tickets-by-status'
      - BY_PRIORITY -> 'get-tickets-by-priority'
      - BY_DATE_RANGE -> 'get-tickets-by-date-range'
      - SEMANTIC_SEARCH -> 'search-tickets'
    Routes to 'fallback_web_search' if results are empty and allow_web_fallback=True,
    otherwise routes to 'has_results'.
    """
    ...

def format_final_response(
    node_input: Any,
    db_operation_result: dict[str, Any] | None = None,
    web_search_result: Any = None,
) -> str:
    """
    Deterministic post-processor that formats single or multiple bug tickets into
    a consistent Markdown table, formats code/timestamps, and appends a conclusion prompt.
    """
    ...
```

#### 3. Focused `LlmAgent` Builders (`adk_bug_ticket_agent/sub_agents.py`)

```python
from typing import Any
from google.adk.agents.llm_agent import LlmAgent

def create_intent_router_agent(model: Any) -> LlmAgent: ...
def create_ticket_create_extractor_agent(model: Any) -> LlmAgent: ...
def create_ticket_update_extractor_agent(model: Any) -> LlmAgent: ...
def create_ticket_search_extractor_agent(model: Any) -> LlmAgent: ...
def create_external_web_search_agent(model: Any) -> LlmAgent: ...
def create_clarification_agent(model: Any) -> LlmAgent: ...
```

#### 4. ADK 2.0 Workflow Graph Factory (`adk_bug_ticket_agent/workflow_graph.py`)

```python
from typing import Any
from . import system_prompt

def build_bug_ticket_workflow(model: Any = "gemini-3.8-flash") -> Any:
    """
    Constructs the ADK 2.0 Workflow graph for the IT Bug Assistant Agent.
    Preserves compatibility with ServiceManager, Runner.run_async, and A2A executor.
    """
    ...
```

---

## 📝 Step-by-Step Implementation Steps

### Step 1: Create Structured Pydantic Schemas for Routing, State, and Tool Validation
- **Files to create**: `adk_bug_ticket_agent/schemas.py`
- **Changes needed**:
  Create `adk_bug_ticket_agent/schemas.py` containing all enums (`TicketIntent`, `TicketPriority`, `TicketStatus`, `TicketQueryMode`, `DateFilterField`), normalization helpers (`normalize_priority`, `normalize_status`), and Pydantic models (`TicketClassificationResult`, `TicketCreatePayload`, `TicketUpdatePayload`, `TicketSearchQuery`).
- **Implementation Notes**:
  - Inherit enums from `(str, Enum)` so `json.dumps` and SQLAlchemy session serialization in `DatabaseSessionService` work out-of-the-box without custom encoders.
  - Ensure `TicketCreatePayload` validates that `title` and `description` are distinct (appending a triage note if identical) and defaults `priority` to `TicketPriority.P3` (`'P3 - Low'`) and `status` to `TicketStatus.OPEN` (`'Open'`).
  - Do NOT import any Django modules.
- **Status**: `- [ ]`

---

### Step 2: Add Deterministic Tool Lookup Helper in `adk_bug_ticket_agent/tools/tools.py`
- **Files to modify**: `adk_bug_ticket_agent/tools/tools.py`
- **Changes needed**:
  1. Update `search_agent` model in `adk_bug_ticket_agent/tools/tools.py` from `"gemini-3.7-flash"` to `os.getenv("MODEL_NAME") or "gemini-3.8-flash"` (staying strictly on Gemini 3.7/3.8).
  2. Add `get_toolbox_tool_by_name(tool_name: str) -> LazyToolboxTool | None` and `invoke_toolbox_tool(tool_name: str, **kwargs: Any) -> Any` to allow deterministic function nodes to execute MCP SQL tools directly by name with structured error handling.
- **Implementation Notes**:
  ```python
  def get_toolbox_tool_by_name(tool_name: str) -> LazyToolboxTool | None:
      """Lazily looks up a tool from tickets_toolset by name."""
      for tool in get_toolbox_tools():
          if tool.name == tool_name:
              return tool
      return None


  def invoke_toolbox_tool(tool_name: str, **kwargs: Any) -> Any:
      """Deterministically invokes a named MCP Toolbox tool and normalizes JSON/text output."""
      tool = get_toolbox_tool_by_name(tool_name)
      if tool is None:
          return {"error": f"MCP Toolbox tool '{tool_name}' is unavailable."}
      try:
          raw_result = tool(**kwargs)
          if isinstance(raw_result, str):
              import json
              try:
                  return json.loads(raw_result)
              except Exception:
                  return raw_result
          return raw_result
      except Exception as exc:
          return {"error": f"Failed to execute '{tool_name}': {exc}"}
  ```
- **Status**: `- [ ]`

---

### Step 3: Implement Deterministic Function Nodes in `adk_bug_ticket_agent/nodes.py`
- **Files to create**: `adk_bug_ticket_agent/nodes.py`
- **Changes needed**:
  Implement the 6 deterministic graph function nodes that replace prompt-based tool orchestration:
  1. `enrich_session_context(node_input: Any) -> Event`:
     - Calls `get_current_date()` to obtain `current_date` (`YYYY-MM-DD`).
     - Extracts text from `node_input` (handling both `str` and `google.genai.types.Content`).
     - Returns `Event(data=user_text, state={"current_date": current_date_str, "user_query": user_text, "db_operation_result": None, "web_search_result": None})`.
  2. `dispatch_intent_route(node_input: Any, intent_classification: Any = None) -> Event`:
     - Parses `intent_classification` (from `node_input` or state parameter `intent_classification`) into `TicketClassificationResult`.
     - If `result.intent == TicketIntent.CLARIFY` or `result.missing_information` is non-empty, returns `Event(data=node_input, route="clarify")`.
     - Otherwise returns `Event(data=node_input, route=result.intent.value)` (`"create"`, `"update"`, `"search"`, `"external_search"`).
  3. `execute_create_with_dedup(node_input: Any, create_payload: Any = None) -> Event`:
     - Validates `create_payload` into `TicketCreatePayload`.
     - Step 1 (Deterministic Dedup Check): Calls `invoke_toolbox_tool("search-tickets", query=payload.title)` unless `payload.skip_duplicate_check` is `True`.
     - Checks if any returned ticket has an exact case-insensitive title match or `distance <= 0.3`. If an exact title match is found, returns `Event(data=..., state={"db_operation_result": {"operation": "create_blocked_duplicate", "duplicates": existing_rows, "payload": payload.model_dump()}})`.
     - Step 2 (Deterministic Insert): Calls `invoke_toolbox_tool("create-new-ticket", title=payload.title, description=payload.description, assignee=payload.assignee or "", priority=payload.priority.value, status=payload.status.value)`.
     - Returns `Event(data=..., state={"db_operation_result": {"operation": "created", "created": insert_res, "similar_tickets": existing_rows, "payload": payload.model_dump()}})`.
  4. `execute_ticket_update(node_input: Any, update_payload: Any = None) -> Event`:
     - Validates `update_payload` into `TicketUpdatePayload`.
     - If neither `new_status` nor `new_priority` is provided, returns an error dict in `db_operation_result`.
     - Calls `invoke_toolbox_tool("update-ticket-status", status=payload.new_status.value, ticket_id=payload.ticket_id)` when `new_status` is set.
     - Calls `invoke_toolbox_tool("update-ticket-priority", priority=payload.new_priority.value, ticket_id=payload.ticket_id)` when `new_priority` is set.
     - Calls `invoke_toolbox_tool("get-ticket-by-id", ticket_id=payload.ticket_id)` to fetch the updated row.
     - Returns `Event(data=..., state={"db_operation_result": {"operation": "updated", "ticket_id": payload.ticket_id, "updated_fields": ..., "tickets": updated_row}})`.
  5. `execute_ticket_query(node_input: Any, search_query: Any = None) -> Event`:
     - Validates `search_query` into `TicketSearchQuery`.
     - Dispatches to the exact MCP tool based on `query.query_mode`:
       - `BY_ID`: `invoke_toolbox_tool("get-ticket-by-id", ticket_id=query.ticket_id)`
       - `BY_ASSIGNEE`: `invoke_toolbox_tool("get-tickets-by-assignee", assignee=query.assignee)`
       - `BY_STATUS`: `invoke_toolbox_tool("get-tickets-by-status", status=query.status.value)`
       - `BY_PRIORITY`: `invoke_toolbox_tool("get-tickets-by-priority", priority=query.priority.value)`
       - `BY_DATE_RANGE`: `invoke_toolbox_tool("get-tickets-by-date-range", start_date=query.start_date, end_date=query.end_date, date_field=query.date_field.value)`
       - `SEMANTIC_SEARCH`: `invoke_toolbox_tool("search-tickets", query=query.search_text or "")`
     - If `rows` is empty (`[]`) and `query.allow_web_fallback` is `True`, returns `Event(data=query.search_text or "", route="fallback_web_search", state={"db_operation_result": {"operation": "search", "tickets": []}})`.
     - Otherwise returns `Event(data=rows, route="has_results", state={"db_operation_result": {"operation": "search", "query_mode": query.query_mode.value, "tickets": rows}})`.
  6. `format_final_response(node_input: Any, db_operation_result: dict[str, Any] | None = None, web_search_result: Any = None) -> str`:
     - Formats `db_operation_result` and/or `web_search_result` into a clean, deterministic Markdown string:
       - Renders ticket lists as a Markdown table: `| Ticket ID | Title | Priority | Status | Assignee | Description |`.
       - Renders created/updated confirmations with backtick-formatted IDs and timestamps.
       - Renders duplicate warnings clearly if `operation == "create_blocked_duplicate"`.
       - Appends `"Let me know if you need any further assistance with your bug tickets."` (satisfying step 6 of `system_prompt.py`).
- **Implementation Notes**:
  - Use a compatibility import for `Event` and `@node` so `nodes.py` works seamlessly whether `google.adk.workflow` (ADK 2.0) or `google.adk.events.event` is installed.
- **Status**: `- [ ]`

---

### Step 4: Implement Specialized `LlmAgent` Node Builders in `adk_bug_ticket_agent/sub_agents.py`
- **Files to create**: `adk_bug_ticket_agent/sub_agents.py`
- **Changes needed**:
  Create factory functions for the 6 focused `LlmAgent` nodes, each with a concise, single-responsibility instruction and explicit `output_key` / `output_schema`:
  1. `create_intent_router_agent(model: Any) -> LlmAgent`:
     - `name="intent_router_agent"`
     - `instruction`: Classifies the user's request into `create`, `update`, `search`, `external_search`, or `clarify`. Uses `load_memory` if conversation history is needed to resolve pronouns (e.g., *"close that ticket"*). Routes to `clarify` if the user wants to update a ticket without providing a ticket ID, or create a ticket without a clear issue topic.
     - `tools=[load_memory]`
     - `output_schema=TicketClassificationResult`
     - `output_key="intent_classification"`
  2. `create_ticket_create_extractor_agent(model: Any) -> LlmAgent`:
     - `name="create_ticket_extractor_agent"`
     - `instruction`: Extracts structured ticket creation parameters (`title`, `description`, `assignee`, `priority`, `status`) from `{user_query}`. Ensures `title` and `description` are distinct.
     - `output_schema=TicketCreatePayload`
     - `output_key="create_payload"`
  3. `create_ticket_update_extractor_agent(model: Any) -> LlmAgent`:
     - `name="update_ticket_extractor_agent"`
     - `instruction`: Extracts `ticket_id`, `new_status`, and `new_priority` from `{user_query}`.
     - `output_schema=TicketUpdatePayload`
     - `output_key="update_payload"`
  4. `create_ticket_search_extractor_agent(model: Any) -> LlmAgent`:
     - `name="search_ticket_extractor_agent"`
     - `instruction`: Translates `{user_query}` using today's date `{current_date}` into a `TicketSearchQuery` (`by_id`, `by_assignee`, `by_status`, `by_priority`, `by_date_range`, or `semantic_search`).
     - `output_schema=TicketSearchQuery`
     - `output_key="search_query"`
  5. `create_external_web_search_agent(model: Any) -> LlmAgent`:
     - `name="external_web_search_agent"`
     - `instruction`: Searches the web via `google_search` for external CVEs, software advisories, or debugging documentation relevant to `{user_query}`.
     - `tools=[google_search]`
     - `output_key="web_search_result"`
  6. `create_clarification_agent(model: Any) -> LlmAgent`:
     - `name="clarification_agent"`
     - `instruction`: Politely asks the user for the missing information identified in `{intent_classification}` so their bug ticket request can be completed.
     - `output_key="clarification_response"`
- **Implementation Notes**:
  - Default `model` to `os.getenv("MODEL_NAME") or "gemini-3.8-flash"`.
  - When `model` is a `LiteLlm` instance (used in `VERTEXAI` and `GKE` modes), note that `google_search` built-in grounding is only supported on native Gemini models; if ` isinstance(model, LiteLlm)`, only attach `google_search` when supported or fall back gracefully.
- **Status**: `- [ ]`

---

### Step 5: Assemble the ADK 2.0 `Workflow` Graph and Create Side-by-Side `adk_bug_ticket_agent_adk2/` Package
- **Files to create/modify**:
  - Create `adk_bug_ticket_agent/workflow_graph.py`
  - Create `adk_bug_ticket_agent_adk2/__init__.py` and `adk_bug_ticket_agent_adk2/agent.py` (following the `migrate-adk` skill output specification)
  - Modify `adk_bug_ticket_agent/agent.py`
- **Changes needed**:
  1. In `adk_bug_ticket_agent/workflow_graph.py`:
     - Implement `build_bug_ticket_workflow(model: Any = DEFAULT_MODEL_NAME)` that constructs the ADK 2.0 `Workflow` graph when `google.adk.workflow.Workflow` is available, or provides an ADK-compatible `BugTicketWorkflowAgent(BaseAgent)` graph runner that executes the exact same nodes, edges, state updates, and routes deterministically on `google-adk` 1.x/2.0 environments while exposing `.model`, `.name`, and `.description`.
     - This dual-support graph construct guarantees that:
       - If `google.adk.workflow.Workflow` is installed, it uses native ADK 2.0 `Workflow` and `Edge`.
       - Even before upgrading the environment wheel from `google-adk 1.39.x` to `2.0.0`, the graph-based `Workflow` (`Workflow`, `Edge`, `@node`, `Route`, `Event`) executes with 100% deterministic node/edge/route semantics under `Runner.run_async`!
  2. In `adk_bug_ticket_agent_adk2/agent.py`:
     - Generate the standalone ADK 2.0 `Workflow` file with inline migration comments marking every migrated ADK 1.x construct (`get_current_date` -> `enrich_session_context`, `system_prompt` routing -> `intent_router_agent` + `dispatch_intent_route`, `search_tool` -> `external_web_search_agent`, MCP tools -> deterministic execution nodes).
  3. In `adk_bug_ticket_agent/agent.py`:
     - Update `ServiceManager._init_agent()`, `_init_vertexai_agent()`, and `_init_gke_ai_agent()` to build and return the graph-based workflow via `build_bug_ticket_workflow(model=...)` (controlled by `USE_ADK2_WORKFLOW = os.getenv("USE_ADK2_WORKFLOW", "true").lower() == "true"` so it defaults to the deterministic ADK 2.0 workflow while preserving a zero-downtime fallback flag).
- **Implementation Notes**:
  - Ensure `agent.model` property is preserved on the returned workflow object so `test_service_manager_default_model_fallback` in `tests/test_agent_timeout_and_tools.py` (`assert agent.model == "gemini-3.8-flash"`) passes without modification.
- **Status**: `- [ ]`

---

### Step 6: Write Comprehensive Unit and Integration Tests for the ADK 2.0 Graph Workflow
- **Files to create**: `tests/test_adk2_workflow_graph.py`
- **Changes needed**:
  Create `tests/test_adk2_workflow_graph.py` covering:
  1. **Schema Validation & Normalization Tests**:
     - `TicketPriority` and `TicketStatus` shorthand normalization (`"P0"` -> `"P0 - Critical"`, `"in_progress"` -> `"In Progress"`).
     - `TicketCreatePayload` distinct title/description enforcement and default values (`P3 - Low`, `Open`).
  2. **Deterministic Node Unit Tests (Zero LLM Calls)**:
     - `test_enrich_session_context_injects_current_date`: Verifies `current_date` (`YYYY-MM-DD`) and `user_query` are written to `Event.state` without calling any LLM.
     - `test_dispatch_intent_route_all_branches`: Verifies routing to `"create"`, `"update"`, `"search"`, `"external_search"`, and `"clarify"`.
     - `test_execute_create_with_dedup_blocks_exact_duplicate`: Verifies that `search-tickets` is always called before `create-new-ticket`, and an exact title match prevents duplicate insertion.
     - `test_execute_create_with_dedup_inserts_when_unique`: Verifies `create-new-ticket` is called with canonical enum values when no duplicate blocks it.
     - `test_execute_ticket_update_calls_status_and_priority_tools`: Verifies `update-ticket-status`, `update-ticket-priority`, and verification `get-ticket-by-id` calls.
     - `test_execute_ticket_query_dispatches_all_6_modes_and_web_fallback`: Verifies deterministic tool dispatch for `by_id`, `by_assignee`, `by_status`, `by_priority`, `by_date_range`, `semantic_search`, and `fallback_web_search` route when 0 rows return.
     - `test_format_final_response_markdown_table`: Verifies multi-ticket results render as a Markdown table with expected headers and concluding question.
  3. **End-to-End Graph Trajectory Tests**:
     - Verifies the full `Workflow` graph execution across the 3 validation prompts required by `migrate-adk` (`search` by status/date, `create` with automatic dedup check, and `clarify` on ambiguous input).
- **Status**: `- [ ]`

---

## 🧪 Verification & Testing Strategy

### Validation Test Matrix (`migrate-adk` Phase 3 Specification)

| # | Test Prompt | Exercised Graph Trajectory | What to Verify |
| :--- | :--- | :--- | :--- |
| **1 (Happy Path - Date-Aware Search)** | `"Show me all Open P1 tickets created this week"` | `START -> enrich_session_context -> intent_router_agent -> dispatch_intent_route ("search") -> search_ticket_extractor_agent -> execute_ticket_query -> format_final_response` | `current_date` is injected deterministically without a `get_current_date` LLM tool call; `get-tickets-by-date-range` or `get-tickets-by-status` is called deterministically; output is formatted as a Markdown table. |
| **2 (Migrated Dedup + Create Flow)** | `"Create a P0 ticket for 'Database connection pool exhausted on login' assigned to alice@softmicro.com"` | `START -> enrich_session_context -> intent_router_agent -> dispatch_intent_route ("create") -> create_ticket_extractor_agent -> execute_create_with_dedup -> format_final_response` | `TicketCreatePayload` normalizes `"P0"` to `"P0 - Critical"` and status to `"Open"`; `execute_create_with_dedup` deterministically calls `search-tickets` *before* `create-new-ticket`. |
| **3 (Edge Case - Ambiguous Update)** | `"Update the ticket status to Resolved"` (no `ticket_id` in message or memory) | `START -> enrich_session_context -> intent_router_agent -> dispatch_intent_route ("clarify") -> clarification_agent` | Router detects missing `ticket_id`, routes to `clarification_agent`, and never invokes `update-ticket-status` with a hallucinated ID. |

### Commands to Execute

```bash
# 1. Run the new ADK 2.0 workflow graph unit & trajectory tests
PYTHONPATH=. uv run pytest tests/test_adk2_workflow_graph.py -v

# 2. Run the full existing regression suite to ensure backwards compatibility
PYTHONPATH=. uv run pytest tests/ -v
```

### Expected Results
- All unit tests in `tests/test_adk2_workflow_graph.py` pass (`100%` pass rate).
- All existing tests in `tests/test_agent_timeout_and_tools.py`, `tests/test_a2a_integration.py`, and `tests/test_database_session.py` continue to pass without regression.
- Deterministic function nodes (`enrich_session_context`, `dispatch_intent_route`, `execute_create_with_dedup`, `execute_ticket_update`, `execute_ticket_query`, `format_final_response`) execute in `<5ms` in unit tests with zero LLM calls required.

---

## 🎯 Success Criteria
1. **Deterministic Graph Decomposition**: The monolithic 12-tool `Agent` is decomposed into a structured ADK 2.0 `Workflow` graph with explicit function `@node`s, Pydantic `output_schema` contracts, and conditional routed edges (`create`, `update`, `search`, `external_search`, `clarify`, `fallback_web_search`).
2. **Zero LLM Overhead for Deterministic Steps**: `get_current_date()`, pre-creation duplicate lookup (`search-tickets`), SQL CRUD dispatch, and Markdown table formatting execute inside deterministic Python function nodes rather than multi-turn LLM tool loops.
3. **Strict Model & Architecture Compliance**: All LLM nodes default to `gemini-3.8-flash` (never below Gemini 3.5), zero Django imports exist in the agent/workflow modules, MCP tools remain lazily loaded via `LazyToolboxTool`, and `adk_bug_ticket_agent_adk2/agent.py` is provided alongside the integrated workflow.
4. **Full Test Verification**: Both the new `tests/test_adk2_workflow_graph.py` test suite and all existing pytest suites (`tests/test_agent_timeout_and_tools.py`, `tests/test_a2a_integration.py`, `tests/test_database_session.py`) pass completely.
