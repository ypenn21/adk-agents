# Example Python dev GEMINI.md file
...

## Mandatory Tooling
To ensure all Python code adheres to these standards, the following commands **must** be run before committing any `.py` files. These commands will automatically fix many common issues and flag any that require manual intervention.

When creating or modifying any `.py` Python files, you **must** run the following commands from the root of the project:

1.  **Check and fix linting issues:**
    ```bash
    uvx ruff@latest check --fix .
    ```
2.  **Format the code:**
    ```bash
    uvx ruff@latest format .
    ```