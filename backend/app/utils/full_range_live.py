"""#683 — ``range=full``'s LIVE arm: our own captures older than the ``hours`` window.

A client's "Full" sends ``hours`` (its own floor, which an older server serves)
plus ``range=full``. The archive arm already reads the question's whole stored
lifetime under that flag (``kalshi_archive_reader`` rule 6). This is the same
promise for the captures we took ourselves, which are the evidence the archive
must YIELD to: Root executed the earlier cut on a 189-day specimen and found its
two live captures drawn at ``hours=4800`` and GONE at the web's real Full request
(``hours=4320&range=full``), with archive intervals painted over the span they
had claimed. A Full chart that shows less of our own evidence than a wide
ordinary window is not Full.

THE RULES
1. **The window starts where the evidence does.** Nothing here assumes a
   ``created_at``, a listing date or a day constant: the read asks the store for
   every capture instant older than the route's own ``hours`` cutoff, and the
   chart then begins at the first one it draws.
2. **Whole instants, never partial columns.** The routes de-vig and blend a
   column per instant (#4992), so a bound that cut some legs out of an instant
   would print a different scale, not a thinner line. Rows are read by INSTANT.
3. **Bounded, and says so.** At most :data:`OLDER_LIVE_INSTANT_CAP` instants
   are read. Past it the older span is read as a rank-stride skeleton keeping
   the first and last instant (the archive arm's span-keeping rule), and the
   response says ``live_thinned``. Never tail-cut: the oldest capture is the one
   a Full chart exists to reach.
4. **Live keeps its precedence over what it actually holds, and nothing
   more.** Unthinned, the rows read ARE the claims, exactly as in the ordinary
   window. Thinned, the skipped instants still exist, so before the archive and
   venue arms are served each of their CANDIDATES is asked of the store
   directly (:meth:`OlderLive.archive_claims`, :meth:`OlderLive.withhold_venue`):
   does a supported capture of the SAME outcome lie inside this interval
   (``[interval_start, interval_end]``, the archive rule's own overlap) or
   within the capture claim of this venue instant? Only an actual capture says
   yes. Root executed the earlier cut, which read each outcome's presence as
   ``lo..hi`` spans over rank buckets, on the real 2,000-instant cap: one
   skipped instant four hours from the dense run stretched a span across the
   empty hours between and erased a valid archive interval no capture touched.
   A thinned read never claims an empty gap, so an interval between two
   captures stands exactly as it does unthinned. The same holds for the two
   SEAT rules applied after it (:meth:`OlderLive.instant_claims`): the combined
   chart's merged instant, which any outcome on the same question holds (the
   reviewer's CERT-4139 witness: a skipped Polymarket twin capture at the
   archive close), and the timeline's bucket start, which the outcome's own
   capture cell holds.
5. **Out of budget is UNKNOWN, never a capture.** Admission reads at most
   ``sum(ADMIT_ROUND_LIMITS)`` rows per window. A window whose budget runs out
   on rows the support filter refuses has an unread remainder that may hold a
   supported capture, so it is neither claimed nor cleared: it is answered
   :class:`Unresolved`, carrying its own window and no instant. Every arm
   withholds that candidate (an archive interval, a venue point, a seat) fail
   closed — a possibly supported capture is never painted over — and states
   it separately from what live actually claimed, so the reader is told its
   history is partial. CERT-4141 executed the earlier cut, which answered
   with a synthetic capture at the window's start: it was counted as live
   ownership, and because archive overlap is inclusive it also erased the
   PRECEDING interval, which ends at that instant and which nothing touched.
6. **Explicit short ranges are untouched.** Nothing here runs without
   ``range=full``; every other request issues exactly today's statements.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional, Sequence

from sqlalchemy import select, text

logger = logging.getLogger(__name__)

#: Capture instants older than the ``hours`` window read under ``range=full``.
#: Sized against what the clients' Full ALREADY reads: the web sends
#: ``hours=4320`` (180 days), which at the futures poll's ~78-minute cadence is
#: ~3,300 instants read densely today. 2,000 more keeps a Full response within
#: the same order as today's widest one however old the question is.
OLDER_LIVE_INSTANT_CAP = 2000

#: The ``window_start_basis`` answer when our own first capture opens the chart.
BASIS_LIVE = "live_first_capture"

#: Every capture instant older than ``:before`` for these outcomes, rank-strided
#: to at most ``:cap + 2`` (both ends kept). ``n`` is the true instant count.
_INSTANTS_SQL = text(
    """
    SELECT s.captured_at, s.n
    FROM (
        SELECT d.captured_at,
               row_number() OVER (ORDER BY d.captured_at) AS rn,
               count(*) OVER () AS n
        FROM (
            SELECT DISTINCT captured_at
            FROM futures_odds_snapshots
            WHERE outcome_id = ANY(CAST(:ids AS integer[]))
              AND captured_at < :before
        ) d
    ) s
    WHERE s.rn = 1 OR s.rn = s.n
       OR (s.rn - 1) % GREATEST(1, CEIL(s.n::numeric / :cap)::integer) = 0
    ORDER BY s.captured_at
    """
)

#: Thinned only (rule 4): per candidate window ``w`` = (outcome, lo, hi), the
#: next captures of that outcome inside ``[lo, hi]`` and older than ``:before``,
#: after the keyset cursor ``(ats, aid)``. One index range probe per window on
#: ``idx_fos_outcome_captured``; never more than ``:m`` rows per window.
_ADMIT_SQL = text(
    """
    SELECT c.w, x.id
    FROM unnest(
        CAST(:ws AS integer[]), CAST(:oids AS integer[]),
        CAST(:los AS timestamptz[]), CAST(:his AS timestamptz[]),
        CAST(:ats AS timestamptz[]), CAST(:aids AS integer[])
    ) AS c(w, oid, lo, hi, ats, aid)
    CROSS JOIN LATERAL (
        SELECT f.id
        FROM futures_odds_snapshots f
        WHERE f.outcome_id = c.oid
          AND f.captured_at >= c.lo
          AND f.captured_at <= c.hi
          AND f.captured_at < :before
          AND (f.captured_at, f.id) > (c.ats, c.aid)
        ORDER BY f.captured_at, f.id
        LIMIT :m
    ) x
    """
)

#: Rows asked per still-open window, per round. A window closes on its first
#: SUPPORTED capture (claimed) or on a short page (no capture there). The first
#: round asks one row because nearly every window closes on it; a window whose
#: rows the support filter refuses asks for more, keyset-paged, never re-read.
#: 72 refused rows close on round three's short page; 73 leave it full, so the
#: window is UNKNOWN (rule 5).
ADMIT_ROUND_LIMITS: tuple[int, ...] = (1, 8, 64)

#: :meth:`OlderLive.instant_claims` answers per seat: a skipped capture that
#: would draw HOLDS it, admission ran out of budget (UNKNOWN), or ``None``.
SEAT_HELD = "held"
SEAT_UNKNOWN = "unknown"

#: The route's own support filter (``_drop_unsupported_snapshot_points`` bound
#: to its outcomes): capture rows in, the rows a chart may draw out.
Supported = Callable[[list], list]


@dataclass
class OlderLive:
    """Our captures older than the ``hours`` cutoff, read under ``range=full``."""

    rows: list = field(default_factory=list)
    #: Distinct capture instants older than the cutoff (the TRUE count, not read).
    instants: int = 0
    thinned: bool = False
    #: What was asked, so a thinned read can answer rule 4's admission later.
    ids: list[int] = field(default_factory=list)
    before: Optional[datetime] = None
    #: The oldest capture instant (the skeleton keeps it): nothing older exists.
    oldest: Optional[datetime] = None
    #: Thinned only: admission checks left open by their row budget, summed
    #: over every call (one window may be asked by more than one arm). A log
    #: figure, never a reader's: each arm states its own withheld candidates.
    unresolved: int = 0

    @property
    def first(self) -> Optional[datetime]:
        return min((r.captured_at for r in self.rows), default=None)

    async def admit(
        self,
        db: Any,
        windows: Sequence[tuple[int, datetime, datetime]],
        supported: Supported,
    ) -> list[Optional[Any]]:
        """Per window, a SUPPORTED skipped capture inside it, :class:`Unresolved`,
        or ``None``.

        Exact: a window is claimed only by a capture of its own outcome whose
        instant lies in ``[lo, hi]`` and which ``supported`` keeps (the routes
        pass their own ``_drop_unsupported_snapshot_points``, the rule their
        claims already went through). ``None`` is proven: a short page showed
        no supported capture there. Unthinned reads issue nothing.
        """
        from app.models.models import FuturesOddsSnapshot

        found: list[Optional[Any]] = [None] * len(windows)
        if not self.thinned or self.oldest is None or self.before is None:
            return found
        # Only a window that can hold a skipped instant is asked: its outcome
        # was read here, and it reaches into [oldest, before).
        asked = set(self.ids)
        open_ = [
            i for i, (oid, lo, hi) in enumerate(windows)
            if int(oid) in asked and hi >= self.oldest and lo < self.before
        ]
        cursor: dict[int, tuple[datetime, int]] = {
            i: (windows[i][1], -1) for i in open_
        }
        for m in ADMIT_ROUND_LIMITS:
            if not open_:
                break
            ids_by_w: dict[int, list[int]] = defaultdict(list)
            for r in (
                await db.execute(_ADMIT_SQL, {
                    "ws": open_,
                    "oids": [int(windows[i][0]) for i in open_],
                    "los": [windows[i][1] for i in open_],
                    "his": [windows[i][2] for i in open_],
                    "ats": [cursor[i][0] for i in open_],
                    "aids": [cursor[i][1] for i in open_],
                    "before": self.before,
                    "m": m,
                })
            ).fetchall():
                ids_by_w[int(r.w)].append(int(r.id))
            wanted = sorted({x for v in ids_by_w.values() for x in v})
            by_id = {}
            if wanted:
                by_id = {
                    row.id: row
                    for row in (
                        await db.execute(
                            select(FuturesOddsSnapshot).where(
                                FuturesOddsSnapshot.id.in_(wanted)
                            )
                        )
                    ).scalars().all()
                }
            kept_ids = {row.id for row in supported(list(by_id.values()))}
            still: list[int] = []
            for i in open_:
                page = [by_id[x] for x in ids_by_w.get(i, ()) if x in by_id]
                hit = next((row for row in page if row.id in kept_ids), None)
                if hit is not None:
                    found[i] = hit
                elif len(page) >= m:
                    last = page[-1]
                    cursor[i] = (last.captured_at, int(last.id))
                    still.append(i)
            open_ = still
        # Out of budget: every row read there was refused, and more lie beyond
        # unread. Neither claimed nor clear (rule 5).
        if open_:
            self.unresolved += len(open_)
            logger.info(
                "full_range_live: %d window(s) unresolved after %d refused captures each",
                len(open_), sum(ADMIT_ROUND_LIMITS),
            )
        for i in open_:
            found[i] = Unresolved(*windows[i])
        return found

    async def archive_claims(
        self,
        db: Any,
        archive: Any,
        claims: Iterable[Any],
        outcome_ids: Iterable[int],
        supported: Supported,
    ) -> tuple[list, list[tuple[int, datetime, datetime]]]:
        """``claims`` plus every skipped capture that sits inside an interval,
        and the intervals admission left UNKNOWN.

        The candidates are the archive's own rows that the drawn ``claims`` do
        not already overlap and that can hold a skipped instant. A capture found
        is appended as an ordinary claim, so the archive's row rule
        (``ArchiveHistory.served``) decides overlap exactly as it does unthinned.
        An unresolved interval is returned by its own ``(outcome, start, end)``
        for ``served(unresolved=...)`` to withhold — that interval and no other.
        """
        claims = list(claims)
        if not self.thinned:
            return claims, []
        windows = archive.unclaimed_windows(claims, outcome_ids)
        found = await self.admit(db, windows, supported)
        return (
            claims + [r for r in found if r is not None and not isinstance(r, Unresolved)],
            [r.window for r in found if isinstance(r, Unresolved)],
        )

    async def instant_claims(
        self,
        db: Any,
        windows: Sequence[tuple[int, datetime, datetime]],
        supported: Supported,
    ) -> list[Optional[str]]:
        """Per window, :data:`SEAT_HELD` when a skipped capture that would DRAW
        lies in it, :data:`SEAT_UNKNOWN` when admission ran out, else ``None``.

        For the two seat rules a chart applies after the interval rule: the
        combined chart keeps a merged instant for live when ANY contributing
        outcome holds a capture there (CERT-4139: a skipped Polymarket twin at
        the archive close), and the timeline seats an outcome at a bucket start
        its own capture cell holds. Both read only captures with a probability,
        so a row without one claims no seat here either.
        """
        def drawn(rows: list) -> list:
            return [r for r in supported(rows) if r.probability is not None]

        return [
            None if hit is None else SEAT_UNKNOWN if isinstance(hit, Unresolved) else SEAT_HELD
            for hit in await self.admit(db, windows, drawn)
        ]

    async def withhold_venue(
        self,
        db: Any,
        rows: Iterable[Any],
        supported: Supported,
    ) -> tuple[list, list]:
        """``(kept, unresolved)``: the venue points no skipped capture of their
        own outcome claims, and the points admission left UNKNOWN.

        A capture claims a venue instant within the radius the venue arm hands
        captures (``generic_market_history.capture_claim_cap_seconds``: the
        venue's own declared grain, halved, never over 30 minutes). Measured from
        each point, so a point in a gap no capture reached stands. An unresolved
        point is not drawn, but it is still a real venue observation, so the
        routes keep it as a claim on the archive interval it sits in.
        """
        rows = list(rows)
        if not self.thinned or not rows:
            return rows, []
        from app.utils.generic_market_history import capture_claim_cap_seconds

        by_outcome: dict[int, list] = defaultdict(list)
        for r in rows:
            by_outcome[int(r.outcome_id)].append(r)
        radius = {
            oid: timedelta(seconds=capture_claim_cap_seconds(
                [r.captured_at for r in pts],
                venue_tiers=[getattr(r, "tier", "") for r in pts],
            ))
            for oid, pts in by_outcome.items()
        }
        windows = [
            (int(r.outcome_id), r.captured_at - radius[int(r.outcome_id)],
             r.captured_at + radius[int(r.outcome_id)])
            for r in rows
        ]
        hits = await self.admit(db, windows, supported)
        return (
            [r for r, hit in zip(rows, hits) if hit is None],
            [r for r, hit in zip(rows, hits) if isinstance(hit, Unresolved)],
        )


@dataclass(frozen=True)
class Unresolved:
    """A window admission could not close inside its budget (rule 5).

    Deliberately carries no ``captured_at``: it is not a capture, and nothing
    that reads claims by instant can mistake it for one.
    """

    outcome_id: int
    lo: datetime
    hi: datetime

    @property
    def window(self) -> tuple[int, datetime, datetime]:
        return (int(self.outcome_id), self.lo, self.hi)


def hours_since(start: datetime, now: Optional[datetime] = None) -> int:
    """Whole hours from ``start`` to ``now``, rounded up: the window drawn."""
    now = now or datetime.now(timezone.utc)
    return max(1, math.ceil((now - start).total_seconds() / 3600))


async def read_older_live(
    db: Any,
    outcome_ids: Iterable[int],
    *,
    before: datetime,
    cap: Optional[int] = None,
) -> OlderLive:
    """Every capture of ``outcome_ids`` older than ``before``, bounded by instant.

    Returns ORM ``FuturesOddsSnapshot`` rows, oldest first, so a route prepends
    them to its own window's rows and every downstream rule (support filter,
    de-vig, blend, overlap) runs on them unchanged.
    """
    from app.models.models import FuturesOddsSnapshot

    cap = OLDER_LIVE_INSTANT_CAP if cap is None else cap
    ids = sorted({int(i) for i in outcome_ids})
    out = OlderLive(ids=ids, before=before)
    if not ids:
        return out
    picked = (
        await db.execute(_INSTANTS_SQL, {"ids": ids, "before": before, "cap": cap})
    ).fetchall()
    if not picked:
        return out
    out.instants = int(picked[0].n)
    out.thinned = out.instants > cap
    out.oldest = picked[0].captured_at
    query = select(FuturesOddsSnapshot).where(
        FuturesOddsSnapshot.outcome_id.in_(ids),
        FuturesOddsSnapshot.captured_at < before,
    )
    if out.thinned:
        query = query.where(
            FuturesOddsSnapshot.captured_at.in_([r.captured_at for r in picked])
        )
    out.rows = list(
        (await db.execute(query.order_by(FuturesOddsSnapshot.captured_at))).scalars().all()
    )
    return out
