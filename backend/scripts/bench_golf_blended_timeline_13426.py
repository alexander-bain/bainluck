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
from typing import Sequence

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.routes import golf as golf_route  # noqa: E402
from app.utils.golf_blended_timeline import (  # noqa: E402
    ClosedBucketEntry,
    SnapshotReading,
    build_golf_blended_timeline,
    detach_winner_market,
    history_fetch_floor,
)


def _synthetic_markets_and_snaps(
    *,
    n_golfers: int,
    n_sources: int,
    pre_tee_days: int,
    pre_step_hours: int,
    play_days: int,
    play_step_minutes: int,
    full_range: bool,
    now: datetime,
):
    commence = now - timedelta(days=play_days)
    floor_dt = history_fetch_floor(
        now,
        hours=168,
        full_range=full_range,
        max_reading_age=golf_route.PREGAME_READING_MAX_AGE,
    )

    markets = []
    snapshots: list[SnapshotReading] = []
    oid_counter = 1
    for s_idx in range(n_sources):
        src = "datagolf" if s_idx == 0 else "kalshi"
        outcomes = []
        for g_idx in range(n_golfers):
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
                resolution_date=commence + timedelta(days=play_days),
                status="open",
                llm_sport_category="golf",
                market_tier=1,
                market_metadata=None,
                mutually_exclusive=True,
            )
        )

    timestamps: list[tuple[datetime, int]] = []
    total_pre_hours = pre_tee_days * 24
    for h in range(total_pre_hours, 0, -pre_step_hours):
        timestamps.append((commence - timedelta(hours=h), pre_step_hours * 3600))
    total_play_min = play_days * 24 * 60
    for m_off in range(0, total_play_min + 1, play_step_minutes):
        timestamps.append((commence + timedelta(minutes=m_off), play_step_minutes * 60))

    rows_total = len(timestamps) * sum(len(m.outcomes) for m in markets)
    rows_read = 0
    for step_idx, (ts, step_s) in enumerate(timestamps):
        if ts < floor_dt or ts > now:
            continue
        delta = (((step_idx % 5) - 2) * 0.001)
        valid_h = max(2, (step_s // 3600) + 1)
        for m in markets:
            for g_idx, o in enumerate(m.outcomes):
                p = o.current_probability
                if g_idx == 0:
                    p = min(0.99, max(0.001, round(p + delta, 4)))
                snapshots.append(
                    SnapshotReading(
                        outcome_id=o.id,
                        captured_at=ts,
                        valid_until=ts + timedelta(hours=valid_h),
                        probability=p,
                        yes_bid=max(0.001, round(p - 0.003, 4)),
                        yes_ask=min(0.999, round(p + 0.003, 4)),
                    )
                )
                rows_read += 1

    current_entry = golf_route._build_one_tournament("synthetic", markets, {})
    assert current_entry is not None
    detached = [detach_winner_market(m) for m in markets]
    return markets, detached, current_entry, snapshots, commence, rows_total, rows_read


def _time_build(
    *,
    label: str,
    detached,
    current_entry,
    snapshots: Sequence[SnapshotReading],
    commence: datetime,
    full_range: bool,
    is_live: bool,
    now: datetime,
    rows_total: int,
    rows_read: int,
    closed_cache: dict[tuple[int, int], ClosedBucketEntry],
) -> dict:
    stats: dict[str, int] = {}
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
        closed_bucket_cache=closed_cache,
        build_stats=stats,
        now=now,
    )
    elapsed = time.perf_counter() - t0
    pts = payload["timeline"]
    play_pts = sum(1 for pt in pts if datetime.fromisoformat(pt["timestamp"]) >= commence)
    return {
        "case": label,
        "full_range": full_range,
        "rows_total_in_table": rows_total,
        "rows_read": rows_read,
        "timeline_points": len(pts),
        "pre_tee_points": len(pts) - play_pts,
        "play_points": play_pts,
        "bucket_seconds": payload["bucket_seconds"],
        "evaluated": stats.get("evaluated", 0),
        "reused": stats.get("reused", 0),
        "seconds": round(elapsed, 4),
    }


def run_synthetic() -> list[dict]:
    now = datetime(2031, 6, 15, 16, 0, tzinfo=timezone.utc)
    markets, detached, current_entry, snapshots, commence, rows_total, rows_read = (
        _synthetic_markets_and_snaps(
            n_golfers=156,
            n_sources=2,
            pre_tee_days=10,
            pre_step_hours=1,
            play_days=4,
            play_step_minutes=15,
            full_range=True,
            now=now,
        )
    )
    closed_cache: dict[tuple[int, int], ClosedBucketEntry] = {}
    cold_156 = _time_build(
        label="worst_case_full_build_156_golfers_14d_with_4d_play_15m",
        detached=detached,
        current_entry=current_entry,
        snapshots=snapshots,
        commence=commence,
        full_range=True,
        is_live=True,
        now=now,
        rows_total=rows_total,
        rows_read=rows_read,
        closed_cache=closed_cache,
    )

    # Simulate a live poll 15 minutes later with 1 new tick appended.
    next_ts = now + timedelta(minutes=15)
    new_snaps = list(snapshots)
    for m in markets:
        for g_idx, o in enumerate(m.outcomes):
            p = min(0.99, max(0.001, round(o.current_probability + (0.002 if g_idx == 0 else 0.0), 4)))
            new_snaps.append(
                SnapshotReading(
                    outcome_id=o.id,
                    captured_at=next_ts,
                    valid_until=next_ts + timedelta(hours=2),
                    probability=p,
                    yes_bid=max(0.001, round(p - 0.003, 4)),
                    yes_ask=min(0.999, round(p + 0.003, 4)),
                )
            )
    warm_156 = _time_build(
        label="live_refresh_during_play_156_golfers_4d_15m",
        detached=detached,
        current_entry=current_entry,
        snapshots=new_snaps,
        commence=commence,
        full_range=True,
        is_live=True,
        now=next_ts,
        rows_total=rows_total + len(detached) * 156,
        rows_read=rows_read + len(detached) * 156,
        closed_cache=closed_cache,
    )

    _, det_m, cur_m, snaps_m, comm_m, rows_tot_m, rows_read_m = _synthetic_markets_and_snaps(
        n_golfers=120,
        n_sources=2,
        pre_tee_days=296,
        pre_step_hours=4,
        play_days=4,
        play_step_minutes=15,
        full_range=True,
        now=now,
    )
    major_300d = _time_build(
        label="major_300d_with_4d_play_15m_full_capped_90d",
        detached=det_m,
        current_entry=cur_m,
        snapshots=snaps_m,
        commence=comm_m,
        full_range=True,
        is_live=True,
        now=now,
        rows_total=rows_tot_m,
        rows_read=rows_read_m,
        closed_cache={},
    )
    return [cold_156, warm_156, major_300d]


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
