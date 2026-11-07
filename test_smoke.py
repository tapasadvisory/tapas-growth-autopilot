"""Offline smoke tests for the TAPAS Growth Autopilot backend.

No provider credentials or external network calls are required.
Run: python growth-autopilot/test_smoke.py
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

_TEMP = tempfile.TemporaryDirectory(prefix="tapas-growth-test-")
os.environ["TAPAS_DATA_DIR"] = _TEMP.name
os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["GEMINI_API_KEY"] = ""

import server  # noqa: E402


class GrowthAutopilotSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(server.app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        _TEMP.cleanup()

    def test_health_and_scheduler(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["scheduler_running"])

    def test_provider_status_catalogue(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        providers = response.json()["providers"]
        expected = {"linkedin", "youtube", "instagram", "x", "spotify", "bluesky", "mastodon", "soundcloud"}
        self.assertEqual(set(providers), expected)
        self.assertEqual(providers["bluesky"]["status"], "available")

    def test_gemini_fails_closed_without_server_key(self):
        response = self.client.post("/api/ai/comments", json={
            "post_text": "This is a sufficiently long source post for the comment draft test.",
            "count": 3
        })
        self.assertEqual(response.status_code, 503)
        self.assertIn("GEMINI_API_KEY", response.json()["detail"])

    def test_rule_create_list_and_patch(self):
        created = self.client.post("/api/discovery/rules", json={
            "keyword": "AI workforce readiness",
            "platform": "Bluesky",
            "rule_type": "keyword",
            "enabled": True
        })
        self.assertEqual(created.status_code, 200)
        rule_id = created.json()["id"]
        listed = self.client.get("/api/discovery/rules")
        self.assertIn(rule_id, [x["id"] for x in listed.json()["rules"]])
        patched = self.client.patch(f"/api/discovery/rules/{rule_id}", json={"enabled": False})
        self.assertEqual(patched.status_code, 200)
        self.assertFalse(next(x for x in self.client.get("/api/discovery/rules").json()["rules"] if x["id"] == rule_id)["enabled"])

    def test_schedule_requires_approval_before_worker(self):
        future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
        created = self.client.post("/api/schedules", json={
            "title": "Weekly leadership insight",
            "platform": "LinkedIn",
            "cadence": "Weekly",
            "next_run_at": future,
            "deliverable": "Original post",
            "approved": False
        })
        self.assertEqual(created.status_code, 200)
        item = created.json()
        self.assertEqual(item["status"], "Pending approval")
        self.assertFalse(item["approved"])
        approved = self.client.post(f"/api/schedules/{item['id']}/approve")
        self.assertEqual(approved.status_code, 200)
        reread = self.client.get("/api/schedules").json()["schedules"]
        self.assertTrue(next(x for x in reread if x["id"] == item["id"])["approved"])

    def test_missing_provider_app_credentials_do_not_fake_connection(self):
        response = self.client.get("/api/connect/linkedin/start", follow_redirects=False)
        self.assertEqual(response.status_code, 400)
        self.assertIn("LINKEDIN_CLIENT_ID", response.json()["detail"])
        status = self.client.get("/api/status").json()["providers"]["linkedin"]
        self.assertNotEqual(status["status"], "connected")

    def test_provider_tokens_are_encrypted_at_rest(self):
        token = "secret-access-token-for-smoke-test"
        encrypted = server.encrypt_secret(token)
        self.assertNotEqual(encrypted, token)
        self.assertEqual(server.decrypt_secret(encrypted), token)


if __name__ == "__main__":
    unittest.main(verbosity=2)
