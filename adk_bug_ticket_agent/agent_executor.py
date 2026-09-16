"""A2A Agent Executor compatibility adapter for Google ADK."""
from typing import Any, Optional

from google.adk.agents import Agent
from google.adk.agents.base_agent import BaseAgent
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor


class AdkAgentToA2AExecutor(A2aAgentExecutor):
    """Backwards-compatible wrapper delegating to Google ADK's native A2aAgentExecutor."""

    def __init__(
        self,
        agent: Optional[BaseAgent] = None,
        session_service: Optional[Any] = None,
        memory_service: Optional[Any] = None,
        runner: Optional[Runner] = None,
    ) -> None:
        self.name = "IT Bug Assistant Agent"
        if runner is None:
            resolved_agent = (
                agent if agent is not None else Agent(name="it_bug_assistant_agent")
            )
            resolved_session = (
                session_service
                if session_service is not None
                else InMemorySessionService()
            )
            resolved_memory = (
                memory_service
                if memory_service is not None
                else InMemoryMemoryService()
            )
            runner = Runner(
                app_name=self.name,
                agent=resolved_agent,
                session_service=resolved_session,
                artifact_service=InMemoryArtifactService(),
                memory_service=resolved_memory,
            )
        super().__init__(runner=runner)
        self.agent = agent
        self._user_id = "remote_agent"