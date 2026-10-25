"""#683 reader half: Kalshi archive intervals on the history charts. Explicit join.

PILLAR: TRUTH. SHIP: a settled Kalshi question with missing history gains its
real recoverable pre-resolution probability journey on web (``/history``, and
``/multi-history`` when the evolution view combines markets) and native
(``/probability-timeline``), with archive provenance on every point.

WHY A SEPARATE ARM AND NOT ``futures_odds_snapshots``. The archive store is its
own table (``kalshi_archive_intervals``) so that no existing snapshot reader,
calibration phase, coverage probe or "latest price" read can see these rows.
This module is the one door the three chart routes open on purpose.

THE RULES THIS ARM HOLDS

1. **Live evidence wins actual overlap, and only actual overlap.** An archive
   interval is withheld when a live observation the chart already draws (a
   capture, or a venue-history point) falls INSIDE it, ``[start, end]``. Every
   other interval stands, whether before the first live capture, between two of
   them or after the last one. A live point never suppresses the rest of a
   recoverable timeline.
2. **An interval is SERVED as an interval.** The point sits at ``interval_end``
   (the candle's close) and carries ``interval_start``, ``period_minutes``,
   ``price_basis`` and ``provenance: kalshi_archive``, so the payload never
   passes it off as a polling instant. Nothing is interpolated or carried
   forward to fill a gap. HOW A CLIENT SHOWS that distinction is the client's:
   as of this change no web or native reader decodes these fields, so a reader
   sees the close as an ordinary chart point. That client half is an explicit,
   owner-routed dependency of #683 (web: UX; native: Native), not a claim here.
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
6. **``range=full`` reads the whole stored lifetime, and says so.** A client's
   "Full" sends ``hours`` (its own floor, which an older server serves) plus
   ``range=full``. The archive arm then has no lower time bound, so a question
   whose recovered intervals are older than any fixed window still draws them
   (Root's 189-day specimen drew nothing at the web's 4320h). The bounds stay:
   an outcome holding more than :data:`READ_CAP_PER_OUTCOME` intervals is read
   SPAN-KEEPING (its newest run in full, everything older as an evenly ranked
   skeleton that keeps the first interval) instead of newest-first tail-cut, and
   is named in ``thinned_outcomes``. Live captures reach their lifetime too
   (``full_range_live``: whole instants, bounded, exact admission of skipped
   captures), so an interval our own capture holds still yields to it however
   old both are, and one no capture touches still stands — Root
   executed the earlier cut, which kept live on ``hours``, and found 189-day
   captures replaced by archive intervals. ``history_range`` states the window
   drawn, why it starts there, and the import's own coverage word, because the
   earliest drawn interval is not proof of the question's open.
7. **An overlap nobody could decide is withheld, and said.** When a thinned
   live read runs out of admission budget on an interval (``full_range_live``
   rule 5), a supported capture may lie in its unread remainder, so the
   interval is not drawn — but it is NOT live's: it is counted apart from
   ``withheld_overlapping_live`` as ``withheld_unresolved_overlap``, with a
   scoped ``overlap_admission`` refusal, and ``history_range`` says the served
   history is ``partial``. Only that exact interval is withheld; its
   neighbours are decided on their own evidence. Stored coverage
   (``archive_coverage``, the import's word) and served completeness
   (``served_history``) are different questions and never share a field.
"""

from __future__ import annotations

import bisect
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import text

from app.utils.kalshi_archive_history import COVERAGE_COMPLETE, COVERAGE_INCOMPLETE

logger = logging.getLogger(__name__)

ARCHIVE_PROVENANCE = "kalshi_archive"
READ_CAP_PER_OUTCOME = 5000
SERVE_TARGET_PER_OUTCOME = 400
#: The ``range`` value that asks a history route for the question's whole lifetime.
FULL_RANGE = "full"
#: ``since`` for a full read: no time bound below what the store holds.
LIFETIME_FLOOR = datetime(1970, 1, 1, tzinfo=timezone.utc)
#: The two ``window_start_basis`` answers. Live captures never move the start
#: under ``range=full`` (their window is the client's ``hours``).
BASIS_ARCHIVE = "archive_first_interval"
BASIS_HOURS = "hours"
#: A served venue point older than every capture and interval opens the chart.
BASIS_VENUE = "venue_first_observation"
#: ``history_range.served_history``: every interval and venue point read was
#: drawn or yielded to proven live evidence, or some were withheld UNKNOWN.
SERVED_COMPLETE = "complete"
SERVED_PARTIAL = "partial"
#: The scoped refusal an UNKNOWN overlap carries, in both history blocks.
OVERLAP_REFUSAL = {"scope": "overlap_admission", "reason": "live_overlap_unresolved"}
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


