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
# Blank provider app credentials so the suite stays hermetic even when a real
# .env sits beside this file (load_dotenv does not override existing vars).
# test_missing_provider_app_credentials_do_not_fake_connection depends on
# LinkedIn app credentials being absent.
os.environ["LINKEDIN_CLIENT_ID"] = ""
os.environ["LINKEDIN_CLIENT_SECRET"] = ""

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
        expected = {"linkedin", "youtube", "instagram", "threads", "facebook", "x", "spotify", "bluesky", "mastodon", "soundcloud"}
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


# ---------------------------------------------------------------------------
# Release 1.1 additive-layer tests (offline; original suite above is untouched)
# ---------------------------------------------------------------------------
import asyncio  # noqa: E402
import json as _json  # noqa: E402

import httpx as _httpx  # noqa: E402

from services.approval_workflow_engine import write_audit_log  # noqa: E402
from services.content_studio_engine import ContentStudio  # noqa: E402
from services.cross_platform_engine import CrossPlatformEngine  # noqa: E402
from services.experimentation_engine import two_proportion_ztest  # noqa: E402
from services.gemini_client import GeminiNotConfigured  # noqa: E402
from services.github_engine import GitHubGrowthEngine  # noqa: E402
from services.search_geo_engine import SEOAEOGEOEngine, geo_audit  # noqa: E402
from services.youtube_engine import YouTubeGrowthEngine  # noqa: E402


class GrowthAutopilotEngineTests(unittest.TestCase):
    def test_ztest_significant_adopt_b(self):
        result = two_proportion_ztest(50, 1000, 80, 1000)
        self.assertLess(result["p_value"], 0.05)
        self.assertTrue(result["significant_at_0_05"])
        self.assertEqual(result["decision"], "adopt_b")
        self.assertGreater(result["z_score"], 1.96)

    def test_ztest_equal_rates_inconclusive(self):
        result = two_proportion_ztest(50, 1000, 50, 1000)
        self.assertEqual(result["z_score"], 0.0)
        self.assertEqual(result["p_value"], 1.0)
        self.assertEqual(result["decision"], "inconclusive")

    def test_ztest_worse_b_keeps_a(self):
        result = two_proportion_ztest(80, 1000, 50, 1000)
        self.assertEqual(result["decision"], "keep_a")

    def test_geo_audit_full_pass(self):
        text = (
            "Ram Narayanan, Founder of TAPAS Advisory, explains CHANGEReadyX™. "
            "MIT NANDA research found 95% of GenAI pilots deliver no P&L return. "
            "Run the diagnostic at tapasadvisory.com/diagnostic — tapasadvisory.com."
        )
        result = geo_audit(text)
        self.assertEqual(result["readiness_score"], 1.0)
        self.assertEqual(result["passed"], result["total"])

    def test_geo_audit_bare_changereadyx_fails_trademark_check(self):
        text = "TAPAS Advisory uses CHANGEReadyX for readiness. tapasadvisory.com/diagnostic"
        result = geo_audit(text)
        checks = {c["check"]: c["passed"] for c in result["checks"]}
        self.assertFalse(checks["no_bare_changereadyx"])
        self.assertFalse(checks["changereadyx_with_trademark"])
        self.assertLess(result["readiness_score"], 1.0)

    def _github_mock_transport(self):
        def handler(request: _httpx.Request) -> _httpx.Response:
            url = str(request.url)
            if "traffic/views" in url:
                return _httpx.Response(403, json={"message": "Must have push access"})
            if url.endswith("/repos/tapasadvisory/tapas-growth-autopilot"):
                return _httpx.Response(200, json={
                    "stargazers_count": 42, "forks_count": 7,
                    "open_issues_count": 3, "watchers_count": 11,
                })
            return _httpx.Response(404, json={"message": "Not Found"})

        return _httpx.MockTransport(handler)

    def test_github_metrics_with_mock_transport(self):
        engine = GitHubGrowthEngine(token="test-token", transport=self._github_mock_transport())
        result = asyncio.run(engine.get_repository_metrics())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["stars"], 42)
        self.assertEqual(result["forks"], 7)
        self.assertEqual(result["watchers"], 11)

    def test_github_traffic_permission_denied_is_null_not_zero(self):
        engine = GitHubGrowthEngine(token="test-token", transport=self._github_mock_transport())
        result = asyncio.run(engine.get_repository_metrics())
        self.assertEqual(result["traffic"]["status"], "permission_denied")
        self.assertIsNone(result["traffic"]["value"])

    def test_github_traffic_unconfigured_without_token(self):
        engine = GitHubGrowthEngine(token="", transport=self._github_mock_transport())
        result = asyncio.run(engine.get_repository_metrics())
        self.assertEqual(result["traffic"]["status"], "unconfigured")
        self.assertIsNone(result["traffic"]["value"])

    def test_youtube_retention_unconfigured_without_token(self):
        result = asyncio.run(YouTubeGrowthEngine().retention_report("abc123", None))
        self.assertEqual(result["status"], "unconfigured")
        self.assertIsNone(result["value"])

    def test_gemini_backed_engines_fail_closed_without_key(self):
        # GEMINI_API_KEY is set to "" at the top of this module.
        with self.assertRaises(GeminiNotConfigured):
            asyncio.run(SEOAEOGEOEngine().generate_aeo("AI transformation failures"))
        with self.assertRaises(GeminiNotConfigured):
            asyncio.run(SEOAEOGEOEngine().research_keywords("AI transformation failures"))
        with self.assertRaises(GeminiNotConfigured):
            asyncio.run(ContentStudio().generate_bundle("AI transformation failures"))
        with self.assertRaises(GeminiNotConfigured):
            asyncio.run(CrossPlatformEngine().generate_drafts("Topic", "Source text for drafting."))
        with self.assertRaises(GeminiNotConfigured):
            asyncio.run(GitHubGrowthEngine(token="x").generate_launch_kit("v1.1", ["Initial release"]))
        with self.assertRaises(GeminiNotConfigured):
            asyncio.run(GitHubGrowthEngine(token="x").generate_readme_improvements())
        with self.assertRaises(GeminiNotConfigured):
            asyncio.run(YouTubeGrowthEngine().evaluate_titles("AI transformation failures"))
        with self.assertRaises(GeminiNotConfigured):
            asyncio.run(YouTubeGrowthEngine().retention_optimize("AI transformation failures"))
        with self.assertRaises(GeminiNotConfigured):
            asyncio.run(YouTubeGrowthEngine().generate_shorts_script("AI transformation failures"))


class GrowthAutopilotEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.init_db()
        cls.client = TestClient(server.app)

    def test_pillars_endpoint_returns_12(self):
        response = self.client.get("/api/youtube/pillars")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 12)
        self.assertIn("Change Readiness & CHANGEReadyX™", body["pillars"])

    def test_dashboard_summary(self):
        response = self.client.get("/api/dashboard/summary")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("counts", body)
        self.assertIn("pending_approvals", body["counts"])
        self.assertIn("connections", body)

    def test_geo_audit_endpoint(self):
        response = self.client.post("/api/search/geo/audit", json={
            "text": "Ram Narayanan of TAPAS Advisory on CHANGEReadyX™ — tapasadvisory.com/diagnostic"
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["passed"], response.json()["total"])

    def test_seo_status_is_honest_about_search_console(self):
        response = self.client.get("/api/search/seo/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "requires_google_search_console")

    def test_entities_registry_without_crpi(self):
        response = self.client.get("/api/search/entities")
        self.assertEqual(response.status_code, 200)
        raw = response.text
        self.assertIn("CHANGEReadyX™", raw)
        self.assertIn("WISL™", raw)
        self.assertIn("TII™", raw)
        self.assertNotIn("CRPI", raw)

    def test_youtube_videos_empty_is_valid(self):
        response = self.client.get("/api/youtube/videos")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["videos"], [])

    def test_thumbnail_brief_and_analyze_alias(self):
        for path in ("/api/youtube/thumbnail/brief", "/api/youtube/thumbnails/analyze"):
            response = self.client.post(path, json={"title": "Why 95% of AI Pilots Return Zero"})
            self.assertEqual(response.status_code, 200, path)
            self.assertTrue(response.json()["checklist"])

    def test_gemini_endpoints_fail_closed_503(self):
        cases = [
            ("/api/youtube/titles/evaluate", {"topic": "AI transformation failures"}),
            ("/api/youtube/retention/optimize", {"topic": "AI transformation failures"}),
            ("/api/youtube/shorts/generate", {"topic": "AI transformation failures"}),
            ("/api/github/audit", None),
            ("/api/github/launch-kit", {"version": "v1.1", "highlights": ["x"]}),
            ("/api/search/aeo/generate", {"topic": "AI transformation failures"}),
            ("/api/search/keywords/research", {"topic": "AI transformation failures"}),
            ("/api/studio/generate-bundle", {"topic": "AI transformation failures"}),
            ("/api/crossplatform/draft", {"topic": "AI failures", "source_text": "A sufficiently long source text."}),
        ]
        for path, payload in cases:
            response = self.client.post(path, json=payload) if payload is not None else self.client.post(path)
            self.assertEqual(response.status_code, 503, path)
            self.assertIn("GEMINI_API_KEY", response.json()["detail"], path)

    def test_studio_bundles_list(self):
        response = self.client.get("/api/studio/bundles")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["bundles"], [])

    def test_retention_endpoint_unconfigured_when_youtube_not_connected(self):
        response = self.client.post("/api/youtube/retention", json={"video_id": "abc123"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "unconfigured")

    def test_experiments_create_and_evaluate(self):
        created = self.client.post("/api/experiments", json={
            "title": "Title variant test",
            "hypothesis": "Question titles lift CTR",
            "target_audience": "CHROs",
            "content_format": "long-form",
            "test_variable": "title",
            "variants": [{"name": "A"}, {"name": "B"}],
            "baseline": {"name": "A"},
        })
        self.assertEqual(created.status_code, 200)
        experiment_id = created.json()["id"]
        evaluated = self.client.post("/api/experiments/evaluate", json={
            "experiment_id": experiment_id,
            "a": {"conversions": 50, "n": 1000},
            "b": {"conversions": 80, "n": 1000},
        })
        self.assertEqual(evaluated.status_code, 200)
        self.assertEqual(evaluated.json()["decision"], "adopt_b")
        listed = self.client.get("/api/experiments").json()["experiments"]
        row = next(x for x in listed if x["id"] == experiment_id)
        self.assertEqual(row["status"], "evaluated")
        self.assertEqual(row["results"]["decision"], "adopt_b")

    def test_approval_flow_and_audit_chain(self):
        created = self.client.post("/api/approvals", json={
            "action_type": "publish_post",
            "platform": "LinkedIn",
            "title": "Test approval item",
            "payload": {"text": "draft"},
            "proposed_by": "test-suite",
            "risk_level": "High",
        })
        self.assertEqual(created.status_code, 200)
        approval_id = created.json()["id"]
        queue = self.client.get("/api/approvals/queue").json()["approvals"]
        self.assertEqual(queue[0]["id"], approval_id)
        self.assertEqual(queue[0]["status"], "pending_approval")
        acted = self.client.post(f"/api/approvals/{approval_id}/action", json={
            "decision": "approve", "actor": "Ram Narayanan", "notes": "ok",
        })
        self.assertEqual(acted.status_code, 200)
        self.assertEqual(acted.json()["status"], "approved")
        logs = self.client.get("/api/audit-logs").json()["audit_logs"]
        self.assertGreaterEqual(len(logs), 2)
        checksums = [row["tamper_proof_checksum"] for row in logs]
        self.assertTrue(all(len(c) == 64 for c in checksums))
        self.assertNotEqual(checksums[0], checksums[1])
        # Second decision on the same item must be refused.
        again = self.client.post(f"/api/approvals/{approval_id}/action", json={
            "decision": "approve", "actor": "Ram Narayanan",
        })
        self.assertEqual(again.status_code, 409)

    def test_audit_chain_links_previous_checksum(self):
        with server.db() as conn:
            first = write_audit_log(conn, timestamp="2026-01-01T00:00:00+00:00",
                                    event_type="test.one", actor="tester",
                                    target_entity="test:1", outcome="ok", details={})
            second = write_audit_log(conn, timestamp="2026-01-01T00:01:00+00:00",
                                     event_type="test.two", actor="tester",
                                     target_entity="test:1", outcome="ok", details={})
        import hashlib as _hashlib
        expected = _hashlib.sha256(
            (first["tamper_proof_checksum"] + "2026-01-01T00:01:00+00:00" + "test.two"
             + "tester" + "test:1" + "ok" + _json.dumps({}, sort_keys=True)).encode()
        ).hexdigest()
        self.assertEqual(second["tamper_proof_checksum"], expected)
