"""API endpoints for ranking judgments (Discover feed review)."""

import csv
import hashlib
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import FuturesMarket, FuturesOutcome, RankingJudgment, Sport
from app.routes.admin_utils import _check_admin_auth, _check_admin_secret, _resolve_admin_email
from app.services import get_db, get_db_rw
from app.utils.discover_reason_tags import canonical_reason_tags
from app.utils.feed_market_quality import classify_market_quality, editorial_archetype
from app.utils.labeling_queue import load_reviewed_ranking_keys

router = APIRouter(prefix="/admin/ranking-judgments", tags=["admin-judgments"])
logger = logging.getLogger(__name__)


class RankingJudgmentCreate(BaseModel):
    secret: str | None = None
    surface: str | None = None
    rank_seen: int | None = None
    item_type: str | None = None
    market_id: int | None = None
    event_id: int | None = None
    market_name: str | None = None
    label: str | None = None
    reason_tags: list[str] | str | None = None
    better_than: str | None = None
    worse_than: str | None = None
    notes: str | None = None
    score_at_review: float | None = None
    category_at_review: str | None = None
    archetype_at_review: str | None = None
    quality_class_at_review: str | None = None
    headline_at_review: str | None = None
    feed_request_id: str | None = None
    card_snapshot: dict[str, Any] | None = None
    label_metadata: dict[str, Any] | None = None
    would_be_interesting_if: str | None = None
    fixable_interest_score: int | None = None
    fix_type: str | None = None
    desired_entity_or_variant: str | None = None
    current_entity_or_variant: str | None = None
    create_issue_candidate: bool | None = None
    fixable_interesting: bool | None = None
    repair_type: str | None = None
    repair_target_entity: str | None = None
    repair_note: str | None = None
    reviewer: str | None = None


class FixableInterestClusterTriage(BaseModel):
    secret: str | None = None
    status: str
    github_issue_url: str | None = None
    github_issue_number: int | None = None
    experiment_key: str | None = None
    notes: str | None = None
    owner: str | None = None


DEFAULT_LABELING_STRATA = [
    "top_feed_like",
    "fresh_public_story",
    "stale_fixable",
    "weather",
    "finance_ladder",
    "low_confidence",
    "duplicate_group",
    "explanation_image_gap",
    "movement_boundary",
    "low_volume_editorial",
]

PUBLIC_STORY_CATEGORIES = (
    "politics",
    "geopolitics",
    "economics",
    "tech",
    "entertainment",
    "culture",
    "health",
    "weather",
)


def _parse_candidate_strata(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_LABELING_STRATA)
    requested = [part.strip() for part in value.split(",") if part.strip()]
    allowed = set(DEFAULT_LABELING_STRATA)
    return [stratum for stratum in requested if stratum in allowed] or list(
        DEFAULT_LABELING_STRATA
    )


def _labeling_stratum_query(stratum: str, *, now: datetime, limit: int):
    base_filters = [
        FuturesMarket.status == "open",
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date > now,
        ),
    ]

    if stratum == "top_feed_like":
        filters = base_filters
        ordering = [
            FuturesMarket.volume_24h.desc().nulls_last(),
            FuturesMarket.market_tier.asc().nulls_last(),
            FuturesMarket.updated_at.desc().nulls_last(),
        ]
    elif stratum == "fresh_public_story":
        filters = [
            *base_filters,
            FuturesMarket.llm_sport_category.in_(PUBLIC_STORY_CATEGORIES),
            FuturesMarket.created_at >= now - timedelta(days=14),
        ]
        ordering = [
            FuturesMarket.created_at.desc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        ]
    elif stratum == "stale_fixable":
        filters = [
            *base_filters,
            or_(
                FuturesMarket.hook_generated_at < now - timedelta(days=10),
                FuturesMarket.updated_at < now - timedelta(days=14),
            ),
            or_(
                FuturesMarket.hook_description.isnot(None),
                FuturesMarket.image_url.isnot(None),
            ),
        ]
        ordering = [
            FuturesMarket.updated_at.asc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        ]
    elif stratum == "weather":
        filters = [
            *base_filters,
            FuturesMarket.name.op("~*")(
                r"\m(weather|temperature|hurricane|rain|rainfall|precipitation|"
                r"snow|tornado|wildfire|heat)\M"
            ),
        ]
        ordering = [
            FuturesMarket.resolution_date.asc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        ]
    elif stratum == "finance_ladder":
        filters = [
            *base_filters,
            or_(
                FuturesMarket.name.ilike("%S&P%"),
                FuturesMarket.name.ilike("%SPX%"),
                FuturesMarket.name.ilike("%Nasdaq%"),
                FuturesMarket.name.ilike("%WTI%"),
                FuturesMarket.name.ilike("%oil%"),
                FuturesMarket.name.ilike("%CPI%"),
                FuturesMarket.name.ilike("%Fed%"),
                FuturesMarket.name.ilike("%rate%"),
            ),
        ]
        ordering = [
            FuturesMarket.resolution_date.asc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        ]
    elif stratum == "low_confidence":
        # Markets near the ranking boundary (score ~30-50 proxy): moderate
        # volume but not top-tier, with some enrichment. These sit at the
        # edge of feed inclusion and are the most valuable for calibrating
        # the scoring function.
        filters = [
            *base_filters,
            FuturesMarket.volume_24h.isnot(None),
            FuturesMarket.volume_24h > 0,
            FuturesMarket.volume_24h < 5000,
            or_(
                FuturesMarket.hook_description.isnot(None),
                FuturesMarket.image_url.isnot(None),
            ),
            FuturesMarket.llm_sport_category.isnot(None),
        ]
        ordering = [
            FuturesMarket.volume_24h.desc().nulls_last(),
            FuturesMarket.max_movement_24h.desc().nulls_last(),
            FuturesMarket.updated_at.desc().nulls_last(),
        ]
    elif stratum == "duplicate_group":
        filters = [*base_filters, FuturesMarket.group_id.isnot(None)]
        ordering = [
            FuturesMarket.group_id.asc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        ]
    elif stratum == "explanation_image_gap":
        filters = [
            *base_filters,
            or_(
                FuturesMarket.hook_description.is_(None),
                FuturesMarket.image_url.is_(None),
            ),
        ]
        ordering = [
            FuturesMarket.volume_24h.desc().nulls_last(),
            FuturesMarket.updated_at.desc().nulls_last(),
        ]
    elif stratum == "movement_boundary":
        filters = [
            *base_filters,
            FuturesMarket.max_movement_24h.isnot(None),
            FuturesMarket.max_movement_24h > 0,
        ]
        ordering = [
            FuturesMarket.max_movement_24h.desc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        ]
    else:
        filters = [
            *base_filters,
            or_(
                FuturesMarket.hook_description.isnot(None),
                FuturesMarket.image_url.isnot(None),
            ),
            or_(FuturesMarket.volume_24h.is_(None), FuturesMarket.volume_24h < 1000),
        ]
        ordering = [
            FuturesMarket.updated_at.desc().nulls_last(),
            FuturesMarket.created_at.desc().nulls_last(),
        ]

    return (
        select(FuturesMarket)
        .options(
            selectinload(FuturesMarket.outcomes).load_only(
                FuturesOutcome.id,
                FuturesOutcome.name,
                FuturesOutcome.current_probability,
                FuturesOutcome.probability_change_24h,
                FuturesOutcome.rank,
            ),
            selectinload(FuturesMarket.sport).load_only(Sport.key, Sport.name),
        )
        .where(*filters)
        .order_by(*ordering)
        .limit(limit)
    )


