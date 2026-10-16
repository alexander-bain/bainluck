"""Kalshi's historical (archive) tier → an exact-ID recovery plan. Pure. (#683)

PILLAR: TRUTH. SHIP: settled Kalshi questions that have no price history get
back their real pre-resolution probability timeline, and archive provenance stays
separate from live capture.

WHY AN ARCHIVE ARM. ``kalshi_retention`` measured that live ``/markets`` reads go
200-empty for a market settled more than ~74–86 days ago, and every recovery rail
was floored at that bound. That floor was right for the LIVE endpoints. It does
not prove the history was deleted: Kalshi moves a market settled before
``GET /historical/cutoff``'s ``market_settled_ts`` into ``/historical/*``. On
2026-10-15 Alex ran an independent sample in plain Mac Terminal: 57 GETs, all 200
(``artifacts/calibration-683-archive-20261015/ROOT-AUDIT.md``). Five series had
usable hourly archive prices before settlement, on 20 of 22 sampled markets.
That is a sample, not a population. This module turns it into a plan that can be
reviewed, and never into a write.

WHAT THIS MODULE DECIDES, AND THE RULES IT WILL NOT BEND

1. **Routing comes from the provider's cutoff, read fresh.** A market settled
   before ``market_settled_ts`` is ``archive``, one settled at or after it is
   ``recent`` (the live rails' job), and one with no settlement time is
   ``unknown``. ``market_settled_ts`` moves about a day per day, so it is never a
   constant here.
2. **Identity is exact.** The archive row must carry the STORED outcome ticker
   byte for byte, under the STORED event ticker, in a settled state. A near miss
   refuses. It never "finds the closest market".
3. **A price is an observation from the interval, never a carried value.**
   Archive candles name their prices without the ``_dollars`` suffix
   (``price.close``, ``yes_bid.close``). They are mapped onto the house reducer
   :func:`~app.utils.kalshi_candle_price.candle_yes_price`, so no second price
   policy exists, and ``price.previous`` is DROPPED first. ``previous`` is the
   last trade from some EARLIER interval, so a candle whose only price is
   ``previous`` has no price of its own. Kalshi returns exactly that shape for
   zero-volume intervals (``KXNBA-26-WAS``: ``close null … previous "0.0100"``,
   ``volume "0.00"``). A row also records whether a trade happened in its
   interval (``traded_interval``) or only a quote was standing (``quote_only``).
   A non-null candle count is not a trade count.
4. **PRE-SETTLEMENT IS NOT PREGAME.** Some spread and total markets open during
   play: ``KXNCAAMBSPREAD-26APR06CONNMICH-MICH20`` opened at 02:31Z and settled
   at 03:28Z. A candle is admitted as a FORECAST only when the WHOLE interval
   ends at or before the authoritative forecast cutoff,
   ``min(event start, settlement)``. The start is admitted only when the existing
   house guard :func:`~app.utils.calibration_paired_prestart.start_refusal`
   passes it. A start stamped by a venue (``kalshi``, ``kalshi_occurrence``,
   ``polymarket``: gotcha #14, a close or expiry or listing time) is also refused
   for this arm. No start, or a start nobody can vouch for, means the candle is at
   most ``reader_only``. It is never a forecast.
5. **Nothing at or after settlement.** A candle that ends at or after the venue's
   own ``settlement_ts`` is refused outright, including one that straddles it.
   It may hold earlier activity, but it cannot be told apart from what came after.

6. **Full history is chunked, never coarsened or clipped.** A long market is
   asked for in several windows at the same width, each inside the request
   bound. The width is one minute or one hour, never daily: daily candles missed
   every sampled NCAA spread market. An outcome whose opening is unknown, or
   whose windows were not all read, is ``incomplete`` and names the windows it
   still owes. A bounded sample is never reported as ``complete``.

The plan carries its provenance on every row (``source``, interval start and end,
period, archive cutoff, forecast cutoff, and the reason a row is not a forecast).
:func:`plan_digest` makes it a reviewable, repeatable artifact: the same inputs
give the same digest, which is what makes a later import idempotent.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional, Sequence

from app.utils.calibration_paired_prestart import start_refusal
from app.utils.event_completion import VENUE_STAMP_COMMENCE_SOURCES
from app.utils.kalshi_candle_price import candle_yes_price

#: Provenance stamped on every planned row. Deliberately NOT ``kalshi``. The
#: rows live in their own archive store (see the #683 models), and the readers
#: serve this value as each point's provenance.
ARCHIVE_SOURCE = "kalshi_archive"

#: Candle widths the archive endpoint takes, in minutes. Recovery asks for
#: ``PERIOD_MINUTE`` or ``PERIOD_HOUR`` only. ``PERIOD_DAY`` is named so a guard
#: can prove it is never chosen.
PERIOD_MINUTE = 1
PERIOD_HOUR = 60
PERIOD_DAY = 1440

#: At or under this open→settlement span, ask for one-minute candles. Hourly
#: candles cannot resolve a market that lives a couple of hours, and daily
#: candles missed every sampled NCAA spread market. 6h of one-minute candles is
#: at most 360 rows, so the response stays small.
SHORT_MARKET_SPAN = timedelta(hours=6)

#: Our own per-request bound on candles. This is a request-size limit WE chose.
#: It is not a claim about Kalshi's limit. A span with more candles than this is
#: CHUNKED into several windows at the same width. It is never coarsened.
CANDLES_PER_REQUEST_BOUND = 4000

#: When the archive listing carries no ``open_time``, how far back of settlement
#: to ask. Bounded so a missing field can never become an unbounded window, and
#: everything before it is OWED (``opening_unknown``): the outcome stays
#: ``incomplete`` and the earlier history is never reported as absent.
MISSING_OPEN_LOOKBACK = timedelta(days=30)

COVERAGE_COMPLETE = "complete"
COVERAGE_INCOMPLETE = "incomplete"
OWED_OPENING_UNKNOWN = "opening_unknown"
OWED_NOT_READ = "window_not_read"
OWED_MALFORMED_CANDLES = "malformed_candles"

#: Venue states that mean "settled". Anything else is not a settled market.
ARCHIVE_SETTLED_STATUSES = frozenset({"finalized", "settled"})

ROUTE_ARCHIVE = "archive"
ROUTE_RECENT = "recent"
ROUTE_UNKNOWN = "unknown"

ADMIT_FORECAST = "forecast"
ADMIT_READER_ONLY = "reader_only"
REFUSE_POST_SETTLEMENT = "post_settlement"
REFUSE_NO_PRICE = "no_price"

BASIS_TRADED = "traded_interval"
BASIS_QUOTE = "quote_only"
BASIS_PREVIOUS_ONLY = "previous_only"
BASIS_NONE = "no_price"

#: Why a start may not bound a forecast in this arm, beyond ``start_refusal``.
CUTOFF_VENUE_STAMP = "start_is_venue_stamp"
CUTOFF_NO_SETTLEMENT = "settlement_unknown"


def parse_instant(value: Any) -> Optional[datetime]:
    """An ISO string, epoch number or datetime, as aware UTC. ``None`` if unusable."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def archive_settled_cutoff(cutoff_payload: Any) -> Optional[datetime]:
    """``market_settled_ts`` from ``/historical/cutoff``; ``None`` fails closed."""
    if not isinstance(cutoff_payload, dict):
        return None
    return parse_instant(cutoff_payload.get("market_settled_ts"))


