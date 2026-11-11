"""Provider capability registry and credential-safe integration health for v1.6.

This module does not claim that a provider is connected merely because an API
key is present. It separates configuration from a successful live handshake.
Provider secrets are only read from the backend environment and are never
returned by status endpoints.

Operational note:
- API adapters must follow each provider's published API and account limits.
- LinkedIn engagement actions are exposed as review/approval tasks, not
  background engagement-pod actions.
- vidIQ and TubeBuddy remain research/analytics links until their vendors
  provide a supported API contract and the account has authorized access.
"""
from __future__ import annotations

import os
from typing import Any

PROVIDER_CATALOGUE: dict[str, dict[str, Any]] = {
    "connectsafely": {
        "label": "ConnectSafely",
        "category": "linkedin_engagement",
        "capabilities": ["account_status", "post_read", "comment_draft", "comment_action_review", "reaction_action_review", "search"],
        "base_url": "https://api.connectsafely.ai",
        "auth_env": ["CONNECTSAFELY_API_KEY"],
        "auth_type": "bearer_api_key",
        "safety": "Actions are not run as pods or unattended comment/reaction campaigns.",
        "verification": "GET /linkedin/account",
    },
    "magicpost": {
        "label": "MagicPost",
        "category": "linkedin_content",
        "capabilities": ["drafts", "post_schedule", "post_publish", "metrics"],
        "base_url": "https://api.magicpost.in/api/v1",
        "auth_env": ["MAGICPOST_API_KEY"],
        "auth_type": "bearer_api_key",
        "safety": "Use only for the account/workspace authorized by the key.",
        "verification": "GET /posts?workspace_id=<workspace_id>&status=all",
    },
    "supergrow": {
        "label": "Supergrow",
        "category": "linkedin_content",
        "capabilities": ["workspaces", "posts", "post_schedule", "post_publish", "analytics"],
        "base_url": "https://external-api.supergrow.ai/api/v1/external",
        "auth_env": ["SUPERGROW_API_KEY"],
        "auth_type": "x_api_key_or_oauth",
        "safety": "Use approved workspace/account context; no scraped browser session.",
        "verification": "GET /workspaces",
    },
    "vidiq": {
        "label": "vidIQ",
        "category": "youtube_research",
        "capabilities": ["keyword_research", "topic_ideas", "video_optimization", "competitor_research"],
        "base_url": None,
        "auth_env": ["VIDIQ_API_KEY"],
        "auth_type": "vendor_api_not_verified",
        "safety": "Do not scrape the vidIQ application or claim live sync until a supported API is supplied.",
        "verification": "Vendor-supported API contract required; link-out fallback only.",
    },
    "tubebuddy": {
        "label": "TubeBuddy",
        "category": "youtube_research",
        "capabilities": ["keyword_research", "tag_research", "thumbnail_testing", "channel_optimization"],
        "base_url": None,
        "auth_env": ["TUBEBUDDY_API_KEY"],
        "auth_type": "vendor_api_not_verified",
        "safety": "Do not scrape the TubeBuddy application or claim live sync until a supported API is supplied.",
        "verification": "Vendor-supported API contract required; link-out fallback only.",
    },
}


def _configured(env: dict[str, str], keys: list[str]) -> bool:
    return all(bool(env.get(key, "").strip()) for key in keys)


def provider_status(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Return safe provider setup status without returning credential values."""
    source = os.environ if env is None else env
    result: dict[str, Any] = {}
    for key, spec in PROVIDER_CATALOGUE.items():
        configured = _configured(source, spec["auth_env"])
        verified_api = spec["base_url"] is not None
        # Credentials are not a successful connection. The status endpoint
        # intentionally requires the adapter's explicit live probe to promote
        # this to connected.
        result[key] = {
            "label": spec["label"],
            "category": spec["category"],
            "status": "configured_unverified" if configured and verified_api
                      else "credential_missing" if not configured
                      else "unsupported_api",
            "configured": configured,
            "connected": False,
            "capabilities": list(spec["capabilities"]),
            "auth_type": spec["auth_type"],
            "verification": spec["verification"],
            "safety": spec["safety"],
        }
    return result


def validate_provider_action(provider: str, action: str) -> dict[str, Any]:
    """Fail closed when a provider/action pair is not in the capability map."""
    spec = PROVIDER_CATALOGUE.get((provider or "").lower())
    if spec is None:
        return {"allowed": False, "reason": "unknown_provider"}
    if action not in spec["capabilities"]:
        return {"allowed": False, "reason": "unsupported_capability"}
    if provider.lower() in {"vidiq", "tubebuddy"}:
        return {"allowed": False, "reason": "vendor_api_contract_not_verified"}
    if provider.lower() == "connectsafely" and action in {
        "comment_action_review", "reaction_action_review"
    }:
        return {
            "allowed": True,
            "mode": "human_review",
            "reason": "Create a review task; require a deliberate user action before dispatch.",
        }
    return {"allowed": True, "mode": "provider_api"}
