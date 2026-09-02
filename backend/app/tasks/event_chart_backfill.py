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

#: THE READER WINDOW (live/036, Fable ruling (b)). How far either side of NOW an
#: event is still something a person can arrive at: a card on the slate, a hub
#: row, a Discover placement, a result page still being read. Backwards AND
#: forwards, because a prediction-market-native market prices for days before
#: first serve — the specimen's own curve had five days of drift before the
#: `events` row existed, and that drift is the most interesting part of an
#: UPCOMING match's chart, not only a settled one's.
READER_REACH_LOOKBACK_DAYS = 7
READER_REACH_LOOKAHEAD_DAYS = 7

#: Past this age an event fills at HOURLY granularity instead of 1-minute
#: (Fable ruling (c)). Nobody scrubs a three-week-old chart for the minute the
#: break happened; they look at the shape. Hourly is ~1 request per ticker
#: instead of 2-5 and ~1/60th the candles to normalize, which is what makes an
#: on-demand fill cheap enough to run inside a page view's shadow.
COARSE_GRANULARITY_AGE_DAYS = 7


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
    min_interval: int = 1,
) -> int:
    """Finest Kalshi interval that covers this lifetime inside the request budget.

    Only values in :data:`KALSHI_PERIOD_INTERVALS` are ever returned — the
    unsupported ones do not error, they answer with nonsense.

    ``min_interval`` is a FLOOR from :func:`granularity_floor_minutes`, not a
    choice: it says "do not pay for finer than this", and the budget rule can
    still push COARSER. A floor that is not itself a supported interval is
    rounded UP to one, never silently honoured — asking Kalshi for
    ``period_interval=5`` returns four candles for a window that yields 1,134 at
    1-minute, which is an answer shaped like data.
    """
    budget_periods = max_requests * max_periods
    lifetime_minutes = max(1.0, lifetime_seconds / 60.0)
    allowed = [i for i in KALSHI_PERIOD_INTERVALS if i >= max(1, min_interval)]
    if not allowed:
        allowed = [KALSHI_PERIOD_INTERVALS[-1]]
    for interval in allowed:
        if lifetime_minutes / interval <= budget_periods:
            return interval
    return allowed[-1]


def is_thin_chart(point_count: int, lifetime_seconds: float) -> bool:
    """Whether this many points is too few for a market that lived this long."""
    if lifetime_seconds <= 0:
        return point_count < 2
    hours = lifetime_seconds / 3600.0
    expected = min(THIN_MAX_EXPECTED_POINTS, max(2.0, hours * THIN_POINTS_PER_HOUR))
    return point_count < expected


def is_reader_reachable_sport_key(sport_key: Optional[str]) -> bool:
    """Whether a reader can plausibly arrive at this sport's pages at all.

    **This is the narrowing Fable ruled (live/036 (b)), and it is a narrowing of
    the NIGHTLY only.** The sweep used to nominate every event inside Kalshi's
    retention floor — 44,315 of them, against a nightly budget of 60 and ~550
    new candidates a day. That is not a slow drain, it is a losing race: ~739
    nights for one traversal of a population that grows every night. No budget
    this task can be given fixes an arithmetic that is the wrong shape.

    So the nightly stops trying to own the backlog and pre-warms what a reader
    can reach. What it now skips is not abandoned — :func:`claim_on_demand_fill`
    catches anything a person actually opens. Nightly = likely-reached;
    on-demand = actually-reached. That pairing is why this predicate is allowed
    to be aggressive.

    MEASURED against the real population, 2026-09-02, over the ±7-day reader
    window (4,542 events carrying a Kalshi/Polymarket market):

        KEPT     1,152 across 28 sport keys
        DROPPED  3,390 across 40 — `soccer_other` 2,409, `esports` 463,
                 `tennis_other` 115, `americanfootball_other` 76, …

    Alex's words for the dropped half are *"February soccer"*, and for the kept
    half *"the US Open is the ship"*: the whole US Open cohort survives —
    `tennis_atp` 307, `tennis_atp_us_open` 90, `tennis_wta_us_open` 74,
    `tennis_wta` 111 — beside MLB 170, NCAAF 80, EPL/La Liga/Bundesliga/MLS.

    🔴 **THE TRAP, and the reason this is not one lookup.** The obvious
    authority, ``LEAGUE_CLASS``, spells the US Open ``tennis_us_open``. The
    events carry ``tennis_atp`` and ``tennis_atp_us_open`` — and the SPECIMEN
    itself, event 15300759 (Vallejo v Monfils), is plain ``tennis_atp``. A
    classifier built on ``LEAGUE_CLASS`` alone excludes the exact event this
    queue exists to fix, and it does it silently. ``SPORT_LEAGUE_MAP`` is the
    authority that holds the tour keys (it imports nothing, gotcha #3), and
    tournament-specific keys are its members plus a suffix.
    """
    if not sport_key:
        return False
    from app.tasks.config import SPORT_POLLING_TIERS
    from app.utils.league_classification import LEAGUE_CLASS
    from app.utils.sport_keys import SPORT_LEAGUE_MAP

    if sport_key in SPORT_LEAGUE_MAP:
        return True
    if sport_key in LEAGUE_CLASS:
        return True
    if SPORT_POLLING_TIERS.get(sport_key):
        return True
    # `tennis_atp_us_open`, `tennis_wta_cincinnati_open`,
    # `americanfootball_ncaaf_fcs` — a named tour or league plus a tournament or
    # division segment. The trailing underscore matters: without it
    # `soccer_x` would be matched by a base key `soccer_xy`'s prefix.
    return any(sport_key.startswith(base + "_") for base in SPORT_LEAGUE_MAP)


