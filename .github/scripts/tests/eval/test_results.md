============================= test session starts ==============================
platform linux -- Python 3.11.16, pytest-9.1.1, pluggy-1.6.0 -- /opt/hostedtoolcache/Python/3.11.16/x64/bin/python
cachedir: .pytest_cache
rootdir: /home/runner/work/adk-agents/adk-agents
configfile: pyproject.toml
plugins: anyio-4.15.1, asyncio-1.4.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 25 items / 16 deselected / 9 selected

.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc01_clean_code] FAILED [ 11%]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc02_secret_leak] PASSED [ 22%]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc03_sql_injection] PASSED [ 33%]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc04_zero_division] PASSED [ 44%]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc05_style_suggestion] PASSED [ 55%]
.github/scripts/tests/eval/test_inference_quality_gate.py::test_live_inference_quality_gate[tc01_clean_code] PASSED [ 66%]
.github/scripts/tests/eval/test_inference_quality_gate.py::test_live_inference_quality_gate[tc02_secret_leak] PASSED [ 77%]
.github/scripts/tests/eval/test_inference_quality_gate.py::test_live_inference_quality_gate[tc06_fail_closed_dlp] PASSED [ 88%]
.github/scripts/tests/eval/test_inference_quality_gate.py::test_live_inference_quality_gate[tc07_blocker_alignment] FAILED [100%]

=================================== FAILURES ===================================
_______________ test_live_inference_pr_reviewer[tc01_clean_code] _______________

case_id = 'tc01_clean_code'
load_eval_case = <function load_eval_case.<locals>._loader at 0x7fea49f49ee0>
eval_cases_dir = PosixPath('/home/runner/work/adk-agents/adk-agents/.github/scripts/tests/eval/cases')
mock_dlp_report = <function mock_dlp_report.<locals>._factory at 0x7fea49f4a5c0>
tmp_path = PosixPath('/tmp/pytest-of-runner/pytest-0/test_live_inference_pr_reviewe0')

    @pytest.mark.inference
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "case_id",
        [
            "tc01_clean_code",
            "tc02_secret_leak",
            "tc03_sql_injection",
            "tc04_zero_division",
            "tc05_style_suggestion",
        ],
    )
    async def test_live_inference_pr_reviewer(
        case_id: str,
        load_eval_case: Any,
        eval_cases_dir: Path,
        mock_dlp_report: Any,
        tmp_path: Path,
    ):
        """Executes live model inference for a golden test case and asserts review accuracy."""
        try:
            case = load_eval_case(case_id)
        except FileNotFoundError:
            pytest.skip(f"Test case fixture {case_id}.json not yet populated on disk")
    
        # Extract case attributes safely whether case is EvalCase model or raw dict
        if hasattr(case, "diff_content"):
            diff_content = case.diff_content
            modified_files = case.modified_files
            category = case.category
            pii_scan = case.pii_scan_content
            expected_review = case.expected_review
        else:
            diff_content = case.get("diff_content", "")
            modified_files = case.get("modified_files", {})
            category = case.get("category", "")
            pii_scan = case.get("pii_scan_content", "✅ No sensitive data or PII detected.")
            expected_review = case.get("expected_review")
    
        dlp_path = mock_dlp_report(
            clean=("secret" not in category and "pii" not in category),
            custom_content=pii_scan,
        )
    
        # Prepare raw files diff representation
        raw_files = [
            {
                "filename": fn,
                "status": "modified",
                "patch": diff_content,
                "changes": len(lines) if isinstance(lines, list) else 10,
                "additions": len(lines) if isinstance(lines, list) else 10,
            }
            for fn, lines in (modified_files.items() if modified_files else {"main.py": [1]})
        ]
    
        # Wire mock MCP server if available
        fixture_file = eval_cases_dir / f"{case_id}.json"
        mcp_server = None
        if create_mock_github_mcp_server is not None and fixture_file.exists():
            mcp_server = create_mock_github_mcp_server(str(fixture_file))
    
        mcp_patcher = (
            patch("pr_reviewer_agent.create_github_mcp_server", return_value=mcp_server)
            if mcp_server is not None
            else patch("pr_reviewer_agent.create_github_mcp_server", return_value=None)
        )
    
        with (
            mcp_patcher,
            patch("pr_reviewer_agent.fetch_all_pr_modified_files", return_value=raw_files),
            patch("pr_reviewer_agent.fetch_pr_comments", return_value=[]),
            patch("pr_reviewer_agent.send_github_review_sync", return_value={"id": 1}),
            patch("pr_reviewer_agent.send_github_issue_comment_sync", return_value={"id": 1}),
        ):
            report = await run_pr_review(
                pr_number="101",
                repo="octocat/hello-world",
                token="ghp_mock_token_for_inference",
                pii_report_path=str(dlp_path),
                project_id=os.environ.get("GOOGLE_CLOUD_PROJECT", "test-gcp-project"),
                location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
                model=os.environ.get("LLM_Model", "gemini-3.7-flash"),
                modified_files_diff=modified_files,
                max_total_tokens=150000,
                max_model_calls=5,
                max_tool_calls=10,
            )
    
        # 1. Schema Invariant: LLM output must successfully deserialize into PRReviewReport
        assert report is not None, "PR reviewer agent returned None"
        assert isinstance(report, PRReviewReport), f"Expected PRReviewReport instance, got {type(report)}"
    
        # 2. Case-specific assertions
        if case_id == "tc01_clean_code":
