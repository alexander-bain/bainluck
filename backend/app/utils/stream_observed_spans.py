"""#11929 Decide 27-B (Alex, Nov 5): observed spans — record a span, not a row.

PILLAR: TRUTH. SHIP: a market we were reading the whole time never shows a
hole. The per-row keep-alive (``stream_history_points.keepalive_pass``) writes
one chart point per live leg every 15 minutes; measured on Nov 4 it held only
about 32 minutes on Kalshi (about 105k live legs against a pass that holds
about 75k) and cost about 3.3M rows a day. A span says the same thing once:
"this leg was observed on a live connection from ``started_at`` to
``ended_at``". ``/history`` draws the stretch flat at serve time (PR 2), so web
and iPhone need no client change. This module is the WRITER only; nothing
reads ``stream_observed_spans`` until the serve PR lands.

WHAT A SPAN CLAIMS, AND WHY IT IS ENOUGH. Only that the leg was in a
connection's live population for the whole stretch. "Price unchanged" is
derived at serve time from the points: the move writer
(``StreamHistoryPoints.plan``) writes a point on any 1-point move, and on ANY
difference once the last point is 5 minutes old (``HISTORY_INTERVAL_S``). So
between two consecutive points inside a span the price sat at the earlier
point's value, to the chart's own resolution. A move therefore ends a flat
stretch at serve time without ending the stored span; storing a new span per
move would cost one row per move, which is what the keep-alive cost.

ALEX'S CONDITION: A SILENT CONNECTION NEVER PRINTS "UNCHANGED". The live
population a consumer passes to :meth:`ObservedSpans.tick` holds only legs on
a connection that is connected, subscribed AND received a message within
:data:`SPAN_LIFE_S`. A leg that leaves it — disconnect, unsubscribe, silence,
or a consumer run ending — closes at the last tick it was seen alive. A
subscription the venue dropped without telling us goes quiet, so its legs
close within a few minutes instead of claiming flat.

HOW IT IS STORED. One row per span. Opened at the first tick a leg is seen
alive (``ended_at`` NULL), closed once with an UPDATE when it leaves. An open
span's end is the venue's heartbeat (``stream_span_heartbeats.beat_at``),
written in the same transaction as every tick, so a reader never extends an
open span past the last tick that saw its leg alive. A consumer that died
without closing leaves open rows; :meth:`ObservedSpans.recover` closes them at
the heartbeat when the next run starts. Ticks run about once a minute, in their
own session and transaction, outside every flush, bounded by
:data:`SPAN_TICK_TIMEOUT_S`; a failure is counted and logged and never touches
a price write.

SWITCH. ``STREAM_OBSERVED_SPANS`` (read when a consumer run starts), the same
grammar as ``STREAM_HISTORY_POINTS``: unset/``0`` = off (the default),
``1``/``all`` = both sockets, or a comma list. Effective only for a venue whose
move points are on: without points there is no "unchanged" to derive.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from app.utils.stream_history_points import stream_history_enabled, stream_history_venues

logger = logging.getLogger(__name__)

STREAM_OBSERVED_SPANS_ENV = "STREAM_OBSERVED_SPANS"
#: A connection with no message for this long is silent: its legs leave the
#: live population and their spans close (Alex: "any message within a few
#: minutes").
SPAN_LIFE_S = 180.0
#: Client-side bound on one tick (inserts + closes + heartbeat + commit).
SPAN_TICK_TIMEOUT_S = 30.0
#: Rows per statement.
SPAN_CHUNK = 5000

END_LEFT = "left"          # disconnect, unsubscribe or silence
END_RUN = "run_end"        # the consumer run ended (recycle, shutdown)
END_RECOVERED = "recovered"  # closed at the heartbeat by the next run

SPAN_COUNTERS = (
    "spans_open", "spans_opened", "spans_closed", "spans_errors",
)


def stream_spans_enabled(venue: str, environ: Mapping[str, str] | None = None) -> bool:
    """Spans for ``venue``: its own switch names it AND its move points are on."""
    env = os.environ if environ is None else environ
    return (
        venue in stream_history_venues(env.get(STREAM_OBSERVED_SPANS_ENV))
        and stream_history_enabled(venue, env)
    )


@dataclass
class SpanPlan:
    """One tick: legs opening at ``at``, spans closing, all in one transaction."""

    at: datetime
    opens: list[int] = field(default_factory=list)
    # (span_id, outcome_id, ended_at)
    closes: list[tuple[int, int, datetime]] = field(default_factory=list)
    reason: str = END_LEFT


@lru_cache(maxsize=1)
def open_statement():
    from sqlalchemy import text

    return text(
        "INSERT INTO stream_observed_spans (venue, outcome_id, started_at) "
        "SELECT CAST(:venue AS text), ids.oid, CAST(:at AS timestamptz) "
        "FROM unnest(CAST(:ids AS integer[])) AS ids(oid) "
        "RETURNING id, outcome_id"
    )


@lru_cache(maxsize=1)
def close_statement():
    from sqlalchemy import text

    # `ended_at IS NULL`: a span closes once. GREATEST: never before it began.
    return text(
        "UPDATE stream_observed_spans AS s "
        "SET ended_at = GREATEST(s.started_at, v.ended_at), end_reason = CAST(:reason AS text) "
        "FROM unnest(CAST(:span_ids AS bigint[]), CAST(:ended AS timestamptz[])) "
        "AS v(span_id, ended_at) "
        "WHERE s.id = v.span_id AND s.ended_at IS NULL"
    )


@lru_cache(maxsize=1)
def heartbeat_statement():
    from sqlalchemy import text

    return text(
        "INSERT INTO stream_span_heartbeats (venue, beat_at) "
        "VALUES (CAST(:venue AS text), CAST(:at AS timestamptz)) "
        "ON CONFLICT (venue) DO UPDATE SET beat_at = EXCLUDED.beat_at"
    )


@lru_cache(maxsize=1)
def recover_statement():
    from sqlalchemy import text

    # A span left open by a run that never closed it ends at the last tick
    # that saw anything alive for this venue (its heartbeat), never later.
    return text(
        "UPDATE stream_observed_spans AS s "
        "SET ended_at = GREATEST(s.started_at, COALESCE(h.beat_at, s.started_at)), "
        "end_reason = CAST(:reason AS text) "
        "FROM (SELECT CAST(:venue AS text) AS venue) AS v "
        "LEFT JOIN stream_span_heartbeats AS h ON h.venue = v.venue "
        "WHERE s.venue = v.venue AND s.ended_at IS NULL"
    )


class ObservedSpans:
    """One consumer run's spans for one venue (see the module docstring)."""

    def __init__(self, venue: str, *, environ: Mapping[str, str] | None = None) -> None:
        self.venue = venue
        self.enabled = stream_spans_enabled(venue, environ)
        # outcome_id -> [span_id, started_at, last_seen]
        self.open: dict[int, list[Any]] = {}
        # Closes whose UPDATE has not committed yet, retried next tick.
        self._pending_closes: list[tuple[int, int, datetime]] = []
        self.stats: dict[str, int] = dict.fromkeys(SPAN_COUNTERS, 0)

    # ── the pure part: who opens, who closes ────────────────────────────────

    def plan(self, alive: Iterable[int], at: datetime) -> SpanPlan:
        """Opens for newly alive legs, closes for legs that left; extends the rest.

        Extension is memory-only (``last_seen``): an open row needs no write
        until it closes, and the heartbeat bounds it meanwhile.
        """
        live = set(alive)
        plan = SpanPlan(at=at, closes=list(self._pending_closes))
        for oid, held in self.open.items():
            if oid in live:
                held[2] = at
            else:
                plan.closes.append((held[0], oid, held[2]))
        plan.opens = sorted(oid for oid in live if oid not in self.open)
        return plan

    def committed(self, plan: SpanPlan, opened: Iterable[tuple[int, int]]) -> None:
        """Memory after the tick's COMMIT: opened rows recorded, closes forgotten."""
        for span_id, oid, _ended in plan.closes:
            held = self.open.get(oid)
            if held is not None and held[0] == span_id:
                del self.open[oid]
        n_opened = 0
        for span_id, oid in opened:
            self.open[oid] = [span_id, plan.at, plan.at]
            n_opened += 1
        self._pending_closes = []
        self.stats["spans_opened"] += n_opened
        self.stats["spans_closed"] += len(plan.closes)
        self.stats["spans_open"] = len(self.open)

    def failed(self, plan: SpanPlan) -> None:
        """The tick rolled back: opens retry next tick; closes are held for it."""
        self.stats["spans_errors"] += 1
        held = {span_id for span_id, _oid, _ended in self._pending_closes}
        for close in plan.closes:
            if close[0] not in held:
                self._pending_closes.append(close)
                held.add(close[0])
        for _span_id, oid, _ended in plan.closes:
            self.open.pop(oid, None)

    # ── the writes ──────────────────────────────────────────────────────────

    async def _write(self, session: Any, plan: SpanPlan) -> list[tuple[int, int]]:
        opened: list[tuple[int, int]] = []
        for start in range(0, len(plan.opens), SPAN_CHUNK):
            chunk = plan.opens[start:start + SPAN_CHUNK]
            result = await session.execute(
                open_statement(), {"venue": self.venue, "at": plan.at, "ids": chunk},
            )
            opened.extend((int(row[0]), int(row[1])) for row in result.all())
        for start in range(0, len(plan.closes), SPAN_CHUNK):
            chunk = plan.closes[start:start + SPAN_CHUNK]
            await session.execute(
                close_statement(),
                {
                    "reason": plan.reason,
                    "span_ids": [span_id for span_id, _oid, _ended in chunk],
                    "ended": [ended for _span_id, _oid, ended in chunk],
                },
            )
        await session.execute(heartbeat_statement(), {"venue": self.venue, "at": plan.at})
        return opened

    async def tick(
        self,
        session_factory: Callable[[], Any],
        alive: Iterable[int],
        *,
        now: Callable[[], datetime] | None = None,
        timeout_s: float = SPAN_TICK_TIMEOUT_S,
    ) -> SpanPlan | None:
        """One tick over the live population, in its own session.

        Never raises except cancellation; a failure is counted and logged and
        the tick's opens and closes are retried by the next one.
        """
        if not self.enabled:
            return None
        clock = now or (lambda: datetime.now(timezone.utc))
        plan = self.plan(alive, clock())
        try:
            # `asyncio.timeout`, never `wait_for` (#11992: on 3.11 `wait_for`
            # can swallow a cancel landing as the inner call finishes).
            async with asyncio.timeout(timeout_s):
                async with session_factory() as session:
                    opened = await self._write(session, plan)
                    await session.commit()
        except Exception:  # noqa: BLE001 — a span never costs a price
            self.failed(plan)
            logger.warning(
                "%s observed spans: tick over %d open legs failed; no price write "
                "is affected", self.venue, len(self.open), exc_info=True,
            )
            return plan
        self.committed(plan, opened)
        return plan

    async def close_all(
        self,
        session_factory: Callable[[], Any],
        *,
        reason: str = END_RUN,
        timeout_s: float = SPAN_TICK_TIMEOUT_S,
    ) -> int:
        """The run is ending: every open span closes at its last tick alive."""
        if not self.enabled or not (self.open or self._pending_closes):
            return 0
        plan = SpanPlan(
            at=datetime.now(timezone.utc),
            closes=list(self._pending_closes) + [
                (held[0], oid, held[2]) for oid, held in self.open.items()
            ],
            reason=reason,
        )
        try:
            async with asyncio.timeout(timeout_s):
                async with session_factory() as session:
                    for start in range(0, len(plan.closes), SPAN_CHUNK):
                        chunk = plan.closes[start:start + SPAN_CHUNK]
                        await session.execute(
                            close_statement(),
                            {
                                "reason": reason,
                                "span_ids": [s for s, _o, _e in chunk],
                                "ended": [e for _s, _o, e in chunk],
                            },
                        )
                    await session.commit()
        except Exception:  # noqa: BLE001 — the next run's recover() closes them
            self.stats["spans_errors"] += 1
            logger.warning(
                "%s observed spans: closing %d spans at run end failed; the next "
                "run closes them at the heartbeat", self.venue, len(plan.closes),
                exc_info=True,
            )
            return 0
        self.committed(plan, ())
        return len(plan.closes)

    async def recover(
        self, session_factory: Callable[[], Any], *, timeout_s: float = SPAN_TICK_TIMEOUT_S,
    ) -> int:
        """Run start: close this venue's spans a dead run left open, at its heartbeat."""
        if not self.enabled:
            return 0
        try:
            async with asyncio.timeout(timeout_s):
                async with session_factory() as session:
                    result = await session.execute(
                        recover_statement(), {"venue": self.venue, "reason": END_RECOVERED},
                    )
                    await session.commit()
        except Exception:  # noqa: BLE001 — never blocks the consumer starting
            self.stats["spans_errors"] += 1
            logger.warning(
                "%s observed spans: recovering open spans failed", self.venue,
                exc_info=True,
            )
            return 0
        return int(getattr(result, "rowcount", 0) or 0)

    def line(self) -> str:
        """The minute's own log line fields (kept off the consumer's long line)."""
        return " ".join(f"{k}={self.stats[k]}" for k in SPAN_COUNTERS)
