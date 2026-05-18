"""Helpers for persisting Discover ground-truth diagnostics."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from app.models.models import DiscoverGroundTruthDiagnostic
from app.tasks.base import get_task_session

DEFAULT_FEED_URL = "https://api.bainluck.com/api/feed"


def build_diagnostic_rows_from_debug_payload(
    payload: dict[str, Any],
    *,
    run_id: str | None = None,
    captured_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Normalize debug payload hit/miss diagnostics into DB row dicts."""
    run_id = run_id or str(uuid.uuid4())
    captured_at = captured_at or datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []

    for source_group, items in (
        ("combined", payload.get("missing_ground_truth") or []),
        ("email", payload.get("email_ground_truth_misses") or []),
        (
            "external_curator",
            payload.get("external_curator_ground_truth_misses") or [],
        ),
    ):
        for item in items:
            rows.append(
                _row_from_missing_item(
                    item,
                    run_id=run_id,
                    captured_at=captured_at,
                    source_group=source_group,
                )
            )

    for source_group, section_key in (
        ("email", "email_ground_truth"),
        ("external_curator", "external_curator_ground_truth"),
    ):
        for hit in (payload.get(section_key) or {}).get("hits") or []:
            rows.append(
                _row_from_hit(
                    hit,
                    run_id=run_id,
                    captured_at=captured_at,
                    source_group=source_group,
                )
            )

    return rows


def _row_from_missing_item(
    item: dict[str, Any],
    *,
    run_id: str,
    captured_at: datetime,
    source_group: str,
) -> dict[str, Any]:
    trace = item.get("db_trace") or {}
    matches = trace.get("matches") or []
    first_match = matches[0] if matches else {}
    return {
        "run_id": run_id,
        "captured_at": captured_at,
        "source_group": source_group,
        "source": _string_or_none(item.get("source")),
        "status": "miss",
        "item_name": _string_or_none(item.get("name")) or "",
        "feed_name": None,
        "category": _string_or_none(item.get("category")),
        "probability": _string_or_none(item.get("probability")),
        "source_url": _string_or_none(item.get("url")),
        "published_at": _string_or_none(item.get("published_at") or item.get("date")),
        "rank": None,
        "score": None,
        "quality_class": _string_or_none(item.get("quality_class")),
        "archetype": _string_or_none(item.get("archetype")),
        "family_key": _string_or_none(item.get("family_key")),
        "story_key": _string_or_none(item.get("story_key")),
        "triage_bucket": _string_or_none(item.get("triage_bucket")),
        "recommended_action": _string_or_none(item.get("recommended_action")),
        "matched_market_id": first_match.get("id") if first_match else None,
        "trace_status": _string_or_none(trace.get("trace_status")),
        "trace_summary": _string_or_none(trace.get("trace_summary")),
        "db_match_count": len(matches),
        "raw": item,
    }


def _row_from_hit(
    hit: dict[str, Any],
    *,
    run_id: str,
    captured_at: datetime,
    source_group: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "captured_at": captured_at,
        "source_group": source_group,
        "source": source_group,
        "status": "hit",
        "item_name": _string_or_none(hit.get("name")) or "",
        "feed_name": _string_or_none(hit.get("feed_name")),
        "category": _string_or_none(hit.get("category")),
        "probability": None,
        "source_url": None,
        "published_at": None,
        "rank": _int_or_none(hit.get("rank")),
        "score": None,
        "quality_class": None,
        "archetype": None,
        "family_key": None,
        "story_key": None,
        "triage_bucket": None,
        "recommended_action": None,
        "matched_market_id": None,
        "trace_status": None,
        "trace_summary": None,
        "db_match_count": None,
        "raw": hit,
    }


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def persist_diagnostic_rows(rows: list[dict[str, Any]]) -> int:
    """Persist normalized diagnostic rows."""
    if not rows:
        return 0
    async with get_task_session() as session:
        session.add_all([DiscoverGroundTruthDiagnostic(**row) for row in rows])
    return len(rows)


def fetch_debug_payload(
    *,
    feed_url: str,
    admin_secret: str,
    limit: int,
    timeout: float = 60.0,
) -> dict[str, Any]:
    response = httpx.get(
        feed_url,
        params={
            "limit": str(limit),
            "include_events": "false",
            "include_futures": "true",
            "debug": "true",
            "secret": admin_secret,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()
