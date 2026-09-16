import importlib
import os
import pytest
from starlette.testclient import TestClient

from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.a2a.utils.agent_to_a2a import to_a2a

import adk_bug_ticket_agent.agent as agent_module
from adk_bug_ticket_agent.agent_executor import AdkAgentToA2AExecutor


def test_agent_module_imports_cleanly_under_django(monkeypatch):
    """Verifies that importing agent.py under DJANGO='true' succeeds with app set to None."""
    monkeypatch.setenv("DJANGO", "true")
    importlib.reload(agent_module)

    assert agent_module.app is None
    assert agent_module.root_agent is None
    assert agent_module._service_manager is not None


def test_agent_card_structure_validity():
    """Verifies that agent_card is constructed using Protobuf schema without schema mismatch errors."""
    card = agent_module.agent_card
    assert card is not None
    assert card.name == "IT Bug Assistant Agent"
    assert card.version == "1.0.0"
    assert card.description.startswith("An agent to help users")
    assert card.capabilities.streaming is True

    # Verify skills
    assert len(card.skills) >= 1
    skill_ids = [s.id for s in card.skills]
    assert "bug_triage_assistant" in skill_ids

    # Verify supported_interfaces contains JSONRPC protocol binding
    assert len(card.supported_interfaces) >= 1
    assert card.supported_interfaces[0].protocol_binding == "JSONRPC"
    assert card.supported_interfaces[0].url == agent_module.AGENT_URL


def test_a2a_standalone_app_endpoints():
    """Verifies that the standalone A2A Starlette application serves agent-card metadata and JSON-RPC routes."""
    test_agent = Agent(name="it_bug_assistant_agent", description="Test agent")
    test_app = to_a2a(
        test_agent,
        host="127.0.0.1",
        port=8000,
        agent_card=agent_module.agent_card,
    )

    with TestClient(test_app) as client:
        # 1. Verify agent card endpoint
        resp = client.get("/.well-known/agent-card.json")
        assert resp.status_code == 200
        card_data = resp.json()
        assert card_data["name"] == "IT Bug Assistant Agent"
        assert card_data["version"] == "1.0.0"
        assert len(card_data["supportedInterfaces"]) >= 1
        assert card_data["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"

        # 2. Verify JSON-RPC root route exists and responds to POST
        rpc_resp = client.post(
            "/",
            json={"jsonrpc": "2.0", "method": "invalid_method", "id": 1},
        )
        assert rpc_resp.status_code == 200
        rpc_data = rpc_resp.json()
        assert "error" in rpc_data
        assert rpc_data["jsonrpc"] == "2.0"


def test_agent_executor_import_and_instantiation():
    """Verifies that AdkAgentToA2AExecutor can be imported and instantiated both standalone and with custom Runner."""
    # 1. Default instantiation
    executor = AdkAgentToA2AExecutor()
    assert isinstance(executor, A2aAgentExecutor)
    assert executor.name == "IT Bug Assistant Agent"
    assert executor._runner is not None

    # 2. Instantiation with custom runner
    custom_agent = Agent(name="custom_agent")
    custom_runner = Runner(
        app_name="custom_app",
        agent=custom_agent,
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )
    custom_executor = AdkAgentToA2AExecutor(runner=custom_runner)
    assert isinstance(custom_executor, A2aAgentExecutor)
    assert custom_executor._runner is custom_runner


def test_service_manager_agent_executor_lazy_load():
    """Verifies that ServiceManager initializes the official A2aAgentExecutor lazily."""
    sm = agent_module.ServiceManager()
    assert sm._agent_executor is None

    executor = sm.agent_executor
    assert executor is not None
    assert isinstance(executor, A2aAgentExecutor)
    assert sm._agent_executor is executor

    # Second access returns cached instance
    assert sm.agent_executor is executor
