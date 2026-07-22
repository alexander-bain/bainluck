"""Cached Sentry 24h snapshot (#237 Item 1).

The ops-snapshot endpoint (`GET /api/admin/ops-snapshot`) must surface the top
Sentry issues by 24h volume WITHOUT making a live Sentry API call on the request
path. This beat task queries Sentry's issues API on a schedule and writes a compact
summary to Redis (``bainluck:sentry:top_24h``); the endpoint only reads that key.

Gotcha #49: a Sentry issue's ``count`` field is its LIFETIME total — a dormant bug
can show thousands there while firing zero in the last 24h. We rank by the summed
24h stats buckets (``stats.24h``), never by ``count``.

Auth: needs ``SENTRY_AUTH_TOKEN`` (an API token, distinct from ``SENTRY_DSN`` which
is only for error reporting). When the token is absent (e.g. not set on the dyno)
the task writes a ``no_token`` status rather than failing — the snapshot degrades
to "no data" and populates the moment a token is configured.
"""

import json
import logging
import os
from datetime import datetime, timezone

import httpx

from app.tasks.redis_state import get_redis_client

logger = logging.getLogger(__name__)

SENTRY_SNAPSHOT_KEY = "bainluck:sentry:top_24h"
_TTL_SECONDS = 3600  # generous — the beat refreshes far more often
_TOP_N = 8
_HTTP_TIMEOUT = 15.0


def _sum_24h_buckets(stats_24h) -> int:
    """Sentry ``stats.24h`` is a list of ``[epoch, count]`` pairs. Sum the counts
    (gotcha #49 — this is the recent volume, not the lifetime ``count`` field)."""
    if not isinstance(stats_24h, list):
        return 0
    total = 0
    for bucket in stats_24h:
        try:
            total += int(bucket[1])
        except (TypeError, ValueError, IndexError):
            continue
    return total


async def _run_sentry_snapshot() -> dict:
    """Fetch top Sentry issues by 24h volume and cache them in Redis. Returns the
    payload written (also returned for task-metrics tracking)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    token = os.getenv("SENTRY_AUTH_TOKEN")
    org = os.getenv("SENTRY_ORG", "alexander-bain")
    project = os.getenv("SENTRY_PROJECT", "bainluck")

    if not token:
        payload = {
            "status": "no_token",
            "generated_at": now_iso,
            "note": "SENTRY_AUTH_TOKEN not set — ops-snapshot Sentry field stays empty until configured.",
            "issues": [],
            "total_24h": 0,
        }
        _write(payload)
        logger.info("sentry_snapshot: no SENTRY_AUTH_TOKEN — wrote no_token status")
        return payload

    url = f"https://sentry.io/api/0/projects/{org}/{project}/issues/"
    params = {"statsPeriod": "24h", "query": "is:unresolved", "sort": "freq", "limit": 25}
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            raw_issues = resp.json()
    except Exception as exc:  # noqa: BLE001 — degrade, never fail the beat hard
        payload = {
            "status": "error",
            "generated_at": now_iso,
            "error": str(exc)[:200],
            "issues": [],
            "total_24h": 0,
        }
        _write(payload)
        logger.warning("sentry_snapshot: query failed — %s", exc)
        return payload

    issues = []
    for it in raw_issues if isinstance(raw_issues, list) else []:
        stats = (it.get("stats") or {}).get("24h")
        count_24h = _sum_24h_buckets(stats)
        issues.append({
            "short_id": it.get("shortId"),
            "title": (it.get("title") or "")[:160],
            "culprit": (it.get("culprit") or "")[:160],
            "level": it.get("level"),
            "count_24h": count_24h,
            "permalink": it.get("permalink"),
        })

    issues.sort(key=lambda x: x["count_24h"], reverse=True)
    top = issues[:_TOP_N]
    payload = {
        "status": "ok",
        "generated_at": now_iso,
        "issues": top,
        "total_24h": sum(i["count_24h"] for i in issues),
        "issue_count_24h": sum(1 for i in issues if i["count_24h"] > 0),
    }
    _write(payload)
    logger.info(
        "sentry_snapshot: cached %d issues (%d with 24h events)",
        len(top), payload["issue_count_24h"],
    )
    return payload


def _write(payload: dict) -> None:
    try:
        get_redis_client().setex(SENTRY_SNAPSHOT_KEY, _TTL_SECONDS, json.dumps(payload))
    except Exception as exc:  # noqa: BLE001
        logger.warning("sentry_snapshot: redis write failed — %s", exc)
