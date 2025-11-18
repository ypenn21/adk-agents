# Feature Implementation Plan: standalone-agent-deployment

## 📋 Todo Checklist
- [x] ~~Refactor `adk_bug_ticket_agent/tools/tools.py` to lazy-load `toolbox_tools`.~~ ✅ Implemented
- [x] ~~Refactor `adk_bug_ticket_agent/agent.py` to use lazy-loaded `toolbox_tools`.~~ ✅ Implemented
- [x] ~~Refactor `deploy_agent_engine.py` to be a standalone script.~~ ✅ Implemented
- [x] ~~Implement `LazyToolboxTool` wrapper to fix pickling issues.~~ ✅ Implemented
- [x] ~~Run the deployment script and verify its success.~~ ✅ Completed
- [ ] Implement a testing strategy for the deployed agent.
- [ ] Final Review and Testing

## 🔍 Analysis & Investigation

### Codebase Structure
- `deploy_agent_engine.py`: The main script for deploying the agent to Vertex AI Agent Engine. It currently has dependencies on the Django framework.
- `adk_bug_ticket_agent/agent.py`: Contains the agent creation logic. The `get_agent` function uses a `ServiceManager` to manage agent-related services.
- `adk_bug_ticket_agent/tools/tools.py`: Defines the tools used by the agent, including `toolbox_tools` which are initialized at the module level.
- `manage.py`: The Django management script, which is currently used to run `deploy_agent_engine.py`. The goal is to run the deployment script without it.
- `a2a_sample/agent_deployment.py`: A sample deployment script that can be used as a reference for a standalone deployment.

### Current Architecture
The project is a Django web application that also serves as a host for an ADK agent. The deployment script is mixed in with the Django project, causing a conflict between the web application context and the deployment context. The `ServiceManager` in `adk_bug_ticket_agent/agent.py` is designed to manage agent services, and the user has confirmed it does not contain direct Django imports.

### Dependencies & Integration Points
- **Vertex AI Agent Engine**: The target deployment platform.
- **Django**: The web framework. The deployment script needs to be decoupled from it.
- **google-cloud-aiplatform**: The client library for interacting with Vertex AI.
- **ToolboxSyncClient**: Used to load `toolbox_tools`. Its module-level initialization is a potential source of non-pickleable objects.

### Considerations & Challenges
- **Pickling Error**: The `TypeError: cannot pickle '_contextvars.Context' object` error persists. While the `ServiceManager` itself might not have Django imports, the `ToolboxSyncClient` (initialized at the module level in `adk_bug_ticket_agent/tools/tools.py`) likely establishes connections or holds state that is not pickleable. This is the most probable cause of the pickling error when the agent (which includes these tools) is serialized for deployment.
- **Standalone Execution**: The script needs to be runnable with a simple `python deploy_agent_engine.py` command. This requires removing Django dependencies and ensuring all necessary imports are handled correctly.

## 📝 Implementation Plan

### Prerequisites
- The user must be authenticated with `gcloud` and have the necessary permissions to deploy to Vertex AI.
- The `PROJECT_ID` environment variable must be set.

### Step-by-Step Implementation

1. **Step 1: Lazy-load `toolbox_tools`**
   - **Files to modify**: `adk_bug_ticket_agent/tools/tools.py`
   - **Changes needed**:
     - Wrap the initialization of `ToolboxSyncClient` and `toolbox.load_toolset` in a function `get_toolbox_tools()`.
     - This function should ensure that `toolbox_tools` are only initialized when first accessed, preventing non-pickleable objects from being created at module load time.
   - **Implementation Notes**: I have added the `get_toolbox_tools` function and kept the original `toolbox_tools` initialization to avoid breaking other parts of the application that might be using it. The new function will be used in the agent creation process for deployment.
   - **Status**: ✅ Completed

2. **Step 2: Use lazy-loaded `toolbox_tools` in Agent creation**
   - **Files to modify**: `adk_bug_ticket_agent/agent.py`
   - **Changes needed**:
     - Import `get_toolbox_tools` from `adk_bug_ticket_agent/tools/tools.py`.
     - Update the `_init_agent` and `_init_vertexai_agent` methods to call `get_toolbox_tools()` when constructing the `Agent`'s `tools` list.
   - **Implementation Notes**: I have updated the `_init_agent` and `_init_vertexai_agent` methods to use the `get_toolbox_tools` function.
   - **Status**: ✅ Completed

