"""v1.4 tests: Google Search Console module + Apple Podcasts detection.

Offline: the Search Console HTTP layer is stubbed at server.http_json;
the iTunes lookup is fixture-based; the Gemini optimizer is stubbed.
No live Google or Apple calls and no real credentials are used.
Run: .venv/bin/python -m unittest test_v14_gsc_apple -v
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import unittest

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

_TEMP = tempfile.TemporaryDirectory(prefix="tapas-growth-v14-")
os.environ["TAPAS_DATA_DIR"] = _TEMP.name
os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["GEMINI_API_KEY"] = ""
os.environ["LINKEDIN_CLIENT_ID"] = ""
os.environ["LINKEDIN_CLIENT_SECRET"] = ""

import server  # noqa: E402
from services import gsc_service, publication_engine  # noqa: E402

FAKE_OPTIMIZATION = {
    "title": "t", "description": "d", "keywords": ["ai adoption"], "hashtags": [],
    "answer_snippet": "Adoption fails when readiness is skipped.",
    "entity_map": ["CHANGEReadyX™"], "schema_recommendations": [],
    "geo_recommendations": ["g"], "audience": "CHROs", "hook_options": ["h"],
    "cta": "Take the diagnostic", "risk_flags": [], "confidence": 0.8,
}


async def _fake_optimize(pub):
    return dict(FAKE_OPTIMIZATION)


ITUNES_FIXTURE = {
    "resultCount": 3,
    "results": [
        {"wrapperType": "collection", "kind": "podcast", "collectionId": 6831708010,
         "collectionName": "Ram's CHANGEReadyX™ from TAPAS Advisory"},
        {"wrapperType": "podcastEpisode", "trackId": 1000800333399,
         "trackName": "Why Firing Half Your Staff for AI Ends in Disaster",
         "trackViewUrl": "https://podcasts.apple.com/us/podcast/id6831708010?i=1000800333399",
         "releaseDate": "2026-11-07T01:06:00Z",
         "description": "<p>The AI Reality Check episode.</p>"},
        {"wrapperType": "podcastEpisode", "episodeGuid": "guid-ep-002",
         "trackName": "Why Do Enterprise AI Pilots Become Expensive Shelfware?",
         "trackViewUrl": "https://podcasts.apple.com/us/podcast/id6831708010?i=1000800111222",
         "releaseDate": "2026-11-05T05:00:00Z",
         "shortDescription": "Shelfware episode."},
    ],
}

GSC_ROWS = {"rows": [
    {"keys": ["erp transformation consultant india", "https://tapasadvisory.com/"],
     "clicks": 3, "impressions": 100, "ctr": 0.03, "position": 12.0},
    {"keys": ["erp transformation consultant india", "https://tapasadvisory.com/diagnostic"],
     "clicks": 1, "impressions": 50, "ctr": 0.02, "position": 8.0},
    {"keys": ["changereadyx", "https://tapasadvisory.com/"],
     "clicks": 6, "impressions": 30, "ctr": 0.2, "position": 3.0},
]}

YOUTUBE_SCOPES_NO_GSC = ("openid email profile "
                         "https://www.googleapis.com/auth/youtube.readonly "
                         "https://www.googleapis.com/auth/yt-analytics.readonly")
YOUTUBE_SCOPES_WITH_GSC = YOUTUBE_SCOPES_NO_GSC + " " + gsc_service.GSC_SCOPE


def _insert_google_connection(scopes: str) -> None:
    with server.db() as conn:
        conn.execute(
            """INSERT INTO connections(provider,status,account_id,display_name,instance,
               access_token_enc,refresh_token_enc,token_type,scopes,expires_at,metadata_json,connected_at,last_error)
               VALUES('youtube','connected','chan-1','Test Channel',NULL,?,?,?,?,?,?,?,NULL)
               ON CONFLICT(provider) DO UPDATE SET status='connected',scopes=excluded.scopes,
               access_token_enc=excluded.access_token_enc,refresh_token_enc=excluded.refresh_token_enc,
               expires_at=excluded.expires_at""",
            (server.encrypt_secret("fake-access-token"), server.encrypt_secret("fake-refresh-token"),
             "Bearer", scopes, int(time.time()) + 86400, "{}", server.iso()))


def _drop_google_connection() -> None:
    with server.db() as conn:
        conn.execute("DELETE FROM connections WHERE provider='youtube'")


class V14VersionAndJobsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(server.app)
        cls.client = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)
        _TEMP.cleanup()

    def test_version_is_1_4_0(self):
        # The 1.4 GSC/Apple contract: health reports the running version.
        # The exact version literal moved on in 1.5 (pinned by
        # test_v15_autopublish); here we assert >= 1.4.0, mirroring how
        # the earlier suites relaxed their pins when the next release
        # shipped.
        major, minor, _patch = (int(p) for p in server.APP_VERSION.split("."))
        self.assertGreaterEqual((major, minor), (1, 4))
        self.assertEqual(self.client.get("/api/health").json()["version"], server.APP_VERSION)

    def test_gsc_sync_job_registered_with_reliability_policy(self):
        ids = [j.id for j in server.scheduler.get_jobs()]
        self.assertIn("gsc_sync", ids)
        job = [j for j in server.scheduler.get_jobs() if j.id == "gsc_sync"][0]
        self.assertTrue(job.coalesce)
        self.assertEqual(job.max_instances, 1)


class V14GscUnitTests(unittest.TestCase):
    def test_scope_split_and_check(self):
        self.assertTrue(gsc_service.has_gsc_scope(YOUTUBE_SCOPES_WITH_GSC))
        self.assertFalse(gsc_service.has_gsc_scope(YOUTUBE_SCOPES_NO_GSC))
        # LinkedIn-style comma separation must also parse.
        self.assertTrue(gsc_service.has_gsc_scope("openid," + gsc_service.GSC_SCOPE))
        self.assertFalse(gsc_service.has_gsc_scope(""))
        self.assertFalse(gsc_service.has_gsc_scope(None))

    def test_configuration_fail_closed(self):
        missing = gsc_service.gsc_configuration(None)
        self.assertFalse(missing["configured"])
        self.assertEqual(missing["status"], "not_configured")
        self.assertEqual(missing["missing_scope"], gsc_service.GSC_SCOPE)
        self.assertIn("reconsent", missing)
        no_scope = gsc_service.gsc_configuration(
            {"status": "connected", "scopes": YOUTUBE_SCOPES_NO_GSC, "display_name": "X"})
        self.assertFalse(no_scope["configured"])
        self.assertEqual(no_scope["reason"], "missing_scope")
        ok = gsc_service.gsc_configuration(
            {"status": "connected", "scopes": YOUTUBE_SCOPES_WITH_GSC, "display_name": "X"})
        self.assertTrue(ok["configured"])

    def test_build_body(self):
        body = gsc_service.build_search_analytics_body("2026-10-12", "2026-11-08")
        self.assertEqual(body["dimensions"], ["query", "page"])
        self.assertEqual(body["startDate"], "2026-10-12")
        self.assertEqual(body["endDate"], "2026-11-08")

    def test_normalize_math(self):
        report = gsc_service.normalize_search_analytics(GSC_ROWS)
        totals = report["totals"]
        self.assertEqual(totals["clicks"], 10)
        self.assertEqual(totals["impressions"], 180)
        self.assertEqual(totals["rows"], 3)
        # Impression-weighted position: (12*100 + 8*50 + 3*30) / 180 = 9.39
        self.assertEqual(totals["position"], 9.39)
        top_q = report["top_queries"][0]
        self.assertEqual(top_q["name"], "changereadyx")  # most clicks (6)
        erp = [q for q in report["top_queries"] if q["name"].startswith("erp")][0]
        self.assertEqual(erp["clicks"], 4)
        self.assertEqual(erp["impressions"], 150)
        home = [p for p in report["top_pages"] if p["name"] == "https://tapasadvisory.com/"][0]
        self.assertEqual(home["clicks"], 9)
        self.assertEqual(home["impressions"], 130)


class V14GscEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(server.app)
        cls.client = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)
        _drop_google_connection()

    def setUp(self):
        _drop_google_connection()
        with server.db() as conn:
            conn.execute("DELETE FROM gsc_snapshots")

    def test_status_not_configured_without_connection(self):
        body = self.client.get("/api/gsc/status").json()
        self.assertEqual(body["status"], "not_configured")
        self.assertEqual(body["missing_scope"], gsc_service.GSC_SCOPE)
        self.assertEqual(body["reconsent"]["extra_scopes_env"], "GOOGLE_EXTRA_SCOPES")
        self.assertEqual(body["property"], "https://tapasadvisory.com/")
        self.assertIsNone(body["last_sync_at"])

    def test_status_not_configured_without_scope(self):
        _insert_google_connection(YOUTUBE_SCOPES_NO_GSC)
        body = self.client.get("/api/gsc/status").json()
        self.assertEqual(body["status"], "not_configured")
        self.assertEqual(body["reason"], "missing_scope")

    def test_sync_fail_closed_without_scope(self):
        _insert_google_connection(YOUTUBE_SCOPES_NO_GSC)
        body = self.client.post("/api/gsc/sync").json()
        self.assertEqual(body["status"], "not_configured")
        self.assertFalse(body["synced"])
        report = self.client.get("/api/gsc/report").json()
        self.assertEqual(report["status"], "no_data")

    def test_sync_and_report_with_scope_and_mocked_http(self):
        _insert_google_connection(YOUTUBE_SCOPES_WITH_GSC)

        async def fake_http_json(method, url, **kwargs):
            if url.endswith("/sites"):
                return {"siteEntry": [{"siteUrl": "https://tapasadvisory.com/",
                                       "permissionLevel": "siteOwner"}]}
            if "searchAnalytics/query" in url:
                # The request body must carry the query+page dimensions.
                assert kwargs["json_body"]["dimensions"] == ["query", "page"]
                return dict(GSC_ROWS)
            raise AssertionError(f"unexpected URL {url}")

        real = server.http_json
        server.http_json = fake_http_json
        try:
            body = self.client.post("/api/gsc/sync").json()
        finally:
            server.http_json = real
        self.assertEqual(body["status"], "synced")
        self.assertEqual(body["totals"]["clicks"], 10)
        self.assertEqual(body["provenance"], "Google Search Console API (webmasters v3)")
        report = self.client.get("/api/gsc/report").json()
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["top_queries"][0]["name"], "changereadyx")
        status = self.client.get("/api/gsc/status").json()
        self.assertEqual(status["status"], "configured")
        self.assertIsNotNone(status["last_sync_at"])

    def test_sync_property_not_found(self):
        _insert_google_connection(YOUTUBE_SCOPES_WITH_GSC)

        async def fake_http_json(method, url, **kwargs):
            return {"siteEntry": [{"siteUrl": "https://example.com/",
                                   "permissionLevel": "siteOwner"}]}

        real = server.http_json
        server.http_json = fake_http_json
        try:
            body = self.client.post("/api/gsc/sync").json()
        finally:
            server.http_json = real
        self.assertEqual(body["status"], "property_not_found")
        self.assertIn("https://example.com/", body["available_properties"])


class V14AppleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(server.app)
        cls.client = cls.ctx.__enter__()
        cls._real_fetch = publication_engine.fetch_itunes_lookup
        cls._real_fetch_server = server.fetch_itunes_lookup

        async def fake_fetch(show_id=publication_engine.APPLE_PODCAST_SHOW_ID, timeout=60.0):
            return json.loads(json.dumps(ITUNES_FIXTURE))

        publication_engine.fetch_itunes_lookup = fake_fetch
        server.fetch_itunes_lookup = fake_fetch
        cls._real_optimize = publication_engine.optimize_publication
        publication_engine.optimize_publication = _fake_optimize
        server.optimize_publication = _fake_optimize

    @classmethod
    def tearDownClass(cls):
        publication_engine.fetch_itunes_lookup = cls._real_fetch
        server.fetch_itunes_lookup = cls._real_fetch_server
        publication_engine.optimize_publication = cls._real_optimize
        server.optimize_publication = cls._real_optimize
        cls.ctx.__exit__(None, None, None)
        # NOTE: _TEMP is cleaned up by V14VersionAndJobsTests, which runs
        # last (alphabetical class order) — cleaning up here would delete
        # the shared test database out from under the later classes.

    def test_show_id_constant(self):
        self.assertEqual(publication_engine.APPLE_PODCAST_SHOW_ID, 6831708010)
        self.assertIn("6831708010", publication_engine.APPLE_LOOKUP_URL.format(
            show_id=publication_engine.APPLE_PODCAST_SHOW_ID))
        self.assertIn("apple_podcasts", publication_engine.PLATFORMS)

    def test_parse_skips_collection_and_maps_fields(self):
        pubs = publication_engine.parse_itunes_episodes(ITUNES_FIXTURE)
        self.assertEqual(len(pubs), 2)
        first = pubs[0]
        self.assertEqual(first["platform"], "apple_podcasts")
        self.assertEqual(first["external_id"], "1000800333399")
        self.assertTrue(first["url"].endswith("i=1000800333399"))
        self.assertNotIn("<p>", first["text"])
        self.assertTrue(first["published_at"].startswith("2026-11-07"))
        # Second episode has no trackId: falls back to episodeGuid.
        self.assertEqual(pubs[1]["external_id"], "guid-ep-002")

    def test_detect_registers_dedups_and_queues_approval(self):
        first, second = asyncio.run(self._detect_twice())
        self.assertEqual(first["found"], 2)
        self.assertEqual(first["new"], 2)
        self.assertEqual(second["new"], 0, "second pass must deduplicate")
        listing = self.client.get("/api/publications?platform=apple_podcasts").json()
        self.assertEqual(listing["count"], 2)
        queue = self.client.get("/api/approvals/queue").json()["approvals"]
        apple_approvals = [a for a in queue if a["payload"]
                           and (a["payload"].get("publication") or {}).get("platform") == "apple_podcasts"]
        self.assertEqual(len(apple_approvals), 2)
        self.assertEqual(apple_approvals[0]["status"], "pending_approval")

    async def _detect_twice(self):
        first = await server.detect_apple_podcasts()
        second = await server.detect_apple_podcasts()
        return first, second


if __name__ == "__main__":
    unittest.main()
