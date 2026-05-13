---
name: update-issue
description: Standardize GitHub Issue updates. Use whenever parsing, checking off tasks, or otherwise modifying the markdown body of an existing GitHub Issue via `mcp_github_update_issue` to ensure formatting and checkboxes are perfectly preserved.
---

# Safe GitHub Issue Updates

## Instructions

When updating a GitHub issue (especially when checking off `- [ ]` task list boxes), you MUST follow these strict rules to prevent destroying the issue's Markdown formatting:

1. **Fetch Latest State:** Always fetch the most recent body of the issue via `mcp_github_get_issue` immediately before attempting an update. Do not rely on cached or older versions of the issue text.
2. **Preserve Newlines:** You must treat the `body` field of the issue exactly as it is. When replacing text (like checking a box), ensure that you use exact string replacement on the specific line. 
3. **DO NOT generate JSON manually:** When using the `mcp_github_update_issue` tool, pass the modified markdown string directly to the `body` parameter. Let the underlying tool handle the JSON serialization and escaping. 
4. **Targeted Replacement:** If you need to check off a box for "Step 1", only replace `- [ ] Step 1:` with `- [x] Step 1:`. Do NOT attempt to rewrite or regenerate the entire issue body from scratch.
5. **Verify Formatting:** If your change modifies the structural layout of the issue beyond checking a box (e.g. appending a new section), ensure you include double newlines (`\n\n`) between major headings.
6. **Preserve Labels (CRITICAL):** Unless your specific system prompt instructs you to manage the state machine or update labels, you MUST NOT include the `labels` parameter when calling `mcp_github_update_issue` to update the issue body. Doing so will accidentally overwrite or modify the issue's state machine and bypass gatekeepers.