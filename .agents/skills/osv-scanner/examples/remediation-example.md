# OSV-Scanner Remediation Example

This walkthrough illustrates how an Antigravity agent triages and fixes a vulnerable dependency detected by OSV-Scanner.

---

## 1. Initial Scan Output

Running `osv-scanner scan -r . --format markdown` flags a vulnerability:

| Package | Installed Version | Vulnerability ID | Severity | Fixed Version |
| :--- | :--- | :--- | :--- | :--- |
| `requests` | `2.31.0` | `GHSA-9wx4-h78v-vm56` / `CVE-2024-35195` | Medium | `2.32.0` |

---

## 2. Agent Diagnosis

- **Ecosystem:** Python (managed via `uv` and `pyproject.toml`)
- **Impact:** `requests` version `< 2.32.0` leaks credentials in sub-requests when following HTTPS-to-HTTP redirects.
- **Remediation Action:** Bump `requests` to `>= 2.32.0` in `pyproject.toml` and synchronize `uv.lock`.

---

## 3. Applying the Fix

```bash
# 1. Update dependency constraint via uv
uv add "requests>=2.32.0"

# 2. Synchronize lockfile and environment
uv sync

# 3. Re-run OSV-Scanner to verify resolution
osv-scanner scan -r .
```

---

## 4. Verification Output

```text
Scanning /path/to/project...
Scanned 1 lockfile:
  - uv.lock (14 packages)
No known vulnerabilities found.
```