def _serialize_labeling_candidate(
    market: FuturesMarket,
    *,
    rank: int,
    stratum: str,
) -> dict[str, Any]:
    outcomes = sorted(
        market.outcomes or [],
        key=lambda outcome: (
            float(outcome.current_probability)
            if outcome.current_probability is not None
            else 0.0
        ),
        reverse=True,
    )
    top_outcomes = [
        {
            "id": outcome.id,
            "name": outcome.name,
            "probability": (
                float(outcome.current_probability)
                if outcome.current_probability is not None
                else None
            ),
            "movement": (
                float(outcome.probability_change_24h)
                if outcome.probability_change_24h is not None
                else None
            ),
            "rank": outcome.rank,
        }
        for outcome in outcomes[:5]
    ]
    category = (
        market.llm_sport_category
        or (market.sport.name if market.sport else None)
        or "?"
    )
    quality = classify_market_quality(
        market_name=market.name,
        sport_category=category,
        outcome_names=[outcome["name"] for outcome in top_outcomes if outcome.get("name")],
    )
    return {
        "rank": rank,
        "type": "futures",
        "item_type": "futures",
        "id": market.id,
        "market_id": market.id,
        "stable_id": f"futures:{market.id}",
        "name": market.name,
        "category": category,
        "archetype": editorial_archetype(market.name, category),
        "source": market.source,
        "stratum": stratum,
        "selection_reason": f"labeling:{stratum}",
        "candidate_source": "labeling_sampler_v1",
        "score": 0.0,
        "headline": None,
        "reason": None,
        "context": market.description,
        "hook_description": market.hook_description,
        "image_url": market.image_url,
        "group_id": market.group_id,
        "quality_class": quality.quality_class,
        "family_key": quality.family_key,
        "story_key": quality.story_key,
        "ladder": quality.is_ladder_or_bucket,
        "reasons": quality.reasons,
        "top_outcomes": top_outcomes,
        "rendered_probability": top_outcomes[0]["probability"] if top_outcomes else None,
        "resolution_date": (
            market.resolution_date.isoformat() if market.resolution_date else None
        ),
        "created_at": market.created_at.isoformat() if market.created_at else None,
        "updated_at": market.updated_at.isoformat() if market.updated_at else None,
    }


def _merged_value(
    body: dict[str, Any],
    key: str,
    query_value: Any,
    default: Any = None,
) -> Any:
    if query_value is not None:
        return query_value
    if key in body:
        return body[key]
    return default


def _normalize_reason_tags(value: list[str] | str | None) -> list[str]:
    return canonical_reason_tags(value)


def _serialize_judgment(judgment: RankingJudgment) -> dict[str, Any]:
    metadata = judgment.label_metadata or {}
    return {
        "id": judgment.id,
        "date": str(judgment.date) if judgment.date else None,
        "surface": judgment.surface,
        "rank_seen": judgment.rank_seen,
        "item_type": judgment.item_type,
        "market_id": judgment.market_id,
        "event_id": judgment.event_id,
        "market_name": judgment.market_name,
        "label": judgment.label,
        "reason_tags": canonical_reason_tags(judgment.reason_tags),
        "better_than": judgment.better_than,
        "worse_than": judgment.worse_than,
        "notes": judgment.notes,
        "score_at_review": judgment.score_at_review,
        "category_at_review": judgment.category_at_review,
        "archetype_at_review": judgment.archetype_at_review,
        "quality_class_at_review": judgment.quality_class_at_review,
        "headline_at_review": judgment.headline_at_review,
        "feed_request_id": judgment.feed_request_id,
        "label_metadata": metadata,
        "card_snapshot": metadata.get("card_snapshot") if isinstance(metadata, dict) else None,
        "fixable_interesting": judgment.fixable_interesting,
        "repair_type": judgment.repair_type,
        "repair_target_entity": judgment.repair_target_entity,
        "repair_note": judgment.repair_note,
        "reviewer": judgment.reviewer,
        "created_at": judgment.created_at.isoformat() if judgment.created_at else None,
    }