def granularity_floor_minutes(
    age_seconds: Optional[float],
    *,
    coarse_after_days: int = COARSE_GRANULARITY_AGE_DAYS,
) -> int:
    """Finest candle interval this event's AGE justifies paying for (ruling (c)).

    Returns a FLOOR handed to :func:`choose_period_interval`, never the interval
    itself — the lifetime-vs-request-budget rule still applies on top, so a
    months-old futures market cannot be dragged back down to hourly paging by
    this. A live or just-finished match keeps 1-minute; anything older than
    :data:`COARSE_GRANULARITY_AGE_DAYS` fills hourly.

    ``None`` — an event with no usable start — reads as RECENT, not as old. The
    safe direction for an unknown is the finer curve: paying too much for one
    event costs a few seconds, drawing a five-day match as 120 hourly dots
    costs the shape of the story.
    """
    if age_seconds is None:
        return 1
    return 60 if age_seconds > coarse_after_days * 86400 else 1


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


def _orient_one_market(
    entry: Any, home_team_name: str, away_team_name: str
) -> Optional[tuple[Any, Any, bool]]:
    """Orientation from ONE market, or None if this market cannot say."""
    from app.utils.live_blend import is_game_winner_market
    from app.utils.prediction_market_matching import (
        extract_matchup_with_ticker_fallback,
        find_moneyline_outcome,
    )

    # Kalshi props/spreads never feed the blend, whatever they are linked to —
    # the same gate `compute_source_home_probability` applies.
    if entry.market.source == "kalshi" and not is_game_winner_market(entry.market):
        return None

    matchup = extract_matchup_with_ticker_fallback(
        entry.market.name, external_id=entry.market.external_id
    )
    if not matchup:
        return None

    ordered = sorted(entry.outcomes, key=lambda o: o.rank or 999)
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
    return entry.market, real, bool(yes_is_home)


