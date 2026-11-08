"""v1.2 reliability tests for the TAPAS Growth Autopilot backend.

Offline: no provider credentials or network calls required.
Run: .venv/bin/python -m unittest test_v12_reliability -v
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

_TEMP = tempfile.TemporaryDirectory(prefix="tapas-growth-v12-")
os.environ["TAPAS_DATA_DIR"] = _TEMP.name
os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["GEMINI_API_KEY"] = ""
os.environ["LINKEDIN_CLIENT_ID"] = ""
os.environ["LINKEDIN_CLIENT_SECRET"] = ""

import server  # noqa: E402


class V12ReliabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(server.app)
        cls.client = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)
        _TEMP.cleanup()

    def test_version_is_1_2_0(self):
        # The 1.2 reliability contract: health reports the running version,
        # uptime and scheduler jobs. The exact version literal moved on in
        # 1.3 (pinned by test_v13_publications); here we assert >= 1.2.0.
        major, minor, _patch = (int(p) for p in server.APP_VERSION.split("."))
        self.assertGreaterEqual((major, minor), (1, 2))
        body = self.client.get("/api/health").json()
        self.assertEqual(body["version"], server.APP_VERSION)
        self.assertIn("uptime_seconds", body)
        self.assertIn("scheduler_jobs", body)

    def test_scheduler_jobs_unique_and_policy_set(self):
        jobs = server.scheduler.get_jobs()
        ids = [j.id for j in jobs]
        self.assertEqual(len(ids), len(set(ids)), "duplicate scheduler job ids")
        self.assertIn("discovery", ids)
        self.assertIn("schedules", ids)
        for job in jobs:
            self.assertTrue(job.coalesce, f"{job.id} must coalesce missed runs")
            self.assertEqual(job.max_instances, 1)
            self.assertIsNotNone(job.misfire_grace_time)
            self.assertGreaterEqual(job.misfire_grace_time, 60)

    def test_missed_schedule_count_does_not_error(self):
        self.assertGreaterEqual(server.count_missed_schedules(), 0)

    def test_approval_has_expiry_and_clear_status(self):
        created = self.client.post("/api/approvals", json={
            "action_type": "publish_post", "platform": "linkedin",
            "title": "v1.2 expiry test", "payload": {"x": 1},
            "proposed_by": "test", "risk_level": "Low",
        })
        self.assertEqual(created.status_code, 200)
        body = created.json()
        self.assertEqual(body["status"], "pending_approval")
        self.assertTrue(body.get("expires_at"), "approval must carry expires_at")

    def test_expired_approval_cannot_be_decided_but_can_be_renewed(self):
        created = self.client.post("/api/approvals", json={
            "action_type": "publish_post", "platform": "x",
            "title": "v1.2 expired test", "payload": {},
            "proposed_by": "test", "risk_level": "Low",
        }).json()
        aid = created["id"]
        with server.db() as conn:
            conn.execute("UPDATE approval_queue SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (aid,))
        decided = self.client.post(f"/api/approvals/{aid}/action", json={
            "decision": "approve", "actor": "ram", "notes": "",
        })
        self.assertEqual(decided.status_code, 410)
        queue = self.client.get("/api/approvals/queue").json()["approvals"]
        item = [a for a in queue if a["id"] == aid][0]
        self.assertEqual(item["status"], "expired")
        renewed = self.client.post(f"/api/approvals/{aid}/renew", json={
            "actor": "ram", "notes": "renew for test",
        })
        self.assertEqual(renewed.status_code, 200)
        self.assertEqual(renewed.json()["status"], "pending_approval")
        decided2 = self.client.post(f"/api/approvals/{aid}/action", json={
            "decision": "approve", "actor": "ram", "notes": "ok",
        })
        self.assertEqual(decided2.status_code, 200)
        self.assertEqual(decided2.json()["status"], "approved")

    def test_audit_log_records_v12_events(self):
        # Self-contained: drive one approval through expire -> renew so the
        # audit assertions do not depend on test execution order.
        created = self.client.post("/api/approvals", json={
            "action_type": "publish_post", "platform": "bluesky",
            "title": "v1.2 audit test", "payload": {},
            "proposed_by": "test", "risk_level": "Low",
        }).json()
        aid = created["id"]
        with server.db() as conn:
            conn.execute("UPDATE approval_queue SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (aid,))
        self.client.post(f"/api/approvals/{aid}/action", json={
            "decision": "approve", "actor": "ram", "notes": "",
        })
        self.client.post(f"/api/approvals/{aid}/renew", json={
            "actor": "ram", "notes": "audit test",
        })
        logs = self.client.get("/api/audit-logs?limit=100").json()["audit_logs"]
        types = {row["event_type"] for row in logs}
        self.assertIn("approval.requested", types)
        self.assertIn("approval.expired", types)
        self.assertIn("approval.renewed", types)

    def test_health_reports_no_secret_values(self):
        text = self.client.get("/api/health").text + self.client.get("/api/status").text
        self.assertNotIn(os.environ["TOKEN_ENCRYPTION_KEY"], text)


if __name__ == "__main__":
    unittest.main()
