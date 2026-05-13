# Agent Farm Team Workflows

This workspace uses a specialized set of sub-agents to manage a customized Agile software development lifecycle within a single repository.

## The State Machine & Phases

The lifecycle of any feature or bug fix follows these strict phases, tracked via GitHub Issue labels.

**1. PM Planning Phase**
- **Trigger:** A new feature request or idea from the user.
- **Action:** The Orchestrator FIRST uses the `codebase_investigator` sub-agent to gather context and map out the current repository. Once context is gathered, the Orchestrator invokes the `pm` sub-agent and provides it with those findings to draft a formal feature specification. The draft is published as a new GitHub Issue.
- **Label:** `status: pm-review` (Applied upon issue creation).
- **Command:** `@pm <prompt>`

**2. PM Refinement Phase**
- **Trigger:** An issue exists with the `status: pm-review` label.
- **Action:** The Orchestrator facilitates a collaborative, interactive review of the spec with the user in the main chat. The Orchestrator directly updates the GitHub issue with any agreed-upon changes.
- **Command:** `@pm <issue_number>`

**3. TPM Planning Phase**
- **Trigger:** The PM specification is approved by the user (or PM lead).
- **Action:** The issue is labeled `status: needs-tpm`. The Orchestrator FIRST uses the `codebase_investigator` sub-agent to analyze the target codebase. Then, it invokes the `tpm` sub-agent and provides the gathered context along with the PM spec to draft a step-by-step Technical Implementation Plan, which is appended to the issue body.
- **Label:** `status: tpm-review` (Applied upon plan creation).
- **Command:** `@tpm <issue_number>`

**4. TPM Refinement Phase**
- **Trigger:** An issue exists with the `status: tpm-review` label.
- **Action:** The Orchestrator facilitates an interactive architectural Q&A with the user in the main chat to refine the technical plan. The Orchestrator directly updates the GitHub issue.
- **Command:** `@tpm <issue_number>`

**5. QA Phase (Headless CI/CD)**
- **Trigger:** The issue is labeled `status: needs-qa` (typically via an approval command or an iteration toggle).
- **Action:** A GitHub Action triggers the `qa` agent. It reads the TPM plan, writes failing TDD tests, and pushes commits to a Draft Pull Request. It *must* ingest any existing PR review feedback if this is an iteration.
- **Automation:** Orchestrated via `.github/workflows/agent-orchestrator.yaml` and verified by `pr-review.yaml`.

**6. Engineer Phase (Headless CI/CD)**
- **Trigger:** An issue exists with the `status: needs-engineer` label.
- **Action:** A GitHub Action triggers the `engineer` agent. It implements the code to pass the QA tests and pushes commits to the PR. It *must* ingest any existing PR review feedback if this is an iteration.
- **Automation:** Orchestrated via `.github/workflows/agent-orchestrator.yaml` and verified by `pr-review.yaml`.

**7. Automated Review Phase (Stateless Gatekeeper)**
- **Trigger:** The PR receives new commits (via `opened` or `synchronize` events from the QA or Engineer agents).
- **Action:** The `pr-review.yaml` workflow triggers the `reviewer` agent. It leaves inline code review comments.
  - **If Approved:** It advances the issue state (`needs-qa` -> `needs-engineer`, or `needs-engineer` -> `ready-to-merge`).
  - **If Rejected:** It increments a `review:X` label and toggles the current state label to re-trigger the QA or Engineer agent. If the review count reaches the limit, it sets `status: review-stuck` for human intervention.

## Label Taxonomy

The Agent Farm utilizes three distinct types of labels to manage issue lifecycles and agent routing.

### State Labels
These labels track the progress of an issue through the development lifecycle and trigger specific agent actions.
- `status: pm-review`: Issue is being drafted by the PM agent.
- `status: needs-tpm`: PM spec is approved; needs a technical plan from the TPM agent.
- `status: tpm-review`: Technical plan is being drafted by the TPM agent.
- `status: needs-qa`: TPM plan is approved or needs rework; needs failing tests from the QA agent.
- `status: needs-engineer`: QA tests are approved or needs rework; needs implementation from the Engineer agent.
- `status: ready-to-merge`: Implementation is complete and approved by reviewer; awaits human merge.
- `status: review-stuck`: The agent is stuck in an iteration loop and requires human intervention.
- `status: needs-platform`: Needs infrastructure or DevOps changes from the Platform agent.
- `status: needs-librarian`: Needs documentation or repository hygiene from the Librarian agent.

