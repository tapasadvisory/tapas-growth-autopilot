"""Shared Gemini access for the Release 1.1 service engines.

Follows the v1 pattern in server.py exactly: the API key comes from the
GEMINI_API_KEY environment variable, the model from GEMINI_MODEL, and the
key is sent in the ``x-goog-api-key`` header — never in the URL. Access is
fail-closed: with no key configured, callers get GeminiNotConfigured and
the API layer answers HTTP 503, mirroring /api/ai/comments.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx


class GeminiNotConfigured(RuntimeError):
    """Raised when GEMINI_API_KEY is not configured (fail-closed)."""


NOT_CONFIGURED_MESSAGE = (
    "Gemini is not configured. Add GEMINI_API_KEY to the backend .env; "
    "Google AI Pro subscription sign-in is not an API key."
)


def gemini_api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def gemini_model() -> str:
    return os.getenv("GEMINI_MODEL") or "gemini-3.5-flash"


async def gemini_generate_json(
    prompt: str,
    schema: dict[str, Any] | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = 60.0,
) -> Any:
    """Call Gemini with a JSON response contract and return the parsed JSON."""
    key = gemini_api_key()
    if not key:
        raise GeminiNotConfigured(NOT_CONFIGURED_MESSAGE)
    generation_config: dict[str, Any] = {
        "temperature": 0.6,
        "responseMimeType": "application/json",
    }
    if schema:
        generation_config["responseSchema"] = schema
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{gemini_model()}:generateContent"
    )
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        response = await client.post(url, headers={"x-goog-api-key": key}, json=body)
        response.raise_for_status()
        data = response.json()
    parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    raw = "".join(part.get("text", "") for part in parts)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Gemini returned a response that did not match the requested JSON format."
        ) from exc
