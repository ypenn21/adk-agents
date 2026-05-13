---
name: create-pr
description: Standardize Pull Request creation. Use whenever creating a new Pull Request or updating an existing PR description to ensure proper linking and formatting.
---

# Create a Pull Request

## Instructions

1. **Review Context:** Identify the issue number and the changes made in your branch.
2. **Format Description:** Use the PR Template provided below.
3. **Link Issue (Conditional Auto-Close):** Link the PR to the original issue depending on the completion status of the issue's checkboxes:
   - Fetch and read the original issue body.
   - If **all** task checkboxes in the entire issue (PM Requirements, TPM Steps, QA Tests, Platform infra) are marked as complete (`- [x]`), use `Closes <org>/<repo>#<Issue-Number>` in your PR description.
   - If there are **any** incomplete checkboxes (`- [ ]`) remaining for other agents to work on, use `Updates <org>/<repo>#<Issue-Number>` instead. This links the PR without prematurely closing the issue.
4. **Create/Update PR:** If continuing work on an existing PR (provided via `pull_request: <number>`), do NOT create a new PR. Instead, use `mcp_github_update_pull_request` to update the existing PR description with the template below. Otherwise, use `mcp_github_create_pull_request` to create a new one.
5. **No Merging:** NEVER merge the Pull Request yourself. A Human-in-the-loop (HITL) will perform the final review and merge the PR.

## PR Template

```markdown
### Description
[Provide a clear and concise description of the changes introduced in this PR. Explain the "what" and the "why".]

### Changes
- [ ] Added `[Feature A]`
- [ ] Updated `[Component B]`
- [ ] Fixed `[Bug C]`

### Verification
- [ ] Tests pass locally (`npm test`, `pytest`, etc.)
- [ ] Linter/formatter checks pass
- [ ] I have manually verified these changes (where applicable)

### Linked Issues
[Closes | Updates] <org>/<repo>#<Issue-Number>
```