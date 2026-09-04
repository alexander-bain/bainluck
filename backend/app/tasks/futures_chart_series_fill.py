"""live/059 — fetch the venues' own price history for an outright market and cache it.

The arithmetic lives in `app/utils/futures_chart_series.py` and is pure. This is
the half that talks to Polymarket, to Kalshi, to Postgres and to Redis, and its
whole job is to be BOUNDED and to run OFF the request path.

WHY A CACHE AND NOT A TABLE. The obvious place to put denser history is
`futures_odds_snapshots` — it is already what the chart reads. It is also read by
38 other modules, including the calibration build, the closing-line derivation,
`kalshi_cliff`, the retention collapse and the movers feed. Venue-derived rows in
that table would silently move calibration's opening and closing prices, which is
a blast radius this queue has no business taking on for a chart-granularity ship
(and gotcha #21: calibration resolution data is fragile). So the layered series
is a CACHE — one Redis key per market — and the only reader is the concept
envelope's `history` field. Nothing else in the system can see it.

WHAT IT COSTS. Per outcome, per venue: two calls, three when the market is old
enough for an hourly middle tier to add anything (`futures_chart_series.clob_calls`
/ `candle_calls` decide, and they are pure so the decision is testable). Top ten
outcomes × two venues × three calls = 60 requests for one market, paced. That is
a per-market cost paid on a beat and on demand, never per page view.

THE BOUND THAT MATTERS IS THE ONE ON THE POPULATION, NOT THE ONE ON THE REQUEST.
`event_chart_backfill.is_reader_reachable_sport_key` is the lesson: a sweep that
nominates every market it COULD fix loses a race it cannot win. This one only
ever fills markets a concept page actually renders — the eligible set is
`futures_markets` that some event concept names as its evolution market, which is
tier-1 winner fields, in the low hundreds, not the tens of thousands.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from app.utils.futures_chart_series import (
    CandleCall,
    ClobCall,
    Point,
    blend_venues,
    candle_calls,
    clob_calls,
    compact_by_band,
    layer_tiers,
    normalize_points,
    same_question,
    series_reach_summary,
    ticker_batches,
)

logger = logging.getLogger(__name__)


#: Cache key version. BUMP THIS when the series shape changes — a reader that
#: cannot tell v1 from v2 draws last week's shape from this week's code, and the
#: failure is invisible because both are valid JSON.
CACHE_VERSION = "v1"

#: How long a cached series is KEPT. Long, on purpose: the reader never sees a
#: stale tail, because `event_concept.apply_venue_history` layers the fresh
#: `futures_odds_snapshots` captures on top of whatever the cache holds — the
#: venue history owns the SHAPE of the past, the sampler owns the last mile to
#: now. That separation is what lets one market be re-fetched every few hours
#: instead of every few minutes. A settled market's series cannot change at all.
CACHE_TTL_SECONDS = 36 * 3600
SETTLED_CACHE_TTL_SECONDS = 7 * 24 * 3600

#: How old a cached series may be before a reader's page view asks for a refresh.
#: Under this, the layered captures cover the difference and a refetch would buy
#: nothing a person can see. Over it, the 1-minute tier no longer covers "the
#: last day" and the page that is being READ is the one worth spending on.
STALE_REFRESH_AFTER_SECONDS = 3 * 3600

#: Redis sorted set: market_id → unix time of its last successful fill. This is
#: what makes the beat FAIR. Ordering the sweep by resolution date alone re-warms
#: the same soonest-resolving handful every run and never reaches the rest — the
#: shared-counter starvation of gotcha #34, wearing a different hat.
FILL_RECENCY_KEY = f"futures:chart-series-filled:{CACHE_VERSION}"

#: Outcomes that get a venue-history series. The chart draws at most ten lines
#: ("Full field" excepted, which is a deliberate spaghetti view nobody scrubs)
#: and the leaderboard sparklines want a few more. Past this, each outcome is
#: three requests to draw a line at 0.1%.
TOP_N_OUTCOMES = 12

#: Pause between venue requests. Polymarket's Gamma/CLOB rate limit and Kalshi's
#: both tolerate this comfortably; bursting is what earns a 429 whose back-off
#: costs more than the pacing did (lesson #2174).
REQUEST_PAUSE_SECONDS = 0.25

#: A market whose life we cannot date. 90 days is chosen to be longer than the
#: CLOB hourly retention wall (~31 days) so the hourly tier is still requested,
#: and short enough that it does not claim a reach the venue never returned.
DEFAULT_LIFETIME_HOURS = 90 * 24


def cache_key(market_id: int) -> str:
    return f"futures:chart-series:{CACHE_VERSION}:{market_id}"


def claim_key(market_id: int) -> str:
    return f"futures:chart-series-claim:{CACHE_VERSION}:{market_id}"


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


def read_cached_series(market_id: int, rc: Any = None) -> Optional[dict]:
    """The cached layered series for a market, or None.

    Never raises: a Redis that is down must cost this chart its density, not its
    existence — the caller falls back to the raw `futures_odds_snapshots` path
    and draws the sparse line it drew before this module existed.
    """
    try:
        if rc is None:
            from app.tasks.redis_state import get_redis_client

            rc = get_redis_client()
        if rc is None:
            return None
        raw = rc.get(cache_key(market_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict) or "outcomes" not in payload:
            return None
        return payload
    except Exception as exc:  # noqa: BLE001 — a cache read never breaks a page
        logger.warning("futures chart series: cache read failed for %s: %s",
                       market_id, str(exc)[:160])
        return None


def write_cached_series(market_id: int, payload: dict, *, settled: bool,
                        rc: Any = None) -> bool:
    try:
        if rc is None:
            from app.tasks.redis_state import get_redis_client

            rc = get_redis_client()
        if rc is None:
            return False
        ttl = SETTLED_CACHE_TTL_SECONDS if settled else CACHE_TTL_SECONDS
        rc.setex(cache_key(market_id), ttl, json.dumps(payload, separators=(",", ":")))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("futures chart series: cache write failed for %s: %s",
                       market_id, str(exc)[:160])
        return False


def note_fill(market_id: int, *, now: Optional[datetime] = None) -> None:
    """Record that this market was just filled, for the beat's fairness ordering."""
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client()
        if rc is None:
            return
        stamp = (now or datetime.now(timezone.utc)).timestamp()
        rc.zadd(FILL_RECENCY_KEY, {str(int(market_id)): stamp})
    except Exception:  # noqa: BLE001 — bookkeeping never fails a fill
        pass


