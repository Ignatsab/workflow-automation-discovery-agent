# Importing the Langflow flow

The supplied flow deliberately keeps Langflow thin. Langflow handles Chat Input and Chat Output; the API Request calls the separately deployed LangGraph service. Qwen, state, validation, scoring, and question planning are therefore versioned Python code and behave the same even if your bank's Langflow build differs.

## Import and configure

1. Deploy the LangGraph API using the container and Kubernetes examples in `deploy/kubernetes/`.
2. In Langflow, choose **New Flow**, then **Import**, and select `workflow_automation_discovery_langgraph.json`.
3. Open **API Request** and replace its URL with the service address reachable from the Langflow pod, normally `http://workflow-intake-agent:8080/langflow/chat` in the same namespace.
4. Replace `REPLACE_WITH_AGENT_API_KEY` in the `x-api-key` header. Prefer your platform's secret-variable substitution if the bank build supports it; do not save a production secret in exported JSON.
5. Save the flow and open the Playground. Langflow supplies a session ID, which becomes the LangGraph thread/case ID.

The flow wiring is:

```text
Chat Input -> Message to Data -> API Request -> Parser ({result}) -> Chat Output
```

It was exported in the Langflow 1.8 JSON format and uses only bundled nodes. It does not require the repository's optional `langflow_components/` code.

## Compatibility with a custom bank build

`Message to Data` is a bundled legacy node in newer Langflow versions. Some installations show it as **Type Converter**, and some may remove the legacy alias. If the imported node is red or missing:

1. Delete only **Message to Data**.
2. Add the bundled **Type Converter**.
3. Connect Chat Input's `Message` output to Type Converter.
4. Select `Data`/`JSON` as the target type and connect it to API Request's `Body` input.

If API Request or Parser is unavailable, ask the platform team which equivalent HTTP POST and JSON-field extraction components are approved. No external component is technically required. If the import itself is rejected, export any simple two-node flow from your installation and use it to align the JSON envelope with that exact version.

## Network and security requirements

- The Langflow pod needs egress only to the agent Service; the agent needs egress only to Qwen and PostgreSQL.
- Use workload identity, a service mesh, or a Kubernetes Secret for the API key; never commit the real value.
- Keep PostgreSQL checkpoints encrypted, access-controlled, and retained according to bank policy.
- Use a unique Langflow session ID per intake case. Do not use one employee-wide session for every request.
- The `/langflow/chat` endpoint returns only display text. The canonical record remains in LangGraph checkpoints and is available through the authenticated `/v1/cases/{thread_id}` endpoint.

## Quick connectivity check

From a network location that can reach the agent:

```bash
curl -sS http://workflow-intake-agent:8080/health
```

The expected body is `{"status":"ok"}`. A 401 from `/langflow/chat` means the `x-api-key` values differ; a 422 normally means the Chat Input session ID was empty.
