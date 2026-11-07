"""Search / AEO / GEO engine — corrected version.

An external draft fabricated an SEO audit (invented impressions, CTR
and broken-link "findings"). That is NOT reproduced here:
- generate_aeo is Gemini-backed and fail-closed.
- geo_audit is fully deterministic: it checks text the caller submits
  against the canonical TAPAS Advisory entity rules. No external calls,
  no invented numbers. The attributed-statistic check is a labelled
  heuristic.
- seo_status honestly reports that live SEO metrics require a Google
  Search Console integration that is not configured.
- Keyword research returns modelled relevance only; search_volume is
  always null because no volume source is connected.
"""
from __future__ import annotations

import re
from typing import Any

from services.gemini_client import gemini_generate_json

CANONICAL_ENTITIES: list[dict[str, str]] = [
    {
        "name": "TAPAS Advisory",
        "type": "Organization",
        "location": "Bengaluru, India",
        "website": "https://tapasadvisory.com",
        "description": "Independent transformation consulting firm founded by Ram Narayanan (founded 2022).",
    },
    {
        "name": "Ram Narayanan",
        "type": "Person",
        "role": "Founder, TAPAS Advisory; Architect of CHANGEReadyX™",
        "byline": "Ram Narayanan – Transformation Leader",
        "website": "https://tapasadvisory.com",
    },
    {
        "name": "CHANGEReadyX™",
        "type": "Framework",
        "owner": "TAPAS Advisory",
        "description": "Change readiness diagnostic and operating framework; always written with the ™ symbol.",
    },
    {
        "name": "WISL™",
        "type": "Framework",
        "owner": "TAPAS Advisory",
        "description": "Leadership coaching framework; always written with the ™ symbol.",
    },
    {
        "name": "TII™",
        "type": "Index",
        "full_name": "Transformation Intelligence Index",
        "owner": "TAPAS Advisory",
        "description": "Evidence-based transformation intelligence index (never described as 'validated').",
    },
    {
        "name": "TAPAS Advisory Diagnostic",
        "type": "WebPage",
        "url": "https://tapasadvisory.com/diagnostic",
        "description": "The CHANGEReadyX™ change readiness diagnostic — the canonical lead instrument.",
    },
]

_KNOWN_SOURCES = (
    "MIT", "NANDA", "McKinsey", "Gartner", "BCG", "S&P", "RAND", "Gallup",
    "Deloitte", "PwC", "Accenture", "Forrester", "IDC", "Harvard",
    "World Economic Forum", "Stanford", "Oxford",
)
_ATTRIBUTION_WORDS = ("according to", "study", "report", "survey", "research", "data from")


def geo_audit(text: str) -> dict[str, Any]:
    """Deterministic entity/consistency checks on caller-submitted text."""
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    add(
        "tapas_advisory_mentioned",
        "TAPAS Advisory" in text,
        "Text names TAPAS Advisory." if "TAPAS Advisory" in text else "TAPAS Advisory is not mentioned.",
    )
    add(
        "ram_narayanan_mentioned",
        "Ram Narayanan" in text,
        "Text names Ram Narayanan." if "Ram Narayanan" in text else "Ram Narayanan is not mentioned.",
    )
    has_tm_form = "CHANGEReadyX™" in text
    add(
        "changereadyx_with_trademark",
        has_tm_form,
        "CHANGEReadyX™ appears with the ™ symbol." if has_tm_form else "CHANGEReadyX™ (with ™) does not appear.",
    )
    bare_occurrences = len(re.findall(r"CHANGEReadyX(?!™)", text))
    add(
        "no_bare_changereadyx",
        bare_occurrences == 0,
        "No bare CHANGEReadyX (missing ™) found."
        if bare_occurrences == 0
        else f"{bare_occurrences} occurrence(s) of CHANGEReadyX without the ™ symbol.",
    )
    has_diagnostic = "tapasadvisory.com/diagnostic" in text
    add(
        "diagnostic_link_present",
        has_diagnostic,
        "Diagnostic link tapasadvisory.com/diagnostic is present."
        if has_diagnostic
        else "Diagnostic link tapasadvisory.com/diagnostic is missing.",
    )
    has_site = "tapasadvisory.com" in text
    add(
        "website_mentioned",
        has_site,
        "tapasadvisory.com is mentioned." if has_site else "tapasadvisory.com is not mentioned.",
    )

    # Heuristic attributed-statistic check: a % figure counts as attributed
    # if a known source name or attribution wording appears within ~120
    # characters of it. Labelled a heuristic — it is not a fact-check.
    percent_matches = list(re.finditer(r"\d+(?:\.\d+)?\s?%", text))
    if not percent_matches:
        add(
            "statistics_attributed_heuristic",
            True,
            "No percentage statistics present; attribution not applicable. (Heuristic check.)",
        )
    else:
        unattributed = 0
        for match in percent_matches:
            window = text[max(0, match.start() - 120): match.end() + 120].lower()
            attributed = any(s.lower() in window for s in _KNOWN_SOURCES) or any(
                w in window for w in _ATTRIBUTION_WORDS
            )
            if not attributed:
                unattributed += 1
        add(
            "statistics_attributed_heuristic",
            unattributed == 0,
            f"All {len(percent_matches)} percentage statistic(s) have a named source nearby. (Heuristic check — verify at the original publication before publishing.)"
            if unattributed == 0
            else f"{unattributed} of {len(percent_matches)} percentage statistic(s) have no named source nearby. (Heuristic check.)",
        )

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    return {
        "status": "success",
        "method": "deterministic local checks (no external calls, no invented data)",
        "checks": checks,
        "passed": passed,
        "total": total,
        "readiness_score": round(passed / total, 3) if total else 0.0,
    }


