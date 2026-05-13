# Quality Gates and Human-in-the-Loop (HITL) Patterns

This document outlines how to introduce quality gates and human-in-the-loop mechanisms into the CI/CD pipeline using Gemini CLI and GitHub Actions.

## 1. Automated Quality Gates

A Quality Gate is an automated step that analyzes multiple signals (security scans, PII detection, code coverage) and makes a "Go/No-Go" decision.

### Implementation Pattern

Add a step in your workflow that aggregates reports and uses Gemini to evaluate them against specific criteria.

```yaml
      - name: 'Quality Gate Decision'
        env:
          GOOGLE_GENAI_USE_VERTEXAI: 'true'
          GOOGLE_CLOUD_PROJECT: ${{ vars.GCP_PROJECT_ID }}
        run: |
          # Aggregate reports
          echo "### SECURITY SCAN ###" > final_report.txt
          cat reports/security-scan.txt >> final_report.txt
          echo "### PII SCAN ###" >> final_report.txt
          cat reports/pii-scan.txt >> final_report.txt
          echo "### COVERAGE ANALYSIS ###" >> final_report.txt
          cat reports/coverage-analysis.txt >> final_report.txt

          # Gemini Evaluation
          gemini -p "Act as a Release Engineer. Review this combined report. 
          Quality Gate Criteria:
          1. Zero 'High' severity security vulnerabilities in source code.
          2. Zero PII leaks (emails/phones).
          3. Zero 'High' or 'Critical' vulnerabilities in third-party packages (SCA).
          4. PR reviews must not identify 'Critical' missing tests or architectural flaws.
          
          If the criteria are met, output 'GATE_PASSED'. 
          If any fail, output 'GATE_FAILED' followed by a bulleted list of reasons. 
          REPORT CONTENT: $(cat final_report.txt)" -y | tee reports/decision.txt
          
          # Enforce the gate
          if grep -q "GATE_FAILED" reports/decision.txt; then
            echo "Quality Gate Failed!"
            exit 1
          fi
```

---

## 2. Human-in-the-Loop (HITL)

HITL ensures that a human provides explicit approval before high-impact actions (like production deployments) occur.

### Pattern A: GitHub Environments (Recommended)

GitHub Environments allow you to set "Required Reviewers." The workflow will pause and wait for a human to click "Approve" in the GitHub UI.

```yaml
jobs:
  scan-and-evaluate:
    runs-on: ubuntu-latest
    steps:
      # ... all scanning and quality gate steps ...

  deploy:
    needs: scan-and-evaluate  # Only runs if Quality Gate passes
    runs-on: ubuntu-latest
    environment: production   # <--- Triggers the Human-in-the-loop popup!
    steps:
      - name: 'Final Production Deployment'
        run: |
          echo "Deploying to production after human approval..."
          # gcloud run deploy ...
```

### Pattern B: Label-Based HITL

Used for agent-driven workflows where a human intervenes when automation gets "stuck."

- **The Gate:** If the review count exceeds a limit, the `@reviewer` agent applies `status: review-stuck`.
- **The Human:** Review the logs, fix the underlying issue, and manually change the label to `status: needs-qa` to restart the automated cycle.

---

## 3. Benefits

- **Consistency:** Every PR is measured against the same quality bar.
- **Safety:** Prevents accidental deployments of insecure or untested code.
- **Efficiency:** Humans only review code that has already passed all automated baseline checks.
