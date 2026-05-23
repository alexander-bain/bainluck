"""Export read-only Discover candidates for human labeling.

The batch is offline-oriented: it reads open futures markets, adds deterministic
quality/interestingness fields, and writes item rows plus optional pairwise rows
for preference labeling. It does not write to the database or call external
services.

Usage:
    python3 scripts/export_discover_labeling_batch.py --output /tmp/items.csv
    python3 scripts/export_discover_labeling_batch.py --format jsonl --limit 100
    python3 scripts/export_discover_labeling_batch.py --output /tmp/items.csv \
        --pairs-output /tmp/pairs.csv --pair-count 50
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import random
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, TextIO

from sqlalchemy import Float, Integer, and_, case, cast, desc, func, literal, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.models import FuturesMarket, FuturesOutcome  # noqa: E402
from app.utils.feed_market_quality import classify_market_quality  # noqa: E402
from app.utils.market_interestingness import (  # noqa: E402
    MarketInterestingnessInputs,
    score_market_interestingness,
)


EXPORT_VERSION = "discover_labeling_batch_v1"

ITEM_FIELDS = [
    "batch_id",
    "row_type",
    "candidate_id",
    "market_id",
    "source",
    "external_id",
    "group_id",
    "name",
    "category",
    "llm_sport_category",
    "market_type",
    "market_tier",
    "status",
    "leader_name",
    "leader_probability",
    "outcome_count",
    "source_count",
    "updated_at",
    "resolution_date",
    "volume_24h",
    "movement_24h",
    "image_url",
    "hook_description",
    "card_snapshot",
    "llm_topic",
    "llm_subtopic",
    "llm_archetype",
    "llm_audience_scope",
    "llm_salience_score",
    "llm_junk_flags",
    "quality_class",
    "family_key",
    "story_key",
    "quality_reasons",
    "interestingness_score",
    "interestingness_reasons",
    "interestingness_components",
    "human_label",
    "would_be_interesting_if",
    "fixable_interest_score",
    "fix_type",
    "desired_entity_or_variant",
    "current_entity_or_variant",
    "create_issue_candidate",
    "human_notes",
]

PAIR_FIELDS = [
    "batch_id",
    "row_type",
    "pair_id",
    "left_candidate_id",
    "right_candidate_id",
    "left_name",
    "right_name",
    "left_category",
    "right_category",
    "left_interestingness_score",
    "right_interestingness_score",
    "pair_strategy",
    "human_preference",
    "human_notes",
]


def build_candidate_statement(
    *,
    updated_since: datetime,
    candidate_pool_limit: int = 1000,
    statuses: tuple[str, ...] = ("open",),
    sources: tuple[str, ...] | None = None,
    categories: tuple[str, ...] | None = None,
    min_volume_24h: int | None = None,
) -> Select:
    """Build the read-only Postgres statement used by the batch exporter."""

    outcome_stats = (
        select(
            FuturesOutcome.market_id.label("market_id"),
            func.count(FuturesOutcome.id).label("outcome_count"),
            func.max(FuturesOutcome.current_probability).label("leader_probability"),
            func.max(func.abs(FuturesOutcome.probability_change_24h)).label(
                "movement_24h"
            ),
            func.array_agg(FuturesOutcome.name).label("outcome_names"),
        )
        .group_by(FuturesOutcome.market_id)
        .subquery("outcome_stats")
    )

    leader_probability = outcome_stats.c.leader_probability
    leader_name = (
        select(FuturesOutcome.name)
        .where(
            FuturesOutcome.market_id == FuturesMarket.id,
            FuturesOutcome.current_probability == leader_probability,
        )
        .order_by(FuturesOutcome.name.asc())
        .limit(1)
        .correlate(FuturesMarket, outcome_stats)
        .scalar_subquery()
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

    category_key = func.coalesce(
        FuturesMarket.llm_sport_category,
        FuturesMarket.category,
        literal("other"),
    )
    category_counts = (
        select(
            category_key.label("category"),
            func.count(FuturesMarket.id).label("category_recent_count"),
        )
        .where(FuturesMarket.status.in_(statuses))
        .group_by(category_key)
        .subquery("category_counts")
    )
    total_candidates = (
        select(func.count(FuturesMarket.id))
        .where(FuturesMarket.status.in_(statuses))
        .scalar_subquery()
    )
    category_feed_share = cast(category_counts.c.category_recent_count, Float) / cast(
        func.nullif(cast(total_candidates, Float), cast(literal(0.0), Float)),
        Float,
    )

    filters = [
        FuturesMarket.status.in_(statuses),
        FuturesMarket.updated_at >= updated_since,
    ]
    if sources:
        filters.append(FuturesMarket.source.in_(sources))
    if categories:
        filters.append(category_key.in_(categories))
    if min_volume_24h is not None:
        filters.append(FuturesMarket.volume_24h >= min_volume_24h)

    group_key = func.coalesce(
        FuturesMarket.group_id,
        func.concat(FuturesMarket.source, literal(":"), cast(FuturesMarket.id, Integer)),
    )
    dedup_rank = func.row_number().over(
        partition_by=group_key,
        order_by=(
            desc(FuturesMarket.volume_24h).nulls_last(),
            desc(FuturesMarket.updated_at).nulls_last(),
            FuturesMarket.id.asc(),
        ),
    )

    candidates = (
        select(
            FuturesMarket.id.label("market_id"),
            FuturesMarket.source,
            FuturesMarket.external_id,
            FuturesMarket.group_id,
            FuturesMarket.name,
            FuturesMarket.category,
            FuturesMarket.llm_sport_category,
            FuturesMarket.market_type,
            FuturesMarket.market_tier,
            FuturesMarket.status,
            FuturesMarket.updated_at,
            FuturesMarket.resolution_date,
            FuturesMarket.volume_24h,
            FuturesMarket.image_url,
            FuturesMarket.hook_description,
            FuturesMarket.market_metadata,
            outcome_stats.c.outcome_count,
            outcome_stats.c.leader_probability,
            leader_name.label("leader_name"),
            outcome_stats.c.movement_24h,
            outcome_stats.c.outcome_names,
            func.coalesce(source_counts.c.source_count, literal(1)).label("source_count"),
            category_counts.c.category_recent_count,
            category_feed_share.label("category_feed_share"),
            dedup_rank.label("dedup_rank"),
        )
        .select_from(FuturesMarket)
        .outerjoin(outcome_stats, outcome_stats.c.market_id == FuturesMarket.id)
        .outerjoin(source_counts, source_counts.c.group_id == FuturesMarket.group_id)
        .outerjoin(category_counts, category_counts.c.category == category_key)
        .where(*filters)
        .subquery("candidates")
    )

    return (
        select(candidates)
        .where(candidates.c.dedup_rank == 1)
        .order_by(
            desc(candidates.c.volume_24h).nulls_last(),
            desc(candidates.c.movement_24h).nulls_last(),
            desc(candidates.c.updated_at).nulls_last(),
            candidates.c.market_id.asc(),
        )
        .limit(candidate_pool_limit)
    )


def format_candidate_row(row: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Normalize a DB row into a human-labeling candidate row."""

    data = dict(row._mapping if hasattr(row, "_mapping") else row)
    metadata = data.get("market_metadata") if isinstance(data.get("market_metadata"), dict) else {}
    discover_llm = metadata.get("discover_llm") if isinstance(metadata, dict) else {}
    if not isinstance(discover_llm, dict):
        discover_llm = {}

    outcome_names = data.get("outcome_names") or []
    quality = classify_market_quality(
        data.get("name"),
        data.get("llm_sport_category") or data.get("category"),
        outcome_names=list(outcome_names),
    )
    category = data.get("llm_sport_category") or data.get("category") or "other"
    scoring_inputs = {
        "probability": data.get("leader_probability"),
        "source_count": data.get("source_count"),
        "updated_at": data.get("updated_at"),
        "movement_24h": data.get("movement_24h"),
        "resolution_date": data.get("resolution_date"),
        "category": category,
        "category_recent_count": data.get("category_recent_count"),
        "category_feed_share": data.get("category_feed_share"),
        "volume_24h": data.get("volume_24h"),
        "llm_quality": discover_llm.get("salience_score"),
    }
    score = score_market_interestingness(
        MarketInterestingnessInputs.from_mapping(scoring_inputs),
        now=now,
    )

    market_id = _as_int(data.get("market_id"))
    candidate_id = f"futures:{market_id}"
    return {
        "batch_id": "",
        "row_type": "item",
        "candidate_id": candidate_id,
        "market_id": market_id,
        "source": data.get("source") or "",
        "external_id": data.get("external_id") or "",
        "group_id": data.get("group_id") or "",
        "name": data.get("name") or "",
        "category": category,
        "llm_sport_category": data.get("llm_sport_category") or "",
        "market_type": data.get("market_type") or "",
        "market_tier": _as_int(data.get("market_tier")),
        "status": data.get("status") or "",
        "leader_name": data.get("leader_name") or "",
        "leader_probability": _round_float(data.get("leader_probability"), 6),
        "outcome_count": _as_int(data.get("outcome_count")) or 0,
        "source_count": _as_int(data.get("source_count")) or 1,
        "updated_at": _isoformat(data.get("updated_at")),
        "resolution_date": _isoformat(data.get("resolution_date")),
        "volume_24h": _as_int(data.get("volume_24h")),
        "movement_24h": _round_float(data.get("movement_24h"), 6),
        "image_url": data.get("image_url") or "",
        "hook_description": data.get("hook_description") or "",
        "card_snapshot": "",
        "llm_topic": discover_llm.get("topic") or "",
        "llm_subtopic": discover_llm.get("subtopic") or "",
        "llm_archetype": discover_llm.get("archetype") or "",
        "llm_audience_scope": discover_llm.get("audience_scope") or "",
        "llm_salience_score": _round_float(discover_llm.get("salience_score"), 4),
        "llm_junk_flags": _json_compact(discover_llm.get("junk_flags") or []),
        "quality_class": quality.quality_class,
        "family_key": quality.family_key,
        "story_key": quality.story_key or "",
        "quality_reasons": _json_compact(quality.reasons),
        "interestingness_score": score.score,
        "interestingness_reasons": _json_compact(score.reasons),
        "interestingness_components": _json_compact(score.components),
        "human_label": "",
        "would_be_interesting_if": "",
        "fixable_interest_score": "",
        "fix_type": "",
        "desired_entity_or_variant": "",
        "current_entity_or_variant": "",
        "create_issue_candidate": "",
        "human_notes": "",
    }


