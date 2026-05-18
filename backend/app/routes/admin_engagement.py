"""Admin endpoints for discover quality, engagement, bug reports, and feedback."""


import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from pydantic import BaseModel, Field

from sqlalchemy import select, update, and_, text, func

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, FuturesMarket

from app.models.models import BugReport, DiscoverInteraction, DiscoverReviewDecision

from app.services import get_db

from app.routes.admin_utils import _check_admin_secret, _check_admin_auth

import logging
logger = logging.getLogger(__name__)


router = APIRouter()


_BUG_FIXED_EMAIL_STATUSES = {"fixed", "actioned"}
_BUG_FIXED_EMAIL_TASK_NAME = "app.tasks.send_bug_fixed_email"
_VALID_BUG_CATEGORIES = {"ui", "data_quality", "performance", "feature_request", "ios", "other"}


def _has_resolution_summary(resolution_summary: Optional[str]) -> bool:
    return bool(resolution_summary and resolution_summary.strip())


def _should_enqueue_bug_fixed_email(
    *,
    previous_status: Optional[str],
    final_status: Optional[str],
    final_resolution_summary: Optional[str],
    notification_sent_at: Optional[datetime],
) -> bool:
    return (
        final_status in _BUG_FIXED_EMAIL_STATUSES
        and previous_status not in _BUG_FIXED_EMAIL_STATUSES
        and _has_resolution_summary(final_resolution_summary)
        and notification_sent_at is None
    )


def _enqueue_bug_fixed_email(report_id: int) -> None:
    try:
        from app.tasks import celery_app

        celery_app.send_task(_BUG_FIXED_EMAIL_TASK_NAME, args=[report_id])
    except Exception as exc:
        logger.warning("Bug fix email enqueue failed for report %d: %s", report_id, exc)


def _suggest_bug_report_category(
    description: Optional[str],
    app_state: Optional[dict],
) -> Optional[str]:
    """Return a deterministic admin category only when metadata is decisive."""
    from app.routes.feedback import categorize_bug_report

    category = categorize_bug_report(description, app_state)
    if category and category != "other":
        return category
    return None


