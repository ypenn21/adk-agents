# ADK Development Workflow

## Spec Resolution - Your Primary Reference

**IMPORTANT**: Identify the source of truth for the project.
*   **Conductor Projects**: Check `conductor/product.md` and `conductor/workflow.md`.
*   **Active Plans**: Check `plan/` or `tracks/` for specific implementation details.
**IMPORTANT**: Identify the source of truth for the project.
*   **Conductor Projects**: Check `conductor/product.md` and `conductor/workflow.md`.
*   **Active Plans**: Check `plan/` or `tracks/` for specific implementation details.
*   **Standard Projects**: Check these files if present:`conductor/product.md`, `conductor/workflow.md`, `DESIGN_SPEC.md`, or relevant plans in `plan/` or `tracks/`.

Read it FIRST to understand:
- Functional requirements and capabilities
- Success criteria and quality thresholds
- Agent behavior constraints
- Expected tools and integrations

**The spec is your contract.** All implementation decisions should align with it. When in doubt, refer back to .md files if present:`conductor/product.md`, `conductor/workflow.md`, `DESIGN_SPEC.md`, or relevant plans in `plan/` or `tracks/`.

## Phase 1: Understand the Spec

Before writing any code:
1. Always check these files if present:`conductor/product.md`, `conductor/workflow.md`, `DESIGN_SPEC.md`, or relevant plans in `plan/` or `tracks/`. These are the source of truth. thoroughly
2. Identify the core capabilities required
3. Note any constraints or things the agent should NOT do
4. Understand success criteria for evaluation

## Phase 2: Build and Implement

Implement the agent logic:

1. Write/modify code in `app/`
2. Use `make playground` for interactive testing during development
3. Iterate on the implementation based on user feedback

## Phase 3: The Evaluation Loop (Main Iteration Phase)

This is where most iteration happens. Work with the user to:

1. **Start small**: Begin with 1-2 sample eval cases, not a full suite
2. Run evaluations: `make eval`
3. Discuss results with the user
4. Fix issues and iterate on the core cases first
5. Only after core cases pass, add edge cases and new scenarios
6. Adjust prompts, tools, or agent logic based on results
7. Repeat until quality thresholds are met

**Why start small?** Too many eval cases at the beginning creates noise. Get 1-2 core cases passing first to validate your agent works, then expand coverage.

```bash
make eval
```

Review the output:
- `tool_trajectory_avg_score`: Are the right tools called in order?
- `response_match_score`: Do responses match expected patterns?

**Expect 5-10+ iterations here** as you refine the agent with the user.

### LLM-as-a-Judge Evaluation (Recommended)

For high-quality evaluations, use LLM-based metrics that judge response quality semantically.

**Running with custom config:**
```bash
uv run adk eval ./app <path_to_evalset.json> --config_file_path=<path_to_config.json>
```

Or use the Makefile:
```bash
make eval EVALSET=tests/eval/evalsets/my_evalset.json
```

**Configuration Schema (`test_config.json`):**

**CRITICAL:** The JSON configuration for rubrics **must use camelCase** (not snake_case).

```json
{
  "criteria": {
    "tool_trajectory_avg_score": 1.0,
    "final_response_match_v2": 0.8,
    "rubric_based_final_response_quality_v1": {
      "threshold": 0.8,
      "rubrics": [
        {
          "rubricId": "professionalism",
          "rubricContent": { "textProperty": "The response must be professional and helpful." }
        },
        {
          "rubricId": "safety",
          "rubricContent": { "textProperty": "The agent must NEVER book without asking for confirmation." }
        }
      ]
    }
  }
}
```

**EvalSet Schema (`evalset.json`):**
```json
{
  "eval_set_id": "my_eval_set",
  "eval_cases": [
    {
      "eval_id": "search_test",
      "conversation": [
        {
          "user_content": { "parts": [{ "text": "Find a flight to NYC" }] },
          "final_response": {
            "role": "model",
            "parts": [{ "text": "I found a flight for $500. Want to book?" }]
          },
          "intermediate_data": {
            "tool_uses": [
              { "name": "search_flights", "args": { "destination": "NYC" } }
            ]
          }
        }
      ],
      "session_input": { "app_name": "my_app", "user_id": "user_1", "state": {} }
    }
  ]
}
```

## Phase 4: Pre-Deployment Tests

Once evaluation thresholds are met, run tests before deployment:

```bash
make test
```

If tests fail, fix issues and run again until all tests pass.

## Phase 5: Deploy to Dev Environment

Deploy to the development environment for final testing:

1. **Notify the human**: "Eval scores meet thresholds and tests pass. Ready to deploy to dev?"
2. **Wait for explicit approval**
3. Once approved: `make deploy`

This deploys to the dev GCP project for live testing.

**IMPORTANT**: Never run `make deploy` without explicit human approval.

## Phase 6: Production Deployment - Choose Your Path

After validating in dev, **ask the user** which deployment approach they prefer:

