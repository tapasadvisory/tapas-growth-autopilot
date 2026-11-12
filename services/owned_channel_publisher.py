"""Official owned-channel publishing adapters, called only after content approval.

No social-login cookies, browser automation, engagement pods or fabricated views.
"""
from __future__ import annotations

import asyncio
import mimetypes
import os
import time
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


async def _recent_threads_match(client: httpx.AsyncClient, headers: dict, text: str) -> dict | None:
    """Find an identical recent Threads post (retry dedupe; fails closed)."""
    data = await _json(await client.get(
        f"{THREADS_ROOT}/me/threads", headers=headers,
        params={"fields": "id,text", "limit": 25}))
    for item in data.get("data") or []:
        if isinstance(item, dict) and item.get("id") and str(item.get("text") or "").strip() == text.strip():
            return {"post_id": str(item["id"]), "url": None, "deduplicated": True}
    return None


async def publish_threads(client: httpx.AsyncClient, token: str, text: str,
                          retry_check: bool = False) -> dict:
    """Create and publish a Threads text post through authorized Graph API."""
    headers = {"Authorization": f"Bearer {token}"}
    text = _text(text, 500)
    if retry_check:
        found = await _recent_threads_match(client, headers, text)
        if found:
            return found
    created = await _json(await client.post(
        f"{THREADS_ROOT}/me/threads", headers=headers,
        data={"media_type": "TEXT", "text": text}
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


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


async def _await_container_ready(client: httpx.AsyncClient, base: str, headers: dict,
                                 container_id: str) -> None:
    """Poll an Instagram media container until FINISHED; fail honestly otherwise."""
    timeout = _float_env("TAPAS_IG_POLL_TIMEOUT_SECONDS", 120.0)
    interval = _float_env("TAPAS_IG_POLL_INTERVAL_SECONDS", 3.0)
    deadline = time.monotonic() + timeout
    while True:
        data = await _json(await client.get(
            f"{base}/{container_id}", headers=headers, params={"fields": "status_code"}))
        status = str(data.get("status_code") or "")
        if status == "FINISHED":
            return
        if status in {"ERROR", "EXPIRED"}:
            raise PublishConfigurationError(f"Instagram container {status.lower()} before publish")
        if time.monotonic() >= deadline:
            raise PublishConfigurationError("Instagram container not ready before timeout")
        await asyncio.sleep(interval)


async def _recent_instagram_match(client: httpx.AsyncClient, base: str, headers: dict,
                                  account_id: str, caption: str) -> dict | None:
    """Find an identical recent Instagram media item (retry dedupe; fails closed)."""
    data = await _json(await client.get(
        f"{base}/{account_id}/media", headers=headers,
        params={"fields": "id,caption", "limit": 25}))
    for item in data.get("data") or []:
        if isinstance(item, dict) and item.get("id") and str(item.get("caption") or "").strip() == caption.strip():
            return {"post_id": str(item["id"]), "url": None, "deduplicated": True}
    return None


async def publish_instagram_image(client: httpx.AsyncClient, token: str,
                                  account_id: str, caption: str, image_url: str,
                                  retry_check: bool = False) -> dict:
    """Instagram Professional image publication with the two-step API."""
    if not str(account_id).isdigit():
        raise PublishConfigurationError("Instagram user ID is unavailable")
    base = f"https://graph.instagram.com/{GRAPH_VERSION}"
    headers = {"Authorization": f"Bearer {token}"}
    caption = _text(caption, 2200)
    if retry_check:
        found = await _recent_instagram_match(client, base, headers, account_id, caption)
        if found:
            return found
    created = await _json(await client.post(
        f"{base}/{account_id}/media", headers=headers,
        data={"image_url": require_media_url(image_url), "caption": caption}
    ))
    if not created.get("id"):
        raise PublishConfigurationError("Instagram did not return a container ID")
    await _await_container_ready(client, base, headers, str(created["id"]))
    published = await _json(await client.post(
        f"{base}/{account_id}/media_publish", headers=headers,
        data={"creation_id": created["id"]}
    ))
    if not published.get("id"):
        raise PublishConfigurationError("Instagram did not confirm post ID")
    return {"post_id": str(published["id"]), "url": None}


async def _recent_youtube_match(client: httpx.AsyncClient, headers: dict, title: str) -> dict | None:
    """Find a recent upload with the exact title (retry dedupe; fails closed)."""
    channels = await _json(await client.get(
        "https://www.googleapis.com/youtube/v3/channels", headers=headers,
        params={"part": "contentDetails", "mine": "true"}))
    items = channels.get("items") or []
    if not items:
        return None
    uploads = (((items[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads"))
    if not uploads:
        return None
    feed = await _json(await client.get(
        "https://www.googleapis.com/youtube/v3/playlistItems", headers=headers,
        params={"part": "snippet", "playlistId": uploads, "maxResults": 25}))
    for item in feed.get("items") or []:
        snippet = item.get("snippet") or {}
        video_id = (snippet.get("resourceId") or {}).get("videoId")
        if video_id and str(snippet.get("title") or "").strip() == title.strip():
            return {"post_id": str(video_id),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "deduplicated": True}
    return None


_UPLOAD_CHUNK = 8 * 1024 * 1024  # resumable protocol: chunks are 256 KiB multiples


def _range_next(response: httpx.Response) -> int:
    """Next byte offset from a 308 Range header ('bytes=0-N' -> N+1)."""
    rng = response.headers.get("Range", "")
    if rng.startswith("bytes=") and "-" in rng:
        try:
            return int(rng.split("-", 1)[1]) + 1
        except ValueError:
            return 0
    return 0


async def _upload_resumable(client: httpx.AsyncClient, session_uri: str, path: Path,
                            size: int, mime: str, token: str) -> dict:
    """PUT the file in chunks; on interruption, query the session and resume
    from the byte offset YouTube has committed, so a retry never restarts
    (or duplicates) a partially received upload."""
    auth = {"Authorization": f"Bearer {token}"}
    offset = 0
    recoveries = 0
    with path.open("rb") as video:
        while offset < size:
            video.seek(offset)
            chunk = video.read(min(_UPLOAD_CHUNK, size - offset))
            end = offset + len(chunk) - 1
            try:
                resp = await client.put(
                    session_uri,
                    headers={**auth, "Content-Type": mime, "Content-Length": str(len(chunk)),
                             "Content-Range": f"bytes {offset}-{end}/{size}"},
                    content=chunk)
            except httpx.TransportError:
                resp = None
            if resp is not None and resp.status_code in (200, 201):
                return await _json(resp)
            if resp is not None and resp.status_code == 308:
                offset = _range_next(resp) or (end + 1)
                continue
            if resp is not None and 400 <= resp.status_code < 500:
                raise PublishConfigurationError(f"YouTube upload refused (HTTP {resp.status_code})")
            recoveries += 1
            if recoveries > 3:
                raise PublishConfigurationError("YouTube upload interrupted repeatedly; session abandoned")
            try:
                status = await client.put(
                    session_uri,
                    headers={**auth, "Content-Length": "0", "Content-Range": f"bytes */{size}"},
                    content=b"")
            except httpx.TransportError:
                continue
            if status.status_code in (200, 201):
                return await _json(status)
            if status.status_code == 308:
                offset = _range_next(status)
                continue
            raise PublishConfigurationError(f"YouTube upload failed (HTTP {status.status_code})")
    raise PublishConfigurationError("YouTube upload ended without a video resource")


async def publish_youtube_video(client: httpx.AsyncClient, token: str, media_path: str,
                                title: str, description: str, privacy: str = "private",
                                retry_check: bool = False) -> dict:
    """Upload an approved local video using YouTube's resumable protocol."""
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
    if retry_check:
        # Before opening a new upload session, adopt an identical earlier
        # upload whose acknowledgement was lost.
        found = await _recent_youtube_match(
            client, {"Authorization": f"Bearer {token}"}, title)
        if found:
            return found
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

    result = await _upload_resumable(client, location, path, size, mime, token)
    if not result.get("id"):
        raise PublishConfigurationError("YouTube did not return a video ID")
    return {"post_id": str(result["id"]), "url": f"https://www.youtube.com/watch?v={result['id']}"}


async def publish_owned(client: httpx.AsyncClient, provider: str, token: str,
                        account_id: str, text: str, payload: dict) -> dict:
    """Dispatch exact content previously approved in the existing queue."""
    retry_check = bool(payload.get("retry_check"))
    if provider == "threads":
        return await publish_threads(client, token, text, retry_check=retry_check)
    media = payload.get("media") or {}
    if provider == "instagram":
        return await publish_instagram_image(client, token, account_id, text, media.get("image_url", ""),
                                             retry_check=retry_check)
    if provider == "youtube":
        return await publish_youtube_video(
            client, token, media.get("video_path", ""), media.get("title") or text,
            media.get("description") or text, media.get("privacy") or "private",
            retry_check=retry_check
        )
    raise PublishConfigurationError("Unsupported owned-channel publisher")
