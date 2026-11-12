import os
from typing import Any, Optional

try:
    from google.adk.agents.llm_agent import LlmAgent
except ImportError:
    from google.adk.agents import Agent as LlmAgent

try:
    from google.adk.models.lite_llm import LiteLlm
except ImportError:
    LiteLlm = None

try:
    from google.adk.tools import load_memory
except ImportError:
    try:
        from google.adk.tools.load_memory import load_memory
    except ImportError:
        load_memory = None

try:
    from google.adk.tools import google_search
except ImportError:
    try:
        from google.adk.tools.google_search import google_search
    except ImportError:
        google_search = None

from .schemas import (
    TicketClassificationResult,
    TicketCreatePayload,
    TicketSearchQuery,
    TicketUpdatePayload,
)

DEFAULT_MODEL_NAME = os.getenv("MODEL_NAME") or "gemini-3.8-flash"

# --- Sub-Agent Instructions ---

INTENT_ROUTER_INSTRUCTION = """You are an intent classification specialist for the IT Bug Ticket Assistant.
Analyze the user's latest query along with conversation history.
Classify the user's intent into one of the following canonical categories:
- 'create': The user wants to report, file, or create a new bug ticket.
- 'update': The user wants to modify an existing ticket (e.g., change status, close, resolve, reopen, escalate, or update priority). Recognizes natural update verbs like 'update', 'modify', 'change', 'set', 'mark', 'close', 'resolve', 'reopen', 'escalate'.
- 'search': The user wants to find, list, view, or filter internal bug tickets (e.g., by status like 'Closed' or 'Open', by priority, by date, or by single ticket ID like 'ticket-id 10', 'ticket 10', '#10').
  SPECIAL CASE (Compound Search + Web Solutions): If the user asks to find/get/look up a specific ticket ID (e.g., 'find ticket-id 10 and find solutions on websearch', 'get ticket 10 and search web for a fix'), classify intent as 'search' so the internal ticket details are retrieved from the database first before performing external research.
- 'external_search': The user is asking about standalone external software issues, general CVEs, public library bugs, or external documentation not tied to looking up an internal ticket.
- 'clarify': The user's request is ambiguous, lacks critical information (such as asking to update a ticket without specifying which ticket ID or referencing an earlier ticket, or asking to file a bug with no information), or is an unintelligible query.

Use the load_memory tool if you need to resolve pronouns or references to tickets mentioned earlier in the conversation.
Provide your output matching the TicketClassificationResult schema with 'intent', 'reasoning', and 'missing_information' (if applicable)."""

TICKET_CREATE_EXTRACTOR_INSTRUCTION = """You are a ticket creation extraction specialist.
Extract structured ticket creation parameters from the user's message and context:
- 'title': Concise, distinct summary of the bug (minimum 3 characters).
- 'description': Detailed description of the problem, steps to reproduce, or observed symptoms (minimum 5 characters).
  Ensure 'title' and 'description' are distinct and not identical copies.
- 'assignee': Assignee email address if mentioned, otherwise null.
- 'priority': Ticket priority ('P0 - Critical', 'P1 - High', 'P2 - Medium', 'P3 - Low'). Default to 'P3 - Low' if unspecified.
- 'status': Initial ticket status ('Open', 'In Progress', 'Closed', 'Resolved'). Default to 'Open'.
- 'skip_duplicate_check': Boolean flag, true only if user explicitly requested creating the ticket despite duplicate warnings.

Produce your output matching the TicketCreatePayload schema."""

TICKET_UPDATE_EXTRACTOR_INSTRUCTION = """You are a ticket update extraction specialist.
Extract update parameters from the user's message and conversation context:
- 'ticket_id': The unique ID of the ticket to be updated (e.g. '10', 'TCK-10', 'ticket-id 10', '#10'). Normalize prefixes and strip whitespace (e.g. 'ticket-id 10' -> '10', '#10' -> '10', 'TCK-123' -> 'TCK-123'). If the user refers to 'it', 'this ticket', or 'that ticket', resolve to the active ticket ID from context.
- 'new_status': New status if specified ('Open', 'In Progress', 'Closed', 'Resolved'). Interpret action verbs appropriately (e.g., 'close ticket 10' -> new_status='Closed', 'resolve ticket 10' -> new_status='Resolved', 'reopen' -> new_status='Open').
- 'new_priority': New priority if specified ('P0 - Critical', 'P1 - High', 'P2 - Medium', 'P3 - Low').

Produce your output matching the TicketUpdatePayload schema."""