def order_by_staleness(market_ids: Sequence[int]) -> list[int]:
    """Re-order candidates least-recently-filled first; never-filled lead.

    Read-only against :data:`FILL_RECENCY_KEY`. A Redis that is down returns the
    input order unchanged — a sweep that is merely unfair still fills markets,
    and refusing to run would be the worse failure.
    """
    ids = [int(m) for m in market_ids]
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client()
        if rc is None:
            return ids
        scores = rc.zmscore(FILL_RECENCY_KEY, [str(m) for m in ids])
    except Exception:  # noqa: BLE001
        return ids
    if not scores or len(scores) != len(ids):
        return ids
    # A market with no score has never been filled and sorts first (-inf).
    pairs = [
        (float(s) if s is not None else float("-inf"), i, market_id)
        for i, (market_id, s) in enumerate(zip(ids, scores))
    ]
    pairs.sort(key=lambda p: (p[0], p[1]))
    return [market_id for _score, _i, market_id in pairs]


def cache_age_seconds(payload: dict, *, now: Optional[datetime] = None) -> Optional[float]:
    """How old a cached payload is, or None when it will not say."""
    built = payload.get("built_at")
    if not built:
        return None
    try:
        stamp = datetime.fromisoformat(str(built))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(0.0, ((now or datetime.now(timezone.utc)) - stamp).total_seconds())


