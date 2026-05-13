---
name: spec
description: Create a formal product specification. Use when gathering requirements to draft a formal Product Specification (spec) with requirements and acceptance criteria in a GitHub Issue.
---

# Create a Product Spec

## Instructions

1. **Understand Requirements:** Ensure you have enough context from the user to define the feature or fix.
2. **Concise & Crisp:** Eliminate boilerplate, checklists, and rigid Agile criteria. The spec should read like a concise, crisp problem statement and a high-level plan, similar to Gemini CLI's plan mode. Downstream autonomous agents (`tpm`, `engineer`, `qa`) will use this as their high-level objective.
   - Make zero assumptions. If a specific library or framework should be used, name it explicitly.
   - Keep it focused on the "why" and "what".
3. **Format the Spec:** Use the Markdown template below. Use standard bullet points (`-`) for the plan. Do NOT use markdown checkboxes anywhere in the spec.
4. **Publish to GitHub Issues:**
   - If an issue does not exist, create a new one using `mcp_github_create_issue` with the generated spec as the body.
   - If the issue exists, update it using `mcp_github_update_issue`.
   - **Do not write the spec to local files.** The GitHub Issue is the single source of truth.

## Spec Template

```markdown
## 🎯 Problem Statement

[A concise, crisp explanation of the problem, need, or goal based on the user's input. No more than a few sentences.]

## 🗺️ High-Level Plan

- [Key objective or step 1]
- [Key objective or step 2]
- [Key objective or step 3]

## 🚫 Out of Scope
- [Explicitly excluded items, if any]
```