def _metadata_dict(judgment: RankingJudgment) -> dict[str, Any]:
    return judgment.label_metadata if isinstance(judgment.label_metadata, dict) else {}


def _fixable_interest(metadata: dict[str, Any]) -> dict[str, Any]:
    fixable = metadata.get("fixable_interest")
    return fixable if isinstance(fixable, dict) else {}


def _card_snapshot(metadata: dict[str, Any]) -> dict[str, Any]:
    snapshot = metadata.get("card_snapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def _has_fixable_interest(fixable: dict[str, Any]) -> bool:
    return any(
        fixable.get(key) not in (None, "", False)
        for key in (
            "would_be_interesting_if",
            "fixable_interest_score",
            "fix_type",
            "desired_entity_or_variant",
            "current_entity_or_variant",
            "create_issue_candidate",
        )
    )


def _cluster_identity(judgment: RankingJudgment) -> dict[str, str]:
    metadata = _metadata_dict(judgment)
    fixable = _fixable_interest(metadata)
    snapshot = _card_snapshot(metadata)
    item_key = (
        snapshot.get("group_id")
        or snapshot.get("story_key")
        or snapshot.get("family_key")
        or f"{judgment.item_type}:{judgment.market_id or judgment.event_id or judgment.id}"
    )
    return {
        "fix_type": str(fixable.get("fix_type") or "unspecified"),
        "item_key": str(item_key or "unknown"),
        "desired_entity_or_variant": str(fixable.get("desired_entity_or_variant") or ""),
        "current_entity_or_variant": str(fixable.get("current_entity_or_variant") or ""),
    }


def _cluster_id(identity: dict[str, str]) -> str:
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return "fix_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _triage_status(fixable: dict[str, Any]) -> str:
    triage = fixable.get("triage")
    if isinstance(triage, dict) and triage.get("status"):
        return str(triage["status"])
    return "open"


def _serialize_fixable_cluster(cluster_id: str, rows: list[RankingJudgment]) -> dict[str, Any]:
    rows = sorted(rows, key=lambda row: row.created_at or row.date, reverse=True)
    representative = rows[0]
    metadata = _metadata_dict(representative)
    fixable = _fixable_interest(metadata)
    snapshot = _card_snapshot(metadata)
    identity = _cluster_identity(representative)

    status_counts: dict[str, int] = {}
    categories: set[str] = set()
    labels: set[str] = set()
    market_ids: set[int] = set()
    affected_ranks: list[int] = []
    issue_candidates = 0
    max_score: int | None = None
    latest_triage: dict[str, Any] | None = None

    for row in rows:
        row_metadata = _metadata_dict(row)
        row_fixable = _fixable_interest(row_metadata)
        status = _triage_status(row_fixable)
        status_counts[status] = status_counts.get(status, 0) + 1
        row_snapshot = _card_snapshot(row_metadata)
        if row.category_at_review:
            categories.add(row.category_at_review)
        elif row_snapshot.get("category"):
            categories.add(str(row_snapshot["category"]))
        if row.label:
            labels.add(row.label)
        if row.market_id is not None:
            market_ids.add(row.market_id)
        if row.rank_seen is not None:
            affected_ranks.append(row.rank_seen)
        if row_fixable.get("create_issue_candidate"):
            issue_candidates += 1
        try:
            score = int(row_fixable.get("fixable_interest_score"))
            max_score = score if max_score is None else max(max_score, score)
        except (TypeError, ValueError):
            pass
        triage = row_fixable.get("triage")
        if isinstance(triage, dict) and triage.get("status") != "open":
            latest_triage = triage

    if status_counts and status_counts.get("open", 0) == len(rows):
        status = "open"
    elif "linked" in status_counts:
        status = "linked"
    elif "experiment" in status_counts:
        status = "experiment"
    elif "dismissed" in status_counts and status_counts["dismissed"] == len(rows):
        status = "dismissed"
    else:
        status = max(status_counts.items(), key=lambda item: item[1])[0]

    return {
        "cluster_id": cluster_id,
        "status": status,
        "triage": latest_triage or {},
        "triage_counts": status_counts,
        "fix_type": identity["fix_type"],
        "item_key": identity["item_key"],
        "story_key": snapshot.get("story_key"),
        "family_key": snapshot.get("family_key"),
        "group_id": snapshot.get("group_id"),
        "desired_entity_or_variant": fixable.get("desired_entity_or_variant") or "",
        "current_entity_or_variant": fixable.get("current_entity_or_variant") or "",
        "would_be_interesting_if": fixable.get("would_be_interesting_if") or "",
        "count": len(rows),
        "issue_candidate_count": issue_candidates,
        "max_fixable_interest_score": max_score,
        "latest_created_at": representative.created_at.isoformat() if representative.created_at else None,
        "categories": sorted(categories),
        "labels": sorted(labels),
        "affected_ranks": sorted(set(affected_ranks)),
        "market_ids": sorted(market_ids),
        "examples": [_serialize_fixable_example(row) for row in rows[:3]],
    }


def _serialize_fixable_example(judgment: RankingJudgment) -> dict[str, Any]:
    metadata = _metadata_dict(judgment)
    fixable = _fixable_interest(metadata)
    snapshot = _card_snapshot(metadata)
    return {
        "judgment_id": judgment.id,
        "created_at": judgment.created_at.isoformat() if judgment.created_at else None,
        "market_id": judgment.market_id,
        "event_id": judgment.event_id,
        "market_name": judgment.market_name,
        "snapshot_name": snapshot.get("name"),
        "label": judgment.label,
        "rank_seen": judgment.rank_seen,
        "score_at_review": judgment.score_at_review,
        "would_be_interesting_if": fixable.get("would_be_interesting_if") or "",
        "notes": judgment.notes,
        "card_snapshot": snapshot,
    }


def _build_fixable_clusters(rows: list[RankingJudgment]) -> list[dict[str, Any]]:
    grouped: dict[str, list[RankingJudgment]] = {}
    for row in rows:
        metadata = _metadata_dict(row)
        fixable = _fixable_interest(metadata)
        if not _has_fixable_interest(fixable):
            continue
        cluster_id = _cluster_id(_cluster_identity(row))
        grouped.setdefault(cluster_id, []).append(row)
    clusters = [
        _serialize_fixable_cluster(cluster_id, cluster_rows)
        for cluster_id, cluster_rows in grouped.items()
    ]
    clusters.sort(
        key=lambda cluster: (
            cluster["status"] != "open",
            -(cluster["max_fixable_interest_score"] or 0),
            -cluster["issue_candidate_count"],
            -cluster["count"],
            cluster["latest_created_at"] or "",
        )
    )
    return clusters


def _structured_label_metadata(
    body: dict[str, Any],
    explicit_metadata: Any,
) -> dict[str, Any] | None:
    metadata = dict(explicit_metadata) if isinstance(explicit_metadata, dict) else {}
    card_snapshot = body.get("card_snapshot")
    if card_snapshot is None:
        card_snapshot = metadata.pop("card_snapshot", None)
    if isinstance(card_snapshot, dict):
        metadata["card_snapshot"] = _normalize_card_snapshot(card_snapshot)

    fixable_keys = [
        "would_be_interesting_if",
        "fixable_interest_score",
        "fix_type",
        "desired_entity_or_variant",
        "current_entity_or_variant",
        "create_issue_candidate",
    ]
    top_level_fixable = {
        key: metadata.pop(key)
        for key in list(metadata.keys())
        if key in fixable_keys and metadata[key] not in (None, "")
    }
    fixable = {
        key: body[key]
        for key in fixable_keys
        if key in body and body[key] not in (None, "")
    }
    if top_level_fixable:
        fixable = {**top_level_fixable, **fixable}
    if fixable:
        existing = metadata.get("fixable_interest")
        if isinstance(existing, dict):
            fixable = {**existing, **fixable}
        metadata["fixable_interest"] = fixable
    return metadata or None


def _normalize_card_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Keep a compact, stable copy of the card state the reviewer saw."""

    allowed_keys = [
        "batch_id",
        "feed_request_id",
        "rank",
        "item_type",
        "item_id",
        "market_id",
        "event_id",
        "name",
        "source",
        "category",
        "archetype",
        "quality_class",
        "headline",
        "reason",
        "context",
        "hook_description",
        "image_url",
        "story_key",
        "family_key",
        "group_id",
        "score",
        "rendered_probability",
        "top_outcomes",
        "reasons",
        "has_hook",
        "has_image",
        "explanation_ok",
        "stratum",
        "selection_reason",
    ]
    normalized: dict[str, Any] = {}
    for key in allowed_keys:
        value = snapshot.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, (str, int, float, bool)):
            normalized[key] = value
        elif key in {"top_outcomes", "reasons"} and isinstance(value, list):
            normalized[key] = value[:5] if key == "top_outcomes" else value[:12]
        elif isinstance(value, dict):
            normalized[key] = value
    normalized["schema_version"] = snapshot.get("schema_version") or "discover-card-v1"
    return normalized


@router.post("")
async def create_judgment(
    request: Request,
    payload: RankingJudgmentCreate | None = Body(None),
    db: AsyncSession = Depends(get_db_rw),
    secret: str | None = Query(None),
    surface: str | None = Query(None),
    rank_seen: int | None = Query(None),
    item_type: str | None = Query(None),
    market_id: int | None = Query(None),
    event_id: int | None = Query(None),
    market_name: str | None = Query(None),
    label: str | None = Query(None),
    reason_tags: str | None = Query(None),
    better_than: str | None = Query(None),
    worse_than: str | None = Query(None),
    notes: str | None = Query(None),
    score_at_review: float | None = Query(None),
    category_at_review: str | None = Query(None),
    archetype_at_review: str | None = Query(None),
    quality_class_at_review: str | None = Query(None),
    headline_at_review: str | None = Query(None),
    feed_request_id: str | None = Query(None),
    fixable_interesting: bool | None = Query(None),
    repair_type: str | None = Query(None),
    repair_target_entity: str | None = Query(None),
    repair_note: str | None = Query(None),
    reviewer: str | None = Query(None),
):
    body = payload.model_dump(exclude_unset=True) if payload else {}
    secret_value = _merged_value(body, "secret", secret)
    if not _check_admin_secret(secret_value) and not await _check_admin_auth(
        secret_value, request, db
    ):
        raise HTTPException(status_code=403, detail="Admin access required")

    label_value = _merged_value(body, "label", label)
    if not label_value:
        raise HTTPException(status_code=400, detail="label is required")

    # Resolve reviewer identity: when the caller passes "native" (iOS default)
    # and is authenticated via Bearer token, persist the admin user's email so
    # server-side reviewed-state is per-user rather than a shared pool.
    reviewer_value = _merged_value(body, "reviewer", reviewer, "alex")
    if reviewer_value == "native":
        admin_email = await _resolve_admin_email(request, db)
        if admin_email:
            reviewer_value = admin_email

    judgment = RankingJudgment(
        surface=_merged_value(body, "surface", surface, "discover"),
        rank_seen=_merged_value(body, "rank_seen", rank_seen),
        item_type=_merged_value(body, "item_type", item_type, "futures"),
        market_id=_merged_value(body, "market_id", market_id),
        event_id=_merged_value(body, "event_id", event_id),
        market_name=_merged_value(body, "market_name", market_name),
        label=label_value,
        reason_tags=_normalize_reason_tags(
            _merged_value(body, "reason_tags", reason_tags)
        ),
        better_than=_merged_value(body, "better_than", better_than),
        worse_than=_merged_value(body, "worse_than", worse_than),
        notes=_merged_value(body, "notes", notes),
        score_at_review=_merged_value(body, "score_at_review", score_at_review),
        category_at_review=_merged_value(body, "category_at_review", category_at_review),
        archetype_at_review=_merged_value(
            body, "archetype_at_review", archetype_at_review
        ),
        quality_class_at_review=_merged_value(
            body, "quality_class_at_review", quality_class_at_review
        ),
        headline_at_review=_merged_value(body, "headline_at_review", headline_at_review),
        feed_request_id=_merged_value(body, "feed_request_id", feed_request_id),
        label_metadata=_structured_label_metadata(
            body,
            _merged_value(body, "label_metadata", None),
        ),
        fixable_interesting=bool(
            _merged_value(body, "fixable_interesting", fixable_interesting, False)
        ),
        repair_type=_merged_value(body, "repair_type", repair_type),
        repair_target_entity=_merged_value(
            body, "repair_target_entity", repair_target_entity
        ),
        repair_note=_merged_value(body, "repair_note", repair_note),
        reviewer=reviewer_value,
    )
    db.add(judgment)
    await db.commit()
    await db.refresh(judgment)
    return {"status": "ok", "id": judgment.id, "label": judgment.label}


@router.get("/candidates")
async def list_labeling_candidates(
    request: Request,
    secret: str | None = Query(None),
    reviewer: str | None = Query("native"),
    reviewed_surface: str | None = Query("native_discover"),
    strata: str | None = Query(
        None,
        description="Comma-separated labeling strata. Defaults to all supported strata.",
    ),
    limit: int = Query(40, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin_secret(secret) and not await _check_admin_auth(
        secret, request, db
    ):
        raise HTTPException(status_code=403, detail="Admin access required")

    # Resolve reviewer: when "native" and authenticated via Bearer token,
    # use the admin's email for per-user reviewed state.
    effective_reviewer = reviewer
    if reviewer == "native":
        admin_email = await _resolve_admin_email(request, db)
        if admin_email:
            effective_reviewer = admin_email

    now = datetime.now(timezone.utc)
    selected_strata = _parse_candidate_strata(strata)
    per_stratum_limit = min(100, max(limit * 2, 40))
    reviewed_keys = await load_reviewed_ranking_keys(
        db,
        reviewer=effective_reviewer,
        surface=reviewed_surface,
    )

    sampled: list[tuple[str, FuturesMarket]] = []
    seen_market_ids: set[int] = set()
    stratum_counts: dict[str, int] = {}
    for stratum in selected_strata:
        result = await db.execute(
            _labeling_stratum_query(
                stratum,
                now=now,
                limit=per_stratum_limit,
            )
        )
        rows = result.scalars().unique().all()
        stratum_counts[stratum] = len(rows)
        for market in rows:
            if market.id in seen_market_ids:
                continue
            seen_market_ids.add(market.id)
            sampled.append((stratum, market))

    candidates: list[dict[str, Any]] = []
    filtered_reviewed = 0
    for stratum, market in sampled:
        if ("futures", market.id) in reviewed_keys:
            filtered_reviewed += 1
            continue
        candidates.append(
            _serialize_labeling_candidate(
                market,
                rank=len(candidates) + 1,
                stratum=stratum,
            )
        )

    return {
        "items": candidates[:limit],
        "total_available": len(candidates),
        "limit": limit,
        "offset": 0,
        "has_more": len(candidates) > limit,
        "candidate_source": "labeling_sampler_v1",
        "strata": selected_strata,
        "stratum_sample_counts": stratum_counts,
        "reviewed_filter": {
            "enabled": True,
            "reviewer": effective_reviewer,
            "surface": reviewed_surface,
            "reviewed_key_count": len(reviewed_keys),
            "filtered_count": filtered_reviewed,
        },
    }


@router.get("")
async def list_judgments(
    db: AsyncSession = Depends(get_db),
    secret: str = Query(...),
    limit: int = Query(50),
    offset: int = Query(0),
    label: str | None = Query(None),
    surface: str | None = Query(None),
):
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    q = select(RankingJudgment).order_by(desc(RankingJudgment.created_at))
    count_q = select(func.count(RankingJudgment.id))

    if label:
        q = q.where(RankingJudgment.label == label)
        count_q = count_q.where(RankingJudgment.label == label)
    if surface:
        q = q.where(RankingJudgment.surface == surface)
        count_q = count_q.where(RankingJudgment.surface == surface)

    total = (await db.execute(count_q)).scalar() or 0
    rows = (await db.execute(q.limit(limit).offset(offset))).scalars().all()

    summary_q = select(
        RankingJudgment.label,
        func.count(RankingJudgment.id),
    ).group_by(RankingJudgment.label)
    summary_rows = (await db.execute(summary_q)).all()
    summary = {row[0]: row[1] for row in summary_rows}

    return {
        "total": total,
        "summary": summary,
        "judgments": [_serialize_judgment(judgment) for judgment in rows],
    }


@router.get("/coverage")
async def labeling_coverage(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str | None = Query(None),
    window: str = Query(
        "all",
        description="Time window: 24h, 7d, 30d, or all",
    ),
):
    """Coverage dashboard for labeling effort.

    Returns reviewed counts grouped by stratum, verdict, category, and
    reviewer (hashed), plus queue health showing unreviewed candidates
    per stratum.
    """
    if not _check_admin_secret(secret) and not await _check_admin_auth(
        secret, request, db
    ):
        raise HTTPException(status_code=403, detail="Admin access required")

    now = datetime.now(timezone.utc)
    window_map = {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    base_filters: list = []
    if window in window_map:
        cutoff = now - window_map[window]
        base_filters.append(RankingJudgment.created_at >= cutoff)

    judgment_q = select(RankingJudgment)
    for f in base_filters:
        judgment_q = judgment_q.where(f)

    stratum_rows = (await db.execute(judgment_q)).scalars().all()

    by_stratum: dict[str, dict[str, int]] = {}
    by_verdict: dict[str, int] = {}
    by_category: dict[str, dict[str, int]] = {}
    by_reviewer: dict[str, int] = {}
    reviewer_daily: dict[str, dict[str, int]] = {}
    total_reviewed = 0
    today_str = now.strftime("%Y-%m-%d")
    week_ago = now - timedelta(days=7)

    for j in stratum_rows:
        total_reviewed += 1
        metadata = j.label_metadata if isinstance(j.label_metadata, dict) else {}
        snapshot = metadata.get("card_snapshot") if isinstance(metadata, dict) else {}
        if not isinstance(snapshot, dict):
            snapshot = {}
        stratum = snapshot.get("stratum") or ""
        if not stratum:
            selection_reason = snapshot.get("selection_reason") or ""
            if selection_reason.startswith("labeling:"):
                stratum = selection_reason[len("labeling:"):]
        if not stratum:
            stratum = "unknown"

        label = j.label or "unknown"
        category = j.category_at_review or snapshot.get("category") or "uncategorized"
        reviewer_h = _reviewer_hash(j.reviewer)

        by_stratum.setdefault(stratum, {})
        by_stratum[stratum][label] = by_stratum[stratum].get(label, 0) + 1

        by_verdict[label] = by_verdict.get(label, 0) + 1

        by_category.setdefault(category, {})
        by_category[category][label] = by_category[category].get(label, 0) + 1

        by_reviewer[reviewer_h] = by_reviewer.get(reviewer_h, 0) + 1

        if j.created_at:
            day_key = j.created_at.strftime("%Y-%m-%d")
            reviewer_daily.setdefault(reviewer_h, {})
            reviewer_daily[reviewer_h][day_key] = (
                reviewer_daily[reviewer_h].get(day_key, 0) + 1
            )

    stratum_heatmap = []
    for stratum, verdicts in sorted(by_stratum.items()):
        stratum_total = sum(verdicts.values())
        stratum_heatmap.append({
            "stratum": stratum,
            "verdicts": verdicts,
            "total": stratum_total,
            "sufficient": stratum_total >= 50,
        })

    reviewer_progress = []
    for rh, count in sorted(by_reviewer.items(), key=lambda x: -x[1]):
        daily = reviewer_daily.get(rh, {})
        today_count = daily.get(today_str, 0)
        week_count = sum(
            c for d, c in daily.items()
            if d >= week_ago.strftime("%Y-%m-%d")
        )
        reviewer_progress.append({
            "reviewer_hash": rh,
            "total": count,
            "today": today_count,
            "this_week": week_count,
        })

    reviewed_keys = await load_reviewed_ranking_keys(db, reviewer=None, surface=None)
    queue_health = []
    for stratum in DEFAULT_LABELING_STRATA:
        result = await db.execute(
            _labeling_stratum_query(stratum, now=now, limit=200)
        )
        markets = result.scalars().unique().all()
        unreviewed = sum(
            1 for m in markets
            if ("futures", m.id) not in reviewed_keys
        )
        reviewed_count = len(markets) - unreviewed
        queue_health.append({
            "stratum": stratum,
            "total_candidates": len(markets),
            "reviewed": reviewed_count,
            "unreviewed": unreviewed,
            "exhausted": unreviewed == 0 and len(markets) > 0,
        })

    insufficient_strata = [
        s["stratum"] for s in stratum_heatmap if not s["sufficient"]
    ]

    return {
        "window": window,
        "total_reviewed": total_reviewed,
        "by_stratum": stratum_heatmap,
        "by_verdict": by_verdict,
        "by_category": by_category,
        "reviewer_progress": reviewer_progress,
        "queue_health": queue_health,
        "insufficient_strata": insufficient_strata,
        "generated_at": now.isoformat(),
    }


@router.get("/summary")
async def judgment_summary(db: AsyncSession = Depends(get_db), secret: str = Query(...)):
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    label_q = select(
        RankingJudgment.label,
        func.count(RankingJudgment.id),
    ).group_by(RankingJudgment.label)
    label_rows = (await db.execute(label_q)).all()

    cat_q = select(
        RankingJudgment.category_at_review,
        RankingJudgment.label,
        func.count(RankingJudgment.id),
    ).group_by(RankingJudgment.category_at_review, RankingJudgment.label)
    cat_rows = (await db.execute(cat_q)).all()

    score_q = (
        select(
            RankingJudgment.label,
            func.avg(RankingJudgment.score_at_review),
            func.min(RankingJudgment.score_at_review),
            func.max(RankingJudgment.score_at_review),
            func.count(RankingJudgment.id),
        )
        .where(RankingJudgment.score_at_review.isnot(None))
        .group_by(RankingJudgment.label)
    )
    score_rows = (await db.execute(score_q)).all()

    pairwise_count = (
        await db.execute(
            select(func.count(RankingJudgment.id)).where(
                (RankingJudgment.better_than.isnot(None))
                | (RankingJudgment.worse_than.isnot(None))
            )
        )
    ).scalar() or 0

    by_category: dict[str, dict[str, int]] = {}
    for category, row_label, count in cat_rows:
        category_key = category or "uncategorized"
        by_category.setdefault(category_key, {})[row_label] = count

    return {
        "total": sum(row[1] for row in label_rows),
        "labels": {row[0]: row[1] for row in label_rows},
        "pairwise_count": pairwise_count,
        "score_by_label": [
            {
                "label": row[0],
                "avg_score": round(row[1], 1) if row[1] is not None else None,
                "min_score": round(row[2], 1) if row[2] is not None else None,
                "max_score": round(row[3], 1) if row[3] is not None else None,
                "count": row[4],
            }
            for row in score_rows
        ],
        "by_category": by_category,
    }


@router.get("/fixable-interest/clusters")
async def fixable_interest_clusters(
    db: AsyncSession = Depends(get_db),
    secret: str = Query(...),
    status: str = Query("open"),
    limit: int = Query(50),
    row_limit: int = Query(1000),
):
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    rows = (
        await db.execute(
            select(RankingJudgment)
            .where(RankingJudgment.label_metadata.isnot(None))
            .order_by(desc(RankingJudgment.created_at))
            .limit(row_limit)
        )
    ).scalars().all()
    clusters = _build_fixable_clusters(list(rows))
    if status != "all":
        clusters = [cluster for cluster in clusters if cluster["status"] == status]
    return {
        "status": status,
        "total": len(clusters),
        "clusters": clusters[:limit],
    }


@router.get("/repair-clusters")
async def repair_clusters(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Cluster fixable-interest judgments by repair_type, category, and entity.

    Groups judgments where ``fixable_interesting=True`` using the first-class
    ``repair_type`` column, ``category_at_review``, and ``repair_target_entity``.
    Returns clusters sorted by count (most common first), each with sample
    market IDs and reviewer count.
    """
    if not _check_admin_secret(secret) and not await _check_admin_auth(
        secret, request, db
    ):
        raise HTTPException(status_code=403, detail="Admin access required")

    rows = (
        await db.execute(
            select(RankingJudgment)
            .where(RankingJudgment.fixable_interesting.is_(True))
            .order_by(desc(RankingJudgment.created_at))
            .limit(2000)
        )
    ).scalars().all()

    grouped: dict[str, list[RankingJudgment]] = {}
    for row in rows:
        key = (
            f"{row.repair_type or 'unspecified'}"
            f"::{row.category_at_review or 'uncategorized'}"
            f"::{row.repair_target_entity or ''}"
        )
        grouped.setdefault(key, []).append(row)

    clusters: list[dict[str, Any]] = []
    for key, cluster_rows in grouped.items():
        parts = key.split("::", 2)
        repair_type = parts[0]
        category = parts[1]
        entity = parts[2] if len(parts) > 2 else ""

        market_ids: list[int] = []
        reviewers: set[str] = set()
        for row in cluster_rows:
            if row.market_id is not None and row.market_id not in market_ids:
                market_ids.append(row.market_id)
            if row.reviewer:
                reviewers.add(row.reviewer)

        clusters.append({
            "repair_type": repair_type,
            "category": category,
            "entity": entity,
            "count": len(cluster_rows),
            "reviewer_count": len(reviewers),
            "sample_market_ids": market_ids[:10],
            "latest_created_at": (
                cluster_rows[0].created_at.isoformat()
                if cluster_rows[0].created_at
                else None
            ),
        })

    clusters.sort(key=lambda c: -c["count"])
    return {
        "total": len(clusters),
        "clusters": clusters[:limit],
    }


@router.post("/fixable-interest/clusters/{cluster_id}/triage")
async def triage_fixable_interest_cluster(
    cluster_id: str,
    payload: FixableInterestClusterTriage | None = Body(None),
    db: AsyncSession = Depends(get_db_rw),
    secret: str | None = Query(None),
):
    body = payload.model_dump(exclude_unset=True) if payload else {}
    secret_value = _merged_value(body, "secret", secret)
    if not _check_admin_secret(secret_value):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    status = str(body.get("status") or "").strip()
    if status not in {"open", "dismissed", "linked", "experiment"}:
        raise HTTPException(status_code=400, detail="Unsupported triage status")

    rows = (
        await db.execute(
            select(RankingJudgment)
            .where(RankingJudgment.label_metadata.isnot(None))
            .order_by(desc(RankingJudgment.created_at))
            .limit(5000)
        )
    ).scalars().all()
    matched: list[RankingJudgment] = []
    triage = {
        "status": status,
        "github_issue_url": body.get("github_issue_url"),
        "github_issue_number": body.get("github_issue_number"),
        "experiment_key": body.get("experiment_key"),
        "notes": body.get("notes"),
        "owner": body.get("owner"),
    }
    triage = {key: value for key, value in triage.items() if value not in (None, "")}

    for row in rows:
        metadata = _metadata_dict(row)
        fixable = _fixable_interest(metadata)
        if not _has_fixable_interest(fixable):
            continue
        if _cluster_id(_cluster_identity(row)) != cluster_id:
            continue
        next_metadata = dict(metadata)
        next_fixable = dict(fixable)
        next_fixable["triage"] = triage
        next_metadata["fixable_interest"] = next_fixable
        row.label_metadata = next_metadata
        matched.append(row)

    if not matched:
        raise HTTPException(status_code=404, detail="Fixable-interest cluster not found")

    await db.commit()
    return {
        "status": "ok",
        "cluster_id": cluster_id,
        "updated_count": len(matched),
        "triage_status": status,
    }


@router.get("/export")
async def export_judgments(db: AsyncSession = Depends(get_db), secret: str = Query(...)):
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    rows = (
        await db.execute(
            select(RankingJudgment).order_by(RankingJudgment.created_at)
        )
    ).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "date", "surface", "rank_seen", "item_type", "market_id",
        "market_name", "label", "reason_tags", "better_than", "worse_than",
        "notes", "score_at_review", "category_at_review", "archetype_at_review",
        "quality_class_at_review", "headline_at_review", "feed_request_id",
        "label_metadata", "card_snapshot", "reviewer",
    ])
    for j in rows:
        writer.writerow([
            j.date, j.surface, j.rank_seen, j.item_type, j.market_id,
            j.market_name, j.label, ",".join(canonical_reason_tags(j.reason_tags)),
            j.better_than, j.worse_than, j.notes, j.score_at_review,
            j.category_at_review, j.archetype_at_review, j.quality_class_at_review,
            j.headline_at_review, j.feed_request_id,
            json.dumps(j.label_metadata or {}, sort_keys=True),
            json.dumps((j.label_metadata or {}).get("card_snapshot") or {}, sort_keys=True),
            j.reviewer,
        ])

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ranking_judgments.csv"},
    )