TICKET_SEARCH_EXTRACTOR_INSTRUCTION = """You are a ticket search extraction specialist.
Using today's reference date {current_date}, analyze the user's query and extract search parameters:
- 'query_mode': One of:
  * 'all': User asks to show, list, get, or view all tickets in the system without any status, priority, assignee, date range, or ticket ID filter (e.g., 'show all tickets', 'list all tickets', 'get all tickets', 'view all tickets', 'show tickets', 'list tickets', 'Check the status of bug tickets in the system').
  * 'by_id': User provides a specific ticket ID (e.g., 'ticket-id 10', 'ticket 10', '#10', 'TCK-10').
  * 'by_assignee': User filters by assignee email or name.
  * 'by_status': User filters by status (e.g. Open, In Progress, Closed, Resolved, e.g., 'find closed status tickets').
  * 'by_priority': User filters by priority (e.g. P0 - Critical, P1 - High, P2 - Medium, P3 - Low).
  * 'by_date_range': User filters by date range (e.g., tickets created this week, updated since yesterday). Compute start_date and end_date in YYYY-MM-DD format using {current_date}.
  * 'semantic_search': Free-text keyword or semantic similarity search across title and description.
- 'ticket_id': Normalized Ticket ID if query_mode is 'by_id' (e.g. '10' for 'ticket-id 10', 'TCK-123' for 'TCK-123').
- 'assignee': Assignee email/name if query_mode is 'by_assignee'.
- 'status': Canonical status if query_mode is 'by_status' (e.g. 'Closed', 'Open', 'In Progress', 'Resolved').
- 'priority': Canonical priority if query_mode is 'by_priority' (or secondary filter).
- 'start_date' / 'end_date': YYYY-MM-DD date bounds if query_mode is 'by_date_range'.
- 'date_field': 'creation_time' or 'updated_time' (defaults to 'creation_time').
- 'search_text': Keywords or description for semantic search. Strip meta-directives like 'and find solutions on websearch'.
- 'allow_web_fallback': True if the query asks about broad technical errors/CVEs where external web search should be attempted if no internal tickets match.
- 'research_solutions': True whenever the user asks to find a ticket AND search the web for solutions, fixes, troubleshooting steps, or workarounds (e.g., 'find ticket-id 10 and find solutions on websearch').

Produce your output matching the TicketSearchQuery schema."""

EXTERNAL_WEB_SEARCH_INSTRUCTION = """You are an external technical research and solutions specialist.
When provided with a search query or bug ticket details (title, description, and error symptoms), use Google Search to identify concrete root causes, recommended fixes, configuration adjustments, and troubleshooting steps from official documentation, CVE advisories, GitHub issues, and community workarounds.
Synthesize the top actionable findings clearly and concisely with direct remediation steps and reference links where available."""

CLARIFICATION_INSTRUCTION = """You are a helpful IT Bug Ticket Assistant.
The user's request is ambiguous, incomplete, or missing critical parameters (such as a missing ticket ID for an update, or missing details for creating a ticket).
Review the missing information identified and ask a polite, concise clarifying question to help the user provide what is needed."""


def _build_llm_agent(
    name: str,
    instruction: str,
    model: Any = DEFAULT_MODEL_NAME,
    description: Optional[str] = None,
    tools: Optional[list[Any]] = None,
    output_schema: Optional[Any] = None,
    output_key: Optional[str] = None,
) -> LlmAgent:
    """Helper to instantiate LlmAgent with output_schema and output_key compatibility."""
    kwargs: dict[str, Any] = {
        "name": name,
        "instruction": instruction,
        "model": model,
    }
    if description is not None:
        kwargs["description"] = description
    if tools is not None:
        kwargs["tools"] = tools

    full_kwargs = dict(kwargs)
    if output_schema is not None:
        full_kwargs["output_schema"] = output_schema
    if output_key is not None:
        full_kwargs["output_key"] = output_key

    try:
        agent = LlmAgent(**full_kwargs)
    except TypeError:
        # Fallback for ADK versions where output_schema/output_key are not direct __init__ parameters
        agent = LlmAgent(**kwargs)

    if output_schema is not None and not hasattr(agent, "output_schema"):
        try:
            setattr(agent, "output_schema", output_schema)
        except Exception:
            pass

    if output_key is not None and not hasattr(agent, "output_key"):
        try:
            setattr(agent, "output_key", output_key)
        except Exception:
            pass

    return agent


def create_intent_router_agent(model: Any = DEFAULT_MODEL_NAME) -> LlmAgent:
    """
    Creates the intent router LlmAgent node.
    Classifies the user's request into 'create', 'update', 'search', 'external_search', or 'clarify'.
    Uses load_memory tool when available to resolve pronouns and conversational references.
    """
    tools = [load_memory] if load_memory is not None else []
    return _build_llm_agent(
        name="intent_router_agent",
        model=model,
        description="Classifies user queries into bug ticket workflow intents.",
        instruction=INTENT_ROUTER_INSTRUCTION,
        tools=tools,
        output_schema=TicketClassificationResult,
        output_key="intent_classification",
    )