def route_market(settled_at: Optional[datetime], archive_cutoff: datetime) -> str:
    """Which tier answers for a market settled at ``settled_at``."""
    if settled_at is None:
        return ROUTE_UNKNOWN
    return ROUTE_ARCHIVE if settled_at < archive_cutoff else ROUTE_RECENT


def identity_refusal(
    stored_ticker: str, stored_event_ticker: Optional[str], listed: Any
) -> Optional[str]:
    """``None`` when ``listed`` IS the stored market; otherwise the reason it is not."""
    if not isinstance(listed, dict):
        return "listing_row_malformed"
    if listed.get("ticker") != stored_ticker:
        return "ticker_mismatch"
    if not stored_event_ticker or listed.get("event_ticker") != stored_event_ticker:
        return "event_ticker_mismatch"
    if listed.get("status") not in ARCHIVE_SETTLED_STATUSES:
        return "not_settled_at_venue"
    if parse_instant(listed.get("settlement_ts")) is None:
        return "settlement_ts_missing"
    return None


def choose_period(open_time: Optional[datetime], settled_at: datetime) -> int:
    """One minute for a market that lives at most ``SHORT_MARKET_SPAN``, else one hour.

    Never daily. The span sets the resolution only. Request size is
    :func:`request_windows`' job, so a season-long market keeps hourly candles
    across several windows instead of trading them for daily ones. An unknown
    opening gets hourly: its span is unknown, not short.
    """
    if open_time is None:
        return PERIOD_HOUR
    span = max(settled_at - open_time, timedelta(0))
    return PERIOD_MINUTE if span <= SHORT_MARKET_SPAN else PERIOD_HOUR


