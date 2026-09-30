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
explicit ``timeValid: true`` at the row's own minute clears the mark (the
equal-instant case). ``timeValid: true`` at another minute KEEPS it: this pass
never moves a start, so until a rail writes the announced time the row still
carries the stand-in, and clearing served "Oct 2 9:00 PM PDT" again
(2026-09-27). An absent flag or a dark board changes nothing.

**And once ESPN announces, this pass writes the time (#8841).** A row whose
stored start carries a placeholder mark — ESPN's or StatPal's — is nominated
whatever its clock, and when its day's board says ``timeValid: true`` at another
minute on the same Eastern date, the announced start is written over the stand-in
(``announced_start_over_placeholder`` holds the rule). The marks name the old
instant, so the TBD retires by the write. Red Sox @ Yankees Wild Card Game 1
(15319563) sat on StatPal's 20:00Z with the 00:00Z first pitch public on ESPN
and MLB; three of the four Wild Card rows had no ``espn_id`` at all, so a row
without one is found on its board by its two team names, in its own
orientation, and only when exactly one game on that board matches and no other
row of ours already carries that game's id. It never writes an id.

Bounded by construction: one scoreboard read per (sport, day) among the
candidates, capped at :data:`MAX_BOARDS`, soonest day first. On 2026-09-27
that was 8 reads.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

import re

from sqlalchemy import String, and_, cast, extract, func, or_, select

from app.utils.sport_keys import ESPN_SPORT_MAPPING
from app.utils.start_placeholder import (
    EASTERN,
    announced_start_over_placeholder,
    desired_espn_start_placeholder_tags,
    espn_start_placeholder_tags,
)
from app.utils.start_time_authority import provider_may_set_start

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


#: Every start-placeholder mark, either provider's, begins with this.
PLACEHOLDER_MARK_PREFIX = "provenance:start-placeholder:"


@dataclass(frozen=True)
class CandidateRow:
    event_id: int
    sport_key: str
    espn_id: Optional[str]
    commence_time: datetime
    event_tags: Any
    commence_time_source: Optional[str] = None
    home_team_name: Optional[str] = None
    away_team_name: Optional[str] = None


def candidate_statement(now: datetime):
    """Scheduled rows a placeholder may be standing in for.

    Two arms: an ESPN-anchored row on a midnight-Eastern stamp (ESPN may still
    be holding its place), or any row carrying a placeholder mark (ESPN may
    since have announced the time, #8841).
    """
    from app.models.models import Event, Sport

    utc_commence = func.timezone("UTC", Event.commence_time)
    return (
        select(
            Event.id,
            Sport.key,
            Event.espn_id,
            Event.commence_time,
            Event.event_tags,
            Event.commence_time_source,
            Event.home_team_name,
            Event.away_team_name,
        )
        .join(Sport, Sport.id == Event.sport_id)
        .where(
            Event.status == "scheduled",
            Event.commence_time > now,
            Event.commence_time <= now + LOOKAHEAD,
            Sport.key.in_(sorted(ESPN_SPORT_MAPPING)),
            or_(
                and_(
                    Event.espn_id.isnot(None),
                    extract("minute", utc_commence) == 0,
                    extract("hour", utc_commence).in_(PLACEHOLDER_UTC_HOURS),
                ),
                cast(Event.event_tags, String).contains(PLACEHOLDER_MARK_PREFIX),
            ),
        )
        .order_by(Event.commence_time, Event.id)
    )


def board_day(commence_time: datetime) -> str:
    """The ESPN board a row sits on: its Eastern date, as ``YYYYMMDD``.

    ESPN dates its boards in Eastern time: the Sep 29 board carries Cubs @
    Padres at ``2026-09-30T02:00Z``, 10 PM Eastern on the 29th.
    """
    if commence_time.tzinfo is None:
        commence_time = commence_time.replace(tzinfo=timezone.utc)
    return commence_time.astimezone(EASTERN).strftime("%Y%m%d")


def _team_key(name: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").casefold())


def _espn_team_name(team: Any) -> str:
    if team is None:
        return ""
    return getattr(team, "display_name", None) or getattr(team, "name", None) or ""


def board_game_for(row: CandidateRow, board: list) -> tuple[str, Any]:
    """``(how, game)``: the game on the row's board the row is.

    By ``espn_id`` when the row has one — and then only by it. Otherwise by the
    row's two team names in the row's own orientation, and only when exactly one
    game on the board matches: two is a doubleheader or a bad read, and nobody
    can say which. ``how`` is ``by_id``, ``by_teams``, ``ambiguous`` or
    ``not_on_board``.
    """
    if row.espn_id:
        for ee in board:
            if str(getattr(ee, "espn_id", "")) == str(row.espn_id):
                return "by_id", ee
        return "not_on_board", None
    home, away = _team_key(row.home_team_name), _team_key(row.away_team_name)
    if not home or not away:
        return "not_on_board", None
    matches = [
        ee for ee in board
        if _team_key(_espn_team_name(getattr(ee, "home_team", None))) == home
        and _team_key(_espn_team_name(getattr(ee, "away_team", None))) == away
    ]
    if len(matches) == 1:
        return "by_teams", matches[0]
    return ("ambiguous" if matches else "not_on_board"), None


def plan_move(row: CandidateRow, ee: Any) -> tuple[str, Optional[datetime]]:
    """``(outcome, announced)`` — whether to write ESPN's announced start.

    ``move`` carries the start; ``outranked`` means the row's own source
    outranks ESPN's (the registry's rule); ``none`` means there is nothing to
    fill in.
    """
    announced = announced_start_over_placeholder(
        event_tags=row.event_tags,
        commence_time=row.commence_time,
        status="scheduled",
        time_announced=getattr(ee, "time_announced", False),
        espn_status=getattr(ee, "status", None),
        espn_date=getattr(ee, "date", None),
    )
    if announced is None:
        return "none", None
    if not provider_may_set_start(row.commence_time_source, "espn"):
        return "outranked", None
    return "move", announced


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
    from app.utils.start_placeholder_write import (
        write_announced_start,
        write_espn_start_placeholder_tags,
    )

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
        "move": 0,
        "moves": [],
        "move_outranked": 0,
        "move_ambiguous": 0,
        "move_id_held_elsewhere": 0,
        "move_stale": 0,
        "errors": [],
    }

    async with get_task_session() as session:
        result = await session.execute(candidate_statement(now))
        rows = [
            CandidateRow(
                event_id=r[0], sport_key=r[1],
                espn_id=str(r[2]) if r[2] is not None else None,
                commence_time=r[3], event_tags=r[4],
                commence_time_source=r[5], home_team_name=r[6], away_team_name=r[7],
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
        # (row, announced, how, game espn_id) — decided per board, written below.
        moves: list[tuple[CandidateRow, datetime, str, str]] = []
        try:
            ordered = sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0]))
            for index, ((sport_key, day), day_rows) in enumerate(ordered):
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
                    how, ee = board_game_for(row, board)
                    if how == "ambiguous":
                        stats["move_ambiguous"] += 1
                    if ee is not None:
                        move, announced = plan_move(row, ee)
                        if move == "outranked":
                            stats["move_outranked"] += 1
                        elif move == "move":
                            moves.append((row, announced, how, str(ee.espn_id)))
                            continue
                    if not row.espn_id:
                        continue
                    outcome, desired = plan_row(row, board_by_id)
                    stats[outcome] += 1
                    if desired is not None:
                        writes.append((row.event_id, desired))
                        key = "marked_ids" if desired else "cleared_ids"
                        stats[key].append(row.event_id)
        finally:
            await espn.close()

        # A row found by its team names may not take a game another row of
        # ours already carries by id: that is two rows for one game, and
        # which one is the game is lane1's to decide, not this pass's.
        by_teams_ids = sorted({gid for _r, _a, how, gid in moves if how == "by_teams"})
        held: set[str] = set()
        if by_teams_ids:
            from app.models.models import Event

            held = {
                str(r[0])
                for r in (
                    await session.execute(
                        select(Event.espn_id).where(Event.espn_id.in_(by_teams_ids))
                    )
                ).all()
            }
        planned_moves = []
        for row, announced, how, gid in moves:
            if how == "by_teams" and gid in held:
                stats["move_id_held_elsewhere"] += 1
                continue
            planned_moves.append((row, announced))

        for row, announced in planned_moves:
            moved = True
            if apply:
                moved = await write_announced_start(
                    session, row.event_id, row.commence_time, announced
                )
            if not moved:
                stats["move_stale"] += 1
                continue
            stats["move"] += 1
            stats["moves"].append({
                "event_id": row.event_id,
                "from": row.commence_time.isoformat(),
                "to": announced.isoformat(),
                "from_source": row.commence_time_source,
            })
            logger.info(
                "ESPN announced start (#8841): event %s %s -> %s (was %s), apply=%s",
                row.event_id, row.commence_time.isoformat(), announced.isoformat(),
                row.commence_time_source, apply,
            )

        if apply and writes:
            for event_id, desired in writes:
                await write_espn_start_placeholder_tags(session, event_id, desired)
        if apply and (writes or planned_moves):
            await session.commit()

    stats["status"] = "complete" if not stats["errors"] else "partial"
    logger.info(
        "ESPN start placeholders (#8981): %d candidates, %d boards (%d dark), "
        "%d marked, %d cleared, %d unchanged, %d announced starts written, apply=%s",
        stats["candidates"], stats["boards_read"], stats["boards_dark"],
        stats["mark"], stats["clear"], stats["unchanged"], stats["move"], apply,
    )
    return stats
