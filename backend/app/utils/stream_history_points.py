"""#11929 cause 2 — the live stream writes bounded chart history from its flush.

WHAT A READER SEES. A futures or props chart is drawn from
``futures_odds_snapshots`` rows, and until now only the polling tasks wrote them
(``kalshi.py``, ``venue_poll_30s.py``, ``futures_price_refresh.py``, …). A leg
the Kalshi or Polymarket socket moved 200 times an hour still charted at the
poll's cadence — on the Midterms collection a point every ~2 hours. With this
module on, the socket's own flush adds a chart point when a leg's committed
price has really moved.

THE RULE (Alex, Nov 3): a streamed leg's committed price gets one history row
when it moved >= 1 point since its last stream history row
(:data:`HISTORY_MOVE`), or when :data:`HISTORY_INTERVAL_S` (5 minutes) has
passed since that row and the price differs from it. A leg seen for the first
time in this process (no memory, e.g. after a restart) is due. The decision is
made from IN-MEMORY state only — ``{outcome_id: (probability, captured_at)}``
per consumer process — so a flush pays no extra read.

Only a row the flush's price UPDATE RETURNED is a candidate: the flush carries
the legs that ticked, and the UPDATE returns the ones it wrote. A leg that did
not tick is never written, which is what keeps "5 minutes" bounded. A price
equal to the leg's last point is never written again (the chart already holds
it), so a liveness re-stamp of an unchanged price adds nothing.

CAP. At most :data:`HISTORY_MAX_PER_MARKET_MINUTE` rows per market per minute.
Due legs over the cap are not written and keep no new memory, so they stay due
and the next flush that carries them writes them; the stalest legs go first so
a large board rotates instead of starving. Measured Nov 4 04:58Z (production,
Kalshi, ungraded legs whose committed price moved in the last minute): 405
markets, moved legs per market p50 1, p90 4, p99 44, max 96. 24 lets a 24-leg
board give every moving leg a point a minute and binds only the ~3% of moving
markets that are 40-500-leg ladders.

WHERE IT RUNS. Inside the flush's own transaction, after its price UPDATE and
re-rank, as ONE multi-row ``INSERT … SELECT`` per flush transaction (never one
per leg), ``captured_at`` = the row's returned ``last_updated`` — the
observation time the flush already stamps on its market invalidation. In a
SAVEPOINT where the session supports one, so a failed history insert costs the
history point and never the price. Memory and the per-market counts advance
only after the flush's COMMIT (:meth:`StreamHistoryPoints.committed`): a
rolled-back flush leaves every leg due.

NEVER FROM A PREVIEW. Market previews (``utils/market_preview``) and blend
previews (``tasks/live_blend_refresh``) publish a buffered price before the
write; they open no session here and never call this module. Only the
committed flush path does (``kalshi_ws.flush_prices``,
``polymarket_ws.write_chunk``).

SETTLED MEANS SETTLED. No point for a leg or market that has an answer:

* in memory — a market the consumer saw settle, a leg it saw graded, a
  returned row that is graded (``futures_liveness.leg_is_graded``) or wears a
  tier-3 settlement badge (the Kalshi flush's own ``_writable`` refusal), and a
  terminal 0/1 price;
* in SQL, in the INSERT itself — the same leg refusals plus
  ``futures_markets.status = 'resolved'``, so a resolution written by any other
  writer since this process last looked is refused too.

``ungradeable_result`` is a retraction, not a grade (#1852), so a retracted leg
that is streaming again (#11924) does get its chart.

KILL SWITCH. ``STREAM_HISTORY_POINTS`` (read when a consumer starts): unset or
``0`` = off (the default — see docs/live-settings.md for the measured cost),
``1``/``all`` = both sockets, or a comma list of venues (``kalshi``,
``polymarket``).

KEEP-ALIVE (Alex, Nov 4: "a flat stretch draws flat"). The socket writes a
price row only when the price CHANGES, so a leg that sat still never reaches
:meth:`StreamHistoryPoints.plan` and its chart showed a hole across a stretch
we were reading the whole time. :meth:`StreamHistoryPoints.keepalive_pass`
runs about once a minute from each consumer's stats loop, in its OWN session
and transaction (never inside a price flush, never under the flush lock): a
leg in the consumer's live population (the outcome ids its connected sockets
carry right now) whose last point is :data:`HISTORY_KEEPALIVE_S` (15 minutes)
old gets one point, at the leg's COMMITTED price — an ``INSERT … SELECT`` from
``futures_outcomes`` (:func:`keepalive_insert_statement`), so the point always
equals the stored price and never a buffer or preview value. Same settled
refusals as the move points (plus a ``settled_at`` market), same bookmaker,
same per-market-per-minute cap (keep-alive and move points share
``_market_minute``; stalest first), memory and counts advance only after its
COMMIT, and a failure is counted (``history_keepalive_errors``) and never
touches a price write.

"Last point" is this process's memory. A live leg with no memory (a restart)
is seeded ONCE from the database's newest ``futures_odds_snapshots`` row for
it (:func:`keepalive_seed_statement`: one ``ORDER BY captured_at DESC LIMIT
1`` probe per leg on ``idx_fos_outcome_captured``, at most
:data:`HISTORY_KEEPALIVE_SEED_BATCH` legs a pass); it is not due until seeded.
A live leg is never pruned from memory.

Its own switch, ``STREAM_HISTORY_KEEPALIVE`` (read when a consumer starts):
unset or ``0`` = off (the default), ``1``/``on`` = on — effective only for a
venue ``STREAM_HISTORY_POINTS`` turns on.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

STREAM_HISTORY_ENV = "STREAM_HISTORY_POINTS"
STREAM_HISTORY_VENUES = frozenset({"kalshi", "polymarket"})

#: A move of at least one point (0.01) since the leg's last stream point.
HISTORY_MOVE = 0.01
#: Or this long since that point, if the price differs from it.
HISTORY_INTERVAL_S = 300.0
#: Rows per market per (UTC) minute. See the module docstring for the measure.
HISTORY_MAX_PER_MARKET_MINUTE = 24
#: A leg not pointed for this long is forgotten (its next move is "first
#: sight", due anyway by the interval arm), so memory holds active legs only.
HISTORY_MEMORY_TTL_S = 3600.0
_PRUNE_EVERY = 1000
#: Float tolerance for the 1-point comparison (0.57 - 0.56 < 0.01 in floats).
_EPSILON = 1e-9

STREAM_HISTORY_KEEPALIVE_ENV = "STREAM_HISTORY_KEEPALIVE"
#: A live leg whose last point is at least this old gets a keep-alive point.
HISTORY_KEEPALIVE_S = 900.0
#: Rows one keep-alive pass may write (stalest first, after the per-market
#: cap). Bounds the statement; at one pass a minute it sustains a 15-minute
#: point for a live population of up to 15 x this many legs.
HISTORY_KEEPALIVE_MAX_PER_PASS = 5000
#: Live legs without memory seeded from the database in one pass.
HISTORY_KEEPALIVE_SEED_BATCH = 5000
#: Client-side bound on one whole pass (seed read + insert + commit).
HISTORY_KEEPALIVE_TIMEOUT_S = 30.0
#: Legs examined between yields to the event loop.
_KEEPALIVE_CHUNK = 4096

#: Counters this module adds to its consumer's minute line.
HISTORY_COUNTERS = (
    "history_points", "history_keepalive", "history_keepalive_errors",
    "history_capped", "history_skipped", "history_refused", "history_errors",
)


def stream_history_venues(raw: str | None) -> frozenset[str]:
    """Which sockets write history points, from the switch's raw value."""
    value = (raw or "").strip().lower()
    if value in ("", "0", "off", "false", "no", "none"):
        return frozenset()
    if value in ("1", "on", "true", "yes", "all"):
        return STREAM_HISTORY_VENUES
    return frozenset(
        part.strip() for part in value.split(",") if part.strip()
    ) & STREAM_HISTORY_VENUES


