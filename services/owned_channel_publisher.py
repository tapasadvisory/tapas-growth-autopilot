"""Official owned-channel publishing adapters, called only after content approval.

No social-login cookies, browser automation, engagement pods or fabricated views.
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx

GRAPH_VERSION = os.getenv("INSTAGRAM_GRAPH_VERSION", "v25.0")
THREADS_ROOT = "https://graph.threads.net/v1.0"


class PublishConfigurationError(ValueError):
    """Invalid publishing input or provider response; no credentials in errors."""


def require_media_url(url: str) -> str:
    """Restrict Instagram media to a preapproved HTTPS media host."""
    if not isinstance(url, str) or len(url) > 2048:
        raise PublishConfigurationError("media URL required")
    allowed = {
        x.strip().lower() for x in os.getenv("TAPAS_MEDIA_HOSTS", "").split(",")
        if x.strip()
    }
    try:
        parsed = urlsplit(url)
        ok = parsed.scheme == "https" and parsed.hostname in allowed and parsed.port in (None, 443)
    except ValueError:
        ok = False
    if not ok or not allowed or parsed.username or parsed.password or "\\" in url:
        raise PublishConfigurationError("HTTPS media URL must use an approved TAPAS_MEDIA_HOSTS domain")
    return url


def require_video_path(raw: str) -> Path:
    """Do not permit local file paths outside TAPAS_MEDIA_ROOT."""
    root_raw = os.getenv("TAPAS_MEDIA_ROOT", "").strip()
    if not root_raw:
        raise PublishConfigurationError("TAPAS_MEDIA_ROOT is not configured")
    try:
        root = Path(root_raw).resolve(strict=True)
        path = Path(str(raw)).resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise PublishConfigurationError("Approved video file not found") from exc
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() not in {".mp4", ".mov", ".webm"}:
        raise PublishConfigurationError("Video must be an approved MP4, MOV, or WebM under TAPAS_MEDIA_ROOT")
    if not 0 < path.stat().st_size <= int(os.getenv("TAPAS_MAX_UPLOAD_BYTES", "524288000")):
        raise PublishConfigurationError("Video exceeds configured upload size or is empty")
    return path


def _text(text: str, limit: int) -> str:
    if not isinstance(text, str) or not text.strip() or len(text) > limit:
        raise PublishConfigurationError(f"Text must contain 1 to {limit} characters")
    return text.strip()


async def _json(response: httpx.Response) -> dict:
    if response.status_code >= 400:
        raise PublishConfigurationError(f"Provider refused operation (HTTP {response.status_code})")
    try:
        data = response.json()
    except ValueError as exc:
        raise PublishConfigurationError("Provider returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise PublishConfigurationError("Provider returned non-object JSON")
    return data


async def publish_threads(client: httpx.AsyncClient, token: str, text: str) -> dict:
    """Create and publish a Threads text post through authorized Graph API."""
    headers = {"Authorization": f"Bearer {token}"}
    created = await _json(await client.post(
        f"{THREADS_ROOT}/me/threads", headers=headers,
        data={"media_type": "TEXT", "text": _text(text, 500)}
    ))
    if not created.get("id"):
        raise PublishConfigurationError("Threads did not return a creation ID")
    published = await _json(await client.post(
        f"{THREADS_ROOT}/me/threads_publish", headers=headers,
        data={"creation_id": created["id"]}
    ))
    if not published.get("id"):
        raise PublishConfigurationError("Threads did not confirm post ID")
    return {"post_id": str(published["id"]), "url": None}


async def publish_instagram_image(client: httpx.AsyncClient, token: str,
                                  account_id: str, caption: str, image_url: str) -> dict:
    """Instagram Professional image publication with the two-step API."""
    if not str(account_id).isdigit():
        raise PublishConfigurationError("Instagram user ID is unavailable")
    base = f"https://graph.instagram.com/{GRAPH_VERSION}"
    headers = {"Authorization": f"Bearer {token}"}
    created = await _json(await client.post(
        f"{base}/{account_id}/media", headers=headers,
        data={"image_url": require_media_url(image_url), "caption": _text(caption, 2200)}
    ))
    if not created.get("id"):
        raise PublishConfigurationError("Instagram did not return a container ID")
    published = await _json(await client.post(
        f"{base}/{account_id}/media_publish", headers=headers,
        data={"creation_id": created["id"]}
    ))
    if not published.get("id"):
        raise PublishConfigurationError("Instagram did not confirm post ID")
    return {"post_id": str(published["id"]), "url": None}


async def publish_youtube_video(client: httpx.AsyncClient, token: str, media_path: str,
                                title: str, description: str, privacy: str = "private") -> dict:
    """Upload an approved local video using YouTube's resumable initialization."""
    path = require_video_path(media_path)
    title = _text(title, 100)
    if not isinstance(description, str) or len(description) > 5000:
        raise PublishConfigurationError("Invalid YouTube description")
    if privacy not in {"private", "unlisted", "public"}:
        raise PublishConfigurationError("Invalid YouTube privacy level")
    size = path.stat().st_size
    mime = mimetypes.guess_type(path.name)[0] or "video/mp4"
    meta = {
        "snippet": {"title": title, "description": description, "categoryId": "22"},
        "status": {"privacyStatus": privacy},
    }
    init = await client.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        headers={
            "Authorization": f"Bearer {token}", "X-Upload-Content-Type": mime,
            "X-Upload-Content-Length": str(size), "Content-Type": "application/json",
        },
        params={"part": "snippet,status", "uploadType": "resumable"},
        json=meta,
    )
    if init.status_code >= 400:
        raise PublishConfigurationError(f"YouTube upload initialization refused (HTTP {init.status_code})")
    location = init.headers.get("Location", "")
    parsed = urlsplit(location)
    if (parsed.scheme != "https" or parsed.hostname != "www.googleapis.com"
            or not parsed.path.startswith("/upload/youtube/v3/videos")
            or parsed.username or parsed.password):
        raise PublishConfigurationError("Untrusted YouTube upload endpoint")

    async def chunks():
        with path.open("rb") as video:
            while True:
                chunk = video.read(262144)
                if not chunk:
                    return
                yield chunk

    response = await client.put(
        location,
        headers={"Authorization": f"Bearer {token}", "Content-Length": str(size),
                 "Content-Type": mime},
        content=chunks(),
    )
    result = await _json(response)
    if not result.get("id"):
        raise PublishConfigurationError("YouTube did not return a video ID")
    return {"post_id": str(result["id"]), "url": f"https://www.youtube.com/watch?v={result['id']}"}


async def publish_owned(client: httpx.AsyncClient, provider: str, token: str,
                        account_id: str, text: str, payload: dict) -> dict:
    """Dispatch exact content previously approved in the existing queue."""
    if provider == "threads":
        return await publish_threads(client, token, text)
    media = payload.get("media") or {}
    if provider == "instagram":
        return await publish_instagram_image(client, token, account_id, text, media.get("image_url", ""))
    if provider == "youtube":
        return await publish_youtube_video(
            client, token, media.get("video_path", ""), media.get("title") or text,
            media.get("description") or text, media.get("privacy") or "private"
        )
    raise PublishConfigurationError("Unsupported owned-channel publisher")
