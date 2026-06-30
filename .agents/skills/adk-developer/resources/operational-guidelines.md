
## Operational Guidelines for Coding Agents

These guidelines are essential for working on this project effectively.

### Principle 1: Code Preservation & Isolation

When executing code modifications, your paramount objective is surgical precision. You **must alter only the code segments directly targeted** by the user's request, while **strictly preserving all surrounding and unrelated code.**

**Mandatory Pre-Execution Verification:**

Before finalizing any code replacement, verify:

1.  **Target Identification:** Clearly define the exact lines or expressions to be changed, based *solely* on the user's explicit instructions.
2.  **Preservation Check:** Ensure all code, configuration values (e.g., `model`, `version`, `api_key`), comments, and formatting *outside* the identified target remain identical.

**Example:**

*   **User Request:** "Change the agent's instruction to be a recipe suggester."
*   **Original Code:**
    ```python
    root_agent = Agent(
        name="root_agent",
        model="gemini-3-flash-preview",
        instruction="You are a helpful AI assistant."
    )
    ```
*   **Incorrect (VIOLATION):**
    ```python
    root_agent = Agent(
        name="recipe_suggester",
        model="gemini-1.5-flash",  # UNINTENDED - model was not requested to change
        instruction="You are a recipe suggester."
    )
    ```
*   **Correct (COMPLIANT):**
    ```python
    root_agent = Agent(
        name="recipe_suggester",  # OK, related to new purpose
        model="gemini-3-flash-preview",  # PRESERVED
        instruction="You are a recipe suggester."  # OK, the direct target
    )
    ```

**Critical:** Always prioritize the integrity of existing code over rewriting entire blocks.

### Principle 2: Execution Best Practices

*   **Model Selection - CRITICAL:**
    *   **NEVER change the model unless explicitly asked.** If the code uses `gemini-3-flash-preview`, keep it as `gemini-3-flash-preview`. Do NOT "upgrade" or "fix" model names.
    *   When creating NEW agents (not modifying existing), use Gemini 3 series: `gemini-3-flash-preview`, `gemini-3-pro-preview`.
    *   Do NOT use older models (`gemini-2.0-flash`, `gemini-1.5-flash`, etc.) unless the user explicitly requests them.

*   **Location Matters More Than Model:**
    *   If a model returns a 404, it's almost always a `GOOGLE_CLOUD_LOCATION` issue (e.g., needing `global` instead of `2`).
    *   Changing the model name to "fix" a 404 is a violation - fix the location instead.
    *   Some models (like `gemini-3-flash-preview`) require specific locations. Check the error message for hints.

*   **ADK Built-in Tool Imports (Precision Required):**
    *   ADK built-in tools require surgical imports to get the tool instance, not the module:
    ```python
    # CORRECT - imports the tool instance
    from google.adk.tools.load_web_page import load_web_page

    # WRONG - imports the module, not the tool
    from google.adk.tools import load_web_page
    ```
    *   Pass the imported tool directly to `tools=[load_web_page]`, not `tools=[load_web_page.load_web_page]`.

*   **Running Python Commands:**
    *   Always use `uv` to execute Python commands (e.g., `uv run python script.py`)
    *   Run `make install` before executing scripts
    *   Consult `Makefile` and `README.md` for available commands

*   **Troubleshooting:**
    *   **Check the ADK cheatsheet in this file first** - it covers most common patterns
    *   **Need more depth?** Try checking ADK docs and source code.
    *   For framework questions (ADK, LangGraph) or GCP products (Cloud Run), check official documentation
    *   When encountering persistent errors, a targeted Google Search often finds solutions faster

*   **Breaking Infinite Loops:**
    *   **Stop immediately** if you see the same error 3+ times in a row
    *   **Don't retry failed operations** - fix the root cause first
    *   **RED FLAGS**: Lock IDs incrementing, names appending v5→v6→v7, "I'll try one more time" repeatedly
    *   **State conflicts** (Error 409: Resource already exists): Import existing resources with `terraform import` instead of retrying creation
    *   **Tool bugs**: Fix source code bugs before continuing - don't work around them
    *   **When stuck**: Run underlying commands directly (e.g., `terraform` CLI) instead of calling problematic tools
