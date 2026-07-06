# AI Collaboration Guide

This document provides essential context for AI models interacting with this project. Adhering to these guidelines will ensure consistency and maintain code quality.

## 1. Project Overview & Purpose

*   **Primary Goal:** This project is a Django-based web service that hosts an "IT Bug Assistant Agent". The agent is designed to help IT support and software developers triage, manage, and resolve software issues. It uses the Google Agent Development Kit (ADK) to interact with a Gemini model, leveraging tools like RAG (Retrieval-Augmented Generation) with a PostgreSQL database and Google Search to provide intelligent assistance.
*   **Business Domain:** IT Service Management (ITSM) and Software Development Support.

## 2. Getting Started

To get the project up and running locally, follow these steps:

1.  **Set up a Python virtual environment:** This project uses `uv`, so you can create a virtual environment using `python -m venv .venv` and activate it with `source .venv/bin/activate`.
2.  **Install dependencies:** Install all the required dependencies using `uv sync`.
3.  **Set up the database:** This project uses PostgreSQL. Make sure you have a local PostgreSQL instance running, and then run the scripts in `/sql/data.sql` to set up the database schema and initial data.
4.  **Configure environment variables:** Create a `.env` file in the root of the project (you can copy `.env.example` to get started) and fill in the required environment variables, such as your database connection string and Google API key.
5.  **Run the MCP Toolbox server:** The MCP Toolbox server is used for agent-database interaction. Run it locally using the instructions in the `mcp-servers/mcp-toolbox/README.md` file.
6.  **Start the Django development server:** Run `python manage.py runserver` to start the Django development server.

## 3. Core Technologies & Stack

*   **Languages:** Python 3.10+ (as specified in `pyproject.toml` and `Dockerfile`).
*   **Frameworks & Runtimes:**
    *   **Web Framework:** Django (>=5.0, <5.3)
    *   **Agent Framework:** Google Agent Development Kit (ADK) (v1.9.0)
    *   **Application Server:** Gunicorn
    *   **Containerization:** Docker
*   **Databases:**
    *   **Primary:** PostgreSQL (Cloud SQL for production, local instance for development).
    *   **Development Fallback:** SQLite (default Django configuration in `settings.py`).
*   **Key Libraries/Dependencies:**
    *   `google-adk`: Core agent development framework.
    *   `google-generativeai`: For interacting with Gemini models.
    *   `psycopg2-binary`: PostgreSQL adapter for Python.
    *   `whitenoise`: For serving static files efficiently.
    *   `python-dotenv`: For managing environment variables.
*   **Package Manager(s):** `uv` (as seen in `uv.lock` and `Dockerfile`). Dependency definitions are in `pyproject.toml`.

## 4. Architectural Patterns

*   **Overall Architecture:** Monolithic Application. The project consists of a single Django application that serves both the web UI and the agent interaction endpoint. It follows Django's Model-View-Template (MVT) pattern.
*   **Directory Structure Philosophy:**
    *   `/web_ui`: The main Django project directory containing global settings (`settings.py`) and root URL configuration (`urls.py`).
    *   `/adk_bug_ticket_agent`: A self-contained Django app that holds the primary application logic.
        *   `views.py`: Contains the request handling logic, including the main `interact_with_agent` endpoint.
        *   `agent.py`: Defines the ADK agent, its model (`gemini-2.5-flash`), and its tools.
        *   `tools/`: Defines the tools available to the agent (e.g., database interactions).
        *   `templates/`: Contains the HTML template for the web UI.
    *   `/sql`: Contains SQL scripts for database schema setup and data insertion.
    *   `/mcp-servers`: Contains configuration and binaries for the Model Context Protocol (MCP) Toolbox, used for agent-database interaction.
    *   `/plans`: Contains implementation plans for new features.

## 5. Coding Conventions & Style Guide

