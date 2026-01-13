# Technology Stack

This document outlines the core technologies and libraries used in the Bug Assistant project.

## Core Language & Frameworks
- **Python (>=3.10):** The primary programming language.
- **Django (>=5.0, <5.3):** The web framework for the application and agent interface.
- **Google Agent Development Kit (ADK) (v1.17.0):** The core framework for building and managing the agent.

## AI & Machine Learning
- **Gemini 2.5 Flash:** The primary LLM used for natural language understanding and task execution.
- **Vertex AI (text-embeddings-005):** Used for generating vector embeddings to support RAG functionality.
- **RAG (Retrieval-Augmented Generation):** Integrated via Cloud SQL's vector support to identify similar or duplicate bug tickets.

## Database & Storage
- **PostgreSQL (Cloud SQL):** The primary relational database for storing bug tickets and metadata.
- **MCP Toolbox for Databases:** An external server used to provide the agent with tools for interacting with the PostgreSQL database.

## Deployment & Infrastructure
- **Google Cloud Run:** The platform for hosting the containerized Django application and the MCP Toolbox.
- **Cloud Build:** Used for the CI/CD pipeline and containerizing the application.
- **Artifact Registry:** Stores the Docker images for deployment.

## Key Python Libraries
- `google-adk`: Core agent logic.
- `google-generativeai`: Interaction with the Gemini API.
- `psycopg2-binary`: PostgreSQL adapter for Python.
- `toolbox-core`: Core library for MCP toolbox integration.
- `gunicorn`: WSGI HTTP Server for production.
- `whitenoise`: Efficient static file serving for Django.
