# OSV-Scanner CLI Reference

Detailed command-line usage and flags for `osv-scanner`.

## Core Scanning Commands

### 1. Recursive Directory Scan
Scans the current directory recursively for all recognized lockfiles and manifests:
```bash
osv-scanner scan -r .
```

### 2. Specific Lockfile / Manifest Scan
Explicitly target individual files:
```bash
# Python uv lockfile
osv-scanner scan --lockfile=uv.lock

# Requirements file
osv-scanner scan --lockfile=requirements.txt

# Node package-lock
osv-scanner scan --lockfile=package-lock.json

# Go modules
osv-scanner scan --lockfile=go.mod
```

### 3. SBOM Scanning
Scan CycloneDX or SPDX Software Bill of Materials:
```bash
# CycloneDX
osv-scanner scan --sbom=bom.cdx.json

# SPDX
osv-scanner scan --sbom=bom.spdx.json
```

### 4. Git Repository History Scan
Scan commits for vulnerable dependencies across repository history:
```bash
osv-scanner scan --commit=<commit-hash>
```

---

## Output Formats & Redirection

The `--format` parameter supports multiple output structures:

| Format | Flag Option | Typical Usage |
| :--- | :--- | :--- |
| **Table** | `--format table` (Default) | Human-readable terminal output |
| **Markdown** | `--format markdown` | PR comments, reports, CI summaries |
| **JSON** | `--format json` | Scripting, custom automation parsing |
| **SARIF** | `--format sarif` | GitHub Advanced Security / Code Scanning |
| **HTML** | `--format html` | Standalone browser-viewable visual reports |
| **CycloneDX** | `--format cyclonedx` | SBOM generation with vulnerability annotations |

### Writing Output to a File
```bash
# Markdown report
osv-scanner scan -r . --format markdown --output-file reports/osv-report.md

# SARIF report
osv-scanner scan -r . --format sarif --output-file reports/osv-report.sarif

# JSON report
osv-scanner scan -r . --format json --output-file reports/osv-report.json
```

---

## Remediation / Guided Fix

OSV-Scanner can calculate and apply minimal version upgrades to satisfy security advisories without breaking dependencies:

```bash
# Preview fixes for a specific manifest/lockfile
osv-scanner fix --manifest=package.json

# Interactive guided fix
osv-scanner fix -M package.json --interactive
```

---

## Offline & Custom Database

For air-gapped or low-latency scanning environments:

```bash
# Download offline database snapshot
osv-scanner --download-offline-databases

# Scan using local database cache
osv-scanner scan -r . --local-db-path=~/.osv-scanner/db
```
