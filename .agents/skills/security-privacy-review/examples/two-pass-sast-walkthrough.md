# Two-Pass SAST & Taint Analysis Walkthrough

This walkthrough demonstrates how the `security-privacy-review` skill applies the **Two-Pass "Recon & Investigate" Model** during an actual audit.

---

## Scenario
Auditing a Pull Request modifying `adk_bug_ticket_agent/views.py` and `adk_bug_ticket_agent/tools/tools.py`.

---

## Step 1: Initial Planning (Phase 0)
The agent initializes `.gemini_security/` and writes high-level objectives to `SECURITY_ANALYSIS_TODO.md`:

```markdown
# Security Analysis Todo
- [ ] Determine scope of files modified in branch/PR
- [ ] Perform SAST analysis across target files
- [ ] Compile final audit report
```

---

## Step 2: Dynamic Plan Expansion (Phase 1)
After running `git diff --name-only origin/main...HEAD`, the agent identifies in-scope files:

```markdown
# Security Analysis Todo
- [ ] SAST Recon on `adk_bug_ticket_agent/views.py`
- [ ] SAST Recon on `adk_bug_ticket_agent/tools/tools.py`
```

---

## Step 3: Reconnaissance Pass (Phase 2A)
The agent performs a rapid scan of `adk_bug_ticket_agent/views.py` to identify Sources without deep tracing:

```markdown
# Security Analysis Todo
- [x] SAST Recon on `adk_bug_ticket_agent/views.py`
  - [ ] Investigate data flow from `request.POST.get('ticket_id')` on line 24
  - [ ] Investigate `@csrf_exempt` decorator on `interact_with_agent` view on line 18
- [ ] SAST Recon on `adk_bug_ticket_agent/tools/tools.py`
  - [ ] Investigate tool parameter `query_filter` on line 35
```

---

## Step 4: Deep-Dive Investigation Pass (Phase 2B)
The agent sequentially performs taint analysis on each item:

1. **Trace 1:** `request.POST.get('ticket_id')` (line 24)
   - Followed to `fetch_ticket_details(ticket_id)`
   - Traced to database query: `Ticket.objects.filter(id=ticket_id)`
   - **Result:** SAFE. Django ORM automatically parameterizes queries.

2. **Trace 2:** `@csrf_exempt` on `interact_with_agent` (line 18)
   - Endpoint receives POST requests from web UI or external API.
   - Evaluated authorization: Endpoint lacks API key or session CSRF validation.
   - **Result:** MEDIUM RISK. Documented in `DRAFT_SECURITY_REPORT.md`.

3. **Trace 3:** `query_filter` in `tools.py` (line 35)
   - Traced to `connection.cursor().execute(f"SELECT * FROM logs WHERE {query_filter}")`
   - **Result:** CRITICAL VULNERABILITY (SQL Injection). Documented in `DRAFT_SECURITY_REPORT.md`.

Updated `SECURITY_ANALYSIS_TODO.md`:
```markdown
# Security Analysis Todo
- [x] SAST Recon on `adk_bug_ticket_agent/views.py`
  - [x] Investigate data flow from `request.POST.get('ticket_id')` on line 24 (SAFE)
  - [x] Investigate `@csrf_exempt` decorator on `interact_with_agent` view on line 18 (FLAGGED)
- [x] SAST Recon on `adk_bug_ticket_agent/tools/tools.py`
  - [x] Investigate tool parameter `query_filter` on line 35 (CRITICAL SQLi)
```

---

## Step 5: Final Report & Remediation (Phase 4)
The agent compiles findings into the standard report format and removes `.gemini_security/` temporary files.

