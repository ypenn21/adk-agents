---
name: research
description: Research a topic by deep-diving into the local repository and conducting targeted web searches, then create a structured implementation plan in the plans/ folder.
---

# Research & Plan Workflow

Use this skill when you need to research a feature, bug, or architecture change, analyze the local repository, perform web searches for credible information, and produce a detailed implementation plan.

## Steps

1. **Clarify the Topic & Goals**
   - Confirm the core objective, requirements, and constraints with the user.
   - Identify the primary components of the codebase or technologies involved.

2. **Deep Dive into the Local Repository**
   - Use `grep_search` to find existing implementations, configuration files, dependencies (e.g., `requirements.txt`, `package.json`, `export_to_sheets.py`), and relevant classes or functions.
   - Use `list_dir` to inspect folder layouts and understand module organization.
   - Use `view_file` to read the key source files, looking specifically for integration points, helper utilities, coding patterns, and structural requirements.

3. **Retrieve Credible Data from the Web**
   - Use `search_web` to find official documentation, API specifications, best practices, or solutions to similar engineering problems.
   - Run multiple queries with varied search terms to ensure comprehensive results.
   - Use `read_url_content` to pull full documentation or article contents from key pages for deeper analysis.
   - Ensure all external resources and findings are documented with credible sources and citations (URLs, titles, retrieval dates).

4. **Analyze & Design**
   - Compare the findings from the web search with the existing codebase patterns.
   - Assess trade-offs between different implementation approaches (e.g., complexity, performance, ease of testing, compliance with repository style).

5. **Create the Implementation Plan**
   - Write a detailed markdown file at `plans/<topic-slug>.md` using the following template:

   ```markdown
   # Implementation Plan: <Plan Title>

   ## Overview
   A brief description of the goal, the problem being solved, and the value of this change.

   ## Research & Web Citations
   List of credible external documents, official specifications, or reference guides retrieved from the web.
   > **Ref-N:** [<Title>](<URL>) — Key technical takeaway, pattern, or constraint discovered.

   ## Existing Codebase Analysis
   Detailed breakdown of the current state of the local codebase, including:
   - Target files and modules to be modified.
   - Current software design/patterns to adhere to.
   - Integration points and existing dependencies.

   ## 📋 Checklist
   A step-by-step list of actionable changes that can be checked off during implementation:
   - [ ] Step 1: Pre-requisites & config changes
   - [ ] Step 2: Component A modifications
   - [ ] Step 3: Integration & testing

   ## Proposed Changes
   Detailed file-by-file changes with complete explanation and **sample code snippets** showing precisely how to implement the code.
   - **File:** `[<filename>](file:///path/to/file)`
     - **Change description:** Explain the modifications.
     - **Draft/Sample Code:** Include clear, styled, and complete sample code blocks.

   ## Trade-offs & Considerations
   Pros, cons, and alternatives evaluated (e.g., security, speed, technical debt, or dependencies).

   ## Next Steps
   Clear chronological order of task execution.
   ```

6. **Present & Iterate**
   - Share the created plan with the user, highlighting key technical decisions, open questions, and recommended paths.
   - Prompt the user to review the plan and provide feedback.
   - If the user requests changes, update the plan at `plans/<topic-slug>.md` and present the revised version. Continue iterating until the plan is approved.

Remember: This is a planning and research workflow. Your primary goal is to draft a clean, detailed, and validated blueprint before executing any code changes.
