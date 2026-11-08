"""Publication detection + optimization — Release 1.3.

Ported, additively, from the external "v1.3 Gemini Core" ZIP after audit
(8 Nov 2026). What was taken: the Substack RSS detector concept, the
optimizer's enriched output fields (answer_snippet, risk_flags,
confidence, entity_map, hook_options) and its no-promises system prompt.
What was NOT taken: the parallel FastAPI app, the second SQLAlchemy
database, static env-token provider auth, the Google Ads / paid-promotion
policy actions, and the uvicorn[standard] requirement.

Everything here runs on the existing spine: Gemini via
services.gemini_client (fail-closed), persistence in the existing sqlite
store (server.py owns the table), approvals via the existing queue.

Release 1.4 adds Apple Podcasts episode detection via the public
iTunes lookup API (no credentials). NOTE on Spotify: the podcast's
Spotify episodes are published from the same Anchor RSS feed as Apple
Podcasts, but Spotify-side detection waits on the parked Spotify
connection — this VM's egress refuses Spotify's token exchange, so no
Spotify connection is attempted from here. Apple detection covers the
episode register in the meantime.
"""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from services.gemini_client import gemini_generate_json

PLATFORMS = ("linkedin", "youtube", "substack", "apple_podcasts")

_NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "atom": "http://www.w3.org/2005/Atom",
}

SYSTEM_PRINCIPLES = """You are TAPAS Growth Intelligence. Produce truthful, useful platform optimization.
Do not promise rankings, virality, views, or citations. No keyword stuffing, fake claims,
fake engagement, misleading titles, or fabricated sources. Optimize for human usefulness,
search intent, expertise, clarity, answerability, and platform policies.
AEO = concise answer-ready passages and explicit question coverage.
SEO = search intent, natural keywords, title/description structure.
GEO = entity clarity, authoritative context, source transparency, citation-ready claims.
Mark uncertain claims in risk_flags. CHANGEReadyX is written CHANGEReadyX\u2122, never with a registered mark."""


def content_hash(title: str, text: str, url: str) -> str:
    return hashlib.sha256((title + text + str(url)).encode()).hexdigest()


def _strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
    except (TypeError, ValueError):
        pass
    return None


def parse_rss_feed(xml_text: str, platform: str = "substack") -> list[dict[str, Any]]:
    """Parse an RSS 2.0 feed (Substack-compatible) into publication dicts."""
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []
    out: list[dict[str, Any]] = []
    for item in channel.findall("item"):
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or "").strip() or link
        if not link and not guid:
            continue
        title = (item.findtext("title") or "").strip()
        body = item.findtext("content:encoded", namespaces=_NS) or item.findtext("description") or ""
        text = _strip_html(body)[:6000]
        out.append({
            "platform": platform,
            "external_id": guid,
            "url": link or guid,
            "title": title,
            "text": text,
            "published_at": _parse_date(item.findtext("pubDate")),
            "content_hash": content_hash(title, text, link or guid),
        })
    return out


async def fetch_feed_text(feed_url: str, timeout: float = 60.0) -> str:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(feed_url, headers={"User-Agent": "TAPAS-Growth-Autopilot/1.3"})
        response.raise_for_status()
        return response.text


OPTIMIZATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "answer_snippet": {"type": "string"},
        "entity_map": {"type": "array", "items": {"type": "string"}},
        "schema_recommendations": {"type": "array", "items": {"type": "string"}},
        "geo_recommendations": {"type": "array", "items": {"type": "string"}},
        "audience": {"type": "string"},
        "hook_options": {"type": "array", "items": {"type": "string"}},
        "cta": {"type": "string"},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
    "required": ["title", "description", "answer_snippet", "risk_flags", "confidence"],
}


# ---------------------------------------------------------------------------
# Apple Podcasts detection (Release 1.4)
#
# The show "Ram's CHANGEReadyX™ from TAPAS Advisory" (Apple show id
# 6831708010) is listed through the public iTunes lookup API, which needs
# no credentials. Episodes register with platform "apple_podcasts" and
# flow through the same register → Gemini optimization → pending-approval
# path as Substack/YouTube (server.py owns that path).
# ---------------------------------------------------------------------------

APPLE_PODCAST_SHOW_ID = 6831708010
APPLE_LOOKUP_URL = (
    "https://itunes.apple.com/lookup?id={show_id}&entity=podcastEpisode&limit=50"
)


def parse_itunes_episodes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse an iTunes lookup response into publication dicts.

    The response mixes one collection record (the show itself) with
    episode records; only episodes are returned. external_id is the
    episode's trackId, falling back to its guid — the register's
    UNIQUE(platform, external_id) makes re-runs idempotent.
    """
    out: list[dict[str, Any]] = []
    for entry in payload.get("results") or []:
        if entry.get("wrapperType") != "podcastEpisode":
            continue
        external_id = entry.get("trackId") or entry.get("episodeGuid") or entry.get("guid")
        url = entry.get("trackViewUrl") or ""
        if external_id is None or not url:
            continue
        title = (entry.get("trackName") or "").strip()
        text = _strip_html(entry.get("description") or entry.get("shortDescription") or "")[:6000]
        out.append({
            "platform": "apple_podcasts",
            "external_id": str(external_id),
            "url": url,
            "title": title,
            "text": text,
            "published_at": entry.get("releaseDate"),
            "content_hash": content_hash(title, text, url),
        })
    return out


async def fetch_itunes_lookup(show_id: int = APPLE_PODCAST_SHOW_ID, timeout: float = 60.0) -> dict[str, Any]:
    url = APPLE_LOOKUP_URL.format(show_id=show_id)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": "TAPAS-Growth-Autopilot/1.4"})
        response.raise_for_status()
        return json.loads(response.text)


async def optimize_publication(pub: dict[str, Any]) -> dict[str, Any]:
    """Gemini AEO/SEO/GEO optimization for one publication.

    Fail-closed: raises GeminiNotConfigured when no key is configured
    (the API layer answers 503), exactly like the other 1.1 engines.
    """
    prompt = f"""{SYSTEM_PRINCIPLES}

Publication:
platform={pub.get('platform')}
url={pub.get('url')}
title={pub.get('title')}
text={(pub.get('text') or '')[:12000]}

Return JSON with: title, description, keywords (8-15), hashtags (0-5),
answer_snippet (40-80 words), entity_map (named entities/topics),
schema_recommendations (only valid web schema suggestions; never claim a
platform supports them natively), geo_recommendations (5 practical
generative-answer discoverability actions), audience, hook_options (3),
cta, risk_flags (uncertain or unverifiable claims; empty list if none),
confidence (0-1)."""
    result = await gemini_generate_json(prompt, OPTIMIZATION_SCHEMA)
    if not isinstance(result, dict):
        raise ValueError("Gemini returned a non-object optimization")
    result.setdefault("risk_flags", [])
    result.setdefault("confidence", 0.0)
    return result