def create_ticket_create_extractor_agent(model: Any = DEFAULT_MODEL_NAME) -> LlmAgent:
    """
    Creates the ticket creation parameter extractor LlmAgent node.
    Extracts structured ticket creation fields (title, description, assignee, priority, status).
    """
    return _build_llm_agent(
        name="create_ticket_extractor_agent",
        model=model,
        description="Extracts validated parameters for creating new bug tickets.",
        instruction=TICKET_CREATE_EXTRACTOR_INSTRUCTION,
        output_schema=TicketCreatePayload,
        output_key="create_payload",
    )


def create_ticket_update_extractor_agent(model: Any = DEFAULT_MODEL_NAME) -> LlmAgent:
    """
    Creates the ticket update parameter extractor LlmAgent node.
    Extracts ticket_id, new_status, and new_priority.
    """
    return _build_llm_agent(
        name="update_ticket_extractor_agent",
        model=model,
        description="Extracts validated parameters for updating existing bug tickets.",
        instruction=TICKET_UPDATE_EXTRACTOR_INSTRUCTION,
        output_schema=TicketUpdatePayload,
        output_key="update_payload",
    )


def create_ticket_search_extractor_agent(model: Any = DEFAULT_MODEL_NAME) -> LlmAgent:
    """
    Creates the ticket search parameter extractor LlmAgent node.
    Translates user query using {current_date} into TicketSearchQuery.
    """
    return _build_llm_agent(
        name="search_ticket_extractor_agent",
        model=model,
        description="Translates natural language search queries into structured TicketSearchQuery filters.",
        instruction=TICKET_SEARCH_EXTRACTOR_INSTRUCTION,
        output_schema=TicketSearchQuery,
        output_key="search_query",
    )


def create_external_web_search_agent(model: Any = DEFAULT_MODEL_NAME) -> LlmAgent:
    """
    Creates the external web research LlmAgent node.
    Searches web for software advisories, CVEs, and external documentation via google_search.
    Gracefully handles LiteLlm instances by omitting google_search if unsupported.
    """
    tools = []
    is_litellm = LiteLlm is not None and isinstance(model, LiteLlm)
    if not is_litellm and google_search is not None:
        tools.append(google_search)

    return _build_llm_agent(
        name="external_web_search_agent",
        model=model,
        description="Searches external web sources for software advisories, CVEs, and documentation.",
        instruction=EXTERNAL_WEB_SEARCH_INSTRUCTION,
        tools=tools,
        output_key="web_search_result",
    )


def create_clarification_agent(model: Any = DEFAULT_MODEL_NAME) -> LlmAgent:
    """
    Creates the clarification LlmAgent node.
    Asks polite, targeted clarifying questions when required information is missing.
    """
    return _build_llm_agent(
        name="clarification_agent",
        model=model,
        description="Generates concise clarifying questions for ambiguous or incomplete ticket requests.",
        instruction=CLARIFICATION_INSTRUCTION,
        output_key="clarification_response",
    )


# --- Module-Level Convenience Aliases ---

intent_router_agent = create_intent_router_agent()
ticket_create_extractor_agent = create_ticket_create_extractor_agent()
ticket_update_extractor_agent = create_ticket_update_extractor_agent()
ticket_search_extractor_agent = create_ticket_search_extractor_agent()
external_web_search_agent = create_external_web_search_agent()
clarification_agent = create_clarification_agent()

# Synonyms matching naming variations in workflow references
create_create_ticket_extractor_agent = create_ticket_create_extractor_agent
create_update_ticket_extractor_agent = create_ticket_update_extractor_agent
create_search_ticket_extractor_agent = create_ticket_search_extractor_agent
create_external_web_research_agent = create_external_web_search_agent
external_web_research_agent = external_web_search_agent

__all__ = [
    "DEFAULT_MODEL_NAME",
    "create_intent_router_agent",
    "create_ticket_create_extractor_agent",
    "create_ticket_update_extractor_agent",
    "create_ticket_search_extractor_agent",
    "create_external_web_search_agent",
    "create_clarification_agent",
    "intent_router_agent",
    "ticket_create_extractor_agent",
    "ticket_update_extractor_agent",
    "ticket_search_extractor_agent",
    "external_web_search_agent",
    "clarification_agent",
    "create_create_ticket_extractor_agent",
    "create_update_ticket_extractor_agent",
    "create_search_ticket_extractor_agent",
    "create_external_web_research_agent",
    "external_web_research_agent",
]
