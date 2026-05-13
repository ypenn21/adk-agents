---
name: tech-spec
description: Create a technical implementation plan. Use when drafting a technical specification for a feature or bug fix based on the PM's product spec, enforcing checkboxes and testing workflows.
---

# Create a Technical Spec

## Instructions

1. **Understand Context:** Read the PM's specification from the GitHub issue.
2. **Agentic Clarity:** The `engineer` and `qa` agents execute this plan autonomously. Your instructions MUST be deterministic and absolute.
   - **Absolute Paths:** Always use exact, absolute file paths from the repository root (e.g., `apps/ui/src/App.tsx`, not just `App.tsx`).
   - **Imperative Execution:** Write steps as exact terminal commands or explicit file modifications (e.g., "Run `npm install react-router-dom` in `apps/hitl`").
   - **Separation of Concerns:** Explicitly separate project scaffolding/setup steps from business logic steps.
   - **Testable Assertions:** Write test cases so the `qa` agent can literally translate them into Vitest/Jest code (e.g., "Assert that `<Sidebar>` contains `<Link href='/claims'>`").
3. **Format the Plan:** Use the Markdown template below. It is **mandatory** to use `- [ ]` checkboxes for Architecture Steps, File Changes, and Test Cases.
4. **Publish to GitHub Issues:** Append the technical plan to the original GitHub issue via `mcp_github_update_issue` or `mcp_github_add_issue_comment`. **Do not write the spec to local files.**

## Technical Spec Template

```markdown
## 🏗️ Technical Specification

**Architectural Approach:** [Briefly describe the design pattern or architecture to be used]

### 🔍 Affected Files
- [ ] `path/to/file1.ts`: [Describe changes]
- [ ] `path/to/file2.ts`: [Describe changes]

### 📋 Implementation Steps (Engineer)
- [ ] Step 1: [Detailed action]
- [ ] Step 2: [Detailed action]

### 🧪 Required Tests (QA)
- [ ] Test Case 1: [What must be tested and how]
- [ ] Test Case 2: [What must be tested and how]

### 🚀 Platform / DevOps Steps (Platform)
- [ ] Step 1: [If applicable, e.g., update Dockerfile or env vars]
- [ ] N/A
```