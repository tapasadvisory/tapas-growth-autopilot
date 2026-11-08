"""Google Search Console integration — Release 1.4.

Reads LIVE search performance for Ram's own Search Console property via
the Search Console API (webmasters v3): the sites list and the
searchAnalytics query endpoint (dimensions: query, page; metrics:
clicks, impressions, ctr, position).

Auth model — no new OAuth flow is invented here. GSC rides the existing
Google connection (the "youtube" provider row in the encrypted
connections store, created by the existing code-relay connect flow).
The Search Console API requires the scope

    https://www.googleapis.com/auth/webmasters.readonly

which is separate from the YouTube scopes. This module is FAIL-CLOSED:
if the stored Google connection is missing, disconnected, or its
granted scopes do not include the webmasters scope, every entry point
reports status "not_configured" with the exact missing scope and the
data needed to start the existing re-consent flow (add the scope via
GOOGLE_EXTRA_SCOPES and re-run the YouTube connect). Nothing here ever
fabricates search metrics: a snapshot exists only after a real API
response has been normalized by this module.

This module is pure logic + constants; server.py owns the HTTP calls,
the token store and persistence (gsc_snapshots table), mirroring how
publication_engine relates to the detection routes.
"""
from __future__ import annotations

from typing import Any

GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
GSC_API_BASE = "https://www.googleapis.com/webmasters/v3"
DEFAULT_PROPERTY = "https://tapasadvisory.com/"
DEFAULT_ROW_LIMIT = 1000
PERIOD_DAYS = 28

# How a missing configuration is fixed, expressed in the codebase's own
# terms: the connect flow for Google already supports extra scopes for
# LinkedIn via LINKEDIN_EXTRA_SCOPES; Release 1.4 adds the mirror
# mechanism GOOGLE_EXTRA_SCOPES for the "youtube" provider.
RECONSENT = {
    "connect_url": "/api/connect/youtube/start",
    "provider": "youtube",
    "extra_scopes_env": "GOOGLE_EXTRA_SCOPES",
    "extra_scopes_value": GSC_SCOPE,
    "instructions": (
        "Set GOOGLE_EXTRA_SCOPES=https://www.googleapis.com/auth/webmasters.readonly "
        "in the backend .env, restart the backend, then re-run the existing "
        "YouTube (Google) connect — GET /api/connect/youtube/start — and "
        "approve the added Search Console scope on Google's consent screen "
        "(the code-relay flow already used for this connection). The stored "
        "connection then carries the scope and GSC sync activates."
    ),
}


def split_scopes(scopes: Any) -> list[str]:
    """Granted scopes are stored as one string; Google returns them
    space-separated, LinkedIn comma-separated. Handle both."""
    if not scopes:
        return []
    text = str(scopes)
    parts: list[str] = []
    for chunk in text.replace(",", " ").split():
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    return parts


def has_gsc_scope(scopes: Any) -> bool:
    return GSC_SCOPE in split_scopes(scopes)


def gsc_configuration(connection: dict | None) -> dict[str, Any]:
    """Fail-closed configuration verdict for the stored Google connection.

    Returns {"configured": True, ...} only when a connected Google
    connection exists AND its granted scopes include the webmasters
    scope. Otherwise the exact gap is named.
    """
    if not connection or connection.get("status") != "connected":
        return {
            "configured": False,
            "status": "not_configured",
            "reason": "google_account_not_connected",
            "missing_scope": GSC_SCOPE,
            "detail": "No connected Google account was found in the backend "
                      "token store (the YouTube connection). Connect Google first.",
            "reconsent": dict(RECONSENT),
        }
    granted = split_scopes(connection.get("scopes"))
    if not has_gsc_scope(connection.get("scopes")):
        return {
            "configured": False,
            "status": "not_configured",
            "reason": "missing_scope",
            "missing_scope": GSC_SCOPE,
            "granted_scopes": granted,
            "detail": "The connected Google account has not granted the "
                      "Search Console scope, so live GSC data cannot be read yet.",
            "reconsent": dict(RECONSENT),
        }
    return {
        "configured": True,
        "status": "configured",
        "granted_scopes": granted,
        "account_name": connection.get("display_name"),
    }


def build_search_analytics_body(start_date: str, end_date: str,
                                row_limit: int = DEFAULT_ROW_LIMIT) -> dict[str, Any]:
    """searchAnalytics.query request body: the last PERIOD_DAYS of data,
    broken down by query and page (metrics arrive per row)."""
    return {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["query", "page"],
        "rowLimit": max(1, min(int(row_limit), 25000)),
    }


def _aggregate(rows: list[dict[str, Any]], key_index: int) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, float]] = {}
    for row in rows:
        keys = row.get("keys") or []
        if len(keys) <= key_index:
            continue
        name = keys[key_index]
        clicks = float(row.get("clicks") or 0)
        impressions = float(row.get("impressions") or 0)
        position = float(row.get("position") or 0)
        bucket = buckets.setdefault(name, {"clicks": 0.0, "impressions": 0.0, "pos_weighted": 0.0})
        bucket["clicks"] += clicks
        bucket["impressions"] += impressions
        bucket["pos_weighted"] += position * impressions
    out = []
    for name, b in buckets.items():
        impressions = b["impressions"]
        out.append({
            "name": name,
            "clicks": int(b["clicks"]),
            "impressions": int(impressions),
            "ctr": round(b["clicks"] / impressions, 4) if impressions else 0.0,
            "position": round(b["pos_weighted"] / impressions, 2) if impressions else 0.0,
        })
    out.sort(key=lambda r: (r["clicks"], r["impressions"]), reverse=True)
    return out


def normalize_search_analytics(api_response: dict[str, Any], limit: int = 25) -> dict[str, Any]:
    """Turn a raw searchAnalytics response (rows keyed [query, page])
    into the stored report shape: totals + top queries + top pages.
    Totals are exact sums over the returned rows; overall position is
    the impression-weighted mean, overall ctr is clicks/impressions."""
    rows = api_response.get("rows") or []
    total_clicks = sum(float(r.get("clicks") or 0) for r in rows)
    total_impressions = sum(float(r.get("impressions") or 0) for r in rows)
    pos_weighted = sum(float(r.get("position") or 0) * float(r.get("impressions") or 0) for r in rows)
    totals = {
        "clicks": int(total_clicks),
        "impressions": int(total_impressions),
        "ctr": round(total_clicks / total_impressions, 4) if total_impressions else 0.0,
        "position": round(pos_weighted / total_impressions, 2) if total_impressions else 0.0,
        "rows": len(rows),
    }
    return {
        "totals": totals,
        "top_queries": _aggregate(rows, 0)[:limit],
        "top_pages": _aggregate(rows, 1)[:limit],
    }