# ---------------------------------------------------------------------------
# Eval-ready labeled dataset export
# ---------------------------------------------------------------------------

_SPLIT_SALT = "bainluck-discover-labels-v1"


def _reviewer_hash(reviewer: str | None) -> str:
    """Deterministic pseudonymous reviewer ID (no PII in export)."""
    raw = str(reviewer or "anonymous")
    return hashlib.sha256(f"{_SPLIT_SALT}:{raw}".encode("utf-8")).hexdigest()[:12]


def _dataset_split(market_id: int | None, event_id: int | None) -> str:
    """Deterministic train/dev/test split based on market_id hash.

    80/10/10 split. Hash-based on item id for reproducibility —
    the same market always lands in the same split.
    """
    item_key = str(market_id or event_id or 0)
    digest = hashlib.md5(
        f"{_SPLIT_SALT}:{item_key}".encode("utf-8")
    ).hexdigest()
    bucket = int(digest[:8], 16) % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "dev"
    return "test"


def _eval_row_from_judgment(judgment: RankingJudgment) -> dict[str, Any]:
    """Build one eval-ready row from a RankingJudgment, with no PII."""
    metadata = judgment.label_metadata if isinstance(judgment.label_metadata, dict) else {}
    snapshot = metadata.get("card_snapshot") if isinstance(metadata, dict) else {}
    if not isinstance(snapshot, dict):
        snapshot = {}

    return {
        "market_id": judgment.market_id,
        "event_id": judgment.event_id,
        "market_name": judgment.market_name or "",
        "reviewer_hash": _reviewer_hash(judgment.reviewer),
        "label": judgment.label,
        "timestamp": judgment.created_at.isoformat() if judgment.created_at else None,
        "split": _dataset_split(judgment.market_id, judgment.event_id),
        "category": judgment.category_at_review or snapshot.get("category") or "",
        "source": snapshot.get("source") or "",
        "archetype": judgment.archetype_at_review or snapshot.get("archetype") or "",
        "quality_class": judgment.quality_class_at_review or snapshot.get("quality_class") or "",
        "score_at_review": judgment.score_at_review,
        "rank_seen": judgment.rank_seen,
        "rendered_probability": snapshot.get("rendered_probability"),
        "story_key": snapshot.get("story_key") or "",
        "family_key": snapshot.get("family_key") or "",
        "group_id": snapshot.get("group_id") or "",
        "has_hook": bool(snapshot.get("hook_description")),
        "has_image": bool(snapshot.get("image_url")),
        "reason_tags": canonical_reason_tags(judgment.reason_tags),
        "surface": judgment.surface or "discover",
        "item_type": judgment.item_type or "futures",
    }


