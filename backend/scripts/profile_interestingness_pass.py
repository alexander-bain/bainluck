#!/usr/bin/env python3
"""#1716 / LAT-P042 — stage-level profile of one `precompute_interestingness` pass.

WHY THIS EXISTS
---------------
`precompute_interestingness` is hard-killed on every single run. Production,
2026-08-12: `starts_24h: 6`, `hard_kills_24h: 6`, `successes_24h: 0`,
`failures_24h: 0`, `incompletes_24h: 0`, `recent_durations_n: 0`. The global
celery `task_time_limit=300` is a HARD limit, so the worker is SIGKILLed and no
end handler ever runs — the task therefore **cannot record its own duration**,
which is precisely why a profiler has to run outside it.

A one-off dyno is not subject to `task_time_limit`, so it can run the same work
to completion and time each stage. That is the only way to answer the question
the fix depends on: is this a pass that *nearly* fits (soft limit + batched
flush is enough) or one that *cannot* fit (needs resumability)?

MEASUREMENT ONLY — IT DOES NOT WRITE THE CACHE
----------------------------------------------
It deliberately does NOT write `interestingness:{id}` keys. The cache is
currently EMPTY (verified by a full-keyspace census: 16,602 of 16,613 keys
scanned, zero `interestingness:*`), so writing it here would silently switch a
20%-weight, admittedly-uncalibrated Discover ranking blend back on as a side
effect of a diagnostic. Restoring that signal is the queue's payoff and belongs
to the scheduled task through its normal beat, not to a profiler.

Write throughput is measured against throwaway `bainluck:latp042scratch:*` keys
at a 60s TTL instead, and they are deleted before exit.

    heroku run:detached -a bainluck -- python3 scripts/profile_interestingness_pass.py

Gotcha #48: a non-detached `heroku run` does not execute at all in an agent
sandbox. Gotcha (memory `reference_heroku_oneoff_dyno_no_cd_backend`): scripts
live at `/app`, NOT `/app/backend` — a `cd backend &&` prefix silently no-ops.
Never trust the dyno's stdout; results are written to Redis and read back with:

    GET /api/admin/redis-read?key=bainluck:lat_p042_interestingness_profile
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

RESULT_KEY = "bainluck:lat_p042_interestingness_profile"
SCRATCH_PREFIX = "bainluck:latp042scratch:"


def rss_mb() -> float | None:
    """Current resident set size in MB, or None off-Linux.

    RSS is the measurement that matters here, not wall time: the pass completes
    in ~15s, so it cannot be hitting `task_time_limit=300`. What it CAN hit is
    the 512 MB of a Standard-1X `worker-background` dyno, which Heroku answers
    with R14 and then R15 — and an R15 is a SIGKILL, which is exactly the
    no-terminal, no-duration, no-traceback signature the metrics show.
    """
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024.0, 1)
    except Exception:
        pass
    return None


class Stopwatch:
    """Ordered stage timings, CHECKPOINTED TO REDIS AS THEY HAPPEN.

    Explicit laps beat a decorator here: the stages are not function-shaped
    (two of them are halves of one ORM call).

    The checkpointing is the load-bearing part, and it is the same lesson the
    task under measurement failed to learn. This profiler is diagnosing a
    process that is SIGKILLed — the health reason names MEMORY first — and a
    SIGKILLed process runs no `finally`, no `except`, and no end handler. A
    profiler that only writes its findings at the end would therefore die in
    exactly the cases worth measuring and report nothing, which is precisely
    the failure it exists to explain. `heroku logs` is egress-blocked from an
    agent sandbox, so stdout is not a fallback either.

    So every lap flushes the partial record. Eight small SETEXs against an
    already-open client is negligible next to the work being timed, and the
    last checkpoint written IS the answer: the stage after the final recorded
    one is the stage that killed it.
    """

    def __init__(self, redis_client=None):
        self.stages: list[tuple[str, float]] = []
        self._t = time.monotonic()
        self._r = redis_client

    def attach(self, redis_client) -> None:
        self._r = redis_client

    def lap(self, name: str) -> float:
        now = time.monotonic()
        ms = (now - self._t) * 1000.0
        self.stages.append((name, round(ms, 1), rss_mb()))
        self._t = now
        self.checkpoint(f"running:after:{name}")
        return ms

    def checkpoint(self, state: str) -> None:
        if self._r is None:
            return
        try:
            self._r.setex(RESULT_KEY, 86400, json.dumps(
                {"state": state, "complete": False,
                 "rss_mb_now": rss_mb(), **self.as_dict()}
            ))
        except Exception:
            pass  # a diagnostic must never be the thing that fails the run

    def as_dict(self) -> dict:
        return {
            "stages": [{"stage": n, "ms": ms, "rss_mb": rss}
                       for n, ms, rss in self.stages],
            "total_ms": round(sum(ms for _, ms, _ in self.stages), 1),
            "peak_rss_mb": max(
                [rss for _, _, rss in self.stages if rss is not None], default=None
            ),
        }


async def profile(scratch_n: int) -> dict:
    from sqlalchemy import select, func, or_
    from sqlalchemy.orm import load_only, selectinload

    from app.models import FuturesMarket, FuturesOutcome
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.utils.market_interestingness import (
        MarketInterestingnessInputs,
        score_market_interestingness,
    )
    # The network fetch helpers are deliberately NOT imported: this reads the
    # title caches only. Both keys were verified present in production, so the
    # fetch path is not what burns the budget.
    from app.tasks.enrich_tmdb import _extract_quoted_title, _normalize_title

    now = datetime.now(timezone.utc)
    sw = Stopwatch()

    r = get_redis_client()
    sw.attach(r)
    sw.lap("redis_client")

    # Cache-only reads. The real task falls back to a NETWORK fetch on a miss;
    # both keys were verified present in production, so the miss path is not
    # what is burning the budget and is not exercised here.
    trending_titles: set[str] = set()
    charting_titles: set[str] = set()
    tmdb_cached = music_cached = False
    try:
        cached = r.get("tmdb:trending_titles")
        if cached:
            trending_titles = set(json.loads(cached))
            tmdb_cached = True
    except Exception:
        pass
    try:
        cached_m = r.get("music:charting_titles")
        if cached_m:
            charting_titles = set(json.loads(cached_m))
            music_cached = True
    except Exception:
        pass
    sw.lap("load_title_sets")

    async with get_task_session() as session:
        sw.lap("db_session_open")

        result = await session.execute(
            select(FuturesMarket)
            .options(
                load_only(
                    FuturesMarket.id,
                    FuturesMarket.name,
                    FuturesMarket.llm_sport_category,
                    FuturesMarket.canonical_market_key,
                    FuturesMarket.volume_24h,
                    FuturesMarket.updated_at,
                    FuturesMarket.resolution_date,
                    FuturesMarket.market_metadata,
                    FuturesMarket.status,
                ),
                selectinload(FuturesMarket.outcomes).load_only(
                    FuturesOutcome.current_probability,
                    FuturesOutcome.probability_change_24h,
                ),
            )
            .where(
                FuturesMarket.status == "open",
                FuturesMarket.event_id.is_(None),
                or_(
                    FuturesMarket.resolution_date.is_(None),
                    FuturesMarket.resolution_date >= now,
                ),
            )
        )
        sw.lap("market_query_execute")

        markets = result.scalars().unique().all()
        sw.lap("market_materialize")

        outcome_rows = sum(len(m.outcomes) for m in markets)
        sw.lap("outcome_touch")

        canonical_keys = {m.canonical_market_key for m in markets if m.canonical_market_key}
        source_counts: dict[str, int] = {}
        if canonical_keys:
            count_result = await session.execute(
                select(
                    FuturesMarket.canonical_market_key,
                    func.count(func.distinct(FuturesMarket.source)).label("cnt"),
                )
                .where(FuturesMarket.canonical_market_key.in_(canonical_keys))
                .group_by(FuturesMarket.canonical_market_key)
            )
            source_counts = {row.canonical_market_key: row.cnt for row in count_result.all()}
        sw.lap("source_count_query")

    sw.lap("db_session_close")

    # The scoring loop, byte-for-byte the task's logic minus the redis write.
    scored = errors = 0
    payload_bytes = 0
    for idx, market in enumerate(markets):
        # Mid-loop checkpoints: if the loop itself is what dies, the stage-level
        # record would otherwise stop at "started scoring" and say nothing about
        # how far it got or how fast it was going.
        if idx and idx % 5000 == 0:
            sw.checkpoint(f"running:scoring_loop:{idx}/{len(markets)}")
        try:
            leader_prob = None
            max_movement = 0.0
            for outcome in market.outcomes:
                prob = (float(outcome.current_probability)
                        if outcome.current_probability is not None else None)
                if prob is not None and (leader_prob is None or prob > leader_prob):
                    leader_prob = prob
                change = (float(outcome.probability_change_24h)
                          if outcome.probability_change_24h is not None else None)
                if change is not None and abs(change) > max_movement:
                    max_movement = abs(change)

            source_count = 1
            if market.canonical_market_key:
                source_count = source_counts.get(market.canonical_market_key, 1)

            llm_quality = None
            metadata = market.market_metadata or {}
            discover_llm = metadata.get("discover_llm")
            if isinstance(discover_llm, dict):
                llm_quality = discover_llm.get("quality_score")

            is_trending = is_charting = False
            if market.llm_sport_category == "entertainment" and (trending_titles or charting_titles):
                quoted = _normalize_title(_extract_quoted_title(market.name))
                norm_name = _normalize_title(market.name)
                if trending_titles:
                    if quoted and quoted in trending_titles:
                        is_trending = True
                    else:
                        is_trending = any(len(t) >= 5 and t in norm_name for t in trending_titles)
                if charting_titles:
                    if quoted and quoted in charting_titles:
                        is_charting = True
                    else:
                        is_charting = any(len(t) >= 5 and t in norm_name for t in charting_titles)

            inputs = MarketInterestingnessInputs(
                probability=leader_prob,
                source_count=source_count,
                updated_at=market.updated_at,
                movement_24h=max_movement if max_movement > 0 else None,
                resolution_date=market.resolution_date,
                category=market.llm_sport_category,
                volume_24h=(float(market.volume_24h) if market.volume_24h is not None else None),
                llm_quality=llm_quality,
                trending=is_trending,
                charting=is_charting,
            )
            res = score_market_interestingness(inputs, now=now)
            payload_bytes += len(json.dumps(
                {"score": res.score, "reasons": res.reasons, "computed_at": now.isoformat()}
            ))
            scored += 1
        except Exception:
            errors += 1
    sw.lap("scoring_loop")

    # Write throughput against throwaway keys, so the real cache stays empty and
    # the ranking blend is not switched on by a diagnostic.
    scratch_ms = None
    scratch_used = 0
    if scratch_n > 0:
        avg = int(payload_bytes / scored) if scored else 200
        blob = "x" * max(avg, 1)
        scratch_used = min(scratch_n, scored or scratch_n)
        t0 = time.monotonic()
        pipe = r.pipeline(transaction=False)
        for i in range(scratch_used):
            pipe.setex(f"{SCRATCH_PREFIX}{i}", 60, blob)
        pipe.execute()
        scratch_ms = round((time.monotonic() - t0) * 1000.0, 1)
        try:
            dp = r.pipeline(transaction=False)
            for i in range(scratch_used):
                dp.delete(f"{SCRATCH_PREFIX}{i}")
            dp.execute()
        except Exception:
            pass
    sw.lap("scratch_write_probe")

    out = sw.as_dict()
    out.update({
        "measured_at": now.isoformat(),
        "markets": len(markets),
        "outcome_rows": outcome_rows,
        "canonical_keys": len(canonical_keys),
        "scored": scored,
        "errors": errors,
        "avg_payload_bytes": round(payload_bytes / scored, 1) if scored else None,
        "est_total_payload_mb": round(payload_bytes / 1048576.0, 2),
        "tmdb_cache_hit": tmdb_cached,
        "music_cache_hit": music_cached,
        "scratch_keys_written": scratch_used,
        "scratch_write_ms": scratch_ms,
        "est_full_write_ms": (
            round(scratch_ms * (scored / scratch_used), 1)
            if scratch_ms and scratch_used else None
        ),
        "hard_task_time_limit_s": 300,
        "dyno_size_env": os.environ.get("DYNO", "?"),
        "final_rss_mb": rss_mb(),
    })
    # The whole point: does the real pass fit inside the hard limit?
    real_ms = out["total_ms"] - (scratch_ms or 0.0)
    out["pass_ms_excluding_probe"] = round(real_ms, 1)
    out["fits_in_300s"] = real_ms + (out["est_full_write_ms"] or 0) < 300_000

    out["state"] = "complete"
    out["complete"] = True
    try:
        r.setex(RESULT_KEY, 86400, json.dumps(out))
        out["_persisted_to"] = RESULT_KEY
    except Exception as exc:  # pragma: no cover - diagnostic path
        out["_persist_error"] = str(exc)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", type=int, default=5000,
                    help="throwaway keys used to measure write throughput (0 to skip)")
    args = ap.parse_args()

    if not os.environ.get("DATABASE_URL"):
        sys.exit("DATABASE_URL is unset — this must run on a Heroku dyno.")

    try:
        out = asyncio.run(profile(args.scratch))
    except BaseException as exc:
        # A raised exception is recoverable evidence; persist it, because
        # `heroku logs` is egress-blocked from an agent sandbox and stdout from
        # a detached one-off is unreadable there. Only a SIGKILL escapes this,
        # and the per-stage checkpoints cover that case.
        import traceback
        try:
            from app.tasks.redis_state import get_redis_client
            get_redis_client().setex(RESULT_KEY, 86400, json.dumps({
                "state": "raised", "complete": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()[-4000:],
            }))
        except Exception:
            pass
        raise

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
