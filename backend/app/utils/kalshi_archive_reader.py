"""#683 reader half: Kalshi archive intervals on the history charts. Explicit join.

PILLAR: TRUTH. SHIP: a settled Kalshi question with missing history gains its
real recoverable pre-resolution probability journey on web (``/history``) and
native (``/probability-timeline``), with archive provenance on every point.

WHY A SEPARATE ARM AND NOT ``futures_odds_snapshots``. The archive store is its
own table (``kalshi_archive_intervals``) so that no existing snapshot reader,
calibration phase, coverage probe or "latest price" read can see these rows.
This module is the one door the two chart routes open on purpose.

THE RULES THIS ARM HOLDS

1. **Live evidence wins actual overlap, and only actual overlap.** An archive
   interval is withheld when a live observation the chart already draws (a
   capture, or a venue-history point) falls INSIDE it, ``[start, end]``. Every
   other interval stands, whether before the first live capture, between two of
   them or after the last one. A live point never suppresses the rest of a
   recoverable timeline.
2. **An interval is drawn as an interval.** The point sits at ``interval_end``
   (the candle's close) and carries ``interval_start``, ``period_minutes``,
   ``price_basis`` and ``provenance: kalshi_archive``, so it can never pass for a
   polling instant. Nothing is interpolated or carried forward to fill a gap.
3. **Never past settlement.** The store refuses an interval ending at or after
   the venue's settlement (``ck_kaiv_before_settlement``), and the read repeats
   the bound.
4. **Bounded and never fatal.** One indexed read per chart, Kalshi markets only,
   at most :data:`READ_CAP_PER_OUTCOME` rows per outcome, inside a SAVEPOINT. A
   store that is absent (migration not yet applied) or unreadable leaves the
   chart exactly as it was and says so in ``state``.
5. **Bounded on the wire too.** Above :data:`SERVE_TARGET_PER_OUTCOME` points a
   line is compacted with the house compactor (``compact_series``: every move,
   both endpoints, by value change and never by stride), and the block says how
   many it was compacted from.
"""

from __future__ import annotations

import bisect
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

ARCHIVE_PROVENANCE = "kalshi_archive"
READ_CAP_PER_OUTCOME = 5000
SERVE_TARGET_PER_OUTCOME = 400
#: How long one process trusts its answer to "is the store there".
_PRESENCE_TTL_S = 300.0
_presence: dict = {"value": None, "checked": 0.0}

PRESENCE_SQL = text("SELECT to_regclass('public.kalshi_archive_intervals') IS NOT NULL")

#: Newest first per outcome, so a capped read keeps the run-up to settlement.
READ_SQL = text(
    """
    SELECT k.outcome_id, k.interval_start, k.interval_end, k.period_minutes,
           k.probability, k.price_basis
    FROM unnest(CAST(:ids AS integer[])) AS o(id)
    CROSS JOIN LATERAL (
        SELECT outcome_id, interval_start, interval_end, period_minutes,
               probability, price_basis
        FROM kalshi_archive_intervals k
        WHERE k.outcome_id = o.id
          AND k.interval_end >= :since
          AND k.interval_end < k.venue_settlement_ts
        ORDER BY k.interval_end DESC
        LIMIT :cap
    ) k
    """
)


@dataclass(frozen=True)
class ArchiveRow:
    """An archive interval wearing the attribute names the chart helpers read."""

    outcome_id: int
    captured_at: datetime
    interval_start: datetime
    period_minutes: int
    probability: float
    price_basis: str
    bookmaker: str = ARCHIVE_PROVENANCE


