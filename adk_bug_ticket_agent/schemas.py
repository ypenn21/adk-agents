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
    if isinstance(value, TicketPriority):
        return value
    cleaned = str(value).strip().upper()
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
    try:
        return TicketPriority(value)
    except ValueError:
        return None


def normalize_status(value: Optional[str]) -> Optional[TicketStatus]:
    """Deterministically normalizes status strings to canonical TicketStatus enum."""
    if value is None:
        return None
    if isinstance(value, TicketStatus):
        return value
    cleaned = str(value).strip().lower()
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
    try:
        return TicketStatus(value)
    except ValueError:
        return None


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
        if v is None:
            return TicketPriority.P3
        return normalize_priority(v) or TicketPriority.P3

    @field_validator("status", mode="before")
    @classmethod
    def _validate_status(cls, v: Any) -> TicketStatus:
        if v is None:
            return TicketStatus.OPEN
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


class WorkflowState(BaseModel):
    """Typed workflow state dictionary contract."""
    current_date: Optional[str] = Field(default=None, description="Current system date formatted as YYYY-MM-DD.")
    user_query: Optional[str] = Field(default=None, description="Raw input text submitted by the user.")
    intent_classification: Optional[TicketClassificationResult] = Field(
        default=None, description="Structured routing intent classified from user message."
    )
    intent_route: Optional[str] = Field(
        default=None, description="Selected route name emitted by dispatch_intent_route."
    )
    create_payload: Optional[TicketCreatePayload] = Field(
        default=None, description="Extracted parameters for creating a new ticket."
    )
    update_payload: Optional[TicketUpdatePayload] = Field(
        default=None, description="Extracted parameters for updating an existing ticket."
    )
    search_query: Optional[TicketSearchQuery] = Field(
        default=None, description="Extracted parameters for searching internal tickets."
    )
    db_operation_result: Optional[Any] = Field(
        default=None, description="Execution result returned from MCP PostgreSQL operations."
    )
    web_search_result: Optional[Any] = Field(
        default=None, description="External Google Search results or grounding response."
    )
    clarification_response: Optional[str] = Field(
        default=None, description="Clarification message generated for incomplete queries."
    )


__all__ = [
    "TicketIntent",
    "TicketPriority",
    "TicketStatus",
    "TicketQueryMode",
    "DateFilterField",
    "normalize_priority",
    "normalize_status",
    "TicketClassificationResult",
    "TicketCreatePayload",
    "TicketUpdatePayload",
    "TicketSearchQuery",
    "WorkflowState",
]
