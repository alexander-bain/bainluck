"""Export human-labeled Discover rows for ranking evals.

This is the durable labeled dataset path: it joins explicit
``ranking_judgments`` rows with futures metadata, outcome stats, and optional
Discover engagement aggregates. It is read-only and writes CSV or JSONL rows
that can feed gold-set evals and ranking calibration scripts.

Usage:
    python3 scripts/export_discover_labeled_dataset.py --output /tmp/labels.csv
    python3 scripts/export_discover_labeled_dataset.py --format jsonl --days 30
    python3 scripts/export_discover_labeled_dataset.py --print-sql
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, TextIO

from sqlalchemy import Integer, case, cast, desc, func, select, true
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.models import (  # noqa: E402
    DiscoverInteraction,
    FuturesMarket,
    FuturesOutcome,
    RankingJudgment,
)


EXPORT_FIELDS = [
    "id",
    "judgment_id",
    "created_at",
    "reviewer",
    "surface",
    "rank_seen",
    "item_type",
    "item_id",
    "market_id",
    "event_id",
    "name",
    "label",
    "reason_tags",
    "notes",
    "score_at_review",
    "category",
    "archetype",
    "quality_class",
    "headline",
    "source",
    "market_status",
    "group_id",
    "leader_probability",
    "movement_24h",
    "volume_24h",
    "resolution_date",
    "image_url",
    "hook_description",
    "label_metadata",
    "card_snapshot",
    "snapshot_schema_version",
    "snapshot_batch_id",
    "snapshot_feed_request_id",
    "snapshot_name",
    "snapshot_source",
    "snapshot_story_key",
    "snapshot_family_key",
    "snapshot_group_id",
    "snapshot_context",
    "snapshot_image_url",
    "snapshot_hook_description",
    "snapshot_rendered_probability",
    "snapshot_top_outcomes",
    "tapworthy_score",
    "boring",
    "clarity",
    "explanation_quality",
    "image_fit",
    "audience_scope",
    "resolution_importance",
    "would_be_interesting_if",
    "fixable_interest_score",
    "fix_type",
    "desired_entity_or_variant",
    "current_entity_or_variant",
    "create_issue_candidate",
    "impressions",
    "positive_engagements",
    "negative_engagements",
    "positive_rate",
    "negative_rate",
    "avg_rank",
    "avg_feed_score",
]

POSITIVE_ACTIONS = (
    "open",
    "detail_click",
    "like",
    "share",
    "context_expand",
    "group_expand",
    "challenge_start",
    "challenge_complete",
)
NEGATIVE_ACTIONS = ("dismiss", "unlike")


def build_labeled_dataset_statement(
    *,
    since: datetime,
    limit: int = 5000,
    surface: str | None = None,
    reviewer: str | None = None,
    labels: tuple[str, ...] | None = None,
) -> Select:
    """Build the read-only statement for explicit Discover labels."""

    judgment_filters = [RankingJudgment.created_at >= since]
    if surface:
        judgment_filters.append(RankingJudgment.surface == surface)
    if reviewer:
        judgment_filters.append(RankingJudgment.reviewer == reviewer)
    if labels:
        judgment_filters.append(RankingJudgment.label.in_(labels))

    outcome_stats = (
        select(
            FuturesOutcome.market_id.label("market_id"),
            func.max(FuturesOutcome.current_probability).label("leader_probability"),
            func.max(func.abs(FuturesOutcome.probability_change_24h)).label(
                "movement_24h"
            ),
        )
        .group_by(FuturesOutcome.market_id)
        .subquery("outcome_stats")
    )

    numeric_item_id = DiscoverInteraction.item_id.op("~")(r"^[0-9]+$")
    item_id_int = case(
        (numeric_item_id, cast(DiscoverInteraction.item_id, Integer)),
        else_=None,
    )
    interaction_filters = [
        DiscoverInteraction.created_at >= since,
        DiscoverInteraction.item_type == RankingJudgment.item_type,
        DiscoverInteraction.surface == RankingJudgment.surface,
        numeric_item_id,
        item_id_int == RankingJudgment.market_id,
    ]
    interaction_stats = (
        select(
            func.count()
            .filter(DiscoverInteraction.action == "impression")
            .label("impressions"),
            func.count()
            .filter(DiscoverInteraction.action.in_(POSITIVE_ACTIONS))
            .label("positive_engagements"),
            func.count()
            .filter(DiscoverInteraction.action.in_(NEGATIVE_ACTIONS))
            .label("negative_engagements"),
            func.avg(DiscoverInteraction.rank).label("avg_rank"),
            func.avg(DiscoverInteraction.score).label("avg_feed_score"),
        )
        .where(*interaction_filters)
        .correlate(RankingJudgment)
        .lateral("interaction_stats")
    )

    return (
        select(
            RankingJudgment.id.label("judgment_id"),
            RankingJudgment.created_at,
            RankingJudgment.reviewer,
            RankingJudgment.surface,
            RankingJudgment.rank_seen,
            RankingJudgment.item_type,
            RankingJudgment.market_id,
            RankingJudgment.event_id,
            func.coalesce(RankingJudgment.market_name, FuturesMarket.name).label("name"),
            RankingJudgment.label,
            RankingJudgment.reason_tags,
            RankingJudgment.notes,
            RankingJudgment.score_at_review,
            func.coalesce(
                RankingJudgment.category_at_review,
                FuturesMarket.llm_sport_category,
                FuturesMarket.category,
            ).label("category"),
            RankingJudgment.archetype_at_review.label("archetype"),
            RankingJudgment.quality_class_at_review.label("quality_class"),
            RankingJudgment.headline_at_review.label("headline"),
            RankingJudgment.label_metadata,
            FuturesMarket.source,
            FuturesMarket.status.label("market_status"),
            FuturesMarket.group_id,
            outcome_stats.c.leader_probability,
            outcome_stats.c.movement_24h,
            FuturesMarket.volume_24h,
            FuturesMarket.resolution_date,
            FuturesMarket.image_url,
            FuturesMarket.hook_description,
            interaction_stats.c.impressions,
            interaction_stats.c.positive_engagements,
            interaction_stats.c.negative_engagements,
            interaction_stats.c.avg_rank,
            interaction_stats.c.avg_feed_score,
        )
        .select_from(RankingJudgment)
        .outerjoin(FuturesMarket, FuturesMarket.id == RankingJudgment.market_id)
        .outerjoin(outcome_stats, outcome_stats.c.market_id == FuturesMarket.id)
        .outerjoin(interaction_stats, true())
        .where(*judgment_filters)
        .order_by(desc(RankingJudgment.created_at), RankingJudgment.id.desc())
        .limit(limit)
    )


def format_labeled_row(row: Any) -> dict[str, Any]:
    """Flatten a labeled DB row into scalar eval/export fields."""

    data = dict(row._mapping if hasattr(row, "_mapping") else row)
    metadata = data.get("label_metadata") if isinstance(data.get("label_metadata"), dict) else {}
    snapshot = metadata.get("card_snapshot") if isinstance(metadata, dict) else {}
    if not isinstance(snapshot, dict):
        snapshot = {}
    fixable = metadata.get("fixable_interest") if isinstance(metadata, dict) else {}
    if not isinstance(fixable, dict):
        fixable = {}

    impressions = _as_int(data.get("impressions")) or 0
    positives = _as_int(data.get("positive_engagements")) or 0
    negatives = _as_int(data.get("negative_engagements")) or 0

    item_type = data.get("item_type") or "futures"
    item_id = data.get("market_id") or data.get("event_id") or ""
    return {
        "id": f"{item_type}:{item_id}",
        "judgment_id": _as_int(data.get("judgment_id")),
        "created_at": _isoformat(data.get("created_at")),
        "reviewer": data.get("reviewer") or "",
        "surface": data.get("surface") or "",
        "rank_seen": _as_int(data.get("rank_seen")),
        "item_type": item_type,
        "item_id": str(item_id),
        "market_id": _as_int(data.get("market_id")),
        "event_id": _as_int(data.get("event_id")),
        "name": data.get("name") or "",
        "label": data.get("label") or "",
        "reason_tags": ",".join(data.get("reason_tags") or []),
        "notes": data.get("notes") or "",
        "score_at_review": _round_float(data.get("score_at_review"), 4),
        "category": data.get("category") or "",
        "archetype": data.get("archetype") or "",
        "quality_class": data.get("quality_class") or "",
        "headline": data.get("headline") or "",
        "source": data.get("source") or "",
        "market_status": data.get("market_status") or "",
        "group_id": data.get("group_id") or "",
        "leader_probability": _round_float(data.get("leader_probability"), 6),
        "movement_24h": _round_float(data.get("movement_24h"), 6),
        "volume_24h": _as_int(data.get("volume_24h")),
        "resolution_date": _isoformat(data.get("resolution_date")),
        "image_url": data.get("image_url") or "",
        "hook_description": data.get("hook_description") or "",
        "label_metadata": _json_dumps(metadata or {}),
        "card_snapshot": _json_dumps(snapshot or {}),
        "snapshot_schema_version": snapshot.get("schema_version") or "",
        "snapshot_batch_id": snapshot.get("batch_id") or "",
        "snapshot_feed_request_id": snapshot.get("feed_request_id") or "",
        "snapshot_name": snapshot.get("name") or "",
        "snapshot_source": snapshot.get("source") or "",
        "snapshot_story_key": snapshot.get("story_key") or "",
        "snapshot_family_key": snapshot.get("family_key") or "",
        "snapshot_group_id": snapshot.get("group_id") or "",
        "snapshot_context": snapshot.get("context") or "",
        "snapshot_image_url": snapshot.get("image_url") or "",
        "snapshot_hook_description": snapshot.get("hook_description") or "",
        "snapshot_rendered_probability": _round_float(snapshot.get("rendered_probability"), 6),
        "snapshot_top_outcomes": _json_dumps(snapshot.get("top_outcomes") or []),
        "tapworthy_score": _metadata_value(metadata, "tapworthy_score"),
        "boring": _metadata_value(metadata, "boring"),
        "clarity": _metadata_value(metadata, "clarity"),
        "explanation_quality": _metadata_value(metadata, "explanation_quality"),
        "image_fit": _metadata_value(metadata, "image_fit"),
        "audience_scope": _metadata_value(metadata, "audience_scope"),
        "resolution_importance": _metadata_value(metadata, "resolution_importance"),
        "would_be_interesting_if": fixable.get("would_be_interesting_if") or "",
        "fixable_interest_score": fixable.get("fixable_interest_score") or "",
        "fix_type": fixable.get("fix_type") or "",
        "desired_entity_or_variant": fixable.get("desired_entity_or_variant") or "",
        "current_entity_or_variant": fixable.get("current_entity_or_variant") or "",
        "create_issue_candidate": fixable.get("create_issue_candidate") or "",
        "impressions": impressions,
        "positive_engagements": positives,
        "negative_engagements": negatives,
        "positive_rate": round(positives / impressions, 6) if impressions else 0.0,
        "negative_rate": round(negatives / impressions, 6) if impressions else 0.0,
        "avg_rank": _round_float(data.get("avg_rank"), 4),
        "avg_feed_score": _round_float(data.get("avg_feed_score"), 4),
    }


async def export_rows(
    session: AsyncSession,
    *,
    since: datetime,
    limit: int,
    surface: str | None,
    reviewer: str | None,
    labels: tuple[str, ...] | None,
) -> list[dict[str, Any]]:
    statement = build_labeled_dataset_statement(
        since=since,
        limit=limit,
        surface=surface,
        reviewer=reviewer,
        labels=labels,
    )
    result = await session.execute(statement)
    return [format_labeled_row(row) for row in result.all()]


def write_rows(rows: Iterable[dict[str, Any]], handle: TextIO, *, fmt: str) -> None:
    rows = list(rows)
    if fmt == "jsonl":
        for row in rows:
            handle.write(json.dumps(_compact_row(row), sort_keys=True) + "\n")
        return

    writer = csv.DictWriter(handle, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(_compact_row(row))


def summarize_fixable_interest(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    fixable_rows = [row for row in rows if row.get("fix_type") or row.get("would_be_interesting_if")]
    by_type: dict[str, int] = {}
    issue_candidates = 0
    for row in fixable_rows:
        fix_type = str(row.get("fix_type") or "unspecified")
        by_type[fix_type] = by_type.get(fix_type, 0) + 1
        if _as_bool(row.get("create_issue_candidate")):
            issue_candidates += 1
    return {
        "rows": len(rows),
        "fixable_rows": len(fixable_rows),
        "issue_candidates": issue_candidates,
        "by_fix_type": dict(sorted(by_type.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Output path. Defaults to stdout.")
    parser.add_argument("--format", choices=("csv", "jsonl"), default="csv")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--surface")
    parser.add_argument("--reviewer")
    parser.add_argument("--label", action="append", help="Filter by label; repeatable.")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--summary-json", action="store_true")
    parser.add_argument("--print-sql", action="store_true")
    args = parser.parse_args()

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    labels = tuple(args.label) if args.label else None
    if args.print_sql:
        statement = build_labeled_dataset_statement(
            since=since,
            limit=args.limit,
            surface=args.surface,
            reviewer=args.reviewer,
            labels=labels,
        )
        print(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        return 0

    return asyncio.run(_run_cli(args=args, since=since, labels=labels))


async def _run_cli(
    *,
    args: argparse.Namespace,
    since: datetime,
    labels: tuple[str, ...] | None,
) -> int:
    from app.services.database import async_session_maker

    async with async_session_maker() as session:
        rows = await export_rows(
            session,
            since=since,
            limit=args.limit,
            surface=args.surface,
            reviewer=args.reviewer,
            labels=labels,
        )

    if args.summary:
        summary = summarize_fixable_interest(rows)
        if args.summary_json:
            print(json.dumps(summary, indent=2, sort_keys=True))
        else:
            print("Discover labeled dataset summary")
            print(f"Rows: {summary['rows']}")
            print(f"Fixable-interest rows: {summary['fixable_rows']}")
            print(f"Issue candidates: {summary['issue_candidates']}")
            print(f"By fix type: {summary['by_fix_type']}")
    elif args.output:
        with Path(args.output).open("w", newline="") as handle:
            write_rows(rows, handle, fmt=args.format)
    else:
        write_rows(rows, sys.stdout, fmt=args.format)
    return 0


def _metadata_value(metadata: dict[str, Any], key: str) -> Any:
    value = metadata.get(key)
    if value is None:
        return ""
    return value


def _json_dumps(value: Any) -> str:
    return json.dumps(value, default=_json_default, sort_keys=True)


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return _isoformat(value)
    return str(value)


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: ("" if value is None else value) for key, value in row.items()}


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return int(value)
    return int(value)


def _round_float(value: Any, digits: int) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        value = float(value)
    return round(float(value), digits)


def _isoformat(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


if __name__ == "__main__":
    raise SystemExit(main())
