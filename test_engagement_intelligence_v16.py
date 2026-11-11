import asyncio
import json
import os
import unittest
from unittest import mock

import httpx

from services.engagement_intelligence_engine import (
    build_intelligence_payload, dispatch_engagement_intelligence, event_id,
)


class PayloadTests(unittest.TestCase):
    def test_payload_is_human_review_only_and_stable(self):
        a = build_intelligence_payload(platform="LinkedIn", post_id="urn:post:1", post_url="https://example.test/p", approval_id=4)
        b = build_intelligence_payload(platform="linkedin", post_id="urn:post:1", post_url="https://example.test/p", approval_id=4)
        self.assertEqual(a["event_id"], b["event_id"])
        self.assertEqual(a["event_id"], event_id("linkedin", "urn:post:1", 4))
        self.assertEqual(a["workflow"]["comment_suggestions"], "human_review_only")
        self.assertEqual(a["workflow"]["reactions_and_comments"], "human_action_required")
        self.assertEqual(a["workflow"]["engagement_pods"], "prohibited")

    def test_payload_requires_platform_and_post(self):
        with self.assertRaises(ValueError):
            build_intelligence_payload(platform="", post_id="p", post_url=None, approval_id=1)


class DispatchTests(unittest.TestCase):
    def test_disabled_returns_without_dispatch(self):
        for enabled in ["false", "0", ""]:
            with self.subTest(enabled=enabled):
                with mock.patch.dict(os.environ, {"ENGAGEMENT_INTELLIGENCE_ENABLED": enabled}):
                    result = asyncio.run(dispatch_engagement_intelligence(
                        platform="linkedin", post_id="p", post_url=None, approval_id=1,
                    ))
                self.assertEqual(result["status"], "skipped")

    def test_successful_webhook_has_signature_and_idempotency(self):
        env = {
            "ENGAGEMENT_INTELLIGENCE_ENABLED": "true",
            "ENGAGEMENT_INTELLIGENCE_WEBHOOK_URL": "https://hooks.example.test/events",
            "ENGAGEMENT_INTELLIGENCE_WEBHOOK_SECRET": "test-secret",
        }
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(202)

        transport = httpx.MockTransport(handler)
        with mock.patch.dict(os.environ, env):
            result = asyncio.run(dispatch_engagement_intelligence(
                platform="linkedin", post_id="p1", post_url="https://linkedin.test/p1",
                approval_id=42, transport=transport,
            ))
        self.assertEqual(result["status"], "delivered")
        self.assertEqual(seen[0].headers["Idempotency-Key"], result["event_id"])
        self.assertTrue(seen[0].headers["X-TAPAS-Signature"].startswith("sha256="))
        self.assertEqual(json.loads(seen[0].content)["post_id"], "p1")

    def test_webhook_retries_and_reports_failure(self):
        env = {
            "ENGAGEMENT_INTELLIGENCE_ENABLED": "true",
            "ENGAGEMENT_INTELLIGENCE_WEBHOOK_URL": "https://hooks.example.test/events",
            "ENGAGEMENT_INTELLIGENCE_WEBHOOK_SECRET": "test-secret",
        }
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(503)

        with mock.patch.dict(os.environ, env):
            result = asyncio.run(dispatch_engagement_intelligence(
                platform="x", post_id="x-1", post_url=None, approval_id=8,
                transport=httpx.MockTransport(handler), attempts=3,
            ))
        self.assertEqual(len(calls), 3)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["attempts"], 3)

    def test_rejects_non_https_webhook(self):
        env = {
            "ENGAGEMENT_INTELLIGENCE_ENABLED": "true",
            "ENGAGEMENT_INTELLIGENCE_WEBHOOK_URL": "http://unsafe.test",
            "ENGAGEMENT_INTELLIGENCE_WEBHOOK_SECRET": "secret",
        }
        with mock.patch.dict(os.environ, env):
            result = asyncio.run(dispatch_engagement_intelligence(
                platform="x", post_id="p", post_url=None, approval_id=1,
            ))
        self.assertEqual(result["status"], "failed")


if __name__ == "__main__":
    unittest.main()