#: An outcome over the cap, read whole-lifetime: both endpoints and every k-th
#: interval by rank, at most ``cap + 2`` rows. Only ever asked for outcomes the
#: newest-first read above already proved hold more than ``cap``.
SKELETON_SQL = text(
    """
    SELECT s.outcome_id, s.interval_start, s.interval_end, s.period_minutes,
           s.probability, s.price_basis
    FROM (
        SELECT k.outcome_id, k.interval_start, k.interval_end, k.period_minutes,
               k.probability, k.price_basis,
               row_number() OVER (
                   PARTITION BY k.outcome_id ORDER BY k.interval_end, k.period_minutes
               ) AS rn,
               count(*) OVER (PARTITION BY k.outcome_id) AS n
        FROM kalshi_archive_intervals k
        WHERE k.outcome_id = ANY(CAST(:ids AS integer[]))
          AND k.interval_end < k.venue_settlement_ts
    ) s
    WHERE s.rn = 1 OR s.rn = s.n
       OR (s.rn - 1) % GREATEST(1, CEIL(s.n::numeric / :cap)::integer) = 0
    """
)

#: The import's own statement of each outcome's archive coverage. Restored
#: imports delete their evidence; a failed or in-flight one is not evidence.
EVIDENCE_SQL = text(
    """
    SELECT ev.outcome_id, ev.coverage, ev.venue_open_ts
    FROM kalshi_archive_outcome_evidence ev
    JOIN kalshi_archive_imports i ON i.id = ev.import_id
    WHERE ev.outcome_id = ANY(CAST(:ids AS integer[]))
      AND i.status IN ('applied', 'partial')
    """
)