def resolve_orientation(
    markets_with_outcomes: Sequence[Any],
    home_team_name: str,
    away_team_name: str,
) -> Optional[tuple[Any, Any, bool]]:
    """(market, moneyline outcome, yes_is_home) for one (event, source).

    ``markets_with_outcomes`` is a sequence of
    ``app.utils.live_blend.MarketOutcomes``. Returns ``None`` — never a guess —
    whenever the live writers would also decline: not a game-winner ticker, an
    unparseable matchup, or no outcome that resolves to a team.

    THE PRIMARY IS A PREFERENCE, NOT A VERDICT. ``select_primary_market`` is
    still asked first, so a group that orients agrees with the live writers
    exactly. But its tie-break among equals is "lowest market id", and
    ``is_game_winner_market`` gates only KALSHI — for Polymarket every row scores
    the same, so "lowest id" means OLDEST, and a Polymarket EVENT-level parent
    (minted before its children, carrying no usable outcomes) beats the
    match-winner child that actually has the price series. Measured by CERT-730:
    parent+child resolves to ``None`` while the child alone resolves, so the
    Polymarket curve stayed blank on exactly the events this rail exists for.

    So the rest of the group is tried, in the same deterministic order, and the
    first market that can orient wins. This can only WIDEN what gets drawn: a
    group that already oriented takes the identical answer, because the primary
    is still tried first. The shared selector is deliberately NOT changed — its
    other consumer is the live blend, whose behaviour is not this queue's to move
    (the same reason ``get_market_candlesticks`` was left alone).
    """
    from app.utils.live_blend import select_primary_market

    group = list(markets_with_outcomes or [])
    if not group:
        return None

    primary = select_primary_market(group)
    order = ([primary] if primary is not None else []) + [
        entry for entry in sorted(group, key=lambda e: e.market.id)
        if primary is None or entry.market.id != primary.market.id
    ]
    for entry in order:
        oriented = _orient_one_market(entry, home_team_name, away_team_name)
        if oriented is not None:
            return oriented
    return None


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
    min_period_minutes: int = 1,
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
    interval = choose_period_interval(lifetime, min_interval=min_period_minutes)
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
    service: Any, market: Any, outcome: Any, *, stats: dict,
    min_period_minutes: int = 1,
) -> list[dict]:
    """The CLOB price history for one outcome, finest granularity first.

    ``fidelity=1`` is asked for first because a match is hours long and hourly
    points cannot draw it. Polymarket silently returns nothing for some
    token/fidelity pairs, so an empty answer retries hourly before it counts as
    an absence.

    ``min_period_minutes`` (ruling (c)) skips straight to hourly for an event old
    enough that nobody is scrubbing its chart. **The 1→60 fallback is kept
    either way** — it is a fallback for a token/fidelity pair that answers
    empty, not a granularity preference, and dropping it would turn "this token
    does not serve minute data" back into "this market has no history"
    (gotcha #53).
    """
    token_id = await _polymarket_token_id(service, market, outcome)
    if not token_id:
        stats["no_token_id"] = stats.get("no_token_id", 0) + 1
        return []

    fidelities = (1, 60) if min_period_minutes <= 1 else (60,)
    for fidelity in fidelities:
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
    min_period_minutes: Optional[int] = None,
) -> dict:
    """Draw one event's whole win-prob lifetime from its venues' price history.

    Returns a per-source verdict dict. Never raises for one bad source — a
    Polymarket outage must not cost the Kalshi curve (gotcha #42).

    ``min_period_minutes`` is the granularity floor (ruling (c)). Left ``None``
    it is DERIVED from the event's own age, so every caller — nightly, targeted,
    admin, on-demand — pays the same cheap price for an old event without having
    to remember to ask for it.
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

    if min_period_minutes is None:
        min_period_minutes = granularity_floor_minutes(_event_age_seconds(event))
    verdict["min_period_minutes"] = min_period_minutes

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
            min_period_minutes=min_period_minutes,
        )
    finally:
        for service in owned:
            try:
                await service.close()
            except Exception:  # noqa: BLE001 — closing must never mask the run
                pass


def _event_age_seconds(event: Any) -> Optional[float]:
    """How long ago this event happened, by the best clock it carries.

    ``completed_at`` first, then ``commence_time``. An event that has NOT
    started yet answers 0.0, not a negative — it is as recent as an event gets,
    and a negative age would read as "older than the coarse threshold" the
    moment anyone compared it with ``>`` on an absolute value.
    """
    stamp = getattr(event, "completed_at", None) or getattr(event, "commence_time", None)
    if stamp is None:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds())


async def _backfill_sources(
    session, event, groups, verdict, *,
    kalshi_service, polymarket_service, dry_run, owned,
    min_period_minutes: int = 1,
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
                    service, ticker, start=start, end=end, stats=stats,
                    min_period_minutes=min_period_minutes,
                )
            else:
                service = polymarket_service
                if service is None:
                    from app.services.polymarket_api import PolymarketAPIService

                    service = PolymarketAPIService()
                    owned.append(service)
                raw = await fetch_polymarket_series(
                    service, market, outcome, stats=stats,
                    min_period_minutes=min_period_minutes,
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
        -- THE READER WINDOW + THE READER'S SURFACES (live/036 ruling (b)).
        -- Both halves are the narrowing, and neither works alone: the window
        -- alone leaves 4,542 events of which 2,409 are `soccer_other`, and the
        -- surface test alone re-admits the whole 86-day backlog. Together they
        -- measured 1,152. NOTE the window now reaches FORWARDS as well —
        -- `commence_time <= NOW()` used to be here, and it excluded exactly the
        -- upcoming matches whose five days of pre-match drift is the most
        -- interesting curve we can draw.
        WHERE e.commence_time IS NOT NULL
          AND e.commence_time >= NOW() - make_interval(days => :lookback_days)
          AND e.commence_time <= NOW() + make_interval(days => :lookahead_days)
          AND e.sport_id IN :sport_ids
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
        --
        -- IT IS A KEYSET ON (timestamp, id), NOT ON THE TIMESTAMP ALONE.
        -- `futures_markets.created_at` is transaction-time `now()`, and the
        -- Polymarket poll inserts a whole batch inside ONE transaction, so a
        -- cohort of hundreds sharing a timestamp to the microsecond is the
        -- normal case, not a pathology. Keyed on the timestamp alone, a tied
        -- cohort
        -- LARGER than the scan loses its tail permanently: the page returns the
        -- first N of the tie, the cursor lands ON the shared value, and the next
        -- page's strict `>` steps over the whole cohort including the part never
        -- looked at. The wrap does not save them either — it restarts at the same
        -- head and re-reads the same N. Simulated at 400 tied rows against a 240
        -- scan: 240 repaired, 160 unreachable forever.
        HAVING CAST(:after_ts AS timestamptz) IS NULL
            OR (MIN(fm.created_at), e.id)
                 > (CAST(:after_ts AS timestamptz), CAST(:after_id AS bigint))
        ORDER BY MIN(fm.created_at) ASC, e.id ASC
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
    ORDER BY c.market_first_seen ASC, c.event_id ASC
"""


