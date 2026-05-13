---
name: git-hygiene
description: Enforce git best practices. Use when creating new git branches, preparing to commit changes, or maintaining repository history to ensure proper naming and Conventional Commits.
---

# Git Hygiene and Standards

## Instructions

### 1. Branch Naming Conventions
When creating a new branch tied to an issue, you MUST include the issue reference in the branch name using the following format: `<type>/<issue-reference>-<short-description>`.
- If the issue is in the current repository: `feat/123-add-login`


If working proactively without an issue (e.g., Librarian direct audit), use `<type>/<short-description>`.

### 2. Commit Message Formatting (Conventional Commits)
All commit messages MUST follow the Conventional Commits format:
`<type>(<optional scope>): <description>`

**Issue References:** If the commit is tied to a GitHub issue, you MUST reference the issue in the commit message. Append it to the description or add it as a footer.
- If the issue is in the current repository: `feat: add user authentication (#123)` or `Refs: #123`.
- If the issue is in another repository: `feat: add user authentication (<org>/<repo>#123)` or `Refs: <org>/<repo>#123`.

Ensure the description is concise, written in the imperative mood (e.g., "add feature" not "added feature"), and clearly states the *why* and *what* of the change.

**Approved Commit Types:**
*   **`feat`**: A new feature (e.g., `feat(api): add user authentication endpoint`).
*   **`fix`**: A bug fix (e.g., `fix(ui): resolve overflow on mobile screens`).
*   **`doc`**: Documentation only changes. **CRITICAL:** The Librarian agent MUST ALWAYS use this type for all of its commits to prevent CI infinite loops. Example: `doc(readme): update installation instructions`.
*   **`style`**: Changes that do not affect the meaning of the code.
*   **`refactor`**: A code change that neither fixes a bug nor adds a feature.
*   **`perf`**: A code change that improves performance.
*   **`test`**: Adding missing tests or correcting existing tests.
*   **`build`**: Changes that affect the build system or external dependencies.
*   **`ci`**: Changes to CI configuration files and scripts.
*   **`chore`**: Other changes that don't modify src or test files.

### 3. Commit Scoping and Sizing
- Keep commits atomic. Each commit should represent a single logical change.
- Do not mix unrelated changes in the same commit.
- Provide a detailed body in the commit message if the change is complex and requires context.