---
name: docs
description: Generate or update documentation. Use when asked to document a target module, API, feature, or file, ensuring comprehensive coverage of usage and configuration.
---

# Generate or Update Documentation

## Instructions

1. **Read the target code:** Understand the public API, exported types, functions, and their behavior. Note any configuration options or environment variables.
2. **Generate documentation:** Use markdown format with the following sections:
   - **Overview:** Brief description of what the module/feature does.
   - **Usage:** Code examples showing common usage patterns.
   - **API Reference:** Document each exported function/type with signature, parameters, return values, and example usage.
   - **Configuration:** Document config options, environment variables, or flags.
3. **Update README:** If the documented module is a top-level feature, add or update its section in the project README.
4. **Add inline comments:** For complex logic that is not self-documenting, add brief comments explaining the "why" (not the "what").
5. **Verify accuracy:** Ensure all documented APIs match the actual code.
6. **Report back:** Summarize what was documented and where it was written.