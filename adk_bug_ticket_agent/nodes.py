from __future__ import annotations

from datetime import datetime
import json
import logging
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, ValidationError

from adk_bug_ticket_agent.tools.tools import get_current_date, invoke_toolbox_tool

try:
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
except ImportError:
    # Graceful fallback in case schemas module is being loaded/modified concurrently
    TicketClassificationResult = None
    TicketCreatePayload = None
    TicketUpdatePayload = None
    TicketSearchQuery = None
    TicketIntent = None
    TicketPriority = None
    TicketStatus = None
    TicketQueryMode = None
    DateFilterField = None
    normalize_priority = None
    normalize_status = None

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ADK 1.x / 2.0 Compatibility Layer: WorkflowEvent, GraphEvent, and @node
# ---------------------------------------------------------------------------

try:
    from google.adk.events.event import Event as AdkEvent

    class WorkflowEvent(AdkEvent):
        """WorkflowEvent subclassing ADK Event with support for data, route, and state."""

        model_config = ConfigDict(extra="allow", populate_by_name=True)

        data: Any = None

        def __init__(
            self,
            data: Any = None,
            route: Any = None,
            state: dict[str, Any] | None = None,
            output: Any = None,
            **kwargs: Any,
        ):
            output_val = output if output is not None else data
            super().__init__(output=output_val, route=route, state=state, **kwargs)
            self.data = data

        @property
        def route(self) -> Any:
            return self.actions.route if self.actions else None

        @route.setter
        def route(self, value: Any) -> None:
            if self.actions is not None:
                self.actions.route = value

        @property
        def state(self) -> dict[str, Any] | None:
            return self.actions.state_delta if self.actions else None

        @state.setter
        def state(self, value: dict[str, Any] | None) -> None:
            if self.actions is not None:
                self.actions.state_delta = value

except ImportError:

    class FallbackWorkflowEvent:
        """Lightweight fallback WorkflowEvent for environments without google.adk."""

        def __init__(
            self,
            data: Any = None,
            route: Any = None,
            state: dict[str, Any] | None = None,
            output: Any = None,
            content: Any = None,
            **kwargs: Any,
        ):
            self.data = data
            self.output = output if output is not None else data
            self.content = content
            self.author = kwargs.get("author")
            self.invocation_id = kwargs.get("invocation_id")
            self._extra = kwargs

            class Actions:
                def __init__(self, route_val: Any, state_val: Any):
                    self.route = route_val
                    self.state_delta = state_val or {}

            self.actions = Actions(route, state)

        @property
        def route(self) -> Any:
            return self.actions.route

        @route.setter
        def route(self, value: Any) -> None:
            self.actions.route = value

        @property
        def state(self) -> dict[str, Any] | None:
            return self.actions.state_delta

        @state.setter
        def state(self, value: dict[str, Any] | None) -> None:
            self.actions.state_delta = value

        def is_final_response(self) -> bool:
            if self.content is not None:
                if hasattr(self.content, "parts") and self.content.parts:
                    return True
                if isinstance(self.content, dict) and self.content.get("parts"):
                    return True
            return False

    WorkflowEvent = FallbackWorkflowEvent  # type: ignore

# Backward compatibility aliases
GraphEvent = WorkflowEvent
Event = WorkflowEvent

try:
    from google.adk.workflow import FunctionNode, node as _adk_node

    def _fn_node_call(self: Any, *args: Any, **kwargs: Any) -> Any:
        fn = getattr(self, "_func", None) or getattr(self, "func", None) or getattr(self, "__wrapped__", None)
        if fn is not None and callable(fn):
            return fn(*args, **kwargs)
        raise TypeError(f"FunctionNode {self} has no callable target.")

    try:
        FunctionNode.__call__ = _fn_node_call  # type: ignore[attr-defined]
    except Exception:
        pass

    def node(func_or_none: Any = None, **kwargs: Any) -> Any:
        """Wrapper around ADK @node ensuring FunctionNode instances are callable."""
        def decorator(f: Callable[..., Any]) -> Any:
            fn_node = _adk_node(f, **kwargs)
            try:
                setattr(fn_node, "__wrapped__", f)
            except Exception:
                pass
            cls = type(fn_node)
            if not hasattr(cls, "__call__") or getattr(cls, "__call__", None) is object.__call__:
                try:
                    cls.__call__ = _fn_node_call  # type: ignore[attr-defined]
                except Exception:
                    pass
            return fn_node

        if func_or_none is not None and callable(func_or_none):
            return decorator(func_or_none)
        return decorator

