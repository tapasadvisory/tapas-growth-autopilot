"""v1.3 publication-detection tests for the TAPAS Growth Autopilot backend.

Offline: the RSS parser is tested against a fixture feed; the Gemini
optimizer is stubbed; no network or provider credentials are used.
Run: .venv/bin/python -m unittest test_v13_publications -v
"""
from __future__ import annotations

import os
import tempfile
import unittest

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

_TEMP = tempfile.TemporaryDirectory(prefix="tapas-growth-v13-")
os.environ["TAPAS_DATA_DIR"] = _TEMP.name
os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["GEMINI_API_KEY"] = ""
os.environ["LINKEDIN_CLIENT_ID"] = ""
os.environ["LINKEDIN_CLIENT_SECRET"] = ""

import server  # noqa: E402
from services import publication_engine  # noqa: E402

FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
<title>CHANGEReadyX Insights</title>
<item>
  <title>Why Firing Half Your Staff for AI Ends in Disaster</title>
  <link>https://ramchangereadyx.substack.com/p/why-firing-half-your-staff-for-ai</link>
  <guid isPermaLink="true">https://ramchangereadyx.substack.com/p/why-firing-half-your-staff-for-ai</guid>
  <pubDate>Sat, 07 Nov 2026 01:06:35 GMT</pubDate>
  <description><![CDATA[<p>Short summary.</p>]]></description>
  <content:encoded><![CDATA[<p>Full body about readiness and adoption.</p>]]></content:encoded>
</item>
<item>
  <title>Diagnose First</title>
  <link>https://ramchangereadyx.substack.com/p/diagnose-first</link>
  <guid>post-002</guid>
  <pubDate>Fri, 06 Nov 2026 10:00:00 GMT</pubDate>
  <description>Second post body.</description>
</item>
</channel>
</rss>"""

FAKE_OPTIMIZATION = {
    "title": "t", "description": "d", "keywords": ["ai adoption"], "hashtags": [],
    "answer_snippet": "Adoption fails when readiness is skipped.",
    "entity_map": ["CHANGEReadyX™"], "schema_recommendations": [],
    "geo_recommendations": ["g"], "audience": "CHROs", "hook_options": ["h"],
    "cta": "Take the diagnostic", "risk_flags": [], "confidence": 0.8,
}


async def _fake_optimize(pub):  # stub replacing the Gemini call
    return dict(FAKE_OPTIMIZATION)


class V13PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(server.app)
        cls.client = cls.ctx.__enter__()
        cls._real_optimize = publication_engine.optimize_publication
        publication_engine.optimize_publication = _fake_optimize
        server.optimize_publication = _fake_optimize

    @classmethod
    def tearDownClass(cls):
        publication_engine.optimize_publication = cls._real_optimize
        server.optimize_publication = cls._real_optimize
        cls.ctx.__exit__(None, None, None)
        _TEMP.cleanup()

    def test_version_is_1_3_0(self):
        self.assertEqual(server.APP_VERSION, "1.3.0")
        self.assertEqual(self.client.get("/api/health").json()["version"], "1.3.0")

    def test_detection_job_registered_with_reliability_policy(self):
        ids = [j.id for j in server.scheduler.get_jobs()]
        self.assertIn("publication_detection", ids)
        job = [j for j in server.scheduler.get_jobs() if j.id == "publication_detection"][0]
        self.assertTrue(job.coalesce)
        self.assertEqual(job.max_instances, 1)

    def test_rss_parser(self):
        pubs = publication_engine.parse_rss_feed(FEED_XML)
        self.assertEqual(len(pubs), 2)
        first = pubs[0]
        self.assertEqual(first["platform"], "substack")
        self.assertTrue(first["external_id"].endswith("why-firing-half-your-staff-for-ai"))
        self.assertIn("readiness and adoption", first["text"])
        self.assertNotIn("<p>", first["text"])
        self.assertTrue(first["published_at"].startswith("2026-11-07"))
        self.assertEqual(len(first["content_hash"]), 64)
        self.assertEqual(pubs[1]["external_id"], "post-002")

    def test_register_dedup_and_approval(self):
        pubs = publication_engine.parse_rss_feed(FEED_XML)

        import asyncio
        async def run():
            first = await server._register_many(pubs)
            second = await server._register_many(pubs)
            return first, second

        first, second = asyncio.run(run())
        self.assertEqual(first["found"], 2)
        self.assertEqual(first["new"], 2)
        self.assertEqual(second["new"], 0, "second pass must deduplicate")

        listing = self.client.get("/api/publications?platform=substack").json()
        self.assertEqual(listing["count"], 2)
        self.assertEqual(listing["publications"][0]["optimization"]["confidence"], 0.8)

        queue = self.client.get("/api/approvals/queue").json()["approvals"]
        pub_approvals = [a for a in queue if a["payload"] and a["payload"].get("source") == "publication-detection"
                         and (a["payload"].get("publication") or {}).get("platform") == "substack"]
        self.assertEqual(len(pub_approvals), 2)
        self.assertEqual(pub_approvals[0]["payload"]["channel"], "organic")
        self.assertEqual(pub_approvals[0]["status"], "pending_approval")
        self.assertTrue(pub_approvals[0].get("expires_at"))

    def test_analyze_endpoint_registers_and_dedups(self):
        body = {"platform": "youtube", "external_id": "vid-123",
                "url": "https://www.youtube.com/watch?v=vid-123",
                "title": "AI Pilots Return Zero", "text": "Readiness first."}
        r1 = self.client.post("/api/publications/analyze", json=body)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json()["status"], "registered")
        self.assertEqual(r1.json()["optimization"]["answer_snippet"],
                         "Adoption fails when readiness is skipped.")
        r2 = self.client.post("/api/publications/analyze", json=body)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["status"], "duplicate")

    def test_optimize_retry_recovers_from_transient_failure(self):
        import asyncio as _asyncio

        calls = {"n": 0}

        async def flaky(pub):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("HTTPStatusError 429 (simulated rate limit)")
            return dict(FAKE_OPTIMIZATION)

        async def no_sleep(_seconds):
            return None

        real_optimize, real_sleep = server.optimize_publication, server.asyncio.sleep
        server.optimize_publication = flaky
        server.asyncio.sleep = no_sleep
        try:
            optimization, error = _asyncio.run(server._optimize_with_retry({"platform": "youtube"}))
        finally:
            server.optimize_publication = real_optimize
            server.asyncio.sleep = real_sleep
        self.assertIsNone(error)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(optimization["confidence"], 0.8)

    def test_reoptimize_endpoint_exists(self):
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("/api/publications/reoptimize", paths)
        self.assertIn("/api/publications/detect", paths)

    def test_analyze_rejects_unknown_platform(self):
        r = self.client.post("/api/publications/analyze", json={
            "platform": "tiktok", "external_id": "x", "url": "https://example.com/x"})
        self.assertEqual(r.status_code, 400)


class V13FailClosedTests(unittest.TestCase):
    """With GEMINI_API_KEY blank, analyze must fail closed with 503."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(server.app)
        cls.client = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_analyze_fails_closed_without_gemini(self):
        # NOTE: runs against the real optimize_publication (no stub in this
        # class) with GEMINI_API_KEY="" set at module import.
        r = self.client.post("/api/publications/analyze", json={
            "platform": "substack", "external_id": "fc-1",
            "url": "https://example.com/fc-1", "title": "t", "text": "body"})
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