def claim_on_demand_fill(market_id: int, *, ttl_seconds: int = 900) -> bool:
    """Take the right to fill this market, once, for `ttl_seconds`.

    SET NX is the whole mechanism: the concept page notices it has no cached
    series and asks for one, and every OTHER page view of the same market in the
    next fifteen minutes is refused the claim rather than piling sixty venue
    requests onto a market that is already being filled. Same shape as
    `event_chart_backfill.claim_on_demand_fill`, same reason.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client()
        if rc is None:
            return False
        return bool(rc.set(claim_key(market_id), "1", nx=True, ex=ttl_seconds))
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Venue fetch
# ---------------------------------------------------------------------------


async def fetch_clob_tier(
    service: Any, token_id: str, call: ClobCall, *, stats: dict
) -> list[Point]:
    """One `prices-history` call, normalised into points.

    An EMPTY answer is a real answer ("this token holds no series at this
    fidelity") and is recorded as such. A FAILURE is not — `get_prices_history`
    raises rather than returning `[]` precisely so the two can be told apart
    (gotcha #53), and a tier we never managed to fetch must not be reported as a
    tier the venue does not serve.
    """
    from app.services.polymarket_api import PolymarketHistoryUnavailable

    try:
        history = await service.get_prices_history(
            token_id=token_id, interval=call.interval, fidelity=call.fidelity
        )
    except PolymarketHistoryUnavailable as exc:
        stats["fetch_errors"] = stats.get("fetch_errors", 0) + 1
        logger.warning("futures chart series: clob %s/%s failed for %s: %s",
                       call.interval, call.fidelity, token_id[:12], str(exc)[:140])
        return []
    stats["clob_requests"] = stats.get("clob_requests", 0) + 1
    if not history:
        stats["clob_empty"] = stats.get("clob_empty", 0) + 1
        return []
    return normalize_points(
        (_utc(pt.get("t")), pt.get("p")) for pt in history
    )


async def fetch_candle_tier(
    service: Any, tickers: Sequence[str], call: CandleCall, *,
    listed_at: Optional[datetime], now: datetime, stats: dict,
) -> dict[str, list[Point]]:
    """One Kalshi candlestick tier for a WHOLE FIELD, keyed by ticker.

    Batched on purpose: `market_tickers` takes a list, so the twelve outcomes of
    a winner field cost one request per tier rather than twelve. The result is
    keyed by the venue's own `market_ticker` and never by request position — see
    the measured order/length hazard on
    :meth:`KalshiAPIService.get_markets_candlesticks_raw`.

    Prices come from `event_chart_backfill.normalize_candle`, NOT from the
    service's own reduction: that reduction falls back to the ask, and a settled
    loser's book is bid 0.00 / ask 1.00, so it reports the loser at 1.0. A chart
    a person reads cannot use it.

    A window wider than Kalshi's per-request period ceiling is chunked by
    `event_chart_backfill.candle_windows`, which is also where an inverted range
    is refused rather than turned into a backwards fetch that answers with an
    empty 200.
    """
    from app.tasks.event_chart_backfill import candle_windows, normalize_candle

    tickers = [t for t in tickers if t]
    if not tickers:
        return {}

    start = now - call.lookback if call.lookback is not None else (
        listed_at or now - timedelta(hours=DEFAULT_LIFETIME_HOURS)
    )
    windows = candle_windows(
        int(start.timestamp()), int(now.timestamp()),
        period_minutes=call.period_interval,
    )
    if not windows:
        return {}

    collected: dict[str, list[tuple[Optional[datetime], Optional[float]]]] = {}
    for window_start, window_end in windows:
        # THE BATCH BUDGET IS SHARED ACROSS TICKERS — see
        # `futures_chart_series.KALSHI_MAX_CANDLES_PER_REQUEST`. Twelve tickers
        # over a 1,440-minute window at 1-minute is 17,280 candles and a 400;
        # split into groups of six it is three requests that all succeed. The
        # period count is derived from the window actually being asked for, so a
        # coarse tier still batches the whole field in one call.
        periods = max(1, (window_end - window_start) // (call.period_interval * 60))
        for group in ticker_batches(tickers, periods=periods):
            try:
                by_ticker = await service.get_markets_candlesticks_raw(
                    tickers=group,
                    period_interval=call.period_interval,
                    start_ts=window_start,
                    end_ts=window_end,
                )
            except Exception as exc:  # noqa: BLE001 — one group, not the tier
                stats["window_errors"] = stats.get("window_errors", 0) + 1
                logger.warning("futures chart series: candle window failed for %s: %s",
                               group[0], str(exc)[:140])
                continue
            stats["candle_requests"] = stats.get("candle_requests", 0) + 1
            for ticker, candles in (by_ticker or {}).items():
                bucket = collected.setdefault(ticker, [])
                for candle in candles or []:
                    bucket.append(
                        (_utc(candle.get("end_period_ts")), normalize_candle(candle))
                    )
            await asyncio.sleep(REQUEST_PAUSE_SECONDS)

    return {ticker: normalize_points(pts) for ticker, pts in collected.items()}


def _utc(unix_ts: Any) -> Optional[datetime]:
    if unix_ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(unix_ts), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


async def polymarket_outcome_series(
    service: Any, market: Any, outcome: Any, *, lifetime_hours: float, stats: dict
) -> list[Point]:
    """The layered Polymarket series for one outcome — finest tier wins."""
    from app.tasks.event_chart_backfill import _polymarket_token_id

    token_id = await _polymarket_token_id(service, market, outcome)
    if not token_id:
        stats["no_token_id"] = stats.get("no_token_id", 0) + 1
        return []
    tiers: list[list[Point]] = []
    for call in clob_calls(lifetime_hours):
        tiers.append(await fetch_clob_tier(service, token_id, call, stats=stats))
        await asyncio.sleep(REQUEST_PAUSE_SECONDS)
    return layer_tiers(tiers)


async def kalshi_field_series(
    service: Any, outcomes: Sequence[Any], *, listed_at: Optional[datetime],
    now: datetime, lifetime_hours: float, stats: dict,
) -> dict[str, list[Point]]:
    """The layered Kalshi series for a whole field, keyed by TICKER.

    Every tier is one batched request for the whole field, then each ticker's
    tiers are layered independently — finest first. Layering per ticker rather
    than per tier is what keeps one outcome's missing minute tier from pulling
    the whole field down to hourly.
    """
    tickers = [
        t for t in (getattr(o, "external_id", None) for o in outcomes) if t
    ]
    if not tickers:
        stats["no_ticker"] = stats.get("no_ticker", 0) + 1
        return {}

    tiers_by_ticker: dict[str, list[list[Point]]] = {t: [] for t in tickers}
    for call in candle_calls(lifetime_hours):
        tier = await fetch_candle_tier(
            service, tickers, call, listed_at=listed_at, now=now, stats=stats
        )
        for ticker in tickers:
            tiers_by_ticker[ticker].append(tier.get(ticker, []))

    return {
        ticker: layer_tiers(tiers)
        for ticker, tiers in tiers_by_ticker.items()
    }


# ---------------------------------------------------------------------------
# Legs: which markets speak for this question
# ---------------------------------------------------------------------------


#: How much of the smaller field two markets must share before one can speak for
#: the other. Only ever applied INSIDE the identity fence — on its own it is the
#: score that chose Cincinnati for the US Open at 0.879 (CERT-881).
MIN_ROSTER_OVERLAP = 0.6

#: A fenced-out candidate is worth naming in `stats`, but only a few: a category
#: holds hundreds of rows this market will never pair with, and a diagnostic that
#: is longer than the payload is a diagnostic nobody reads.
MAX_REFUSALS_LOGGED = 5


def _norm(name: Optional[str]) -> str:
    from app.utils.event_concept import _norm_player_name

    return _norm_player_name(name or "")


async def find_venue_legs(session, market, *, stats: Optional[dict] = None) -> list:
    """Every market that prices the SAME question, one per venue.

    The evolution market is one venue's answer to a question both venues price —
    the US Open men's title is `KXATP-26USO` on Kalshi and event 139236 on
    Polymarket, two `futures_markets` rows with no shared id.

    TWO TESTS, IN THIS ORDER, AND THE ORDER IS THE WHOLE FIX:

      1. **WHICH QUESTION** — `futures_chart_series.same_question()` on the two
         market NAMES. A candidate that asks a different question is not a
         candidate, however its roster reads.
      2. **WHOSE ROSTER** — outcome-name overlap, ranked, inside that fence.
         This is what survives a venue renaming its market, and it is the right
         tie-breaker between two rows that already agree on the question.

    🔴 **STEP 1 IS NOT A REFINEMENT OF STEP 2 (CERT-881).** Overlap alone chose
    Polymarket's Cincinnati Open (29 of the Kalshi field's 33 names, 0.879) over
    the real US Open (18 of 23, 0.783) for Kalshi's `KXATP-26USO`, and
    `blend_venues()` then averaged Cincinnati's prices into the US Open chart.
    One tour draws from one pool of players, so roster overlap is HIGHEST
    between sibling tournaments — the score is most confident exactly where it
    is most wrong. `same_question()` carries the measured population and the
    other five wrong pairs this fence removes.

    Deliberately NOT `cross_source_matching.find_cross_source_markets`: that
    pairs BINARY questions by normalised question text and ranks by price delta,
    which is the right tool for "will X happen" and the wrong one for a 33-way
    field whose name differs by more than its outcomes do.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import FuturesMarket

    own_names = {
        _norm(o.name) for o in (market.outcomes or []) if o.name
    }
    own_names.discard("")
    if len(own_names) < 4:
        return [market]

    rows = (
        await session.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.id != market.id,
                FuturesMarket.market_tier == market.market_tier,
                FuturesMarket.llm_sport_category == market.llm_sport_category,
                FuturesMarket.source != market.source,
                FuturesMarket.status == "open",
            )
            .limit(400)
        )
    ).scalars().all()

    legs = [market]
    seen_sources = {market.source}
    best_by_source: dict[str, tuple[float, Any]] = {}
    refused: list[dict] = []
    for candidate in rows:
        names = {_norm(o.name) for o in (candidate.outcomes or []) if o.name}
        names.discard("")
        if len(names) < 4:
            continue
        overlap = len(own_names & names) / float(min(len(own_names), len(names)))
        # THE FENCE IS DECISIVE AND IT IS FIRST: `overlap` below this line can
        # only RANK candidates that already asked the same question, and the
        # refusal branch reads the score without ever acting on it — a fenced-out
        # candidate is out at any score. It is recorded only when the score would
        # have made it a leg, because those are the rows an operator needs to see
        # and the other two hundred in the category are noise.
        if not same_question(
            market.name, candidate.name,
            category=getattr(market, "llm_sport_category", None),
        ):
            if overlap >= MIN_ROSTER_OVERLAP and len(refused) < MAX_REFUSALS_LOGGED:
                refused.append({
                    "id": candidate.id, "name": candidate.name,
                    "overlap": round(overlap, 4),
                })
            continue
        if overlap < MIN_ROSTER_OVERLAP:
            continue
        prior = best_by_source.get(candidate.source)
        if prior is None or overlap > prior[0]:
            best_by_source[candidate.source] = (overlap, candidate)

    for source, (_overlap, candidate) in best_by_source.items():
        if source in seen_sources:
            continue
        legs.append(candidate)
        seen_sources.add(source)
    if stats is not None and refused:
        stats["identity_refused"] = refused
    return legs


