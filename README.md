# IT Bug Assistant Agent

The Bug Assistant is a sample agent hosted on django designed to help IT Support and Software Developers triage, manage, and resolve software issues. This agent uses ADK Python, PostgreSQL database, Gemini, MCP server, RAG, and Google Search to assist IT in triaging. 

![](mcp-server/images/softmicro-agent.png)

## Agent Flow
IT Support triggers the Bug Assistant Agent

**The agent:**

Queries Gemini 2.5 Flash for AI insights

Uses Google Search Tool for supplemental external context

Connects to MCP Toolbox, which in turn interacts with the Bug Ticket Database

## Key Features

* **Components:**        Tools, Database, RAG, Google Search 
* **MVP:**          Bug Support for IT support reps

*   **MCP Toolbox for Databases:** [MCP Toolbox for Databases](https://github.com/googleapis/genai-toolbox) to provide database-specific tools to our agent.

## Setup and Installation

### Prerequisites 

- [uv](https://docs.astral.sh/uv/getting-started/installation) (to manage dependencies)
- Python 3.10+

Install the python 3.12 locally and confirm it as the default:
```shell
pyenv install 3.12.4
pyenv global 3.12.4
python3 -m venv .venv #check notification in vscode and click click yes
```

### Installation

1. Clone the repository:

```bash
git clone git@github.com:ypenn21/adk-agents.git
cd adk-agents
```

2. Configure environment variables (via `.env.example` file):

There are two different ways to call Gemini models:

- Calling Gemini models through Vertex AI APIs on Google Cloud.
- Calling the Gemini API directly using an API key created via Google AI Studio.

<details open>
<summary>Gemini API Key</summary> 

Get an API Key from Google AI Studio: https://aistudio.google.com/apikey

Create a `.env` file by running the following (replace `<your_api_key_here>` with your API key):

```sh
echo "GOOGLE_GENAI_USE_VERTEXAI=FALSE" >> .env \
&& echo "GOOGLE_API_KEY=<your_api_key_here>" >> .env
```

</details>

<details>
<summary>Vertex AI</summary>

To use Vertex AI, you will need to [create a Google Cloud project](https://developers.google.com/workspace/guides/create-project) , [enable Vertex AI](https://cloud.google.com/vertex-ai/docs/start/cloud-environment), and `gcloud` CLI ([Installation instructions](https://cloud.google.com/sdk/docs/install))


Authenticate and enable Vertex AI API:

```bash
gcloud auth login
# Replace <your_project_id> with your project ID
gcloud config set project <your_project_id>
gcloud services enable aiplatform.googleapis.com
```

Create a `.env` file by running the following (replace `<your_project_id>` with your project ID):
```sh
echo "GOOGLE_GENAI_USE_VERTEXAI=TRUE" >> .env \
&& echo "GOOGLE_CLOUD_PROJECT=<your_project_id>" >> .env \
&& echo "GOOGLE_CLOUD_LOCATION=us-central1" >> .env
```

> Deploying to Cloud Run use Vertex AI instead.
</details>


There is an example `.env` file located at [.env.example](.env.example) if you would like to
verify your `.env` was set up correctly.

Source the `.env` file into your environment:

```bash
set -o allexport && source .env && set +o allexport
```

3. Download [MCP Toolbox for Databases](https://github.com/googleapis/genai-toolbox)

```bash
export OS="linux/amd64" # one of linux/amd64, darwin/arm64, darwin/amd64, or windows/amd64
curl -O --output-dir mcp-server/mcp-toolbox https://storage.googleapis.com/genai-toolbox/v0.6.0/$OS/toolbox
chmod +x mcp-server/mcp-toolbox/toolbox
```

## Deploy to GCP 

These instructions walk through the process of deploying the Software Bug Assistant agent to Google Cloud, including Cloud Run and Cloud SQL (PostgreSQL). This setup also adds RAG capabilities to the tickets database, using the [google_ml_integration](https://cloud.google.com/blog/products/ai-machine-learning/google-ml-intergration-extension-for-cloud-sql) vector plugin for Cloud SQL, and the `text-embeddings-005` model from Vertex AI.

![](mcp-server/images/adk-cloud-architecture.png)

*Note you can use Vertexai or AI Studio api key

### Presetup 

- `gcloud` CLI ([Installation instructions](https://cloud.google.com/sdk/docs/install))
- A Google Cloud project

### 1 - Authenticate the Google Cloud CLI, and enable Google Cloud APIs. 

```
gcloud auth login
gcloud auth application-default login 

export PROJECT_ID="<YOUR_PROJECT_ID>"
gcloud config set project $PROJECT_ID

gcloud services enable sqladmin.googleapis.com \
   compute.googleapis.com \
   cloudresourcemanager.googleapis.com \
   servicenetworking.googleapis.com \
   aiplatform.googleapis.com
```

### 2 - Create a Cloud SQL (Postgres) instance. 

```bash
gcloud sql instances create adk \
--database-version=POSTGRES_16 \
--tier=db-custom-1-3840 \
--region=us-central1 \
--edition=ENTERPRISE \
--enable-google-ml-integration \
--database-flags cloudsql.enable_google_ml_integration=on \
--root-password=admin
```

### 3 - Create a SQL database, and grant Cloud SQL service account access to Vertex AI. 

This step is necessary for creating vector embeddings (Agent RAG search).

```bash 
gcloud sql databases create tickets-db --instance=adk

SERVICE_ACCOUNT_EMAIL=$(gcloud sql instances describe adk --format="value(serviceAccountEmailAddress)")
echo $SERVICE_ACCOUNT_EMAIL

gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role="roles/aiplatform.user"
```

### 4 - Set up the db table. 

From the Cloud Console (Cloud SQL), open **Cloud SQL Studio**. 

Log into the `tickets-db` database using the `postgres` user (password: `admin`, but note you can change to a more secure password under Cloud SQL > Primary Instance > Users).


Open a new **Editor** tab. Then, paste in the SQL code from [`sql/data.sql`](sql/data.sql) to set up the table and create vector embeddings.

### 5 - Load in sample data. 

Run the SQL code from [`sql/data.sql`](sql/data.sql) to load in sample data.

```

### 6 - Create a trigger to update the `updated_time` field when a record is updated.

```SQL
CREATE OR REPLACE FUNCTION update_updated_time_tickets()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_time = NOW();  -- Set the updated_time to the current timestamp
    RETURN NEW;                -- Return the new row
END;
$$ language 'plpgsql';        

CREATE TRIGGER update_tickets_updated_time
BEFORE UPDATE ON tickets
FOR EACH ROW                  -- This means the trigger fires for each row affected by the UPDATE statement
EXECUTE PROCEDURE update_updated_time_tickets();
```


### 7 - Create vector embeddings from the `description` field.

```SQL
ALTER TABLE tickets ADD COLUMN embedding vector(768) GENERATED ALWAYS AS (embedding('text-embedding-005',description)) STORED;
```

**Retrieval-Augmented Generation (RAG):** Leverages Cloud SQL's built-in [Vertex AI ML Integration](https://cloud.google.com/sql/docs/postgres/integrate-cloud-sql-with-vertex-ai) to fetch relevant/duplicate software bugs.

### 8 - Verify that the database is ready.

From Cloud SQL studio, run:

```SQL
SELECT * FROM tickets;
```


### 9 - Deploy the MCP Toolbox for Databases server to Cloud Run 

Now that we have a Cloud SQL database, we can deploy the MCP Toolbox for Databases server to Cloud Run and point it at our Cloud SQL instance.

First, update `mcp-server/mcp-toolbox/tools.yaml` for your Cloud SQL instance: 

```yaml
  postgresql:
    kind: cloud-sql-postgres
    project: ${PROJECT_ID}
    region: us-central1
    instance: software-assistant
    database: tickets-db
    user: ${DB_USER}
    password: ${DB_PASS}
```

Then, configure Toolbox's Cloud Run service account to access both Secret Manager and Cloud SQL. Secret Manager is where we'll store our `tools.yaml` file because it contains sensitive Cloud SQL credentials. 

Note - run this from the top-level `adk_bug_ticket_agent/` directory. 

```bash 
gcloud services enable run.googleapis.com \
   cloudbuild.googleapis.com \
   artifactregistry.googleapis.com \
   iam.googleapis.com \
   secretmanager.googleapis.com
                       
gcloud iam service-accounts create toolbox-identity

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member serviceAccount:toolbox-identity@$PROJECT_ID.iam.gserviceaccount.com \
    --role roles/secretmanager.secretAccessor

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member serviceAccount:toolbox-identity@$PROJECT_ID.iam.gserviceaccount.com \
    --role roles/cloudsql.client

gcloud secrets create tools --data-file=mcp-server/mcp-toolbox/tools.yaml
```

Now we can deploy Toolbox to Cloud Run. We'll use the latest [release version](https://github.com/googleapis/genai-toolbox/releases) of the MCP Toolbox image (we don't need to build or deploy the `toolbox` from source.)

```bash
gcloud run deploy toolbox \
    --image us-central1-docker.pkg.dev/database-toolbox/toolbox/toolbox:latest \
    --service-account toolbox-identity \
    --region us-central1 \
    --set-secrets "/app/tools.yaml=tools:latest" \
    --set-env-vars="PROJECT_ID=$PROJECT_ID,DB_USER=postgres,DB_PASS=admin" \
    --args="--tools-file=/app/tools.yaml","--address=0.0.0.0","--port=8080" \
    --allow-unauthenticated
```

Verify that the Toolbox is running by getting the Cloud Run logs: 

```bash 
gcloud run services logs read toolbox --region us-central1
```

Save the Cloud Run URL for the Toolbox service as an environment variable.

```bash
export MCP_TOOLBOX_URL=$(gcloud run services describe toolbox --region us-central1 --format "value(status.url)")
```

Now we are ready to deploy the ADK Python agent to Cloud Run! :rocket:

### 10 - Create an Artifact Registry repository.

This is where we'll store the agent container image.

```bash
gcloud artifacts repositories create adk \
  --repository-format=docker \
  --location=us-central1 \
  --description="Repository for ADK Python sample agents" \
  --project=$PROJECT_ID
```

### 11 - Containerize the ADK Python agent. 

Build the container image and push it to Artifact Registry with Cloud Build.

```bash
gcloud builds submit --region=us-central1 --tag us-central1-docker.pkg.dev/$PROJECT_ID/adk/adk-agent-bug-assist:latest
```

### 12 - Create Rag Engine Corpus in Vertexai

Navigate to the Rag Engine in Vertexai and create a new corpus called user-chat-history
![](mcp-server/images/vertexai-rag.png)

Once its done. Click on the corpus and click on details to get the Resource name to use in your python adk app. 
```bash
# set using Resource name
export RAG_CORPUS="projects/project-id/locations/region/ragCorpora/rag-corpus-id"
```

### 13 - Cloud Run Connectivity to Cloud Sql


> [!NOTE]    
> 
> Create VPC Network Peering connection between your VPC and Google's service producer VPC (assuming you have a [vpc called default if not create one](https://cloud.google.com/vpc/docs/create-modify-vpc-networks#gcloud)
).
> 
```bash
gcloud compute networks create default \
    --subnet-mode=auto \
    --bgp-routing-mode=DYNAMIC_ROUTING_MODE \
    --mtu=MTU
```

Navigate to the Cloud Sql instance called adk, and create the private ip, and connect to the VPC. This is the same vpc you need enable direct vpc-egress on Cloud Run deployment.
![](mcp-server/images/cloud-sql-instance.png)

*Note you can also connect to Cloud Sql with [PSC connectivity](https://cloud.google.com/sql/docs/mysql/configure-private-service-connect), but for simplicity sake we will go with peering.

### 14 - Deploy the agent to Cloud Run 

You need enable direct vpc-egress on Cloud Run deployment to connect to the Cloud Sql. Network is the same one with the private ip connection to Cloud Sql. Subnet can be any on the network.

```bash
export MCP_TOOLBOX_URL=$(gcloud run services describe toolbox --region us-central1 --format "value(status.url)")
export PROJECT_ID="project-id"
# set using Resource name
export RAG_CORPUS="projects/project-id/locations/region/ragCorpora/rag-corpus-id"
export DB_URL="postgresql://postgres:pword@internal-ip-address:5432/tickets-db"

gcloud run deploy adk-agent-bug-assist \
  --image=us-central1-docker.pkg.dev/$PROJECT_ID/adk/adk-agent-bug-assist:latest \
  --region=us-central1 \
  --allow-unauthenticated \
  --cpu=4 \
  --memory=2Gi \
  --network=default \
  --subnet=default \
  --vpc-egress=private-ranges-only \
  --set-env-vars=RAG_CORPUS=$RAG_CORPUS,DB_URL=$DB_URL,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=us-central1,GOOGLE_GENAI_USE_VERTEXAI=TRUE,MCP_TOOLBOX_URL=$MCP_TOOLBOX_URL
```

Check log to see that this deployment is successfully.


### 15 - Test the Cloud Run Agent

Open the Cloud Run Service URL outputted by the previous step. 

You should see the Web UI for the Software Bug Assistant. At https://cloud-run-host.com/agent/interact/

Test the agent by asking questions like: 
- `Any issues around database timeouts?` 
- `How many bugs are assigned to samuel.green@example.com? Show a table.` 
- `What are some possible root-causes for the unresponsive login page issue?` (Invoke Google Search tool)
- `Get the bug ID for the unresponsive login page issues` --> `Boost that bug's priority to P0.`. 
- `Create a new bug.` (let the agent guide you through bug creation)


## Local Environment 

### Presetup

Install PostgreSQL:

- [PostgreSQL - local instance and psql command-line tool](https://www.postgresql.org/download/)


### 1 - Start a local Pgsql

For instance, on MacOS: 

```bash
brew services start postgresql
```

### 2 - Setup the database

```bash
psql -U postgres
```

Then, initialize the database and `tickets` table by running the queries in [`sql/data.sql`](sql/data.sql).

*note you don't need to create the extension for local environment. Only create the table and insert the records.

```sql
CREATE EXTENSION IF NOT EXISTS google_ml_integration CASCADE;
CREATE EXTENSION IF NOT EXISTS vector CASCADE;
GRANT EXECUTE ON FUNCTION embedding TO postgres;
```

### 3 - Run the MCP Toolbox

[MCP Toolbox for Databases](https://googleapis.github.io/genai-toolbox) is an open-source [Model Context Protocol (MCP)](https://modelcontextprotocol.io/introduction) server for databases including PostgreSQL. It allows you to define "tools" against your database, with matching SQL queries, effectively enabling agent "function-calling" for your database. 

First, [download the MCP toolbox](https://googleapis.github.io/genai-toolbox/getting-started/local_quickstart/) binary if not already installed.

Then, open the `mcp-server/mcp-toolbox/tools.yaml` file. This is a prebuilt configuration for the MCP Toolbox that defines several SQL tools against the `tickets` table we just created, including getting a ticket by its ID, creating a new ticket, or searching tickets. 

> [!Note]
> Vector search via `search-tickets` is not yet enabled for local development - see Google Cloud setup below.

**Important:** Update the first lines of `tools.yaml` to point to your local Postgres instance, for example: 

```yaml
  postgresql:
    kind: postgres
    host: localhost
    port: 5432
    database: tickets-db
    user: ${DB_USER}
    password: ${DB_PASS}
```

Now you run the toolbox server locally: 

```bash 
cd mcp-server/mcp-toolbox/
./toolbox --tools-file="tools.yaml"
```

You can verify the server is running by opening http://localhost:5000/api/toolset in your browser. 
You should see a JSON response with the list of tools specified in `tools.yaml`. 

```json
{
}
```
---------

### 3. Run Python Django:

```bash
rm uv.lock
uv sync
python manage.py runserver 
gunicorn web_ui.wsgi:application
#try the ui: http://127.0.0.1:8000/agent/interact/
```

Here are some example requests you may ask the agent:
- "Show me all the tickets with status Open"
- "List the tickets with highest priority"
- "Can you bump the priority of ticket ID 7 to P0?"
- "What are some possible root-causes for the unresponsive login page issue? (Invoke Google Search tool)"
- "Which issues are currenlty marked as 'In Progress'?"
- "What bugs are assigned to robert.jones@example.com?"
