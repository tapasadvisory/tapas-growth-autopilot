"""Meta Integration Hub (v1.8) contract tests.

Offline: Facebook Graph calls run against httpx MockTransport; server
registration is checked statically so this module never imports server
(importing it here would hijack the shared test DB for other modules).
No real post is ever fired.
Run: python -m unittest test_meta_hub_v18 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx  # noqa: E402

from services.owned_channel_publisher import (  # noqa: E402
    PublishConfigurationError, publish_facebook_page, publish_owned,
)
from services.publish_engine import provider_readiness  # noqa: E402
from services.publication_orchestrator_v16 import plan_distribution  # noqa: E402

PAGE = "61595126285733"


class FacebookPublisherTests(unittest.TestCase):
    def run_async(self, value):
        return asyncio.run(value)

    def test_feed_publish(self):
        calls = []

        def mocked(request):
            calls.append((request.method, request.url.path))
            return httpx.Response(200, json={"id": f"{PAGE}_123"})

        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(mocked)) as c:
                return await publish_facebook_page(c, "page-token", PAGE, "Hello Page")

        result = self.run_async(go())
        self.assertEqual(result["post_id"], f"{PAGE}_123")
        self.assertEqual(result["url"], f"https://www.facebook.com/{PAGE}_123")
        self.assertEqual(calls, [("POST", f"/v25.0/{PAGE}/feed")])

    def test_photo_publish_uses_post_id(self):
        def mocked(request):
            return httpx.Response(200, json={"id": "photo-1", "post_id": f"{PAGE}_124"})

        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(mocked)) as c:
                return await publish_facebook_page(
                    c, "page-token", PAGE, "Caption",
                    image_url="https://assets.tapasadvisory.com/p.png")

        with patch.dict(os.environ, {"TAPAS_MEDIA_HOSTS": "assets.tapasadvisory.com"}):
            result = self.run_async(go())
        self.assertEqual(result["post_id"], f"{PAGE}_124")

    def test_retry_dedupe_adopts_existing_post(self):
        calls = []

        def mocked(request):
            calls.append(request.method)
            if request.method == "GET":
                return httpx.Response(200, json={"data": [
                    {"id": f"{PAGE}_99", "message": "Same text"}]})
            return httpx.Response(200, json={"id": f"{PAGE}_100"})

        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(mocked)) as c:
                return await publish_facebook_page(
                    c, "page-token", PAGE, "Same text", retry_check=True)

        result = self.run_async(go())
        self.assertTrue(result["deduplicated"])
        self.assertEqual(result["post_id"], f"{PAGE}_99")
        self.assertEqual(calls, ["GET"])  # no second POST

    def test_bad_page_id_and_bad_link_rejected(self):
        async def go_bad_page():
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda r: httpx.Response(200, json={"id": "x"}))) as c:
                await publish_facebook_page(c, "t", "not-a-page", "Hi")

        async def go_bad_link():
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda r: httpx.Response(200, json={"id": "x"}))) as c:
                await publish_facebook_page(c, "t", PAGE, "Hi", link="http://example.com/x")

        with self.assertRaises(PublishConfigurationError):
            self.run_async(go_bad_page())
        with self.assertRaises(PublishConfigurationError):
            self.run_async(go_bad_link())

    def test_dispatch_routes_facebook(self):
        def mocked(request):
            return httpx.Response(200, json={"id": f"{PAGE}_7"})

        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(mocked)) as c:
                return await publish_owned(c, "facebook", "page-token", PAGE,
                                           "Dispatched", {})

        self.assertEqual(self.run_async(go())["post_id"], f"{PAGE}_7")


class FacebookReadinessTests(unittest.TestCase):
    def test_readiness_fails_closed_then_ready(self):
        s = provider_readiness({})
        self.assertEqual(s["facebook"]["status"], "blocked")
        data = {"facebook": {"status": "connected", "scopes": "pages_show_list"}}
        self.assertEqual(provider_readiness(data)["facebook"]["status"], "blocked")
        data["facebook"]["scopes"] += " pages_manage_posts"
        self.assertEqual(provider_readiness(data)["facebook"]["status"], "ready")

    def test_planner_accepts_facebook(self):
        p = plan_distribution({"publication_id": "sample", "status": "published"},
                              channels=["facebook"])
        tasks = [t for t in p["tasks"] if t["action"] == "distribution"]
        self.assertEqual(len(tasks), 1)
        self.assertTrue(all(t["approval_required"] for t in tasks))


class FacebookServerRegistrationTests(unittest.TestCase):
    """Static registration checks (the live /api/status + /api/health checks
    after a port verify the same facts against the running app)."""

    def test_version_and_registries(self):
        src = (Path(__file__).parent / "server.py").read_text()
        self.assertIn('APP_VERSION = "1.8.0"', src)
        self.assertIn('"facebook": {"label":"Facebook Page"', src)
        self.assertIn('"client_id":"META_APP_ID","client_secret":"META_APP_SECRET",\n  "scopes":["pages_show_list","pages_manage_posts","pages_read_engagement","read_insights"]', src)
        self.assertIn("async def sync_facebook(", src)
        self.assertIn('provider in {"youtube", "instagram", "threads", "facebook"}', src)


if __name__ == "__main__":
    unittest.main()
