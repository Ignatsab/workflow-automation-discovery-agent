# Kubernetes deployment

Build the container in your internal CI and replace `registry.example.bank` and the Qwen service URL in the manifests.

1. Create the secret through your approved secret manager. `secret.example.yaml` is a key-name reference only; do not commit real credentials.
2. Run `checkpoint-migration-job.yaml` once for each new database before starting or upgrading the deployment.
3. Apply `agent.yaml` in a namespace reachable from Langflow.
4. Set the API Request URL in the imported Langflow flow to `http://workflow-intake-agent:8080/langflow/chat` (or the service's fully qualified cluster DNS name).

The deployment uses two replicas, PostgreSQL checkpoint persistence, strict MessagePack serialization, non-root execution, and a read-only root filesystem. Add your bank's NetworkPolicy, service mesh policy, image signature, certificate, and observability sidecars at the platform layer.
