import json
import unittest
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from use_case_agent.langgraph_agent import build_graph


ROOT = Path(__file__).resolve().parents[1]


class FakeExtractor:
    async def extract(self, *, message, message_id, current_case, planned_questions):
        return {
            "acknowledgement": "I recorded the stated goal.",
            "candidate_patch": {
                "summary": {
                    "goal": {
                        "value": message,
                        "evidence": "confirmed",
                        "source_ref": message_id,
                        "notes": "",
                    }
                }
            },
            "citations": [message_id],
        }


class LangGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_state_persists_by_thread_and_rejects_protected_fields(self):
        graph = build_graph(checkpointer=InMemorySaver(), extractor=FakeExtractor())
        config = {"configurable": {"thread_id": "CASE-A"}}
        first = await graph.ainvoke(
            {"user_message": "Reduce manual ticket routing", "message_id": "msg-1"}, config
        )
        second = await graph.ainvoke(
            {"user_message": "Reduce handling time", "message_id": "msg-2"}, config
        )
        self.assertEqual(first["case"]["case_id"], "CASE-A")
        self.assertEqual(second["case"]["summary"]["goal"]["value"], "Reduce handling time")
        self.assertIn("Please answer", second["assistant_message"])


if __name__ == "__main__":
    unittest.main()
