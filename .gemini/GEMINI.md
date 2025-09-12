# GEMINI.MD: AI Collaboration Guide

This document provides essential context for AI models interacting with this project. Adhering to these guidelines will ensure consistency and maintain code quality.

## 1. Project Overview & Purpose

* **Primary Goal:** This project is an "IT Bug Assistant Agent" designed to help IT Support and Software Developers triage, manage, and resolve software issues. It provides a web interface for interaction.
* **Business Domain:** IT Support, Software Development, and Issue Tracking.

## 2. Core Technologies & Stack

* **Languages:** Python 3.12
* **Frameworks & Runtimes:** Django, Gunicorn
* **Databases:** PostgreSQL (for production), SQLite (for local development)
* **Key Libraries/Dependencies:** `google-adk`, `google-generativeai`, `django`, `psycopg2-binary`, `whitenoise`
* **Package Manager(s):** `uv`

## 3. Architectural Patterns

* **Overall Architecture:** Monolithic Application using Django's Model-View-Template (MVT) architecture.
* **Directory Structure Philosophy:**
    * `/web_ui`: The main Django project directory containing settings and configurations.
    * `/adk_bug_ticket_agent`: A Django app that contains the core logic for the bug assistant agent.
    * `/mcp-servers`: Contains the MCP Toolbox for database interactions.
    * `/sql`: Holds SQL scripts for database schema and data setup.
    * `/Dockerfile`: Defines the container for the Django application.
    * `/cloudbuild.yaml`: CI/CD configuration for Google Cloud Build.

## 4. Coding Conventions & Style Guide

* **Formatting:** The code follows the PEP 8 style guide for Python. Indentation is 4 spaces.
* **Naming Conventions:**
    * `variables`, `functions`: `snake_case` (`my_variable`)
    * `classes`: `PascalCase` (`MyClass`)
    * `files`: `snake_case` (`views.py`)
* **API Design:** The project exposes a RESTful-like API endpoint at `/agent/interact/` for interacting with the agent, using JSON for request/response bodies.
* **Error Handling:** Uses standard Python `try...except` blocks for error handling in view functions.

## 5. Key Files & Entrypoints

* **Main Entrypoint(s):** `manage.py` for development server, `web_ui/wsgi.py` for production (used by Gunicorn).
* **Configuration:** `web_ui/settings.py` (Django settings), `.env` (for environment variables), `pyproject.toml` (project dependencies).
* **CI/CD Pipeline:** `cloudbuild.yaml` and `cloudbuild-django.yaml` for Google Cloud Build.

## 6. Development & Testing Workflow

* **Local Development Environment:** The `README.md` provides detailed instructions for setting up a local environment using `pyenv`, a Python virtual environment, `uv`, and a local PostgreSQL database. The development server is run with `python manage.py runserver`.
* **Testing:** A `/adk_bug_ticket_agent/tests` directory exists, but contains no tests. New code should ideally be accompanied by corresponding tests.
* **CI/CD Process:** When code is pushed, Google Cloud Build uses `cloudbuild.yaml` to build a Docker image from the `Dockerfile` and push it to Google Artifact Registry.

## 7. Specific Instructions for AI Collaboration

* **Contribution Guidelines:** No formal `CONTRIBUTING.md` was found. Please follow existing patterns in the code.
* **Infrastructure (IaC):** The `README.md` contains `gcloud` commands for setting up cloud infrastructure. Any changes to these commands must be carefully reviewed.
* **Security:** Be mindful of security. Do not hardcode secrets or keys. The project uses `.env` files for secrets, which should not be committed to version control.
* **Dependencies:** To add a new dependency, add it to the `[project.dependencies]` section in `pyproject.toml` and then run `uv sync` to update the environment.
* **Commit Messages:** The commit history does not show a strict convention. It is recommended to write clear, concise, and imperative-style commit messages (e.g., "feat: Add user authentication").
