---
name: ADK Developer
description: Master skill for building and maintaining Google ADK Python agents. Includes the ADK references such as Agent, Tool, Session, State, Runner, Event, workflow, callbacks, and common patterns. In addition, it includes evaluation guide, deployment guide, development workflow guide, ADK official documentation, operational guidelines, and commands.
---

# ADK Developer Skill

When working on this project, you are acting as an expert ADK (Agent Development Kit) Python developer. You MUST ALWAYS follow the guidelines and workflows defined in this document.

## 1. Reference Documentation

The following reference documents are included in this skill's `resources/` directory. You MUST use the `view_file` tool to read them as needed:
- **ADK Cheatsheet** (`resources/adk-cheat-sheet.md`) — Agent definitions, Tool, Session, State, Runner, Event, workflow, callbacks, orchestration, and common patterns.
- **Development Guide** (`resources/development-workflow.md`) — Full development workflow
- **Operational Guidelines** (`resources/operational-guidelines.md`) — Operational guidelines for coding agents

For topics not covered locally, fetch these external resources as needed:
- **ADK Cheatsheet**: https://raw.githubusercontent.com/GoogleCloudPlatform/agent-starter-pack/refs/heads/main/agent_starter_pack/resources/docs/adk-cheatsheet.md —  Agent definitions, Tool, Session, State, Runner, Event, workflow, callbacks, orchestration, and common patterns.
- **Evaluation Guide**: https://raw.githubusercontent.com/GoogleCloudPlatform/agent-starter-pack/refs/heads/main/agent_starter_pack/resources/docs/adk-eval-guide.md — Eval config, metrics, gotchas
- **Deployment Guide**: https://raw.githubusercontent.com/GoogleCloudPlatform/agent-starter-pack/refs/heads/main/agent_starter_pack/resources/docs/adk-deploy-guide.md — Infrastructure, CI/CD, testing deployed agents
- **Development Guide**: https://raw.githubusercontent.com/GoogleCloudPlatform/agent-starter-pack/refs/heads/main/docs/guide/development-guide.md — Full development workflow
- **ADK Docs**: https://google.github.io/adk-docs/llms.txt
---

## 2. Development Phases

### Phase 1: Understand Requirements
Before writing any code, thoroughly understand the project's requirements, constraints, and success criteria.

### Phase 2: Build and Implement
Implement agent logic in `app/`. Use `make playground` for interactive testing. Iterate based on user feedback.

### Phase 3: The Evaluation Loop (Main Iteration Phase)
Start with 1-2 eval cases, run `make eval`, and iterate. Expect 5-10+ iterations. See the **Evaluation Guide** for metrics, evalset schema, LLM-as-judge config, and common gotchas.

### Phase 4: Pre-Deployment Tests
Run `make test`. Fix issues until all tests pass successfully.

### Phase 5: Deploy to Dev
**Requires explicit human approval.** Run `make deploy` only after the user confirms. See the **Deployment Guide** for detailed instructions.

### Phase 6: Production Deployment
Ask the user: Option A (simple single-project) or Option B (full CI/CD pipeline with `uvx agent-starter-pack setup-cicd`). See the deployment docs for step-by-step instructions.

---

## 3. Development Commands

| Command | Purpose |
|---------|---------|
| `make playground` | Interactive local testing |
| `make test` | Run unit and integration tests |
| `make eval` | Run evaluation against evalsets |
| `make eval-all` | Run all evalsets |
| `make lint` | Check code quality |
| `make setup-dev-env` | Set up dev infrastructure (Terraform) |
| `make deploy` | Deploy to dev |

---

## 4. Operational Guidelines for Coding Agents

- **Code preservation**: Only modify code directly targeted by the user's request. Preserve all surrounding code, config values (e.g., `model`), comments, and formatting.
- **NEVER change the model** unless explicitly asked. Use `gemini-3-flash-preview` or `gemini-3-pro-preview` for new agents.
- **Model 404 errors**: Fix `GOOGLE_CLOUD_LOCATION` (e.g., `global` instead of `us-central1`), not the model name.
- **ADK tool imports**: Import the tool instance, not the module: `from google.adk.tools.load_web_page import load_web_page`
- **Run Python with `uv`**: `uv run python script.py`. Run `make install` first.
- **Stop on repeated errors**: If the same error appears 3+ times, fix the root cause instead of retrying to brute-force a fix.
- **Terraform conflicts** (Error 409): Use `terraform import` instead of retrying creation.