### Category Labels
These labels provide context about the work and can override or bypass standard state-based routing.
- `type: bug`: Indicates a defect. Triggers the inclusion of "Steps to Reproduce" in PM specifications.
- `type: feature`: Indicates a new feature request.
- `type: doc`: Documentation-only change. Bypasses automated QA and Engineer steps, directly routing to the Librarian.
- `type: platform/devops`: Infrastructure-focused work. Can trigger the Platform agent directly from a `status: needs-qa` state.

### Priority Labels
These labels are applied by the Triager to help the PM and team prioritize work.
- `priority: high`: Security vulnerabilities, crashes, or blocked core flows.
- `priority: medium`: Standard features or non-critical bugs.
- `priority: low`: Minor UI tweaks, typos, or tech debt.

### Metadata Labels
These labels provide additional information and are explicitly ignored by the automated orchestrator to prevent unnecessary CI runs.
- `good-first-issue`: Easy tasks for new contributors.
- `easy-issue`: Simple tasks.
- `development`: Internal development or tracking issues.
- `hold`: Circuit breaker. Halts ALL automated workflows on the issue when present.
- `flag: no-tests-needed`: Bypasses the QA testing phase, routing directly to the Engineer agent.

## Specialized Support Agents

In addition to the core lifecycle agents, the Orchestrator has access to specialized support agents:

- **Librarian:** Technical Documentation & Hygiene Engineer. Handles proactive repository audits, documentation, and resolves architectural drift. Handled manually or automatically via the `status: needs-librarian` label.
- **Platform:** Cloud & DevOps Engineer. Focuses on environment setup, infrastructure, networking, containerization, and deployment.

## ADK Agent Development

When building out an ADK (Agent Development Kit) app, sub-agents have access to a suite of `google-agents-cli-*` skills to guide development:
- **`google-agents-cli-adk-code`**: For agent API patterns, tool definitions, and state management (Engineer).
- **`google-agents-cli-scaffold`**: For creating new projects and scaffolding (TPM).
- **`google-agents-cli-workflow`**: For workflow orchestration and internal patterns (TPM).
- **`google-agents-cli-eval`**: For evaluation methodology, evalsets, and LLM-as-judge (QA).
- **`google-agents-cli-deploy`**: For CI/CD, Cloud Run, and GKE deployment (Platform).
- **`google-agents-cli-observability`**: For tracing, monitoring, and Agent Analytics (Platform).
- **`google-agents-cli-publish`**: For publishing agents to Gemini Enterprise (Platform).

## Core Directives for All Agents

*   **Makefile Preference:** Always first refer to the `Makefile` to check for `test`, `lint`, `build`, and `dev` commands before running language-specific or framework-specific commands.
*   **Interactive Refinement:** The "Refine" phases are *never* delegated to background sub-agents. The Orchestrator must handle refinement interactively in the main chat to prevent black-box assumptions.
*   **Clean Up:** Any temporary directories created for the purpose of codebase investigation MUST be immediately deleted after the context is gathered to prevent disk bloat.
*   **Temporary Files:** All temporary files, draft documents, or intermediate state MUST be stored in the `.agentfarm/` directory at the project root. This directory is ignored by version control.
*   **Strict Delegation Mandate:** The main Orchestrator agent MUST NOT perform specialized tasks (e.g., drafting PM specifications, writing TPM technical plans, writing code) directly. It must strictly act as a router and orchestrator. When a workflow phase calls for a specific agent (e.g., 'the Orchestrator delegates to the tpm agent'), the Orchestrator MUST invoke that sub-agent tool, pass the required instructions and context in the query, and wait for its completion. Never bypass sub-agents to execute their tasks directly.
*   **Testing Only Application Code:** Automated tests should ONLY be written for application code (e.g., Python, React, TypeScript).
    *   Explicitly prohibiting bash shell-type tests for meta improvements on the repository; infrastructure and bash code must rely on human PR reviews instead.
    *   Standardized test frameworks: use `pytest` (with `pytest-mock` for mocking) for Python, `vitest` alongside `@testing-library/react` for React/TypeScript unit/component tests, and `playwright` for integration/UI testing.