@dataclass(frozen=True)
class RequestWindow:
    """One archive candle request. ``start_ts``/``end_ts`` are epoch seconds."""

    start_ts: int
    end_ts: int
    period_minutes: int


def request_windows(
    open_time: Optional[datetime], settled_at: datetime, period_minutes: int
) -> tuple[list[RequestWindow], Optional[dict]]:
    """Every window from the opening to settlement, oldest first, plus any owed gap.

    Each window holds at most ``CANDLES_PER_REQUEST_BOUND`` candles of
    ``period_minutes``. Adjacent windows share their boundary instant, and
    :func:`classify_candles` drops the repeated interval. When the opening is
    unknown the windows cover only ``MISSING_OPEN_LOOKBACK`` before settlement
    and the second value is the owed gap before them (``start_ts`` ``None``:
    nobody knows where it begins). Otherwise it is ``None``.
    """
    end = settled_at
    gap: Optional[dict] = None
    if open_time is None:
        start = settled_at - MISSING_OPEN_LOOKBACK
        gap = {
            "start_ts": None,
            "end_ts": int(start.timestamp()),
            "period_minutes": period_minutes,
            "reason": OWED_OPENING_UNKNOWN,
        }
    else:
        start = min(open_time, settled_at)
    width = timedelta(minutes=period_minutes * CANDLES_PER_REQUEST_BOUND)
    windows: list[RequestWindow] = []
    cursor = start
    while cursor < end:
        upper = min(cursor + width, end)
        windows.append(
            RequestWindow(
                int(cursor.timestamp()), int(upper.timestamp()), period_minutes
            )
        )
        cursor = upper
    if not windows:  # opened at settlement: one zero-span ask, still bounded
        windows.append(
            RequestWindow(int(start.timestamp()), int(end.timestamp()), period_minutes)
        )
    return windows, gap


def owed_window(window: RequestWindow, reason: str = OWED_NOT_READ) -> dict:
    """A window this run did not read, as the plan reports it."""
    return {**asdict(window), "reason": reason}


def _side(container: Any, keys: Iterable[str]) -> dict:
    """Map an archive price block (``close``) onto the live spelling (``close_dollars``)."""
    out: dict = {}
    if not isinstance(container, dict):
        return out
    for key in keys:
        value = container.get(f"{key}_dollars")
        if value is None:
            value = container.get(key)
        if value is not None and value != "":
            out[f"{key}_dollars"] = value
    return out


