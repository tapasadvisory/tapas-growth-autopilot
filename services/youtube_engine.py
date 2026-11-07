"""YouTube growth engine: content pillars, title evaluation, retention
reporting/optimisation guidance, thumbnail briefs and Shorts scripting.

Gemini-backed methods are fail-closed (GeminiNotConfigured when no key is
configured). Retention reporting uses the owner's OAuth access token,
passed in by the API layer (which obtains it via the v1 access_token
helper); raw audienceWatchRatio values are preserved — they can exceed
1.0 when viewers rewind. The thumbnail brief is a deterministic
checklist generator: guidance only, no invented measurements.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from services.gemini_client import gemini_generate_json

PILLARS: list[str] = [
    "AI Transformation Failures",
    "ERP Transformation Failures",
    "AI Investment Without Payback",
    "GCC Leadership & Talent",
    "CHRO Strategy",
    "Change Readiness & CHANGEReadyX™",
    "Leadership Failures",
    "The Human Side of Transformation",
    "Target Operating Models",
    "Capability Architecture",
    "AI at Work",
    "The People-First Blueprint",
]

ANALYTICS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"


class YouTubeGrowthEngine:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def evaluate_titles(self, topic: str, current_title: str = "") -> dict[str, Any]:
        prompt = f"""You are the title strategist for the YouTube channel "Ram's CHANGEReadyX™ from TAPAS Advisory" (Ram Narayanan, Transformation Leader). The audience is CHROs, GCC heads, CIOs and transformation leaders.
Topic: {topic}
Current title (may be empty): {current_title or "(none)"}

Generate exactly 10 distinct title suggestions, spread across the discovery surfaces Search, Browse, Suggested and Shorts. Rules: use only statistics that are widely verifiable and attribute them inside the title only when certain; never invent numbers, clients or results; no clickbait that the video cannot deliver; keep each title under 70 characters where possible. Score each title from 0.0 to 1.0 on clarity, curiosity and credibility, and set overall to their average. Give a one-sentence rationale per title. Rank best first.
Return JSON only matching the schema."""
        score_schema = {
            "type": "OBJECT",
            "properties": {
                "clarity": {"type": "NUMBER"},
                "curiosity": {"type": "NUMBER"},
                "credibility": {"type": "NUMBER"},
                "overall": {"type": "NUMBER"},
            },
            "required": ["clarity", "curiosity", "credibility", "overall"],
        }
        schema = {
            "type": "OBJECT",
            "properties": {
                "suggestions": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "title": {"type": "STRING"},
                            "target_discovery": {
                                "type": "STRING",
                                "enum": ["Search", "Browse", "Suggested", "Shorts"],
                            },
                            "rationale": {"type": "STRING"},
                            "scores": score_schema,
                        },
                        "required": ["title", "target_discovery", "rationale", "scores"],
                    },
                }
            },
            "required": ["suggestions"],
        }
        result = await gemini_generate_json(prompt, schema)
        suggestions = list(result.get("suggestions") or [])
        suggestions.sort(
            key=lambda s: float((s.get("scores") or {}).get("overall") or 0), reverse=True
        )
        for index, suggestion in enumerate(suggestions, start=1):
            suggestion["rank"] = index
        return {
            "status": "success",
            "topic": topic,
            "current_title": current_title,
            "suggestions": suggestions,
            "provenance": "Gemini title evaluation (draft guidance, not performance data)",
        }

    async def retention_report(
        self, video_id: str, access_token: str | None
    ) -> dict[str, Any]:
        if not access_token:
            return {
                "status": "unconfigured",
                "metric": "retention",
                "value": None,
                "source": "YouTube Analytics API",
                "message": "YouTube is not connected, so no OAuth access token is available for Analytics.",
            }
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start_date = (datetime.now(timezone.utc) - timedelta(days=28)).strftime("%Y-%m-%d")
        params = {
            "ids": "channel==MINE",
            "startDate": start_date,
            "endDate": end_date,
            "metrics": "audienceWatchRatio,relativeRetentionPerformance",
            "dimensions": "elapsedVideoTimeRatio",
            "filters": f"video=={video_id}",
        }
        async with httpx.AsyncClient(timeout=35, transport=self.transport) as client:
            response = await client.get(
                ANALYTICS_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
        if response.status_code == 403:
            return {
                "status": "permission_denied",
                "metric": "retention",
                "value": None,
                "source": "YouTube Analytics API",
            }
        if response.status_code == 400 and "INSUFFICIENT_DATA" in response.text:
            return {
                "status": "insufficient_data",
                "metric": "retention",
                "value": None,
                "source": "YouTube Analytics API",
            }
        if response.status_code >= 400:
            return {
                "status": "error",
                "metric": "retention",
                "value": None,
                "source": "YouTube Analytics API",
                "http_status": response.status_code,
            }
        data = response.json()
        # Raw ratios are preserved as returned; audienceWatchRatio can
        # exceed 1.0 because of viewer rewinds.
        return {
            "status": "success",
            "video_id": video_id,
            "date_range": {"start": start_date, "end": end_date},
            "rows": data.get("rows", []),
            "column_headers": data.get("columnHeaders", []),
            "provenance": "YouTube Analytics API",
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    async def retention_optimize(
        self, topic: str, duration_seconds: int | None = None
    ) -> dict[str, Any]:
        duration_text = (
            f"Planned duration: {duration_seconds} seconds."
            if duration_seconds
            else "Duration not fixed yet; plan in percentages of runtime."
        )
        prompt = f"""You are the retention planner for a TAPAS Advisory long-form YouTube video by Ram Narayanan, Transformation Leader.