# ---------------------------------------------------------------------------
# Our own captures — the tier of last resort
# ---------------------------------------------------------------------------


async def capture_series_by_name(session, market_ids: Sequence[int]) -> dict[str, list[Point]]:
    """Our `futures_odds_snapshots` readings, keyed by normalised outcome name.

    These are the tier of LAST resort in the layering, and that is a demotion,
    not a dismissal: they are the only source that survives a venue purge, and
    for a market older than the CLOB retention wall they may be the only thing
    that reaches the middle of its life.

    Readings from different bookmakers at the same instant are averaged, which
    is what `attach_competitor_history` already does — this is that reduction,
    moved next to the layering so both halves of the series agree on what one
    point means.
    """
    from sqlalchemy import select

    from app.models.models import FuturesOddsSnapshot, FuturesOutcome

    if not market_ids:
        return {}

    rows = (
        await session.execute(
            select(
                FuturesOutcome.name,
                FuturesOddsSnapshot.captured_at,
                FuturesOddsSnapshot.probability,
            )
            .join(FuturesOutcome, FuturesOutcome.id == FuturesOddsSnapshot.outcome_id)
            .where(FuturesOutcome.market_id.in_(list(market_ids)))
            .order_by(FuturesOutcome.name, FuturesOddsSnapshot.captured_at)
        )
    ).all()

    buckets: dict[str, dict[datetime, list[float]]] = {}
    for name, captured_at, probability in rows:
        if probability is None or captured_at is None:
            continue
        key = _norm(name)
        if not key:
            continue
        buckets.setdefault(key, {}).setdefault(captured_at, []).append(float(probability))

    return {
        key: normalize_points(
            (ts, sum(vals) / len(vals)) for ts, vals in sorted(per_ts.items())
        )
        for key, per_ts in buckets.items()
    }


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------


