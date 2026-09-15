# Feature Implementation Plan: Context-Managed Batching, Compaction & Triage for PR Reviewer Agent

## 📋 Todo Checklist
- [ ] Task 1: Implement paginated file retrieval and exclusion filtering (`fetch_all_pr_modified_files`, `triage_and_filter_files`) in [`.github/scripts/helper.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/helper.py)
- [ ] Task 2: Implement token-aware batch partitioner (`partition_files_into_batches`) in [`.github/scripts/helper.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/helper.py)
- [ ] Task 3: Implement risk scoring and file triage heuristics (`triage_review_files`) in [`.github/scripts/helper.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/helper.py)
- [ ] Task 4: Define batch data schemas (`FileDiffItem`, `ReviewBatch`, `BatchReviewResult`, `PRTriageSummary`) in [`.github/scripts/pr_reviewer_agent.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/pr_reviewer_agent.py)
- [ ] Task 5: Implement isolated-context batch review runner (`review_batch_with_isolated_context`) in [`.github/scripts/pr_reviewer_agent.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/pr_reviewer_agent.py)
- [ ] Task 6: Implement finding accumulator, cross-batch deduplication, and final report synthesis (`synthesize_final_review_report`) in [`.github/scripts/pr_reviewer_agent.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/pr_reviewer_agent.py)
- [ ] Task 7: Refactor `run_pr_review()` in [`.github/scripts/pr_reviewer_agent.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/pr_reviewer_agent.py) to execute the batch review pipeline
- [ ] Task 8: Update configuration resolution in `resolve_env_config()` for batch thresholds (`BATCH_MAX_FILES`, `BATCH_MAX_TOKENS`, `MAX_REVIEW_FILES_CAP`)
- [ ] Task 9: Update [`.github/workflows/source-code-pii-review.yml`](file:///Users/yannipeng/git-projects/adk-agents/.github/workflows/source-code-pii-review.yml) with batch configuration environment variables
- [ ] Task 10: Update architectural specification [`docs/spec.md`](file:///Users/yannipeng/git-projects/adk-agents/docs/spec.md) with Decisions D-15 through D-18
- [ ] Task 11: Write unit and contract tests in [`.github/scripts/tests/test_helper.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/tests/test_helper.py) and [`.github/scripts/tests/test_pr_reviewer_agent.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/tests/test_pr_reviewer_agent.py)

---

## 🔍 Analysis & Investigation

### Codebase Structure
The files governing the PR review lifecycle and their responsibilities:

| File Path | Current Responsibility | Proposed Changes |
| :--- | :--- | :--- |
| [`.github/scripts/helper.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/helper.py) | Shared utilities for GitHub REST API, environment config, and reports. | Add `fetch_all_pr_modified_files` (pagination), exclusion filtering, `triage_and_filter_files`, and `partition_files_into_batches`. |
| [`.github/scripts/pr_reviewer_agent.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/pr_reviewer_agent.py) | Main agent runner; currently runs a single monolithic `Agent.chat()` turn. | Implement Map-Reduce architecture: isolated batch worker `review_batch_with_isolated_context` and reducer `synthesize_final_review_report`. |
| [`docs/spec.md`](file:///Users/yannipeng/git-projects/adk-agents/docs/spec.md) | Architectural specification and decision log (D-1 through D-14). | Add Decision D-15 (paginated file discovery), D-16 (batch partitioning & triage), D-17 (isolated-context execution), and D-18 (finding accumulation & synthesis). |
| [`.github/workflows/source-code-pii-review.yml`](file:///Users/yannipeng/git-projects/adk-agents/.github/workflows/source-code-pii-review.yml) | GitHub Actions workflow configuration. | Add `BATCH_MAX_FILES`, `BATCH_MAX_TOKENS`, and `MAX_REVIEW_FILES_CAP` environment controls. |
| [`.github/scripts/tests/test_helper.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/tests/test_helper.py) | Unit test suite for helper utilities. | Add tests for pagination, file exclusion, triage ranking, and batch chunking. |
| [`.github/scripts/tests/test_pr_reviewer_agent.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/tests/test_pr_reviewer_agent.py) | Acceptance and contract tests for PR reviewer agent. | Add tests for multi-batch execution, context clearing, finding accumulation, and large PR triage caps. |

### Current Architecture vs. Proposed Architecture
- **Current (Monolithic):** GitHub Actions triggers `run_pr_review()`, which creates a single `Agent` session with `github-mcp-server`. The agent is asked to review the entire PR in one turn. On large PRs, context window overflow or budget limits (`MAX_INPUT_TOKENS`, `MAX_TOOL_CALLS`) abort the review prematurely.
- **Proposed (Map-Reduce with Isolated Contexts):**
  1. **Discovery & Triage:** Paginate through GitHub REST API to fetch all modified files and patch hunks. Filter out non-reviewable files (lockfiles, vendor assets, binaries, docs). If the file count exceeds `MAX_REVIEW_FILES_CAP` (e.g. 200 files), triage files using risk scoring (security modules, API routes, DLP findings).
  2. **Partitioning:** Group files into batches bounded by `BATCH_MAX_FILES` (default 25) and `BATCH_MAX_TOKENS` (default 60,000 tokens).
  3. **Map Phase (Context Isolation):** For each batch, instantiate a dedicated `Agent` session or fresh `Conversation`. Pass only that batch's diff hunks and relevant DLP findings. Once the batch yields structured `BatchReviewResult`, close the session and discard the raw diff memory.
  4. **Reduce Phase (Synthesis):** Aggregate findings from all batches, deduplicate inline comments, and execute a lightweight synthesis turn (or deterministic assembly) to produce the unified `PRReviewReport`.

### Dependencies & Integration Points
- **Google Antigravity SDK (`google.antigravity`):** Ephemeral `Agent` sessions with `LocalAgentConfig`, `response_schema=BatchReviewResult`, and per-batch budget controls.
- **GitHub REST API (`/repos/{owner}/{repo}/pulls/{number}/files`):** Paginated retrieval (`per_page=100`, page 1 to $N$) with `Link` header parsing.
- **Cloud DLP Artifacts (`reports/pii-scan.txt`, `reports/pii-scan.json`):** Correlated with modified files so only relevant DLP findings are sent to each batch.

### Considerations & Challenges
1. **Context Memory Leakage:** In Python, keeping long-lived conversation objects or accumulating large strings in memory causes garbage collection latency. Explicitly destroying the agent session (`async with Agent(...) as agent:`) ensures conversation history is cleared after each batch.
2. **Cumulative Token Budget Governance:** `MAX_TOTAL_TOKENS` and `MAX_SPEND_USD` must be tracked across the entire pipeline. If cumulative token consumption approaches the ceiling, subsequent batches are skipped, and the reducer produces a consolidated summary of reviewed files versus skipped files.
3. **CI Execution Time:** Reviewing 10,000 files in a single CI job is impossible due to the 6-hour GitHub Actions job limit and cost constraints. Triage caps ensure the pipeline remains bounded, deterministic, and fast (under 10 minutes).

---

## 📐 Technical Specification & Design

### Component Architecture

```
                               ┌────────────────────────────────────────────────────────┐
                               │           1. Paginated File Discovery                  │
                               │   GET /pulls/{pr}/files?page=1..N (helper.py)          │
                               └──────────────────────────┬─────────────────────────────┘
                                                          │
                                                          ▼
                               ┌────────────────────────────────────────────────────────┐
                               │           2. Exclusion Filter & Risk Triage            │
                               │   Drop lockfiles, vendor, generated code. Cap at N max │
                               └──────────────────────────┬─────────────────────────────┘
                                                          │
                                                          ▼
                               ┌────────────────────────────────────────────────────────┐
                               │           3. Token-Aware Partitioner                   │
                               │   Split into Batches: max 25 files / 60k tokens        │
                               └──────────────────────────┬─────────────────────────────┘
                                                          │
                    ┌─────────────────────────────────────┴─────────────────────────────────────┐
                    ▼                                     ▼                                     ▼
      ┌───────────────────────────┐         ┌───────────────────────────┐         ┌───────────────────────────┐
      │      Batch 1 Worker       │         │      Batch 2 Worker       │         │      Batch N Worker       │
      │  Isolated Agent Session   │         │  Isolated Agent Session   │         │  Isolated Agent Session   │
      │  Raw diffs discarded      │         │  Raw diffs discarded      │         │  Raw diffs discarded      │
      └─────────────┬─────────────┘         └─────────────┬─────────────┘         └─────────────┬─────────────┘
                    │                                     │                                     │
                    └─────────────────────────────────────┼─────────────────────────────────────┘
                                                          │
                                                          ▼
                               ┌────────────────────────────────────────────────────────┐
                               │           4. Reducer & Cross-Batch Aggregation         │
                               │   Deduplicate findings, calculate cumulative tokens    │
                               └──────────────────────────┬─────────────────────────────┘
                                                          │
                                                          ▼
                               ┌────────────────────────────────────────────────────────┐
                               │           5. Final PRReviewReport Generation           │
                               │   Publish to GitHub PR & write reports/pr-review.json  │
                               └────────────────────────────────────────────────────────┘
```

### Mermaid Diagram
```mermaid
sequenceDiagram
    autonumber
    participant CI as GitHub Actions Runner
    participant Main as pr_reviewer_agent.py
    participant Helper as helper.py
    participant GH as GitHub REST API
    participant Agent as Antigravity Agent (Batch Worker)

    CI->>Main: run_pr_review(pr_number, repo, token)
    Main->>Helper: fetch_all_pr_modified_files(owner, repo, pr_number, token)
    loop Paginate Pages 1 to N
        Helper->>GH: GET /pulls/{pr}/files?per_page=100&page={page}
        GH-->>Helper: JSON file list with patch hunks
    end
    Helper-->>Main: Complete modified files list
    Main->>Helper: triage_and_filter_files(files, pii_findings, max_cap=200)
    Helper-->>Main: Prioritized reviewable files
    Main->>Helper: partition_files_into_batches(files, max_files=25, max_tokens=60000)
    Helper-->>Main: List of ReviewBatch objects

    loop For Each ReviewBatch (Context Isolation)
        Main->>Agent: Create fresh Agent(LocalAgentConfig)
        Main->>Agent: chat(batch_prompt_with_diffs)
        Agent-->>Main: BatchReviewResult(batch_summary, findings)
        Note over Agent,Main: Session closed; raw diffs discarded from context
    end

    Main->>Main: Aggregate findings & check cumulative budget
    Main->>Helper: synthesize_final_review_report(all_findings, triage_meta)
    Main->>Helper: write_pr_reports(final_report)
    Main->>Helper: post_github_pr_review(final_report)
    Helper->>GH: POST /pulls/{pr}/reviews
    Main-->>CI: Return final PRReviewReport
```

### Schemas & Models

#### 1. Batch Data Schemas (`pr_reviewer_agent.py`)
```python
class FileDiffItem(BaseModel):
    filename: str
    status: str  # modified, added, removed, renamed
    additions: int
    deletions: int
    changes: int
    patch: str = ""
    estimated_tokens: int = 0
    pii_flagged: bool = False
    risk_score: int = 0


class ReviewBatch(BaseModel):
    batch_index: int
    total_batches: int
    files: list[FileDiffItem]
    total_estimated_tokens: int


class BatchReviewResult(BaseModel):
    batch_index: int
    batch_summary: str
    findings: list[InlineFinding] = Field(default_factory=list)
```

#### 2. Triage & Summary Metadata Schema
```python
class PRTriageSummary(BaseModel):
    total_files_in_pr: int
    reviewable_files_count: int
    excluded_files_count: int
    triaged_files_count: int
    skipped_files_count: int
    batches_executed: int
    triage_applied: bool = False
```

### API & Code Signatures

#### `fetch_all_pr_modified_files` in `.github/scripts/helper.py`
```python
def fetch_all_pr_modified_files(
    owner: str,
    repo_name: str,
    pr_number: Union[str, int],
    token: str,
    timeout: int = 15,
) -> list[dict[str, Any]]:
    """Paginates through GitHub REST API to fetch all modified files on a PR.

    Handles Link headers and page iteration until an empty page or < 100 items returned.
    """
```

#### `triage_and_filter_files` in `.github/scripts/helper.py`
```python
EXCLUDED_FILE_PATTERNS: list[str] = [
    r"package-lock\.json$",
    r"yarn\.lock$",
    r"pnpm-lock\.yaml$",
    r"poetry\.lock$",
    r"Pipfile\.lock$",
    r"composer\.lock$",
    r"go\.sum$",
    r"\.min\.(js|css)$",
    r"\.map$",
    r"\.(png|jpg|jpeg|gif|svg|ico|pdf|zip|tar|gz|woff|woff2|ttf|eot)$",
    r"vendor/",
    r"node_modules/",
]

def triage_and_filter_files(
    files: list[dict[str, Any]],
    pii_context: str = "",
    max_cap: int = 200,
) -> tuple[list[FileDiffItem], PRTriageSummary]:
    """Filters non-reviewable files, assigns risk scores, and caps review volume."""
```

#### `partition_files_into_batches` in `.github/scripts/helper.py`
```python
def partition_files_into_batches(
    files: list[FileDiffItem],
    max_files_per_batch: int = 25,
    max_tokens_per_batch: int = 60_000,
) -> list[ReviewBatch]:
    """Partitions files into bounded batches based on file count and estimated tokens."""
```

#### `review_batch_with_isolated_context` in `.github/scripts/pr_reviewer_agent.py`
```python
async def review_batch_with_isolated_context(
    batch: ReviewBatch,
    cfg: dict[str, Any],
    pii_context_subset: str,
    telemetry_dir: str,
) -> tuple[BatchReviewResult, dict[str, Any]]:
    """Executes a single batch review in an isolated agent session, discarding raw diff context upon return."""
```

---

## 📝 Step-by-Step Implementation Steps

### Step 1: Paginated File Retrieval & Exclusion Filtering in `helper.py`
- **Files to modify:** [`.github/scripts/helper.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/helper.py)
- **Changes needed:**
  1. Add `fetch_all_pr_modified_files(owner, repo_name, pr_number, token)` supporting pagination up to 100 pages (10,000 files).
  2. Implement `EXCLUDED_FILE_PATTERNS` regex matching. Exclude lockfiles, vendor folders, minified assets, and binary files.
  3. Implement risk calculation: files with PII/DLP findings get +100 risk, security/auth/crypto paths get +50 risk, API routes get +30 risk.
  4. Cap reviewable files at `MAX_REVIEW_FILES_CAP` (default 200). If total files exceed cap, sort descending by risk score and truncate, populating `PRTriageSummary`.