async def export_candidate_rows(
    session: AsyncSession,
    *,
    updated_since: datetime,
    limit: int,
    candidate_pool_limit: int,
    statuses: tuple[str, ...],
    sources: tuple[str, ...] | None,
    categories: tuple[str, ...] | None,
    min_volume_24h: int | None,
    seed: str,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    statement = build_candidate_statement(
        updated_since=updated_since,
        candidate_pool_limit=candidate_pool_limit,
        statuses=statuses,
        sources=sources,
        categories=categories,
        min_volume_24h=min_volume_24h,
    )
    result = await session.execute(statement)
    rows = [format_candidate_row(row, now=now) for row in result.all()]
    return select_labeling_items(rows, limit=limit, seed=seed)


def select_labeling_items(
    rows: list[dict[str, Any]],
    *,
    limit: int,
    seed: str,
) -> list[dict[str, Any]]:
    """Pick a deterministic high/medium/low-score mix for labelers."""

    rows = list(rows)
    rows.sort(
        key=lambda row: (
            -(float(row.get("interestingness_score") or 0)),
            row.get("candidate_id") or "",
        )
    )
    if len(rows) <= limit:
        return rows

    high_target = max(1, int(limit * 0.50))
    medium_target = max(1, int(limit * 0.30))
    low_target = max(0, limit - high_target - medium_target)

    high = rows[: max(high_target * 2, high_target)]
    medium_start = max(0, len(rows) // 3)
    medium = rows[medium_start : medium_start + max(medium_target * 3, medium_target)]
    low = rows[-max(low_target * 4, low_target or 1) :]

    rng = random.Random(seed)
    selected = (
        _sample(high, high_target, rng)
        + _sample(medium, medium_target, rng)
        + _sample(low, low_target, rng)
    )
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in selected + rows:
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        deduped.append(row)
        if len(deduped) >= limit:
            break

    deduped.sort(
        key=lambda row: (
            -(float(row.get("interestingness_score") or 0)),
            row.get("candidate_id") or "",
        )
    )
    return deduped


def build_pairwise_rows(
    rows: list[dict[str, Any]],
    *,
    batch_id: str,
    pair_count: int,
    seed: str,
) -> list[dict[str, Any]]:
    """Build deterministic pairwise comparison rows from item candidates."""

    if pair_count <= 0 or len(rows) < 2:
        return []

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            row.get("category") or "",
            -(float(row.get("interestingness_score") or 0)),
            row.get("candidate_id") or "",
        ),
    )
    adjacent_pairs = [
        (left, right, "same_category_adjacent")
        for left, right in zip(sorted_rows, sorted_rows[1:])
        if left.get("category") == right.get("category")
    ]

    rng = random.Random(seed)
    shuffled = list(rows)
    rng.shuffle(shuffled)
    mixed_pairs = [
        (left, right, "seeded_cross_category")
        for left, right in zip(shuffled[::2], shuffled[1::2])
        if left.get("candidate_id") != right.get("candidate_id")
    ]

    pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for left, right, strategy in adjacent_pairs + mixed_pairs:
        left_id = str(left.get("candidate_id") or "")
        right_id = str(right.get("candidate_id") or "")
        key = tuple(sorted((left_id, right_id)))
        if not left_id or not right_id or key in seen:
            continue
        seen.add(key)
        pair_id = f"pair:{len(pairs) + 1:04d}:{_stable_hash([batch_id, left_id, right_id])[:10]}"
        pairs.append(
            {
                "batch_id": batch_id,
                "row_type": "pair",
                "pair_id": pair_id,
                "left_candidate_id": left_id,
                "right_candidate_id": right_id,
                "left_name": left.get("name") or "",
                "right_name": right.get("name") or "",
                "left_category": left.get("category") or "",
                "right_category": right.get("category") or "",
                "left_interestingness_score": left.get("interestingness_score") or "",
                "right_interestingness_score": right.get("interestingness_score") or "",
                "pair_strategy": strategy,
                "human_preference": "",
                "human_notes": "",
            }
        )
        if len(pairs) >= pair_count:
            break
    return pairs


