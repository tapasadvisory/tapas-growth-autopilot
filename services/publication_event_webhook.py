"""Signed publication-event delivery for approved external distribution workflows.

This module does NOT automate likes, comments, engagement pods, or coordinated
engagement. It emits a factual post-published event to an operator-owned
distribution/analytics endpoint. The receiving system must independently comply
with each platform's terms and privacy rules.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("tapas.publication_events")


def build_publication_event(
    *, post_id: str, platform: str, post_url: str | None, approval_id: int
) -> dict[str, Any]:
    """Build a minimal, non-personal-data publication event."""
    if not post_id or not platform:
        raise ValueError("post_id and platform are required")
    return {
        "event": "post.published",
        "event_version": "1",
        "occurred_at": int(time.time()),
        "platform": platform.lower(),
        "post_id": post_id,
        "post_url": post_url or "",
        "approval_id": int(approval_id),
    }


def _validated_endpoint(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Publication event endpoint must be an HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("Endpoint URL must not contain embedded credentials")
    return raw_url


def sign_payload(payload: dict[str, Any], secret: str) -> tuple[bytes, str]:
    """Canonical JSON + HMAC-SHA256 signature for receiver verification."""
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return body, signature


async def dispatch_publication_event(
    *, post_id: str, platform: str, post_url: str | None, approval_id: int,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Deliver an opt-in, signed event; never send engagement instructions."""
    if os.getenv("PUBLICATION_EVENTS_ENABLED", "false").strip().lower() != "true":
        return {"status": "skipped", "reason": "publication_events_disabled"}
    endpoint = os.getenv("PUBLICATION_EVENTS_WEBHOOK_URL", "").strip()
    secret = os.getenv("PUBLICATION_EVENTS_WEBHOOK_SECRET", "").strip()
    if not endpoint or not secret:
        return {"status": "skipped", "reason": "webhook_endpoint_or_secret_missing"}
    try:
        endpoint = _validated_endpoint(endpoint)
        payload = build_publication_event(
            post_id=post_id, platform=platform, post_url=post_url, approval_id=approval_id
        )
        body, signature = sign_payload(payload, secret)
    except ValueError as exc:
        return {"status": "failed", "reason": str(exc)}
    headers = {
        "Content-Type": "application/json",
        "X-TAPAS-Event": "post.published",
        "X-TAPAS-Signature": f"sha256={signature}",
        "X-TAPAS-Approval-ID": str(approval_id),
    }
    try:
        async with httpx.AsyncClient(timeout=8.0, transport=transport) as client:
            response = await client.post(endpoint, content=body, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Publication event delivery failed approval=%s error=%s", approval_id, type(exc).__name__)
        return {"status": "failed", "reason": type(exc).__name__}
    logger.info("Publication event delivered approval=%s platform=%s", approval_id, platform)
    return {"status": "delivered", "http_status": response.status_code, "event": "post.published"}