>           assert report.overall_status == ReviewStatus.APPROVE, (
                f"Clean code was rejected with status {report.overall_status}"
            )
E           AssertionError: Clean code was rejected with status ReviewStatus.COMMENT
E           assert <ReviewStatus...NT: 'COMMENT'> == <ReviewStatus...VE: 'APPROVE'>
E             
E             - APPROVE
E             + COMMENT

.github/scripts/tests/eval/test_inference_pr_reviewer.py:142: AssertionError
----------------------------- Captured stdout call -----------------------------

============================================================
🤖 BATCH 1/1 AGENT EXECUTION & THINKING STREAM
============================================================
Finished
🔧 [Tool Call] finish({'output_string': '{"batch_index":1,"batch_summary":"Reviewed changes across `web_ui/views.py` and `web_ui/tests.py`. The addition of the `/health/` operational status endpoint and its accompanying unit tests is clean, well-typed, and robust. No security, DLP/PII leaks, or performance issues were found. A minor suggestion is included to enforce HTTP GET method restrictions via `@require_GET`.","findings":[{"details":"The `health_check` view currently accepts all HTTP verbs (such as POST, PUT, DELETE) and returns HTTP 200 OK. Restricting health check endpoints to GET requests using Django\'s `@require_GET` decorator enforces RESTful semantics and ensures non-GET requests are properly rejected with HTTP 405 Method Not Allowed.","file_path":"web_ui/views.py","line_number":12,"pii_leak":false,"severity":"SUGGESTION","suggestion":"from django.views.decorators.http import require_GET\\n\\n\\n@require_GET\\ndef health_check(request: HttpRequest) -\\u003e JsonResponse:\\n    \\"\\"\\"Returns system operational status.\\"\\"\\"\\n    return JsonResponse({\\"status\\": \\"ok\\", \\"service\\": \\"it-bug-assistant\\"}, status=200)","title":"Restrict health check endpoint to GET requests"}]}'})

------------------------------------------------------------

📄 [Structured LLM Output (BatchReviewResult 1/1)]:
{
  "batch_index": 1,
  "batch_summary": "Reviewed changes across `web_ui/views.py` and `web_ui/tests.py`. The addition of the `/health/` operational status endpoint and its accompanying unit tests is clean, well-typed, and robust. No security, DLP/PII leaks, or performance issues were found. A minor suggestion is included to enforce HTTP GET method restrictions via `@require_GET`.",
  "findings": [
    {
      "file_path": "web_ui/views.py",
      "line_number": 12,
      "severity": "SUGGESTION",
      "title": "Restrict health check endpoint to GET requests",
      "details": "The `health_check` view currently accepts all HTTP verbs (such as POST, PUT, DELETE) and returns HTTP 200 OK. Restricting health check endpoints to GET requests using Django's `@require_GET` decorator enforces RESTful semantics and ensures non-GET requests are properly rejected with HTTP 405 Method Not Allowed.",
      "suggestion": "from django.views.decorators.http import require_GET\n\n\n@require_GET\ndef health_check(request: HttpRequest) -> JsonResponse:\n    \"\"\"Returns system operational status.\"\"\"\n    return JsonResponse({\"status\": \"ok\", \"service\": \"it-bug-assistant\"}, status=200)",
      "pii_leak": false
    }
  ]
}
============================================================


============================================================
📊 CUMULATIVE TOKEN USAGE & ESTIMATED SPEND
============================================================
Model: gemini-3.7-flash
Prompt Tokens (Uncached): 11,696
Cached Tokens: 0
Candidate Tokens: 300
Reasoning / Thought Tokens: 1,619
Total Tokens: 13,615
Estimated Spend: $0.015968 USD
Stop Reason: UNSPECIFIED
Batches Executed: 1 / 1
============================================================