#: Where the last nightly sweep stopped LOOKING, stored as ``<iso>|<event_id>``.
#: Redis, not a column: the cursor is an optimisation, not a fact about the data,
#: and the 100 MB LRU evicting it costs one wasted re-scan of the oldest page —
#: exactly the behaviour the sweep had before the cursor existed. Never a
#: migration for a hint.
SWEEP_CURSOR_KEY = "event_chart_backfill:sweep_cursor"

#: A keyset position: ``(market_first_seen, event_id)``. The id half is not
#: decoration — see the SQL comment above the HAVING clause.
SweepCursor = tuple


class ThinChartPage(NamedTuple):
    """One page of the ring the nightly sweep walks."""

    event_ids: list[int]
    #: ``(market_first_seen, event_id)`` of the last candidate LOOKED AT (not the
    #: last picked) — everything at or before that KEY has been judged this pass.
    #: A timestamp alone is not a position: `futures_markets.created_at` is
    #: transaction-time, so hundreds of rows share one.
    next_cursor: Optional[tuple]
    #: True when the scan reached the end of the population, so the next run
    #: must WRAP rather than advance. A ring with no wrap is a queue that ends.
    exhausted: bool
    #: How many candidates were LOOKED AT to fill this page. With `event_ids`
    #: it gives the thin density, which is what says whether the sweep is
    #: bounded by work or by budget — see `_note_budget_shortfall`.
    scanned: int = 0


async def reachable_sport_ids(session) -> list[int]:
    """``sports.id`` for every sport a reader can reach, classified in Python.

    The whole table is 176 rows, so this is one trivial scan and the rule stays
    in :func:`is_reader_reachable_sport_key` — one tested pure function — rather
    than being re-expressed as a `LIKE` ladder in SQL that would drift away from
    it. Same discipline as :func:`is_thin_chart`, and the same reason.
    """
    from sqlalchemy import select

    from app.models.models import Sport

    rows = (await session.execute(select(Sport.id, Sport.key))).all()
    return [int(sid) for sid, key in rows if is_reader_reachable_sport_key(key)]


