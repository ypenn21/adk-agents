# OWASP Top 10: Software Composition Analysis (SCA) & Vulnerability Management

This document outlines the strategy for detecting and remediating known vulnerabilities (CVEs) in third-party packages, container images, and IaC files to ensure compliance with OWASP Top 10 standards (e.g., A06: Vulnerable and Outdated Components).

## 1. Objective
Identify and block deployments that contain high-severity vulnerabilities in dependencies, leveraging both automated CI/CD scans and AI-assisted investigation.

## 2. Tool Comparison & Landscape

Choosing the right tool depends on the "layer" of the stack you are scanning. A robust strategy uses both Trivy for infrastructure/OS and Gemini for application-level remediation.

| Feature | **Trivy CLI** | **Gemini Security Extension** |
| :--- | :--- | :--- |
| **Primary Scope** | Infrastructure, Container OS (Alpine/Ubuntu), IaC (Terraform). | Application Dependencies (npm, pip, Go, etc.) and Source Code. |
| **Strengths** | Best for finding OS-level bugs (e.g., OpenSSL) and container misconfigurations. | Best for deep dependency analysis and providing AI-powered code fixes. |
| **Pros** | Fast, zero cost, works entirely offline, comprehensive for DevOps. | AI-powered remediation advice, high accuracy for app-level vulnerabilities. |
| **Cons** | Static reports; does not suggest code-level patches. | Requires internet for LLM analysis; small token cost per scan. |
| **Data Source** | NVD, Vendor Databases (RedHat, Debian), GitHub Advisories. | OSV.dev (aggregated from 30+ sources like PyPA, RustSec, etc.). |
| **Cost** | **$0** (Apache 2.0 Open Source). | **$0** for scanning; **Token usage** for AI analysis. |

---

## 3. The Three-Layer Stack (Gemini Security Extension)

The Gemini Security Extension isn't just one tool; it's a three-layer pipeline that transforms raw data into actionable fixes:

1.  **Layer 1: Data (OSV.dev)**
    - **Source:** Managed by Google. A public, distributed database of vulnerabilities for open-source projects.
    - **Function:** The "Source of Truth" for which package versions are unsafe.
2.  **Layer 2: Scanning (OSV-Scanner)**
    - **Source:** Google's technical engine.
    - **Function:** Efficiently crawls your project, identifies exact package versions, and cross-references them with OSV.dev.
3.  **Layer 3: Analysis (Gemini LLM)**
    - **Source:** Gemini 3.0 Flash/Pro.
    - **Function:** Takes the technical vulnerability report and "translates" it. It explains the risk and **writes the specific code patch** (e.g., updating a Dockerfile or package.json) to resolve the issue.

---

## 4. Gemini Dependency Scan
The Gemini Dependency Scan (via the `/security:scan-deps` command) is an AI-powered analyzer that goes beyond static vulnerability matching. It uses the Gemini LLM to reason about dependency graphs and provide context-aware remediation.

- **Capabilities**:
    - **Contextual Risk Analysis**: Evaluates if a vulnerable package is actually being used in a risky way within your codebase.
    - **Direct Remediation**: Generates precise code patches for `package.json`, `requirements.txt`, or `Dockerfile`.
    - **Dependency Graph Reasoning**: Identifies transitive dependencies that are causing issues.
- **CLI Command**:
  ```bash
  gemini -p "/security:scan-deps"
  ```
- **Prerequisites**: Requires the Gemini Security Extension.
  ```bash
  gemini extensions install https://github.com/gemini-cli-extensions/security --consent
  ```

---

## 5. Implementation Pattern (CI/CD)

### Step A: Pre-Build Filesystem Scan (Shift-Left)
Scan the repository source code and dependency lockfiles *before* the Docker image is built.

```yaml
      - name: 'Run Filesystem SCA Scan'
        run: |
          trivy fs . --severity HIGH,CRITICAL --format table --output reports/fs-sca-scan.txt
```

### Step B: Post-Build Container Image Scan
Scan the final Docker image to ensure the base OS and all installed artifacts are secure.

```yaml
      - name: 'Run Container SCA Scan'
        run: |
          trivy image --severity HIGH,CRITICAL --format table --output reports/container-sca-scan.txt us-central1-docker.pkg.dev/genai-apps-25/adk/fast-api-fe:latest
```

### Step C: AI-Powered Dependency Audit
Augment Trivy results with the Gemini Security Extension to identify complex dependency issues.

```yaml
      - name: 'Gemini Dependency Scan'
        run: |
          gemini -p "/security:scan-deps" -y >> reports/dependency-audit.txt
```

### Step D: Integrate with Quality Gate
All SCA reports are aggregated into the final report for Gemini evaluation.

```yaml
      - name: 'Quality Gate Decision'
        run: |
          cat reports/fs-sca-scan.txt >> final_report.txt
          cat reports/container-sca-scan.txt >> final_report.txt
          cat reports/dependency-audit.txt >> final_report.txt
          gemini -p "... 4. Zero High/Critical CVEs in dependencies or the container image. ..."
```

---

## 6. AI-Assisted Investigation & Remediation (Local)

To accelerate the "Fix" phase, developers can use the **Trivy MCP Server** to give AI assistants direct visibility into the vulnerability state.

### Setup MCP Server
```bash
# Install the plugin
trivy plugin install mcp

# Start the server (connects to Cursor, Claude Code, or Gemini CLI)
trivy mcp
```

### AI-Assisted Remediation Workflow
1.  **Analyze**: Use `/security:scan-deps` to get a high-level audit.
2.  **Investigate**: Use the MCP server to ask the AI: *"What is the blast radius of CVE-2023-XXXX in my current architecture?"*
3.  **Patch**: Ask the AI to: *"Update my Dockerfile and requirements.txt to resolve the critical vulnerabilities identified by Trivy."*

---

## 7. Standard Remediation Workflow
1. **Identify**: Trivy or Gemini flags a vulnerability.
2. **Analyze**: The Quality Gate fails with specific CVE details.
3. **Fix**: Use AI-assisted patching to update `Dockerfile` or dependency lockfiles.
4. **Verify**: Re-run the pipeline and local scans.
