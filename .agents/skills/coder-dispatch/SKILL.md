---
name: coder-dispatch
description: Dispatch coding tasks to the remote coder-agent deployed on Gemini Enterprise Agent Platform (GEAP) from GitHub issues or Jira workitems, and follow execution live until completion.
---

# Coder Dispatch Skill

Dispatch coding jobs to the `coder-agent` deployed on Google Cloud Agent Platform (GEAP) using the `geap` MCP tools, resolve requirements from GitHub issues or Jira tickets (via `acli`), and stream the agent's progress in real time.

## Required Tools & Prerequisites

- `call_mcp_tool` (for `geap` MCP server tools: `list_agents`, `start_query`, `read_query`)
- `run_command` (for querying local git context and executing Atlassian CLI `acli` commands)
- `ask_question` (for clarifying ambiguous or missing parameters)
- `view_file` & `list_dir` (for inspecting repository files)

---

## 1. Inspect and Clarify Parameters

> [!IMPORTANT]
> **Mandatory First Question:** Always use the `ask_question` tool as the very first step to ask the user whether they want to use **Jira Tickets** or **GitHub Issues** as the task source (unless already explicitly answered in their command):
> - Option 1: `(Recommended) Jira Ticket (via acli)`
> - Option 2: `GitHub Issue`

Before dispatching, ensure all required parameters (`owner/repo`, `COMMIT_SHA`, `branch_name`, and `issue`) are clear and resolved. If any parameter is ambiguous, missing, or has multiple possibilities, utilize the `ask_question` tool to clarify with the user before proceeding.

### A. Task Source Resolution (Jira or GitHub)

1. **Jira Ticket via Atlassian CLI (`acli`)**:
   - Verify `acli` authentication: `acli auth login` (if needed).
   - **Target Ticket Resolution & Search**:
     - If a specific Issue Key was not explicitly provided by the user, search for recent issues:
       ```bash
       acli jira workitem search --jql "project = OPS ORDER BY created DESC" --limit 10
       ```
     - **Display Tickets**: Print/show the search results table or list of retrieved Jira tickets (Key, Type, Priority, Status, Summary) to the user.
     - **Prompt for Selection**: Use the `ask_question` tool to present the list of tickets as options (formatted e.g. `<KEY>: <Summary>`) so the user can choose which ticket to proceed with.
     - Once a ticket key is selected (or if provided directly), retrieve full ticket details if needed:
       ```bash
       acli jira workitem view <KEY> --json
       ```
   - **Ticket Extraction**:
     - Extract Issue Key (e.g., `OPS-9`), Summary, Status, Priority, and Description.
   - **Optional Transition to In Progress**:
     - If requested or moving from `To Do`:
       ```bash
       acli jira workitem transition --key <KEY> --status "In Progress" --yes
       ```

2. **GitHub Issue**:
   - Identify the issue number (e.g., `"1"`).
   - If ambiguous, clarify with `ask_question`.

### B. Repository (`owner/repo`)
- Inspect `git remote get-url origin`.
- Extract `<owner>/<repo>` (e.g., `ypenn21/workshop-agentic-sdlc-lab`, verifying it targets the expected repository ending in `-lab`).
- If the repository cannot be determined automatically or is ambiguous, prompt the user using `ask_question`.

### C. Base Commit (`COMMIT_SHA`)
- Determine the current active branch (e.g., `git branch --show-current`) and its latest commit (e.g., `git rev-parse HEAD` or `git rev-parse "origin/$(git branch --show-current)"`).
- Ensure the commit has been pushed to the remote repository so the remote agent can clone and checkout the exact SHA.
- If the target base branch or commit is ambiguous, clarify with `ask_question`.

### D. Target Branch (`branch_name`)
- Determine the target branch name to push changes to:
  - For GitHub issues: default `agent/parse` (or `agent/issue-<issue_number>`).
  - For Jira tickets: default `agent/<key-in-lowercase>` (e.g., `agent/ops-9`) or `agent/parse`.
### E. Mandatory Pre-Dispatch Parameter Confirmation Gate

> [!IMPORTANT]
> **MANDATORY PRE-DISPATCH PARAMETER CONFIRMATION:**
> Before calling `start_query` or dispatching any coding job to `coder-agent`, you MUST pause and present the resolved parameters to the user for explicit confirmation:
> - **Repository (`repo`)**: `<owner>/<repo>`
> - **Commit SHA (`sha`)**: `<COMMIT_SHA>`
> - **Target Branch (`branch`)**: `<branch_name>`
> - **Issue Key / Number (`issue`)**: `<issue_key_or_number>`
>
> **Actionable Directive:**
> 1. Display the four resolved parameters clearly in the conversation.
> 2. Use `ask_question` (or inline prompt) asking: *"Please confirm the dispatch parameters: Are the SHA (`<sha>`), target branch (`<branch>`), and issue (`<issue>`) correct, or do you want to modify them before dispatching?"*
> 3. If the user provides modifications or alternative values, update the parameters accordingly.
> 4. **NEVER** dispatch the job without this explicit human confirmation.

---

## 2. Locate the Deployed Agent

1. Call the `list_agents` tool on the `geap` MCP server (passing `project` and `location`, e.g., `us-central1`).
2. Verify that `coder-agent` exists, `deployed` is `true`, and note its engine name / ID.

---

## 3. Dispatch the Job (`start_query`)

1. Construct the payload JSON string:
   ```json
   {"repo": "<owner>/<repo>", "sha": "<COMMIT_SHA>", "branch": "<branch_name>", "issue": "<issue_number_or_jira_key>"}
   ```
   *Examples:*
   - GitHub Issue: `{"repo": "ypenn21/workshop-agentic-sdlc-lab", "sha": "41007b892cfb...", "branch": "agent/parse", "issue": "1"}`
   - Jira Ticket: `{"repo": "ypenn21/workshop-agentic-sdlc-lab", "sha": "41007b892cfb...", "branch": "agent/ops-9", "issue": "OPS-9"}`

2. Call the `start_query` tool on `geap` with:
   - `engine`: `"coder-agent"` (or the engine's resource name / ID)
   - `message`: The JSON payload string above.
   - `location`: `"us-central1"` (or configured region)
   - `project`: The active project ID (e.g., from `gcloud config get-value project`)
3. Note the returned `run_id`.

---

## 4. Follow the Run Trajectory (`read_query`)

1. Initialize `cursor` to `0`.
2. In a loop, call `read_query` on `geap` with `run_id` and the current `cursor`.
3. For each call:
   - **Stream Output**: Print any newly returned `lines` immediately before making the next call.
   - Update `cursor` to `next_cursor`.
   - Check `state`:
     - If `state` is `"running"`, continue polling in the loop.
     - If `state` is `"done"` or any terminal status, exit the loop.

---

## 5. Report Summary & Next Steps

When the run finishes:
1. Print the final narration lines and tool call metrics.
2. Present a clear summary containing:
   - Repository and base commit SHA dispatched
   - Branch where changes were pushed
   - Associated issue (GitHub Issue or Jira Ticket Key & Summary)
   - GitHub compare link: `https://github.com/<owner>/<repo>/compare/<base_branch>...<branch>`
   - Next steps for testing and reviewing the branch:
     ```bash
     git fetch origin <branch> && git checkout -b review origin/<branch> && uv run pytest -q
     ```
3. **Jira Follow-up (if Jira ticket was used)**:
   - Optionally update or transition the Jira ticket status (e.g., to `In Review` or `Done`):
     ```bash
     acli jira workitem transition --key <KEY> --status "In Review" --yes
     ```
