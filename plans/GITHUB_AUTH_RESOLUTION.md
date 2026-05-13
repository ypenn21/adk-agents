# GitHub Authentication Resolution Plan

## Problem Statement
When attempting to use the `mcp_github_pull_request_review_write` tool, the following error is encountered:
`Resource not accessible by personal access token`

This occurs even for simple `COMMENT` events, indicating a fundamental permission issue with the Personal Access Token (PAT) configured for the GitHub MCP server.

## Root Cause Analysis
The failure is likely due to one of the following:
1. **Insufficient Scopes:** The PAT lacks the `repo` scope (for classic tokens) or "Pull requests: Read & write" permissions (for fine-grained tokens).
2. **Workflow Modification Restrictions:** Since the PR modifies `.github/workflows/security-pii-review.yml`, the PAT must have the `workflow` scope.
3. **SAML SSO Authorization:** The token has not been authorized for the `cloud-gtm-core-apps` organization.
4. **Repository Access:** The account associated with the PAT lacks sufficient write permissions on the repository.

## Resolution Steps

### 1. Update PAT Scopes
- Ensure the token has the `repo` and `workflow` scopes enabled.
- For fine-grained tokens, ensure "Contents", "Pull requests", and "Workflows" are set to **Read and write**.

### 2. SAML SSO Authorization
- Go to [GitHub Token Settings](https://github.com/settings/tokens).
- Find the token being used.
- Click **Configure SSO** and ensure `cloud-gtm-core-apps` is authorized.

### 3. Verify Environment Configuration
- Ensure the `GITHUB_PERSONAL_ACCESS_TOKEN` in the local `.env` file matches the updated token.
- Restart the MCP server if necessary to pick up the new credentials.

### 4. Validation
- Run a test review comment using the tool:
  ```json
  {
    "method": "create",
    "owner": "cloud-gtm-core-apps",
    "repo": "e2e-agent-patterns",
    "pullNumber": 8,
    "event": "COMMENT",
    "body": "Validation of updated PAT permissions."
  }
  ```
