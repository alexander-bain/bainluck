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
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
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

#: Counters this module adds to its consumer's minute line.
HISTORY_COUNTERS = (
    "history_points", "history_capped", "history_skipped", "history_refused",
    "history_errors",
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


class StreamHistoryPoints:
    """One consumer process's chart-point memory, rule and cap."""

    def __init__(
        self,
        venue: str,
        *,
        enabled: bool | None = None,
        refused_market: Callable[[int], bool] | None = None,
        max_per_market_minute: int = HISTORY_MAX_PER_MARKET_MINUTE,
    ) -> None:
        self.venue = venue
        self.enabled = stream_history_enabled(venue) if enabled is None else bool(enabled)
        self.max_per_market_minute = max_per_market_minute
        #: outcome_id → (probability, captured_at) of its last stream point.
        self.last_point: dict[int, tuple[float, datetime]] = {}
        #: market_id → (minute, rows written in it).
        self._market_minute: dict[int, tuple[int, int]] = {}
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

    def _used(self, market_id: int, minute: int) -> int:
        held = self._market_minute.get(market_id)
        return held[1] if held is not None and held[0] == minute else 0

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
                minute, self._used(point.market_id, minute) + 1,
            )
        stats["history_points"] += written
        self._commits += 1
        if self._commits % _PRUNE_EVERY == 0 and plan.points:
            self._prune(plan.points[0].captured_at)

    def _prune(self, now: datetime) -> None:
        horizon = now.timestamp() - HISTORY_MEMORY_TTL_S
        for oid in [o for o, (_p, at) in self.last_point.items() if at.timestamp() < horizon]:
            del self.last_point[oid]
        minute = _minute(now)
        for mid in [m for m, (mm, _n) in self._market_minute.items() if mm < minute]:
            del self._market_minute[mid]

    def line_fields(self) -> dict[str, int]:
        return dict(self.stats)
