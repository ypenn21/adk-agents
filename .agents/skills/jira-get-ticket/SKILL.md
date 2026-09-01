---
name: jira-get-ticket
description: Retrieves and inspects Jira tickets or workitems using the Atlassian CLI (`acli`), including searching for issues, fetching complete field metadata, descriptions, and statuses.
---

# Jira Get Ticket Skill

Use this skill to search for, inspect, and retrieve full details of a Jira ticket/workitem using the Atlassian CLI (`acli`).

## 🔗 Reference Documentation
- **Getting Started Guide**: [Atlassian CLI (acli) Guide](https://developer.atlassian.com/cloud/acli/guides/how-to-get-started/)
- **Installation Guide**: [Install Atlassian CLI Guide](https://developer.atlassian.com/cloud/acli/guides/install-acli/)
- **CLI Commands**: `acli jira workitem --help`, `acli jira workitem view --help`, `man acli`

---

## Phase 0: Installation & Authentication

1. **Verify & Install `acli`**:
   Check if `acli` is installed:
   ```bash
   acli --version
   ```
   
2. **Mandatory Authentication**:
   Ensure authentication before executing Jira operations:
   ```bash
   acli auth login
   ```

---

## Phase 1: Search & Identify Jira Ticket

When the ticket key is not explicitly provided or when searching for relevant issues:

> [!IMPORTANT]
> **No Unbounded JQL Queries**: Jira Cloud strictly prohibits unbounded queries (e.g., `ORDER BY created DESC` without a filter). Every JQL query MUST include a search restriction such as `project = OPS`.
>
> **Default Project**: If no project is specified by the user, **default to `OPS`**.

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
     ```

2. **Discover Other Projects (Only if requested or needed)**:
   ```bash
   acli jira project list --limit 10 --json
   ```

3. **Clarify Ambiguous Ticket**:
   - If multiple candidate tickets match and no specific key was requested, prompt the user with `ask_question` to select the target ticket.

---

## Phase 2: Retrieve Full Ticket Details

1. **Retrieve Ticket JSON**:
   Fetch full metadata and description for a specific ticket key (e.g., `OPS-9`):
   ```bash
   acli jira workitem view <ISSUE_KEY> --json
   ```
   *Example*:
   ```bash
   acli jira workitem view OPS-9 --json
   ```

2. **View Formatted Ticket**:
   View standard CLI formatted view:
   ```bash
   acli jira workitem view <ISSUE_KEY>
   ```

3. **Extract Core Fields**:
   Parse and extract the following ticket fields:
   - **Key**: Issue identifier (e.g., `OPS-9`)
   - **Summary**: Title of the ticket
   - **Type**: Issue type (e.g., `Story`, `Bug`, `Task`, `Epic`)
   - **Status**: Lifecycle status (e.g., `To Do`, `In Progress`, `Done`)
   - **Priority**: Urgency level (e.g., `Highest`, `High`, `Medium`, `Low`)
   - **Assignee**: Assignee display name / account ID
   - **Reporter**: Reporter display name / account ID
   - **Description**: Ticket requirements, acceptance criteria, or defect details
   - **Labels / Components**: Categorization tags
   - **Created / Updated Dates**: Timestamp metadata

---

## Phase 3: Presenting Ticket Details

Format the retrieved ticket details cleanly for the user or downstream workflow:

```markdown
### 🎫 [<ISSUE_KEY>] <SUMMARY>

- **Type**: <TYPE>
- **Status**: <STATUS>
- **Priority**: <PRIORITY>
- **Assignee**: <ASSIGNEE>
- **Reporter**: <REPORTER>
- **Labels**: `<LABEL_1>`, `<LABEL_2>`

#### Description
<DESCRIPTION_TEXT>
```

---

## Phase 4: Optional Ticket Updates & Transition

After presenting the ticket details, prompt the user to determine if any updates or transitions should be made to the Jira ticket.

1. **Prompt for Updates**:
   Use the `ask_question` tool to ask if the user wants to update the ticket:
   - Option 1: `(Recommended) No changes needed - proceed`
   - Option 2: `Transition status (e.g., In Progress, In Review, Done)`
   - Option 3: `Assign ticket (e.g., assign to @me or a specific user)`
   - Option 4: `Edit ticket fields (Summary, Description, Priority, Type)`

2. **Execute Requested Updates via `acli`**:
   - **Transition Status**:
     ```bash
     acli jira workitem transition --key <KEY> --status "<STATUS>" --yes
     ```
   - **Assign Ticket**:
     ```bash
     acli jira workitem edit --key <KEY> --assignee "@me" --yes
     ```
   - **Edit Summary, Description, Priority, or Type**:
     ```bash
     acli jira workitem edit --key <KEY> --summary "<NEW_SUMMARY>" --yes
     acli jira workitem edit --key <KEY> --description "<NEW_DESCRIPTION>" --yes
     acli jira workitem edit --key <KEY> --priority "<PRIORITY>" --yes
     acli jira workitem edit --key <KEY> --type "<TYPE>" --yes
     ```

3. **Confirm Updates**:
   Display confirmation of the applied changes or updated ticket state to the user before proceeding.

