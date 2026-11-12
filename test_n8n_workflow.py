"""Offline structure and safety tests for the importable n8n workflow."""
import json
import unittest
from pathlib import Path

PATH = Path(__file__).parent / "n8n" / "workflows" / "rea_observation_workflow.json"


class N8nWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = json.loads(PATH.read_text(encoding="utf-8"))
        cls.nodes = {n["name"]: n for n in cls.workflow["nodes"]}

    def test_inactive_by_default(self):
        self.assertFalse(self.workflow["active"])

    def test_expected_read_only_endpoints(self):
        requests = [n for n in self.nodes.values() if n["type"] == "n8n-nodes-base.httpRequest"]
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(n["parameters"].get("method", "GET") == "GET" for n in requests))
        self.assertEqual(
            {n["parameters"]["url"].split("/api/")[-1] for n in requests},
            {"autopublish/status", "analytics/snapshots"},
        )

    def test_sequential_execution_and_capture(self):
        edges = self.workflow["connections"]
        expected = [
            ("Every 30 minutes", "Read publication status"),
            ("Read publication status", "Read analytics snapshots"),
            ("Read analytics snapshots", "Create REA observation"),
        ]
        for source, target in expected:
            self.assertEqual(edges[source]["main"][0][0]["node"], target)

    def test_no_engagement_or_social_cookies(self):
        content = PATH.read_text(encoding="utf-8").lower()
        for prohibited in ("li_at", "sessionid", "auth_token", "cookie:", "likes/create"):
            self.assertNotIn(prohibited, content)

    def test_reach_not_fabricated(self):
        js = self.nodes["Create REA observation"]["parameters"]["jsCode"]
        self.assertIn("not evidence of increased organic views", js)
        self.assertIn("snapshot_count", js)


if __name__ == "__main__":
    unittest.main()
