"""Content studio engine: one topic in, a full cross-platform draft
bundle out. Gemini-backed and fail-closed. Every output is a draft for
human review — the studio never publishes."""
from __future__ import annotations

from typing import Any

from services.gemini_client import gemini_generate_json

DEFAULT_AUDIENCE = "CHROs, OD leaders, GCC heads and transformation executives"
DEFAULT_GOAL = "Drive qualified consulting inquiries and establish thought leadership"


class ContentStudio:
    async def generate_bundle(
        self,
        topic: str,
        target_audience: str = DEFAULT_AUDIENCE,
        primary_goal: str = DEFAULT_GOAL,
    ) -> dict[str, Any]:
        prompt = f"""Act as the content studio for TAPAS Advisory.
Topic: {topic}
Audience: {target_audience}
Goal: {primary_goal}
Brand context: Ram Narayanan, Transformation Leader | Architect of CHANGEReadyX™, TAPAS Advisory. Focus: AI transformation failures, change management and organisational readiness. Rules: use only verifiable, attributed statistics (name the source in the text); never invent clients, testimonials, metrics or results; CHANGEReadyX™ is always written with the ™ symbol; every asset carries one clear CTA to the diagnostic at tapasadvisory.com/diagnostic where natural; LinkedIn assets close with the byline "Ram Narayanan – Transformation Leader | Architect of CHANGEReadyX™, TAPAS Advisory".

Generate a complete, platform-native content bundle:
- primary_keyword and supporting_keywords (buyer vocabulary)
- youtube_titles: exactly 10 options
- thumbnail_brief: one-paragraph brief (3-4 word overlay, face, contrast, 120px legibility)
- youtube_description: full description with the diagnostic CTA and chapter placeholders
- youtube_tags: 10-15 tags
- chapters: 4-7 entries with title and purpose
- shorts_script: a 20-60 second vertical script with on-screen text cues
- linkedin_post: full formatted post in the EETA pattern (evidence, experience, takeaway, action)
- x_thread, bluesky_post, mastodon_post: native drafts
- website_article: title plus outline (section list)
- newsletter_draft: CHANGEReadyX™ Insights edition draft
- ctas: the calls to action used across the bundle
- cadence: suggested publishing schedule per platform
- measurement_plan: what to measure per platform at 24h / 7d / 30d — name the metrics, invent no target numbers presented as facts
Return JSON only matching the schema."""
        string_list = {"type": "ARRAY", "items": {"type": "STRING"}}
        string_map = {"type": "OBJECT", "additionalProperties": {"type": "STRING"}}
        schema = {
            "type": "OBJECT",
            "properties": {
                "primary_keyword": {"type": "STRING"},
                "supporting_keywords": string_list,
                "youtube_titles": string_list,
                "thumbnail_brief": {"type": "STRING"},
                "youtube_description": {"type": "STRING"},
                "youtube_tags": string_list,
                "chapters": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "title": {"type": "STRING"},
                            "purpose": {"type": "STRING"},
                        },
                        "required": ["title", "purpose"],
                    },
                },
                "shorts_script": {"type": "STRING"},
                "linkedin_post": {"type": "STRING"},
                "x_thread": {"type": "STRING"},
                "bluesky_post": {"type": "STRING"},
                "mastodon_post": {"type": "STRING"},
                "website_article": {
                    "type": "OBJECT",
                    "properties": {
                        "title": {"type": "STRING"},
                        "outline": string_list,
                    },
                    "required": ["title", "outline"],
                },
                "newsletter_draft": {"type": "STRING"},
                "ctas": string_list,
                "cadence": string_map,
                "measurement_plan": string_map,
            },
            "required": [
                "primary_keyword", "supporting_keywords", "youtube_titles",
                "thumbnail_brief", "youtube_description", "youtube_tags", "chapters",
                "shorts_script", "linkedin_post", "x_thread", "bluesky_post",
                "mastodon_post", "website_article", "newsletter_draft", "ctas",
                "cadence", "measurement_plan",
            ],
        }
        result = await gemini_generate_json(prompt, schema)
        result["status"] = "draft"
        result["topic"] = topic
        result["target_audience"] = target_audience
        result["primary_goal"] = primary_goal
        result["note"] = "Draft bundle for human review. Nothing has been published or scheduled."
        return result