async def select_thin_chart_page(
    session, *, limit: int, scan_multiple: int = 6, after: Optional[tuple] = None
) -> ThinChartPage:
    """One page of events whose chart holds too few points for their market's life.

    Scans a multiple of ``limit`` candidates STARTING AFTER the keyset position
    ``after`` and applies :func:`is_thin_chart` in Python, so the thinness rule
    lives in one tested pure function rather than being re-expressed (and
    drifting) in SQL.

    The cursor is what makes this a sweep rather than a fixed prefix. The scan
    has to be bounded — counting points for all 44,315 candidates inside the
    retention floor is the shape that hit ``statement_timeout`` — but a bound
    with no cursor selects the same oldest page every night, and the night after
    it is repaired that page yields nothing, forever. The cursor advances past
    everything JUDGED, thin or thick, and :data:`ThinChartPage.exhausted` tells
    the caller to wrap.

    ``after`` is a PAIR, ``(timestamp, event_id)``, and the tie-breaker is the
    load-bearing half. ``futures_markets.created_at`` is transaction-time
    ``now()`` and the Polymarket poll commits a whole batch at once, so a cohort
    of hundreds sharing one microsecond is ordinary. Keyed on the timestamp
    alone, a tied cohort larger than the scan loses its tail forever: the page
    reads the first N, the cursor lands ON the shared value, and the next page
    steps over the entire cohort. Same shape as the keyset in
    ``app/tasks/repair_kalshi_fabricated_loss.py``, which runs in production.
    """
    from sqlalchemy import bindparam, text

    from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

    sport_ids = await reachable_sport_ids(session)
    if not sport_ids:
        # Not "nothing is thin" — "the classifier matched no sport we track",
        # which is a broken map, not an empty night. Say so and select nothing
        # rather than falling through to an unfiltered `IN ()` (gotcha #53).
        logger.error(
            "event chart backfill: NO reachable sports resolved — the sweep "
            "selected nothing. Check is_reader_reachable_sport_key against the "
            "sports table; this is a classifier failure, not an idle night."
        )
        return ThinChartPage(event_ids=[], next_cursor=after, exhausted=True, scanned=0)

    after_ts, after_id = (after or (None, None))
    scan_size = max(1, limit * max(1, scan_multiple))
    # `expanding=True`, not `= ANY(:ids)`. An expanding bind renders as a literal
    # IN list at execution time, so it works on every dialect the guards can
    # actually run the REAL statement against — which is the whole point after a
    # `:func:` Sphinx role in this same SQL became a phantom required bind that
    # no stubbed-session test could see.
    statement = text(THIN_CHART_CANDIDATES_SQL).bindparams(
        bindparam("sport_ids", expanding=True)
    )
    rows = (
        await session.execute(
            statement,
            {
                "limit": scan_size,
                "purge_days": PROVABLY_PURGED_AGE_DAYS,
                "after_ts": after_ts,
                "after_id": after_id,
                "lookback_days": READER_REACH_LOOKBACK_DAYS,
                "lookahead_days": READER_REACH_LOOKAHEAD_DAYS,
                "sport_ids": sport_ids,
            },
        )
    ).fetchall()

    thin: list[int] = []
    cursor: Optional[tuple] = None
    for row in rows:
        first = row.market_first_seen
        last = row.market_last_seen
        # Advance over every row JUDGED, not only over the ones picked. A thick
        # chart that the cursor did not pass would be re-counted every night.
        if first is not None:
            cursor = (first, int(row.event_id))
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
        scanned=len(rows),
    )


async def select_thin_chart_events(session, *, limit: int, scan_multiple: int = 6) -> list[int]:
    """The ids of one page, from the start of the ring."""
    page = await select_thin_chart_page(
        session, limit=limit, scan_multiple=scan_multiple
    )
    return page.event_ids