def wants_full_range(value: Any) -> bool:
    """True only for the literal ``range=full``. A direct Python caller's
    unresolved ``Query`` default, ``None`` or any other word is today's read."""
    return isinstance(value, str) and value.strip().lower() == FULL_RANGE


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
        #: Rule 7: ``(outcome, interval_start, interval_end)`` of each interval
        #: withheld because live overlap could not be decided. Never live's.
        self.unresolved: set[tuple[int, datetime, datetime]] = set()
        self.compacted_from: dict[int, int] = {}
        #: ``range=full`` only: outcomes read span-keeping, and the evidence rows.
        self.thinned: list[int] = []
        self.coverage: dict[int, set] = {}
        self.venue_open: dict[int, datetime] = {}

    def served(
        self,
        cutoff: datetime,
        claims: Iterable[Any],
        outcome_ids: Iterable[int],
        unresolved: Iterable[tuple[int, datetime, datetime]] = (),
    ) -> dict[int, list[ArchiveRow]]:
        """Per outcome, the intervals at/after ``cutoff`` no live point overlaps.

        ``claims`` are the live rows the chart already draws (``outcome_id`` and
        ``captured_at``). Under ``range=full`` with a thinned live read, the
        route first adds every skipped capture that actually sits inside an
        interval (``full_range_live.OlderLive.archive_claims``), so this one
        rule decides overlap for read and skipped captures alike. Counts
        withheld intervals in ``claimed_by_live``. ``unresolved`` names, by
        exact ``(outcome, start, end)``, the intervals admission could not
        decide: those are withheld into :attr:`unresolved` instead (rule 7).
        """
        self.unresolved = set()
        if not self.rows:
            return {}
        live = _claim_stamps(claims)
        unknown = {(int(o), lo, hi) for o, lo, hi in unresolved}
        out: dict[int, list[ArchiveRow]] = {}
        self.claimed_by_live = 0
        self.compacted_from = {}
        for oid in outcome_ids:
            stamps = live.get(int(oid), [])
            kept: list[ArchiveRow] = []
            for row in self.rows.get(int(oid), ()):
                if row.captured_at < cutoff:
                    continue
                if _overlaps(stamps, row):
                    self.claimed_by_live += 1
                    continue
                if _identity(row) in unknown:
                    self.unresolved.add(_identity(row))
                    continue
                kept.append(row)
            if len(kept) > SERVE_TARGET_PER_OUTCOME:
                kept = _compact(kept)
                self.compacted_from[int(oid)] = len(self.rows.get(int(oid), ()))
            if kept:
                out[int(oid)] = kept
        return out

    def withhold_unresolved(self, row: ArchiveRow) -> None:
        """A served interval a SEAT rule could not decide (rule 7): the route
        leaves it undrawn and it is counted with the interval-rule unknowns."""
        self.unresolved.add(_identity(row))

    def unclaimed_windows(
        self, claims: Iterable[Any], outcome_ids: Iterable[int]
    ) -> list[tuple[int, datetime, datetime]]:
        """``(outcome, interval_start, interval_end)`` of every held interval the
        ``claims`` do not already overlap: the candidates a thinned live read
        must ask the store about (``full_range_live`` rule 4)."""
        live = _claim_stamps(claims)
        return [
            (int(oid), row.interval_start, row.captured_at)
            for oid in outcome_ids
            for row in self.rows.get(int(oid), ())
            if not _overlaps(live.get(int(oid), []), row)
        ]

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
            "withheld_unresolved_overlap": len(self.unresolved),
        }
        if self.compacted_from:
            block["compacted_from"] = {str(k): v for k, v in self.compacted_from.items()}
        if self.read_capped:
            block["read_capped_outcomes"] = sorted(self.read_capped)
        refusals = []
        if scale_refused:
            refusals.append({"scope": "reader", "reason": scale_refused})
        if self.unresolved:
            refusals.append({**OVERLAP_REFUSAL, "intervals": len(self.unresolved)})
        if refusals:
            block["refusals"] = refusals
        return block

    def range_block(
        self,
        live_window_start: datetime,
        served_rows: list[ArchiveRow],
        charted_ids: Iterable[int],
        *,
        live_basis: str = BASIS_HOURS,
        venue_first: Optional[datetime] = None,
        live_thinned: bool = False,
        venue_unresolved: Iterable[Any] = (),
    ) -> dict:
        """``history_range`` for a ``range=full`` response. Metadata only.

        ``window_start`` is where the drawn chart begins: the earliest of the
        first served archive interval's START, the first served venue point, and
        the live window — which under ``range=full`` is our own first capture
        (``live_basis`` = ``live_first_capture``) when one predates ``hours``.
        ``archive_coverage`` is ``complete`` only when EVERY charted outcome
        carries a complete import (one never imported makes it ``incomplete``);
        ``None`` when no charted outcome carries any import at all.
        ``live_thinned`` says the older live captures were read as a skeleton.
        ``served_history`` is ``partial`` when a charted outcome had an archive
        interval (:attr:`unresolved`) or a venue point (``venue_unresolved``,
        rows from ``OlderLive.withhold_venue``) withheld UNKNOWN (rule 7);
        ``unresolved_withheld`` counts each arm's distinct candidates apart.
        """
        charted = sorted({int(i) for i in charted_ids})
        first = min((r.interval_start for r in served_rows), default=None)
        start, basis = live_window_start, live_basis
        if venue_first is not None and venue_first < start:
            start, basis = venue_first, BASIS_VENUE
        if first is not None and first < start:
            start, basis = first, BASIS_ARCHIVE
        asked = [oid for oid in charted if oid in self.coverage]
        if not asked:
            coverage = None
        elif all(COVERAGE_COMPLETE in self.coverage.get(oid, ()) for oid in charted):
            coverage = COVERAGE_COMPLETE
        else:
            coverage = COVERAGE_INCOMPLETE
        opens = [self.venue_open[oid] for oid in charted if oid in self.venue_open]
        withheld = {
            "archive_intervals": len({k for k in self.unresolved if k[0] in charted}),
            "venue_points": len({
                (int(r.outcome_id), r.captured_at)
                for r in venue_unresolved
                if int(r.outcome_id) in charted
            }),
        }
        return {
            "requested": FULL_RANGE,
            "window_start": start.isoformat(),
            "window_start_basis": basis,
            "archive_coverage": coverage,
            "archive_venue_open": min(opens).isoformat() if opens else None,
            "thinned_outcomes": [oid for oid in sorted(self.thinned) if oid in charted],
            "live_thinned": bool(live_thinned),
            "served_history": SERVED_PARTIAL if any(withheld.values()) else SERVED_COMPLETE,
            "unresolved_withheld": withheld,
        }


def _claim_stamps(claims: Iterable[Any]) -> dict[int, list[datetime]]:
    live: dict[int, list[datetime]] = defaultdict(list)
    for row in claims:
        stamp = getattr(row, "captured_at", None)
        if stamp is not None:
            live[int(row.outcome_id)].append(stamp)
    for stamps in live.values():
        stamps.sort()
    return live