- **Implementation Notes:** Ensure `fetch_pr_modified_lines()` reuses `fetch_all_pr_modified_files()` for backward compatibility.
- **Status:** `- [ ] Pending`

### Step 2: Token Estimation & Partitioner in `helper.py`
- **Files to modify:** [`.github/scripts/helper.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/helper.py)
- **Changes needed:**
  1. Implement lightweight token estimation: `len(patch) // 4` or line-based heuristic.
  2. Implement `partition_files_into_batches(files, max_files_per_batch=25, max_tokens_per_batch=60_000)`:
     - Group files into batches without exceeding either constraint.
     - Single files exceeding `max_tokens_per_batch` get placed into a solo batch with truncated diff hunks.
- **Implementation Notes:** Ensure batch indices are 1-indexed (`batch_index` out of `total_batches`).
- **Status:** `- [ ] Pending`

### Step 3: Isolated Context Batch Reviewer in `pr_reviewer_agent.py`
- **Files to modify:** [`.github/scripts/pr_reviewer_agent.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/pr_reviewer_agent.py)
- **Changes needed:**
  1. Define `BatchReviewResult` schema with `response_schema=BatchReviewResult`.
  2. Implement `review_batch_with_isolated_context()`:
     - Formulate batch-specific prompt containing only that batch's file paths and patch hunks.
     - Spin up `async with Agent(config) as agent:` session.
     - Call `await agent.chat(batch_prompt)`.
     - Extract `await response.structured_output()` as `BatchReviewResult`.
     - Close agent session so context memory is released.
- **Implementation Notes:** Track cumulative token usage across batches. If cumulative tokens reach `MAX_TOTAL_TOKENS`, break early and synthesize partial results.
- **Status:** `- [ ] Pending`

### Step 4: Finding Aggregator & Final Report Synthesis in `pr_reviewer_agent.py`
- **Files to modify:** [`.github/scripts/pr_reviewer_agent.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/pr_reviewer_agent.py)
- **Changes needed:**
  1. Collect all `findings` from completed batches.
  2. If any finding has `BLOCKER` severity or `pii_leak=True`, enforce `ReviewStatus.REQUEST_CHANGES`.
  3. If all batches clean and zero findings, enforce `ReviewStatus.APPROVE`.
  4. Append triage summary note to `summary` if files were capped (e.g., *"Reviewed 200 of 10,000 modified files based on risk triage..."*).
  5. Save reports to `reports/pr-review.json` and post to GitHub PR via `post_github_pr_review()`.
- **Status:** `- [ ] Pending`

### Step 5: Configuration Resolution & Workflow Updates
- **Files to modify:**
  - [`.github/scripts/helper.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/helper.py)
  - [`.github/workflows/source-code-pii-review.yml`](file:///Users/yannipeng/git-projects/adk-agents/.github/workflows/source-code-pii-review.yml)
- **Changes needed:**
  1. Update `resolve_env_config()` to support:
     - `BATCH_MAX_FILES` (default 25)
     - `BATCH_MAX_TOKENS` (default 60,000)
     - `MAX_REVIEW_FILES_CAP` (default 200)
  2. Expose these variables in workflow YAML env blocks.
- **Status:** `- [ ] Pending`

### Step 6: Acceptance & Contract Unit Tests
- **Files to create/modify:**
  - [`.github/scripts/tests/test_helper.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/tests/test_helper.py)
  - [`.github/scripts/tests/test_pr_reviewer_agent.py`](file:///Users/yannipeng/git-projects/adk-agents/.github/scripts/tests/test_pr_reviewer_agent.py)
- **Changes needed:**
  1. Test GitHub pagination across multiple pages of `/files`.
  2. Test file exclusion rules (lockfiles, assets, minified code).
  3. Test triage capping on simulated 10,000 file PR.
  4. Test batch partitioning respecting file and token thresholds.
  5. Test isolated-context batch review execution and final finding aggregation.
- **Status:** `- [ ] Pending`

---

## 🧪 Verification & Testing Strategy

### Unit/Integration Tests
1. **Pagination & Triage Tests (`test_helper.py`):**
   - Mock GitHub API returning 3 pages of files (250 files total). Verify all 250 are discovered.
   - Inject lockfiles and test they are filtered out.
   - Simulate 1,000 files with `MAX_REVIEW_FILES_CAP=50`; assert exactly 50 highest-risk files are retained and `PRTriageSummary.triage_applied` is True.
2. **Batching Tests (`test_helper.py`):**
   - Provide 100 files with varied diff sizes; assert batches do not exceed 25 files or 60,000 tokens.
3. **Multi-Batch Agent Execution (`test_pr_reviewer_agent.py`):**
   - Mock `Agent` chat returning distinct findings across 3 batches.
   - Assert all findings are aggregated into the final `PRReviewReport`.
   - Assert `REQUEST_CHANGES` is triggered if any batch contains a blocker.
   - Assert context memory does not carry over between batches.

### Commands
```bash
# Run helper unit tests
uv run pytest .github/scripts/tests/test_helper.py -v

# Run agent multi-batch contract tests
uv run pytest .github/scripts/tests/test_pr_reviewer_agent.py -v

# Run full project test suite
uv run pytest tests/ .github/scripts/tests/ -v
```

### Expected Results
- All unit and contract tests pass with 0 failures.
- PRs with 100+ or 10,000 files complete review without context length errors or budget halts.
- Context size per batch stays strictly bounded (< 70,000 tokens).

---

## 🎯 Success Criteria
1. **Zero Context Overflows:** PRs with arbitrary file counts (up to 10,000 files) never exceed the 1M token context window or crash with HTTP 400.
2. **Context Isolation per Batch:** Each batch is processed in a clean session, discarding raw diff contents before the next batch starts.
3. **Intelligent Triage & Capping:** Massive PRs (> 200 reviewable files) are automatically prioritized by risk score and security sensitivity, with transparent summary reporting.
4. **Resilient Aggregate Reporting:** All findings across batches are merged, deduplicated against diff coordinates, and serialized to [`reports/pr-review.json`](file:///Users/yannipeng/git-projects/adk-agents/reports/pr-review.json).
5. **Full Backward Compatibility:** Existing Quality Gate criteria and single-file/small PR workflows continue to pass without regression.
