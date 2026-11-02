import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LangflowJsonTests(unittest.TestCase):
    def test_import_file_has_expected_portable_chain(self):
        flow = json.loads(
            (ROOT / "langflow" / "workflow_automation_discovery_langgraph.json").read_text()
        )
        types = [node["data"]["type"] for node in flow["data"]["nodes"]]
        self.assertEqual(
            types,
            ["ChatInput", "MessagetoData", "APIRequest", "ParserComponent", "ChatOutput"],
        )
        self.assertEqual(len(flow["data"]["edges"]), 4)
        api = next(node for node in flow["data"]["nodes"] if node["data"]["type"] == "APIRequest")
        self.assertTrue(api["data"]["node"]["template"]["url_input"]["value"].endswith("/langflow/chat"))


if __name__ == "__main__":
    unittest.main()