class ArchiveHistory:
    """What the archive store holds for one market's charted field, already bounded."""

    def __init__(self) -> None:
        self.state = "not_applicable"
        self.rows: dict[int, list[ArchiveRow]] = {}
        self.read_capped: list[int] = []
        self.claimed_by_live = 0
        self.compacted_from: dict[int, int] = {}

    def served(
        self, cutoff: datetime, claims: Iterable[Any], outcome_ids: Iterable[int]
    ) -> dict[int, list[ArchiveRow]]:
        """Per outcome, the intervals at/after ``cutoff`` no live point overlaps.

        ``claims`` are the live rows the chart already draws (``outcome_id`` and
        ``captured_at``). Counts withheld intervals in ``claimed_by_live``.
        """
        if not self.rows:
            return {}
        live: dict[int, list[datetime]] = defaultdict(list)
        for row in claims:
            stamp = getattr(row, "captured_at", None)
            if stamp is not None:
                live[int(row.outcome_id)].append(stamp)
        for stamps in live.values():
            stamps.sort()
        out: dict[int, list[ArchiveRow]] = {}
        self.claimed_by_live = 0
        self.compacted_from = {}
        for oid in outcome_ids:
            stamps = live.get(int(oid), [])
            kept: list[ArchiveRow] = []
            for row in self.rows.get(int(oid), ()):
                if row.captured_at < cutoff:
                    continue
                i = bisect.bisect_left(stamps, row.interval_start)
                if i < len(stamps) and stamps[i] <= row.captured_at:
                    self.claimed_by_live += 1
                    continue
                kept.append(row)
            if len(kept) > SERVE_TARGET_PER_OUTCOME:
                kept = _compact(kept)
                self.compacted_from[int(oid)] = len(self.rows.get(int(oid), ()))
            if kept:
                out[int(oid)] = kept
        return out

    def describe(
        self, served_rows: list[ArchiveRow], *, scale_refused: Optional[str] = None
    ) -> dict:
        """The reader's own statement of what it served and why. Metadata only."""
        stamps = [r.captured_at for r in served_rows]
        bases: dict[str, int] = defaultdict(int)
        for r in served_rows:
            bases[r.price_basis] += 1
        block = {
            "state": "refused" if scale_refused else self.state,
            "provenance": ARCHIVE_PROVENANCE,
            "points_served": len(served_rows),
            "outcomes_served": len({r.outcome_id for r in served_rows}),
            "observed_from": min(stamps).isoformat() if stamps else None,
            "observed_through": max(stamps).isoformat() if stamps else None,
            "periods_minutes": sorted({r.period_minutes for r in served_rows}),
            "price_basis": dict(bases),
            "withheld_overlapping_live": self.claimed_by_live,
        }
        if self.compacted_from:
            block["compacted_from"] = {str(k): v for k, v in self.compacted_from.items()}
        if self.read_capped:
            block["read_capped_outcomes"] = sorted(self.read_capped)
        if scale_refused:
            block["refusals"] = [{"scope": "reader", "reason": scale_refused}]
        return block


def _compact(rows: list[ArchiveRow]) -> list[ArchiveRow]:
    from app.utils.futures_chart_series import compact_series

    keep = {
        ts
        for ts, _ in compact_series(
            [(r.captured_at, float(r.probability)) for r in rows],
            target_points=SERVE_TARGET_PER_OUTCOME,
        )
    }
    return [r for r in rows if r.captured_at in keep]


async def _store_present(db: Any) -> bool:
    now = time.monotonic()
    if _presence["value"] is not None and now - _presence["checked"] < _PRESENCE_TTL_S:
        return bool(_presence["value"])
    value = bool((await db.execute(PRESENCE_SQL)).scalar())
    _presence.update(value=value, checked=now)
    return value


async def load_archive_history(
    db: Any, market: Any, outcome_ids: Iterable[int], *, since: datetime
) -> ArchiveHistory:
    """Read the archive intervals for ``outcome_ids``. NEVER raises, NEVER fetches.

    Only a Kalshi market is asked, so every other chart issues no extra query.
    """
    history = ArchiveHistory()
    ids = sorted({int(i) for i in outcome_ids})
    if getattr(market, "source", None) != "kalshi" or not ids or db is None:
        return history
    try:
        if not await _store_present(db):
            history.state = "absent"
            return history
        async with db.begin_nested():
            result = await db.execute(
                READ_SQL, {"ids": ids, "since": since, "cap": READ_CAP_PER_OUTCOME}
            )
            fetched = result.fetchall()
        by_outcome: dict[int, list[ArchiveRow]] = defaultdict(list)
        for r in fetched:
            by_outcome[int(r.outcome_id)].append(
                ArchiveRow(
                    outcome_id=int(r.outcome_id),
                    captured_at=r.interval_end,
                    interval_start=r.interval_start,
                    period_minutes=int(r.period_minutes),
                    probability=float(r.probability),
                    price_basis=r.price_basis,
                )
            )
        for oid, rows in by_outcome.items():
            rows.sort(key=lambda r: r.captured_at)
            if len(rows) >= READ_CAP_PER_OUTCOME:
                history.read_capped.append(oid)
        history.rows = dict(by_outcome)
        history.state = "warm" if history.rows else "empty"
    except Exception as exc:  # noqa: BLE001 — archive history never fails a chart
        logger.warning(
            "kalshi archive history unavailable for market %s: %s",
            getattr(market, "id", None),
            str(exc)[:200],
        )
        history.rows = {}
        history.state = "unavailable"
    return history


def history_point(row: ArchiveRow) -> dict:
    """One ``/history`` point for an archive interval."""
    return {
        "timestamp": row.captured_at.isoformat(),
        "probability": round(float(row.probability), 6),
        "american_odds": None,
        "bookmaker": ARCHIVE_PROVENANCE,
        "provenance": ARCHIVE_PROVENANCE,
        "interval_start": row.interval_start.isoformat(),
        "period_minutes": row.period_minutes,
        "price_basis": row.price_basis,
    }


def timeline_mark(row: ArchiveRow) -> dict:
    """What a ``/probability-timeline`` entry says about one archive value."""
    return {
        "provenance": ARCHIVE_PROVENANCE,
        "interval_start": row.interval_start.isoformat(),
        "period_minutes": row.period_minutes,
        "price_basis": row.price_basis,
    }
