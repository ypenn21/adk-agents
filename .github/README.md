# Security-First CI/CD with Gemini & Workload Identity Federation

## Overview
This project provides a robust, AI-powered security and compliance pipeline integrated directly into GitHub Actions. It leverages the **Gemini CLI** for intelligent code analysis and **Google Cloud Workload Identity Federation (WIF)** for secure, keyless authentication to GCP. The pipeline automatically scans every pull request and commit for security vulnerabilities, PII (Personally Identifiable Information) leaks, and dependency risks before allowing code to be deployed.

## Problems It Solves
*   **Static Analysis Limitations:** Traditional linting often misses complex logic flaws. This pipeline uses Gemini's GenAI capabilities to perform deep, contextual security reviews.
*   **Credential Sprawl:** Eliminates the need for long-lived Service Account JSON keys by using OIDC tokens, significantly reducing the risk of credential theft.
*   **Accidental Data Exposure:** Automates the detection of PII (emails, phone numbers, locations) using Google Cloud DLP, preventing sensitive data from reaching production logs or databases.
*   **Manual Review Bottlenecks:** Provides automated PR reviews and quality gate decisions, allowing security teams to focus on high-impact strategic work rather than repetitive checks.

## Why Use It?
*   **Automated Quality Gates:** Enforces strict security standards (Zero "High" severity issues) automatically.
*   **Auditability:** Every scan generates detailed reports that are archived in Google Cloud Storage for compliance and post-mortem analysis.
*   **Seamless Integration:** Designed to work out-of-the-box with GitHub Actions and Google Cloud Run.
*   **AI-Driven Insights:** Goes beyond pattern matching to understand the *intent* and *impact* of code changes.

## Target Audience
*   **Security Engineers:** Looking to automate "shift-left" security practices and scale their impact.
*   **DevOps/SRE Teams:** Aiming to build secure, keyless deployment pipelines with built-in quality gates.
*   **Compliance Officers:** Needing automated evidence collection and consistent enforcement of data privacy rules.
*   **Software Developers:** Wanting immediate, actionable feedback on security and PII risks within their PRs.

## Security PII and Code Review Pipeline

```mermaid
flowchart TD
    Trigger([Push to main / PR Opened]) --> Job1[Job: scan-and-evaluate]
    
    subgraph Job1 [Job: scan-and-evaluate]
        direction TB
        S1[Checkout & GCP Auth] --> S2[Setup Gemini CLI & Extensions]
        S2 --> SS1[Gemini Security Scan]
        SS1 --> SS2[Gemini Dependency Scan]
        SS2 --> SS3[Gemini PR Review - if PR]
        SS3 --> SS4[GCP DLP PII Scan]
        SS4 --> S4[Quality Gate Decision - Release Engineer Agent]
        S4 --> S5[Collect Telemetry & Upload to GCS]
        S5 --> S6{Gate Result?}
        S6 -- FAILED --> S7([Exit 1])
        S6 -- PASSED --> S8([Job Success])
    end
    
    Job1 -->|On PASSED & Branch is main| Job2[Job: build]
    
    subgraph Job2 [Job: build]
        direction TB
        B1[Checkout & GCP Auth] --> B2[Submit Cloud Build]
    end
```

## OIDC Auth To GCP

```mermaid
graph TD
    A["GitHub Repository"] -->|Triggers| B["GitHub Actions Workflow"]
    B -->|Requests Token| C["GitHub Token Service"]
    C -->|Issues OIDC Token| B
    B -->|Exchanges Token| D["Cloud Provider<br/>OIDC Endpoint"]
    D -->|Validates & Returns<br/>Access Token| E["Cloud Provider<br/>Credentials"]
    E -->|Authorizes| F["Cloud Services<br/>AWS/GCP/Azure"]
    F -->|Executes Actions| G["Deployment/Infrastructure"]
```