def build_batch_metadata(
    *,
    args: argparse.Namespace | dict[str, Any],
    rows: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
    updated_since: datetime,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build reproducible metadata with a stable batch ID."""

    params = dict(vars(args) if isinstance(args, argparse.Namespace) else args)
    stable_params = {
        key: value
        for key, value in sorted(params.items())
        if key
        not in {
            "output",
            "metadata_output",
            "pairs_output",
            "print_sql",
        }
    }
    row_fingerprint = [
        {
            "candidate_id": row.get("candidate_id"),
            "score": row.get("interestingness_score"),
            "quality_class": row.get("quality_class"),
        }
        for row in rows
    ]
    batch_id = "dlb_" + _stable_hash(
        [EXPORT_VERSION, _isoformat(updated_since), stable_params, row_fingerprint]
    )[:16]
    generated_at = generated_at or datetime.now(timezone.utc)
    category_counts: dict[str, int] = {}
    quality_counts: dict[str, int] = {}
    for row in rows:
        category_counts[str(row.get("category") or "other")] = (
            category_counts.get(str(row.get("category") or "other"), 0) + 1
        )
        quality_counts[str(row.get("quality_class") or "unknown")] = (
            quality_counts.get(str(row.get("quality_class") or "unknown"), 0) + 1
        )

    return {
        "batch_id": batch_id,
        "export_version": EXPORT_VERSION,
        "generated_at": generated_at.isoformat(),
        "updated_since": _isoformat(updated_since),
        "git_sha": _git_sha(),
        "params": stable_params,
        "row_count": len(rows),
        "pair_count": len(pairs),
        "category_counts": dict(sorted(category_counts.items())),
        "quality_counts": dict(sorted(quality_counts.items())),
        "candidate_ids": [row.get("candidate_id") for row in rows],
    }


def attach_batch_id(rows: list[dict[str, Any]], *, batch_id: str) -> list[dict[str, Any]]:
    for row in rows:
        row["batch_id"] = batch_id
        if row.get("row_type", "item") == "item":
            row["card_snapshot"] = _json_compact(_candidate_card_snapshot(row))
    return rows


def write_rows(
    rows: Iterable[dict[str, Any]],
    handle: TextIO,
    *,
    fmt: str,
    fields: list[str],
) -> None:
    rows = list(rows)
    if fmt == "jsonl":
        for row in rows:
            handle.write(json.dumps(_compact_row(row), sort_keys=True) + "\n")
        return

    writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(_compact_row(row))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Item output path. Defaults to stdout.")
    parser.add_argument("--format", choices=("csv", "jsonl"), default="csv")
    parser.add_argument("--metadata-output", help="Metadata JSON path.")
    parser.add_argument("--pairs-output", help="Pairwise output path.")
    parser.add_argument("--pair-count", type=int, default=50)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--candidate-pool-limit", type=int, default=1000)
    parser.add_argument("--status", action="append")
    parser.add_argument("--source", action="append")
    parser.add_argument("--category", action="append")
    parser.add_argument("--min-volume-24h", type=int)
    parser.add_argument("--seed", default="discover-labeling-v1")
    parser.add_argument(
        "--print-sql",
        action="store_true",
        help="Print the compiled SQL instead of querying the database.",
    )
    args = parser.parse_args()

    updated_since = datetime.now(timezone.utc) - timedelta(days=args.days)
    statuses = tuple(args.status or ["open"])
    sources = tuple(args.source) if args.source else None
    categories = tuple(args.category) if args.category else None

    if args.print_sql:
        statement = build_candidate_statement(
            updated_since=updated_since,
            candidate_pool_limit=args.candidate_pool_limit,
            statuses=statuses,
            sources=sources,
            categories=categories,
            min_volume_24h=args.min_volume_24h,
        )
        print(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        return 0

    return asyncio.run(
        _run_cli(
            args=args,
            updated_since=updated_since,
            statuses=statuses,
            sources=sources,
            categories=categories,
        )
    )


async def _run_cli(
    *,
    args: argparse.Namespace,
    updated_since: datetime,
    statuses: tuple[str, ...],
    sources: tuple[str, ...] | None,
    categories: tuple[str, ...] | None,
) -> int:
    from app.services.database import async_session_maker

    async with async_session_maker() as session:
        rows = await export_candidate_rows(
            session,
            updated_since=updated_since,
            limit=args.limit,
            candidate_pool_limit=args.candidate_pool_limit,
            statuses=statuses,
            sources=sources,
            categories=categories,
            min_volume_24h=args.min_volume_24h,
            seed=args.seed,
        )

    metadata_stub = build_batch_metadata(
        args=args,
        rows=rows,
        pairs=[],
        updated_since=updated_since,
    )
    batch_id = metadata_stub["batch_id"]
    attach_batch_id(rows, batch_id=batch_id)
    pairs = build_pairwise_rows(
        rows,
        batch_id=batch_id,
        pair_count=args.pair_count,
        seed=args.seed,
    )
    metadata = build_batch_metadata(
        args=args,
        rows=rows,
        pairs=pairs,
        updated_since=updated_since,
    )

    if args.output:
        item_path = Path(args.output)
        with item_path.open("w", newline="") as handle:
            write_rows(rows, handle, fmt=args.format, fields=ITEM_FIELDS)
    else:
        write_rows(rows, sys.stdout, fmt=args.format, fields=ITEM_FIELDS)

    metadata_output = args.metadata_output
    if not metadata_output and args.output:
        metadata_output = str(Path(args.output).with_suffix(".metadata.json"))
    if metadata_output:
        with Path(metadata_output).open("w") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True)
            handle.write("\n")

    pairs_output = args.pairs_output
    if not pairs_output and args.output and args.pair_count > 0:
        suffix = ".pairs.jsonl" if args.format == "jsonl" else ".pairs.csv"
        pairs_output = str(Path(args.output).with_suffix(suffix))
    if pairs_output:
        with Path(pairs_output).open("w", newline="") as handle:
            write_rows(pairs, handle, fmt=args.format, fields=PAIR_FIELDS)

    return 0


def _sample(
    rows: list[dict[str, Any]],
    count: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    if len(rows) <= count:
        return list(rows)
    return rng.sample(rows, count)


def _stable_hash(parts: list[Any]) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def _candidate_card_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "discover-card-v1",
        "batch_id": row.get("batch_id") or "",
        "item_type": "futures",
        "item_id": row.get("market_id"),
        "market_id": row.get("market_id"),
        "name": row.get("name") or "",
        "source": row.get("source") or "",
        "category": row.get("llm_sport_category") or row.get("category") or "",
        "archetype": row.get("llm_archetype") or "",
        "quality_class": row.get("quality_class") or "",
        "hook_description": row.get("hook_description") or "",
        "image_url": row.get("image_url") or "",
        "story_key": row.get("story_key") or "",
        "family_key": row.get("family_key") or "",
        "group_id": row.get("group_id") or "",
        "rendered_probability": row.get("leader_probability"),
        "top_outcomes": [
            {
                "name": row.get("leader_name") or "",
                "probability": row.get("leader_probability"),
            }
        ] if row.get("leader_name") or row.get("leader_probability") not in (None, "") else [],
        "reasons": json.loads(row.get("quality_reasons") or "[]"),
    }


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


def _git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT.parent,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


if __name__ == "__main__":
    raise SystemExit(main())