Topic: {topic}
{duration_text}

Produce planning guidance only (no invented performance statistics):
- hook_script: the spoken 0-15 second cold-open hook — the sharpest debate line first, then the promise of the video. First person, Ram's voice.
- pattern_interrupts: exactly 3 entries, at 30, 55 and 80 (percent of runtime), each with a concrete technique (question to camera, on-screen evidence card, story beat, visual switch).
- chapter_plan: 4-7 chapters, each with a title and start_percent.
- end_screen_suggestion: what the final 20 seconds should point to and say.
Return JSON only matching the schema."""
        schema = {
            "type": "OBJECT",
            "properties": {
                "hook_script": {"type": "STRING"},
                "pattern_interrupts": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "percent": {"type": "NUMBER"},
                            "technique": {"type": "STRING"},
                        },
                        "required": ["percent", "technique"],
                    },
                },
                "chapter_plan": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "title": {"type": "STRING"},
                            "start_percent": {"type": "NUMBER"},
                        },
                        "required": ["title", "start_percent"],
                    },
                },
                "end_screen_suggestion": {"type": "STRING"},
            },
            "required": [
                "hook_script",
                "pattern_interrupts",
                "chapter_plan",
                "end_screen_suggestion",
            ],
        }
        result = await gemini_generate_json(prompt, schema)
        if duration_seconds:
            for interrupt in result.get("pattern_interrupts") or []:
                interrupt["at_seconds"] = round(
                    float(interrupt.get("percent") or 0) / 100 * duration_seconds
                )
            for chapter in result.get("chapter_plan") or []:
                chapter["start_seconds"] = round(
                    float(chapter.get("start_percent") or 0) / 100 * duration_seconds
                )
        return {
            "status": "success",
            "kind": "guidance",
            "topic": topic,
            "duration_seconds": duration_seconds,
            "hook_window": "0-15s",
            **result,
            "note": "Planning guidance only — not measured retention data.",
        }

    async def generate_shorts_script(
        self, topic: str, pillar: str | None = None
    ) -> dict[str, Any]:
        pillar_text = pillar or "AI Transformation Failures"
        prompt = f"""Write a 20-60 second vertical YouTube Short script for Ram Narayanan, Transformation Leader (TAPAS Advisory).
Topic: {topic}
Content pillar: {pillar_text}
Format: white-background animated corporate explainer. Open with the hook in the first 3 seconds, one idea only, every line paired with short on-screen text. Use only verifiable, attributed statistics if any statistic is used; never invent numbers. Close with the line "I am Ram Narayanan, Transformation Leader" and a CTA to the full video and the CHANGEReadyX™ diagnostic at tapasadvisory.com/diagnostic.
Return JSON only matching the schema: hook (first spoken line), lines (timestamp like "0:00-0:03", spoken, on_screen_text), cta, estimated_duration_seconds."""
        schema = {
            "type": "OBJECT",
            "properties": {
                "hook": {"type": "STRING"},
                "lines": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "timestamp": {"type": "STRING"},
                            "spoken": {"type": "STRING"},
                            "on_screen_text": {"type": "STRING"},
                        },
                        "required": ["timestamp", "spoken", "on_screen_text"],
                    },
                },
                "cta": {"type": "STRING"},
                "estimated_duration_seconds": {"type": "NUMBER"},
            },
            "required": ["hook", "lines", "cta", "estimated_duration_seconds"],
        }
        result = await gemini_generate_json(prompt, schema)
        return {
            "status": "draft",
            "topic": topic,
            "pillar": pillar_text,
            **result,
            "note": "Draft script for human review. Nothing has been published.",
        }

    def thumbnail_brief(self, title: str) -> dict[str, Any]:
        words = [w.strip("—–-|:,.!?\"'") for w in title.replace("—", " ").split()]
        words = [w for w in words if w]
        overlay_candidate = " ".join(words[:4])
        return {
            "status": "success",
            "kind": "brief",
            "title": title,
            "overlay_text_candidate": overlay_candidate,
            "checklist": [
                {
                    "item": "Overlay text length",
                    "guidance": "3-4 words maximum, large type. Candidate from the title: "
                    f"\"{overlay_candidate}\". Do not repeat the full video title in the thumbnail.",
                },
                {
                    "item": "Face presence",
                    "guidance": "Ram's face large, right third of frame, direct eye contact, one clear expression.",
                },
                {
                    "item": "Contrast",
                    "guidance": "Aim for roughly 7:1 contrast between overlay text and its background so the words survive compression and dark mode.",
                },
                {
                    "item": "120px legibility rule",
                    "guidance": "Shrink the design to 120px wide (mobile feed size): overlay text and the single focal idea must still read instantly.",
                },
                {
                    "item": "Single focal point",
                    "guidance": "One face, one short phrase, one visual idea. Remove any element that competes with those three.",
                },
                {
                    "item": "Brand",
                    "guidance": "Master palette only (Navy #001F7A, Royal Blue #0D4BFF, Cyan #14B8E6, Purple #6A00FF, Violet #8F1FFF) with the CHANGEReadyX™ identity consistent with the channel.",
                },
                {
                    "item": "Format",
                    "guidance": "1280x720 canvas for long-form video thumbnails.",
                },
            ],
            "note": "Deterministic design brief/checklist. It contains guidance only — no measured performance data.",
        }
