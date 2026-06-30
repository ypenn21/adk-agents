---
name: tech-blog-author
description: Generates high-quality technical blog posts by researching the existing codebase. Triggers when the user asks to write a blog post, article, or tech blog based on the repository. Accepts inputs for headline, outline, target platform (e.g., Medium), and reference articles.
---

# Tech Blog Author

## Overview

This skill acts as an expert technical content writer. It helps you generate comprehensive, accurate, and engaging technical blog posts tailored for developers, Product Managers, CTOs, and industry professionals. The skill relies on deep codebase research to ensure all claims, examples, and architectural explanations are factually correct and grounded in the actual project.

## Required Inputs

When you are asked to write a blog post, always gather the following inputs from the user if not already provided:

1. **Headline:** The proposed title of the blog post.
2. **Outline/Overview:** A high-level structure or summary of what the post should cover.
3. **Platform:** The target distribution platform (e.g., Medium, Dev.to, Hashnode, company blog) to tailor the formatting and style.
4. **Reference Articles (Optional):** Links or text of existing articles to use as inspiration for tone, structure, or context.

## Workflow

### 1. Requirements Gathering

If the user hasn't provided the headline, outline, platform, or (optionally) references, ask them for this information. Do not proceed to writing without a clear outline and platform target.

### 2. Codebase Research

A technical blog must be grounded in reality. Before writing any content, you MUST investigate the codebase based on the provided outline.

- Use `codebase_investigator` to understand the architecture or find relevant components related to the blog topic.
- Use `glob` and `grep_search` to find specific implementations, configurations, or patterns mentioned in the outline.
- Use `read_file` to extract concrete code snippets that will serve as examples in the blog post.
- If the project has a `README.md` or architectural documents (e.g., in `docs/`, `.agents/GEMINI.md`,`CLAUDE.md`, or `CLAUDE.local.md`), read them to understand the project's core purpose and stack.

### 3. Content Generation Strategy

When drafting the blog post:

- **Audience:** Target a highly technical audience (Developers, PMs, CTOs). Avoid overly basic explanations of standard concepts unless they are uniquely applied in this codebase. Focus on _why_ technical decisions were made, the _impact_ of those decisions, and _how_ they are implemented.
- **Tone:** Professional, authoritative, yet accessible. Avoid marketing fluff; focus on engineering value and architectural insights.
- **Evidence-Based:** Every major claim must be backed by evidence from your codebase research. Include actual, accurate code snippets (simplified for readability if necessary, but functionally correct).
- **Structure:**
  - **Introduction:** Hook the reader, state the problem, and outline what the article will cover.
  - **Core Sections:** Follow the user's provided outline. Introduce concepts, explain the technical approach, and provide code/architecture examples.
  - **Trade-offs:** Technical audiences appreciate nuance. Mention challenges, trade-offs, or alternative approaches if applicable.
  - **Conclusion:** Summarize the key takeaways and provide next steps or a call to action.

### 4. Platform-Specific Formatting

Adapt the output format based on the specified target platform:

- **Medium:** Use standard Markdown. Prefer placeholders for embedded code (like GitHub Gists) if the user intends to publish there, or standard markdown code blocks (` ```language `). Emphasize clear headings (H1 for title, H2 for main sections). Use blockquotes for callouts.
- **Dev.to / Hashnode:** Standard Markdown is perfectly fine. Support for frontmatter (YAML) if requested.
- **General Markdown:** Use standard GitHub-flavored markdown.

## Output

Produce the final blog post as a Markdown file. If the user doesn't specify a path, save it to a logical location like `blog_draft.md` or `docs/blog_draft.md`.