def archive_candle_price(candle: Any) -> tuple[Optional[float], str]:
    """``(probability, basis)`` for one archive candle, or ``(None, why not)``.

    The reduction is the house one. Only the spelling is adapted, and
    ``price.previous`` is removed so a carried value can never become a point.
    """
    if not isinstance(candle, dict):
        return None, BASIS_NONE
    price_block = _side(candle.get("price"), ("close", "mean"))
    normalized = {
        "yes_bid": _side(candle.get("yes_bid"), ("close",)),
        "yes_ask": _side(candle.get("yes_ask"), ("close",)),
        "price": price_block,
    }
    probability = candle_yes_price(normalized)
    if probability is None:
        previous = _side(candle.get("price"), ("previous",))
        return None, (BASIS_PREVIOUS_ONLY if previous else BASIS_NONE)
    return probability, (BASIS_TRADED if price_block else BASIS_QUOTE)


def forecast_cutoff(
    event: Any, settled_at: Optional[datetime]
) -> tuple[Optional[datetime], Optional[str]]:
    """``(cutoff, None)`` when a forecast boundary is known, else ``(None, reason)``.

    ``event`` is duck-typed on ``commence_time``, ``commence_time_source``,
    ``created_at`` and ``completed_at`` (``None`` when nothing is linked). The
    settlement passed in is the VENUE's ``settlement_ts``, not
    ``futures_markets.resolution_date``, which is a backstop (CAL-P989).
    """
    if settled_at is None:
        return None, CUTOFF_NO_SETTLEMENT
    refusal = start_refusal(event, resolution_date=settled_at)
    if refusal is not None:
        return None, refusal
    if getattr(event, "commence_time_source", None) in VENUE_STAMP_COMMENCE_SOURCES:
        return None, CUTOFF_VENUE_STAMP
    commence = parse_instant(getattr(event, "commence_time", None))
    return min(commence, settled_at), None


@dataclass(frozen=True)
class PlannedPoint:
    """One archive interval and the decision made about it. Never a write."""

    outcome_id: int
    ticker: str
    interval_start: str
    interval_end: str
    period_minutes: int
    admission: str
    reason: Optional[str]
    price_basis: str
    probability: Optional[float]
    volume: Optional[str]
    source: str = ARCHIVE_SOURCE
    already_stored: bool = False
    #: SHA-256 of the exact provider response this candle was read from. The
    #: import stores it beside the interval, so every stored row names its bytes.
    raw_sha256: Optional[str] = None


@dataclass
class OutcomePlan:
    """Everything decided for one stored outcome."""

    outcome_id: int
    ticker: str
    route: str
    refusal: Optional[str] = None
    period_minutes: Optional[int] = None
    settled_at: Optional[str] = None
    forecast_cutoff: Optional[str] = None
    cutoff_refusal: Optional[str] = None
    #: ``complete`` only when every window from a KNOWN opening to settlement
    #: was read and no candle was malformed. ``None`` when no candles were asked.
    coverage: Optional[str] = None
    windows_requested: int = 0
    windows_read: int = 0
    owed_windows: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    points: list = field(default_factory=list)
    #: The stored identity this plan was decided on, and its fingerprint. An
    #: import re-reads the same fields and refuses the outcome if they moved.
    event_ticker: Optional[str] = None
    input_fingerprint: Optional[str] = None
    #: The listed market fields the plan used (identity, opening, settlement).
    market: Optional[dict] = None
    #: One entry per window READ: its bounds, the echoed ticker, the response
    #: digest and the exact response text. An import re-derives the points from
    #: these bytes and refuses a plan whose points do not follow from them.
    windows: list = field(default_factory=list)
    #: How many live snapshots the outcome already had when planned. Archive
    #: evidence is kept beside them; the reader decides overlap, not the plan.
    live_snapshots: int = 0


def candle_is_wellformed(candle: Any) -> bool:
    """A dict with a numeric ``end_period_ts`` (a bool is not a number here)."""
    if not isinstance(candle, dict):
        return False
    end = candle.get("end_period_ts")
    return (
        isinstance(end, (int, float))
        and not isinstance(end, bool)
        and parse_instant(end) is not None
    )