def _lifetime_hours(market, now: datetime) -> float:
    stamp = getattr(market, "created_at", None)
    if stamp is None:
        return DEFAULT_LIFETIME_HOURS
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(1.0, (now - stamp).total_seconds() / 3600.0)


def _top_outcomes(market, limit: int) -> list:
    from app.utils.outcome_display import is_field_outcome

    real = [
        o for o in (market.outcomes or [])
        if o.name and not is_field_outcome(o.name)
    ]
    real.sort(key=lambda o: float(o.current_probability or 0), reverse=True)
    return real[:limit]


async def build_market_series(
    session,
    market,
    *,
    kalshi_service: Any = None,
    polymarket_service: Any = None,
    top_n: int = TOP_N_OUTCOMES,
    now: Optional[datetime] = None,
) -> dict:
    """The layered, blended, compacted series for one outright market.

    Returns the cache payload: `{"market_id", "built_at", "outcomes": {norm_name:
    [[iso_ts, prob], …]}, "stats": {…}}`. Never raises for one bad venue or one
    bad outcome — a Polymarket outage must cost Polymarket's tiers and nothing
    else (gotcha #42).
    """
    now = now or datetime.now(timezone.utc)
    stats: dict = {"legs": [], "outcomes_built": 0, "outcomes_empty": 0}
    owned: list[Any] = []

    try:
        legs = await find_venue_legs(session, market, stats=stats)
        stats["legs"] = [{"id": m.id, "source": m.source} for m in legs]

        captures = await capture_series_by_name(session, [m.id for m in legs])

        # Every outcome the chart could draw, keyed by normalised name, from
        # whichever leg names it. The evolution market leads so its field
        # ordering (which is what the leaderboard shows) decides the top-N: a
        # name only the sibling leg carries is not on this chart.
        chart_field = {
            _norm(o.name): o for o in _top_outcomes(legs[0], top_n) if _norm(o.name)
        }
        per_leg: dict[int, dict[str, Any]] = {}
        for leg in legs:
            per_leg[leg.id] = {
                key: o
                for key, o in (
                    (_norm(o.name), o) for o in (leg.outcomes or []) if o.name
                )
                if key in chart_field
            }

        # Venue fetch, ONE LEG AT A TIME so a venue's batch stays a batch.
        venue_points: dict[str, dict[str, list[Point]]] = {}
        for leg in legs:
            wanted_outcomes = per_leg.get(leg.id) or {}
            if not wanted_outcomes:
                continue
            lifetime = _lifetime_hours(leg, now)
            try:
                if leg.source == "kalshi":
                    if kalshi_service is None:
                        from app.services.kalshi_api import KalshiAPIService

                        kalshi_service = KalshiAPIService()
                        owned.append(kalshi_service)
                    by_ticker = await kalshi_field_series(
                        kalshi_service, list(wanted_outcomes.values()),
                        listed_at=getattr(leg, "created_at", None),
                        now=now, lifetime_hours=lifetime, stats=stats,
                    )
                    venue_points[leg.source] = {
                        key: by_ticker.get(getattr(o, "external_id", "") or "", [])
                        for key, o in wanted_outcomes.items()
                    }
                elif leg.source == "polymarket":
                    if polymarket_service is None:
                        from app.services.polymarket_api import PolymarketAPIService

                        polymarket_service = PolymarketAPIService()
                        owned.append(polymarket_service)
                    per_name: dict[str, list[Point]] = {}
                    for key, outcome in wanted_outcomes.items():
                        try:
                            per_name[key] = await polymarket_outcome_series(
                                polymarket_service, leg, outcome,
                                lifetime_hours=lifetime, stats=stats,
                            )
                        except Exception as exc:  # noqa: BLE001 — one outcome
                            stats.setdefault("errors", []).append(
                                f"polymarket/{key}: {type(exc).__name__}: {str(exc)[:100]}"
                            )
                    venue_points[leg.source] = per_name
                else:
                    # odds_api and friends publish no history endpoint; their
                    # contribution is already in `captures`.
                    continue
            except Exception as exc:  # noqa: BLE001 — one venue, not the chart
                stats.setdefault("errors", []).append(
                    f"{leg.source}: {type(exc).__name__}: {str(exc)[:120]}"
                )

        series: dict[str, list[list]] = {}
        for key in chart_field:
            by_venue = {
                source: pts
                for source, per_name in venue_points.items()
                if (pts := per_name.get(key))
            }
            blended = blend_venues(by_venue)
            # Our own captures are the LAST tier: they fill only where no venue
            # spoke — before a venue listed, after a venue purged, or across an
            # outage in the middle.
            layered = layer_tiers([blended, captures.get(key, [])])
            final = compact_by_band(layered, now)
            if len(final) < 2:
                stats["outcomes_empty"] += 1
                continue
            series[key] = [[ts.isoformat(), round(p, 6)] for ts, p in final]
            stats["outcomes_built"] += 1

        payload = {
            "market_id": market.id,
            "built_at": now.isoformat(),
            "outcomes": series,
            # 🔴 The chart drops any competitor without an `outcome_id` —
            # `competitorsToOutcomeHistory` refuses a line it cannot key
            # (`frontend/lib/eventConceptDisplay.ts`). A competitor whose venue
            # series matched by name but whose SAMPLED series did not would
            # therefore vanish from a chart it had just been given 400 points
            # for. The evolution market's own outcome ids travel with the series
            # so the read path can supply one.
            "outcome_ids": {
                key: outcome.id for key, outcome in chart_field.items()
                if key in series
            },
            "stats": stats,
        }
        return payload
    finally:
        for service in owned:
            try:
                await service.close()
            except Exception:  # noqa: BLE001 — closing never masks the run
                pass