def stream_history_enabled(venue: str, environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return venue in stream_history_venues(env.get(STREAM_HISTORY_ENV))


def _keepalive_switch(environ: Mapping[str, str]) -> bool:
    value = (environ.get(STREAM_HISTORY_KEEPALIVE_ENV) or "").strip().lower()
    return value in ("1", "on", "true", "yes")


def stream_history_keepalive_enabled(
    venue: str, environ: Mapping[str, str] | None = None,
) -> bool:
    """The keep-alive runs for ``venue``: its own switch on AND the venue's
    ``STREAM_HISTORY_POINTS`` on."""
    env = os.environ if environ is None else environ
    return _keepalive_switch(env) and stream_history_enabled(venue, env)


@dataclass(frozen=True)
class HistoryPoint:
    outcome_id: int
    market_id: int
    probability: float
    yes_bid: float | None
    yes_ask: float | None
    captured_at: datetime


@dataclass
class HistoryPlan:
    """One flush transaction's due points; ``written`` once the INSERT ran."""

    points: list[HistoryPoint] = field(default_factory=list)
    capped: int = 0
    skipped: int = 0
    refused: int = 0
    written: set[int] = field(default_factory=set)
    failed: bool = False


@dataclass
class KeepalivePlan:
    """One keep-alive pass's due legs; ``written`` once its INSERT committed.

    ``legs``: ``(outcome_id, market_id)``, stalest first. ``written``:
    outcome_id → (stored probability, captured_at) the INSERT returned.
    ``reserved``: market → rows held against the cap in ``minute`` while the
    pass is in flight, so a flush in the same minute sees them.
    """

    at: datetime
    minute: int
    legs: list[tuple[int, int]] = field(default_factory=list)
    capped: int = 0
    seeded: int = 0
    written: dict[int, tuple[float, datetime]] = field(default_factory=dict)
    failed: bool = False
    reserved: dict[int, int] = field(default_factory=dict)


def _graded_row(row: Any) -> bool:
    """A returned row with an answer: graded, or a tier-3 settlement badge."""
    from app.utils.futures_liveness import leg_is_graded
    from app.utils.resolution_authority import AUTHORITATIVE_SOURCES

    is_winner = getattr(row, "is_winner", None)
    source = getattr(row, "resolution_source", None)
    return leg_is_graded(is_winner, source) or source in AUTHORITATIVE_SOURCES


def _quote(value: Any) -> tuple[float | None, float | None, float | None]:
    """(probability, bid, ask) from a buffered entry: a float or a tuple."""
    if isinstance(value, (tuple, list)):
        prob = value[0] if len(value) > 0 else None
        bid = value[1] if len(value) > 1 else None
        ask = value[2] if len(value) > 2 else None
        if bid is None or ask is None:
            bid = ask = None  # half a book is no quote (#8753)
        return prob, bid, ask
    return value, None, None


def _minute(at: datetime) -> int:
    return int(at.timestamp() // 60)


@lru_cache(maxsize=4)
def history_insert_statement(venue: str):
    """The flush's one multi-row INSERT of chart points, refusing settled rows.

    The SAME columns the polling writers fill (``venue_poll_30s.write_market``,
    ``futures_price_refresh._write_prices``): outcome, bookmaker (the venue),
    probability, American odds, the book, ``captured_at``; ``reading_count``
    takes its model default. One array per column, so one prepared statement
    serves every flush size. RETURNING the outcome ids it inserted, so memory
    advances only for rows that were really written.
    """
    from sqlalchemy import (
        ARRAY, DateTime, Integer, String, bindparam, cast, column, func, insert,
        literal, select,
    )

    from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.utils.kalshi_price_statement import _writable

    snap = FuturesOddsSnapshot.__table__
    outcomes = FuturesOutcome.__table__
    markets = FuturesMarket.__table__

    def array(name, type_):
        # Cast explicitly: a list of NULLs (no book) has no element type of
        # its own on every driver.
        return cast(bindparam(name, type_=ARRAY(type_)), ARRAY(type_))

    given = (
        func.unnest(
            array("history_outcome_ids", Integer()),
            array("history_probabilities", snap.c.probability.type),
            array("history_american_odds", Integer()),
            array("history_yes_bids", snap.c.yes_bid.type),
            array("history_yes_asks", snap.c.yes_ask.type),
            array("history_captured_at", DateTime(timezone=True)),
        )
        .table_valued(
            column("outcome_id", Integer),
            column("probability", snap.c.probability.type),
            column("american_odds", Integer),
            column("yes_bid", snap.c.yes_bid.type),
            column("yes_ask", snap.c.yes_ask.type),
            column("captured_at", DateTime(timezone=True)),
        )
        .render_derived(name="history_given")
    )
    rows = (
        select(
            given.c.outcome_id,
            cast(literal(venue), String(50)),
            given.c.probability,
            given.c.american_odds,
            given.c.yes_bid,
            given.c.yes_ask,
            given.c.captured_at,
        )
        .join_from(given, outcomes, outcomes.c.id == given.c.outcome_id)
        .join(markets, markets.c.id == outcomes.c.market_id)
        .where(
            # Settled means settled: no point for a graded leg, a tier-3
            # settled leg (the Kalshi flush's own refusal) or a resolved market.
            outcomes.c.is_winner.is_not(True),
            _writable(),
            markets.c.status.is_distinct_from("resolved"),
        )
    )
    return (
        insert(snap)
        .from_select(
            ["outcome_id", "bookmaker", "probability", "american_odds",
             "yes_bid", "yes_ask", "captured_at"],
            rows,
        )
        .returning(snap.c.outcome_id)
    )


def history_insert_parameters(points: Iterable[HistoryPoint]) -> dict[str, list]:
    from app.utils.odds_math import probability_to_american

    points = list(points)
    return {
        "history_outcome_ids": [p.outcome_id for p in points],
        "history_probabilities": [p.probability for p in points],
        "history_american_odds": [probability_to_american(p.probability) for p in points],
        "history_yes_bids": [p.yes_bid for p in points],
        "history_yes_asks": [p.yes_ask for p in points],
        "history_captured_at": [p.captured_at for p in points],
    }


def is_history_insert(stmt: Any) -> bool:
    """Is this statement a stream history INSERT (for rigs and guards)."""
    return any(stmt is history_insert_statement(v) for v in STREAM_HISTORY_VENUES)


@lru_cache(maxsize=4)
def keepalive_insert_statement(venue: str):
    """The keep-alive pass's one INSERT: each due leg's COMMITTED price.

    ``INSERT … SELECT`` from ``futures_outcomes`` for the due ids, so the
    point is the stored ``current_probability`` at the statement's snapshot —
    never a buffered or preview value. The same columns and bookmaker as
    :func:`history_insert_statement`; ``captured_at`` = the transaction's
    ``now()``. The book: Kalshi's stored book only when both sides are
    present and bracket the stored price (a price-only write leaves an older
    book behind, #8753); Polymarket's move points carry none, so neither does
    this. Refuses what the move INSERT refuses (graded, tier-3 settled,
    resolved market), plus a market with ``settled_at`` and any price that is
    not strictly inside (0, 1) — including NULL. RETURNING what it wrote.
    """
    from sqlalchemy import (
        ARRAY, Integer, Numeric, String, and_, any_, bindparam, case, cast, func,
        insert, literal, null, select,
    )

    from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.utils.kalshi_price_statement import _writable

    snap = FuturesOddsSnapshot.__table__
    outcomes = FuturesOutcome.__table__
    markets = FuturesMarket.__table__
    price = outcomes.c.current_probability
    # `probability_to_american`, in SQL, on plain NUMERIC (an untyped -100
    # would bind as the column's NUMERIC(7, 6) and overflow).
    p = cast(price, Numeric())
    one, hundred = literal(1, Integer()), literal(100, Integer())
    american = cast(
        func.round(case(
            (p >= literal(0.5, Numeric()), -hundred * p / (one - p)),
            else_=hundred * (one - p) / p,
        )),
        Integer(),
    )
    if venue == "kalshi":
        bid, ask = outcomes.c.current_yes_bid, outcomes.c.current_yes_ask
        book = and_(bid.is_not(None), ask.is_not(None), bid <= price, price <= ask)
        yes_bid = case((book, bid), else_=null())
        yes_ask = case((book, ask), else_=null())
    else:
        yes_bid = cast(null(), snap.c.yes_bid.type)
        yes_ask = cast(null(), snap.c.yes_ask.type)
    due = cast(bindparam("keepalive_outcome_ids", type_=ARRAY(Integer())), ARRAY(Integer()))
    rows = (
        select(
            outcomes.c.id,
            cast(literal(venue), String(50)),
            price,
            american,
            yes_bid,
            yes_ask,
            func.now(),
        )
        .join_from(outcomes, markets, markets.c.id == outcomes.c.market_id)
        .where(
            outcomes.c.id == any_(due),
            # Settled means settled — the move INSERT's refusals, and more.
            outcomes.c.is_winner.is_not(True),
            _writable(),
            markets.c.status.is_distinct_from("resolved"),
            markets.c.settled_at.is_(None),
            price > 0,
            price < 1,
        )
    )
    return (
        insert(snap)
        .from_select(
            ["outcome_id", "bookmaker", "probability", "american_odds",
             "yes_bid", "yes_ask", "captured_at"],
            rows,
        )
        .returning(snap.c.outcome_id, snap.c.probability, snap.c.captured_at)
    )


@lru_cache(maxsize=1)
def keepalive_seed_statement():
    """Each asked leg's newest chart point, for a leg this process has no
    memory of: one backward probe of ``idx_fos_outcome_captured``
    ``(outcome_id, captured_at)`` per leg (``ORDER BY captured_at DESC LIMIT
    1``), never a scan of the table. A leg with no row returns nothing."""
    from sqlalchemy import ARRAY, Integer, bindparam, cast, column, func, select, true

    from app.models.models import FuturesOddsSnapshot

    snap = FuturesOddsSnapshot.__table__
    asked = (
        func.unnest(cast(bindparam("keepalive_seed_ids", type_=ARRAY(Integer())),
                         ARRAY(Integer())))
        .table_valued(column("outcome_id", Integer))
        .render_derived(name="keepalive_seed")
    )
    latest = (
        select(snap.c.probability, snap.c.captured_at)
        .where(snap.c.outcome_id == asked.c.outcome_id, snap.c.captured_at.is_not(None))
        .order_by(snap.c.captured_at.desc())
        .limit(1)
        .lateral("keepalive_latest")
    )
    return (
        select(asked.c.outcome_id, latest.c.probability, latest.c.captured_at)
        .select_from(asked)
        .join(latest, true())
    )


def is_keepalive_statement(stmt: Any) -> bool:
    """A keep-alive pass's seed read or INSERT (for rigs and guards)."""
    return stmt is keepalive_seed_statement() or any(
        stmt is keepalive_insert_statement(v) for v in STREAM_HISTORY_VENUES
    )


class StreamHistoryPoints:
    """One consumer process's chart-point memory, rule and cap."""

    def __init__(
        self,
        venue: str,
        *,
        enabled: bool | None = None,
        refused_market: Callable[[int], bool] | None = None,
        max_per_market_minute: int = HISTORY_MAX_PER_MARKET_MINUTE,
        keepalive: bool | None = None,
    ) -> None:
        self.venue = venue
        self.enabled = stream_history_enabled(venue) if enabled is None else bool(enabled)
        #: The keep-alive pass: its own switch, and only where points are on.
        self.keepalive = self.enabled and (
            _keepalive_switch(os.environ) if keepalive is None else bool(keepalive)
        )
        self.max_per_market_minute = max_per_market_minute
        #: outcome_id → (probability, captured_at) of its last stream point.
        self.last_point: dict[int, tuple[float, datetime]] = {}
        #: market_id → (minute, rows written in it).
        self._market_minute: dict[int, tuple[int, int]] = {}
        #: market_id → (minute, rows an in-flight keep-alive pass holds).
        self._reserved: dict[int, tuple[int, int]] = {}
        #: The live population the last keep-alive pass saw: never pruned.
        self._live: frozenset[int] = frozenset()
        #: Live legs already seeded from the database (once each).
        self._seeded: set[int] = set()
        #: Legs the keep-alive INSERT refused, not asked again before this.
        self._keepalive_hold: dict[int, datetime] = {}
        self._refused_markets: set[int] = set()
        self._refused_outcomes: set[int] = set()
        self._refused_market = refused_market
        self._commits = 0
        self.stats: dict[str, int] = dict.fromkeys(HISTORY_COUNTERS, 0)

    # ── what the consumer saw settle ────────────────────────────────────────

    def refuse_market(self, market_id: int) -> None:
        self._refused_markets.add(market_id)

    def refuse_outcome(self, outcome_id: int) -> None:
        self._refused_outcomes.add(outcome_id)
        self.last_point.pop(outcome_id, None)

    def _refused(self, row: Any) -> bool:
        market_id = getattr(row, "market_id", None)
        if row.id in self._refused_outcomes or market_id in self._refused_markets:
            return True
        if self._refused_market is not None and market_id is not None:
            try:
                if self._refused_market(market_id):
                    return True
            except Exception:  # noqa: BLE001 — refusing is the safe answer
                return True
        return _graded_row(row)

    # ── the rule ────────────────────────────────────────────────────────────

    def due(self, outcome_id: int, probability: float, at: datetime) -> bool:
        last = self.last_point.get(outcome_id)
        if last is None:
            return True
        last_p, last_at = last
        if probability == last_p:
            return False
        if abs(probability - last_p) >= HISTORY_MOVE - _EPSILON:
            return True
        return (at - last_at).total_seconds() >= HISTORY_INTERVAL_S

    def _committed_used(self, market_id: int, minute: int) -> int:
        held = self._market_minute.get(market_id)
        return held[1] if held is not None and held[0] == minute else 0

    def _used(self, market_id: int, minute: int) -> int:
        """Rows the market has spent in ``minute``: committed, plus those an
        in-flight keep-alive pass holds (the two kinds share one cap)."""
        held = self._reserved.get(market_id)
        reserved = held[1] if held is not None and held[0] == minute else 0
        return self._committed_used(market_id, minute) + reserved

    def plan(self, rows: Iterable[Any], quotes: Mapping[int, Any]) -> HistoryPlan:
        """The due, capped points among the rows a price UPDATE returned.

        ``rows``: RETURNING rows (``id``, ``market_id``, ``last_updated``, and
        when present ``current_probability``/``is_winner``/
        ``resolution_source``; Polymarket's ``skipped`` rows are held back,
        not written). ``quotes``: the batch the UPDATE wrote, ``{outcome_id:
        probability}`` or ``{outcome_id: (probability, bid, ask)}``.
        """
        plan = HistoryPlan()
        if not self.enabled:
            return plan
        by_market: dict[int, dict[int, HistoryPoint]] = {}
        for row in rows:
            if getattr(row, "skipped", False):
                continue
            at = getattr(row, "last_updated", None)
            market_id = getattr(row, "market_id", None)
            if at is None or market_id is None:
                continue
            if self._refused(row):
                plan.refused += 1
                continue
            prob, bid, ask = _quote(quotes.get(row.id))
            if prob is None:
                prob = getattr(row, "current_probability", None)
            if prob is None:
                continue
            prob = round(float(prob), 6)  # the stored NUMERIC(7, 6)
            if not 0 < prob < 1:
                plan.refused += 1  # a terminal price is settlement's to write
                continue
            if not self.due(row.id, prob, at):
                plan.skipped += 1
                continue
            by_market.setdefault(market_id, {})[row.id] = HistoryPoint(
                row.id, market_id, prob,
                None if bid is None else float(bid),
                None if ask is None else float(ask),
                at,
            )
        for market_id, points in by_market.items():
            ordered = sorted(
                points.values(),
                # Stalest first: a never-pointed leg, then the oldest point.
                key=lambda p: (
                    p.outcome_id in self.last_point,
                    self.last_point[p.outcome_id][1].timestamp()
                    if p.outcome_id in self.last_point else 0.0,
                ),
            )
            room = max(
                self.max_per_market_minute
                - self._used(market_id, _minute(ordered[0].captured_at)),
                0,
            )
            plan.points.extend(ordered[:room])
            plan.capped += max(len(ordered) - room, 0)
        return plan

    # ── the write, inside the flush's transaction ───────────────────────────

    async def write(self, session: Any, plan: HistoryPlan | None) -> None:
        """Run the plan's one INSERT in the flush's open transaction.

        In a SAVEPOINT when the session offers one: a failed insert is counted
        and dropped (its legs stay due) and the price write carries on. A
        session without savepoints (a rig) runs it bare.
        """
        if plan is None or not plan.points or not self.enabled:
            return
        statement = history_insert_statement(self.venue)
        parameters = history_insert_parameters(plan.points)
        nested = getattr(session, "begin_nested", None)
        if not callable(nested):
            result = await session.execute(statement, parameters)
            plan.written = {row[0] for row in result.all()}
            return
        try:
            async with nested():
                result = await session.execute(statement, parameters)
                plan.written = {row[0] for row in result.all()}
        except Exception:  # noqa: BLE001 — a chart point never costs a price
            plan.written = set()
            plan.failed = True
            logger.warning(
                "%s stream history: insert of %d points failed; the price "
                "write continues and the legs stay due",
                self.venue, len(plan.points), exc_info=True,
            )

    def committed(self, plan: HistoryPlan | None) -> None:
        """The flush's transaction COMMITTED: advance memory and the counts.

        Never called for a rolled-back transaction, so its legs stay due.
        """
        if plan is None:
            return
        stats = self.stats
        stats["history_capped"] += plan.capped
        stats["history_skipped"] += plan.skipped
        stats["history_refused"] += plan.refused
        if plan.failed:
            stats["history_errors"] += 1
        written = 0
        for point in plan.points:
            if point.outcome_id not in plan.written:
                # The INSERT's own refusal (settled since this process looked).
                stats["history_refused"] += 1
                continue
            written += 1
            self.last_point[point.outcome_id] = (point.probability, point.captured_at)
            minute = _minute(point.captured_at)
            self._market_minute[point.market_id] = (
                minute, self._committed_used(point.market_id, minute) + 1,
            )
        stats["history_points"] += written
        self._commits += 1
        if self._commits % _PRUNE_EVERY == 0 and plan.points:
            self._prune(plan.points[0].captured_at)

    def _prune(self, now: datetime) -> None:
        horizon = now.timestamp() - HISTORY_MEMORY_TTL_S
        live = self._live  # a leg we are still reading is never forgotten
        for oid in [
            o for o, (_p, at) in self.last_point.items()
            if at.timestamp() < horizon and o not in live
        ]:
            del self.last_point[oid]
        minute = _minute(now)
        for mid in [m for m, (mm, _n) in self._market_minute.items() if mm < minute]:
            del self._market_minute[mid]
        for oid in [o for o, until in self._keepalive_hold.items() if until <= now]:
            del self._keepalive_hold[oid]

    # ── the keep-alive: a flat stretch draws flat ───────────────────────────

    def keepalive_due(self, outcome_id: int, at: datetime) -> bool:
        """A live leg whose last point is :data:`HISTORY_KEEPALIVE_S` old.

        The price is NOT compared: an unchanged price is exactly the case.
        A leg with no memory is due only once it was seeded (and the database
        had no point for it); before that it waits for its seed.
        """
        hold = self._keepalive_hold.get(outcome_id)
        if hold is not None and at < hold:
            return False
        last = self.last_point.get(outcome_id)
        if last is None:
            return outcome_id in self._seeded
        return (at - last[1]).total_seconds() >= HISTORY_KEEPALIVE_S

    def keepalive_seed_ids(self, live: Iterable[int]) -> list[int]:
        """Live legs with no memory and no seed yet, at most one batch."""
        out: list[int] = []
        for oid in live:
            if (oid in self.last_point or oid in self._seeded
                    or oid in self._refused_outcomes):
                continue
            out.append(oid)
            if len(out) >= HISTORY_KEEPALIVE_SEED_BATCH:
                break
        return out

    def keepalive_seeded(self, asked: Iterable[int], rows: Iterable[Any]) -> int:
        """Memory from the seed read; every asked leg is seeded, found or not.

        A newer point this process wrote meanwhile is kept.
        """
        found = 0
        for oid, prob, at in rows:
            if prob is None or at is None:
                continue
            found += 1
            held = self.last_point.get(oid)
            if held is None or held[1] < at:
                self.last_point[oid] = (round(float(prob), 6), at)
        self._seeded.update(asked)
        return found

    def _keepalive_refused(self, oid: int, market_id: int, cache: dict[int, bool]) -> bool:
        if oid in self._refused_outcomes or market_id in self._refused_markets:
            return True
        if self._refused_market is None:
            return False
        refused = cache.get(market_id)
        if refused is None:
            try:
                refused = bool(self._refused_market(market_id))
            except Exception:  # noqa: BLE001 — refusing is the safe answer
                refused = True
            cache[market_id] = refused
        return refused

    def _keepalive_collect(
        self, legs: Iterable[tuple[int, int]], at: datetime,
        due: dict[int, list[tuple[float, int]]], cache: dict[int, bool],
    ) -> None:
        for oid, market_id in legs:
            if self._keepalive_refused(oid, market_id, cache):
                continue
            if not self.keepalive_due(oid, at):
                continue
            last = self.last_point.get(oid)
            # Stalest first: never pointed, then the oldest point.
            age = float("inf") if last is None else (at - last[1]).total_seconds()
            due.setdefault(market_id, []).append((age, oid))

    def _keepalive_select(
        self, plan: KeepalivePlan, due: dict[int, list[tuple[float, int]]],
    ) -> KeepalivePlan:
        chosen: list[tuple[float, int, int]] = []
        for market_id, legs in due.items():
            legs.sort(key=lambda leg: (-leg[0], leg[1]))
            room = max(self.max_per_market_minute - self._used(market_id, plan.minute), 0)
            chosen.extend((age, oid, market_id) for age, oid in legs[:room])
            plan.capped += max(len(legs) - room, 0)
        chosen.sort(key=lambda leg: (-leg[0], leg[1]))
        plan.capped += max(len(chosen) - HISTORY_KEEPALIVE_MAX_PER_PASS, 0)
        plan.legs = [(oid, market_id) for _age, oid, market_id
                     in chosen[:HISTORY_KEEPALIVE_MAX_PER_PASS]]
        for _oid, market_id in plan.legs:
            plan.reserved[market_id] = plan.reserved.get(market_id, 0) + 1
        for market_id, n in plan.reserved.items():
            held = self._reserved.get(market_id)
            before = held[1] if held is not None and held[0] == plan.minute else 0
            self._reserved[market_id] = (plan.minute, before + n)
        return plan

    def keepalive_plan(
        self, legs: Iterable[tuple[int, int]], at: datetime,
    ) -> KeepalivePlan:
        """The due, capped legs among ``legs`` (``(outcome_id, market_id)``).

        Reserves their cap rows until :meth:`keepalive_committed` or
        :meth:`keepalive_release`.
        """
        plan = KeepalivePlan(at=at, minute=_minute(at))
        if not self.keepalive:
            return plan
        due: dict[int, list[tuple[float, int]]] = {}
        self._keepalive_collect(dict(legs).items(), at, due, {})
        return self._keepalive_select(plan, due)

    def keepalive_release(self, plan: KeepalivePlan | None) -> None:
        """Give back an in-flight pass's cap rows (idempotent)."""
        if plan is None:
            return
        for market_id, n in plan.reserved.items():
            held = self._reserved.get(market_id)
            if held is None or held[0] != plan.minute:
                continue
            left = held[1] - n
            if left > 0:
                self._reserved[market_id] = (held[0], left)
            else:
                del self._reserved[market_id]
        plan.reserved = {}

    def keepalive_committed(self, plan: KeepalivePlan) -> None:
        """The pass's transaction COMMITTED: advance memory and the counts."""
        self.keepalive_release(plan)
        stats = self.stats
        stats["history_capped"] += plan.capped
        written = 0
        for oid, market_id in plan.legs:
            got = plan.written.get(oid)
            if got is None:
                # The INSERT's own refusal (settled, terminal or no price):
                # not asked again for one keep-alive interval.
                stats["history_refused"] += 1
                self._keepalive_hold[oid] = plan.at + timedelta(seconds=HISTORY_KEEPALIVE_S)
                continue
            written += 1
            prob, at = got
            held = self.last_point.get(oid)
            if held is None or held[1] <= at:
                self.last_point[oid] = (prob, at)
            minute = _minute(at)
            self._market_minute[market_id] = (
                minute, self._committed_used(market_id, minute) + 1,
            )
        stats["history_keepalive"] += written

    async def keepalive_pass(
        self,
        session_factory: Callable[[], Any],
        legs: Iterable[tuple[int, int]],
        *,
        now: Callable[[], datetime] | None = None,
        timeout_s: float = HISTORY_KEEPALIVE_TIMEOUT_S,
    ) -> KeepalivePlan | None:
        """One keep-alive pass over the live population, in its own session.

        ``legs``: ``(outcome_id, market_id)`` the consumer's connected sockets
        carry now. Seeds memory-less legs (one bounded read), plans the due
        legs, runs ONE ``INSERT … SELECT`` and COMMITs; memory and counts
        advance only after that commit. Any failure — the read, the insert,
        the commit, or the ``timeout_s`` bound — is counted in
        ``history_keepalive_errors`` and logged; it never raises (except
        cancellation) and never touches a price write.
        """
        if not self.keepalive:
            return None
        population = dict(legs)
        self._live = frozenset(population)
        self._seeded.intersection_update(self._live)
        holder: list[KeepalivePlan] = []
        try:
            return await asyncio.wait_for(
                self._keepalive_pass(session_factory, population, now, holder),
                timeout_s,
            )
        except Exception:  # noqa: BLE001 — a chart point never costs a price
            self.stats["history_keepalive_errors"] += 1
            if holder:
                holder[0].failed = True
            logger.warning(
                "%s stream history keep-alive: pass over %d live legs failed; "
                "no price write is affected and the legs stay due",
                self.venue, len(population), exc_info=True,
            )
            return holder[0] if holder else None
        finally:
            if holder:
                self.keepalive_release(holder[0])

    async def _keepalive_pass(self, session_factory, population, now, holder):
        clock = now or (lambda: datetime.now(timezone.utc))
        async with session_factory() as session:
            seed = self.keepalive_seed_ids(population)
            seeded = 0
            if seed:
                result = await session.execute(
                    keepalive_seed_statement(), {"keepalive_seed_ids": seed},
                )
                seeded = self.keepalive_seeded(seed, result.all())
            at = clock()
            plan = KeepalivePlan(at=at, minute=_minute(at), seeded=seeded)
            due: dict[int, list[tuple[float, int]]] = {}
            cache: dict[int, bool] = {}
            items = list(population.items())
            for start in range(0, len(items), _KEEPALIVE_CHUNK):
                if start:
                    await asyncio.sleep(0)  # never hold the socket's loop
                self._keepalive_collect(items[start:start + _KEEPALIVE_CHUNK], at, due, cache)
            self._keepalive_select(plan, due)
            holder.append(plan)
            if not plan.legs:
                return plan
            result = await session.execute(
                keepalive_insert_statement(self.venue),
                {"keepalive_outcome_ids": [oid for oid, _mid in plan.legs]},
            )
            written = {
                row[0]: (round(float(row[1]), 6), row[2]) for row in result.all()
            }
            await session.commit()
            # Committed: nothing awaits between here and the memory update.
            plan.written = written
            self.keepalive_committed(plan)
            return plan

    def line_fields(self) -> dict[str, int]:
        return dict(self.stats)
