from __future__ import annotations

import hashlib
import hmac
import json
import unittest

from services.publication_event_webhook import (
    _validated_endpoint,
    build_publication_event,
    sign_payload,
)


class PublicationEventWebhookTests(unittest.TestCase):
    def test_event_is_publication_notice_only(self):
        event = build_publication_event(
            post_id="urn:li:share:123",
            platform="linkedin",
            post_url="https://www.linkedin.com/feed/update/123",
            approval_id=42,
        )
        self.assertEqual(event["event"], "post.published")
        self.assertEqual(event["approval_id"], 42)
        self.assertNotIn("actions", event)
        self.assertNotIn("comment_pool", event)

    def test_signature_verifies_canonical_body(self):
        payload = {"event": "post.published", "post_id": "abc"}
        secret = "test-secret"
        body, signature = sign_payload(payload, secret)
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertEqual(signature, expected)
        self.assertEqual(json.loads(body), payload)

    def test_endpoint_requires_https(self):
        with self.assertRaises(ValueError):
            _validated_endpoint("http://example.com/hook")
        self.assertEqual(_validated_endpoint("https://example.com/hook"),
                         "https://example.com/hook")


if __name__ == "__main__":
    unittest.main()
