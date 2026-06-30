---
trigger: always_on
---

# Best Practices for Building ADK Python Agents

## 1. General Principles & Code Preservation

- **Surgical Precision:** When modifying code, alter _only_ the specific lines targeted by a request. Strictly preserve all surrounding code, configuration values (like `model`, `version`, `api_key`), comments, and formatting.
- **Follow the Spec First:** Always check `conductor/product.md`, `conductor/workflow.md`, or the `plan/` directory before building. These files are the source of truth for features and constraints.
- **Location vs. Model Errors:** If you hit a 404 error using a model, it is almost always a `GOOGLE_CLOUD_LOCATION` issue (e.g., using `global` instead of `2`), rather than a wrong model name. Never change the `model` property to try to "fix" a 404.

## 2. Best Practices for ADK Agent Architecture

- **Agent-Executor Pattern:** Utilize a `ServiceManager` (typically in `app/agent.py`) to lazily load and manage singletons for the Agent and Services (e.g., `SessionService`, `MemoryService`).
- **Specific Built-in Tool Imports:** When using ADK built-in tools, import the _tool instance_ directly, not the module (e.g., use `from google.adk.tools.load_web_page import load_web_page`, and pass it as `tools=[load_web_page]`).
- **Model Selection:** Never change the model unless explicitly asked. If creating a brand new agent, default to `gemini-3-flash-preview` or `gemini-3-pro-preview`.
- **Separation of Concerns:**
  - Place agent configuration in `app/agent.py`.
  - Place system prompts and pure business logic functions in `app/strategies.py`.
  - Place custom tools (using `FunctionTool`) in `app/tools.py`.

## 3. Iteration & The Evaluation Loop

- **Fail Fast on Repeated Errors:** Stop immediately if the same error happens 3+ times. Fix the root cause instead of looping through retries. Do not try to workaround tool bugs; fix the source instead.
- **Start Small with Evals:** When testing logic via `make eval`, begin with 1-2 core evaluation cases in `tests/eval/evalsets/` to validate the core trajectory before running a full test suite. Expect 5-10 iterations to get these passing perfectly.
- **Focus on Trajectory & Response Match:** When evaluating, check the `tool_trajectory_avg_score` (are tools called in the right order?) and the `response_match_score` (do responses match the expected pattern?).

## 4. Local Execution & Environments

- **Use `uv` for Python:** Always execute scripts and application code using `uv run python script.py`. Ensure you run `make install` first.
- **Use Make:** Rely on the included `Makefile` commands to maintain consistency:
  - `make playground` for interactive local testing on `localhost:8000`.
  - `make test` before deploying code.
  - `make eval` for running rubrics over test cases.

## 5. Deployment Protocol

- **Pre-Deployment Testing:** Run `make test` and resolve all unit/integration test issues before proceeding to deployments.
- **Explicit Human Approval for Dev:** Never run `make deploy` to push an agent to the development environment without explicit human sign-off.
- **Production Deployment Path:** Always clarify with the user if they want a simple single-project push (`setup-dev-env` -> `deploy`) or a full CI/CD pipeline.
