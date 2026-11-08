"""Auto-publish execution layer — Release 1.5 (pure logic).

Ram's decision (8 Nov 2026): "Go further — auto-publish approved queues
without me." The property this creates, stated exactly:

    Nothing publishes without approval. Approved items publish
    automatically.

This module holds the deterministic policy; server.py holds the worker,
the provider HTTP calls and persistence. The policy, in order:

1. THE GATE STAYS. Only approval_queue items with status "approved"
   may ever execute. Expired approvals never execute (the worker moves
   them to "expired" and audits the refusal).
2. ONLY PUBLISH-TYPE ITEMS EXECUTE. A publish item is an approval whose
   action_type is "publish_post", whose platform column names the
   target provider, and whose payload carries actual post text (see
   extract_publish_text). The publication_optimization approvals created
   by publication detection are informational metadata suggestions —
   they are NEVER publish items and must never trigger a post, even if
   approved.
3. IDEMPOTENCY. The worker claims an item atomically
   (approved -> executing) before any provider call, so an item
   executes at most once per claim; terminal states are "executed",
   "blocked_scope" and "execution_failed".
4. HONEST PROVIDER SCOPE. LinkedIn personal-profile text posts
   (w_member_social) and Bluesky (AT Protocol, app password) are the
   live routes; X is attemptable but expected to fail until its write
   scope / API credits exist. YouTube has no upload scope — uploads are
   never attempted. Providers with no posting route on this backend are
   blocked with a named reason, never silently dropped.
5. BOUNDED RETRIES. A failed publish is retried at most
   MAX_ATTEMPTS times with exponential backoff, then parked as
   "execution_failed". Every attempt is audit-logged by the worker.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

PUBLISH_ACTION_TYPE = "publish_post"
INFORMATIONAL_ACTION_TYPES = frozenset({"publication_optimization"})

# Terminal/intermediate approval statuses owned by this layer.
STATUS_EXECUTING = "executing"
STATUS_EXECUTED = "executed"
STATUS_BLOCKED = "blocked_scope"
STATUS_FAILED = "execution_failed"

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_INTERVAL_MINUTES = 5
BACKOFF_BASE_SECONDS = 300

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"

# Providers that can never execute from this backend, with the reason
# recorded on the item and in the audit log. YouTube is scope-blocked,
# not connection-blocked — the distinction matters and is kept.
STATIC_BLOCKED_REASONS = {
    "youtube": ("missing_scope: the connected Google account does not hold "
                "https://www.googleapis.com/auth/youtube.upload; uploads are "
                "never attempted by this backend."),
    "mastodon": ("not_connected_on_this_backend: Mastodon completes only via "
                 "the parked PC bridge (VM-side app registration hangs); no "
                 "Mastodon connection exists on this backend."),
    "instagram": ("not_connected_on_this_backend: the Instagram connection is "
                  "blocked at the consent step; no Instagram connection exists "
                  "on this backend."),
    "spotify": ("not_a_post_route: Spotify is a podcast/audio connection, not "
                "a text-post publishing route, and its connection is parked."),
    "substack": ("no_posting_route: Substack is detection-only here (public "
                 "RSS read); the backend has no Substack posting route."),
    "soundcloud": ("not_connected_on_this_backend: SoundCloud requires a paid "
                   "Artist Pro app registration; no connection exists."),
}

# Platform keys inside a cross-platform "drafts" payload, per target.
_DRAFT_KEYS = {
    "linkedin": "linkedin_post",
    "bluesky": "bluesky_post",
    "mastodon": "mastodon_post",
    "instagram": "instagram_caption",
    "x": "x_thread",
}

_TEXT_FIELDS = ("text", "content", "post_text", "post")


def extract_publish_text(payload: Any, platform: str) -> str | None:
    """Pull the post text out of an approval payload, or None.

    Accepted shapes (first non-empty string wins): the direct fields
    text / content / post_text / post, then a cross-platform "drafts"
    dict keyed per platform (linkedin_post, bluesky_post, ...). For X,
    a drafts list means a thread — only the first post is publishable
    as a single tweet; other platforms join list drafts with a blank
    line. Anything else (including the publication-detection payload
    shape) yields None.
    """
    if not isinstance(payload, dict):
        return None
    for field in _TEXT_FIELDS:
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    drafts = payload.get("drafts")
    if isinstance(drafts, dict):
        key = _DRAFT_KEYS.get((platform or "").lower())
        value = drafts.get(key) if key else None
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            parts = [str(v).strip() for v in value if isinstance(v, str) and str(v).strip()]
            if parts:
                return parts[0] if (platform or "").lower() == "x" else "\n\n".join(parts)
    return None


def classify_item(action_type: str, platform: str, payload: Any) -> dict[str, Any]:
    """Classify an approval_queue row for the auto-publish worker.

    kind: "publish" (executable, text present), "publish_no_text"
    (publish-type but no extractable text — never attempted),
    "informational" (detection metadata — NEVER executes), or "other"
    (any other action type — not this worker's business).
    """
    action = (action_type or "").strip()
    if action in INFORMATIONAL_ACTION_TYPES:
        return {"kind": "informational", "text": None}
    if action != PUBLISH_ACTION_TYPE:
        return {"kind": "other", "text": None}
    text = extract_publish_text(payload, platform)
    if text is None:
        return {"kind": "publish_no_text", "text": None}
    return {"kind": "publish", "text": text}


def backoff_seconds(attempts_done: int) -> int:
    """Exponential backoff before the next retry: 5m, 10m, 20m, ..."""
    return BACKOFF_BASE_SECONDS * (2 ** max(0, attempts_done - 1))


def auto_publish_enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return (env.get("AUTO_PUBLISH_ENABLED") or "true").strip().lower() == "true"


def auto_publish_dry_run(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return (env.get("AUTO_PUBLISH_DRY_RUN") or "false").strip().lower() == "true"


def max_attempts(env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    try:
        return max(1, int(env.get("AUTO_PUBLISH_MAX_ATTEMPTS") or DEFAULT_MAX_ATTEMPTS))
    except ValueError:
        return DEFAULT_MAX_ATTEMPTS


def _scopes_of(connection: dict | None) -> list[str]:
    if not connection:
        return []
    return [s for s in str(connection.get("scopes") or "").replace(",", " ").split() if s]


def provider_readiness(connections: Mapping[str, dict | None],
                       *, bluesky_handle: bool = False,
                       bluesky_app_password: bool = False) -> dict[str, dict[str, Any]]:
    """Per-provider execution readiness, honestly scoped.

    connections maps provider -> its connections-table row (or None).
    status is "ready", "ready_with_warning" (the worker will attempt;
    failure is expected until the named gap is fixed) or "blocked"
    (the worker parks items as blocked_scope with this reason).
    """
    out: dict[str, dict[str, Any]] = {}

    linkedin = connections.get("linkedin")
    if linkedin and linkedin.get("status") == "connected" and "w_member_social" in _scopes_of(linkedin):
        out["linkedin"] = {"status": "ready", "reason": None,
                           "detail": "Personal-profile text posts via w_member_social."}
    elif linkedin and linkedin.get("status") == "connected":
        out["linkedin"] = {"status": "blocked",
                           "reason": "missing_scope: the LinkedIn connection does not hold w_member_social.",
                           "detail": "Reconnect LinkedIn with the Share on LinkedIn product granted."}
    else:
        out["linkedin"] = {"status": "blocked",
                           "reason": "not_connected: no LinkedIn connection on this backend.",
                           "detail": "Connect LinkedIn first."}

    if bluesky_handle and bluesky_app_password:
        out["bluesky"] = {"status": "ready", "reason": None,
                          "detail": "AT Protocol createRecord with the configured app password."}
    else:
        out["bluesky"] = {"status": "blocked",
                          "reason": ("credential_not_configured: Bluesky posting needs an app "
                                     "password (BLUESKY_APP_PASSWORD) alongside BLUESKY_HANDLE; "
                                     "the existing Bluesky setup is read-only public discovery."),
                          "detail": "Create an app password in Bluesky settings and add it to the backend .env."}

    x = connections.get("x")
    if x and x.get("status") == "connected":
        gaps = []
        if "tweet.write" not in _scopes_of(x):
            gaps.append("granted scopes lack tweet.write")
        gaps.append("the account carries $0 API credits (posts return HTTP 402)")
        out["x"] = {"status": "ready_with_warning",
                    "reason": None,
                    "detail": "Worker will attempt posts; failure is expected until fixed: "
                              + "; ".join(gaps) + "."}
    else:
        out["x"] = {"status": "blocked",
                    "reason": "not_connected: no X connection on this backend.",
                    "detail": "Connect X first."}

    for provider, reason in STATIC_BLOCKED_REASONS.items():
        out[provider] = {"status": "blocked", "reason": reason, "detail": reason}
    return out
