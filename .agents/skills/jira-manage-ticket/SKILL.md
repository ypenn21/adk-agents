---
name: jira-manage-ticket
description: Creates new Jira tickets or updates existing Jira tickets (summary, description, priority, type, assignee, labels, comments, status transitions) using the Atlassian CLI (`acli`).
---

# Jira Manage Ticket Skill

Use this skill to create new Jira tickets or modify existing Jira workitems using the Atlassian CLI (`acli`).

## 🔗 Reference Documentation
- **Getting Started Guide**: [Atlassian CLI (acli) Guide](https://developer.atlassian.com/cloud/acli/guides/how-to-get-started/)
- **Installation Guide**: [Install Atlassian CLI Guide](https://developer.atlassian.com/cloud/acli/guides/install-acli/)
- **CLI Commands**: `acli jira workitem create --help`, `acli jira workitem edit --help`, `acli jira workitem transition --help`, `acli jira workitem comment --help`

---

## Phase 0: Verification & Authentication

1. **Verify `acli` Installation**:
   ```bash
   acli --version
   ```

2. **Verify Authentication**:
   Ensure active authentication with Atlassian Cloud:
   ```bash
   acli auth login
   ```

---

## Phase 1: Determine Action & Scope

Identify whether the user intends to:
- **A. Create a new Jira ticket** (e.g., Story, Task, Bug, Epic)
- **B. Update an existing Jira ticket** (e.g., update description, summary, labels, assignee, transition status, add comment)

> [!IMPORTANT]
> **Default Project**: When no project is specified, always default to **`OPS`** (`project = OPS`).

---

## Phase 2: Creating a New Jira Ticket

### Method 1: CLI Direct Creation (Standard Plain Text Description)

For standard ticket creation with a plain text description:

1. Write the description to a temporary file:
   ```bash
   cat << 'EOF' > /tmp/desc.txt
   #### Overview
   Feature overview and scope details...

   #### Acceptance Criteria
   [ ] Criteria 1
   [ ] Criteria 2
   EOF
   ```

2. Execute `acli jira workitem create`:
   ```bash
   acli jira workitem create \
     --project "OPS" \
     --type "Story" \
     --summary "<SUMMARY_TITLE>" \
     --description-file "/tmp/desc.txt" \
     --label "ci-cd,automation" \
     --json
   ```

---

### Method 2: JSON Payload Creation (Priority, ADF Formatting, & Attributes)

To specify priority (e.g. `Highest`, `High`, `Medium`, `Low`), custom attributes, or formatted rich text on creation:

1. Create a JSON payload (e.g., `/tmp/ticket.json`):
   ```json
   {
     "projectKey": "OPS",
     "summary": "pr_reviewer_agent: Deduplicate PR review comments across pipeline runs",
     "type": "Story",
     "additionalAttributes": {
       "priority": {
         "name": "High"
       }
     },
     "labels": [
       "ci-cd",
       "pr-reviewer",
       "automation"
     ],
     "description": {
       "type": "doc",
       "version": 1,
       "content": [
         {
           "type": "heading",
           "attrs": { "level": 2 },
           "content": [{ "type": "text", "text": "Overview" }]
         },
         {
           "type": "paragraph",
           "content": [{ "type": "text", "text": "Feature description and requirements..." }]
         },
         {
           "type": "heading",
           "attrs": { "level": 2 },
           "content": [{ "type": "text", "text": "Acceptance Criteria" }]
         },
         {
           "type": "bulletList",
           "content": [
             {
               "type": "listItem",
               "content": [{ "type": "paragraph", "content": [{ "type": "text", "text": "Item 1" }] }]
             }
           ]
         }
       ]
     }
   }
   ```

2. Execute `acli jira workitem create --from-json`:
   ```bash
   acli jira workitem create --from-json "/tmp/ticket.json" --json
   ```

3. Extract the created ticket key (e.g., `OPS-16`).

---

## Phase 3: Updating Existing Jira Tickets

When modifying an existing ticket by key (e.g., `OPS-16`):

### 1. Update Priority
Update the ticket priority level (`Highest`, `High`, `Medium`, `Low`, `Lowest`):
```bash
acli jira workitem edit --key <KEY> --priority "<PRIORITY_LEVEL>" --yes
```
*Example*:
```bash
acli jira workitem edit --key OPS-16 --priority "High" --yes
```

### 2. Update Status (Workflow Transitions)
Transition the ticket across workflow states (e.g., `To Do`, `In Progress`, `In Review`, `Done`):
```bash
acli jira workitem transition --key <KEY> --status "<STATUS_NAME>" --yes
```
*Transitioning by JQL*:
```bash
acli jira workitem transition --jql "project = OPS AND key = 'OPS-16'" --status "In Progress" --yes
```

### 3. Update Summary
```bash
acli jira workitem edit --key <KEY> --summary "<NEW_SUMMARY>" --yes
```

### 4. Update Description
Using a plain text file:
```bash
acli jira workitem edit --key <KEY> --description-file "/tmp/update_desc.txt" --yes
```
Or inline text:
```bash
acli jira workitem edit --key <KEY> --description "<NEW_DESCRIPTION_TEXT>" --yes
```

### 5. Update Labels
```bash
acli jira workitem edit --key <KEY> --labels "<LABEL_1>,<LABEL_2>" --yes
```

### 6. Assign Ticket
- Self-assign:
  ```bash
  acli jira workitem edit --key <KEY> --assignee "@me" --yes
  ```
- Assign to user email or account ID:
  ```bash
  acli jira workitem edit --key <KEY> --assignee "<EMAIL_OR_ACCOUNT_ID>" --yes
  ```

### 7. Change Issue Type
```bash
acli jira workitem edit --key <KEY> --type "Task" --yes
```

### 8. Add Comments
Add a comment to the workitem discussion:
```bash
acli jira workitem comment add --key <KEY> --body "<COMMENT_TEXT>"
```

### 9. Add Attachments
Attach files or reports to the ticket:
```bash
acli jira workitem attachment add --key <KEY> --file "<FILE_PATH>"
```

---

## Phase 4: Verification & Presentation

1. **Verify Ticket State**:
   Retrieve the latest ticket metadata:
   ```bash
   acli jira workitem view <KEY>
   ```
   Or structured JSON:
   ```bash
   acli jira workitem view <KEY> --json
   ```

2. **Present Formatted Markdown Summary**:
   Display the final ticket status and fields clearly to the user:

   ```markdown
   ### 🎫 [<ISSUE_KEY>] <SUMMARY>

   | Field | Value |
   | :--- | :--- |
   | **Key** | `<ISSUE_KEY>` |
   | **Project** | `<PROJECT>` |
   | **Type** | `<TYPE>` |
   | **Priority** | `<PRIORITY>` |
   | **Status** | `<STATUS>` |
   | **Assignee** | `<ASSIGNEE>` |
   | **Labels** | `<LABELS>` |

   #### Description
   <DESCRIPTION>
   ```

3. **Clean Up Scratch Files**:
   Remove any temporary JSON or text payload files created during the operation.
