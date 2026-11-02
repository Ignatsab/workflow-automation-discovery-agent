import unittest

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from use_case_agent.api import create_app


class FakeExtractor:
    async def extract(self, *, message, message_id, current_case, planned_questions):
        return {"acknowledgement": "Recorded.", "candidate_patch": {}, "citations": [message_id]}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client_context = TestClient(
            create_app(extractor=FakeExtractor(), checkpointer=InMemorySaver())
        )
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)

    def test_langflow_adapter_returns_scalar_text(self):
        response = self.client.post(
            "/langflow/chat", json={"text": "Automate ticket triage", "session_id": "case-1", "id": "msg-1"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), str)
        self.assertIn("Please answer", response.json())

    def test_missing_session_is_rejected(self):
        response = self.client.post("/langflow/chat", json={"text": "Hello"})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