3. **Step 3: Refactor `deploy_agent_engine.py` to be a Standalone Script**
   - **Files to modify**: `deploy_agent_engine.py`
   - **Changes needed**:
     - Remove the Django-related imports (`from django.apps import AppConfig`) and the `AdkAgentConfig` class.
     - Ensure `get_agent` is imported from `adk_bug_ticket_agent.agent`.
     - Add a `main` function and a `if __name__ == "__main__":` block to make the script directly executable.
     - Initialize `vertexai` with the project and location.
     - Add the project root to `sys.path` to ensure imports work correctly when run as a standalone script.
   - **Implementation Notes**: I have refactored the script to be a standalone executable python script.
   - **Status**: ✅ Completed

4. **Step 4: Implement Pickleable Tool Wrapper**
   - **Files to modify**: `adk_bug_ticket_agent/tools/tools.py`
   - **Changes needed**:
     - Create a `LazyToolboxTool` class that wraps `ToolboxSyncTool`.
     - Implement `__getstate__` to exclude the unpickleable `ToolboxSyncTool` instance.
     - Implement `__setstate__` and `__call__` to re-initialize the tool on demand using a shared `ToolboxSyncClient`.
     - Update `get_toolbox_tools` to return `LazyToolboxTool` instances.
   - **Status**: ✅ Completed

5. **Step 5: Run the Deployment Script**
   - **Command**: `.venv/bin/python deploy_agent_engine.py`
   - **Expected Outcome**: The script should run without errors and print the resource name of the created agent engine.
   - **Status**: ✅ Completed. Resource Name: `projects/803095609412/locations/us-central1/reasoningEngines/7116122817849982976`

### Testing Strategy
- Create a test script `test_agent_engine.py`.
- The script will:
  1. Initialize Vertex AI.
  2. Get the agent engine using `agent_engines.get(RESOURCE_NAME)`.
  3. Create a new session with the agent.
  4. Send a query to the agent (e.g., "Show me all the tickets with status Open").
  5. Print the agent's response.
- This will verify that the agent is deployed correctly and is functional.

## 🎯 Success Criteria
- The `deploy_agent_engine.py` script runs successfully without any pickling or import errors.
- A new agent engine is created in the Vertex AI console.
- The test script can successfully interact with the deployed agent and get a valid response.

## 📅 Session Summary (2025-11-17)

### Actions Taken
1.  **Fixed Pickling Issues**:
    - Implemented `LazyToolboxTool` wrapper in `adk_bug_ticket_agent/tools/tools.py` to handle `ToolboxSyncTool` pickling during deployment.
    - Updated `get_toolbox_tools` to use this wrapper.
    - Fixed import errors related to `toolbox_core`.

2.  **Updated Deployment Script**:
    - Modified `deploy_agent_engine.py` to include `extra_packages=["adk_bug_ticket_agent"]`. This ensures the remote environment has access to the custom `LazyToolboxTool` class.
    - Updated the requirements list in the deployment script.

3.  **Successful Deployment**:
    - Ran `deploy_agent_engine.py` successfully.
    - **Agent Engine Resource Name**: `projects/803095609412/locations/us-central1/reasoningEngines/7116122817849982976`

4.  **Testing & Troubleshooting**:
    - Created `test_agent_engine.py` to verify the deployed agent.
    - Iteratively fixed issues in the test script:
        - Switched from `agent_engine.query()` to `create_session` + `stream_query` flow.
        - Added required `user_id` to `create_session`.
        - Handled session object as a dictionary (extracted `session['id']`).
    - **Current Status**: The test script connects to the agent engine, but the remote execution fails with `400 Reasoning Engine Execution failed`. This indicates a runtime error within the deployed agent environment, likely related to the tool execution or initialization on the server side.

### Next Steps
- Investigate the remote logs for the Reasoning Engine to understand the cause of the `400` error.
- Verify if the `LazyToolboxTool` is correctly re-initializing the `ToolboxSyncClient` in the remote environment.
- Ensure all environment variables (like `MCP_TOOLBOX_URL`) are correctly propagated and accessible in the remote environment.