*   **Formatting:** While no explicit linter configuration (e.g., `.flake8`, `.pylintrc`) is present, the code generally follows the PEP 8 style guide for Python.
*   **Naming Conventions:**
    *   `variables`, `functions`: snake_case (`interact_with_agent`).
    *   `classes`: PascalCase (e.g., `Runner` from ADK).
    *   `files`: snake_case (`views.py`).
*   **API Design:** The primary endpoint `/agent/interact/` is a RESTful-style endpoint that accepts POST requests with a JSON payload for agent interaction and GET requests to serve the HTML interface.
*   **Error Handling:** The main view `interact_with_agent` in `views.py` uses a `try...except` block to catch and log exceptions, returning a JSON response with a 500 status code on error.

## 6. Key Files & Entrypoints

*   **Main Entrypoint(s):**
    *   `manage.py`: Standard Django command-line utility for development tasks (e.g., `runserver`).
    *   `web_ui/wsgi.py`: The WSGI entrypoint for Gunicorn in production.
*   **Configuration:**
    *   `.env`: (Not committed) For storing environment variables like API keys and database URLs. An example is provided in `.env.example`.
    *   `web_ui/settings.py`: Main Django project settings.
    *   `gunicorn.conf.py`: Configuration for the Gunicorn server.
    *   `mcp-servers/mcp-toolbox/tools.yaml`: Defines the database tools for the MCP Toolbox server.

## 7. Testing

*   **Current Status:** There is no dedicated `/tests` directory or testing framework specified in the dependencies. Testing appears to be done manually by interacting with the local or deployed service.
*   **Recommendation:** To improve the quality and reliability of the codebase, it is highly recommended to add automated tests. `pytest` is a good choice for a testing framework, and it integrates well with Django.

## 8. Deployment

*   **CI/CD Process:** When `gcloud builds submit` is run, Google Cloud Build uses `cloudbuild.yaml` or `cloudbuild-django.yaml` to build a Docker image from the corresponding `Dockerfile` and pushes it to Google Artifact Registry. The application is then deployed to Cloud Run.
*   **Deployment Target:** The application is deployed to Google Cloud Run.

## 9. Specific Instructions for AI Collaboration

*   **Contribution Guidelines:** No `CONTRIBUTING.md` file exists. Follow existing patterns:
    *   Place new Django views in `adk_bug_ticket_agent/views.py`.
    *   Register new URL patterns in `adk_bug_ticket_agent/urls.py`.
    *   Define new agent tools in `adk_bug_ticket_agent/tools/tools.py` and register them in `adk_bug_ticket_agent/agent.py`.
*   **Infrastructure (IaC):** The project does not use declarative IaC tools like Terraform. Deployment is managed through a series of `gcloud` CLI commands documented in `README.md`. Be cautious when suggesting changes to these commands.
*   **Security:** The `SECRET_KEY` in `settings.py` is hardcoded and exposed. For production, this should be loaded from a secure source like Secret Manager. The `@csrf_exempt` decorator is used on the main view; ensure any new POST endpoints are also properly secured.
*   **Dependencies:** To add a new Python dependency, add it to the `[project]` section of `pyproject.toml` and then run `uv sync` to update the `uv.lock` file and the virtual environment.
*   **Commit Messages:** No formal commit message convention is apparent from the context. It is recommended to adopt a standard like Conventional Commits (e.g., `feat:`, `fix:`, `docs:`) for future work.

## 10. Multi-Agent Development Workflow (Spec-Driven SDLC)

This project strictly follows a **Spec-Driven Software Development Life Cycle (SDLC)** using a Master Orchestrator (root agent) and specialized Technical Architect and Software Engineer subagents.

To ensure strict adherence to development and routing rules, all guidelines, role definitions, and proxy delegation instructions have been moved to a dedicated rule file:

👉 **Multi-Agent Development Workflow Rules**

Please read and follow the instructions in that file whenever designing, chunking, implementing, or testing new features.