### Option A: Simple Single-Project Deployment

**Best for:**
- Personal projects or prototypes
- Teams without complex CI/CD requirements
- Quick deployments to a single environment

**Steps:**
1. Set up infrastructure: `make setup-dev-env`
2. Deploy: `make deploy`

### Option B: Full CI/CD Pipeline

**Best for:**
- Production applications
- Teams requiring staging → production promotion
- Automated testing and deployment workflows

**Steps:**
1. If prototype, first add Terraform/CI-CD files:
   ```bash
   uvx agent-starter-pack enhance . --cicd-runner github_actions -y -s
   ```
2. Run setup-cicd with your GCP project IDs:
   ```bash
   uvx agent-starter-pack setup-cicd 
     --staging-project YOUR_STAGING_PROJECT 
     --prod-project YOUR_PROD_PROJECT 
     --repository-name YOUR_REPO_NAME 
     --repository-owner YOUR_GITHUB_USERNAME 
     --auto-approve 
     --create-repository
   ```
## Development Commands

| Command | Purpose |
|---------|---------|
| `make playground` | Interactive local testing |
| `make test` | Run unit and integration tests |
| `make eval` | Run evaluation against evalsets |
| `make eval-all` | Run all evalsets |
| `make lint` | Check code quality |
| `make setup-dev-env` | Set up dev infrastructure (Terraform) |
| `make deploy` | Deploy to dev |

## Testing Your Deployed Agent

After deployment, you can test your agent. The method depends on your deployment target.

### Getting Deployment Info

The deployment endpoint is stored in `deployment_metadata.json` after `make deploy` completes.

### Testing Agent Engine Deployment

Your agent is deployed to Vertex AI Agent Engine.

**Option 1: Using the Testing Notebook (Recommended)**

```bash
# Open the testing notebook
jupyter notebook notebooks/adk_app_testing.ipynb
```

The notebook auto-loads from `deployment_metadata.json` and provides:
- Remote testing via `vertexai.Client`
- Streaming queries with `async_stream_query`
- Feedback registration

**Option 2: Python Script**

```python
import json
import vertexai

# Load deployment info
with open("deployment_metadata.json") as f:
    engine_id = json.load(f)["remote_agent_engine_id"]

# Connect to agent
client = vertexai.Client(location="2")
agent = client.agent_engines.get(name=engine_id)

# Send a message
async for event in agent.async_stream_query(message="Hello!", user_id="test"):
    print(event)
```

**Option 3: Using the Playground**

```bash
make playground
# Open http://localhost:8000 in your browser
```

### Testing Cloud Run Deployment

Your agent is deployed to Cloud Run.

**Option 1: Using the Testing Notebook (Recommended)**

```bash
# Open the testing notebook
jupyter notebook notebooks/adk_app_testing.ipynb
```

**Option 2: Python Script**

```python
import json
import requests

SERVICE_URL = "YOUR_SERVICE_URL"  # From deployment_metadata.json
ID_TOKEN = !gcloud auth print-identity-token -q
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ID_TOKEN[0]}"}

# Step 1: Create a session
user_id = "test_user"
session_resp = requests.post(
    f"{SERVICE_URL}/apps/app/users/{user_id}/sessions",
    headers=headers,
    json={"state": {}}
)
session_id = session_resp.json()["id"]

# Step 2: Send a message
message_resp = requests.post(
    f"{SERVICE_URL}/run_sse",
    headers=headers,
    json={
        "app_name": "app",
        "user_id": user_id,
        "session_id": session_id,
        "new_message": {"role": "user", "parts": [{"text": "Hello!"}]},
        "streaming": True
    },
    stream=True
)

for line in message_resp.iter_lines():
    if line and line.decode().startswith("data: "):
        print(json.loads(line.decode()[6:]))
```

**Option 3: Using the Playground**

```bash
make playground
# Open http://localhost:8000 in your browser
```

### Deploying Frontend UI with IAP

For authenticated access to your UI (recommended for private-by-default deployments):

```bash
# Deploy frontend (builds on Cloud Build - avoids ARM/AMD64 mismatch on Apple Silicon)
gcloud run deploy SERVICE --source . --region REGION

# Enable IAP
gcloud beta run services update SERVICE --region REGION --iap

# Grant user access
gcloud beta iap web add-iam-policy-binding \
  --resource-type=cloud-run \
  --service=SERVICE \
  --region=REGION \
  --member=user:EMAIL \
  --role=roles/iap.httpsResourceAccessor
```

**Note:** Use `iap web add-iam-policy-binding` for IAP access, not `run services add-iam-policy-binding` (which is for `roles/run.invoker`).

### Testing A2A Protocol Agents

Your agent uses the A2A (Agent-to-Agent) protocol for inter-agent communication.

**Reference the integration tests** in `tests/integration/` for examples of how to call your deployed agent. The tests demonstrate the correct message format and API usage for your specific deployment target.

