"""Pre-ranking Discover candidate-pool snapshot for offline replay (#142/RANK-2).

The keystone of the offline replay harness. Each run persists the scored futures
candidate pool with, per candidate, the served rank, the interestingness input
features, and the RANK-1 score anatomy. A frozen snapshot can then be re-ranked
under a different config (InterestingnessWeights + blend weight + base scores)
and diffed against the served ordering, the human-label gold set, and classifier
metrics — see ``scripts/replay_discover_ranking.py``.

This module is eval infrastructure only. It reuses the existing feed scoring and
tracer code paths read-only; it never mutates ranking behavior.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import DiscoverCandidateSnapshot, FuturesMarket

DEFAULT_LIMIT = 300
DEFAULT_RETENTION_DAYS = 30


def _json_safe(obj: Any) -> Any:
    """Recursively coerce Decimal → float so a value is JSON-serializable.

    The ``features``/``anatomy`` JSONB columns are built from FuturesOutcome
    Numeric fields (current_probability, etc.), which SQLAlchemy hands back as
    ``Decimal``. asyncpg's JSONB encoder raises ``TypeError: Object of type
    Decimal is not JSON serializable`` on insert (the #195/consec-6 failure of
    ``discover_candidate_snapshot``). Sanitize the dicts before persisting.
    """
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _leader_probability(market: FuturesMarket) -> float | None:
    probs = [
        o.current_probability
        for o in market.outcomes
        if o.current_probability is not None
    ]
    return max(probs) if probs else None


def _max_movement(market: FuturesMarket) -> float | None:
    moves = [
        abs(o.probability_change_24h)
        for o in market.outcomes
        if o.probability_change_24h is not None
    ]
    peak = max(moves) if moves else 0.0
    return peak if peak > 0 else None


def _llm_quality(market: FuturesMarket) -> float | None:
    metadata = market.market_metadata or {}
    discover_llm = metadata.get("discover_llm")
    if isinstance(discover_llm, dict):
        return discover_llm.get("quality_score")
    return None


def build_candidate_features(market: FuturesMarket, *, source_count: int) -> dict[str, Any]:
    """Interestingness-scorer input features, mirroring precompute_interestingness.

    Field names match ``MarketInterestingnessInputs.from_mapping`` aliases so the
    replay runner can rebuild inputs and recompute interestingness under a new
    weight config. ``trending``/``charting`` are intentionally omitted here (the
    TMDB/chart title sets are not fetched offline); the replay recomputes on the
    8 weighted signals — the knobs the calibrator actually tunes. This is a small,
    documented fidelity gap for the +6 entertainment cultural-hotness bonus.
    """

    return {
        "leader_probability": _leader_probability(market),
        "source_count": source_count,
        "updated_at": market.updated_at.isoformat() if market.updated_at else None,
        "movement_24h": _max_movement(market),
        "resolution_date": (
            market.resolution_date.isoformat() if market.resolution_date else None
        ),
        "category": market.llm_sport_category,
        "volume_24h": (
            float(market.volume_24h) if market.volume_24h is not None else None
        ),
        "llm_quality": _llm_quality(market),
    }


async def snapshot_discover_candidate_pool(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = DEFAULT_LIMIT,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> dict[str, Any]:
    """Score the anonymous Discover candidate pool once and persist a snapshot.

    Returns a small run summary. Reuses ``feed._score_futures`` for the served
    ordering and ``feed._score_market_trace`` for the per-candidate anatomy.
    """

    # Local imports: feed.py is heavy and would create an import cycle at module
    # load. This mirrors how tasks/__init__.py imports task impls lazily.
    from app.routes.feed import (
        _get_canonical_source_counts,
        _rank_key,
        _score_futures,
        _score_market_trace,
    )
    from app.utils.personalization import PersonalizationContext

    now = now or datetime.now(timezone.utc)
    run_id = str(uuid4())

    # Anonymous context = the baseline ranker (no per-user personalization). This
    # is the correct eval substrate: personalization is a per-user post-multiplier
    # layered on top of the base ranking the replay harness tunes.
    ctx = PersonalizationContext()
    scored = await _score_futures(db, now, None, ctx)
    scored.sort(key=_rank_key, reverse=True)
    top = scored[:limit]

    ids = [
        item["data"]["id"]
        for item in top
        if isinstance(item.get("data"), dict) and item["data"].get("id")
    ]
    if not ids:
        return {
            "status": "empty",
            "run_id": run_id,
            "count": 0,
            "candidates_scored": len(scored),
        }

    result = await db.execute(
        select(FuturesMarket)
        .options(
            selectinload(FuturesMarket.outcomes),
            selectinload(FuturesMarket.sport),
        )
        .where(FuturesMarket.id.in_(ids))
    )
    markets = {m.id: m for m in result.scalars().all()}
    canonical_counts = await _get_canonical_source_counts(db)

    rows: list[DiscoverCandidateSnapshot] = []
    for served_rank, item in enumerate(top, start=1):
        market_id = item["data"]["id"]
        market = markets.get(market_id)
        if market is None:
            continue
        source_count = (
            canonical_counts.get(market.canonical_market_key, 1)
            if market.canonical_market_key
            else 1
        )
        trace = _score_market_trace(market, now, source_count)
        anatomy = trace.get("score_anatomy", {}) if isinstance(trace, dict) else {}
        ranking = anatomy.get("ranking", {}) if isinstance(anatomy, dict) else {}
        data = item.get("data") or {}
        rows.append(
            DiscoverCandidateSnapshot(
                run_id=run_id,
                market_id=market_id,
                item_type="futures",
                served_rank=served_rank,
                name=(market.name or "")[:500],
                category=market.llm_sport_category,
                source=market.source,
                quality_class=item.get("_quality_class"),
                family_key=item.get("_quality_family_key"),
                story_key=item.get("_quality_story_key"),
                rank_score=item.get("_rank_score"),
                display_score=item.get("score"),
                pre_blend_rank_score=ranking.get("final_uncapped"),
                category_base=anatomy.get("category_base"),
                interestingness_score=data.get("interestingness_score"),
                features=_json_safe(
                    build_candidate_features(market, source_count=source_count)
                ),
                anatomy=_json_safe(anatomy),
            )
        )

    db.add_all(rows)
    # Retention: drop snapshots older than the window so the table stays bounded.
    cutoff = now - timedelta(days=retention_days)
    await db.execute(
        delete(DiscoverCandidateSnapshot).where(
            DiscoverCandidateSnapshot.captured_at < cutoff
        )
    )
    await db.commit()

    return {
        "status": "ok",
        "run_id": run_id,
        "count": len(rows),
        "candidates_scored": len(scored),
        "limit": limit,
        "retention_days": retention_days,
    }


# --------------------------------------------------------------------------- #
# Email lead-time metric (#142/RANK-2, plan addendum item 1)
# --------------------------------------------------------------------------- #
def compute_email_lead_time_rows(
    first_surfaced_by_market: dict[int, dict[str, Any]],
    email_items: list[dict[str, Any]],
    *,
    name_matcher,
) -> dict[str, Any]:
    """Did we surface a market before Polymarket's email featured it?

    ``first_surfaced_by_market`` maps market_id -> {"name", "first_surfaced_at"}
    (earliest snapshot ``captured_at`` for the market). ``email_items`` are the
    Polymarket email ground-truth rows (each with ``name`` + ``date``). For each
    dated email item we find the matching snapshot market by name and compare our
    first-surfaced date to the email date. "Beat the email" = we surfaced it on or
    before the email date — the timeliness ground truth and the anti-Kalshi thesis
    as a number.
    """

    surfaced = [
        {
            "market_id": mid,
            "name": info.get("name") or "",
            "first_surfaced_at": info.get("first_surfaced_at"),
        }
        for mid, info in first_surfaced_by_market.items()
        if info.get("first_surfaced_at") is not None
    ]

    matched_rows: list[dict[str, Any]] = []
    for item in email_items:
        email_name = item.get("name") or ""
        email_date = _parse_iso_date(item.get("date"))
        if not email_name or email_date is None:
            continue
        match = next(
            (s for s in surfaced if name_matcher(email_name, s["name"])),
            None,
        )
        if match is None:
            continue
        surfaced_date = match["first_surfaced_at"]
        surfaced_day = (
            surfaced_date.date() if hasattr(surfaced_date, "date") else surfaced_date
        )
        lead_days = (email_date - surfaced_day).days
        matched_rows.append(
            {
                "market_id": match["market_id"],
                "email_name": email_name,
                "our_name": match["name"],
                "email_date": email_date.isoformat(),
                "our_first_surfaced": surfaced_day.isoformat(),
                "lead_days": lead_days,  # positive = we beat the email
                "beat_email": lead_days >= 0,
            }
        )

    matched = len(matched_rows)
    beat = sum(1 for r in matched_rows if r["beat_email"])
    leads = [r["lead_days"] for r in matched_rows]
    note = None
    if matched == 0:
        note = (
            "No matched dated email items yet. Snapshot history accrues daily; "
            "the metric is meaningful once the candidate-pool snapshot has run "
            "across the email window."
        )
    return {
        "matched": matched,
        "beat_email_count": beat,
        "beat_email_rate": round(beat / matched, 4) if matched else None,
        "mean_lead_days": round(sum(leads) / len(leads), 2) if leads else None,
        "median_lead_days": _median(leads) if leads else None,
        "rows": sorted(matched_rows, key=lambda r: r["lead_days"], reverse=True),
        "note": note,
    }


async def load_first_surfaced_by_market(
    db: AsyncSession,
    *,
    days: int = 30,
) -> dict[int, dict[str, Any]]:
    """Earliest snapshot ``captured_at`` (and name) per market within the window."""
    from sqlalchemy import func as _func

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            DiscoverCandidateSnapshot.market_id,
            _func.min(DiscoverCandidateSnapshot.captured_at).label("first_surfaced_at"),
            _func.max(DiscoverCandidateSnapshot.name).label("name"),
        )
        .where(DiscoverCandidateSnapshot.captured_at >= cutoff)
        .group_by(DiscoverCandidateSnapshot.market_id)
    )
    return {
        row.market_id: {"name": row.name, "first_surfaced_at": row.first_surfaced_at}
        for row in result.all()
    }


async def compute_email_lead_time(
    db: AsyncSession,
    *,
    days: int = 30,
) -> dict[str, Any]:
    """Load snapshot first-surfaced dates + email ground truth and compute the metric."""
    from app.utils.feed_quality_debug import _names_match
    from app.utils.polymarket_email_ground_truth import (
        load_polymarket_email_ground_truth_report_from_env,
    )

    first_surfaced = await load_first_surfaced_by_market(db, days=days)
    report = load_polymarket_email_ground_truth_report_from_env()
    email_items = report.get("items", []) if isinstance(report, dict) else []
    metric = compute_email_lead_time_rows(
        first_surfaced, email_items, name_matcher=_names_match
    )
    metric["window_days"] = days
    metric["snapshot_markets"] = len(first_surfaced)
    metric["email_items"] = len(email_items)
    return metric


def _parse_iso_date(value: Any):
    if not value:
        return None
    if hasattr(value, "date") and not isinstance(value, str):
        return value.date() if hasattr(value, "date") else value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2
