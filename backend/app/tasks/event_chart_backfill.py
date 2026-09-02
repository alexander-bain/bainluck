"""live/035 — a finished match page draws its WHOLE life, not the one point we saw.

THE SPECIMEN. `/events/15300759` (Vallejo v Monfils, US Open) rendered a single
dot. Measured on production 2026-09-02:

    events.id 15300759          created_at  2026-09-01 22:05 UTC
    futures_markets 59693708    created_at  2026-08-28 18:49 UTC   (resolved)
    futures_outcomes            53 price snapshots, 2026-08-28 → 2026-09-02
    win_prob_snapshots          **1 row**, captured 2026-09-02 02:59 UTC

The event row is *younger than the match it describes*. Kalshi listed the market
on 08-27, we minted the market on 08-28, the match played on 09-01 — and the
`events` row that the chart hangs off did not exist until 09-01 22:05, three
hours before first serve and four days after the price started moving. Every
win-prob writer in this codebase is a sampler: it records what it happens to see
while it is looking. None of them can record what happened before the row
existed.

That is not a cadence bug and no amount of live-cadence work fixes it. For
prediction-market-native events — tennis, combat, anything with no sportsbook
and therefore no odds-driven event creation — the event is routinely born after
the story is over. The only place the missing history still exists is the venue,
and both venues publish it:

    Kalshi      GET /markets/candlesticks?market_tickers=…   (per market ticker)
    Polymarket  GET /prices-history?market={clob_token_id}   (per CLOB token)

Measured for the specimen's own ticker on 2026-09-02: **2,081 one-minute
candles from 0.495 to 1.0**, spanning 2026-08-27T17:17 to 2026-09-02T01:43 —
five days of pre-match drift and the in-match swing to settlement, all of it
recoverable, none of it ours. This module makes it ours.

ORIENTATION IS BORROWED, NEVER RE-DERIVED. A backfilled curve that is flipped is
worse than no curve: it is a confident lie about who was winning. So the home/away
decision comes from `app/utils/live_blend.py` — `select_primary_market` →
`extract_matchup_with_ticker_fallback` → `find_moneyline_outcome` — the exact
chain the 120s live poll and the WS fast lane use. If those three would decline
to write a point for this market, so does this. The one concession is
:class:`_ClampedOutcome`, below, and it changes only which outcome is SELECTED.

WHAT IT WRITES. `win_prob_snapshots` rows, the table `/api/events/{id}/history`
reads into `win_prob_history` and the chart draws. `game_state` carries market
provenance and `poll_type: "history_backfill"` — and deliberately carries NO
`period`/`inning`/`clock` key, so the #1828 cross-game state filter
(`app/utils/game_window.py`) never has cause to touch these rows. That filter is
keyed on in-game state, and a candlestick asserts a price, not an inning.

IDEMPOTENT BY MINUTE, NOT BY CONSTRAINT. `win_prob_snapshots` has no unique index
on (event_id, source, captured_at) and adding one means a non-CONCURRENT unique
build over a very large table inside an Alembic release — gotcha #31, the shape
that took the site down in May. Instead the existing minute-truncated timestamps
for (event, source) are read once up front and used as a skip set. Candle
timestamps are period-aligned and therefore stable across runs, so re-running is
a no-op; live-written points are never overwritten, only skipped around.

COMPRESSION, AND WHY IT IS NOT LOSSY WHERE IT MATTERS. 2,081 points per source
per event does not survive as a nightly sweep policy. :func:`compress_series`
keeps **every value change** plus a heartbeat on flat stretches, which for the
specimen is 266 changes + heartbeats ≈ 600 points: full resolution exactly where
the line moves, and a breathing line where it does not. A chart is ~1,000px
wide; the discarded points were never going to be pixels.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, NamedTuple, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — every one of these is a decision, not a default
# ---------------------------------------------------------------------------

#: Kalshi's candlestick endpoint 400s when a request spans too many periods. A
#: 7-day window at ``period_interval=1`` (10,080 periods) is refused; 10,000 is
#: served. Measured 2026-09-02 against ``KXATPMATCH-26AUG30VALMON-MON``. Chunked
#: at half the observed ceiling so the next tightening upstream does not turn a
#: backfill into a silent zero.
KALSHI_MAX_PERIODS_PER_REQUEST = 5000

#: Kalshi accepts only these ``period_interval`` values. 5 and 15 are documented
#: nowhere and return junk (4 candles for a window that yields 1,134 at 1-minute,
#: measured 2026-09-02) — an answer shaped like data, which is worse than an
#: error. Never widen this set without re-probing.
KALSHI_PERIOD_INTERVALS = (1, 60, 1440)

#: How many candlestick requests one outcome may cost. At 1-minute granularity
#: this covers ~17 days of market life; past that the fetch drops to hourly
#: rather than paging forever. A market listed months before its event is common
#: (futures), and its pre-match hour-by-hour drift is not worth 40 requests.
MAX_CANDLE_REQUESTS_PER_OUTCOME = 5

#: Target series length after compression. Sized against a ~1,000px chart: more
#: points than this cannot become more pixels, and each one is a row forever.
TARGET_POINTS_PER_SERIES = 600

#: Heartbeat floor/ceiling. The floor is the finest granularity either venue
#: publishes; the ceiling stops a months-long futures market from drawing a line
#: with a joint every six hours.
MIN_HEARTBEAT_SECONDS = 60
MAX_HEARTBEAT_SECONDS = 30 * 60

#: A chart is THIN when it holds fewer than one point per hour of the market's
#: life, capped — so a five-day market needs 120 points to be considered drawn,
#: and a two-hour market needs 2. Below this the nightly sweep offers to fill it.
THIN_POINTS_PER_HOUR = 1.0
THIN_MAX_EXPECTED_POINTS = 120

#: Slack around the market's own open/close when no exact venue timestamps are
#: available, so a clock skew at either end cannot clip the settlement move.
WINDOW_SLACK = timedelta(hours=2)

#: Above this bid/ask gap the mid-price stops meaning anything and the last
#: TRADE is the honest number. Gotcha #19 is the same rule already learned at
#: the other venue ("Polymarket midpoint can be stale in blowouts — wide spread
#: → lastTradePrice"). 10c is far wider than a traded Kalshi match market ever
#: sits and far tighter than the 0.00/1.00 book a settled one leaves behind.
WIDE_SPREAD_DOLLARS = 0.10


@dataclass(frozen=True)
class SeriesPoint:
    """One point of a venue-published price series, already oriented to home."""

    captured_at: datetime
    home_probability: float
    yes_probability: float


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def heartbeat_seconds_for(
    lifetime_seconds: float,
    *,
    target_points: int = TARGET_POINTS_PER_SERIES,
    floor_s: int = MIN_HEARTBEAT_SECONDS,
    cap_s: int = MAX_HEARTBEAT_SECONDS,
) -> int:
    """Spacing at which a FLAT stretch still earns a point.

    Value changes are always kept (see :func:`compress_series`); this only sets
    how often a line that is not moving says so. Scaled by lifetime so a
    two-hour market keeps minute resolution and a two-month one does not try to.
    """
    if lifetime_seconds <= 0 or target_points <= 0:
        return floor_s
    raw = lifetime_seconds / target_points
    return int(max(floor_s, min(cap_s, math.ceil(raw))))


def compress_series(
    points: Sequence[SeriesPoint], heartbeat_seconds: int
) -> list[SeriesPoint]:
    """Keep every move, plus a heartbeat while flat, plus the two endpoints.

    The endpoints matter independently: the first point is the market's opening
    opinion (the "pre-match" end of Alex's acceptance) and the last is where it
    settled. A compressor that could drop either would be trading away the two
    points the chart is actually read for.
    """
    if not points:
        return []

    kept: list[SeriesPoint] = []
    last_value: Optional[float] = None
    last_ts: Optional[datetime] = None

    for index, point in enumerate(points):
        is_first = index == 0
        is_last = index == len(points) - 1
        changed = last_value is None or point.home_probability != last_value
        stale = last_ts is None or (
            point.captured_at - last_ts
        ).total_seconds() >= heartbeat_seconds

        if is_first or is_last or changed or stale:
            # An endpoint that is already the last kept point is not a new point.
            if kept and kept[-1].captured_at == point.captured_at:
                continue
            kept.append(point)
            last_value = point.home_probability
            last_ts = point.captured_at

    return kept


def candle_windows(
    start_ts: int,
    end_ts: int,
    *,
    period_minutes: int,
    max_periods: int = KALSHI_MAX_PERIODS_PER_REQUEST,
) -> list[tuple[int, int]]:
    """Split [start, end) into request-sized windows.

    Returns ``[]`` for an empty or inverted range rather than one degenerate
    window: an inverted range means the caller's open/close timestamps disagree,
    and fetching "backwards" would return an empty 200 that reads as "no data"
    (gotcha #53).
    """
    if end_ts <= start_ts or period_minutes <= 0 or max_periods <= 0:
        return []
    span = max_periods * period_minutes * 60
    windows: list[tuple[int, int]] = []
    cursor = start_ts
    while cursor < end_ts:
        nxt = min(end_ts, cursor + span)
        windows.append((cursor, nxt))
        cursor = nxt
    return windows


def choose_period_interval(
    lifetime_seconds: float,
    *,
    max_requests: int = MAX_CANDLE_REQUESTS_PER_OUTCOME,
    max_periods: int = KALSHI_MAX_PERIODS_PER_REQUEST,
) -> int:
    """Finest Kalshi interval that covers this lifetime inside the request budget.

    Only values in :data:`KALSHI_PERIOD_INTERVALS` are ever returned — the
    unsupported ones do not error, they answer with nonsense.
    """
    budget_periods = max_requests * max_periods
    lifetime_minutes = max(1.0, lifetime_seconds / 60.0)
    for interval in KALSHI_PERIOD_INTERVALS:
        if lifetime_minutes / interval <= budget_periods:
            return interval
    return KALSHI_PERIOD_INTERVALS[-1]


def is_thin_chart(point_count: int, lifetime_seconds: float) -> bool:
    """Whether this many points is too few for a market that lived this long."""
    if lifetime_seconds <= 0:
        return point_count < 2
    hours = lifetime_seconds / 3600.0
    expected = min(THIN_MAX_EXPECTED_POINTS, max(2.0, hours * THIN_POINTS_PER_HOUR))
    return point_count < expected


def _dollars(container: Any, *keys: str) -> Optional[float]:
    """First parseable ``*_dollars`` value among ``keys``, or None.

    Gotcha: Kalshi publishes prices ONLY in the ``*_dollars`` fields; the cents
    spellings are absent on these payloads. Values arrive as strings.
    """
    if not isinstance(container, dict):
        return None
    for key in keys:
        raw = container.get(key)
        if raw is None or raw == "":
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def normalize_candle(candle: dict) -> Optional[float]:
    """One Kalshi candle → the YES price a CHART should draw, or None.

    THE BUG THIS EXISTS FOR. `KalshiAPIService.get_market_candlesticks` reduces
    a candle to ``(bid+ask)/2``, falling back to whichever side is non-zero. At
    settlement a losing market's book is **bid 0.00 / ask 1.00**, so that
    fallback returns the ask — and the LOSER's final chart point reads 1.0.
    Measured 2026-09-02 on ``KXATPMATCH-26AUG30VALMON-VAL``: Vallejo lost, his
    last real trade was 0.01, and the shared normalizer answers 1.0. A curve
    that ends by declaring the loser certain is worse than no curve at all.

    So: the mid is trusted only while the book is tight enough for a mid to
    mean something. Past :data:`WIDE_SPREAD_DOLLARS` the last TRADE wins —
    gotcha #19's rule, already learned at Polymarket, applied at Kalshi. With
    no trade and only one side quoted there is no honest price and this returns
    None rather than inventing one.
    """
    bid = _dollars(candle.get("yes_bid"), "close_dollars")
    ask = _dollars(candle.get("yes_ask"), "close_dollars")
    last = _dollars(
        candle.get("price"), "close_dollars", "mean_dollars", "previous_dollars"
    )

    def _usable(value: Optional[float]) -> bool:
        return value is not None and 0.0 < value < 1.0

    if bid is not None and ask is not None and bid > 0 and ask > 0 and ask >= bid:
        if (ask - bid) <= WIDE_SPREAD_DOLLARS:
            return (bid + ask) / 2.0

    if _usable(last):
        return last

    # A one-sided book with no trade behind it. Trust the quote only when it is
    # a real price rather than the 0.00/1.00 shell a settled market leaves.
    if _usable(bid) and not _usable(ask):
        return bid
    if _usable(ask) and not _usable(bid):
        return ask
    if _usable(bid) and _usable(ask):
        return (bid + ask) / 2.0
    return None


#: How wrong a settled curve's last point must be before we refuse to draw it.
#: Deliberately stark. `FuturesOutcome.is_winner` is a Boolean defaulting to
#: False, so "not marked a winner" is not evidence of losing — this only ever
#: acts on a market with exactly ONE positively-marked winner, and only when the
#: curve ends CONFIDENTLY on the other side. An ambiguous ending is left alone;
#: the check exists to catch an inverted axis, not to grade a price.
WINNER_CONTRADICTION_MARGIN = 0.10


def contradicts_known_winner(
    terminal_home_probability: float, home_won: Optional[bool]
) -> bool:
    """Whether this curve ends by naming the wrong winner.

    A flipped curve is worse than no curve: it is a confident, legible lie about
    who was ahead. Orientation is borrowed from the live writers precisely so
    this cannot happen — and this is the assertion that the borrowing worked,
    checked against the one fact the venue already settled.
    """
    if home_won is None:
        return False
    if home_won:
        return terminal_home_probability < WINNER_CONTRADICTION_MARGIN
    return terminal_home_probability > (1.0 - WINNER_CONTRADICTION_MARGIN)


def home_won_from_outcomes(
    outcomes: Sequence[Any], selected_outcome: Any, yes_is_home: bool
) -> Optional[bool]:
    """Did the home side win, per the venue's own settlement? ``None`` if unknown.

    Requires exactly one outcome positively marked ``is_winner`` — with a Boolean
    defaulting to False, anything less is an absence of information rather than a
    loss (the same trap #195 hit when it graded ungraded props as misses).
    """
    winners = [o for o in outcomes if getattr(o, "is_winner", None) is True]
    if len(winners) != 1:
        return None
    yes_won = getattr(winners[0], "id", None) == getattr(selected_outcome, "id", None)
    return yes_won if yes_is_home else not yes_won


#: The leg suffixes our own outcome ids carry, longest first so a value ending
#: in the shorter one cannot be matched by a prefix of the longer.
LEG_SUFFIXES = ("_yes", "_no")


def strip_leg_suffix(value: str) -> str:
    """``"0xabcde_yes"`` -> ``"0xabcde"``. A SUFFIX strip, not a character strip.

    This used to be ``value.rstrip("_yes").rstrip("_no")``, which is not what it
    reads as: :meth:`str.rstrip` takes a SET OF CHARACTERS, so it eats every
    trailing ``_``, ``y``, ``e``, ``s``, ``n`` and ``o`` it can find. The real
    Polymarket shape ``0xabcde_yes`` came back as ``0xabcd`` — the trailing ``e``
    of the condition id went with the suffix — so the id matched no
    ``conditionId`` on the Gamma event and the outcome silently resolved to no
    token at all. That is a whole Polymarket curve missing, reported as
    ``no_token_id`` rather than as an error (gotcha #53's shape).
    """
    for suffix in LEG_SUFFIXES:
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def minute_key(value: datetime) -> datetime:
    """Truncate to the minute in UTC — the grain idempotency is judged on."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Orientation — borrowed from the live writers, with one settled-market relaxation
# ---------------------------------------------------------------------------


class _ClampedOutcome:
    """An outcome proxy whose price is nudged inside (0, 1).

    ``find_moneyline_outcome`` discards any outcome priced at exactly 0 or 1,
    which is correct for a LIVE read — a 1.0 is a resolved row, not a market
    opinion, and blending it would pin the hero. But this module runs *after*
    settlement by design, where 1.0/0.0 is the normal steady state, and refusing
    to orient there would mean the backfill can never reach the events that need
    it most. The clamp changes only which outcome is SELECTED; the probabilities
    written to the chart come from the candlesticks, never from here.
    """

    __slots__ = ("_wrapped", "current_probability")

    def __init__(self, wrapped: Any, probability: float) -> None:
        self._wrapped = wrapped
        self.current_probability = probability

    def __getattr__(self, item: str) -> Any:
        return getattr(self._wrapped, item)


def _clamped(outcomes: Sequence[Any]) -> list[Any]:
    out: list[Any] = []
    for outcome in outcomes:
        prob = outcome.current_probability
        if prob is None:
            out.append(outcome)
            continue
        value = float(prob)
        if value <= 0.0:
            out.append(_ClampedOutcome(outcome, 0.001))
        elif value >= 1.0:
            out.append(_ClampedOutcome(outcome, 0.999))
        else:
            out.append(outcome)
    return out


def resolve_orientation(
    markets_with_outcomes: Sequence[Any],
    home_team_name: str,
    away_team_name: str,
) -> Optional[tuple[Any, Any, bool]]:
    """(primary market, moneyline outcome, yes_is_home) for one (event, source).

    ``markets_with_outcomes`` is a sequence of
    ``app.utils.live_blend.MarketOutcomes``. Returns ``None`` — never a guess —
    whenever the live writers would also decline: not a game-winner ticker, an
    unparseable matchup, or no outcome that resolves to a team.
    """
    from app.utils.live_blend import (
        is_game_winner_market,
        select_primary_market,
    )
    from app.utils.prediction_market_matching import (
        extract_matchup_with_ticker_fallback,
        find_moneyline_outcome,
    )

    primary = select_primary_market(markets_with_outcomes)
    if primary is None:
        return None

    # Kalshi props/spreads never feed the blend, whatever they are linked to —
    # the same gate `compute_source_home_probability` applies.
    if primary.market.source == "kalshi" and not is_game_winner_market(primary.market):
        return None

    matchup = extract_matchup_with_ticker_fallback(
        primary.market.name, external_id=primary.market.external_id
    )
    if not matchup:
        return None

    ordered = sorted(primary.outcomes, key=lambda o: o.rank or 999)
    if not ordered:
        return None

    result = find_moneyline_outcome(
        ordered, matchup, home_team_name, away_team_name
    )
    if result is None:
        # Settled market: every price is 0 or 1 and the live selector rejects
        # them all. Re-run the SAME selector over clamped copies.
        result = find_moneyline_outcome(
            _clamped(ordered), matchup, home_team_name, away_team_name
        )
    if result is None:
        return None

    outcome, yes_is_home = result
    # Unwrap the proxy so callers get the real ORM row back — they stamp
    # `outcome.external_id` into the candlestick request, and a wrapper that
    # leaked would fetch a ticker nobody has.
    real = getattr(outcome, "_wrapped", outcome)
    return primary.market, real, bool(yes_is_home)


def orient_points(
    raw: Iterable[dict],
    *,
    yes_is_home: bool,
    timestamp_key: str = "t",
    price_key: str = "yes_price",
) -> list[SeriesPoint]:
    """Venue points → home-oriented :class:`SeriesPoint`, sorted, deduped by minute.

    Prices at exactly 0 or 1 are KEPT here (unlike in orientation), because the
    settlement move to certainty is the most-read part of a finished chart.
    Prices outside [0, 1] are dropped as corrupt.
    """
    seen: set[datetime] = set()
    points: list[SeriesPoint] = []
    for item in raw:
        ts = item.get(timestamp_key)
        price = item.get(price_key)
        if ts is None or price is None:
            continue
        try:
            yes = float(price)
            captured = minute_key(datetime.fromtimestamp(float(ts), tz=timezone.utc))
        except (TypeError, ValueError, OSError, OverflowError):
            continue
        if yes < 0.0 or yes > 1.0:
            continue
        if captured in seen:
            continue
        seen.add(captured)
        home = yes if yes_is_home else 1.0 - yes
        points.append(
            SeriesPoint(
                captured_at=captured,
                home_probability=round(home, 4),
                yes_probability=round(yes, 4),
            )
        )
    points.sort(key=lambda p: p.captured_at)
    return points


# ---------------------------------------------------------------------------
# Venue fetchers
# ---------------------------------------------------------------------------


async def fetch_kalshi_series(
    service: Any,
    ticker: str,
    *,
    start: datetime,
    end: datetime,
    stats: dict,
) -> list[dict]:
    """Every candle for one Kalshi market ticker across [start, end], chunked.

    Reads the RAW candles and prices them with :func:`normalize_candle` rather
    than taking the service's reduction, which reports a settled loser at 1.0.

    A window that errors is counted and skipped, not fatal: losing one chunk of
    a five-day curve must not lose the other four.

    An empty result is disambiguated the way gotcha #53 requires — a market
    lookup that returns ``None`` (404, and only 404) means Kalshi purged it, and
    that is recorded as ``purged`` rather than as "no data".
    """
    lifetime = (end - start).total_seconds()
    interval = choose_period_interval(lifetime)
    windows = candle_windows(
        int(start.timestamp()), int(end.timestamp()), period_minutes=interval
    )
    if not windows:
        stats["empty_window"] = stats.get("empty_window", 0) + 1
        return []

    stats["period_interval"] = interval
    collected: list[dict] = []
    for window_start, window_end in windows:
        try:
            candles = await service.get_market_candlesticks_raw(
                ticker=ticker,
                period_interval=interval,
                start_ts=window_start,
                end_ts=window_end,
            )
        except Exception as exc:  # noqa: BLE001 — one window, not the series
            stats["window_errors"] = stats.get("window_errors", 0) + 1
            logger.warning(
                "event chart backfill: candle window %s..%s failed for %s: %s",
                window_start, window_end, ticker, str(exc)[:120],
            )
            continue
        stats["candle_requests"] = stats.get("candle_requests", 0) + 1
        for candle in candles or []:
            ts = candle.get("end_period_ts")
            price = normalize_candle(candle)
            if ts is None or price is None:
                stats["candles_unpriced"] = stats.get("candles_unpriced", 0) + 1
                continue
            collected.append({"t": ts, "yes_price": price})

    if not collected:
        market = await service.get_market(ticker)
        if market is None:
            stats["purged"] = stats.get("purged", 0) + 1
        else:
            stats["api_empty"] = stats.get("api_empty", 0) + 1
    return collected


async def _polymarket_token_id(service: Any, market: Any, outcome: Any) -> Optional[str]:
    """The CLOB token id whose price series IS this outcome's YES price.

    Prefers the ids Q460 now stamps on the market at ingest; falls back to the
    Gamma event payload, which is the only place they existed before that.
    """
    metadata = market.market_metadata or {}
    token_ids = metadata.get("clob_token_ids") or metadata.get("clobTokenIds")
    if token_ids:
        index = 0
        if outcome.rank is not None and 0 <= (outcome.rank - 1) < len(token_ids):
            index = outcome.rank - 1
        if index < len(token_ids):
            return str(token_ids[index])

    event_external = (
        metadata.get("polymarket_event_id")
        or (market.group_id or "").replace("polymarket:", "")
        or market.external_id
    )
    if not event_external:
        return None

    import json as _json

    event_data = await service.get_event_by_id(event_external)
    if not event_data:
        return None
    condition_id = outcome.external_id or ""
    for sub in event_data.get("markets", []):
        cid = sub.get("conditionId")
        if not cid:
            continue
        if cid != condition_id and cid != strip_leg_suffix(condition_id):
            continue
        raw = sub.get("clobTokenIds", "[]")
        try:
            ids = _json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            ids = []
        if ids:
            return str(ids[0])
    return None


async def fetch_polymarket_series(
    service: Any, market: Any, outcome: Any, *, stats: dict
) -> list[dict]:
    """The CLOB price history for one outcome, finest granularity first.

    ``fidelity=1`` is asked for first because a match is hours long and hourly
    points cannot draw it. Polymarket silently returns nothing for some
    token/fidelity pairs, so an empty answer retries hourly before it counts as
    an absence.
    """
    token_id = await _polymarket_token_id(service, market, outcome)
    if not token_id:
        stats["no_token_id"] = stats.get("no_token_id", 0) + 1
        return []

    for fidelity in (1, 60):
        history = await service.get_prices_history(
            token_id=token_id, interval="max", fidelity=fidelity
        )
        stats["clob_requests"] = stats.get("clob_requests", 0) + 1
        if history:
            return [{"t": pt.get("t"), "yes_price": pt.get("p")} for pt in history]
    stats["api_empty"] = stats.get("api_empty", 0) + 1
    return []


# ---------------------------------------------------------------------------
# The rail
# ---------------------------------------------------------------------------


async def _load_groups(session, event_id: int) -> dict[str, list]:
    """Linked prediction markets for one event, grouped by source, with outcomes."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import FuturesMarket
    from app.utils.live_blend import MarketOutcomes

    rows = (
        await session.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.event_id == event_id,
                FuturesMarket.source.in_(("kalshi", "polymarket")),
            )
        )
    ).scalars().all()

    groups: dict[str, list] = {}
    for market in rows:
        groups.setdefault(market.source, []).append(
            MarketOutcomes(market=market, outcomes=list(market.outcomes))
        )
    return groups


async def _existing_minutes(session, event_id: int, source: str) -> set[datetime]:
    from sqlalchemy import select

    from app.models.models import WinProbSnapshot

    rows = (
        await session.execute(
            select(WinProbSnapshot.captured_at).where(
                WinProbSnapshot.event_id == event_id,
                WinProbSnapshot.source == source,
            )
        )
    ).scalars().all()
    return {minute_key(ts) for ts in rows if ts is not None}


async def _kalshi_window(service: Any, market: Any, ticker: str) -> tuple[datetime, datetime]:
    """The market's own listing→settlement window, from Kalshi when it will say.

    Falls back to our own row's timestamps plus slack. The fallback is the
    degraded path on purpose: a window anchored on when WE first saw the market
    starts after the price did, which is the very failure this module exists to
    undo.
    """
    now = datetime.now(timezone.utc)
    start = market.created_at or (now - timedelta(days=30))
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    end = now

    detail = await service.get_market(ticker)
    if detail:
        parsed_open = _parse_iso(detail.get("open_time"))
        parsed_close = _parse_iso(detail.get("close_time"))
        if parsed_open:
            start = parsed_open
        if parsed_close:
            end = parsed_close
    return start - WINDOW_SLACK, min(now, end + WINDOW_SLACK)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


async def backfill_event_chart(
    session,
    event,
    *,
    kalshi_service: Any = None,
    polymarket_service: Any = None,
    dry_run: bool = False,
) -> dict:
    """Draw one event's whole win-prob lifetime from its venues' price history.

    Returns a per-source verdict dict. Never raises for one bad source — a
    Polymarket outage must not cost the Kalshi curve (gotcha #42).
    """
    verdict: dict = {
        "event_id": event.id,
        "sources": {},
        "points_written": 0,
        "errors": [],
    }

    groups = await _load_groups(session, event.id)
    if not groups:
        verdict["status"] = "no_linked_markets"
        return verdict

    # Clients this call built itself, which it therefore has to close. The sweep
    # passes its own long-lived pair and they are not in here — closing a
    # caller's client mid-sweep would poison every event after this one.
    owned: list[Any] = []
    try:
        return await _backfill_sources(
            session, event, groups, verdict,
            kalshi_service=kalshi_service,
            polymarket_service=polymarket_service,
            dry_run=dry_run,
            owned=owned,
        )
    finally:
        for service in owned:
            try:
                await service.close()
            except Exception:  # noqa: BLE001 — closing must never mask the run
                pass


async def _backfill_sources(
    session, event, groups, verdict, *,
    kalshi_service, polymarket_service, dry_run, owned,
) -> dict:
    from app.models.models import WinProbSnapshot

    for source, group in groups.items():
        stats: dict = {"points_fetched": 0, "points_kept": 0, "points_written": 0}
        verdict["sources"][source] = stats
        try:
            oriented = resolve_orientation(
                group, event.home_team_name or "", event.away_team_name or ""
            )
            if oriented is None:
                stats["status"] = "orientation_unresolved"
                continue
            market, outcome, yes_is_home = oriented
            stats["market_id"] = market.id
            stats["outcome_name"] = outcome.name
            stats["yes_is_home"] = yes_is_home

            if source == "kalshi":
                service = kalshi_service
                if service is None:
                    from app.services.kalshi_api import KalshiAPIService

                    service = KalshiAPIService()
                    owned.append(service)
                ticker = outcome.external_id
                if not ticker:
                    stats["status"] = "no_ticker"
                    continue
                start, end = await _kalshi_window(service, market, ticker)
                raw = await fetch_kalshi_series(
                    service, ticker, start=start, end=end, stats=stats
                )
            else:
                service = polymarket_service
                if service is None:
                    from app.services.polymarket_api import PolymarketAPIService

                    service = PolymarketAPIService()
                    owned.append(service)
                raw = await fetch_polymarket_series(
                    service, market, outcome, stats=stats
                )

            points = orient_points(raw, yes_is_home=yes_is_home)
            stats["points_fetched"] = len(points)
            if not points:
                stats.setdefault("status", "no_history")
                continue

            lifetime = (
                points[-1].captured_at - points[0].captured_at
            ).total_seconds()
            kept = compress_series(points, heartbeat_seconds_for(lifetime))
            stats["points_kept"] = len(kept)
            stats["lifetime_hours"] = round(lifetime / 3600.0, 2)
            stats["first"] = points[0].captured_at.isoformat()
            stats["last"] = points[-1].captured_at.isoformat()

            # Refuse to draw a curve that names the wrong winner. Orientation is
            # borrowed from the live writers so this cannot happen; this is the
            # check that the borrowing worked, against the one fact already
            # settled. Nothing is written on a contradiction — a missing chart is
            # a gap, a mirrored one is a lie.
            primary_outcomes = next(
                (
                    entry.outcomes
                    for entry in group
                    if entry.market.id == market.id
                ),
                [],
            )
            home_won = home_won_from_outcomes(
                primary_outcomes, outcome, yes_is_home
            )
            stats["home_won"] = home_won
            if contradicts_known_winner(kept[-1].home_probability, home_won):
                stats["status"] = "orientation_contradicts_winner"
                stats["terminal_home_probability"] = kept[-1].home_probability
                logger.error(
                    "event chart backfill: REFUSED event %s %s — curve ends at "
                    "home=%.3f but home_won=%s (inverted axis?)",
                    event.id, source, kept[-1].home_probability, home_won,
                )
                continue

            already = await _existing_minutes(session, event.id, source)
            fresh = [p for p in kept if p.captured_at not in already]
            stats["points_skipped_existing"] = len(kept) - len(fresh)
            if not fresh:
                stats["status"] = "already_complete"
                continue

            if dry_run:
                stats["status"] = "dry_run"
                stats["points_written"] = 0
                continue

            provenance = (
                "kalshi_candlesticks" if source == "kalshi" else "polymarket_clob"
            )
            for index, point in enumerate(fresh):
                # `valid_until` chains to the next point so the series reads the
                # same way a live-written one does. NOTE: no `period`/`inning`/
                # `clock` key here — see the module docstring on #1828.
                next_ts = (
                    fresh[index + 1].captured_at if index + 1 < len(fresh) else None
                )
                session.add(
                    WinProbSnapshot(
                        event_id=event.id,
                        source=source,
                        captured_at=point.captured_at,
                        home_win_probability=point.home_probability,
                        away_win_probability=round(1.0 - point.home_probability, 4),
                        game_state={
                            "market_name": market.name,
                            "market_id": market.id,
                            "outcome_name": outcome.name,
                            "yes_probability": point.yes_probability,
                            "poll_type": "history_backfill",
                            "backfill_source": provenance,
                        },
                        reading_count=1,
                        valid_until=next_ts,
                    )
                )
            stats["points_written"] = len(fresh)
            stats["status"] = "written"
            verdict["points_written"] += len(fresh)
        except Exception as exc:  # noqa: BLE001 — one source must not cost the other
            stats["status"] = "error"
            verdict["errors"].append(f"{source}: {str(exc)[:160]}")
            logger.warning(
                "event chart backfill: %s failed for event %s",
                source, event.id, exc_info=True,
            )

    verdict.setdefault(
        "status", "written" if verdict["points_written"] else "no_new_points"
    )
    return verdict


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------


#: MEASURED, and it is the second shape. The obvious one — a single GROUP BY
#: with ``LEFT JOIN win_prob_snapshots`` and ``COUNT(DISTINCT w.id)`` — hit
#: ``statement_timeout`` on production 2026-09-02: it counts points for every
#: candidate event before the LIMIT can discard any of them, over a very large
#: table. Bounding the candidate set FIRST and counting only the survivors with a
#: correlated subquery (one index scan per kept row) measured **1.9s for 360
#: candidates** against the same data. A nightly task whose selection query times
#: out is a nightly task that never runs (gotcha #53 — it would return cleanly,
#: having done nothing).
THIN_CHART_CANDIDATES_SQL = """
    WITH candidates AS (
        SELECT
            e.id                                         AS event_id,
            MIN(fm.created_at)                           AS market_first_seen,
            MAX(COALESCE(e.completed_at, fm.updated_at)) AS market_last_seen
        FROM events e
        JOIN futures_markets fm
          ON fm.event_id = e.id
         AND fm.source IN ('kalshi', 'polymarket')
         -- BOTH bounds, per gotcha #41. This floor keeps the sweep off markets
         -- whose upstream history is provably deleted (gotcha #35), and the
         -- ORDER BY below works oldest-first INSIDE that floor so the at-risk
         -- edge is harvested before it expires rather than after. Newest-first
         -- would starve exactly the rows that die.
         AND COALESCE(e.completed_at, fm.updated_at)
             >= NOW() - make_interval(days => :purge_days)
        WHERE e.commence_time IS NOT NULL
          AND e.commence_time <= NOW()
          AND e.commence_time >= NOW() - make_interval(days => :purge_days)
        GROUP BY e.id
        -- The SWEEP CURSOR. Without it the LIMIT below pins the sweep to one
        -- fixed prefix forever: the oldest N are selected, repaired, and then
        -- selected again every night as a set of thick charts that yield
        -- nothing, while every thin chart behind them starves until it expires.
        -- (Measured: 44,315 candidates inside the floor, so the prefix is 0.8%
        -- of the population and the other 99.2% is unreachable.) See
        -- `select_thin_chart_page` for the wrap that closes the ring. (No
        -- Sphinx roles inside SQL. `text()` does not strip comments, so a
        -- colon-prefixed word in one reads as a REQUIRED bind parameter and
        -- every execution raises InvalidRequestError before reaching the
        -- database. There is a repo guard for exactly this, and it caught it
        -- here — a defect no unit test in this file could have seen, because
        -- they all stub the session.)
        HAVING CAST(:after AS timestamptz) IS NULL
            OR MIN(fm.created_at) > CAST(:after AS timestamptz)
        ORDER BY MIN(fm.created_at) ASC
        LIMIT :limit
    )
    SELECT
        c.event_id,
        c.market_first_seen,
        c.market_last_seen,
        (
            SELECT COUNT(*)
            FROM win_prob_snapshots w
            WHERE w.event_id = c.event_id
              AND w.source IN ('kalshi', 'polymarket')
        ) AS point_count
    FROM candidates c
    ORDER BY c.market_first_seen ASC
"""


#: Where the last nightly sweep stopped LOOKING, as an ISO `market_first_seen`.
#: Redis, not a column: the cursor is an optimisation, not a fact about the data,
#: and the 100 MB LRU evicting it costs one wasted re-scan of the oldest page —
#: exactly the behaviour the sweep had before the cursor existed. Never a
#: migration for a hint.
SWEEP_CURSOR_KEY = "event_chart_backfill:sweep_cursor"


class ThinChartPage(NamedTuple):
    """One page of the ring the nightly sweep walks."""

    event_ids: list[int]
    #: `market_first_seen` of the last candidate LOOKED AT (not the last picked)
    #: — everything at or before it has been judged this pass.
    next_cursor: Optional[datetime]
    #: True when the scan reached the end of the population, so the next run
    #: must WRAP rather than advance. A ring with no wrap is a queue that ends.
    exhausted: bool


async def select_thin_chart_page(
    session, *, limit: int, scan_multiple: int = 6, after: Optional[datetime] = None
) -> ThinChartPage:
    """One page of events whose chart holds too few points for their market's life.

    Scans a multiple of ``limit`` candidates STARTING AFTER ``after`` and applies
    :func:`is_thin_chart` in Python, so the thinness rule lives in one tested
    pure function rather than being re-expressed (and drifting) in SQL.

    The cursor is what makes this a sweep rather than a fixed prefix. The scan
    has to be bounded — counting points for all 44,315 candidates inside the
    retention floor is the shape that hit ``statement_timeout`` — but a bound
    with no cursor selects the same oldest page every night, and the night after
    it is repaired that page yields nothing, forever. The cursor advances past
    everything JUDGED, thin or thick, and :data:`ThinChartPage.exhausted` tells
    the caller to wrap.

    Ties on ``MIN(fm.created_at)`` are advanced past with a strict ``>``, so
    progress is guaranteed; a candidate skipped by a tie is picked up on the
    next wrap rather than blocking the ring.
    """
    from sqlalchemy import text

    from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

    scan_size = max(1, limit * max(1, scan_multiple))
    rows = (
        await session.execute(
            text(THIN_CHART_CANDIDATES_SQL),
            {
                "limit": scan_size,
                "purge_days": PROVABLY_PURGED_AGE_DAYS,
                "after": after,
            },
        )
    ).fetchall()

    thin: list[int] = []
    cursor: Optional[datetime] = None
    for row in rows:
        first = row.market_first_seen
        last = row.market_last_seen
        # Advance over every row JUDGED, not only over the ones picked. A thick
        # chart that the cursor did not pass would be re-counted every night.
        if first is not None:
            cursor = first
        lifetime = 0.0
        if first is not None and last is not None and last > first:
            lifetime = (last - first).total_seconds()
        if is_thin_chart(int(row.point_count or 0), lifetime):
            thin.append(int(row.event_id))
        if len(thin) >= limit:
            break
    return ThinChartPage(
        event_ids=thin,
        next_cursor=cursor,
        exhausted=len(rows) < scan_size,
    )


async def select_thin_chart_events(session, *, limit: int, scan_multiple: int = 6) -> list[int]:
    """The ids of :func:`select_thin_chart_page`, from the start of the ring."""
    page = await select_thin_chart_page(
        session, limit=limit, scan_multiple=scan_multiple
    )
    return page.event_ids


def _read_sweep_cursor() -> Optional[datetime]:
    """The stored cursor, or None to start the ring again from the oldest end.

    Every failure mode — no Redis, an evicted key, an unparseable value —
    answers None, which restarts the sweep. Restarting is the pre-cursor
    behaviour: it wastes a scan, it never writes a wrong row.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client().get(SWEEP_CURSOR_KEY)
    except Exception:  # noqa: BLE001 — a hint that cannot be read is no hint
        return None
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "ignore")
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _write_sweep_cursor(cursor: Optional[datetime], *, exhausted: bool) -> None:
    """Persist the cursor, or CLEAR it when the ring has been walked all the way."""
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        if exhausted or cursor is None:
            client.delete(SWEEP_CURSOR_KEY)
        else:
            client.set(SWEEP_CURSOR_KEY, cursor.isoformat())
    except Exception:  # noqa: BLE001 — losing the hint costs a re-scan, not a row
        logger.warning("event chart backfill: sweep cursor not persisted", exc_info=True)


async def _run_for_event_ids(event_ids: Sequence[int], *, dry_run: bool = False) -> dict:
    """Backfill a concrete list of events, committing per event.

    Per-event commits, not one big transaction: a network sweep that dies on
    item 40 must keep the 39 curves it already drew (gotcha #13's shape, applied
    to a backfill rather than to matching).
    """
    from sqlalchemy import select

    from app.models.models import Event
    from app.tasks.base import get_task_session

    summary: dict = {
        "requested": len(event_ids),
        "events_processed": 0,
        "events_written": 0,
        "points_written": 0,
        "no_linked_markets": 0,
        "orientation_unresolved": 0,
        "purged": 0,
        "api_empty": 0,
        "already_complete": 0,
        "errors": [],
        "per_event": [],
    }
    if not event_ids:
        return {**summary, "status": "nothing_to_backfill"}

    kalshi_service = None
    polymarket_service = None
    try:
        from app.services.kalshi_api import KalshiAPIService
        from app.services.polymarket_api import PolymarketAPIService

        kalshi_service = KalshiAPIService()
        polymarket_service = PolymarketAPIService()

        async with get_task_session() as session:
            for event_id in event_ids:
                event = (
                    await session.execute(select(Event).where(Event.id == event_id))
                ).scalar_one_or_none()
                if event is None:
                    summary["errors"].append(f"{event_id}: not_found")
                    continue
                verdict = await backfill_event_chart(
                    session,
                    event,
                    kalshi_service=kalshi_service,
                    polymarket_service=polymarket_service,
                    dry_run=dry_run,
                )
                summary["events_processed"] += 1
                summary["points_written"] += verdict["points_written"]
                if verdict["points_written"]:
                    summary["events_written"] += 1
                if verdict.get("status") == "no_linked_markets":
                    summary["no_linked_markets"] += 1
                for source_stats in verdict["sources"].values():
                    status = source_stats.get("status")
                    if status in ("orientation_unresolved", "already_complete"):
                        summary[status] += 1
                    summary["purged"] += source_stats.get("purged", 0)
                    summary["api_empty"] += source_stats.get("api_empty", 0)
                summary["errors"].extend(verdict["errors"])
                summary["per_event"].append(verdict)

                if not dry_run:
                    await session.commit()
    finally:
        for service in (kalshi_service, polymarket_service):
            if service is not None:
                try:
                    await service.close()
                except Exception:  # noqa: BLE001 — closing must never mask the run
                    pass

    # gotcha #53 / `task_verdict`: "it returned" is not "it worked". A sweep that
    # touched events and wrote nothing says so in the terminal, loudly, instead
    # of reporting the same shape as a sweep that drew forty curves.
    if summary["points_written"]:
        summary["status"] = "complete"
    elif summary["events_processed"]:
        summary["status"] = "no_new_points"
    else:
        summary["status"] = "nothing_to_backfill"
    return summary


async def run_event_chart_backfill(
    event_ids: Optional[Sequence[int]] = None,
    *,
    limit: int = 40,
    dry_run: bool = False,
) -> dict:
    """Targeted backfill: the named events, or the thinnest charts we can still fix."""
    from app.tasks.base import get_task_session

    ids = list(event_ids or [])
    page = None
    if not ids:
        # Walk the ring, do not re-read the head of it. `after` is where the
        # last sweep stopped LOOKING; `exhausted` wraps it back to the oldest
        # end so a chart that turns thin later is still reachable.
        after = _read_sweep_cursor()
        async with get_task_session() as session:
            page = await select_thin_chart_page(session, limit=limit, after=after)
        ids = page.event_ids
    result = await _run_for_event_ids(ids[:limit], dry_run=dry_run)
    result["selection"] = "explicit" if event_ids else "thin_sweep"
    if page is not None:
        result["swept_from"] = after.isoformat() if after else None
        result["swept_to"] = (
            page.next_cursor.isoformat() if page.next_cursor else None
        )
        result["ring_wrapped"] = page.exhausted
        if not dry_run:
            _write_sweep_cursor(page.next_cursor, exhausted=page.exhausted)
    return result