def classify_candles(
    *,
    outcome_id: int,
    ticker: str,
    candles: Iterable[Any],
    period_minutes: int,
    settled_at: datetime,
    cutoff: Optional[datetime],
    cutoff_refusal: Optional[str],
    stored_instants: Iterable[datetime] = (),
    candle_lineage: Optional[Sequence[Optional[str]]] = None,
) -> tuple[list[PlannedPoint], dict]:
    """Decide every candle. Returns ``(points, counts)``; refused rows are kept.

    ``stored_instants`` are interval ends this outcome already holds in the
    archive store at this period. A point at one of them is marked
    ``already_stored`` and is never importable, so a plan built twice, or after
    a partial import, cannot double a row. ``candle_lineage`` is the response
    digest of each candle, position for position; it rides onto the point.
    """
    stored = {parse_instant(t) for t in stored_instants}
    candles = list(candles)
    lineage = list(candle_lineage) if candle_lineage is not None else []
    if lineage and len(lineage) != len(candles):
        raise ValueError("candle_lineage must align with candles")
    period = timedelta(minutes=period_minutes)
    counts = {
        ADMIT_FORECAST: 0,
        ADMIT_READER_ONLY: 0,
        REFUSE_POST_SETTLEMENT: 0,
        REFUSE_NO_PRICE: 0,
        "previous_only": 0,
        "malformed": 0,
        "duplicate_interval": 0,
        "already_stored": 0,
    }
    seen: set = set()
    points: list[PlannedPoint] = []
    for index, candle in enumerate(candles):
        if not candle_is_wellformed(candle):
            counts["malformed"] += 1
            continue
        end = parse_instant(candle["end_period_ts"])
        if end in seen:
            counts["duplicate_interval"] += 1
            continue
        seen.add(end)
        start = end - period
        probability, basis = archive_candle_price(candle)
        reason: Optional[str] = None
        if end >= settled_at:
            admission = REFUSE_POST_SETTLEMENT
            reason = (
                "interval_crosses_settlement"
                if start < settled_at
                else "after_settlement"
            )
        elif probability is None:
            admission = REFUSE_NO_PRICE
            reason = basis
            if basis == BASIS_PREVIOUS_ONLY:
                counts["previous_only"] += 1
        elif cutoff is not None and end <= cutoff:
            admission = ADMIT_FORECAST
        else:
            admission = ADMIT_READER_ONLY
            if cutoff is None:
                reason = f"forecast_cutoff_unknown:{cutoff_refusal}"
            elif start < cutoff:
                reason = "interval_crosses_forecast_cutoff"
            else:
                reason = "after_forecast_cutoff"
        counts[admission] += 1
        already = end in stored and admission in (ADMIT_FORECAST, ADMIT_READER_ONLY)
        if already:
            counts["already_stored"] += 1
        volume = candle.get("volume_fp", candle.get("volume"))
        points.append(
            PlannedPoint(
                outcome_id=outcome_id,
                ticker=ticker,
                interval_start=start.isoformat(),
                interval_end=end.isoformat(),
                period_minutes=period_minutes,
                admission=admission,
                reason=reason,
                price_basis=basis,
                probability=None if probability is None else round(probability, 6),
                volume=None if volume is None else str(volume),
                already_stored=already,
                raw_sha256=lineage[index] if lineage else None,
            )
        )
    return points, counts


def importable(points: Iterable[PlannedPoint]) -> list[PlannedPoint]:
    """The points a FUTURE import could write: priced, pre-settlement, not stored."""
    return [
        p
        for p in points
        if p.admission in (ADMIT_FORECAST, ADMIT_READER_ONLY) and not p.already_stored
    ]


def plan_digest(points: Iterable[PlannedPoint]) -> str:
    """SHA-256 over the importable points in canonical order. Order-independent."""
    rows = sorted(
        (asdict(p) for p in importable(points)),
        key=lambda r: (r["outcome_id"], r["interval_end"], r["period_minutes"]),
    )
    blob = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


