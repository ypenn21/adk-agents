# Agent Farm Gemini CLI Extension

A Gemini CLI extension that provides a specialized team of autonomous software development subagents and expert skills to help with engineering, QA, product management, and platform operations.

## Features

- **Custom Agents:** Includes specialized AI personas (e.g., Engineer, Platform, PM, QA, TPM, Librarian) for different phases of the software development lifecycle.
- **Expert Skills:** Bundles actionable workflows (e.g., brainstorm, create-pr, debug, docs, git-hygiene, spec, tech-spec) and ADK agent development skills (`google-agents-cli-adk-code`, `google-agents-cli-deploy`, `google-agents-cli-eval`, `google-agents-cli-observability`, `google-agents-cli-publish`, `google-agents-cli-scaffold`, `google-agents-cli-workflow`).
- **GitHub MCP Server:** Automatically configures the GitHub Model Context Protocol server for seamless repository interaction.

## Prerequisites

- [Gemini CLI](https://github.com/google/gemini-cli) installed globally.
- Ensure `experimental.enableAgents` is set to `true` in your personal `~/.gemini/settings.json`.

## Installation

If you are using the full Agent Farm Orchestrator scaffolding, this extension is included in the `extensions/agent-farm` directory.

To link the extension locally with the Gemini CLI, run the following from the root of the repository:
```bash
gemini extensions link ./extensions/agent-farm
```
*(Alternatively, you can run `gemini extensions link .` from within this directory)*

## Configuration

This extension utilizes the `@modelcontextprotocol/server-github` MCP server. You will need to provide your personal GitHub token for it to authenticate successfully.

1. Create a personal access token (classic or fine-grained) with Repo permissions on GitHub.
2. The Gemini CLI will automatically prompt you to provide your `GitHub Personal Access Token` when linking or installing the extension. The value is stored securely in your OS keychain.

## Temporary Files
Agent Farm subagents generate drafts, scratchpads, and intermediate files during workflow execution. These are centrally located in the `.agentfarm/` directory at the project root, which is ignored by version control to prevent repository clutter.

## Usage

- **Start Planning:** Quickly kick off a new feature or issue with the PM agent:
  ```bash
  @pm create a new login page
  ```
- **Refine Technical Plans:** Pull GitHub issues requiring TPM attention to formulate an implementation plan:
  ```bash
  @tpm <issue_number>
  ```
- **Check Dashboard:** View the current state of the Agent Farm:
  ```bash
  /farm:status
  ```
- **List Agents:** Start a chat and view the available agents:
  ```bash
  /agents
  ```
- **Direct Delegation:** Delegate tasks to a specific agent:
  ```bash
  @engineer Please implement the login page.
  ```
- **Skills:** View and activate available skills:
  ```bash
  /skills list
  /skills activate brainstorm
  ```
