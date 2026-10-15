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
4. **Live keeps its precedence over the span it actually holds.** Unthinned,
   the rows read ARE the claims, exactly as in the ordinary window. Thinned, the
   skipped instants still exist, so each outcome's presence is read as spans
   (consecutive skeleton buckets in which that outcome holds any capture) and an
   archive interval or venue point inside one yields to live — the archive
   never fills an instant our own capture already spoke for merely because the
   bound did not draw it.
5. **Explicit short ranges are untouched.** Nothing here runs without
   ``range=full``; every other request issues exactly today's statements.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import select, text

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

#: Thinned only: per outcome, the spans of consecutive ``:k``-instant buckets in
#: which it holds any capture (gaps-and-islands), so a skipped instant still
#: claims its place. At most one row per island, typically one per outcome.
_SPANS_SQL = text(
    """
    WITH inst AS (
        SELECT d.captured_at,
               (row_number() OVER (ORDER BY d.captured_at) - 1) / :k AS b
        FROM (
            SELECT DISTINCT captured_at
            FROM futures_odds_snapshots
            WHERE outcome_id = ANY(CAST(:ids AS integer[]))
              AND captured_at < :before
        ) d
    ), per AS (
        SELECT f.outcome_id, i.b, min(f.captured_at) AS lo, max(f.captured_at) AS hi
        FROM futures_odds_snapshots f
        JOIN inst i ON i.captured_at = f.captured_at
        WHERE f.outcome_id = ANY(CAST(:ids AS integer[]))
          AND f.captured_at < :before
        GROUP BY f.outcome_id, i.b
    )
    SELECT g.outcome_id, min(g.lo) AS lo, max(g.hi) AS hi
    FROM (
        SELECT outcome_id, lo, hi,
               b - row_number() OVER (PARTITION BY outcome_id ORDER BY b) AS grp
        FROM per
    ) g
    GROUP BY g.outcome_id, g.grp
    """
)


@dataclass
class OlderLive:
    """Our captures older than the ``hours`` cutoff, read under ``range=full``."""

    rows: list = field(default_factory=list)
    #: Distinct capture instants older than the cutoff (the TRUE count, not read).
    instants: int = 0
    thinned: bool = False
    #: Thinned only: outcome -> [(lo, hi)] live-presence spans (rule 4).
    spans: dict[int, list[tuple[datetime, datetime]]] = field(default_factory=dict)

    @property
    def first(self) -> Optional[datetime]:
        return min((r.captured_at for r in self.rows), default=None)

    def withhold(self, rows: Iterable[Any]) -> list:
        """Drop the rows (venue points) inside a live span of their own outcome."""
        rows = list(rows)
        if not self.spans:
            return rows
        return [
            r for r in rows
            if not any(
                lo <= r.captured_at <= hi for lo, hi in self.spans.get(int(r.outcome_id), ())
            )
        ]


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
    out = OlderLive()
    if not ids:
        return out
    picked = (
        await db.execute(_INSTANTS_SQL, {"ids": ids, "before": before, "cap": cap})
    ).fetchall()
    if not picked:
        return out
    out.instants = int(picked[0].n)
    out.thinned = out.instants > cap
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
    if out.thinned:
        k = math.ceil(out.instants / cap)
        for r in (
            await db.execute(_SPANS_SQL, {"ids": ids, "before": before, "k": k})
        ).fetchall():
            out.spans.setdefault(int(r.outcome_id), []).append((r.lo, r.hi))
    return out