📄 [Structured LLM Output (PRReviewReport)]:
{
  "overall_status": "COMMENT",
  "summary": "Reviewed changes across `web_ui/views.py` and `web_ui/tests.py`. The addition of the `/health/` operational status endpoint and its accompanying unit tests is clean, well-typed, and robust. No security, DLP/PII leaks, or performance issues were found. A minor suggestion is included to enforce HTTP GET method restrictions via `@require_GET`.",
  "findings": [
    {
      "file_path": "web_ui/views.py",
      "line_number": 12,
      "severity": "SUGGESTION",
      "title": "Restrict health check endpoint to GET requests",
      "details": "The `health_check` view currently accepts all HTTP verbs (such as POST, PUT, DELETE) and returns HTTP 200 OK. Restricting health check endpoints to GET requests using Django's `@require_GET` decorator enforces RESTful semantics and ensures non-GET requests are properly rejected with HTTP 405 Method Not Allowed.",
      "suggestion": "from django.views.decorators.http import require_GET\n\n\n@require_GET\ndef health_check(request: HttpRequest) -> JsonResponse:\n    \"\"\"Returns system operational status.\"\"\"\n    return JsonResponse({\"status\": \"ok\", \"service\": \"it-bug-assistant\"}, status=200)",
      "pii_leak": false
    }
  ]
}
============================================================

[Warning] Failed to post PR review to GitHub (HTTP 401: {
  "message": "Bad credentials",
  "documentation_url": "https://docs.github.com/rest",
  "status": "401"
}).
___________ test_live_inference_quality_gate[tc07_blocker_alignment] ___________

case_id = 'tc07_blocker_alignment'
mock_dlp_report = <function mock_dlp_report.<locals>._factory at 0x7fea49f8d080>
mock_pr_review_file = <function mock_pr_review_file.<locals>._factory at 0x7fea49f8ff60>
load_eval_case = <function load_eval_case.<locals>._loader at 0x7fea49f8f600>
tmp_path = PosixPath('/tmp/pytest-of-runner/pytest-0/test_live_inference_quality_ga3')

    @pytest.mark.inference
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "case_id",
        [
            "tc01_clean_code",
            "tc02_secret_leak",
            "tc06_fail_closed_dlp",
            "tc07_blocker_alignment",
        ],
    )
    async def test_live_inference_quality_gate(
        case_id: str,
        mock_dlp_report: Any,
        mock_pr_review_file: Any,
        load_eval_case: Any,
        tmp_path: Path,
    ):
        """Executes live model inference for Quality Gate decision scenarios and asserts gating accuracy."""
        # Attempt to load custom case fixture if present, or use built-in canonical fixtures
        case = None
        try:
            case = load_eval_case(case_id)
        except FileNotFoundError:
            pass
    
        # Setup report files based on scenario
        if case_id == "tc01_clean_code":
            dlp_file = mock_dlp_report(clean=True)
            pr_file = mock_pr_review_file(approved=True)
        elif case_id == "tc02_secret_leak":
            dlp_file = mock_dlp_report(clean=False)
            pr_file = mock_pr_review_file(approved=False)
        elif case_id == "tc06_fail_closed_dlp":
            # Missing DLP report simulates scanning failure or missing artifact (fail-closed)
            dlp_file = tmp_path / "nonexistent-dlp-scan.txt"
            pr_file = mock_pr_review_file(approved=True)
        elif case_id == "tc07_blocker_alignment":
            # DLP clean, but PR Reviewer found architectural / logic blockers
            dlp_file = mock_dlp_report(clean=True)
            pr_file = mock_pr_review_file(approved=False)
        else:
            pytest.fail(f"Unknown test case scenario: {case_id}")
    
        decision = await evaluate_quality_gate(
            pii_report_path=str(dlp_file),
            pr_review_path=str(pr_file),
            project_id=os.environ.get("GOOGLE_CLOUD_PROJECT", "test-gcp-project"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
            model=os.environ.get("LLM_Model", "gemini-3.7-flash"),
            pr_number="101",
        )
    
        # 1. Schema Invariant: Must deserialize into QualityGateDecision
        assert isinstance(decision, QualityGateDecision), (
            f"Expected QualityGateDecision instance, got {type(decision)}"
        )
    
        # 2. Scenario-specific gating assertions
        if case_id == "tc01_clean_code":
            assert decision.passed is True, "Clean PR was unexpectedly blocked by Quality Gate"
            assert len(decision.failures) == 0, "Clean PR produced unexpected failure details"
    
        elif case_id == "tc02_secret_leak":
            assert decision.passed is False, "Secret leak was not blocked by Quality Gate"
            assert len(decision.failures) >= 1, "Secret leak failure details were empty"
            assert any(
                f.category in (ViolationCategory.PII_LEAK, ViolationCategory.CREDENTIAL_LEAK)
                for f in decision.failures
            ), "Expected PII_LEAK or CREDENTIAL_LEAK violation category"
    
        elif case_id == "tc06_fail_closed_dlp":
            assert decision.passed is False, "Missing DLP report did not trigger fail-closed gating"
            assert len(decision.failures) >= 1, "Missing DLP report should produce at least one failure"
            assert any(
                "dlp" in f.reason.lower() or "cloud dlp" in f.component.lower()
                for f in decision.failures
            ), "Failure reason does not mention missing DLP report"
    
        elif case_id == "tc07_blocker_alignment":
            assert decision.passed is False, "PR review blockers did not trigger Quality Gate failure"
            assert len(decision.failures) >= 1, "PR review blockers produced 0 failure details"
>           assert any(
                f.category == ViolationCategory.ARCHITECTURAL_DEFECT
                or "pr" in f.component.lower()
                or "review" in f.component.lower()
                for f in decision.failures
            ), "Expected ARCHITECTURAL_DEFECT or PR review failure component"
E           AssertionError: Expected ARCHITECTURAL_DEFECT or PR review failure component
E           assert False
E            +  where False = any(<generator object test_live_inference_quality_gate.<locals>.<genexpr> at 0x7fea49ea7760>)

.github/scripts/tests/eval/test_inference_quality_gate.py:121: AssertionError
=============================== warnings summary ===============================
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc01_clean_code]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc02_secret_leak]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc03_sql_injection]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc04_zero_division]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc05_style_suggestion]
.github/scripts/tests/eval/test_inference_quality_gate.py::test_live_inference_quality_gate[tc01_clean_code]
.github/scripts/tests/eval/test_inference_quality_gate.py::test_live_inference_quality_gate[tc02_secret_leak]
.github/scripts/tests/eval/test_inference_quality_gate.py::test_live_inference_quality_gate[tc07_blocker_alignment]
  /opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/google/antigravity/types.py:595: DeprecationWarning: CapabilitiesConfig.compaction_threshold is deprecated. Configure CompactionConfig(token_threshold=...) directly on AgentConfig instead.
    if self.compaction_threshold is not None:

