 i tested the pr reivew pipeline and got the following result:
  
  📊 PR Reviewer Token Usage & Estimated Spend
  Metric    Value
  Model    gemini-3.7-flash
  Execution Status    ✅ Normal (UNSPECIFIED)
  Prompt Tokens (Uncached)    44,366
  Cached Prompt Tokens    0
  Candidate Generation Tokens    151
  Reasoning / Thought Tokens    2,263
  Total Tokens Billed    46,780
  Estimated Spend (USD)    $0.042327
  
  what is Candidate Generation Tokens ?? And why  Cached Prompt Tokens    0 ???

▸ Thought for 1m 0s
  I've analyzed the token cost calculation in `helper.py`. It appears my instr...
  ### 1. What Are "Candidate Generation Tokens"?

  In Gemini APIs and the Google Agent Development Kit (ADK), the model’s
  generated output is divided into two distinct components when
  reasoning/thinking is active:
  • Reasoning / Thought Tokens (2,263): The internal "chain-of-thought"
  scratchpad tokens generated while the model analyzes the diffs, checks logic,
  and decides whether there are bugs or PII leaks.
  • Candidate Generation Tokens (151): The actual visible output payload
  returned by the model (in Gemini terminology, a completion response is called
  a "candidate").

  In this run, the 151 tokens represent the final structured JSON output
  conforming to pr_reviewer_agent.py:96-128 (e.g., batch_summary, findings
  list, and status flags).
  Both Candidate Tokens and Thought Tokens are billed at the candidate/output
  rate ($3.75 per 1M tokens on gemini-3.7-flash).
  ──────
  ### 2. Why Are "Cached Prompt Tokens" 0?
  Gemini's Prompt Caching mechanism shows 0 here for the following reasons:
  #### A. Unique PR Diffs (Cache Miss)
  Prompt caching in Gemini functions as an exact prefix match. Even when a
  prompt exceeds the minimum cache eligibility threshold (~32,768 tokens):

  • Every Pull Request review prompt includes unique, dynamic content: file
  diffs, commit SHA, PR number, and file paths.
  • Because these diffs are seen for the first time in this run, there was no
  pre-warmed cache with an identical token prefix in the Vertex AI serving
  cluster.
  #### B. Dynamic vs. Explicit Cache Creation
  • Automatic / Implicit Caching: Occurs only when identical prompts or
  identical long prefixes are sent repeatedly within a short TTL window
  (typically 5–60 minutes depending on the tier).
  • Explicit Caching: Gemini supports creating dedicated, persistent cache
  objects (CachedContent.create) for large, static assets (e.g., an entire
  codebase, a 500-page manual, or a massive codebase embedding). In CI/CD
  review workflows, code diffs vary with every commit, so static cache pinning
  is not automatically created.
  • The shared static portion of the prompt (the system instructions in
  pr_reviewer_agent.py:78) is only ~600 tokens, which is far below the minimum
  32k token threshold required by Vertex AI to create a cache entry.
  ──────
  ### Breakdown of the Spend Calculation

  From helper.py:1170-1235:

                                                $0.75
       Prompt Tokens (Uncached):   44, 366 × ───────────    = $0.033275
                                             1, 000, 000
                                            $3.75
    Candidate Generation Tokens:   151 × ───────────        = $0.000566
                                         1, 000, 000
                                               $3.75
     Reasoning / Thought Tokens:   2, 263 × ───────────     = $0.008486
                                            1, 000, 000
              hline Total Spend:                            = $𝟎.𝟎𝟒𝟐𝟑𝟐𝟕