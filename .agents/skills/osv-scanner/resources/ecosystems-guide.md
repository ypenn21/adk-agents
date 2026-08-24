# Supported Ecosystems & Remediation Strategies

OSV-Scanner recognizes standard lockfiles and package manifests across the major software ecosystems.

---

## Ecosystems & Target Files

| Ecosystem | Manifest / Lockfile Files | Package Manager | Recommended Upgrade Command |
| :--- | :--- | :--- | :--- |
| **Python** | `uv.lock`, `pyproject.toml` | `uv` | `uv add "<pkg>>=<fixed_ver>"` or `uv lock --upgrade-package <pkg>` |
| **Python** | `poetry.lock`, `pyproject.toml`| `poetry` | `poetry update <pkg>` |
| **Python** | `Pipfile.lock`, `Pipfile` | `pipenv` | `pipenv update <pkg>` |
| **Python** | `requirements.txt` | `pip` | Update version pinned in `requirements.txt` |
| **JavaScript / Node** | `package-lock.json`, `package.json` | `npm` | `npm install <pkg>@<fixed_ver>` |
| **JavaScript / Node** | `yarn.lock`, `package.json` | `yarn` | `yarn upgrade <pkg>@<fixed_ver>` |
| **JavaScript / Node** | `pnpm-lock.yaml`, `package.json` | `pnpm` | `pnpm update <pkg>` |
| **Go** | `go.mod`, `go.sum` | `go` | `go get <module>@<fixed_ver>` && `go mod tidy` |
| **Rust** | `Cargo.lock`, `Cargo.toml` | `cargo` | `cargo update -p <crate> --precise <fixed_ver>` |
| **Java / JVM** | `pom.xml` | `maven` | Update version tag in `<dependency>` in `pom.xml` |
| **Java / JVM** | `build.gradle`, gradle locks | `gradle` | Update implementation dependency version in `build.gradle` |
| **Ruby** | `Gemfile.lock`, `Gemfile` | `bundler` | `bundle update <gem>` |
| **PHP** | `composer.lock`, `composer.json` | `composer` | `composer update <vendor>/<pkg>` |
| **Dart / Flutter** | `pubspec.lock`, `pubspec.yaml` | `pub` | `dart pub upgrade <pkg>` |

---

## Remediation Workflow for AI Agents

1. **Direct Dependency Fix:**
   - Locate the package in the project manifest (`pyproject.toml`, `package.json`, `go.mod`).
   - Bump the version constraint to meet or exceed the fixed version identified in the advisory.
   - Regenerate the lockfile using the ecosystem's native package manager (`uv sync`, `npm install`, `go mod tidy`).

2. **Transitive (Sub-dependency) Fix:**
   - Run lockfile-level upgrade (`uv lock --upgrade-package <pkg>`, `npm update <pkg>`, `cargo update -p <pkg>`).
   - If the parent library restricts the allowed version range, update the parent library or declare a direct pin / override / dependency resolution rule.

3. **Re-scanning:**
   - Run `osv-scanner scan -r .` to confirm the advisory is resolved with zero regressions.
