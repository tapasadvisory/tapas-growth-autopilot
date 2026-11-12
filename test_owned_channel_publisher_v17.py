"""Offline contract tests for v1.7 official publishing adapters."""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from services.owned_channel_publisher import (
    PublishConfigurationError, publish_owned, require_media_url, require_video_path,
)
from services.publish_engine import provider_readiness
from services.publication_orchestrator_v16 import plan_distribution


class OwnedChannelTests(unittest.TestCase):
    def run_async(self, value):
        return asyncio.run(value)

    def test_readiness_needs_explicit_scope(self):
        data = {"youtube": {"status": "connected", "scopes": "https://www.googleapis.com/auth/youtube.readonly"},
                "instagram": {"status": "connected", "scopes": "instagram_business_basic"},
                "threads": {"status": "connected", "scopes": "threads_basic"}}
        s = provider_readiness(data)
        for platform in data:
            self.assertEqual(s[platform]["status"], "blocked", platform)
        data["youtube"]["scopes"] += " https://www.googleapis.com/auth/youtube.upload"
        data["instagram"]["scopes"] += " instagram_business_content_publish"
        data["threads"]["scopes"] += " threads_content_publish"
        s = provider_readiness(data)
        for platform in data:
            self.assertEqual(s[platform]["status"], "ready", platform)

    def test_planner_accepts_new_channels(self):
        p = plan_distribution({"publication_id": "sample", "status": "published"},
                              channels=["threads", "instagram"])
        self.assertEqual(len([t for t in p["tasks"] if t["action"] == "distribution"]), 2)
        self.assertTrue(all(t["approval_required"] for t in p["tasks"]))

    def test_url_allowlist(self):
        with patch.dict(os.environ, {"TAPAS_MEDIA_HOSTS": "assets.tapasadvisory.com"}):
            self.assertEqual(
                require_media_url("https://assets.tapasadvisory.com/photo.png"),
                "https://assets.tapasadvisory.com/photo.png")
            for bad in ("http://assets.tapasadvisory.com/photo.png",
                        "https://evil.example/photo.png",
                        "https://assets.tapasadvisory.com.evil.example/photo.png"):
                with self.assertRaises(PublishConfigurationError):
                    require_media_url(bad)

    def test_threads_two_stage_publish(self):
        calls = []
        def mocked(request):
            calls.append((request.url.path, request.headers.get("Authorization")))
            if request.url.path.endswith("threads_publish"):
                return httpx.Response(200, json={"id": "post-123"})
            return httpx.Response(200, json={"id": "container-123"})
        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(mocked)) as c:
                return await publish_owned(c, "threads", "token", "456", "Test content", {})
        r = self.run_async(go())
        self.assertEqual(r["post_id"], "post-123")
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(x[1] == "Bearer token" for x in calls))

    def test_instagram_two_stage_publish(self):
        calls = []
        def mocked(request):
            calls.append(request.url.path)
            return httpx.Response(200, json={"id": "1234"})
        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(mocked)) as c:
                return await publish_owned(c, "instagram", "token", "123", "Image caption",
                    {"media": {"image_url": "https://assets.tapasadvisory.com/photo.png"}})
        with patch.dict(os.environ, {"TAPAS_MEDIA_HOSTS": "assets.tapasadvisory.com"}):
            r = self.run_async(go())
        self.assertEqual(r["post_id"], "1234")
        self.assertIn("/media_publish", calls[-1])

    def test_youtube_upload_stays_in_media_root(self):
        with tempfile.TemporaryDirectory() as media, tempfile.TemporaryDirectory() as outside:
            video = Path(media) / "test.mp4"
            video.write_bytes(b"test media")
            other = Path(outside) / "test.mp4"
            other.write_bytes(b"bad")
            calls = []
            def mocked(req):
                calls.append(req.method)
                if req.method == "POST":
                    return httpx.Response(200, headers={
                        "Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=1"})
                return httpx.Response(201, json={"id": "video-xyz"})
            async def go():
                async with httpx.AsyncClient(transport=httpx.MockTransport(mocked)) as c:
                    return await publish_owned(c, "youtube", "token", "channel", "Video title",
                                               {"media": {"video_path": str(video), "privacy": "private"}})
            with patch.dict(os.environ, {"TAPAS_MEDIA_ROOT": media}):
                self.assertEqual(require_video_path(str(video)), video)
                with self.assertRaises(PublishConfigurationError):
                    require_video_path(str(other))
                result = self.run_async(go())
            self.assertEqual(result["post_id"], "video-xyz")
            self.assertEqual(calls, ["POST", "PUT"])

    def test_unknown_provider_does_not_publish(self):
        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200))) as c:
                await publish_owned(c, "unknown", "token", "id", "body", {})
        with self.assertRaises(PublishConfigurationError):
            self.run_async(go())


if __name__ == "__main__":
    unittest.main()
