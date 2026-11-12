"""Post-publication campaign planner for TAPAS Growth Autopilot v1.6.

Creates deterministic, auditable distribution tasks from a confirmed publication.
It deliberately does not perform provider calls: adapters must separately be
connected, authorized, and invoked by an approval-aware worker.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from typing import Any


SUPPORTED_CHANNELS = {
    "youtube", "spotify", "apple_podcasts", "substack", "linkedin_profile",
    "linkedin_page", "x", "instagram", "threads", "medium", "tapas_website",
    "facebook",
}
HUMAN_REVIEW_ACTIONS = {"comment", "reaction", "share"}
PAID_ACTIONS = {"paid_promotion", "boost"}


@dataclass(frozen=True)
class DistributionTask:
    task_id: str
    publication_id: str
    channel: str
    action: str
    status: str
    approval_required: bool
    reason: str


def _id(publication_id: str, channel: str, action: str) -> str:
    return sha256(f"{publication_id}:{channel}:{action}".encode()).hexdigest()[:24]


def plan_distribution(
    publication: dict[str, Any],
    channels: list[str] | None = None,
    *,
    include_engagement: bool = True,
    include_paid: bool = False,
    paid_approved: bool = False,
) -> dict[str, Any]:
    """Build idempotent task records; never publish or engage by itself."""
    publication_id = str(publication.get("publication_id", "")).strip()
    if not publication_id:
        raise ValueError("publication_id_required")
    if publication.get("status") != "published":
        raise ValueError("publication_must_be_confirmed_published")
    selected = channels or ["linkedin_profile", "x", "substack", "medium", "tapas_website"]
    unknown = sorted(set(selected) - SUPPORTED_CHANNELS)
    if unknown:
        raise ValueError("unsupported_channels:" + ",".join(unknown))

    tasks: list[DistributionTask] = []
    for channel in sorted(set(selected)):
        tasks.append(DistributionTask(
            task_id=_id(publication_id, channel, "distribution"),
            publication_id=publication_id, channel=channel, action="distribution",
            status="queued_for_approval", approval_required=True,
            reason="Confirm channel format, account authorization, and publication approval.",
        ))
    if include_engagement:
        for channel in sorted(set(selected) & {"linkedin_profile", "linkedin_page", "x"}):
            for action in sorted(HUMAN_REVIEW_ACTIONS):
                tasks.append(DistributionTask(
                    task_id=_id(publication_id, channel, action),
                    publication_id=publication_id, channel=channel, action=action,
                    status="human_review_queue", approval_required=True,
                    reason="Draft/suggest only; a human must perform the interaction.",
                ))
    if include_paid:
        tasks.append(DistributionTask(
            task_id=_id(publication_id, "campaign", "paid_promotion"),
            publication_id=publication_id, channel="campaign", action="paid_promotion",
            status="approved_to_queue" if paid_approved else "approval_required",
            approval_required=not paid_approved,
            reason="Paid promotion requires explicit budget, audience, duration, and spend approval.",
        ))
    return {
        "publication_id": publication_id,
        "idempotency_key": sha256(publication_id.encode()).hexdigest(),
        "tasks": [asdict(t) for t in tasks],
        "task_count": len(tasks),
        "execution": "plan_only",
    }
