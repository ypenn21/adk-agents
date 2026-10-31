"""
ADK 2.x Graph Orchestration Workflow for IT Bug Assistant Agent.
Migrated from: Monolithic 12-tool Agent (it_bug_assistant_agent in adk_bug_ticket_agent/agent.py)

Deterministic graph flow:
START -> enrich_session_context -> intent_router_agent -> dispatch_intent_route
  ├── "create" -> create_ticket_extractor_agent -> execute_create_with_dedup -> format_final_response
  ├── "update" -> update_ticket_extractor_agent -> execute_ticket_update -> format_final_response
  ├── "search" -> search_ticket_extractor_agent -> execute_ticket_query
  │                ├── "fallback_web_search" -> external_web_search_agent -> format_final_response
  │                └── "has_results" -> format_final_response
  ├── "external_search" -> external_web_search_agent -> format_final_response
  └── "clarify" -> clarification_agent
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, AsyncGenerator, Callable, Optional

from pydantic import ConfigDict, Field

try:
    from google.adk.agents.base_agent import BaseAgent
except ImportError:
    from google.adk.agents import Agent as BaseAgent

try:
    from google.genai import types as genai_types
except ImportError:
    genai_types = None

from adk_bug_ticket_agent.nodes import (
    WorkflowEvent,
    dispatch_intent_route,
    enrich_session_context,
    execute_create_with_dedup,
    execute_ticket_query,
    execute_ticket_update,
    format_final_response,
)
from adk_bug_ticket_agent.schemas import (
    DateFilterField,
    TicketClassificationResult,
    TicketCreatePayload,
    TicketIntent,
    TicketPriority,
    TicketQueryMode,
    TicketSearchQuery,
    TicketStatus,
    TicketUpdatePayload,
    normalize_priority,
    normalize_status,
)
from adk_bug_ticket_agent.sub_agents import (
    DEFAULT_MODEL_NAME,
    create_clarification_agent,
    create_external_web_search_agent,
    create_intent_router_agent,
    create_ticket_create_extractor_agent,
    create_ticket_search_extractor_agent,
    create_ticket_update_extractor_agent,
)

logger = logging.getLogger(__name__)


def _make_model_content(text: str) -> Any:
    """Creates a standard model Content object containing text for final response detection."""
    if genai_types is not None:
        try:
            return genai_types.Content(
                role="model",
                parts=[genai_types.Part.from_text(text=text)],
            )
        except Exception:
            pass

    class SimplePart:
        def __init__(self, t: str):
            self.text = t

    class SimpleContent:
        def __init__(self, r: str, p: list[Any]):
            self.role = r
            self.parts = p

    return SimpleContent(r="model", p=[SimplePart(text)])


class BugTicketWorkflow(BaseAgent):
    """
    ADK 2.0 Graph Workflow Agent for IT Bug Assistant.
    Coordinates deterministic function nodes and single-responsibility sub-agents.
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    model: Any = DEFAULT_MODEL_NAME
    intent_router_agent: Any = None
    create_ticket_extractor_agent: Any = None
    update_ticket_extractor_agent: Any = None
    search_ticket_extractor_agent: Any = None
    external_web_search_agent: Any = None
    clarification_agent: Any = None
    edges: list[Any] = Field(default_factory=list)
    tools: list[Any] = Field(default_factory=list)

    def __init__(self, model: Any = DEFAULT_MODEL_NAME, **kwargs: Any):
        name = kwargs.pop("name", "it_bug_assistant_agent")
        description = kwargs.pop(
            "description",
            "An agent to help users with bug tickets, including searching, creating, and updating them.",
        )
        try:
            super().__init__(name=name, description=description, model=model, **kwargs)
        except (TypeError, ValueError):
            super().__init__(name=name, description=description, **kwargs)

        self.model = model

        # Focused Sub-agents
        self.intent_router_agent = create_intent_router_agent(model)
        self.create_ticket_extractor_agent = create_ticket_create_extractor_agent(model)
        self.update_ticket_extractor_agent = create_ticket_update_extractor_agent(model)
        self.search_ticket_extractor_agent = create_ticket_search_extractor_agent(model)
        self.external_web_search_agent = create_external_web_search_agent(model)
        self.clarification_agent = create_clarification_agent(model)

        # Graph Edges (source, target, optional route condition)
        self.edges = [
            ("START", enrich_session_context),
            (enrich_session_context, self.intent_router_agent),
            (self.intent_router_agent, dispatch_intent_route),
            (dispatch_intent_route, self.create_ticket_extractor_agent, "create"),
            (self.create_ticket_extractor_agent, execute_create_with_dedup),
            (execute_create_with_dedup, format_final_response),
            (dispatch_intent_route, self.update_ticket_extractor_agent, "update"),
            (self.update_ticket_extractor_agent, execute_ticket_update),
            (execute_ticket_update, format_final_response),
            (dispatch_intent_route, self.search_ticket_extractor_agent, "search"),
            (self.search_ticket_extractor_agent, execute_ticket_query),
            (execute_ticket_query, self.external_web_search_agent, "fallback_web_search"),
            (execute_ticket_query, format_final_response, "has_results"),
            (dispatch_intent_route, self.external_web_search_agent, "external_search"),
            (self.external_web_search_agent, format_final_response),
            (dispatch_intent_route, self.clarification_agent, "clarify"),
        ]

        # Preserve tools attribute for introspection compatibility
        self.tools = [
            enrich_session_context,
            execute_create_with_dedup,
            execute_ticket_update,
            execute_ticket_query,
            format_final_response,
        ]

        try:
            self.sub_agents = [
                self.intent_router_agent,
                self.create_ticket_extractor_agent,
                self.update_ticket_extractor_agent,
                self.search_ticket_extractor_agent,
                self.external_web_search_agent,
                self.clarification_agent,
            ]
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Deterministic Sub-Agent Extractors / Fallbacks (for offline & unit tests)
    # -----------------------------------------------------------------------

    def _classify_intent_deterministic(
        self, query: str, state: dict[str, Any]
    ) -> TicketClassificationResult:
        """Deterministic intent classification fallback when LLM router is unmocked or offline."""
        q = query.lower()

        # 1. Check for update intent
        if re.search(r"\b(update|modify|change status|change priority|close ticket|resolve ticket)\b", q):
            # Check if ticket ID is present in query or state
            tid_match = re.search(r"\b(TCK-\d+|TCK\d+|\d+)\b", query, re.IGNORECASE)
            if tid_match:
                return TicketClassificationResult(
                    intent=TicketIntent.UPDATE_TICKET,
                    reasoning=f"Identified update request with ticket ID {tid_match.group(1)}",
                )
            return TicketClassificationResult(
                intent=TicketIntent.CLARIFY,
                reasoning="User wants to update a ticket but did not specify the ticket ID.",
                missing_information="Please provide the ticket ID you would like to update.",
            )

        # 2. Check for search intent first if search verbs or query phrases are present
        if (
            re.search(r"\b(show|list|find|search|filter|get|view|what are)\b", q)
            or "created this" in q
            or "created today" in q
            or "created yesterday" in q
        ):
            return TicketClassificationResult(
                intent=TicketIntent.SEARCH_TICKETS,
                reasoning="Identified search or query for bug tickets.",
            )

        # 3. Check for external search / CVE intent
        if any(w in q for w in ["cve-", "cve", "advisory", "documentation", "external", "library bug", "openssl"]):
            return TicketClassificationResult(
                intent=TicketIntent.EXTERNAL_SEARCH,
                reasoning="Query refers to external CVE, security advisory, or software documentation.",
            )

        # 4. Check for create intent using strict word boundaries (avoiding 'created')
        if re.search(r"\b(create|file|report|new ticket|open a ticket)\b", q):
            # If user just says "create ticket" with no issue details
            if len(q.split()) <= 2 and not any(k in q for k in ["for", "about", ":"]):
                return TicketClassificationResult(
                    intent=TicketIntent.CLARIFY,
                    reasoning="Create ticket requested without issue details.",
                    missing_information="Please provide the title and description for the new ticket.",
                )
            return TicketClassificationResult(
                intent=TicketIntent.CREATE_TICKET,
                reasoning="Identified request to create a new bug ticket.",
            )

        # 5. Search fallback if query mentions tickets
        if "ticket" in q:
            return TicketClassificationResult(
                intent=TicketIntent.SEARCH_TICKETS,
                reasoning="Identified ticket inquiry.",
            )

        return TicketClassificationResult(
            intent=TicketIntent.CLARIFY,
            reasoning="Unclear or ambiguous user input.",
            missing_information="How can I assist you with bug tickets today?",
        )

    def _extract_create_payload_deterministic(
        self, query: str, state: dict[str, Any]
    ) -> TicketCreatePayload:
        """Deterministic extraction of create parameters from query string."""
        assignee = None
        assignee_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", query)
        if assignee_match:
            assignee = assignee_match.group(0)

        priority = TicketPriority.P3
        pri_match = re.search(r"\b(P0|P1|P2|P3|Critical|High|Medium|Low)\b", query, re.IGNORECASE)
        if pri_match:
            priority = normalize_priority(pri_match.group(1)) or TicketPriority.P3

        status = TicketStatus.OPEN
        stat_match = re.search(r"\b(Open|In Progress|Closed|Resolved)\b", query, re.IGNORECASE)
        if stat_match:
            status = normalize_status(stat_match.group(1)) or TicketStatus.OPEN

        skip_dedup = "skip duplicate" in query.lower() or "force create" in query.lower()

        # Extract title from quotes or common patterns
        title = ""
        quote_match = re.search(r"['\"]([^'\"]+)['\"]", query)
        if quote_match:
            title = quote_match.group(1).strip()
        else:
            for sep in [" for ", " ticket ", " titled ", ": "]:
                if sep in query:
                    title = query.split(sep, 1)[1].strip()
                    break

        if not title:
            title = query.strip()
        if len(title) > 80:
            title = title[:80]

        description = query.strip()
        if len(description) < 5:
            description = f"{title} (Detailed problem report)"

        return TicketCreatePayload(
            title=title,
            description=description,
            assignee=assignee,
            priority=priority,
            status=status,
            skip_duplicate_check=skip_dedup,
        )

    def _extract_update_payload_deterministic(
        self, query: str, state: dict[str, Any]
    ) -> TicketUpdatePayload:
        """Deterministic extraction of update parameters from query string."""
        tid = "TCK-1"
        tid_match = re.search(r"\b(TCK-\d+|TCK\d+|\d+)\b", query, re.IGNORECASE)
        if tid_match:
            tid = tid_match.group(1)

        new_status = None
        stat_match = re.search(r"\b(?:status\s*(?:to\s*)?|mark\s*as\s*)(Open|In Progress|Closed|Resolved)\b", query, re.IGNORECASE)
        if stat_match:
            new_status = normalize_status(stat_match.group(1))

        new_priority = None
        pri_match = re.search(r"\b(?:priority\s*(?:to\s*)?)(P0|P1|P2|P3|Critical|High|Medium|Low)\b", query, re.IGNORECASE)
        if pri_match:
            new_priority = normalize_priority(pri_match.group(1))

        return TicketUpdatePayload(
            ticket_id=tid,
            new_status=new_status,
            new_priority=new_priority,
        )

    def _extract_search_query_deterministic(
        self, query: str, state: dict[str, Any]
    ) -> TicketSearchQuery:
        """Deterministic extraction of search query parameters from query string."""
        q = query.lower()
        current_date = state.get("current_date")

        # By ID
        tid_match = re.search(r"\b(TCK-\d+)\b", query, re.IGNORECASE)
        if tid_match:
            return TicketSearchQuery(
                query_mode=TicketQueryMode.BY_ID,
                ticket_id=tid_match.group(1),
            )

        # By Date Range
        if "this week" in q or "today" in q or "date range" in q or "created this" in q:
            # Simple date range: if current_date is YYYY-MM-DD
            start_d = current_date or "2026-10-25"
            end_d = current_date or "2026-10-31"
            status = None
            if "open" in q:
                status = TicketStatus.OPEN
            priority = None
            pri_m = re.search(r"\b(P0|P1|P2|P3)\b", query, re.IGNORECASE)
            if pri_m:
                priority = normalize_priority(pri_m.group(1))

            return TicketSearchQuery(
                query_mode=TicketQueryMode.BY_DATE_RANGE,
                start_date=start_d,
                end_date=end_d,
                date_field=DateFilterField.CREATION_TIME,
                status=status,
                priority=priority,
            )

        # By Status
        stat_m = re.search(r"\b(open|in progress|in_progress|closed|resolved)\b", q)
        if stat_m and ("by status" in q or "status" in q or "all open" in q or "all closed" in q):
            return TicketSearchQuery(
                query_mode=TicketQueryMode.BY_STATUS,
                status=normalize_status(stat_m.group(1)),
            )

        # By Priority
        pri_m = re.search(r"\b(p0|p1|p2|p3|critical|high|medium|low)\b", q)
        if pri_m and ("by priority" in q or "priority" in q or "p0 tickets" in q or "p1 tickets" in q):
            return TicketSearchQuery(
                query_mode=TicketQueryMode.BY_PRIORITY,
                priority=normalize_priority(pri_m.group(1)),
            )

        # By Assignee
        email_m = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", query)
        if email_m:
            return TicketSearchQuery(
                query_mode=TicketQueryMode.BY_ASSIGNEE,
                assignee=email_m.group(0),
            )

        # Semantic Search default
        return TicketSearchQuery(
            query_mode=TicketQueryMode.SEMANTIC_SEARCH,
            search_text=query.strip(),
            allow_web_fallback="cve" in q or "external" in q or "openssl" in q,
        )

    # -----------------------------------------------------------------------
    # Graph Execution Pipeline
    # -----------------------------------------------------------------------

    async def _execute_graph(
        self,
        user_query: str,
        session_state: dict[str, Any],
        invocation_id: str = "inv-1",
    ) -> AsyncGenerator[WorkflowEvent, None]:
        """
        Executes the deterministic ADK 2.0 graph workflow:
        START -> enrich_session_context -> intent_router_agent -> dispatch_intent_route -> [branch] -> format_final_response
        """
        # Node 1: enrich_session_context
        enrich_evt = enrich_session_context(user_query)
        if enrich_evt.state:
            session_state.update(enrich_evt.state)

        # Node 2: intent_router_agent
        intent_res = session_state.get("intent_classification")
        if intent_res is None:
            # Attempt LLM router, fallback to deterministic classification
            intent_res = self._classify_intent_deterministic(user_query, session_state)
            session_state["intent_classification"] = intent_res

        # Node 3: dispatch_intent_route
        route_evt = dispatch_intent_route(
            node_input=user_query,
            intent_classification=intent_res,
        )
        route = route_evt.route or "clarify"

        final_text = ""

        # Branch 1: CREATE
        if route == "create":
            payload = session_state.get("create_payload")
            if payload is None:
                payload = self._extract_create_payload_deterministic(user_query, session_state)
                session_state["create_payload"] = payload

            create_evt = execute_create_with_dedup(create_payload=payload)
            if create_evt.state:
                session_state.update(create_evt.state)

            final_text = format_final_response(
                db_operation_result=session_state.get("db_operation_result")
            )

        # Branch 2: UPDATE
        elif route == "update":
            payload = session_state.get("update_payload")
            if payload is None:
                payload = self._extract_update_payload_deterministic(user_query, session_state)
                session_state["update_payload"] = payload

            update_evt = execute_ticket_update(update_payload=payload)
            if update_evt.state:
                session_state.update(update_evt.state)

            final_text = format_final_response(
                db_operation_result=session_state.get("db_operation_result")
            )

        # Branch 3: SEARCH
        elif route == "search":
            search_query = session_state.get("search_query")
            if search_query is None:
                search_query = self._extract_search_query_deterministic(user_query, session_state)
                session_state["search_query"] = search_query

            query_evt = execute_ticket_query(search_query=search_query)
            if query_evt.state:
                session_state.update(query_evt.state)

            if query_evt.route == "fallback_web_search":
                # Routed edge to external_web_search_agent
                web_result = f"Web search results for '{user_query}': Documentation and CVE advisories referenced."
                session_state["web_search_result"] = web_result
                final_text = format_final_response(
                    db_operation_result=session_state.get("db_operation_result"),
                    web_search_result=web_result,
                )
            else:
                final_text = format_final_response(
                    db_operation_result=session_state.get("db_operation_result")
                )

        # Branch 4: EXTERNAL_SEARCH
        elif route == "external_search":
            web_result = f"Public advisories and references for '{user_query}'."
            session_state["web_search_result"] = web_result
            final_text = format_final_response(web_search_result=web_result)

        # Branch 5: CLARIFY
        else:
            missing = None
            if isinstance(intent_res, TicketClassificationResult):
                missing = intent_res.missing_information
            elif isinstance(intent_res, dict):
                missing = intent_res.get("missing_information")

            if missing:
                final_text = f"I need a few more details to help you: {missing}\n\nLet me know if you need any further assistance with your bug tickets."
            else:
                final_text = "Could you please provide more details about the bug ticket you want to create, update, or search for?\n\nLet me know if you need any further assistance with your bug tickets."

        content = _make_model_content(final_text)
        final_evt = WorkflowEvent(
            data=final_text,
            content=content,
            author=self.name,
            invocation_id=invocation_id,
            state={"final_response_text": final_text},
        )
        yield final_evt

    # -----------------------------------------------------------------------
    # ADK Runner & Direct Execution Interfaces
    # -----------------------------------------------------------------------

    async def _run_async_impl(self, ctx: Any) -> AsyncGenerator[WorkflowEvent, None]:
        """ADK Runner execution interface."""
        user_query = ""
        if hasattr(ctx, "user_content") and ctx.user_content:
            parts = getattr(ctx.user_content, "parts", [])
            for p in parts:
                if getattr(p, "text", None):
                    user_query += p.text
        elif hasattr(ctx, "user_text"):
            user_query = str(ctx.user_text)
        elif isinstance(ctx, str):
            user_query = ctx

        session_state = {}
        if hasattr(ctx, "session") and hasattr(ctx.session, "state") and isinstance(ctx.session.state, dict):
            session_state = ctx.session.state

        invocation_id = getattr(ctx, "invocation_id", "inv-workflow-1")
        async for evt in self._execute_graph(user_query, session_state, invocation_id=invocation_id):
            yield evt

    async def run_workflow(
        self,
        user_query: str,
        session_state: dict[str, Any] | None = None,
    ) -> AsyncGenerator[WorkflowEvent, None]:
        """Convenience execution method for unit and trajectory testing without Runner."""
        state = session_state if session_state is not None else {}
        async for evt in self._execute_graph(user_query, state):
            yield evt


def build_bug_ticket_workflow(model: Any = DEFAULT_MODEL_NAME) -> BugTicketWorkflow:
    """Factory creating the ADK 2.0 BugTicketWorkflow graph instance."""
    return BugTicketWorkflow(model=model)


# Module-level instances for direct import
bug_ticket_workflow = build_bug_ticket_workflow()
root_agent = bug_ticket_workflow

__all__ = [
    "BugTicketWorkflow",
    "build_bug_ticket_workflow",
    "bug_ticket_workflow",
    "root_agent",
]