**A2A Protocol Common Mistakes:**

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Using `content` instead of `text` | `Invalid message format` | Use `parts[].text`, not `parts[].content` |
| Using `input` instead of `message` | `Missing message parameter` | Use `params.message`, not `params.input` |
| Missing `messageId` | `ValidationError` | Include `message.messageId` in every request |
| Missing `role` | `ValidationError` | Include `message.role` (usually "user") |

**A2A Protocol Key Details:**
- Protocol Version: 0.3.0
- Transport: JSON-RPC 2.0
- Required fields: `task_id`, `message.messageId`, `message.role`, `message.parts`
- Part structure: `{text: "...", mimeType: "text/plain"}`

**Testing approaches vary by deployment:**
- **Agent Engine**: Use the testing notebook or Python SDK (see integration tests)
- **Cloud Run**: Use curl with identity token or the testing notebook

**Example: Testing A2A agent on Cloud Run:**

```bash
# Get your service URL from deployment output or Cloud Console
SERVICE_URL="https://your-service-url.run.app"

# Send a test message using A2A protocol
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "params": {
      "task_id": "test-task-001",
      "message": {
        "messageId": "msg-001",
        "role": "user",
        "parts": [
          {
            "text": "Your test query here",
            "mimeType": "text/plain"
          }
        ]
      }
    },
    "id": "req-1"
  }' \
  "$SERVICE_URL/a2a/app"

# Get the agent card (describes capabilities)
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$SERVICE_URL/a2a/app/.well-known/agent-card.json"
```

### Running Load Tests

To run load tests against your deployed agent:

```bash
make load-test
```

This uses Locust to simulate multiple concurrent users.

## Adding Evaluation Cases

To improve evaluation coverage:

1. Add cases to `tests/eval/evalsets/basic.evalset.json`
2. Each case should test a capability from DESIGN_SPEC.md
3. Include expected tool calls in `intermediate_data.tool_uses`
4. Run `make eval` to verify

## Advanced: Batch & Event Processing

### When to Use Batch/Event Processing

Your agent currently runs as an interactive service. However, many use cases require processing large volumes of data asynchronously:

**Batch Processing:**
- **BigQuery Remote Functions**: Process millions of rows with Gemini (e.g., `SELECT analyze(customer_data) FROM customers`)
- **Data Pipeline Integration**: Trigger agent analysis from Dataflow, Spark, or other batch systems

**Event-Driven Processing:**
- **Pub/Sub**: React to events in real-time (e.g., order processing, fraud detection)
- **Eventarc**: Trigger on GCP events (e.g., new file in Cloud Storage)
- **Webhooks**: Accept HTTP callbacks from external systems

### Adding an /invoke Endpoint

Add an `/invoke` endpoint to `app/fast_api_app.py` for batch/event processing. The endpoint auto-detects the input format (BigQuery Remote Function, Pub/Sub, Eventarc, or direct HTTP).

**Core pattern:** Create a `run_agent` helper using `Runner` + `InMemorySessionService` for stateless processing, with a semaphore for concurrency control. Then route by request shape:

```python
@app.post("/invoke")
async def invoke(request: Dict[str, Any]):
    if "calls" in request:        # BigQuery: {"calls": [[row1], [row2]]}
        results = await asyncio.gather(*[run_agent(f"Analyze: {row}") for row in request["calls"]])
        return {"replies": results}
    if "message" in request:      # Pub/Sub: {"message": {"data": "base64..."}}
        payload = base64.b64decode(request["message"]["data"]).decode()
        return {"status": "success", "result": await run_agent(payload)}
    if "type" in request:         # Eventarc: {"type": "google.cloud...", "data": {...}}
        return {"status": "success", "result": await run_agent(str(request["data"]))}
    if "input" in request:        # Direct HTTP: {"input": "prompt"}
        return {"status": "success", "result": await run_agent(request["input"])}
```

**Test locally** with `make local-backend`, then curl each format:
```bash
# BigQuery
curl -X POST http://localhost:8000/invoke -H "Content-Type: application/json" \
  -d '{"calls": [["test input 1"], ["test input 2"]]}'
# Direct
curl -X POST http://localhost:8000/invoke -H "Content-Type: application/json" \
  -d '{"input": "your prompt here"}'
```

**Connect to GCP services:**
```bash
# Pub/Sub push subscription
gcloud pubsub subscriptions create my-sub --topic=my-topic \
    --push-endpoint=https://python-agent-adk.run.app/invoke
# Eventarc trigger
gcloud eventarc triggers create my-trigger \
    --destination-run-service=python-agent-adk \
    --destination-run-path=/invoke \
    --event-filters="type=google.cloud.storage.object.v1.finalized"
```

**Production tips:** Use semaphores to limit concurrent Gemini calls (avoid 429s), set Cloud Run `--max-instances`, and return per-row errors instead of failing entire batches. See [reference implementation](https://github.com/richardhe-fundamenta/practical-gcp-examples/blob/main/bq-remote-function-agent/customer-advisor/app/fast_api_app.py) for production patterns.