def _read_sweep_cursor() -> Optional[tuple]:
    """The stored ``(timestamp, event_id)``, or None to restart the ring.

    Every failure mode — no Redis, an evicted key, a half-written value, an
    unparseable one — answers None, which restarts the sweep. Restarting is the
    pre-cursor behaviour: it wastes a scan, it never writes a wrong row.
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
    stamp, _, event_id = str(raw).partition("|")
    try:
        parsed = datetime.fromisoformat(stamp)
        # A cursor with no id half is not usable as a keyset — half a position
        # is the bug this pair exists to fix, so refuse it and restart.
        parsed_id = int(event_id)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (parsed, parsed_id)


#: 🔴 HISTORICAL, and kept only so nobody re-derives the number that caused the
#: redesign. This was the UNNARROWED population — every event inside the 86-day
#: retention floor carrying a Kalshi/Polymarket market — against ~550 new
#: candidates a day. At `limit=60` that is ~739 nights for one traversal of a
#: set that grows every night. **It is no longer the sweep's population and must
#: never be used as its denominator again** (live/036 ruling (b) dropped the
#: backlog as a goal); `_note_budget_shortfall` measures the NARROWED set.
HISTORICAL_UNNARROWED_POPULATION = 44_315
HISTORICAL_UNNARROWED_DAILY_INFLOW = 550

#: Measured on production 2026-09-02 AFTER the narrowing, and these are the
#: numbers the shortfall arithmetic actually uses. `REACHABLE_POPULATION` is
#: events inside the ±7-day reader window on a reader-reachable sport;
#: `REACHABLE_DAILY_INFLOW` is that population divided by the window's own width
#: — an event enters at `commence - 7d` and leaves at `commence + 7d`, so in the
#: steady state the set turns over once every `lookback + lookahead` days. That
#: is a DERIVED rate, not a second observation, which is why it is computed from
#: the two numbers beside it rather than quoted.
MEASURED_REACHABLE_POPULATION = 1_152


def _reachable_daily_inflow(
    population: int = MEASURED_REACHABLE_POPULATION,
    *,
    window_days: int = READER_REACH_LOOKBACK_DAYS + READER_REACH_LOOKAHEAD_DAYS,
) -> int:
    """Events per day entering the reader window, derived from its own width."""
    return max(1, round(population / max(1, window_days)))


def _note_budget_shortfall(result: dict, page: "ThinChartPage", limit: int) -> None:
    """Say out loud when the sweep is bounded by BUDGET rather than by work.

    Gotcha #53 / `task_verdict`: "it returned" is not "it worked". A nightly that
    repairs its 60 and reports `status: complete` is indistinguishable from one
    that has finished the job.

    What changed in live/036: the denominator. This used to compare the budget
    against 44,315 candidates and ~550/day of inflow and correctly conclude that
    the sweep could never win. It is now measured against the population the
    sweep actually has — the ±7-day reader window on reachable sports, 1,152
    events turning over roughly every 14 days — because comparing a narrowed
    sweep to the backlog it was explicitly told to stop chasing would report
    failure on a ship that works.

    It still tells the truth in the other direction: if the narrowed set ALSO
    outruns the budget, this says so, in the terminal, with the arithmetic.
    """
    budget_bound = not page.exhausted and len(page.event_ids) >= limit
    inflow = _reachable_daily_inflow()
    result["candidates_scanned"] = page.scanned
    result["thin_seen"] = len(page.event_ids)
    result["sweep_budget_bound"] = budget_bound
    result["sweep_population"] = "reader_reachable"
    result["measured_reachable_population"] = MEASURED_REACHABLE_POPULATION
    result["measured_daily_inflow"] = inflow
    result["sweep_keeps_up"] = limit >= inflow
    if not budget_bound:
        return
    nights = max(1, MEASURED_REACHABLE_POPULATION // max(1, limit))
    result["measured_nights_per_traversal"] = nights
    logger.warning(
        "event chart backfill: sweep is BUDGET-BOUND — filled its limit of %s from "
        "a scan of %s and did not reach the end. ~%s nights per traversal of the "
        "%s reader-reachable candidates, against ~%s entering the window per day. "
        "Keeps up: %s. On-demand fills cover what this misses.",
        limit, page.scanned, nights,
        MEASURED_REACHABLE_POPULATION, inflow, limit >= inflow,
    )


def _cursor_label(cursor: Optional[tuple]) -> Optional[str]:
    """A keyset position, readable in the task verdict. Both halves or neither."""
    if not cursor:
        return None
    stamp, event_id = cursor
    return f"{stamp.isoformat()}|{event_id}"


def _write_sweep_cursor(cursor: Optional[tuple], *, exhausted: bool) -> None:
    """Persist ``<iso>|<event_id>``, or CLEAR it when the ring has been walked."""
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        if exhausted or cursor is None:
            client.delete(SWEEP_CURSOR_KEY)
        else:
            stamp, event_id = cursor
            client.set(SWEEP_CURSOR_KEY, f"{stamp.isoformat()}|{int(event_id)}")
    except Exception:  # noqa: BLE001 — losing the hint costs a re-scan, not a row
        logger.warning("event chart backfill: sweep cursor not persisted", exc_info=True)


# ---------------------------------------------------------------------------
# On demand — the half the nightly is allowed to miss (live/036 ruling (c))
# ---------------------------------------------------------------------------

#: How long one event stays claimed after an on-demand fill is enqueued. Long
#: enough that a page being refreshed, or shared and opened by twenty people,
#: costs ONE fill; short enough that a live match whose chart is still filling in
#: gets another pass the same day.
ON_DEMAND_CLAIM_TTL_SECONDS = 6 * 3600

#: Ceiling on on-demand fills started in any one clock hour, across the whole
#: site. This is the crawler bound: `/api/events/{id}/history` is a public,
#: cacheable GET, and a bot walking every event id must not be able to convert
#: page views into unbounded outbound venue traffic. Sized above any plausible
#: human hour on this cohort and far below the venues' rate limits.
ON_DEMAND_HOURLY_CAP = 120

ON_DEMAND_CLAIM_KEY = "event_chart_backfill:ondemand:{event_id}"
ON_DEMAND_BUDGET_KEY = "event_chart_backfill:ondemand:budget:{hour}"


def claim_on_demand_fill(
    event_id: int, *, now: Optional[datetime] = None, cap: int = ON_DEMAND_HOURLY_CAP
) -> tuple[bool, str]:
    """Reserve the right to enqueue ONE fill for this event. ``(claimed, why)``.

    Two bounds, and they are checked in this order for a reason. The per-event
    claim goes first so a popular page cannot spend the hourly budget on itself;
    the hourly budget is only charged once a claim has actually been won.

    🔴 **A Redis failure REFUSES the claim.** Every other Redis touch in this
    module treats a miss as "no hint, do the work anyway" — this one must not.
    Without Redis there is no dedupe, and the caller is a public GET: failing
    open would turn one crawler into one enqueued task per request, forever. The
    cost of failing closed is that charts fill on the nightly instead of on the
    click. Routed through ``get_redis_client()`` so it cannot hang the event loop
    on a socket with no timeout (gotcha #39).
    """
    stamp = now or datetime.now(timezone.utc)
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        claim_key = ON_DEMAND_CLAIM_KEY.format(event_id=int(event_id))
        if not client.set(claim_key, "1", nx=True, ex=ON_DEMAND_CLAIM_TTL_SECONDS):
            return False, "already_claimed"

        budget_key = ON_DEMAND_BUDGET_KEY.format(hour=stamp.strftime("%Y%m%d%H"))
        spent = client.incr(budget_key)
        # Expire generously past the hour so a counter minted at :59 cannot be
        # read as a fresh hour at :00 — and set every time, because a key that
        # was INCR'd without an EXPIRE (a crash between the two) would otherwise
        # cap that hour forever.
        client.expire(budget_key, 7200)
        if spent > max(1, cap):
            # Hand the claim back. The next hour's budget should be able to fill
            # this chart; a six-hour claim on an event we refused would make one
            # busy hour suppress it for the rest of the day.
            client.delete(claim_key)
            return False, "hourly_cap"
        return True, "claimed"
    except Exception:  # noqa: BLE001 — see the docstring: no Redis, no claim
        logger.warning(
            "event chart backfill: on-demand claim refused for event %s — Redis "
            "unavailable, so there is no dedupe to enqueue behind",
            event_id, exc_info=True,
        )
        return False, "no_redis"


def release_on_demand_claim(event_id: int) -> None:
    """Hand a won claim back, for a caller whose dispatch then failed.

    Without this, a broker hiccup would hold the event's claim for the full TTL
    and the chart would wait six hours for a fill that was never enqueued.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().delete(ON_DEMAND_CLAIM_KEY.format(event_id=int(event_id)))
    except Exception:  # noqa: BLE001 — the claim expires on its own regardless
        logger.warning(
            "event chart backfill: on-demand claim for event %s not released",
            event_id, exc_info=True,
        )


async def plan_on_demand_fill(
    session, event, *, served_points: int
) -> Optional[dict]:
    """A thin chart was just SERVED — decide whether to start filling it.

    🔴 **THIS DECIDES; IT DOES NOT DISPATCH.** The `.apply_async` lives in the
    ROUTE, and that is a rule with a guard behind it
    (`test_no_task_dispatches_another_task`): anything under `app/tasks/` that
    dispatches is invisible to the route scan that derives
    `RESULT_CONSUMER_TASKS`, so an intra-task dispatch can grow a result
    consumer nobody declared and leave its status poll hanging forever. The
    claim is still won HERE, because winning it is part of the decision — see
    :func:`release_on_demand_claim` for the caller's side of that bargain.

    This is the half of live/036 that makes the narrowing honest. The nightly
    now pre-warms only what a reader is likely to reach; this covers what a
    reader DID reach, which is the only population that was ever really owed a
    curve. A February soccer match nobody opens stays thin forever and that is
    the ruling, not a gap — the same match, opened once, fills itself.

    Never raises and never blocks: it enqueues, it does not backfill. The
    response the caller is about to return is unchanged — this reader still sees
    the thin chart. The next one does not.

    Returns ``{"enqueue": True, ...}`` when the caller should dispatch, a
    ``{"enqueue": False, "reason": ...}`` verdict when it should not, or
    ``None`` when the event was never a candidate at all.
    """
    try:
        return await _plan_on_demand_fill(
            session, event, served_points=served_points
        )
    except Exception:  # noqa: BLE001 — a chart endpoint never fails on its own
        logger.warning(
            "event chart backfill: on-demand consideration failed for event %s",
            getattr(event, "id", None), exc_info=True,
        )
        return None


async def _plan_on_demand_fill(
    session, event, *, served_points: int
) -> Optional[dict]:
    from sqlalchemy import func, select

    from app.models.models import FuturesMarket
    from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

    event_id = int(getattr(event, "id", 0) or 0)
    if not event_id:
        return None

    # CHEAP GATE FIRST, and it is load-bearing. Everything below costs a query;
    # a chart that already holds a full life of points must reach none of it.
    # `THIN_MAX_EXPECTED_POINTS` is the cap inside `is_thin_chart`, so no series
    # at or above it can be thin under any lifetime — this cannot reject a
    # candidate the real predicate would have accepted.
    if served_points >= THIN_MAX_EXPECTED_POINTS:
        return None

    age_seconds = _event_age_seconds(event)
    if age_seconds is not None and age_seconds > PROVABLY_PURGED_AGE_DAYS * 86400:
        # Past the retention floor the venue has provably deleted the candles
        # (gotcha #35). Enqueueing here spends a worker to learn nothing.
        return {"enqueue": False, "reason": "beyond_retention_floor"}

    first_seen = (
        await session.execute(
            select(func.min(FuturesMarket.created_at)).where(
                FuturesMarket.event_id == event_id,
                FuturesMarket.source.in_(("kalshi", "polymarket")),
            )
        )
    ).scalar_one_or_none()
    if first_seen is None:
        # No venue market means no venue history. Not every thin chart is one
        # this rail can fix, and saying so is not the same as saying it is fine.
        return {"enqueue": False, "reason": "no_venue_markets"}

    if first_seen.tzinfo is None:
        first_seen = first_seen.replace(tzinfo=timezone.utc)
    end = getattr(event, "completed_at", None) or datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    lifetime = max(0.0, (end - first_seen).total_seconds())

    if not is_thin_chart(served_points, lifetime):
        return None

    claimed, why = claim_on_demand_fill(event_id)
    if not claimed:
        return {"enqueue": False, "reason": why}

    floor_minutes = granularity_floor_minutes(age_seconds)
    logger.info(
        "event chart backfill: on-demand fill planned for event %s — served %s "
        "points for a %.1fh market life, filling at %s-minute granularity",
        event_id, served_points, lifetime / 3600.0, floor_minutes,
    )
    return {
        "enqueue": True,
        "event_id": event_id,
        "served_points": served_points,
        "lifetime_hours": round(lifetime / 3600.0, 2),
        "min_period_minutes": floor_minutes,
    }


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
        result["swept_from"] = _cursor_label(after)
        result["swept_to"] = _cursor_label(page.next_cursor)
        result["ring_wrapped"] = page.exhausted
        _note_budget_shortfall(result, page, limit)
        if not dry_run:
            _write_sweep_cursor(page.next_cursor, exhausted=page.exhausted)
    return result