# ── #683 successor: input fingerprint and the continuation carry ───────────

#: The stored fields a plan's decision depends on: identity (which market) and
#: the forecast-cutoff inputs (``forecast_cutoff``). An import re-reads exactly
#: these and refuses an outcome whose fingerprint moved since it was planned.
FINGERPRINT_FIELDS = (
    "outcome_id",
    "ticker",
    "event_ticker",
    "market_id",
    "event_id",
    "commence_time",
    "commence_time_source",
    "created_at",
    "completed_at",
    "resolution_source",
)

#: Version of the carry a stopped run hands the next one. A carry from another
#: version is refused, never guessed at.
CONTINUATION_VERSION = 1


def _canonical(value: Any) -> Any:
    if isinstance(value, datetime):
        return parse_instant(value).isoformat()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _digest(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def input_fingerprint(row: Any) -> str:
    """SHA-256 over :data:`FINGERPRINT_FIELDS` read off ``row`` (duck-typed)."""
    return _digest({name: _canonical(getattr(row, name, None)) for name in FINGERPRINT_FIELDS})


def listed_identity(market: dict) -> dict:
    """The listed fields a plan relies on, nothing else (no prices, no volumes)."""
    return {
        key: market.get(key)
        for key in ("ticker", "event_ticker", "status", "open_time", "settlement_ts")
    }


def continuation_digest(carry: dict) -> str:
    """Digest of a carry, over everything except its own ``digest`` field."""
    return _digest({k: v for k, v in carry.items() if k != "digest"})


def seal_continuation(carry: dict) -> dict:
    """Stamp the version and the digest a later run will check."""
    sealed = {**carry, "version": CONTINUATION_VERSION}
    sealed["digest"] = continuation_digest(sealed)
    return sealed


def continuation_refusal(
    carry: Any, *, outcome_id: int, ticker: str, event_ticker: Optional[str]
) -> Optional[str]:
    """``None`` when ``carry`` may resume this stored outcome; else why not.

    Structural checks only (version, seal, identity, listing shape, and that
    carried windows are exactly the leading windows a fresh plan would ask
    for). The raw bytes of each carried window are re-verified by the caller,
    which owns the response parser.
    """
    if not isinstance(carry, dict):
        return "carry_malformed"
    if carry.get("version") != CONTINUATION_VERSION:
        return "carry_version"
    if carry.get("digest") != continuation_digest(carry):
        return "carry_digest_mismatch"
    if carry.get("outcome_id") != outcome_id or carry.get("ticker") != ticker:
        return "carry_identity_mismatch"
    if carry.get("event_ticker") != event_ticker:
        return "carry_event_ticker_mismatch"
    stage = carry.get("stage")
    if stage == "listing":
        if not isinstance(carry.get("listing_markets"), dict):
            return "carry_listing_malformed"
        if not isinstance(carry.get("listing_cursor"), str) or not carry["listing_cursor"]:
            return "carry_listing_cursor_missing"
        return None
    if stage != "candles":
        return "carry_stage_unknown"
    market = carry.get("market")
    if identity_refusal(ticker, event_ticker, market) is not None:
        return "carry_market_identity"
    settled_at = parse_instant(market.get("settlement_ts"))
    open_time = parse_instant(market.get("open_time"))
    period = choose_period(open_time, settled_at)
    if carry.get("period_minutes") != period:
        return "carry_period_mismatch"
    expected, _ = request_windows(open_time, settled_at, period)
    read = carry.get("read_windows")
    if not isinstance(read, list) or not read or len(read) >= len(expected):
        return "carry_windows_malformed"
    for window, want in zip(read, expected):
        if not isinstance(window, dict) or (
            window.get("start_ts"),
            window.get("end_ts"),
            window.get("period_minutes"),
        ) != (want.start_ts, want.end_ts, want.period_minutes):
            return "carry_window_bounds_mismatch"
    return None
