"""ESPN's date-only placeholder is marked, so a reader sees "TBD" (#8981).

**SHIP: a college football game whose kickoff is not announced shows its date
and "TBD", not a made-up "Oct 2 9:00 PM" and a countdown.** (Pillar: TRUTH.)

ESPN lists a game weeks before its kickoff is set, dated at midnight Eastern
with ``timeValid=false``. Clemson–Miami (401858249) is listed that way, measured
2026-09-27 00:00Z: ``2026-10-03T04:00Z``, status "10/3 - TBD". Our row 14870012
sits on that instant (stamped from ESPN before #8841 taught the rails to refuse
it), so the event page read "Oct 2, 2026 · 9:00 PM PDT · Starts in 6d 4h": the
wrong day for a Pacific reader, and a countdown to a time nobody announced. On
that date 34 upcoming college football rows (10/3 to 11/21) sat on a
midnight-Eastern stamp, and no other sport had any.

Nothing else revisits those rows until their game week. The live and pre-game
ESPN passes read only the CURRENT board, and the Odds ingest (#8841) now
declines to write a ``timeValid=false`` date at all. So this pass reads ESPN's
board for each day those rows sit on and writes ESPN's own mark,
``provenance:start-placeholder:espn:<instant>``, which ``start_is_tbd`` honours
exactly like StatPal's.

**The clock only nominates a row, and ESPN decides.** The candidate filter is
"on the hour at 04:00Z or 05:00Z" (midnight Eastern in summer and in winter),
but a real Hawaii home kickoff at 6 PM or 7 PM HST lands on those same
instants. A row is marked only when ESPN's board, read by ``espn_id``, says
``timeValid: false`` AND the row still sits on ESPN's placeholder minute. An
explicit ``timeValid: true`` clears the mark. That includes the equal-instant
case, where the announced kickoff is the placeholder minute itself. An absent
flag or a dark board changes nothing.

Bounded by construction: one scoreboard read per (sport, day) among the
candidates, capped at :data:`MAX_BOARDS`. On 2026-09-27 that was 8 reads.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import extract, func, select

from app.utils.sport_keys import ESPN_SPORT_MAPPING
from app.utils.start_placeholder import (
    desired_espn_start_placeholder_tags,
    espn_start_placeholder_tags,
)

logger = logging.getLogger(__name__)

#: How far ahead a placeholder is worth marking. ESPN posts a college football
#: season's whole schedule in advance; 120 days covers any regular season
#: from its opening week.
LOOKAHEAD = timedelta(days=120)

#: Midnight US Eastern in UTC: 04:00 under EDT, 05:00 under EST. These hours
#: only NOMINATE a row. ESPN's ``timeValid`` decides whether it is marked.
PLACEHOLDER_UTC_HOURS = (4, 5)

#: Upper bound on scoreboard reads per run.
MAX_BOARDS = 40


@dataclass(frozen=True)
class CandidateRow:
    event_id: int
    sport_key: str
    espn_id: str
    commence_time: datetime
    event_tags: Any


def candidate_statement(now: datetime):
    """Scheduled, ESPN-anchored rows sitting on a midnight-Eastern stamp."""
    from app.models.models import Event, Sport

    utc_commence = func.timezone("UTC", Event.commence_time)
    return (
        select(
            Event.id,
            Sport.key,
            Event.espn_id,
            Event.commence_time,
            Event.event_tags,
        )
        .join(Sport, Sport.id == Event.sport_id)
        .where(
            Event.status == "scheduled",
            Event.espn_id.isnot(None),
            Event.commence_time > now,
            Event.commence_time <= now + LOOKAHEAD,
            extract("minute", utc_commence) == 0,
            extract("hour", utc_commence).in_(PLACEHOLDER_UTC_HOURS),
            Sport.key.in_(sorted(ESPN_SPORT_MAPPING)),
        )
        .order_by(Event.commence_time, Event.id)
    )


def board_day(commence_time: datetime) -> str:
    """The ESPN board a placeholder sits on: its UTC date, as ``YYYYMMDD``.

    ESPN's boards are dated in Eastern time, and at midnight Eastern the UTC
    date is the same day. That holds only for the two candidate hours, which
    are the only rows this pass reads.
    """
    if commence_time.tzinfo is None:
        commence_time = commence_time.replace(tzinfo=timezone.utc)
    return commence_time.astimezone(timezone.utc).strftime("%Y%m%d")


def group_by_board(rows: Iterable[CandidateRow]) -> dict[tuple[str, str], list[CandidateRow]]:
    grouped: dict[tuple[str, str], list[CandidateRow]] = defaultdict(list)
    for row in rows:
        grouped[(row.sport_key, board_day(row.commence_time))].append(row)
    return dict(grouped)


def plan_row(row: CandidateRow, board_by_id: dict[str, Any]) -> tuple[str, Optional[list[str]]]:
    """``(outcome, desired)`` for one row against its day's board.

    ``desired`` is None when nothing is to be written. The outcomes are
    ``not_on_board``, ``silent`` (flag absent), ``unchanged``, ``mark`` and
    ``clear``.
    """
    ee = board_by_id.get(str(row.espn_id))
    if ee is None:
        return "not_on_board", None
    desired = desired_espn_start_placeholder_tags(
        time_valid=getattr(ee, "time_valid", True),
        time_announced=getattr(ee, "time_announced", False),
        espn_date=getattr(ee, "date", None),
        commence_time=row.commence_time,
    )
    if desired is None:
        return "silent", None
    current = espn_start_placeholder_tags(row.event_tags)
    if sorted(current) == sorted(desired):
        return "unchanged", None
    return ("mark" if desired else "clear"), desired


async def _run_mark_espn_start_placeholders(apply: bool = True) -> dict:
    from app.services.espn_api import ESPN_FULL_SLATE_GROUPS, ESPNAPIService
    from app.tasks.base import get_task_session
    from app.utils.start_placeholder_write import write_espn_start_placeholder_tags

    now = datetime.now(timezone.utc)
    stats: dict[str, Any] = {
        "apply": apply,
        "candidates": 0,
        "boards_read": 0,
        "boards_dark": 0,
        "boards_skipped_cap": 0,
        "not_on_board": 0,
        "silent": 0,
        "unchanged": 0,
        "mark": 0,
        "clear": 0,
        "marked_ids": [],
        "cleared_ids": [],
        "errors": [],
    }

    async with get_task_session() as session:
        result = await session.execute(candidate_statement(now))
        rows = [
            CandidateRow(
                event_id=r[0], sport_key=r[1], espn_id=str(r[2]),
                commence_time=r[3], event_tags=r[4],
            )
            for r in result.all()
        ]
        stats["candidates"] = len(rows)
        if not rows:
            stats["status"] = "no_candidates"
            return stats

        groups = group_by_board(rows)
        espn = ESPNAPIService()
        writes: list[tuple[int, list[str]]] = []
        try:
            for index, ((sport_key, day), day_rows) in enumerate(sorted(groups.items())):
                if index >= MAX_BOARDS:
                    stats["boards_skipped_cap"] += 1
                    continue
                try:
                    board = await espn.get_scoreboard(
                        sport_key, date=day, groups=ESPN_FULL_SLATE_GROUPS.get(sport_key)
                    )
                except Exception as e:  # one day's read must not cost the rest
                    stats["errors"].append(f"{sport_key}/{day}: {e}")
                    continue
                if board is None:
                    # ESPN did not answer: absence proves nothing, so nothing moves.
                    stats["boards_dark"] += 1
                    continue
                stats["boards_read"] += 1
                board_by_id = {str(ee.espn_id): ee for ee in board if ee.espn_id}
                for row in day_rows:
                    outcome, desired = plan_row(row, board_by_id)
                    stats[outcome] += 1
                    if desired is not None:
                        writes.append((row.event_id, desired))
                        key = "marked_ids" if desired else "cleared_ids"
                        stats[key].append(row.event_id)
        finally:
            await espn.close()

        if apply and writes:
            for event_id, desired in writes:
                await write_espn_start_placeholder_tags(session, event_id, desired)
            await session.commit()

    stats["status"] = "complete" if not stats["errors"] else "partial"
    logger.info(
        "ESPN start placeholders (#8981): %d candidates, %d boards (%d dark), "
        "%d marked, %d cleared, %d unchanged, apply=%s",
        stats["candidates"], stats["boards_read"], stats["boards_dark"],
        stats["mark"], stats["clear"], stats["unchanged"], apply,
    )
    return stats
