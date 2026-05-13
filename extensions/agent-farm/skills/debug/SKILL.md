---
name: debug
description: Systematic debugging workflow. Use when confronted with a bug, error message, or unexpected behavior to systematically reproduce, isolate, and fix the root cause.
---

# Systematic Debugging Workflow

## Instructions

1. **Reproduce the issue:** Run the failing scenario to confirm the bug. Capture the exact error message, stack trace, or unexpected output.
2. **Read the logs:** Check application logs, test output, and stderr for clues. Search for the error message in the codebase to find where it originates.
3. **Isolate the root cause:** Trace the call stack from the error back to the source.
   - Add temporary logging or print statements if needed.
   - Use `git bisect` if the bug is a regression and the failing commit is unclear.
   - Narrow down to the specific function, line, or condition that causes the failure.
4. **Implement the fix:** Make the minimal change needed to resolve the root cause. Do not refactor surrounding code.
5. **Write a regression test:** Add a test that fails without the fix and passes with it to prevent recurrence.
6. **Verify the fix:** Run the full test suite to confirm the regression test passes, no existing tests are broken, and the original reproduction case works correctly.
7. **Clean up:** Remove any temporary logging or debug statements added.
8. **Report back:** Summarize what the bug was, what caused it, what the fix was, and what test was added.