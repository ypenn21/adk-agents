import os
from google.adk.agents import Agent
from google.adk.sessions import DatabaseSessionService
from . import system_prompt
from .tools.tools import get_current_date, search_tool, toolbox_tools
from google.adk.tools import load_memory
from google.adk.memory import VertexAiRagMemoryService, InMemoryMemoryService


# --- Global Initializations ---
# For SQLite, make sure the directory for the DB file is writable by the Django process.
# Using an absolute path or ensuring BASE_DIR is correctly set for Django is important.
# For simplicity, placing it in the project root. For local PostgreSQL, use the following format.
DB_URL = os.environ.get("DB_URL", "postgresql://postgres:admin@localhost:5432/tickets-db")
# Explore using VertexAiSessionService or InMemorySessionService for production https://google.github.io/adk-docs/sessions/session/#managing-sessions-with-a-sessionservice
# Lazy initialization for session_service
_session_service_instance = None
def get_session_service():
    global _session_service_instance
    if _session_service_instance is None:
        print("set _session_service_instance to a new DatabaseSessionService instance")
        _session_service_instance = DatabaseSessionService(db_url=DB_URL)
        print(f"ADK Database URL: {DB_URL}")
    return _session_service_instance

# adding memory https://google.github.io/adk-docs/sessions/memory/#how-memory-works-in-practice

# The RAG Corpus name or ID
RAG_CORPUS_RESOURCE_NAME = os.environ.get("RAG_CORPUS", "projects/genai-playground/locations/us-central1/ragCorpora/rag-corpus-id")
# Optional configuration for retrieval
SIMILARITY_TOP_K = 5
VECTOR_DISTANCE_THRESHOLD = 0.7

# Lazy initialization for memory_service
_memory_service_instance = None
def get_memory_service():
    global _memory_service_instance
    if _memory_service_instance is None:
        print("set _memory_service_instance to a new VertexAiRagMemoryService instance")
        _memory_service_instance = VertexAiRagMemoryService(
            rag_corpus=RAG_CORPUS_RESOURCE_NAME,
            similarity_top_k=SIMILARITY_TOP_K,
            vector_distance_threshold=VECTOR_DISTANCE_THRESHOLD
        )
    return _memory_service_instance


_memory_service_instance = InMemoryMemoryService() #uncomment this line to use in-memory storage for local environment testing

# Lazy initialization for root_agent
_root_agent_instance = None

def get_root_agent():
    global _root_agent_instance
    if _root_agent_instance is None:
        _root_agent_instance = Agent(
            model="gemini-2.5-flash",
            name="it_bug_assistant_agent",
            instruction=system_prompt.agent_instruction,
            tools=[load_memory, get_current_date, search_tool, *toolbox_tools],
        )
        print("Root agent initialized.") # Added for debugging cold start
    return _root_agent_instance
# --- End Global Initializations ---

# this is only used by adk web not in the django framework.
root_agent = get_root_agent()