.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc01_clean_code]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc02_secret_leak]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc03_sql_injection]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc04_zero_division]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc05_style_suggestion]
.github/scripts/tests/eval/test_inference_quality_gate.py::test_live_inference_quality_gate[tc01_clean_code]
.github/scripts/tests/eval/test_inference_quality_gate.py::test_live_inference_quality_gate[tc02_secret_leak]
.github/scripts/tests/eval/test_inference_quality_gate.py::test_live_inference_quality_gate[tc07_blocker_alignment]
  /opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/google/antigravity/connections/connection.py:113: DeprecationWarning: CapabilitiesConfig.compaction_threshold is deprecated. Configure CompactionConfig(token_threshold=...) directly on AgentConfig instead.
    and self.capabilities.compaction_threshold is not None

.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc01_clean_code]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc02_secret_leak]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc03_sql_injection]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc04_zero_division]
.github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc05_style_suggestion]
.github/scripts/tests/eval/test_inference_quality_gate.py::test_live_inference_quality_gate[tc01_clean_code]
.github/scripts/tests/eval/test_inference_quality_gate.py::test_live_inference_quality_gate[tc02_secret_leak]
.github/scripts/tests/eval/test_inference_quality_gate.py::test_live_inference_quality_gate[tc07_blocker_alignment]
  /opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/google/antigravity/connections/local/local_connection.py:113: DeprecationWarning: CapabilitiesConfig.compaction_threshold is deprecated. Configure CompactionConfig(token_threshold=...) directly on AgentConfig instead.
    if capabilities.compaction_threshold is not None:

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
- generated xml file: /home/runner/work/adk-agents/adk-agents/reports/eval-results.xml -
=========================== short test summary info ============================
FAILED .github/scripts/tests/eval/test_inference_pr_reviewer.py::test_live_inference_pr_reviewer[tc01_clean_code] - AssertionError: Clean code was rejected with status ReviewStatus.COMMENT
assert <ReviewStatus...NT: 'COMMENT'> == <ReviewStatus...VE: 'APPROVE'>
  
  - APPROVE
  + COMMENT
FAILED .github/scripts/tests/eval/test_inference_quality_gate.py::test_live_inference_quality_gate[tc07_blocker_alignment] - AssertionError: Expected ARCHITECTURAL_DEFECT or PR review failure component
assert False
 +  where False = any(<generator object test_live_inference_quality_gate.<locals>.<genexpr> at 0x7fea49ea7760>)
====== 2 failed, 7 passed, 16 deselected, 24 warnings in 69.43s (0:01:09) ======