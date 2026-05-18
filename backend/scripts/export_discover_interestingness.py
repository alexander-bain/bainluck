"""Export Discover engagement rows for interestingness calibration.

The export is intentionally read-only and offline-oriented: it aggregates
append-only Discover interactions, joins futures/event metadata when item IDs
can be matched, and writes CSV or JSONL rows accepted by
``scripts/calibrate_interestingness.py``.

Usage:
    python3 scripts/export_discover_interestingness.py --output /tmp/discover.csv
    python3 scripts/export_discover_interestingness.py --format jsonl --days 14
    python3 scripts/export_discover_interestingness.py --summary --summary-json
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

from sqlalchemy import Float, Integer, and_, case, cast, desc, func, literal, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.models import (  # noqa: E402
    DiscoverInteraction,
    Event,
    FuturesMarket,
    FuturesOutcome,
)


EXPORT_FIELDS = [
    "id",
    "item_type",
    "item_id",
    "name",
    "category",
    "surface",
    "source",
    "market_status",
    "event_status",
    "probability",
    "source_count",
    "updated_at",
    "movement_24h",
    "resolution_date",
    "category_recent_count",
    "category_feed_share",
    "volume_24h",
    "llm_quality",
    "label",
    "engagement_score",
    "impressions",
    "opens",
    "detail_clicks",
    "likes",
    "shares",
    "context_expands",
    "group_expands",
    "dismisses",
    "unlikes",
    "positive_engagements",
    "negative_engagements",
    "positive_rate",
    "negative_rate",
    "avg_rank",
    "avg_feed_score",
    "first_seen_at",
    "last_seen_at",
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


def build_export_statement(
    *,
    since: datetime,
    limit: int = 5000,
    min_impressions: int = 3,
    surface: str | None = None,
    item_types: tuple[str, ...] = ("futures", "event"),
):
    """Build the read-only Postgres statement used by the export CLI."""

    impression_filter = DiscoverInteraction.action == "impression"
    base_filters = [
        DiscoverInteraction.created_at >= since,
        DiscoverInteraction.item_type.in_(item_types),
    ]
    if surface:
        base_filters.append(DiscoverInteraction.surface == surface)

    category_counts = (
        select(
            DiscoverInteraction.category.label("category"),
            func.count(DiscoverInteraction.id).label("category_recent_count"),
        )
        .where(*base_filters, impression_filter)
        .group_by(DiscoverInteraction.category)
        .subquery("category_counts")
    )
    total_impressions = (
        select(func.count(DiscoverInteraction.id))
        .where(*base_filters, impression_filter)
        .scalar_subquery()
    )

    interactions = (
        select(
            DiscoverInteraction.item_type.label("item_type"),
            DiscoverInteraction.item_id.label("item_id"),
            DiscoverInteraction.surface.label("surface"),
            func.max(DiscoverInteraction.item_name).label("item_name"),
            func.max(DiscoverInteraction.category).label("category"),
            func.count().filter(impression_filter).label("impressions"),
            func.count().filter(DiscoverInteraction.action == "open").label("opens"),
            func.count()
            .filter(DiscoverInteraction.action == "detail_click")
            .label("detail_clicks"),
            func.count().filter(DiscoverInteraction.action == "like").label("likes"),
            func.count().filter(DiscoverInteraction.action == "share").label("shares"),
            func.count()
            .filter(DiscoverInteraction.action == "context_expand")
            .label("context_expands"),
            func.count()
            .filter(DiscoverInteraction.action == "group_expand")
            .label("group_expands"),
            func.count()
            .filter(DiscoverInteraction.action == "dismiss")
            .label("dismisses"),
            func.count()
            .filter(DiscoverInteraction.action == "unlike")
            .label("unlikes"),
            func.count()
            .filter(DiscoverInteraction.action.in_(POSITIVE_ACTIONS))
            .label("positive_engagements"),
            func.count()
            .filter(DiscoverInteraction.action.in_(NEGATIVE_ACTIONS))
            .label("negative_engagements"),
            func.avg(DiscoverInteraction.rank).label("avg_rank"),
            func.avg(DiscoverInteraction.score).label("avg_feed_score"),
            func.min(DiscoverInteraction.created_at).label("first_seen_at"),
            func.max(DiscoverInteraction.created_at).label("last_seen_at"),
        )
        .where(*base_filters)
        .group_by(
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
            DiscoverInteraction.surface,
        )
        .having(func.count().filter(impression_filter) >= min_impressions)
        .subquery("interactions")
    )

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
    source_counts = (
        select(
            FuturesMarket.group_id.label("group_id"),
            func.count(func.distinct(FuturesMarket.source)).label("source_count"),
        )
        .where(FuturesMarket.group_id.isnot(None))
        .group_by(FuturesMarket.group_id)
        .subquery("source_counts")
    )

    numeric_item_id = interactions.c.item_id.op("~")(r"^[0-9]+$")
    item_id_int = case(
        (numeric_item_id, cast(interactions.c.item_id, Integer)),
        else_=None,
    )
    futures_join = and_(
        interactions.c.item_type == "futures",
        numeric_item_id,
        FuturesMarket.id == item_id_int,
    )
    event_join = and_(
        interactions.c.item_type == "event",
        numeric_item_id,
        Event.id == item_id_int,
    )

    event_probability = func.nullif(
        func.greatest(
            func.coalesce(Event.closing_home_probability, 0),
            func.coalesce(Event.closing_away_probability, 0),
            func.coalesce(Event.opening_home_probability, 0),
            func.coalesce(Event.opening_away_probability, 0),
            func.coalesce(Event.espn_win_prob_home, 0),
            1 - func.coalesce(Event.espn_win_prob_home, 1),
        ),
        0,
    )
    category_share = cast(category_counts.c.category_recent_count, Float) / cast(
        func.nullif(
            cast(total_impressions, Float),
            cast(literal(0.0), Float),
        ),
        Float,
    )

    probability = func.coalesce(outcome_stats.c.leader_probability, event_probability)
    source_count = func.coalesce(
        source_counts.c.source_count,
        func.nullif(func.jsonb_object_length(Event.win_probability_sources), 0),
        literal(1),
    )

    statement = (
        select(
            interactions.c.item_type,
            interactions.c.item_id,
            func.coalesce(
                interactions.c.item_name,
                FuturesMarket.name,
                func.concat(Event.away_team_name, " at ", Event.home_team_name),
            ).label("name"),
            func.coalesce(
                interactions.c.category,
                FuturesMarket.llm_sport_category,
                FuturesMarket.category,
                literal("other"),
            ).label("category"),
            interactions.c.surface,
            FuturesMarket.source.label("source"),
            FuturesMarket.status.label("market_status"),
            Event.status.label("event_status"),
            probability.label("probability"),
            source_count.label("source_count"),
            func.coalesce(
                FuturesMarket.updated_at,
                Event.completed_at,
                Event.commence_time,
            ).label("updated_at"),
            outcome_stats.c.movement_24h.label("movement_24h"),
            func.coalesce(FuturesMarket.resolution_date, Event.commence_time).label(
                "resolution_date"
            ),
            category_counts.c.category_recent_count,
            category_share.label("category_feed_share"),
            FuturesMarket.volume_24h,
            interactions.c.impressions,
            interactions.c.opens,
            interactions.c.detail_clicks,
            interactions.c.likes,
            interactions.c.shares,
            interactions.c.context_expands,
            interactions.c.group_expands,
            interactions.c.dismisses,
            interactions.c.unlikes,
            interactions.c.positive_engagements,
            interactions.c.negative_engagements,
            interactions.c.avg_rank,
            interactions.c.avg_feed_score,
            interactions.c.first_seen_at,
            interactions.c.last_seen_at,
        )
        .select_from(interactions)
        .outerjoin(FuturesMarket, futures_join)
        .outerjoin(outcome_stats, outcome_stats.c.market_id == FuturesMarket.id)
        .outerjoin(source_counts, source_counts.c.group_id == FuturesMarket.group_id)
        .outerjoin(Event, event_join)
        .outerjoin(
            category_counts,
            category_counts.c.category == interactions.c.category,
        )
        .order_by(desc(interactions.c.impressions), desc(interactions.c.last_seen_at))
        .limit(limit)
    )
    return statement


def format_export_row(row: Any) -> dict[str, Any]:
    """Normalize a database row into calibration-friendly scalar fields."""

    data = dict(row._mapping if hasattr(row, "_mapping") else row)
    impressions = _as_int(data.get("impressions")) or 0
    positives = _as_int(data.get("positive_engagements")) or 0
    negatives = _as_int(data.get("negative_engagements")) or 0
    positive_rate = positives / impressions if impressions else 0.0
    negative_rate = negatives / impressions if impressions else 0.0
    engagement_score = positive_rate - negative_rate
    item_type = data.get("item_type") or "unknown"
    item_id = data.get("item_id") or ""

    formatted = {
        "id": f"{item_type}:{item_id}",
        "item_type": item_type,
        "item_id": item_id,
        "name": data.get("name") or "",
        "category": data.get("category") or "other",
        "surface": data.get("surface") or "unknown",
        "source": data.get("source") or "",
        "market_status": data.get("market_status") or "",
        "event_status": data.get("event_status") or "",
        "probability": _round_float(data.get("probability"), 6),
        "source_count": _as_int(data.get("source_count")),
        "updated_at": _isoformat(data.get("updated_at")),
        "movement_24h": _round_float(data.get("movement_24h"), 6),
        "resolution_date": _isoformat(data.get("resolution_date")),
        "category_recent_count": _as_int(data.get("category_recent_count")),
        "category_feed_share": _round_float(data.get("category_feed_share"), 6),
        "volume_24h": _as_int(data.get("volume_24h")),
        "llm_quality": None,
        "label": _engagement_label(
            impressions=impressions,
            positive_rate=positive_rate,
            negative_rate=negative_rate,
        ),
        "engagement_score": round(engagement_score, 6),
        "impressions": impressions,
        "opens": _as_int(data.get("opens")) or 0,
        "detail_clicks": _as_int(data.get("detail_clicks")) or 0,
        "likes": _as_int(data.get("likes")) or 0,
        "shares": _as_int(data.get("shares")) or 0,
        "context_expands": _as_int(data.get("context_expands")) or 0,
        "group_expands": _as_int(data.get("group_expands")) or 0,
        "dismisses": _as_int(data.get("dismisses")) or 0,
        "unlikes": _as_int(data.get("unlikes")) or 0,
        "positive_engagements": positives,
        "negative_engagements": negatives,
        "positive_rate": round(positive_rate, 6),
        "negative_rate": round(negative_rate, 6),
        "avg_rank": _round_float(data.get("avg_rank"), 4),
        "avg_feed_score": _round_float(data.get("avg_feed_score"), 4),
        "first_seen_at": _isoformat(data.get("first_seen_at")),
        "last_seen_at": _isoformat(data.get("last_seen_at")),
    }
    return formatted


async def export_rows(
    session: AsyncSession,
    *,
    since: datetime,
    limit: int,
    min_impressions: int,
    surface: str | None,
) -> list[dict[str, Any]]:
    statement = build_export_statement(
        since=since,
        limit=limit,
        min_impressions=min_impressions,
        surface=surface,
    )
    result = await session.execute(statement)
    return [format_export_row(row) for row in result.all()]


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


def summarize_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate export rows into category and score-bucket engagement diagnostics."""
    rows = list(rows)
    total = _aggregate_group(rows)
    categories = _summarize_grouped(rows, key_fn=lambda row: row.get("category") or "other")
    score_buckets = _summarize_grouped(rows, key_fn=_score_bucket)
    labels = {
        "positive": sum(1 for row in rows if row.get("label") == "positive"),
        "negative": sum(1 for row in rows if row.get("label") == "negative"),
        "unlabeled": sum(1 for row in rows if not row.get("label")),
    }

    return {
        "rows": len(rows),
        "labels": labels,
        "overall": total,
        "categories": categories,
        "score_buckets": score_buckets,
        "opportunities": _ranking_opportunities(categories),
    }


