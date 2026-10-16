"""#1853 — which stored Kalshi legs an exact-event ARCHIVE listing may grade.

THE DEFECT. ``_backfill_kalshi_winners`` asks ``GET /events/{ticker}`` and grades
the nested legs. Once the venue moves an event's markets to its archive tier, that
read still finds the event but returns NO legs, and the only fallback left is the
price-crown arm, which needs every leg at >=0.95 or <=0.05. Specimen
``KXUECLSCORE-26JUL30LEVIFK`` (market 59280512): the archive lists all 30 legs
finalized with a binary result, 8 stored legs already carry ``api_settlement``,
and 22 stayed ``resolution_source = NULL`` / ``is_winner = NULL`` — e.g. outcome
229512806 at 0.47, finalized ``no`` at the venue.

THIS MODULE IS THE DECISION, AND ONLY THE DECISION. It reads an archive listing
that :func:`app.tasks.kalshi_resolution_sweep.read_archived_event_legs` already
proved exact (exhausted, every leg naming the event, no repeated ticker) and the
stored legs of that event, and says which legs may be written. The grader's
archive arm and the attended exact-ID repair script both call it, so the live
path and the historical plan cannot disagree about a leg.

What it refuses, each under its own reason so nothing becomes a silent skip:

* a stored leg the listing does not name (``absent_from_archive``);
* a leg that already carries ANY grade or source (``already_graded``) — the
  authoritative controls are preserved and a softer existing grade is not this
  ship's to overwrite;
* a declaration that maps to no side (``no_verdict``): empty, ``scalar``, or a
  status that carries no result (:func:`kalshi_market_status.gradeable_winner`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from app.utils import kalshi_market_status as kms

#: The provenance an archive-backed grade is written with. The archive is the
#: venue's own settlement record for the same market ticker, read through the same
#: provider — the identity ``api_settlement`` already names.
ARCHIVE_GRADE_SOURCE = "api_settlement"

ABSENT = "absent_from_archive"
ALREADY_GRADED = "already_graded"
NO_VERDICT = "no_verdict"


@dataclass(frozen=True)
class StoredLeg:
    outcome_id: int
    external_id: Optional[str]
    resolution_source: Optional[str]
    is_winner: Optional[bool]


@dataclass(frozen=True)
class ArchiveGrade:
    outcome_id: int
    ticker: str
    is_winner: bool
    status: Optional[str]
    result: Optional[str]


def stored_legs(rows: Iterable[Any]) -> list[StoredLeg]:
    """Rows of ``(id, external_id, resolution_source, is_winner)`` as plain data."""
    return [
        StoredLeg(int(r[0]), r[1], r[2], None if r[3] is None else bool(r[3]))
        for r in rows
    ]


def plan_archive_grades(
    legs: list[dict], stored: Iterable[StoredLeg]
) -> tuple[list[ArchiveGrade], dict[str, list[int]]]:
    """``(grades, refused)`` for one event: what may be written, and why not.

    ``legs`` must already be an exact, exhausted listing of this event — this
    function does not re-check identity, it maps it. ``refused`` maps each reason
    to the outcome ids it covers, so callers can count every leg.
    """
    by_ticker = {leg["ticker"]: leg for leg in legs}
    grades: list[ArchiveGrade] = []
    refused: dict[str, list[int]] = {ABSENT: [], ALREADY_GRADED: [], NO_VERDICT: []}
    for row in stored:
        if row.resolution_source is not None or row.is_winner is not None:
            refused[ALREADY_GRADED].append(row.outcome_id)
            continue
        leg = by_ticker.get(row.external_id) if row.external_id else None
        if leg is None:
            refused[ABSENT].append(row.outcome_id)
            continue
        status, result = leg.get("status"), leg.get("result")
        winner = kms.gradeable_winner(status, result)
        if winner is None:
            refused[NO_VERDICT].append(row.outcome_id)
            continue
        grades.append(ArchiveGrade(row.outcome_id, leg["ticker"], winner, status, result))
    return grades, refused
