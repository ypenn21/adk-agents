#!/usr/bin/env bash

# 1. Fetch data safely
USER_NAME=$(GITHUB_TOKEN=$GITHUB_PERSONAL_ACCESS_TOKEN gh api user --jq '.name' 2>/dev/null || echo "$USER")
REPO_NAME=$(basename "$PWD")
ISSUES=$(GITHUB_TOKEN=$GITHUB_PERSONAL_ACCESS_TOKEN gh issue list --limit 3 --json number,title --jq '.[] | "- #\(.number): \(.title)"' 2>/dev/null)
PR_STATUS=$(GITHUB_TOKEN=$GITHUB_PERSONAL_ACCESS_TOKEN gh pr status 2>/dev/null | awk 'NR>1')

# 2. Build a structured Markdown message for the UI
# This will be rendered inside the CLI's info box.
WELCOME_HEADER="### 👋 Welcome back, **$USER_NAME**"
WORKSPACE_INFO="📂 **Workspace:** \`$REPO_NAME\`
📍 **Path:** \`$GEMINI_PROJECT_DIR\`"

if [ -n "$ISSUES" ]; then
    ISSUES_SECTION="#### 📌 Top Open Issues
$ISSUES"
else
    ISSUES_SECTION="✨ *No open issues right now.*"
fi

if [ -n "$PR_STATUS" ]; then
    PRS_SECTION="#### 🚀 Pull Request Status
\`\`\`text
$PR_STATUS
\`\`\`"
else
    PRS_SECTION="✨ *No pull requests right now.*"
fi

# Combine sections with double newlines for clear spacing
UI_MARKDOWN="$WELCOME_HEADER

$WORKSPACE_INFO

$ISSUES_SECTION

$PRS_SECTION"

# 3. Output the final JSON
# jq handles the encoding perfectly so the Markdown preserves its structure.
jq -n --arg msg "$UI_MARKDOWN" '{systemMessage: $msg}'