def seo_status() -> dict[str, Any]:
    return {
        "status": "requires_google_search_console",
        "message": (
            "Live SEO metrics (impressions, CTR, indexing status) require a connected "
            "Google Search Console API integration, which is not configured. No audit "
            "findings are reported without live data."
        ),
    }


class SEOAEOGEOEngine:
    async def generate_aeo(self, topic: str) -> dict[str, Any]:
        prompt = f"""You are the AEO (Answer Engine Optimization) writer for TAPAS Advisory.
Topic: {topic}
Author identity for attribution: Ram Narayanan, Transformation Leader | Architect of CHANGEReadyX™, TAPAS Advisory.

Produce:
- direct_answer: a direct, quotable answer to the primary question a CHRO or GCC leader would ask about this topic, UNDER 60 words, standalone (understandable without context). Use only verifiable, attributed claims; never invent statistics, clients or results. Where a statistic is used, name its source in the text.
- faqs: 4 to 6 frequently asked questions with concise, evidence-led answers (40-80 words each), same rules.
Return JSON only matching the schema."""
        schema = {
            "type": "OBJECT",
            "properties": {
                "direct_answer": {"type": "STRING"},
                "faqs": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "question": {"type": "STRING"},
                            "answer": {"type": "STRING"},
                        },
                        "required": ["question", "answer"],
                    },
                },
            },
            "required": ["direct_answer", "faqs"],
        }
        result = await gemini_generate_json(prompt, schema)
        faqs = result.get("faqs") or []
        faq_json_ld = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": faq.get("question", ""),
                    "acceptedAnswer": {"@type": "Answer", "text": faq.get("answer", "")},
                }
                for faq in faqs
            ],
        }
        return {
            "status": "success",
            "topic": topic,
            "direct_answer": result.get("direct_answer", ""),
            "direct_answer_word_count": len((result.get("direct_answer") or "").split()),
            "faqs": faqs,
            "faq_json_ld": faq_json_ld,
            "provenance": "Gemini AEO generation (draft content for human review)",
        }

    async def research_keywords(self, topic: str) -> dict[str, Any]:
        prompt = f"""You are the keyword researcher for TAPAS Advisory (Ram Narayanan, Transformation Leader; CHANGEReadyX™).
Topic: {topic}
Audience: CHROs, GCC heads, CIOs and transformation leaders, primarily India/global capability centres.

Generate 10-15 keyword candidates a buyer in this audience would actually search. For each: keyword, search_intent (one of informational, navigational, commercial, transactional), funnel_stage (awareness, consideration, decision), relevance_score 0.0-1.0 for TAPAS Advisory's AI-transformation and change-readiness positioning, confidence 0.0-1.0, and topic_cluster (a short cluster label). Buyer vocabulary leads; do not invent search volumes — none will be reported.
Return JSON only matching the schema."""
        schema = {
            "type": "OBJECT",
            "properties": {
                "keywords": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "keyword": {"type": "STRING"},
                            "search_intent": {
                                "type": "STRING",
                                "enum": ["informational", "navigational", "commercial", "transactional"],
                            },
                            "funnel_stage": {"type": "STRING"},
                            "topic_cluster": {"type": "STRING"},
                            "relevance_score": {"type": "NUMBER"},
                            "confidence": {"type": "NUMBER"},
                        },
                        "required": [
                            "keyword",
                            "search_intent",
                            "funnel_stage",
                            "topic_cluster",
                            "relevance_score",
                            "confidence",
                        ],
                    },
                }
            },
            "required": ["keywords"],
        }
        result = await gemini_generate_json(prompt, schema)
        keywords = []
        for item in result.get("keywords") or []:
            keywords.append(
                {
                    "keyword": item.get("keyword", ""),
                    "search_intent": item.get("search_intent", ""),
                    "funnel_stage": item.get("funnel_stage", ""),
                    "topic_cluster": item.get("topic_cluster", ""),
                    "relevance_score": item.get("relevance_score"),
                    "confidence": item.get("confidence"),
                    "search_volume": None,
                    "source": "gemini_keyword_model",
                }
            )
        return {
            "status": "success",
            "topic": topic,
            "keywords": keywords,
            "search_volume": None,
            "note": (
                "Search volume is null: no keyword-volume source is connected, and no "
                "volume figures are fabricated. Relevance and confidence are model "
                "estimates for prioritisation, not measured demand."
            ),
        }
