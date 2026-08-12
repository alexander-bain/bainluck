"""Precompute market interestingness scores and cache in Redis.

Runs every 2h on the background queue. Queries all feed-eligible FuturesMarket
rows, computes interestingness via the pure scorer in
``utils/market_interestingness.py``, and stores results in a Redis hash so
``GET /api/feed`` can read them without any DB or LLM calls on the hot path.

Redis key: ``interestingness:{market_id}`` → JSON with score, reasons,
computed_at. TTL 6h so stale scores expire if the task stops running.

WHY THIS IS CHUNKED (LAT-P042, #1716) — IT WAS AN OOM, NOT A TIMEOUT
--------------------------------------------------------------------
This task was hard-killed on EVERY run for months. Production 2026-08-12:
``starts_24h: 6``, ``hard_kills_24h: 6``, zero successes, zero failures, zero
incompletes, ``recent_durations_ms: []``, ``health: critical``. Because nothing
ever reached an end handler, the cache was not stale — it was **EMPTY**: a
full-keyspace Redis census (16,602 of 16,613 keys) found ZERO
``interestingness:*`` keys, so the 20%-weight Discover ranking blend that reads
them had been contributing nothing at all.

The standing diagnosis blamed celery's hard ``task_time_limit=300``, and the
prescribed fix was a ``soft_time_limit`` so the kill became catchable. **That
fix would never have fired.** Measured on a one-off dyno with room to finish,
the whole pass is **15.4s** — 20x inside the limit:

    market_query_execute  13,113 ms   <- dominant
    source_count_query       599 ms
    scoring_loop           1,394 ms
    est. full Redis write    849 ms (extrapolated from a 5,000-key probe)

What it actually exceeds is MEMORY. The same pass re-run on a Standard-1X
one-off — the same 512 MB size as ``worker-background`` — checkpointed
**peak RSS 515.0 MB** while still inside ``market_query_execute``, and took
over 4 minutes to reach the point the larger dyno reached in 13 seconds,
because it was swapping. Baseline RSS with the app merely imported is already
**149 MB**, and the worker runs ``--concurrency=2 --max-memory-per-child=200000``
(~195 MB per child), so a single unbounded pass never had room.

The cause is materialising the entire working set at once: **41,318 markets and
191,360 outcome ORM objects**, every one carrying its ``market_metadata`` JSONB,
built solely to compute two scalars per market and write one small key each.

So the pass is now keyset-chunked by ``id``. Peak memory becomes a function of
``CHUNK_SIZE`` rather than of how many markets exist, the identity map is
expunged between chunks so it cannot accumulate, and each chunk's Redis writes
are flushed as that chunk finishes.

**Verified on the same 512 MB dyno size that could not finish before**: peak RSS
**178.0 MB** against a 144.9 MB baseline, whole pass **17.0s**, 55 chunks,
41,148 markets scored, 0 errors. (Run with cache writes redirected to throwaway
keys, so proving the memory fix did not switch the ranking blend on early.)

Two consequences beyond not dying:

* **Partial progress is durable.** The old code buffered all ~41K ``setex``
  calls into one pipeline executed on the LAST line, so a kill at 99% wrote
  NOTHING. That is why an empty cache and a never-run task looked identical.
* **The longest single uninterrupted op is bounded** — one chunk, not one
  whole pass (memory ``project_budget_guard_inner_op``: a guard checked between
  loop iterations does nothing when one iteration is what overruns).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

#: Markets materialised per chunk. CHOSEN BY MEASUREMENT, not by arithmetic —
#: both candidate sizes were run end-to-end against production data on a
#: Standard-1X one-off, the same 512 MB size as `worker-background`:
#:
#:     CHUNK_SIZE   peak RSS   above baseline   wall    chunks
#:     (unbounded)   515.0 MB      +366 MB      DNF*        1
#:     2000          205.1 MB       +60 MB      37.5s      21
#:     750           178.0 MB       +33 MB      17.0s      55
#:
#:     * did not finish: still inside the single query after 4 minutes, on the
#:       same dyno size where a 2.5 GB dyno completed that query in 13.1s. It
#:       was swapping.
#:
#: 750 wins on BOTH axes, which arithmetic would not have predicted: smaller
#: `selectinload` batches cost less in allocator churn than the extra round
#: trips cost in latency. It also lands under the ~195 MB effective ceiling a
#: background child has (`--max-memory-per-child=200000`, i.e. ~195 MB) with
#: ~17 MB of margin, where 2000 would have exceeded it and forced a recycle
#: after every single run.
#:
#: Note the scaling is NOT linear in markets — ~44 KB/market at 750 vs
#: ~30 KB/market at 2000 — so do not "tune" this by multiplying. Re-measure.
CHUNK_SIZE = 750

#: Cache TTL for a scored market. Unchanged at 6h — deliberately longer than the
#: 2h beat, so one missed run degrades the blend's freshness instead of dropping
#: markets out of it entirely.
SCORE_TTL_S = 21600


async def _precompute_interestingness() -> dict:
    """Score all feed-eligible futures markets and cache in Redis.

    Keyset-chunked by ``id``: see the module docstring for the measurements
    that forced it. The work per market is unchanged; only how much of it is
    resident at once, and when it becomes durable, are different.
    """
    from sqlalchemy import select, func, or_
    from sqlalchemy.orm import load_only, selectinload

    from app.models import FuturesMarket, FuturesOutcome
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    # The scorer and the title-matching helpers moved to `_score_chunk`; this
    # function keeps only the two network fallbacks it still calls itself.
    from app.tasks.enrich_tmdb import _fetch_tmdb_trending, _fetch_music_charts

    now = datetime.now(timezone.utc)
    r = get_redis_client()
    started = time.monotonic()

    # #882 slice 4: load the TMDB-trending title set (cached 12h in Redis so the
    # 2h interestingness run doesn't hammer TMDB). Empty set = feature no-ops.
    trending_titles: set[str] = set()
    try:
        cached = r.get("tmdb:trending_titles")
        if cached:
            trending_titles = set(json.loads(cached))
        else:
            trending_titles = await _fetch_tmdb_trending()
            if trending_titles:
                r.setex("tmdb:trending_titles", 43200, json.dumps(sorted(trending_titles)))
    except Exception:
        logger.warning("TMDB trending load failed — interestingness runs without it", exc_info=True)
        trending_titles = set()

    # #882 slice 3: load the music-charts title set (cached 12h; same pattern).
    charting_titles: set[str] = set()
    try:
        cached_m = r.get("music:charting_titles")
        if cached_m:
            charting_titles = set(json.loads(cached_m))
        else:
            charting_titles = await _fetch_music_charts()
            if charting_titles:
                r.setex("music:charting_titles", 43200, json.dumps(sorted(charting_titles)))
    except Exception:
        logger.warning("Music charts load failed — interestingness runs without it", exc_info=True)
        charting_titles = set()

    # Feed-eligible: open, not event-linked, not past resolution. Held as a
    # list so the chunk query and the canonical-key query cannot drift apart.
    eligible = [
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= now,
        ),
    ]

    scored = 0
    errors = 0
    total_markets = 0
    chunks = 0

    async with get_task_session() as session:
        # The canonical_market_key -> distinct-source-count map, built ONCE.
        # It is small (383 keys in production) and every chunk needs all of it,
        # so chunking it would cost round trips AND change results: a market's
        # source count must not depend on which chunk its siblings landed in.
        #
        # Two queries rather than one because the ORIGINAL semantics must be
        # preserved exactly — the keys come from the ELIGIBLE set, but the
        # counts are taken over ALL markets carrying those keys, at any status.
        # Folding the eligibility filter into the count would silently lower
        # source_count for anything whose siblings have already resolved.
        key_result = await session.execute(
            select(FuturesMarket.canonical_market_key)
            .where(FuturesMarket.canonical_market_key.is_not(None), *eligible)
            .distinct()
        )
        canonical_keys = {row[0] for row in key_result.all()}

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
            source_counts = {
                row.canonical_market_key: row.cnt for row in count_result.all()
            }

        # Keyset pagination on the primary key. Keyset rather than OFFSET
        # because OFFSET re-scans everything it skips, so the last chunk would
        # cost as much as the whole original query it is meant to replace.
        last_id = 0
        while True:
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
                .where(*eligible, FuturesMarket.id > last_id)
                .order_by(FuturesMarket.id)
                .limit(CHUNK_SIZE)
            )
            markets = result.scalars().unique().all()
            if not markets:
                break

            chunks += 1
            total_markets += len(markets)
            last_id = markets[-1].id

            scored_chunk, errors_chunk = _score_chunk(
                markets,
                r=r,
                now=now,
                source_counts=source_counts,
                trending_titles=trending_titles,
                charting_titles=charting_titles,
            )
            scored += scored_chunk
            errors += errors_chunk

            # Drop this chunk's ORM graph before loading the next one, so peak
            # memory is a function of CHUNK_SIZE and not of how many markets
            # exist. Without this the identity map retains every object and the
            # chunking buys nothing at all.
            session.expunge_all()
            del markets

    duration_ms = (time.monotonic() - started) * 1000

    return {
        "status": "ok",
        "scored": scored,
        "errors": errors,
        "total_markets": total_markets,
        "chunks": chunks,
        "duration_ms": round(duration_ms, 1),
    }


def _score_chunk(
    markets,
    *,
    r,
    now,
    source_counts: dict[str, int],
    trending_titles: set[str],
    charting_titles: set[str],
) -> tuple[int, int]:
    """Score one chunk and flush its writes before returning.

    Extracted so the flush cannot drift away from the chunk it belongs to. The
    pre-LAT-P042 code buffered every ``setex`` into a single pipeline executed
    on the function's last line, which meant a process killed at 99% wrote
    nothing — indistinguishable, from the outside, from a task that had never
    run. One pipeline per chunk makes progress durable as it happens.
    """
    from app.utils.market_interestingness import (
        MarketInterestingnessInputs,
        score_market_interestingness,
    )
    from app.tasks.enrich_tmdb import _extract_quoted_title, _normalize_title

    scored = 0
    errors = 0
    pipe = r.pipeline(transaction=False)
    for market in markets:
        try:
            # Gather inputs from DB columns
            leader_prob = None
            max_movement = 0.0
            for outcome in market.outcomes:
                prob = (
                    float(outcome.current_probability)
                    if outcome.current_probability is not None
                    else None
                )
                if prob is not None and (leader_prob is None or prob > leader_prob):
                    leader_prob = prob
                change = (
                    float(outcome.probability_change_24h)
                    if outcome.probability_change_24h is not None
                    else None
                )
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

            # #882 slice 4: entertainment-only TMDB-trending match (bounded boost).
            # Reliable signals: a quoted subject title, OR a trending title (>=5
            # chars) appearing in the normalized market name.
            is_trending = False
            is_charting = False
            if market.llm_sport_category == "entertainment" and (
                trending_titles or charting_titles
            ):
                quoted = _normalize_title(_extract_quoted_title(market.name))
                norm_name = _normalize_title(market.name)
                if trending_titles:
                    if quoted and quoted in trending_titles:
                        is_trending = True
                    else:
                        is_trending = any(
                            len(t) >= 5 and t in norm_name for t in trending_titles
                        )
                if charting_titles:
                    if quoted and quoted in charting_titles:
                        is_charting = True
                    else:
                        is_charting = any(
                            len(t) >= 5 and t in norm_name for t in charting_titles
                        )

            inputs = MarketInterestingnessInputs(
                probability=leader_prob,
                source_count=source_count,
                updated_at=market.updated_at,
                movement_24h=max_movement if max_movement > 0 else None,
                resolution_date=market.resolution_date,
                category=market.llm_sport_category,
                volume_24h=(
                    float(market.volume_24h)
                    if market.volume_24h is not None
                    else None
                ),
                llm_quality=llm_quality,
                trending=is_trending,
                charting=is_charting,
            )
            result = score_market_interestingness(inputs, now=now)

            cache_value = json.dumps(
                {
                    "score": result.score,
                    "reasons": result.reasons,
                    "computed_at": now.isoformat(),
                }
            )
            redis_key = f"interestingness:{market.id}"
            pipe.setex(redis_key, SCORE_TTL_S, cache_value)
            scored += 1
        except Exception:
            errors += 1
            logger.warning(
                "Failed to score interestingness for market %s", market.id, exc_info=True
            )

    pipe.execute()
    return scored, errors
