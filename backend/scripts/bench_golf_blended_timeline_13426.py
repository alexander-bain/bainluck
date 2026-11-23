"""Read-only timing benchmark for #13426 golf blended tournament timeline.

Supports two modes:
- ``--synthetic``: local simulation of (a) 1 live full-field tournament (156 golfers,
  2 sources, 4 days of dense snapshots) and (b) 1 multi-month major (120 golfers,
  90+ days of snapshots). No database or network access.
- ``--live-db``: read-only timing against PostgreSQL for one live full-field
  tournament and one multi-month major. Run ONLY when explicitly approved and
  never during blackout windows.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.routes import golf as golf_route  # noqa: E402
from app.utils.golf_blended_timeline import (  # noqa: E402
    SnapshotReading,
    build_golf_blended_timeline,
    detach_winner_market,
    history_fetch_floor,
)


def _run_synthetic_case(
    *,
    label: str,
    n_golfers: int,
    n_sources: int,
    span_days: int,
    snap_step_hours: int,
    is_live: bool,
    full_range: bool,
) -> dict:
    now = datetime(2031, 6, 15, 16, 0, tzinfo=timezone.utc)
    commence = now - timedelta(days=2) if is_live else now + timedelta(days=14)

    markets = []
    snapshots: list[SnapshotReading] = []
    oid_counter = 1
    for s_idx in range(n_sources):
        src = "datagolf" if s_idx == 0 else "kalshi"
        outcomes = []
        for g_idx in range(n_golfers):
            # Concentrated power-law weights summing near 1.0
            base_prob = round(max(0.002, 0.25 / ((g_idx + 1) ** 0.85)), 4)
            outcomes.append(
                SimpleNamespace(
                    id=oid_counter,
                    external_id=f"{src}_{oid_counter}",
                    name=f"Player {g_idx + 1:03d} Lastname",
                    current_probability=base_prob,
                    current_yes_bid=max(0.001, base_prob - 0.003),
                    current_yes_ask=min(0.999, base_prob + 0.003),
                    opening_probability=None,
                    probability_change_24h=None,
                    is_winner=None,
                    resolution_source=None,
                )
            )
            oid_counter += 1
        markets.append(
            SimpleNamespace(
                id=100 + s_idx,
                name="Synthetic Tournament Winner",
                source=src,
                external_id=f"{src}:pga:synthetic:win" if src == "datagolf" else "KXSYNTH-26",
                outcomes=outcomes,
                commence_time=commence,
                resolution_date=commence + timedelta(days=4),
                status="open",
                llm_sport_category="golf",
                market_tier=1,
                market_metadata=None,
                mutually_exclusive=True,
            )
        )

    total_hours = span_days * 24
    floor_dt = history_fetch_floor(
        now,
        hours=168,
        full_range=full_range,
        max_reading_age=golf_route.PREGAME_READING_MAX_AGE,
    )
    rows_generated = 0
    rows_inside_floor = 0
    for h in range(0, total_hours + 1, snap_step_hours):
        ts = now - timedelta(hours=h)
        rows_generated += sum(len(m.outcomes) for m in markets)
        if ts < floor_dt:
            continue
        for m in markets:
            for o in m.outcomes:
                snapshots.append(
                    SnapshotReading(
                        outcome_id=o.id,
                        captured_at=ts,
                        valid_until=ts + timedelta(hours=max(2, snap_step_hours)),
                        probability=o.current_probability,
                        yes_bid=o.current_yes_bid,
                        yes_ask=o.current_yes_ask,
                    )
                )
                rows_inside_floor += 1

    current_entry = golf_route._build_one_tournament("synthetic", markets, {})
    assert current_entry is not None
    detached = [detach_winner_market(m) for m in markets]

    t0 = time.perf_counter()
    payload = build_golf_blended_timeline(
        "synthetic",
        detached,
        current_entry,
        snapshots,
        build_entry=lambda k, mkts, snaps: golf_route._build_one_tournament(
            k, [golf_route._AsOfMarket(m, snaps) for m in mkts], {}
        ),
        match_key_fn=golf_route._match_key,
        top=10,
        hours=168,
        full_range=full_range,
        commence_time=commence,
        is_live=is_live,
        max_reading_age=golf_route.PREGAME_READING_MAX_AGE,
        now=now,
    )
    elapsed = time.perf_counter() - t0
    return {
        "case": label,
        "golfers": n_golfers,
        "sources": n_sources,
        "span_days": span_days,
        "full_range": full_range,
        "rows_total_in_table": rows_generated,
        "rows_read": rows_inside_floor,
        "timeline_points": len(payload["timeline"]),
        "bucket_seconds": payload["bucket_seconds"],
        "seconds": round(elapsed, 4),
    }


def run_synthetic() -> list[dict]:
    return [
        _run_synthetic_case(
            label="live_full_field_156_golfers_4d_15m",
            n_golfers=156,
            n_sources=2,
            span_days=4,
            snap_step_hours=1,
            is_live=True,
            full_range=False,
        ),
        _run_synthetic_case(
            label="multi_month_major_120_golfers_150d_full_capped_90d",
            n_golfers=120,
            n_sources=2,
            span_days=150,
            snap_step_hours=4,
            is_live=False,
            full_range=True,
        ),
    ]


async def run_live_db() -> list[dict]:
    """Read-only timing against PostgreSQL for 1 live field + 1 multi-month major."""
    from fastapi import Response
    from sqlalchemy import select, func as sqlfunc

    from app.models import FuturesOddsSnapshot
    from app.services.database import async_session_maker
    from app.utils.golf_blended_timeline import reset_timeline_cache_for_tests

    results: list[dict] = []
    async with async_session_maker() as db:
        golf_data = await golf_route.get_golf(db=db)
        tournaments = golf_data.get("tournaments", []) or []
        live_t = next(
            (t for t in tournaments if str(t.get("schedule_status") or "").lower() in ("in-progress", "in_progress", "live")),
            tournaments[0] if tournaments else None,
        )
        major_t = next((t for t in tournaments if t.get("is_major")), tournaments[-1] if tournaments else None)
        picks = []
        if live_t is not None:
            picks.append(("live_full_field", live_t, None))
        if major_t is not None and (live_t is None or major_t.get("slug") != live_t.get("slug")):
            picks.append(("multi_month_major", major_t, "full"))
        elif major_t is not None:
            picks.append(("multi_month_major_range_full", major_t, "full"))

        for label, tourn, rng in picks:
            slug = tourn.get("slug") or golf_route._clean_slug(tourn["name"])
            mids = list(tourn.get("market_ids") or [])
            floor_dt = history_fetch_floor(
                datetime.now(timezone.utc),
                hours=168,
                full_range=(rng == "full"),
                max_reading_age=golf_route.PREGAME_READING_MAX_AGE,
            )
            row_count = 0
            if mids:
                from app.models import FuturesOutcome

                cnt_stmt = (
                    select(sqlfunc.count(FuturesOddsSnapshot.id))
                    .select_from(FuturesOddsSnapshot)
                    .join(FuturesOutcome, FuturesOutcome.id == FuturesOddsSnapshot.outcome_id)
                    .where(
                        FuturesOutcome.market_id.in_(mids),
                        FuturesOddsSnapshot.probability.isnot(None),
                        sqlfunc.coalesce(
                            FuturesOddsSnapshot.valid_until,
                            FuturesOddsSnapshot.captured_at,
                        ) >= floor_dt,
                    )
                )
                row_count = int((await db.execute(cnt_stmt)).scalar_one() or 0)

            reset_timeline_cache_for_tests()
            resp = Response()
            t0 = time.perf_counter()
            payload = await golf_route.get_golf_tournament_probability_timeline(
                slug=slug,
                response=resp,
                top=10,
                hours=168,
                history_range=rng,
                db=db,
            )
            elapsed = time.perf_counter() - t0
            results.append({
                "case": label,
                "slug": slug,
                "range": rng or "168h",
                "rows_read": row_count,
                "timeline_points": len(payload.get("timeline") or []),
                "bucket_seconds": payload.get("bucket_seconds"),
                "seconds": round(elapsed, 4),
            })
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--synthetic", action="store_true")
    mode.add_argument("--live-db", action="store_true")
    args = parser.parse_args()

    if args.synthetic:
        out = run_synthetic()
    else:
        out = asyncio.run(run_live_db())
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
