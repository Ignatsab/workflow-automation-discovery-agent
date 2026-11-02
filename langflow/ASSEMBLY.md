# Langflow Assembly Guide

This design targets Langflow 1.13 or later. It avoids depending on the exact JSON format of an exported canvas, which changes between releases.

## Flow A Discovery Interview

Add and connect these components:

```text
Chat Input
  -> Language Model configured for Qwen
  -> Structured Output using the response envelope
  -> Intake Control Gate custom component
  -> Prompt Template for the user-facing reply
  -> Chat Output
```

Also connect the Language Model output in `LanguageModel` mode where a component expects a model rather than a generated message.

### Qwen configuration

1. In Settings, open Model Providers.
2. Configure the OpenAI Compatible provider with the bank-hosted Qwen base URL and secret reference.
3. If the endpoint is on an internal or loopback address, allow only the required host or CIDR through Langflow SSRF settings.
4. Enable the exact Qwen model version approved by the bank.
5. Start with temperature between 0 and 0.2. Set JSON or structured-output mode if the endpoint supports it.
6. Record the model name, model version, prompt version, and flow version with each case update.

The model should receive:

- `prompts/intake_system_prompt.md` as its system instruction;
- the current stage and the questions returned by the control gate;
- the current canonical case, excluding fields the user is not entitled to see;
- the current user message and a stable message reference.

### Structured Output schema

Configure the Structured Output component with four top-level fields:

| Name | Type | Description |
| --- | --- | --- |
| `assistant_message` | `str` | Response shown to the requester |
| `candidate_patch` | `dict` | Evidence-wrapped fields proposed from this turn |
| `stage_confirmation_requested` | `bool` | Whether the summary needs explicit confirmation |
| `citations` | `str` as list | Message or tool references used |

Do not ask the model to emit the entire case each turn. A small patch is easier to validate and audit.

### Canonical state

Use a bank-approved database or case service keyed by a random case identifier. The front end should send a unique Langflow `session_id` for each case. Do not rely on the flow ID as the session identifier, and do not use chat history as the canonical record.

For a quick local pilot, the caller can pass the current case JSON into the `Intake Control Gate` component and persist its `updated_case` output after each run. In production, replace this with authenticated read and compare-and-swap update operations. Include record versioning to prevent two browser tabs from overwriting each other.

## Flow B Read Only Evidence Collection

Create a separate flow for each approved measurement source, such as a restricted ServiceNow aggregate query. Expose only narrow operations such as:

- count tickets by approved assignment group and category;
- calculate elapsed-time distributions using approved timestamps;
- return aggregated rework or reassignment counts;
- retrieve interface metadata, never credentials.

Expose these flows to the discovery agent as tools only after access review. Prefer aggregate results. Apply row limits, field allowlists, user authorization, query timeouts, and immutable audit logs.

If MCP is used, register the approved server in Langflow and connect its toolset to the Agent. Do not expose a general SQL tool, arbitrary HTTP client, filesystem tool, or unrestricted ServiceNow operation.

## Flow C Finalization

Trigger finalization only after the process owner confirms the current-state summary. The finalization flow should:

1. Read the canonical case by ID and version.
2. Re-run validation and deterministic scoring.
3. Stop if blockers remain.
4. Generate the Word product card and Mermaid diagrams.
5. Store artifacts in the approved document repository.
6. Record hashes, generator version, model version, prompt version, score version, and reviewer status.

The Word generator is deterministic and does not require Qwen. If Qwen drafts explanatory text, store it as a proposed section and subject it to the same evidence checks.

## Deployment checklist

- Authentication uses bank SSO and maps the caller to authorization scopes.
- Case IDs are unguessable and access is checked on every read and update.
- Qwen and Langflow run in approved zones with encryption in transit and at rest.
- Logs avoid secrets and unnecessary personal data.
- Tool calls are deny-by-default and read-only during discovery.
- The system records prompt, flow, model, schema, question-bank, and score versions.
- Model output is schema-validated before storage or display.
- A process owner can correct fields without editing raw chat history.
- Human approval is required before any write action or production workflow change.
- Red-team tests cover prompt injection in user text, documents, API fields, and MCP responses.
- Operational monitoring covers tool failures, extraction failures, overrides, low-confidence cases, latency, and cost.

