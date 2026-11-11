"""YouTube 5,000-view campaign target tracker.

A target is a planning threshold, not a promise or a mechanism for artificial
views. This module records the goal and calculates the remaining gap from
source-reported metrics only.
"""
from __future__ import annotations

from typing import Any

DEFAULT_VIEW_TARGET = 5000


def evaluate_view_target(
    reported_views: int | None,
    target_views: int = DEFAULT_VIEW_TARGET,
    *,
    source: str = "YouTube Analytics API",
) -> dict[str, Any]:
    if target_views < 1:
        raise ValueError("target_views must be at least 1")
    if reported_views is None:
        return {
            "status": "awaiting_metrics",
            "target_views": target_views,
            "reported_views": None,
            "remaining_views": None,
            "attainment_percent": None,
            "source": source,
            "note": "No source-reported view count is available; no estimate is substituted.",
        }
    if reported_views < 0:
        raise ValueError("reported_views cannot be negative")
    attainment = round((reported_views / target_views) * 100, 2)
    return {
        "status": "target_met" if reported_views >= target_views else "in_progress",
        "target_views": target_views,
        "reported_views": reported_views,
        "remaining_views": max(0, target_views - reported_views),
        "attainment_percent": attainment,
        "source": source,
        "note": "5,000 views is a campaign target, not a guaranteed outcome.",
    }