except ImportError:

    def node(func_or_none: Any = None, **kwargs: Any) -> Any:
        """Shim for @node decorator when google.adk.workflow is not installed."""
        if func_or_none is not None and callable(func_or_none):
            return func_or_none

        def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
            return f

        return decorator


# ---------------------------------------------------------------------------
# Helper Utilities
# ---------------------------------------------------------------------------

def _extract_user_text(node_input: Any) -> str:
    """Safely extracts raw user query string from various ADK input representations."""
    if node_input is None:
        return ""
    if isinstance(node_input, str):
        return node_input
    if isinstance(node_input, dict):
        if "user_query" in node_input:
            return str(node_input["user_query"])
        if "text" in node_input:
            return str(node_input["text"])
        if "parts" in node_input and isinstance(node_input["parts"], list):
            parts = []
            for p in node_input["parts"]:
                if isinstance(p, dict) and "text" in p:
                    parts.append(str(p["text"]))
                elif hasattr(p, "text") and p.text:
                    parts.append(str(p.text))
            if parts:
                return "".join(parts)
        return str(node_input)
    if hasattr(node_input, "text") and node_input.text:
        return str(node_input.text)
    if hasattr(node_input, "parts") and getattr(node_input, "parts", None):
        parts = [
            getattr(p, "text", "")
            for p in getattr(node_input, "parts")
            if getattr(p, "text", None)
        ]
        return "".join(parts)
    return str(node_input)


