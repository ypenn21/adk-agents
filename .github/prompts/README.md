# Externalized Agent Prompt Templates

This directory houses externalized, version-controlled prompt templates for Antigravity AI agents (e.g., PR Reviewer Agent, Quality Gate Decision Agent).

## Directory Structure

```
.github/prompts/
├── README.md                      # This documentation
├── pr_reviewer/                   # PR Reviewer agent templates
│   ├── v1.0.0.md                  # Semantic versioned prompt templates
│   └── ...
└── quality_gate/                  # Quality Gate decision agent templates
    ├── v1.0.0.md
    └── ...
```

## Template File Specification

Each template is a standard Markdown file consisting of two required parts:
1. **YAML Frontmatter:** Delimited by `---` at the beginning of the file, providing metadata for versioning, validation, and audit telemetry.
2. **Markdown Sections:**
   - `## System Instructions`: Guidance, rules, checklist, and severity calibration for the model's system role.
   - `## User Prompt`: Execution context with `${variable}` placeholders to be dynamically substituted at runtime.

### Frontmatter Schema

```yaml
---
name: pr_reviewer                  # Identifier matching agent key
version: "1.0.0"                   # Semantic version string (X.Y.Z)
description: "Prompt description"
author: "Team or Author name"
created_at: "YYYY-MM-DD"
model_compatibility:               # List of compatible Gemini models
  - "gemini-3.7-flash"
  - "gemini-3.8-flash"
required_variables:                # Variables that MUST be supplied to render_user_prompt
  - pr_number
  - repo
  - pii_context
optional_variables:                # Optional variables
  - additional_guidelines
changelog:                         # Structured revision history
  - version: "1.0.0"
    date: "YYYY-MM-DD"
    summary: "Initial externalized prompt release."
---
```

## Variable Substitution Syntax: `${variable}`

- Prompt variables use Python's `string.Template` syntax: `${variable_name}` (or `$variable_name`).
- **Literal Braces Preservation:** Standard curly braces like `{id}`, JSON snippets `{"key": "value"}`, or regex patterns in prompts are **not** treated as placeholders and are safely preserved without double-escaping (`{{...}}`).
- If any required variable defined in `required_variables` is missing or `None`, `PromptLoader` will raise a descriptive `ValueError`.

## Semantic Versioning and Resolution Strategy

Templates follow Semantic Versioning (`vMAJOR.MINOR.PATCH.md` or `MAJOR.MINOR.PATCH.md`):
- **Pinning Version:** Specify `PR_REVIEW_PROMPT_VERSION="1.0.0"` or `QUALITY_GATE_PROMPT_VERSION="1.0.0"`.
- **Latest Resolution:** Specifying `"latest"` resolves to the file with the highest semantic version on disk.
- **Explicit Path:** Use `PR_REVIEW_PROMPT_PATH` or `QUALITY_GATE_PROMPT_PATH` to point to a custom template file anywhere in the repository.
- **Fail-Safe Fallback:** If a template file is deleted or unreadable, `PromptLoader` falls back to embedded defaults (`is_fallback: true`), ensuring CI pipelines never crash.
