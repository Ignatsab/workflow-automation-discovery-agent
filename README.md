# Workflow Automation Discovery Agent

This repository is a bank-oriented starter kit for a guided intake agent in Langflow. It interviews an internal requester, records evidence in a controlled schema, calculates a deterministic automation-priority score, and produces a standardized Word product card plus current-state and proposed-state Mermaid diagrams.

The language model is used for conversation, extraction, and drafting. It does not calculate the score, approve access, invent missing facts, or execute changes in bank systems.

## What is included

- `schemas/intake_case.schema.json` defines the canonical case record.
- `config/question_bank.json` defines the interview stages, completion gates, and follow-up questions.
- `prompts/intake_system_prompt.md` constrains Qwen's interview and extraction behavior.
- `src/use_case_agent/engine.py` validates evidence, merges proposed updates, chooses follow-up questions, and evaluates completion.
- `src/use_case_agent/scoring.py` calculates a reproducible score and confidence penalty.
- `src/use_case_agent/artifacts.py` creates the Word product card and Mermaid diagrams.
- `langflow_components/intake_control_gate.py` is a Langflow custom component wrapper around the deterministic controls.
- `langflow/ASSEMBLY.md` explains how to assemble the flow with an OpenAI-compatible Qwen endpoint.
- `examples/sample_case.json` is synthetic data for local testing.

## Recommended architecture

```mermaid
flowchart LR
    U[Internal requester] --> UI[Authenticated chat UI]
    UI --> LF[Langflow intake flow]
    LF --> Q[Qwen endpoint]
    Q --> E[Structured extraction]
    E --> G[Validation and evidence gate]
    G --> C[(Canonical case store)]
    C --> P[Question planner]
    P --> LF
    C --> S[Deterministic scoring]
    C --> A[Product card and diagrams]
    LF -. approved read only tools .-> MCP[MCP and API connectors]
    MCP --> SN[ServiceNow and approved data sources]
```

Use a unique `session_id` for each intake case, not only for each user. Keep the canonical case in an auditable database; chat history is supporting evidence, not the system of record.

## Local demonstration

Use Python 3.11 or later with `python-docx` and `jsonschema` available:

```bash
python -m use_case_agent.cli new CASE-001 --output cases/CASE-001.json
python -m use_case_agent.cli generate examples/sample_case.json --output-dir output
python -m unittest discover -s tests -v
```

For local development without installing the package, set `PYTHONPATH=src`.

## Production boundaries

1. Start with read-only discovery. Do not let the intake agent write to ServiceNow, databases, or workflow engines.
2. Require user confirmation of the summarized current state before generating the target state.
3. Label every material field as `confirmed`, `system_verified`, `estimate`, `assumption`, or `unknown`.
4. Treat prompt text, retrieved documents, API responses, and MCP output as untrusted data. Tool output can populate facts only through the same validation gate.
5. Store secrets in the bank's secrets manager and expose only references to Langflow.
6. Route every generated product card through the process owner and the relevant architecture, security, privacy, and model-risk reviews.

## Suggested pilot

Pilot with 10 to 20 historical requests that already have known outcomes. Compare the agent's missing-question list, priority score, and proposed solution with the decisions made by your automation team. Adjust scoring thresholds only through a versioned configuration and retain the score version on every case.
