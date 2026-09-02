# Spec: Account Health Scoring (OPS-13)

**Status:** `Approved`

---

## What this does

Customer Success (CS) needs early visibility into at-risk customer accounts weeks before renewal cycles and cancellation emails arrive. This service ingests monthly customer usage export data, computes a deterministic health score (0–10 scale), assigns each account to an actionable health tier (`HEALTHY`, `MEDIUM`, `AT RISK`), and outputs explicit, human-explainable deduction reasons so CSMs have clear context for proactive outreach.

---

## Input

The input is a UTF-8 CSV text string representing the monthly account usage export.

### CSV Schema & Constraints:
- Columns: `account_id` (string), `month` (`YYYY-MM`), `seats_active` (integer or blank), `logins` (integer), `tickets_open` (integer).
- Column order is position-independent and matched by header name.
- Blank `seats_active` values are parsed as `0`.
- Missing/blank `logins` or `tickets_open`, negative numeric values, and duplicate `(account_id, month)` rows raise `ValueError`.
- Empty CSV text or headers-only input produces an empty dictionary `{}`.

---

## The two halves

The system is strictly partitioned into two pure functions in `scorer/usage.py` that perform zero filesystem, network, or OS I/O:

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class MonthSnapshot:
    account_id: str
    month: str          # "YYYY-MM"
    seats_active: int   # >= 0, blank in CSV parsed as 0
    logins: int         # >= 0
    tickets_open: int   # >= 0

@dataclass(frozen=True)
class Result:
    score: int          # 0..10 inclusive
    tier: str           # "HEALTHY" | "MEDIUM" | "AT RISK"
    reasons: list[str]  # Ordered deduction reasons that fired

def parse_usage(csv_text: str) -> dict[str, list[MonthSnapshot]]:
    """Group export text by account, each list in ascending month order."""
    ...

def score(months: list[MonthSnapshot]) -> Result:
    """Score one account's chronological months. Never reads CSV or filesystem."""
    ...
```

The CLI entrypoint in `scorer/main.py` is the only module that performs file I/O, loading `fixtures/usage.csv` and printing sorted terminal output.

---

## Rules

### 1. Baseline Score & Flooring
- Every account starts with a baseline score of **10**.
- The score is floored at **0** (minimum score is 0; never negative).

### 2. Health Tiers
- `HEALTHY`: Score **8 – 10**
- `MEDIUM`: Score **5 – 7**
- `AT RISK`: Score **0 – 4**

### 3. Deductions & Evaluation Order
Deductions are evaluated in strict order against the latest chronological month:
1. **Seat Decline (−4 points, reason: `seats down sharply`)**:
   - The latest month's `seats_active` has fallen by **40% or more** compared to the peak (maximum) `seats_active` across all prior recorded months (`months[:-1]`).
   - *Condition:* `latest_seats <= peak_prior_seats * 0.60` (where `peak_prior_seats = max(m.seats_active for m in months[:-1])`).
   - Single-month accounts have no prior history and never trigger this rule.
   - If `peak_prior_seats == 0`, this rule does not trigger.
2. **Low Engagement (−3 points, reason: `low engagement`)**:
   - The latest month has strictly fewer than 3 logins (`latest_month.logins < 3`).
3. **Unresolved Support Load (−2 points, reason: `unresolved support load`)**:
   - The latest month has 2 or more open support tickets (`latest_month.tickets_open >= 2`).

### 4. Reason Ordering
`Result.reasons` must strictly maintain the evaluation order:
`["seats down sharply", "low engagement", "unresolved support load"]` (omitting reasons for rules that did not trigger). When no deductions trigger, `reasons` is `[]`.

---

## Out of scope

- Direct database connections, CRM integrations (Salesforce/HubSpot), or Slack/email automated messaging.
- Real-time streaming usage ingestion.
- Modifying or writing files inside `scorer/usage.py`.
- Dynamic rule weight configuration outside `scorer/usage.py`.

---

## Decisions

| ID | Rule a builder follows | Passage it resolves | Case that would differ |
| :--- | :--- | :--- | :--- |
| **D-1** | Blank `seats_active` cells in CSV are parsed as integer `0`. | Missing seat values in exports | Empty string vs raising ValueError vs parsing as 0 |
| **D-2** | Snapshots for each account must be sorted in ascending order by `month` (`YYYY-MM`). | CSV rows appearing out of chronological order | Comparing latest month vs last row in CSV |
| **D-3** | Accounts with only 1 month of historical data never trigger the seat decline deduction. | Single-month accounts having no prior baseline | Triggering false positive 100% drop on month 1 |
| **D-4** | Seat decline deduction triggers when `latest_seats <= peak_prior_seats * 0.60`. | Ambiguity around 40% drop threshold calculation | Comparing against previous month vs prior peak |
| **D-5** | Low engagement deduction triggers strictly when `logins < 3` in latest month. | Definition of low engagement | `<= 3` vs `< 3` |
| **D-6** | Unresolved support load deduction triggers when `tickets_open >= 2` in latest month. | Definition of support backlog | `> 2` vs `>= 2` |
| **D-7** | Base score is 10, total score is floored at `0` via `max(0, 10 - deductions)`. | Score bounds when multiple deductions total > 10 | Negative score vs floored at 0 |
| **D-8** | Tiers are partitioned: `HEALTHY` (8–10), `MEDIUM` (5–7), `AT RISK` (0–4). | Boundary placement for health tiers | Score 7 being HEALTHY vs MEDIUM |
| **D-9** | Deduction reasons list preserves order: `seats down sharply`, `low engagement`, `unresolved support load`. | Ordering of reasons in output | Alphabetical vs arbitrary vs evaluation order |
| **D-10** | `score([])` with an empty list raises `ValueError("months must not be empty")`. | Invoking scorer on empty account history | Returning default Result vs raising exception |
| **D-11** | `parse_usage()` returns `{}` if CSV contains only headers or empty lines. | Parsing empty usage export | Returning `{}` vs throwing exception |
| **D-12** | CSV parsing matches columns by header name, independent of header order. | CSV export column permutations | Positional index parsing vs header DictReader |
| **D-13** | Blank/invalid `logins` or `tickets_open` values raise `ValueError`. | Malformed numeric fields in CSV | Defaulting to 0 vs rejecting corrupt data |
| **D-14** | Negative values for numeric fields raise `ValueError`. | Corrupted or negative metric values in CSV | Silent parsing vs strict validation |
| **D-15** | Duplicate `(account_id, month)` records in CSV raise `ValueError`. | Overlapping export records | Overwriting vs keeping first vs raising error |

---

## Open questions

*(None. All edge cases, schemas, and scoring boundaries are resolved.)*

---

## The gate

- **Status:** `Approved`
- **Open questions:** Empty
- **Testability:** Every rule is backed by an explicit Decision ID (`D-1` through `D-15`) ready for acceptance contract test assertions.