def _format_tickets_table(tickets: list[dict[str, Any]]) -> str:
    """Formats a list of ticket records into a standardized GitHub Flavored Markdown table."""
    if not tickets:
        return "No tickets found."
    lines = [
        "| Ticket ID | Title | Priority | Status | Assignee | Description |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for t in tickets:
        if not isinstance(t, dict):
            continue
        tid = t.get("ticket_id") or t.get("id", "N/A")
        title = str(t.get("title", "")).replace("|", "\\|").strip()
        priority = t.get("priority", "N/A")
        status = t.get("status", "N/A")
        assignee = t.get("assignee") or "Unassigned"
        raw_desc = str(t.get("description", "")).replace("|", "\\|").replace("\n", " ").strip()
        desc = (raw_desc[:77] + "...") if len(raw_desc) > 80 else raw_desc
        lines.append(f"| `{tid}` | {title} | {priority} | {status} | {assignee} | {desc} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Deterministic Function Nodes
# ---------------------------------------------------------------------------

@node
def enrich_session_context(node_input: Any = None, **kwargs: Any) -> WorkflowEvent:
    """
    Migrated from: get_current_date() tool call.
    Runs deterministically at workflow START with zero LLM cost.
    Injects 'current_date' (YYYY-MM-DD) and 'user_query' into workflow state.
    """
    try:
        date_data = get_current_date()
        current_date_str = (
            date_data.get("current_date")
            if isinstance(date_data, dict)
            else str(date_data)
        )
    except Exception as exc:
        logger.warning("Failed to invoke get_current_date(): %s", exc)
        current_date_str = datetime.now().strftime("%Y-%m-%d")

    user_text = _extract_user_text(node_input)
    state_delta = {
        "current_date": current_date_str,
        "user_query": user_text,
        "db_operation_result": None,
        "web_search_result": None,
    }
    return WorkflowEvent(data=user_text, state=state_delta)


@node
def dispatch_intent_route(
    node_input: Any = None,
    intent_classification: Any = None,
    **kwargs: Any,
) -> WorkflowEvent:
    """
    Deterministic router node. Evaluates the structured output from intent_router_agent
    and returns WorkflowEvent(data=..., route=<route_name>) matching the Workflow edges:
    'create', 'update', 'search', 'external_search', or 'clarify'.
    """
    target = intent_classification if intent_classification is not None else node_input

    intent_val = None
    missing_info = None

    if isinstance(target, BaseModel):
        intent_val = getattr(target, "intent", None)
        missing_info = getattr(target, "missing_information", None)
    elif isinstance(target, dict):
        intent_val = target.get("intent")
        missing_info = target.get("missing_information")
    elif isinstance(target, str):
        intent_val = target

    # Handle enum objects vs string names
    if hasattr(intent_val, "value"):
        intent_str = str(intent_val.value).lower()
    elif intent_val is not None:
        intent_str = str(intent_val).lower().strip()
    else:
        intent_str = "clarify"

    # Route decision: missing info always routes to clarify
    if missing_info and str(missing_info).strip():
        route = "clarify"
    elif intent_str in ("create", "ticketintent.create_ticket", "create_ticket"):
        route = "create"
    elif intent_str in ("update", "ticketintent.update_ticket", "update_ticket"):
        route = "update"
    elif intent_str in ("search", "ticketintent.search_tickets", "search_tickets"):
        route = "search"
    elif intent_str in ("external_search", "ticketintent.external_search"):
        route = "external_search"
    elif intent_str in ("clarify", "ticketintent.clarify"):
        route = "clarify"
    else:
        route = intent_str

    return WorkflowEvent(data=node_input, route=route)


@node
def execute_create_with_dedup(
    node_input: Any = None,
    create_payload: Any = None,
    **kwargs: Any,
) -> WorkflowEvent:
    """
    Deterministic ticket creation pipeline:
    1. Validates create_payload via TicketCreatePayload.
    2. Invokes MCP 'search-tickets' with payload.title to check for existing duplicates.
    3. If duplicate exists and not skip_duplicate_check, halts creation and returns duplicate warning.
    4. Otherwise invokes MCP 'create-new-ticket' and stores result in state['db_operation_result'].
    """
    payload_source = create_payload if create_payload is not None else node_input

    # Parse and normalize payload attributes via TicketCreatePayload
    payload_obj = None
    if TicketCreatePayload is not None:
        if isinstance(payload_source, TicketCreatePayload):
            payload_obj = payload_source
        elif isinstance(payload_source, BaseModel):
            try:
                payload_obj = TicketCreatePayload.model_validate(payload_source.model_dump())
            except Exception:
                pass
        elif isinstance(payload_source, dict):
            try:
                payload_obj = TicketCreatePayload.model_validate(payload_source)
            except Exception:
                pass

    if payload_obj is not None:
        title = payload_obj.title
        description = payload_obj.description
        assignee = payload_obj.assignee
        priority = payload_obj.priority
        status = payload_obj.status
        skip_duplicate_check = payload_obj.skip_duplicate_check
    elif isinstance(payload_source, dict):
        title = str(payload_source.get("title", "")).strip()
        raw_desc = str(payload_source.get("description", "")).strip()
        if title and raw_desc and title.lower() == raw_desc.lower():
            description = f"{raw_desc} (Reported issue details pending further triage)"
        else:
            description = raw_desc
        assignee = payload_source.get("assignee")
        raw_pri = payload_source.get("priority", "P3 - Low")
        norm_pri = normalize_priority(raw_pri) if normalize_priority else None
        priority = norm_pri if norm_pri is not None else (raw_pri or "P3 - Low")
        raw_stat = payload_source.get("status", "Open")
        norm_stat = normalize_status(raw_stat) if normalize_status else None
        status = norm_stat if norm_stat is not None else (raw_stat or "Open")
        skip_duplicate_check = payload_source.get("skip_duplicate_check", False)
    else:
        title = str(payload_source or "").strip()
        description = f"{title} (Reported issue details pending further triage)" if title else ""
        assignee = None
        priority = "P3 - Low"
        status = "Open"
        skip_duplicate_check = False

    priority_val = priority.value if hasattr(priority, "value") else str(priority)
    status_val = status.value if hasattr(status, "value") else str(status)

    payload_dict = {
        "title": title,
        "description": description,
        "assignee": assignee,
        "priority": priority_val,
        "status": status_val,
        "skip_duplicate_check": bool(skip_duplicate_check),
    }

    # Step 1: Duplicate check via search-tickets
    existing_duplicates = []
    if not skip_duplicate_check and title.strip():
        search_res = invoke_toolbox_tool("search-tickets", query=title.strip())
        candidate_rows = (
            search_res
            if isinstance(search_res, list)
            else search_res.get("tickets", [])
            if isinstance(search_res, dict)
            else []
        )
        for row in candidate_rows:
            if not isinstance(row, dict):
                continue
            row_title = str(row.get("title", "")).strip().lower()
            target_title = title.strip().lower()
            distance = row.get("distance")
            is_exact = row_title == target_title
            is_close = (
                distance is not None
                and isinstance(distance, (int, float))
                and distance <= 0.3
            )
            if is_exact or is_close:
                existing_duplicates.append(row)

        if existing_duplicates:
            db_res = {
                "operation": "create_blocked_duplicate",
                "duplicates": existing_duplicates,
                "payload": payload_dict,
            }
            return WorkflowEvent(data=db_res, state={"db_operation_result": db_res})

    # Step 2: Insert new ticket via create-new-ticket
    insert_res = invoke_toolbox_tool(
        "create-new-ticket",
        title=title,
        description=description,
        assignee=assignee or "",
        priority=priority_val,
        status=status_val,
    )

    db_res = {
        "operation": "created",
        "created": insert_res,
        "similar_tickets": existing_duplicates if not skip_duplicate_check else [],
        "payload": payload_dict,
    }
    return WorkflowEvent(data=db_res, state={"db_operation_result": db_res})


# Aliases for checklist and testing compatibility
pre_create_duplicate_check = execute_create_with_dedup
execute_ticket_create = execute_create_with_dedup


@node
def execute_ticket_update(
    node_input: Any = None,
    update_payload: Any = None,
    **kwargs: Any,
) -> WorkflowEvent:
    """
    Deterministic ticket update pipeline:
    1. Validates update_payload via TicketUpdatePayload.
    2. Calls 'update-ticket-status' if new_status is provided.
    3. Calls 'update-ticket-priority' if new_priority is provided.
    4. Calls 'get-ticket-by-id' to fetch updated record and stores in state['db_operation_result'].
    """
    payload_source = update_payload if update_payload is not None else node_input

    payload_obj = None
    if TicketUpdatePayload is not None:
        if isinstance(payload_source, TicketUpdatePayload):
            payload_obj = payload_source
        elif isinstance(payload_source, BaseModel):
            try:
                payload_obj = TicketUpdatePayload.model_validate(payload_source.model_dump())
            except Exception:
                pass
        elif isinstance(payload_source, dict):
            try:
                payload_obj = TicketUpdatePayload.model_validate(payload_source)
            except Exception:
                pass

    if payload_obj is not None:
        ticket_id = payload_obj.ticket_id
        new_status = payload_obj.new_status
        new_priority = payload_obj.new_priority
    elif isinstance(payload_source, dict):
        ticket_id = payload_source.get("ticket_id")
        raw_status = payload_source.get("new_status")
        new_status = normalize_status(raw_status) if normalize_status and raw_status is not None else raw_status
        raw_priority = payload_source.get("new_priority")
        new_priority = normalize_priority(raw_priority) if normalize_priority and raw_priority is not None else raw_priority
    else:
        ticket_id = str(payload_source or "")
        new_status = None
        new_priority = None

    if not ticket_id or (new_status is None and new_priority is None):
        err_res = {
            "error": "Missing ticket_id or no fields (status/priority) provided for update.",
            "ticket_id": ticket_id,
        }
        return WorkflowEvent(data=err_res, state={"db_operation_result": err_res})

    updated_fields: dict[str, str] = {}
    if new_status is not None:
        status_val = new_status.value if hasattr(new_status, "value") else str(new_status)
        invoke_toolbox_tool("update-ticket-status", status=status_val, ticket_id=str(ticket_id))
        updated_fields["status"] = status_val

    if new_priority is not None:
        priority_val = new_priority.value if hasattr(new_priority, "value") else str(new_priority)
        invoke_toolbox_tool("update-ticket-priority", priority=priority_val, ticket_id=str(ticket_id))
        updated_fields["priority"] = priority_val

    updated_record = invoke_toolbox_tool("get-ticket-by-id", ticket_id=str(ticket_id))

    db_res = {
        "operation": "updated",
        "ticket_id": str(ticket_id),
        "updated_fields": updated_fields,
        "tickets": updated_record,
    }
    return WorkflowEvent(data=db_res, state={"db_operation_result": db_res})


@node
def execute_ticket_query(
    node_input: Any = None,
    search_query: Any = None,
    **kwargs: Any,
) -> WorkflowEvent:
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
    query_source = search_query if search_query is not None else node_input

    query_obj = None
    if TicketSearchQuery is not None:
        if isinstance(query_source, TicketSearchQuery):
            query_obj = query_source
        elif isinstance(query_source, BaseModel):
            try:
                query_obj = TicketSearchQuery.model_validate(query_source.model_dump())
            except Exception:
                pass
        elif isinstance(query_source, dict):
            try:
                query_obj = TicketSearchQuery.model_validate(query_source)
            except Exception:
                pass

    if query_obj is not None:
        mode = query_obj.query_mode
        ticket_id = query_obj.ticket_id
        assignee = query_obj.assignee
        status = query_obj.status
        priority = query_obj.priority
        start_date = query_obj.start_date
        end_date = query_obj.end_date
        date_field = query_obj.date_field
        search_text = query_obj.search_text
        allow_web_fallback = bool(query_obj.allow_web_fallback)
    elif isinstance(query_source, dict):
        mode = query_source.get("query_mode", "semantic_search")
        ticket_id = query_source.get("ticket_id")
        assignee = query_source.get("assignee")
        raw_status = query_source.get("status")
        status = normalize_status(raw_status) if normalize_status and raw_status is not None else raw_status
        raw_priority = query_source.get("priority")
        priority = normalize_priority(raw_priority) if normalize_priority and raw_priority is not None else raw_priority
        start_date = query_source.get("start_date")
        end_date = query_source.get("end_date")
        date_field = query_source.get("date_field", "creation_time")
        search_text = query_source.get("search_text")
        allow_web_fallback = bool(query_source.get("allow_web_fallback", False))
    else:
        mode = "semantic_search"
        ticket_id = None
        assignee = None
        status = None
        priority = None
        start_date = None
        end_date = None
        date_field = "creation_time"
        search_text = str(query_source or "")
        allow_web_fallback = False

    mode_val = mode.value if hasattr(mode, "value") else str(mode).lower()

    if mode_val in ("by_id", "by-id"):
        raw_rows = invoke_toolbox_tool("get-ticket-by-id", ticket_id=str(ticket_id or search_text or ""))
    elif mode_val in ("by_assignee", "by-assignee"):
        raw_rows = invoke_toolbox_tool("get-tickets-by-assignee", assignee=str(assignee or search_text or ""))
    elif mode_val in ("by_status", "by-status"):
        status_val = status.value if hasattr(status, "value") else str(status or "")
        raw_rows = invoke_toolbox_tool("get-tickets-by-status", status=status_val)
    elif mode_val in ("by_priority", "by-priority"):
        priority_val = priority.value if hasattr(priority, "value") else str(priority or "")
        raw_rows = invoke_toolbox_tool("get-tickets-by-priority", priority=priority_val)
    elif mode_val in ("by_date_range", "by-date-range"):
        date_field_val = date_field.value if hasattr(date_field, "value") else str(date_field or "creation_time")
        raw_rows = invoke_toolbox_tool(
            "get-tickets-by-date-range",
            start_date=str(start_date or ""),
            end_date=str(end_date or ""),
            date_field=date_field_val,
        )
    else:
        raw_rows = invoke_toolbox_tool("search-tickets", query=str(search_text or ""))

    # Normalize rows list
    if isinstance(raw_rows, list):
        rows_list = raw_rows
    elif isinstance(raw_rows, dict):
        if "error" in raw_rows:
            rows_list = []
        elif "tickets" in raw_rows and isinstance(raw_rows["tickets"], list):
            rows_list = raw_rows["tickets"]
        elif "id" in raw_rows or "ticket_id" in raw_rows:
            rows_list = [raw_rows]
        else:
            rows_list = []
    else:
        rows_list = []

    is_empty = len(rows_list) == 0

    if is_empty and allow_web_fallback:
        db_res = {
            "operation": "search",
            "query_mode": mode_val,
            "tickets": [],
        }
        return WorkflowEvent(
            data=search_text or "",
            route="fallback_web_search",
            state={"db_operation_result": db_res},
        )

    db_res = {
        "operation": "search",
        "query_mode": mode_val,
        "tickets": rows_list,
    }
    return WorkflowEvent(
        data=rows_list,
        route="has_results",
        state={"db_operation_result": db_res},
    )


@node
def format_final_response(
    node_input: Any = None,
    db_operation_result: dict[str, Any] | None = None,
    web_search_result: Any = None,
    **kwargs: Any,
) -> str:
    """
    Deterministic post-processor that formats single or multiple bug tickets into
    a consistent Markdown table, formats code/timestamps, and appends a conclusion prompt.
    """
    db_res = db_operation_result
    if db_res is None and isinstance(node_input, dict):
        if "operation" in node_input or "tickets" in node_input or "error" in node_input:
            db_res = node_input
        elif "db_operation_result" in node_input and isinstance(node_input["db_operation_result"], dict):
            db_res = node_input["db_operation_result"]

    web_res = web_search_result
    if web_res is None and isinstance(node_input, dict):
        web_res = node_input.get("web_search_result")

    parts: list[str] = []

    if db_res:
        if "error" in db_res:
            parts.append(f"An error occurred while processing the ticket: {db_res['error']}")
        else:
            operation = db_res.get("operation")
            if operation == "create_blocked_duplicate":
                duplicates = db_res.get("duplicates", [])
                parts.append("⚠️ **Duplicate Ticket Warning**: A bug ticket with an identical title or similar description was found:")
                parts.append(_format_tickets_table(duplicates if isinstance(duplicates, list) else [duplicates]))
                parts.append("If you still want to proceed with creation, please confirm by asking to create the ticket with duplicate check skipped.")

            elif operation == "created":
                created = db_res.get("created", {})
                payload = db_res.get("payload", {})
                created_dict = (
                    created[0]
                    if isinstance(created, list) and created and isinstance(created[0], dict)
                    else (created if isinstance(created, dict) else {})
                )
                tid = (
                    created_dict.get("ticket_id")
                    or created_dict.get("id")
                    or (payload.get("ticket_id") if isinstance(payload, dict) else None)
                    or "New"
                )
                parts.append(f"✅ Bug ticket `{tid}` has been successfully created.")
                info = (
                    created_dict
                    if "title" in created_dict
                    else (payload if isinstance(payload, dict) else {})
                )
                parts.append(f"- **Title**: {info.get('title', 'N/A')}")
                parts.append(f"- **Priority**: {info.get('priority', 'N/A')}")
                parts.append(f"- **Status**: {info.get('status', 'Open')}")
                parts.append(f"- **Assignee**: {info.get('assignee') or 'Unassigned'}")
                parts.append(f"- **Description**: {info.get('description', 'N/A')}")

                similar = db_res.get("similar_tickets", [])
                if similar and isinstance(similar, list):
                    parts.append(f"\n*Note: {len(similar)} existing similar tickets were noted during creation.*")

            elif operation == "updated":
                tid = db_res.get("ticket_id", "N/A")
                updated_fields = db_res.get("updated_fields", {})
                records = db_res.get("tickets", {})
                parts.append(f"✅ Bug ticket `{tid}` has been successfully updated.")
                for k, v in updated_fields.items():
                    parts.append(f"- **{k.capitalize()}**: `{v}`")

                if isinstance(records, list) and records:
                    parts.append(f"\nUpdated Ticket Details:\n{_format_tickets_table(records)}")
                elif isinstance(records, dict) and (records.get("id") or records.get("ticket_id")):
                    parts.append(f"\nUpdated Ticket Details:\n{_format_tickets_table([records])}")

            elif operation == "search":
                tickets = db_res.get("tickets", [])
                t_list = tickets if isinstance(tickets, list) else [tickets] if isinstance(tickets, dict) else []
                if not t_list:
                    parts.append("No bug tickets were found matching your search criteria.")
                else:
                    parts.append(f"Found {len(t_list)} bug ticket(s):\n")
                    parts.append(_format_tickets_table(t_list))

    elif isinstance(node_input, str) and node_input.strip():
        parts.append(node_input.strip())

    if web_res:
        web_text = (
            web_res.text
            if hasattr(web_res, "text")
            else str(web_res.get("text", web_res))
            if isinstance(web_res, dict)
            else str(web_res)
        )
        if web_text.strip():
            parts.append(f"\n### External Research & Advisories:\n{web_text.strip()}")

    if not parts:
        parts.append("Request processed successfully.")

    parts.append("\nLet me know if you need any further assistance with your bug tickets.")
    return "\n\n".join(parts).strip()


format_ticket_response = format_final_response

__all__ = [
    "enrich_session_context",
    "dispatch_intent_route",
    "execute_create_with_dedup",
    "pre_create_duplicate_check",
    "execute_ticket_create",
    "execute_ticket_update",
    "execute_ticket_query",
    "format_final_response",
    "format_ticket_response",
    "WorkflowEvent",
    "GraphEvent",
    "Event",
    "node",
]
