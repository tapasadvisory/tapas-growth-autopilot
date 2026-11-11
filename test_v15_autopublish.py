"""v1.5 auto-publish execution-layer tests.

Offline and side-effect-free: provider calls are stubbed at the
server._publish_via_provider seam or replaced by dry-run mode. NO real
post is ever fired. The worker is driven directly
(server.run_auto_publish_cycle), never left to the scheduler.
Run: .venv/bin/python -m unittest test_v15_autopublish -v
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest

from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient

_TEMP = tempfile.TemporaryDirectory(prefix="tapas-growth-v15-")
os.environ["TAPAS_DATA_DIR"] = _TEMP.name
os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["GEMINI_API_KEY"] = ""
os.environ["LINKEDIN_CLIENT_ID"] = ""
os.environ["LINKEDIN_CLIENT_SECRET"] = ""

import server  # noqa: E402
from services import publish_engine  # noqa: E402

_ENV_KEYS = ("AUTO_PUBLISH_ENABLED", "AUTO_PUBLISH_DRY_RUN", "AUTO_PUBLISH_MAX_ATTEMPTS")


def _create_and_approve(client, action_type, platform, payload, title="v1.5 test item"):
    created = client.post("/api/approvals", json={
        "action_type": action_type, "platform": platform, "title": title,
        "payload": payload, "proposed_by": "test", "risk_level": "Medium",
    })
    assert created.status_code == 200, created.text
    aid = created.json()["id"]
    decided = client.post(f"/api/approvals/{aid}/action", json={
        "decision": "approve", "actor": "ram", "notes": "test approval",
    })
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"
    return aid


def _insert_connection(provider: str, scopes: str) -> None:
    """Fake connected-provider row (dummy encrypted tokens; the worker's
    provider seam is stubbed or dry-run in every test, so the tokens are
    never used — readiness reads only status + scopes)."""
    with server.db() as conn:
        conn.execute(
            """INSERT INTO connections(provider,status,account_id,display_name,instance,
               access_token_enc,refresh_token_enc,token_type,scopes,expires_at,metadata_json,connected_at,last_error)
               VALUES(?,'connected','acct-1','Test Account',NULL,?,?, 'Bearer',?,?, '{}',?,NULL)
               ON CONFLICT(provider) DO UPDATE SET status='connected',scopes=excluded.scopes""",
            (provider, server.encrypt_secret("fake-access"), server.encrypt_secret("fake-refresh"),
             scopes, int(time.time()) + 86400, server.iso()))


def _queue_item(client, aid):
    queue = client.get("/api/approvals/queue").json()["approvals"]
    return [a for a in queue if a["id"] == aid][0]


def _audit_events(client, aid):
    logs = client.get("/api/audit-logs?limit=300").json()["audit_logs"]
    return [row["event_type"] for row in logs if row["target_entity"] == f"approval:{aid}"]


class _EnvGuard(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in _ENV_KEYS}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class V15UnitTests(_EnvGuard):
    def test_extract_text_shapes(self):
        self.assertEqual(publish_engine.extract_publish_text({"text": " hello "}, "linkedin"), "hello")
        self.assertEqual(publish_engine.extract_publish_text({"content": "c"}, "x"), "c")
        drafts = {"drafts": {"linkedin_post": "LI body", "bluesky_post": "BS body",
                             "x_thread": ["first post", "second post"]}}
        self.assertEqual(publish_engine.extract_publish_text(drafts, "linkedin"), "LI body")
        self.assertEqual(publish_engine.extract_publish_text(drafts, "bluesky"), "BS body")
        self.assertEqual(publish_engine.extract_publish_text(drafts, "x"), "first post")
        # The publication-detection payload shape must yield NO text.
        detection_payload = {"publication": {"platform": "substack", "title": "t"},
                             "optimization": {"title": "x"}, "channel": "organic",
                             "source": "publication-detection"}
        self.assertIsNone(publish_engine.extract_publish_text(detection_payload, "substack"))
        self.assertIsNone(publish_engine.extract_publish_text(None, "linkedin"))
        self.assertIsNone(publish_engine.extract_publish_text({"text": "  "}, "linkedin"))

    def test_classify(self):
        info = publish_engine.classify_item("publication_optimization", "linkedin", {"text": "sneaky"})
        self.assertEqual(info["kind"], "informational",
                         "detection approvals must never classify as publish, even with a text field")
        pub = publish_engine.classify_item("publish_post", "linkedin", {"text": "body"})
        self.assertEqual(pub["kind"], "publish")
        self.assertEqual(pub["text"], "body")
        self.assertEqual(publish_engine.classify_item("publish_post", "linkedin", {})["kind"],
                         "publish_no_text")
        self.assertEqual(publish_engine.classify_item("experiment", "linkedin", {"text": "b"})["kind"],
                         "other")

    def test_backoff_and_flags(self):
        self.assertEqual(publish_engine.backoff_seconds(1), 300)
        self.assertEqual(publish_engine.backoff_seconds(2), 600)
        self.assertEqual(publish_engine.backoff_seconds(3), 1200)
        self.assertTrue(publish_engine.auto_publish_enabled({}))
        self.assertFalse(publish_engine.auto_publish_enabled({"AUTO_PUBLISH_ENABLED": "false"}))
        self.assertFalse(publish_engine.auto_publish_dry_run({}))
        self.assertTrue(publish_engine.auto_publish_dry_run({"AUTO_PUBLISH_DRY_RUN": "true"}))
        self.assertEqual(publish_engine.max_attempts({}), 3)
        self.assertEqual(publish_engine.max_attempts({"AUTO_PUBLISH_MAX_ATTEMPTS": "2"}), 2)

    def test_readiness_honest_scope(self):
        conns = {
            "linkedin": {"status": "connected", "scopes": "email,openid,profile,w_member_social"},
            "x": {"status": "connected", "scopes": "users.read tweet.read offline.access"},
            "youtube": {"status": "connected", "scopes": "openid https://www.googleapis.com/auth/youtube.readonly"},
        }
        ready = publish_engine.provider_readiness(conns)
        self.assertEqual(ready["linkedin"]["status"], "ready")
        self.assertEqual(ready["x"]["status"], "ready_with_warning")
        self.assertIn("tweet.write", ready["x"]["detail"])
        self.assertEqual(ready["youtube"]["status"], "blocked")
        self.assertIn("youtube.upload", ready["youtube"]["reason"])
        self.assertEqual(ready["bluesky"]["status"], "blocked")
        self.assertIn("BLUESKY_APP_PASSWORD", ready["bluesky"]["reason"])
        ready2 = publish_engine.provider_readiness(conns, bluesky_handle=True, bluesky_app_password=True)
        self.assertEqual(ready2["bluesky"]["status"], "ready")
        self.assertEqual(ready["mastodon"]["status"], "blocked")
        self.assertEqual(ready["substack"]["status"], "blocked")


class V15WorkerTests(_EnvGuard):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(server.app)
        cls.client = cls.ctx.__enter__()
        _insert_connection("linkedin", "email,openid,profile,w_member_social")
        _insert_connection("x", "users.read tweet.read follows.read offline.access")

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)
        _TEMP.cleanup()

    def _cycle(self):
        return asyncio.run(server.run_auto_publish_cycle())

    def test_version_and_job(self):
        self.assertEqual(server.APP_VERSION, "1.6.0")
        self.assertEqual(self.client.get("/api/health").json()["version"], "1.6.0")
        ids = [j.id for j in server.scheduler.get_jobs()]
        self.assertIn("auto_publish", ids)
        job = [j for j in server.scheduler.get_jobs() if j.id == "auto_publish"][0]
        self.assertTrue(job.coalesce)
        self.assertEqual(job.max_instances, 1)

    def test_dry_run_executes_approved_publish_item(self):
        os.environ["AUTO_PUBLISH_DRY_RUN"] = "true"
        aid = _create_and_approve(self.client, "publish_post", "linkedin",
                                  {"text": "Dry-run proof post — never leaves the backend."})
        summary = self._cycle()
        self.assertEqual(summary["executed"], 1)
        item = _queue_item(self.client, aid)
        self.assertEqual(item["status"], "executed")
        execution = item["payload"]["execution"]
        self.assertEqual(execution["post_id"], f"dry-run-{aid}")
        self.assertTrue(execution["dry_run"])
        self.assertIn("autopublish.executed", _audit_events(self.client, aid))
        # Idempotency: a second cycle must not execute it again.
        summary2 = self._cycle()
        self.assertEqual(summary2["executed"], 0)
        events = _audit_events(self.client, aid)
        self.assertEqual(events.count("autopublish.executed"), 1)

    def test_informational_approval_never_executes(self):
        os.environ["AUTO_PUBLISH_DRY_RUN"] = "true"
        aid = _create_and_approve(self.client, "publication_optimization", "linkedin",
                                  {"publication": {"platform": "linkedin", "title": "t"},
                                   "optimization": {"title": "x"}, "channel": "organic",
                                   "source": "publication-detection"})
        self._cycle()
        item = _queue_item(self.client, aid)
        self.assertEqual(item["status"], "approved", "informational items must stay untouched")
        self.assertNotIn("execution", item["payload"])
        self.assertNotIn("autopublish.executed", _audit_events(self.client, aid))

    def test_expired_approval_never_executes(self):
        os.environ["AUTO_PUBLISH_DRY_RUN"] = "true"
        aid = _create_and_approve(self.client, "publish_post", "linkedin", {"text": "expired body"})
        with server.db() as conn:
            conn.execute("UPDATE approval_queue SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (aid,))
        summary = self._cycle()
        self.assertGreaterEqual(summary["expired"], 1)
        item = _queue_item(self.client, aid)
        self.assertEqual(item["status"], "expired")
        self.assertIn("autopublish.expired", _audit_events(self.client, aid))

    def test_youtube_item_blocked_scope_without_provider_call(self):
        os.environ["AUTO_PUBLISH_DRY_RUN"] = "true"
        calls = []

        async def recording_stub(provider, text):
            calls.append(provider)
            return {"post_id": "should-never-happen", "url": None}

        real = server._publish_via_provider
        server._publish_via_provider = recording_stub
        try:
            aid = _create_and_approve(self.client, "publish_post", "youtube", {"text": "video post"})
            summary = self._cycle()
        finally:
            server._publish_via_provider = real
        self.assertEqual(calls, [], "blocked providers must not reach the provider seam")
        self.assertGreaterEqual(summary["blocked_scope"], 1)
        item = _queue_item(self.client, aid)
        self.assertEqual(item["status"], "blocked_scope")
        self.assertIn("youtube.upload", item["payload"]["execution"]["reason"])
        self.assertIn("autopublish.blocked", _audit_events(self.client, aid))

    def test_provider_failure_retries_bounded_then_parks(self):
        os.environ.pop("AUTO_PUBLISH_DRY_RUN", None)
        os.environ["AUTO_PUBLISH_MAX_ATTEMPTS"] = "2"

        async def failing_stub(provider, text):
            raise HTTPException(402, "Payment Required (simulated $0-credit X account)")

        real = server._publish_via_provider
        server._publish_via_provider = failing_stub
        try:
            aid = _create_and_approve(self.client, "publish_post", "x", {"text": "x body"})
            first = self._cycle()
            item = _queue_item(self.client, aid)
            self.assertEqual(item["status"], "approved", "first failure must schedule a retry, not park")
            self.assertEqual(item["payload"]["execution"]["attempts"], 1)
            self.assertIn("next_attempt_at", item["payload"]["execution"])
            # Fast-forward past the backoff and run the second (final) attempt.
            with server.db() as conn:
                import json as _json
                row = conn.execute("SELECT payload_json FROM approval_queue WHERE id=?", (aid,)).fetchone()
                payload = _json.loads(row["payload_json"])
                payload["execution"]["next_attempt_at"] = "2000-01-01T00:00:00+00:00"
                conn.execute("UPDATE approval_queue SET payload_json=? WHERE id=?",
                             (_json.dumps(payload), aid))
            second = self._cycle()
        finally:
            server._publish_via_provider = real
        self.assertGreaterEqual(first["retry_scheduled"], 1)
        self.assertGreaterEqual(second["failed"], 1)
        item = _queue_item(self.client, aid)
        self.assertEqual(item["status"], "execution_failed")
        self.assertEqual(item["payload"]["execution"]["attempts"], 2)
        events = _audit_events(self.client, aid)
        self.assertIn("autopublish.attempt_failed", events)
        self.assertIn("autopublish.failed", events)
        # Parked: further cycles leave it alone.
        third = self._cycle()
        self.assertEqual(third["failed"], 0)
        self.assertEqual(_queue_item(self.client, aid)["status"], "execution_failed")

    def test_real_route_success_records_post_id(self):
        os.environ.pop("AUTO_PUBLISH_DRY_RUN", None)

        async def ok_stub(provider, text):
            return {"post_id": "urn:li:share:123", "url": "https://www.linkedin.com/feed/update/urn:li:share:123/"}

        real = server._publish_via_provider
        server._publish_via_provider = ok_stub
        try:
            aid = _create_and_approve(self.client, "publish_post", "linkedin", {"text": "real route body"})
            summary = self._cycle()
        finally:
            server._publish_via_provider = real
        self.assertEqual(summary["executed"], 1)
        item = _queue_item(self.client, aid)
        self.assertEqual(item["status"], "executed")
        self.assertEqual(item["payload"]["execution"]["post_id"], "urn:li:share:123")
        self.assertFalse(item["payload"]["execution"]["dry_run"])

    def test_kill_switch_disables_cycle(self):
        os.environ["AUTO_PUBLISH_ENABLED"] = "false"
        os.environ["AUTO_PUBLISH_DRY_RUN"] = "true"
        aid = _create_and_approve(self.client, "publish_post", "linkedin", {"text": "must not run"})
        summary = self._cycle()
        self.assertEqual(summary["status"], "disabled")
        self.assertEqual(_queue_item(self.client, aid)["status"], "approved")

    def test_status_endpoint(self):
        body = self.client.get("/api/autopublish/status").json()
        self.assertIn("enabled", body)
        self.assertIn("dry_run", body)
        self.assertIn("max_attempts", body)
        providers = body["providers"]
        for name in ("linkedin", "bluesky", "x", "youtube", "mastodon", "instagram", "spotify", "substack"):
            self.assertIn(name, providers)
        self.assertEqual(providers["youtube"]["status"], "blocked")
        self.assertIn("publish_items_by_status", body)


if __name__ == "__main__":
    unittest.main()
