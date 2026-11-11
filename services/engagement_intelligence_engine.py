"""Engagement Intelligence: post-publish notifications and human review tasks.

This service sends factual publication events to an operator-owned HTTPS
webhook. It never likes, comments, follows, or coordinates engagement.
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("tapas.engagement_intelligence")


def event_id(platform: str, post_id: str, approval_id: int | str) -> str:
    key = f"{platform.lower()}:{post_id}:{approval_id}"
    return hashlib.sha256(key.encode()).hexdigest()


def build_intelligence_payload(
    *, platform: str, post_id: str, post_url: str | None,
    approval_id: int | str,
) -> dict[str, Any]:
    if not platform.strip() or not post_id.strip():
        raise ValueError("platform_and_post_id_required")
    eid = event_id(platform, post_id, approval_id)
    return {
        "event": "engagement.intelligence.post_published",
        "event_id": eid,
        "platform": platform.lower(),
        "post_id": post_id,
        "post_url": post_url or "",
        "approval_id": str(approval_id),
        "workflow": {
            "comment_suggestions": "human_review_only",
            "community_notifications": "enabled_if_receiver_supports",
            "reactions_and_comments": "human_action_required",
            "engagement_pods": "prohibited",
        },
    }


async def dispatch_engagement_intelligence(
    *, platform: str, post_id: str, post_url: str | None,
    approval_id: int | str, transport: httpx.AsyncBaseTransport | None = None,
    attempts: int = 3, timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Send a retryable, idempotent notification; no social action is executed."""
    if os.getenv("ENGAGEMENT_INTELLIGENCE_ENABLED", "false").strip().lower() != "true":
        return {"status": "skipped", "reason": "engagement_intelligence_disabled"}
    endpoint = os.getenv("ENGAGEMENT_INTELLIGENCE_WEBHOOK_URL", "").strip()
    secret = os.getenv("ENGAGEMENT_INTELLIGENCE_WEBHOOK_SECRET", "").strip()
    if not endpoint or not secret:
        return {"status": "skipped", "reason": "webhook_or_secret_missing"}
    try:
        payload = build_intelligence_payload(
            platform=platform, post_id=post_id, post_url=post_url, approval_id=approval_id
        )
        # Reuse the existing canonical HMAC implementation.
        from services.publication_event_webhook import _validated_endpoint, sign_payload
        endpoint = _validated_endpoint(endpoint)
        body, signature = sign_payload(payload, secret)
    except ValueError as exc:
        return {"status": "failed", "reason": str(exc)}
    headers = {
        "Content-Type": "application/json",
        "X-TAPAS-Event": payload["event"],
        "X-TAPAS-Signature": f"sha256={signature}",
        "Idempotency-Key": payload["event_id"],
    }
    last_error = "unknown"
    for attempt in range(1, max(1, attempts) + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, transport=transport) as client:
                response = await client.post(endpoint, content=body, headers=headers)
                response.raise_for_status()
            return {
                "status": "delivered", "http_status": response.status_code,
                "event_id": payload["event_id"], "attempt": attempt,
            }
        except httpx.HTTPError as exc:
            last_error = type(exc).__name__
            logger.warning("Engagement intelligence delivery failed event=%s attempt=%s error=%s",
                           payload["event_id"], attempt, last_error)
    return {"status": "failed", "event_id": payload["event_id"],
            "attempts": max(1, attempts), "reason": last_error}