@router.get("/eval-export")
async def export_eval_dataset(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str | None = Query(None),
    fmt: str = Query("json", description="Output format: json or csv"),
    days: int = Query(90, ge=1, le=365),
    split: str | None = Query(None, description="Filter to train/dev/test split"),
    label: str | None = Query(None, description="Filter by label"),
    surface: str | None = Query(None),
    limit: int = Query(10000, ge=1, le=50000),
):
    """Export eval-ready labeled dataset with hashed reviewers and train/dev/test splits.

    Returns JSON by default. Set fmt=csv for CSV download.
    No PII is included — reviewer emails are hashed.
    """
    if not _check_admin_secret(secret) and not await _check_admin_auth(
        secret, request, db
    ):
        raise HTTPException(status_code=403, detail="Admin access required")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query = (
        select(RankingJudgment)
        .where(RankingJudgment.created_at >= cutoff)
        .order_by(RankingJudgment.created_at.desc())
        .limit(limit)
    )
    if surface:
        query = query.where(RankingJudgment.surface == surface)
    if label:
        query = query.where(RankingJudgment.label == label)

    result = await db.execute(query)
    all_rows = [_eval_row_from_judgment(j) for j in result.scalars().all()]

    if split:
        all_rows = [r for r in all_rows if r["split"] == split]

    split_counts = {}
    label_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for row in all_rows:
        split_counts[row["split"]] = split_counts.get(row["split"], 0) + 1
        label_counts[row["label"]] = label_counts.get(row["label"], 0) + 1
        category_counts[row["category"] or "unknown"] = (
            category_counts.get(row["category"] or "unknown", 0) + 1
        )

    if fmt == "csv":
        output = io.StringIO()
        if all_rows:
            writer = csv.DictWriter(output, fieldnames=list(all_rows[0].keys()))
            writer.writeheader()
            for row in all_rows:
                csv_row = dict(row)
                csv_row["reason_tags"] = ",".join(csv_row.get("reason_tags") or [])
                writer.writerow(csv_row)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=discover_labels_eval.csv"
            },
        )

    return {
        "total": len(all_rows),
        "split_counts": split_counts,
        "label_counts": label_counts,
        "category_counts": category_counts,
        "rows": all_rows,
    }