@router.get("/hook-coverage")
async def hook_coverage(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Hook description and image coverage stats for open markets."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from sqlalchemy import text
    result = await db.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(hook_description) AS with_hook,
            COUNT(image_url) AS with_image,
            MAX(hook_generated_at) AS latest_hook,
            COUNT(*) FILTER (WHERE hook_generated_at > NOW() - INTERVAL '24 hours') AS hooks_last_24h,
            COUNT(*) FILTER (WHERE market_tier <= 3) AS tier_1_3_total,
            COUNT(*) FILTER (WHERE market_tier <= 3 AND hook_description IS NOT NULL) AS tier_1_3_with_hook
        FROM futures_markets WHERE status = 'open'
    """))
    r = result.first()
    return {
        "total_open": r.total,
        "with_hook": r.with_hook,
        "with_image": r.with_image,
        "hook_pct": round(r.with_hook / r.total * 100, 1) if r.total else 0,
        "image_pct": round(r.with_image / r.total * 100, 1) if r.total else 0,
        "latest_hook_generated_at": r.latest_hook.isoformat() if r.latest_hook else None,
        "hooks_generated_last_24h": r.hooks_last_24h,
        "tier_1_3_total": r.tier_1_3_total,
        "tier_1_3_with_hook": r.tier_1_3_with_hook,
        "tier_1_3_hook_pct": round(r.tier_1_3_with_hook / r.tier_1_3_total * 100, 1) if r.tier_1_3_total else 0,
    }


@router.post("/hook-enrichment/trigger")
async def trigger_hook_enrichment(
    secret: str = Query(...),
    limit: int = Query(100, ge=1, le=250),
):
    """Queue hook enrichment for feed-prioritized open markets."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app

    task = celery_app.send_task("app.tasks.enrich_market_hooks", kwargs={"limit": limit})
    return {
        "queued": True,
        "task_id": task.id,
        "limit": limit,
    }


@router.get("/discover-quality/trace/{market_id}")
async def discover_quality_market_trace(
    market_id: int,
    secret: str = Query(...),
    include_events: bool = Query(False),
    event_pct: float = Query(0.15, ge=0, le=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Explain how a futures market flows through Discover ranking."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.routes.feed import build_discover_market_trace

    trace = await build_discover_market_trace(
        db,
        market_id,
        include_events=include_events,
        event_pct=event_pct,
        limit=limit,
    )
    if not trace:
        raise HTTPException(status_code=404, detail="Market not found")
    return trace


_DISCOVER_CONFIG_KEY = "bainluck:discover_runtime_config"


class DiscoverReviewDecisionIn(BaseModel):
    item_type: str = Field(..., max_length=20)
    item_id: str = Field(..., max_length=100)
    item_name: Optional[str] = Field(None, max_length=300)
    category: Optional[str] = Field(None, max_length=80)
    surface: Optional[str] = Field(None, max_length=20)
    auth_segment: Optional[str] = Field(None, max_length=20)
    family_key: Optional[str] = Field(None, max_length=300)
    archetype: Optional[str] = Field(None, max_length=80)
    decision: str = Field(..., max_length=40)
    admin_notes: Optional[str] = Field(None, max_length=5000)


def _discover_config_defaults() -> dict:
    return {
        "interaction_suppression_enabled": os.getenv("DISCOVER_INTERACTION_SUPPRESSION", "true").lower() != "false",
        "seen_suppression_hours": float(os.getenv("DISCOVER_SEEN_SUPPRESSION_HOURS", "48")),
        "dismiss_suppression_days": float(os.getenv("DISCOVER_DISMISS_SUPPRESSION_DAYS", "14")),
        "stale_no_movement_days": float(os.getenv("DISCOVER_STALE_NO_MOVEMENT_DAYS", "2")),
        "no_resolution_stale_days": float(os.getenv("DISCOVER_NO_RESOLUTION_STALE_DAYS", "5")),
    }


async def _load_discover_runtime_config() -> dict:
    config = _discover_config_defaults()
    try:
        from app.tasks.redis_state import get_async_redis_client

        redis = get_async_redis_client()
        raw = await redis.hgetall(_DISCOVER_CONFIG_KEY)
        if raw:
            decoded = {
                (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
                for k, v in raw.items()
            }
            if "interaction_suppression_enabled" in decoded:
                config["interaction_suppression_enabled"] = decoded["interaction_suppression_enabled"].lower() == "true"
            for key in (
                "seen_suppression_hours",
                "dismiss_suppression_days",
                "stale_no_movement_days",
                "no_resolution_stale_days",
            ):
                if key in decoded:
                    config[key] = float(decoded[key])
    except Exception:
        pass
    return config


@router.get("/discover-config")
async def get_discover_runtime_config(
    secret: str = Query(...),
):
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    return await _load_discover_runtime_config()


@router.post("/discover-config")
async def update_discover_runtime_config(
    secret: str = Query(...),
    body: dict = Body(...),
):
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    allowed = _discover_config_defaults()
    values = {}
    for key, default in allowed.items():
        if key not in body:
            continue
        value = body[key]
        if isinstance(default, bool):
            values[key] = "true" if bool(value) else "false"
        else:
            number = float(value)
            if number < 0:
                raise HTTPException(status_code=400, detail=f"{key} must be non-negative")
            values[key] = str(number)
    if not values:
        raise HTTPException(status_code=400, detail="No valid Discover config fields provided")

    try:
        from app.tasks.redis_state import get_async_redis_client

        redis = get_async_redis_client()
        await redis.hset(_DISCOVER_CONFIG_KEY, mapping=values)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Redis unavailable: {exc}") from exc
    return await _load_discover_runtime_config()


@router.post("/discover-review-decisions")
async def create_discover_review_decision(
    payload: DiscoverReviewDecisionIn,
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    valid = {"accepted_promote", "accepted_downrank", "ignored", "needs_design_fix", "needs_data_fix"}
    if payload.decision not in valid:
        raise HTTPException(status_code=400, detail=f"decision must be one of: {sorted(valid)}")

    clauses = [
        DiscoverReviewDecision.item_type == payload.item_type,
        DiscoverReviewDecision.item_id == payload.item_id,
    ]
    if payload.surface is None:
        clauses.append(DiscoverReviewDecision.surface.is_(None))
    else:
        clauses.append(DiscoverReviewDecision.surface == payload.surface)
    if payload.auth_segment is None:
        clauses.append(DiscoverReviewDecision.auth_segment.is_(None))
    else:
        clauses.append(DiscoverReviewDecision.auth_segment == payload.auth_segment)

    existing_result = await db.execute(
        select(DiscoverReviewDecision)
        .where(and_(*clauses))
        .order_by(DiscoverReviewDecision.created_at.desc())
        .limit(1)
    )
    row = existing_result.scalars().first()
    if row:
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
        row.created_at = datetime.now(timezone.utc)
    else:
        row = DiscoverReviewDecision(**payload.model_dump())
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"status": "ok", "id": row.id}


@router.get("/discover-review-decisions")
async def list_discover_review_decisions(
    secret: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    result = await db.execute(
        select(DiscoverReviewDecision)
        .order_by(DiscoverReviewDecision.created_at.desc())
        .limit(limit)
    )
    rows = []
    seen_keys = set()
    for row in result.scalars().all():
        key = (row.item_type, row.item_id, row.surface, row.auth_segment)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        rows.append(row)
    return {
        "decisions": [
            {
                "id": row.id,
                "item_type": row.item_type,
                "item_id": row.item_id,
                "item_name": row.item_name,
                "category": row.category,
                "surface": row.surface,
                "auth_segment": row.auth_segment,
                "family_key": row.family_key,
                "archetype": row.archetype,
                "decision": row.decision,
                "admin_notes": row.admin_notes,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }


@router.get("/discover-engagement")
async def discover_engagement_summary(
    secret: str = Query(..., description="Admin secret for authorization"),
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    """Summarize first-party Discover engagement by surface/category/type."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            DiscoverInteraction.surface,
            DiscoverInteraction.category,
            DiscoverInteraction.item_type,
            DiscoverInteraction.action,
            func.count(DiscoverInteraction.id).label("count"),
        )
        .where(DiscoverInteraction.created_at >= cutoff)
        .group_by(
            DiscoverInteraction.surface,
            DiscoverInteraction.category,
            DiscoverInteraction.item_type,
            DiscoverInteraction.action,
        )
    )

    groups: dict[tuple[str, str, str], dict] = {}
    for surface, category, item_type, action, count in result.all():
        key = (surface or "unknown", category or "other", item_type or "unknown")
        bucket = groups.setdefault(
            key,
            {
                "surface": key[0],
                "category": key[1],
                "item_type": key[2],
                "impressions": 0,
                "opens": 0,
                "dismisses": 0,
                "shares": 0,
                "likes": 0,
                "group_expands": 0,
                "context_expands": 0,
                "context_collapses": 0,
                "challenge_starts": 0,
                "challenge_completes": 0,
                "actions": 0,
            },
        )
        n = int(count or 0)
        if action == "impression":
            bucket["impressions"] += n
        elif action in ("detail_click", "open"):
            bucket["opens"] += n
            bucket["actions"] += n
        elif action == "dismiss":
            bucket["dismisses"] += n
            bucket["actions"] += n
        elif action == "share":
            bucket["shares"] += n
            bucket["actions"] += n
        elif action in ("like", "unlike"):
            bucket["likes"] += n
            bucket["actions"] += n
        elif action == "group_expand":
            bucket["group_expands"] += n
            bucket["actions"] += n
        elif action == "context_expand":
            bucket["context_expands"] += n
            bucket["actions"] += n
        elif action == "context_collapse":
            bucket["context_collapses"] += n
            bucket["actions"] += n
        elif action == "challenge_start":
            bucket["challenge_starts"] += n
            bucket["actions"] += n
        elif action == "challenge_complete":
            bucket["challenge_completes"] += n
            bucket["actions"] += n
        else:
            bucket["actions"] += n

    rows = []
    totals = {
        "impressions": 0,
        "opens": 0,
        "dismisses": 0,
        "shares": 0,
        "likes": 0,
        "group_expands": 0,
        "context_expands": 0,
        "context_collapses": 0,
        "challenge_starts": 0,
        "challenge_completes": 0,
        "actions": 0,
    }
    for bucket in groups.values():
        impressions = bucket["impressions"]
        for key in totals:
            totals[key] += bucket[key]
        rows.append(
            {
                **bucket,
                "open_rate": round(bucket["opens"] / impressions, 4) if impressions else 0,
                "dismiss_rate": round(bucket["dismisses"] / impressions, 4) if impressions else 0,
                "share_rate": round(bucket["shares"] / impressions, 4) if impressions else 0,
                "context_expand_rate": round(bucket["context_expands"] / impressions, 4)
                if impressions
                else 0,
                "challenge_completion_rate": round(bucket["challenge_completes"] / bucket["challenge_starts"], 4)
                if bucket["challenge_starts"]
                else 0,
            }
        )

    opportunities = []
    for row in rows:
        impressions = row["impressions"]
        if impressions < 10:
            continue
        label = f"{row['surface']} / {row['category']} / {row['item_type']}"
        if row["open_rate"] >= 0.18 or row["share_rate"] >= 0.04:
            opportunities.append(
                {
                    "kind": "promote",
                    "priority": round((row["open_rate"] * 100) + (row["share_rate"] * 250), 2),
                    "label": label,
                    "surface": row["surface"],
                    "category": row["category"],
                    "item_type": row["item_type"],
                    "metric": "open_share_rate",
                    "value": round(row["open_rate"] + row["share_rate"], 4),
                    "impressions": impressions,
                    "recommendation": "Consider a small ranking lift or stronger first-page representation.",
                }
            )
        if row["context_expand_rate"] >= 0.08:
            opportunities.append(
                {
                    "kind": "promote",
                    "priority": round(row["context_expand_rate"] * 120, 2),
                    "label": label,
                    "surface": row["surface"],
                    "category": row["category"],
                    "item_type": row["item_type"],
                    "metric": "context_expand_rate",
                    "value": row["context_expand_rate"],
                    "impressions": impressions,
                    "recommendation": "Users are asking for more context here; consider stronger snippet wording or ranking lift.",
                }
            )
        if row["dismiss_rate"] >= 0.12:
            opportunities.append(
                {
                    "kind": "investigate",
                    "priority": round(row["dismiss_rate"] * 100, 2),
                    "label": label,
                    "surface": row["surface"],
                    "category": row["category"],
                    "item_type": row["item_type"],
                    "metric": "dismiss_rate",
                    "value": row["dismiss_rate"],
                    "impressions": impressions,
                    "recommendation": "Review card wording, repetition, or category weighting before boosting similar items.",
                }
            )
        if impressions >= 50 and row["open_rate"] <= 0.02 and row["share_rate"] == 0:
            opportunities.append(
                {
                    "kind": "downrank",
                    "priority": round((0.02 - row["open_rate"]) * 100 + impressions / 100, 2),
                    "label": label,
                    "surface": row["surface"],
                    "category": row["category"],
                    "item_type": row["item_type"],
                    "metric": "low_open_rate",
                    "value": row["open_rate"],
                    "impressions": impressions,
                    "recommendation": "Candidate for a bounded score cap or improved explanation/media treatment.",
                }
            )

    from app.utils.feed_market_quality import classify_market_quality, editorial_archetype

    signed_in_expr = DiscoverInteraction.user_id.isnot(None).label("signed_in")
    review_result = await db.execute(
        select(
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
            func.max(DiscoverInteraction.item_name).label("item_name"),
            func.max(DiscoverInteraction.category).label("category"),
            DiscoverInteraction.surface,
            signed_in_expr,
            DiscoverInteraction.action,
            func.count(DiscoverInteraction.id).label("count"),
            func.avg(DiscoverInteraction.rank).label("avg_rank"),
            func.avg(DiscoverInteraction.score).label("avg_score"),
        )
        .where(DiscoverInteraction.created_at >= cutoff)
        .group_by(
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
            DiscoverInteraction.surface,
            signed_in_expr,
            DiscoverInteraction.action,
        )
    )

    review_buckets: dict[tuple[str, str, str, str], dict] = {}
    for (
        item_type,
        item_id,
        item_name,
        category,
        surface,
        signed_in,
        action,
        count,
        avg_rank,
        avg_score,
    ) in review_result.all():
        key = (
            item_type or "unknown",
            str(item_id),
            surface or "unknown",
            "signed_in" if signed_in else "anonymous",
        )
        bucket = review_buckets.setdefault(
            key,
            {
                "item_type": key[0],
                "item_id": key[1],
                "item_name": item_name,
                "category": category or "other",
                "surface": key[2],
                "auth_segment": key[3],
                "impressions": 0,
                "opens": 0,
                "dismisses": 0,
                "shares": 0,
                "likes": 0,
                "group_expands": 0,
                "context_expands": 0,
                "avg_rank": None,
                "avg_score": None,
            },
        )
        if item_name:
            bucket["item_name"] = item_name
        if category:
            bucket["category"] = category
        n = int(count or 0)
        if action == "impression":
            bucket["impressions"] += n
            if avg_rank is not None:
                bucket["avg_rank"] = round(float(avg_rank), 1)
            if avg_score is not None:
                bucket["avg_score"] = round(float(avg_score), 1)
        elif action in ("detail_click", "open"):
            bucket["opens"] += n
        elif action == "dismiss":
            bucket["dismisses"] += n
        elif action == "share":
            bucket["shares"] += n
        elif action in ("like", "unlike"):
            bucket["likes"] += n
        elif action == "group_expand":
            bucket["group_expands"] += n
        elif action == "context_expand":
            bucket["context_expands"] += n

    review_decisions_result = await db.execute(
        select(DiscoverReviewDecision)
        .order_by(DiscoverReviewDecision.created_at.desc())
        .limit(500)
    )
    all_review_decisions = []
    seen_review_decision_keys = set()
    for row in review_decisions_result.scalars().all():
        key = (row.item_type, row.item_id, row.surface, row.auth_segment)
        if key in seen_review_decision_keys:
            continue
        seen_review_decision_keys.add(key)
        all_review_decisions.append(row)
    reviewed_keys = {
        (
            row.item_type,
            row.item_id,
            row.surface or "unknown",
            row.auth_segment or "anonymous",
        )
        for row in all_review_decisions
    }

    review_queue = []
    for bucket in review_buckets.values():
        if (
            bucket["item_type"],
            bucket["item_id"],
            bucket["surface"],
            bucket["auth_segment"],
        ) in reviewed_keys:
            continue
        impressions = bucket["impressions"]
        if impressions < 5:
            continue
        open_rate = bucket["opens"] / impressions if impressions else 0
        dismiss_rate = bucket["dismisses"] / impressions if impressions else 0
        share_rate = bucket["shares"] / impressions if impressions else 0
        context_expand_rate = bucket["context_expands"] / impressions if impressions else 0
        avg_rank = bucket["avg_rank"] if bucket["avg_rank"] is not None else 999
        item_name = bucket["item_name"] or ""
        category = bucket["category"] or "other"
        if bucket["item_type"] == "futures":
            quality = classify_market_quality(item_name, category)
            archetype = editorial_archetype(item_name, category)
            family_key = quality.story_key or quality.family_key
        elif bucket["item_type"] == "event":
            archetype = "sports_story"
            family_key = f"event:{category}"
        else:
            archetype = "other"
            family_key = f"{bucket['item_type']}:{category}"

        kind = None
        recommendation = None
        priority = 0.0
        if dismiss_rate >= 0.18 and avg_rank <= 30 and open_rate <= 0.08 and share_rate <= 0.01:
            kind = "downrank"
            priority = (dismiss_rate * 100) + max(0, 30 - avg_rank)
            recommendation = "High dismiss rate for a high-ranked card. Review for score cap, family cap, stale odds, or weak explanation."
        elif open_rate >= 0.20 or share_rate >= 0.03 or context_expand_rate >= 0.10:
            kind = "promote"
            priority = (open_rate * 80) + (share_rate * 250) + (context_expand_rate * 80) + max(0, 30 - avg_rank) / 4
            recommendation = "Users are opening, sharing, or expanding this card. Review for a bounded lift or stronger family representation."
        elif dismiss_rate >= 0.12 and context_expand_rate >= 0.08:
            kind = "investigate"
            priority = (dismiss_rate * 80) + (context_expand_rate * 60)
            recommendation = "Mixed signal: people want more context but also dismiss it. Review wording and snippet length."
        if not kind:
            continue

        review_queue.append(
            {
                **bucket,
                "kind": kind,
                "priority": round(priority, 2),
                "family_key": family_key,
                "archetype": archetype,
                "open_rate": round(open_rate, 4),
                "dismiss_rate": round(dismiss_rate, 4),
                "share_rate": round(share_rate, 4),
                "context_expand_rate": round(context_expand_rate, 4),
                "recommendation": recommendation,
            }
        )

    runtime_config = await _load_discover_runtime_config()

    repeat_result = await db.execute(
        select(
            DiscoverInteraction.session_id,
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
            func.max(DiscoverInteraction.item_name).label("item_name"),
            func.max(DiscoverInteraction.category).label("category"),
            func.max(DiscoverInteraction.surface).label("surface"),
            func.count(DiscoverInteraction.id).label("impressions"),
        )
        .where(
            DiscoverInteraction.created_at >= cutoff,
            DiscoverInteraction.action == "impression",
            DiscoverInteraction.session_id.isnot(None),
        )
        .group_by(
            DiscoverInteraction.session_id,
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
        )
        .having(func.count(DiscoverInteraction.id) > 1)
    )
    repeat_rows = repeat_result.all()
    repeat_extra = sum(max(0, int(row.impressions or 0) - 1) for row in repeat_rows)
    repeat_sessions = {row.session_id for row in repeat_rows if row.session_id}
    repeat_top = sorted(
        [
            {
                "session_id": row.session_id,
                "item_type": row.item_type,
                "item_id": row.item_id,
                "item_name": row.item_name,
                "category": row.category,
                "surface": row.surface,
                "impressions": int(row.impressions or 0),
                "extra_impressions": max(0, int(row.impressions or 0) - 1),
            }
            for row in repeat_rows
        ],
        key=lambda row: row["extra_impressions"],
        reverse=True,
    )[:20]

    impression_items_result = await db.execute(
        select(
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
            func.max(DiscoverInteraction.item_name).label("item_name"),
            func.max(DiscoverInteraction.category).label("category"),
            func.max(DiscoverInteraction.surface).label("surface"),
            func.count(DiscoverInteraction.id).label("impressions"),
        )
        .where(
            DiscoverInteraction.created_at >= cutoff,
            DiscoverInteraction.action == "impression",
            DiscoverInteraction.item_type.in_(("event", "futures")),
        )
        .group_by(DiscoverInteraction.item_type, DiscoverInteraction.item_id)
    )
    impression_items = impression_items_result.all()
    futures_ids = []
    event_ids = []
    for row in impression_items:
        try:
            item_id_int = int(row.item_id)
        except (TypeError, ValueError):
            continue
        if row.item_type == "futures":
            futures_ids.append(item_id_int)
        elif row.item_type == "event":
            event_ids.append(item_id_int)

    futures_by_id = {}
    if futures_ids:
        futures_result = await db.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.status,
                FuturesMarket.updated_at,
                FuturesMarket.resolution_date,
            ).where(FuturesMarket.id.in_(futures_ids))
        )
        futures_by_id = {row.id: row for row in futures_result.all()}

    events_by_id = {}
    if event_ids:
        events_result = await db.execute(
            select(Event.id, Event.status, Event.commence_time).where(Event.id.in_(event_ids))
        )
        events_by_id = {row.id: row for row in events_result.all()}

    now = datetime.now(timezone.utc)
    stale_impressions = 0
    stale_items = []
    for row in impression_items:
        try:
            item_id_int = int(row.item_id)
        except (TypeError, ValueError):
            continue
        impressions = int(row.impressions or 0)
        stale_reason = None
        if row.item_type == "futures":
            market = futures_by_id.get(item_id_int)
            if market:
                updated_at = market.updated_at
                if updated_at and updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                resolution_date = market.resolution_date
                if resolution_date and resolution_date.tzinfo is None:
                    resolution_date = resolution_date.replace(tzinfo=timezone.utc)
                if market.status in ("closed", "resolved"):
                    stale_reason = "closed"
                elif resolution_date and resolution_date < now:
                    stale_reason = "past_resolution"
                elif updated_at and (now - updated_at).total_seconds() / 86400 > runtime_config["stale_no_movement_days"]:
                    stale_reason = "stale_updated_at"
        elif row.item_type == "event":
            event = events_by_id.get(item_id_int)
            if event and event.status in ("completed", "closed"):
                commence_time = event.commence_time
                if commence_time and commence_time.tzinfo is None:
                    commence_time = commence_time.replace(tzinfo=timezone.utc)
                if commence_time and (now - commence_time).total_seconds() > 8 * 3600:
                    stale_reason = "completed_old"
        if stale_reason:
            stale_impressions += impressions
            stale_items.append(
                {
                    "item_type": row.item_type,
                    "item_id": row.item_id,
                    "item_name": row.item_name,
                    "category": row.category,
                    "surface": row.surface,
                    "impressions": impressions,
                    "reason": stale_reason,
                }
            )
    stale_items.sort(key=lambda row: row["impressions"], reverse=True)

    recent_decisions = [
        row
        for row in all_review_decisions
        if row.created_at and row.created_at.replace(tzinfo=row.created_at.tzinfo or timezone.utc) >= cutoff
    ][:20]

    top_items_result = await db.execute(
        select(
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
            func.max(DiscoverInteraction.item_name).label("item_name"),
            func.max(DiscoverInteraction.category).label("category"),
            func.max(DiscoverInteraction.surface).label("surface"),
            func.count(DiscoverInteraction.id).label("actions"),
        )
        .where(
            DiscoverInteraction.created_at >= cutoff,
            DiscoverInteraction.action != "impression",
        )
        .group_by(DiscoverInteraction.item_type, DiscoverInteraction.item_id)
        .order_by(func.count(DiscoverInteraction.id).desc())
        .limit(20)
    )

    return {
        "days": days,
        "totals": {
            **totals,
            "open_rate": round(totals["opens"] / totals["impressions"], 4) if totals["impressions"] else 0,
            "dismiss_rate": round(totals["dismisses"] / totals["impressions"], 4) if totals["impressions"] else 0,
            "share_rate": round(totals["shares"] / totals["impressions"], 4) if totals["impressions"] else 0,
            "context_expand_rate": round(totals["context_expands"] / totals["impressions"], 4)
            if totals["impressions"]
            else 0,
            "challenge_completion_rate": round(totals["challenge_completes"] / totals["challenge_starts"], 4)
            if totals["challenge_starts"]
            else 0,
        },
        "groups": sorted(rows, key=lambda r: (r["surface"], -r["impressions"], r["category"]))[:100],
        "opportunities": sorted(opportunities, key=lambda r: r["priority"], reverse=True)[:20],
        "review_queue": sorted(review_queue, key=lambda r: r["priority"], reverse=True)[:50],
        "runtime_config": runtime_config,
        "launch_health": {
            "repeat_extra_impressions": repeat_extra,
            "repeat_rate": round(repeat_extra / totals["impressions"], 4) if totals["impressions"] else 0,
            "repeat_sessions": len(repeat_sessions),
            "stale_impressions": stale_impressions,
            "stale_rate": round(stale_impressions / totals["impressions"], 4) if totals["impressions"] else 0,
            "top_repeat_items": repeat_top,
            "top_stale_items": stale_items[:20],
        },
        "recent_review_decisions": [
            {
                "id": row.id,
                "item_type": row.item_type,
                "item_id": row.item_id,
                "item_name": row.item_name,
                "category": row.category,
                "surface": row.surface,
                "auth_segment": row.auth_segment,
                "family_key": row.family_key,
                "archetype": row.archetype,
                "decision": row.decision,
                "admin_notes": row.admin_notes,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in recent_decisions
        ],
        "top_items": [
            {
                "item_type": item_type,
                "item_id": item_id,
                "item_name": item_name,
                "category": category,
                "surface": surface,
                "actions": int(actions or 0),
            }
            for item_type, item_id, item_name, category, surface, actions in top_items_result.all()
        ],
    }


@router.get("/bug-reports")
async def list_bug_reports(
    request: Request,
    secret: str = Query(None),
    status: str = Query(None),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db),
):
    if not await _check_admin_auth(secret, request, db):
        raise HTTPException(status_code=403, detail="Unauthorized")

    query = select(BugReport).order_by(BugReport.created_at.desc()).limit(limit)
    if status:
        query = query.where(BugReport.status == status)

    result = await db.execute(query)
    reports = result.scalars().all()

    auto_category_updates: dict[str, list[int]] = {}
    for report in reports:
        if report.category:
            continue
        suggested_category = _suggest_bug_report_category(
            report.description,
            report.app_state,
        )
        if not suggested_category:
            continue
        report.category = suggested_category
        auto_category_updates.setdefault(suggested_category, []).append(report.id)

    if auto_category_updates:
        for category_name, report_ids in auto_category_updates.items():
            await db.execute(
                update(BugReport)
                .where(BugReport.id.in_(report_ids))
                .values(category=category_name)
            )
        await db.commit()

    return {
        "reports": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "session_id": r.session_id,
                "description": r.description,
                "has_screenshot": r.screenshot_base64 is not None,
                "app_state": r.app_state,
                "status": r.status,
                "category": r.category,
                "admin_notes": r.admin_notes,
                "backlog_ref": r.backlog_ref,
                "resolution_summary": r.resolution_summary,
                "user_email": r.user_email,
                "notification_sent_at": r.notification_sent_at.isoformat() if r.notification_sent_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ],
        "count": len(reports),
    }


@router.patch("/bug-reports/{report_id}")
async def update_bug_report(
    report_id: int,
    request: Request,
    secret: str = Query(None),
    status: str = Query(None),
    category: str = Query(None),
    admin_notes: str = Query(None),
    resolution_summary: str = Query(None),
    backlog_ref: str = Query(None),
    user_email: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if not await _check_admin_auth(secret, request, db):
        raise HTTPException(status_code=403, detail="Unauthorized")

    _VALID_STATUSES = {"new", "reviewed", "in_progress", "fixed", "wont_fix", "duplicate", "actioned", "dismissed"}
    values = {}
    if status:
        if status not in _VALID_STATUSES:
            raise HTTPException(400, f"Invalid status. Must be one of: {sorted(_VALID_STATUSES)}")
        values["status"] = status
    if category is not None:
        if category and category not in _VALID_BUG_CATEGORIES:
            raise HTTPException(400, f"Invalid category. Must be one of: {sorted(_VALID_BUG_CATEGORIES)}")
        values["category"] = category or None
    if admin_notes is not None:
        if len(admin_notes) > 5000:
            raise HTTPException(400, "Admin notes too long (max 5000 chars)")
        values["admin_notes"] = admin_notes
    if resolution_summary is not None:
        values["resolution_summary"] = resolution_summary
    if backlog_ref is not None:
        values["backlog_ref"] = backlog_ref
    if user_email is not None:
        values["user_email"] = user_email or None

    notification_state = None
    if values:
        if status in _BUG_FIXED_EMAIL_STATUSES:
            current_result = await db.execute(
                select(
                    BugReport.status,
                    BugReport.resolution_summary,
                    BugReport.notification_sent_at,
                ).where(BugReport.id == report_id)
            )
            notification_state = current_result.first()
            if notification_state is None:
                raise HTTPException(404, f"Bug report {report_id} not found")

        result = await db.execute(
            update(BugReport).where(BugReport.id == report_id).values(**values)
        )
        if result.rowcount == 0:
            raise HTTPException(404, f"Bug report {report_id} not found")
        await db.commit()

        if notification_state is not None:
            final_resolution_summary = (
                resolution_summary
                if resolution_summary is not None
                else notification_state.resolution_summary
            )
            if _should_enqueue_bug_fixed_email(
                previous_status=notification_state.status,
                final_status=status,
                final_resolution_summary=final_resolution_summary,
                notification_sent_at=notification_state.notification_sent_at,
            ):
                _enqueue_bug_fixed_email(report_id)

    return {"status": "ok"}


@router.get("/bug-reports/{report_id}/screenshot")
async def get_bug_screenshot(
    report_id: int,
    request: Request,
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if not await _check_admin_auth(secret, request, db):
        raise HTTPException(status_code=403, detail="Unauthorized")

    result = await db.execute(
        select(BugReport.screenshot_base64).where(BugReport.id == report_id)
    )
    b64 = result.scalar_one_or_none()
    if not b64:
        raise HTTPException(status_code=404, detail="No screenshot")

    import base64
    from fastapi.responses import Response
    try:
        image_data = base64.b64decode(b64)
    except Exception:
        raise HTTPException(400, "Invalid screenshot data")
    media_type = "image/png" if image_data[:4] == b"\x89PNG" else "image/jpeg"
    return Response(content=image_data, media_type=media_type)


@router.post("/daily-digest/test")
async def test_daily_digest(
    request: Request,
    secret: str = Query(None),
    email: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Send a test daily digest email."""
    if not await _check_admin_auth(secret, request, db):
        raise HTTPException(status_code=403, detail="Unauthorized")

    if not email:
        raise HTTPException(400, "email query parameter required")

    from app.tasks.daily_digest import send_daily_digest
    success = await send_daily_digest(db, to_email=email)
    return {"status": "sent" if success else "no_content", "to": email}