async def fill_market_series(
    session, market_id: int, *, dry_run: bool = False,
    kalshi_service: Any = None, polymarket_service: Any = None,
) -> dict:
    """Build and cache one market's series. The unit the beat and /admin call."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import FuturesMarket

    market = (
        await session.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(FuturesMarket.id == market_id)
        )
    ).scalar_one_or_none()
    if market is None:
        return {"market_id": market_id, "status": "not_found"}

    payload = await build_market_series(
        session, market,
        kalshi_service=kalshi_service, polymarket_service=polymarket_service,
    )
    settled = (market.status or "").lower() in {"settled", "closed", "resolved"}
    written = False
    if not dry_run:
        written = write_cached_series(market_id, payload, settled=settled)
        if written:
            note_fill(market_id)
    return {
        "market_id": market_id,
        "status": "built" if payload["stats"]["outcomes_built"] else "empty",
        "outcomes_built": payload["stats"]["outcomes_built"],
        "outcomes_empty": payload["stats"]["outcomes_empty"],
        "legs": payload["stats"]["legs"],
        "cached": written,
        "reach": {
            key: series_reach_summary(
                [(datetime.fromisoformat(t), p) for t, p in pts],
                datetime.now(timezone.utc),
            )
            for key, pts in list(payload["outcomes"].items())[:3]
        },
    }


#: How far ahead a race has to resolve before the beat stops warming it. A title
#: that settles in March is a race nobody scrubs today, and the venue's minute
#: data for it will still be there in February. The wall is what keeps the beat
#: off a population it cannot traverse.
WARM_HORIZON_DAYS = 30

#: How far PAST resolution a market stays warm. A slam's chart is read hardest in
#: the two days after the final, and by then `status` may still say open
#: (gotcha: Kalshi settled markets stay `status='open'` in our rows).
WARM_TRAILING_DAYS = 2


async def eligible_market_ids(session, *, limit: int, now: Optional[datetime] = None) -> list[int]:
    """The outright markets a concept page can actually draw, SOONEST FIRST.

    🔴 **THE POPULATION IS THE BOUND, NOT THE REQUEST.** Measured 2026-09-04:
    tier-1 open Kalshi/Polymarket fields with ≥4 outcomes number **1,113**. At
    ~39 requests per market that is a 43,000-request traversal, which is the
    exact shape `event_chart_backfill.is_reader_reachable_sport_key` exists
    because of — a sweep that loses ground every night and that no budget fixes.

    Narrowed to races resolving inside :data:`WARM_HORIZON_DAYS` (and up to
    :data:`WARM_TRAILING_DAYS` past), the same measurement returns **107**, from
    2026-09-06 to 2026-10-04. At limit 15 every four hours that is 90 markets a
    day against a population of 107 — a set that fits inside the cadence, which
    is the only kind of sweep worth running. Anything outside it fills on demand
    the moment a reader opens its page.

    Ordered by resolution date so the race that settles first is warmed first.
    """
    from sqlalchemy import func, select

    from app.models.models import FuturesMarket, FuturesOutcome

    now = now or datetime.now(timezone.utc)
    rows = (
        await session.execute(
            select(FuturesMarket.id)
            .join(FuturesOutcome, FuturesOutcome.market_id == FuturesMarket.id)
            .where(
                FuturesMarket.market_tier == 1,
                FuturesMarket.status == "open",
                FuturesMarket.source.in_(("kalshi", "polymarket")),
                FuturesMarket.resolution_date.is_not(None),
                FuturesMarket.resolution_date
                >= now - timedelta(days=WARM_TRAILING_DAYS),
                FuturesMarket.resolution_date
                <= now + timedelta(days=WARM_HORIZON_DAYS),
            )
            .group_by(FuturesMarket.id, FuturesMarket.resolution_date)
            .having(func.count(FuturesOutcome.id) >= 4)
            .order_by(FuturesMarket.resolution_date.asc())
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def run_futures_chart_series_fill(
    market_ids: Optional[Sequence[int]] = None,
    *,
    limit: int = 25,
    dry_run: bool = False,
) -> dict:
    """Targeted fill for the named markets, or the eligible outright population."""
    from app.tasks.base import get_task_session

    ids = list(market_ids or [])
    async with get_task_session() as session:
        if not ids:
            # Take a candidate pool WIDER than the run's budget, then let
            # staleness pick from it — that pair is the rotation. A pool sized
            # to the budget would hand back the same soonest-resolving markets
            # every run no matter how the pool is ordered.
            pool = await eligible_market_ids(session, limit=limit * 8)
            ids = order_by_staleness(pool)
        results = []
        for market_id in ids[:limit]:
            try:
                results.append(
                    await fill_market_series(session, market_id, dry_run=dry_run)
                )
            except Exception as exc:  # noqa: BLE001 — one market, not the sweep
                logger.warning("futures chart series: fill failed for %s: %s",
                               market_id, str(exc)[:200])
                results.append({
                    "market_id": market_id, "status": "error",
                    "error": f"{type(exc).__name__}: {str(exc)[:160]}",
                })
    built = sum(1 for r in results if r.get("status") == "built")
    return {
        "markets_attempted": len(results),
        "markets_built": built,
        "selection": "explicit" if market_ids else "eligible",
        "dry_run": dry_run,
        "results": results,
    }