def write_summary(summary: dict[str, Any], handle: TextIO, *, as_json: bool) -> None:
    if as_json:
        handle.write(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        return

    overall = summary["overall"]
    handle.write("Discover engagement calibration summary\n")
    handle.write("=" * 72 + "\n")
    handle.write(
        f"Rows: {summary['rows']} | impressions: {overall['impressions']} | "
        f"positive_rate: {overall['positive_rate']:.1%} | "
        f"negative_rate: {overall['negative_rate']:.1%} | "
        f"engagement_score: {overall['engagement_score']:.3f}\n\n"
    )

    handle.write("Categories\n")
    handle.write("-" * 72 + "\n")
    for row in summary["categories"][:20]:
        handle.write(
            f"{row['key'][:18]:18s} imp={row['impressions']:5d} "
            f"pos={row['positive_rate']:.1%} neg={row['negative_rate']:.1%} "
            f"score={row['engagement_score']:.3f} avg_rank={_format_float(row['avg_rank'])} "
            f"avg_feed={_format_float(row['avg_feed_score'])}\n"
        )

    handle.write("\nScore buckets\n")
    handle.write("-" * 72 + "\n")
    for row in summary["score_buckets"]:
        handle.write(
            f"{row['key']:>7s} imp={row['impressions']:5d} "
            f"pos={row['positive_rate']:.1%} neg={row['negative_rate']:.1%} "
            f"score={row['engagement_score']:.3f}\n"
        )

    if summary["opportunities"]:
        handle.write("\nReview opportunities\n")
        handle.write("-" * 72 + "\n")
        for item in summary["opportunities"]:
            handle.write(
                f"{item['kind']}: {item['category']} "
                f"(score={item['engagement_score']:.3f}, "
                f"impressions={item['impressions']})\n"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Output path. Defaults to stdout.")
    parser.add_argument("--format", choices=("csv", "jsonl"), default="csv")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--min-impressions", type=int, default=3)
    parser.add_argument("--surface", choices=("web", "native", "unknown"))
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print category and score-bucket engagement diagnostics instead of rows.",
    )
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help="Print --summary output as JSON.",
    )
    parser.add_argument(
        "--print-sql",
        action="store_true",
        help="Print the compiled SQL instead of querying the database.",
    )
    args = parser.parse_args()

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    if args.print_sql:
        statement = build_export_statement(
            since=since,
            limit=args.limit,
            min_impressions=args.min_impressions,
            surface=args.surface,
        )
        print(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        return 0

    return asyncio.run(_run_cli(args=args, since=since))


async def _run_cli(*, args: argparse.Namespace, since: datetime) -> int:
    from app.services.database import async_session_maker

    async with async_session_maker() as session:
        rows = await export_rows(
            session,
            since=since,
            limit=args.limit,
            min_impressions=args.min_impressions,
            surface=args.surface,
        )

    if args.summary:
        write_summary(summarize_rows(rows), sys.stdout, as_json=args.summary_json)
    elif args.output:
        path = Path(args.output)
        with path.open("w", newline="") as handle:
            write_rows(rows, handle, fmt=args.format)
    else:
        write_rows(rows, sys.stdout, fmt=args.format)
    return 0


def _summarize_grouped(rows: list[dict[str, Any]], *, key_fn) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = key_fn(row)
        grouped.setdefault(str(key), []).append(row)
    summaries = [
        {"key": key, **_aggregate_group(group_rows)}
        for key, group_rows in grouped.items()
    ]
    summaries.sort(
        key=lambda row: (
            row["impressions"],
            row["positive_engagements"] - row["negative_engagements"],
        ),
        reverse=True,
    )
    return summaries


def _aggregate_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    impressions = sum(_as_int(row.get("impressions")) or 0 for row in rows)
    positives = sum(_as_int(row.get("positive_engagements")) or 0 for row in rows)
    negatives = sum(_as_int(row.get("negative_engagements")) or 0 for row in rows)
    positive_rate = positives / impressions if impressions else 0.0
    negative_rate = negatives / impressions if impressions else 0.0
    return {
        "rows": len(rows),
        "impressions": impressions,
        "positive_engagements": positives,
        "negative_engagements": negatives,
        "positive_rate": round(positive_rate, 6),
        "negative_rate": round(negative_rate, 6),
        "engagement_score": round(positive_rate - negative_rate, 6),
        "avg_rank": _weighted_average(rows, value_key="avg_rank", weight_key="impressions"),
        "avg_feed_score": _weighted_average(
            rows,
            value_key="avg_feed_score",
            weight_key="impressions",
        ),
    }


def _ranking_opportunities(category_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    opportunities: list[dict[str, Any]] = []
    for row in category_rows:
        if row["impressions"] < 20:
            continue
        category = row["key"]
        if row["engagement_score"] >= 0.12 and (
            row["avg_rank"] is None or row["avg_rank"] > 10
        ):
            opportunities.append({"kind": "under-ranked_category", "category": category, **row})
        elif row["engagement_score"] <= -0.20 and (
            row["avg_rank"] is None or row["avg_rank"] <= 20
        ):
            opportunities.append({"kind": "over-ranked_category", "category": category, **row})
    return opportunities[:10]


def _score_bucket(row: dict[str, Any]) -> str:
    score = _round_float(row.get("avg_feed_score"), 4)
    if score is None:
        return "unknown"
    floor = int(score // 10) * 10
    floor = max(0, min(100, floor))
    if floor == 100:
        return "100"
    return f"{floor:02d}-{floor + 9:02d}"


def _weighted_average(
    rows: list[dict[str, Any]],
    *,
    value_key: str,
    weight_key: str,
) -> float | None:
    total_weight = 0
    weighted = 0.0
    for row in rows:
        value = _round_float(row.get(value_key), 6)
        weight = _as_int(row.get(weight_key)) or 0
        if value is None or weight <= 0:
            continue
        total_weight += weight
        weighted += value * weight
    if total_weight <= 0:
        return None
    return round(weighted / total_weight, 4)


def _format_float(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}"


def _engagement_label(
    *,
    impressions: int,
    positive_rate: float,
    negative_rate: float,
) -> str | None:
    if impressions < 10:
        return None
    if positive_rate >= 0.10 and negative_rate <= 0.25:
        return "positive"
    if negative_rate >= 0.40 and positive_rate <= 0.03:
        return "negative"
    return None


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: ("" if value is None else value) for key, value in row.items()}


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
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


if __name__ == "__main__":
    raise SystemExit(main())
