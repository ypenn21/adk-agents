# Security & Privacy Review Report Templates

This document specifies the standard output structures used by the `security-privacy-review` skill across local CLI invocations, Pull Request reviews, and CI/CD Quality Gate evaluations.

---

## 1. CI/CD Static Analysis (SAST) Report Format

Targeted for `reports/security-scan.txt` in `.github/workflows/security-pii-review.yml`.

### Template:

```markdown
# 🛡️ Antigravity AI Security & Privacy SAST Report

## Executive Summary
- **Total Files Analyzed:** <Count>
- **Critical Findings:** <Count>
- **High Findings:** <Count>
- **Medium Findings:** <Count>
- **Low / Informational Findings:** <Count>
- **Overall Codebase Status:** [PASSED | ACTION REQUIRED]

---

## Detailed Findings Table

| Severity | File Path | Line Number | Category / Vulnerability | Remediation |
| :--- | :--- | :--- | :--- | :--- |
| **Critical** | `path/to/file.py` | L42 | SQL Injection via raw query | Use parameterized ORM filter |
| **High** | `path/to/settings.py` | L18 | Hardcoded Secret / API Key | Load from environment variable |
| **Medium** | `path/to/views.py` | L64 | Missing CSRF Protection on POST | Add `@csrf_protect` or Bearer auth |
| **Low** | `path/to/tools.py` | L29 | Unbounded Input Length in Agent Tool | Add string length validation |

---

## Actionable Remediation Guidance

### Finding 1: [Critical] SQL Injection in `path/to/file.py`
- **Location:** Line 42
- **Vulnerable Code Snippet:**
  ```python
  cursor.execute(f"SELECT * FROM tickets WHERE id = '{ticket_id}'")
  ```
- **Recommended Fix:**
  ```python
  cursor.execute("SELECT * FROM tickets WHERE id = %s", [ticket_id])
  ```
- **Explanation:** Using format string interpolation exposes the database to arbitrary SQL execution when `ticket_id` contains unescaped single quotes or subqueries.
```

---

## 2. Clean Scan Output (Zero Vulnerabilities)

When no issues are found, emit this deterministic message:

```markdown
# 🛡️ Antigravity AI Security & Privacy SAST Report

## Executive Summary
- **Total Files Analyzed:** <Count>
- **Critical Findings:** 0
- **High Findings:** 0
- **Medium Findings:** 0
- **Low / Informational Findings:** 0

✅ No Critical, High, or Medium security or privacy vulnerabilities detected. All analyzed code adheres to secure coding standards.
```

---

## 3. Pull Request Inline Comment Format

When reviewing PR diffs via the `@reviewer` subagent:

```markdown
### ⚠️ Security Issue: [Severity] [Vulnerability Name]
**Location:** `file.py:L12-L14`

**Problem:** Untrusted data from `request.data['input']` flows directly into `subprocess.Popen()` without sanitization.

**Suggested Fix:**
```suggestion
subprocess.run(["safe_command", validated_arg], check=True)
```
```