def _identity(row: ArchiveRow) -> tuple[int, datetime, datetime]:
    """One interval, as ``unclaimed_windows`` names its candidate window."""
    return (int(row.outcome_id), row.interval_start, row.captured_at)


def _overlaps(stamps: list[datetime], row: ArchiveRow) -> bool:
    """Rule 1: a live instant inside ``[interval_start, interval_end]``."""
    i = bisect.bisect_left(stamps, row.interval_start)
    return i < len(stamps) and stamps[i] <= row.captured_at


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


def _archive_row(r: Any) -> ArchiveRow:
    return ArchiveRow(
        outcome_id=int(r.outcome_id),
        captured_at=r.interval_end,
        interval_start=r.interval_start,
        period_minutes=int(r.period_minutes),
        probability=float(r.probability),
        price_basis=r.price_basis,
    )


async def load_archive_history(
    db: Any,
    market: Any,
    outcome_ids: Iterable[int],
    *,
    since: datetime,
    full_range: bool = False,
) -> ArchiveHistory:
    """Read the archive intervals for ``outcome_ids``. NEVER raises, NEVER fetches.

    Only a Kalshi market is asked, so every other chart issues no extra query.
    ``full_range`` (rule 6) reads from :data:`LIFETIME_FLOOR`, span-keeping, and
    reads the evidence coverage; without it the read is exactly the bounded one.
    """
    history = ArchiveHistory()
    ids = sorted({int(i) for i in outcome_ids})
    if getattr(market, "source", None) != "kalshi" or not ids or db is None:
        return history
    try:
        if not await _store_present(db):
            history.state = "absent"
            return history
        if full_range:
            since = LIFETIME_FLOOR
        skeleton: list = []
        evidence: list = []
        async with db.begin_nested():
            # Not `result = await db.execute(`: that exact text is a typeahead
            # mutant's replacement, and the residue scan's Pass B flags it in any
            # changed file (test_mutation_guard; CI on 0bbfafd348, shard 8).
            fetched = (
                await db.execute(
                    READ_SQL, {"ids": ids, "since": since, "cap": READ_CAP_PER_OUTCOME}
                )
            ).fetchall()
            if full_range:
                counts: dict[int, int] = defaultdict(int)
                for r in fetched:
                    counts[int(r.outcome_id)] += 1
                over = sorted(o for o, n in counts.items() if n >= READ_CAP_PER_OUTCOME)
                if over:
                    skeleton = (
                        await db.execute(
                            SKELETON_SQL, {"ids": over, "cap": READ_CAP_PER_OUTCOME}
                        )
                    ).fetchall()
                evidence = (await db.execute(EVIDENCE_SQL, {"ids": ids})).fetchall()
        by_outcome: dict[int, list[ArchiveRow]] = defaultdict(list)
        for r in fetched:
            by_outcome[int(r.outcome_id)].append(_archive_row(r))
        for oid, rows in by_outcome.items():
            rows.sort(key=lambda r: r.captured_at)
        # Span-keeping: the newest run stands in full; the skeleton supplies only
        # what lies before its oldest interval, so the first interval is drawn.
        thinned: set[int] = set()
        for r in skeleton:
            row = _archive_row(r)
            dense = by_outcome.get(row.outcome_id)
            if dense and row.captured_at < dense[0].captured_at:
                by_outcome[row.outcome_id].append(row)
                thinned.add(row.outcome_id)
        for oid in thinned:
            by_outcome[oid].sort(key=lambda r: r.captured_at)
        # Tail-cut is only ever the bounded read's: under a full read every
        # outcome at the cap was asked whole-lifetime, so nothing older is unread.
        if not full_range:
            for oid, rows in by_outcome.items():
                if len(rows) >= READ_CAP_PER_OUTCOME:
                    history.read_capped.append(oid)
        history.thinned = sorted(thinned)
        for r in evidence:
            oid = int(r.outcome_id)
            history.coverage.setdefault(oid, set()).add(r.coverage)
            if r.venue_open_ts is not None and (
                oid not in history.venue_open or r.venue_open_ts < history.venue_open[oid]
            ):
                history.venue_open[oid] = r.venue_open_ts
        history.rows = dict(by_outcome)
        history.state = "warm" if history.rows else "empty"
    except Exception as exc:  # noqa: BLE001 — archive history never fails a chart
        logger.warning(
            "kalshi archive history unavailable for market %s: %s",
            getattr(market, "id", None),
            str(exc)[:200],
        )
        history.rows = {}
        history.read_capped = []
        history.thinned = []
        history.coverage = {}
        history.venue_open = {}
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
