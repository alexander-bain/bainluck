"""#8547 half 2 — an MLB game that was moved to another day stops being listed
on the day it left.

**SHIP: search for "orioles" stops listing a Saturday Orioles @ Yankees game
that will not be played (row 15316409), and Kalshi's market for it reaches
Friday's game 1 page.** (Pillar: MATCHING.)

On 2026-09-25 ESPN's scoreboard carried BAL @ NYY at 20:05Z with the note
*"Doubleheader - Game 1 - Rescheduled from Sep. 26"*, and its Saturday board
listed no BAL @ NYY at all. Our registry still held the Saturday row StatPal had
minted before the move — no score, no ESPN id — and it held Kalshi's game
market. This module is the pure judgement that names such a row a duplicate of
the game ESPN says replaced it; :mod:`app.tasks.mlb_reschedule_ghost_sweep` reads
the database and ESPN and writes the label.

THE RULE, AND WHY IT IS ID-ANCHORED (ruling 048)
════════════════════════════════════════════════

*Canonical*: the ONE row whose ``espn_id`` IS the ESPN event carrying the
``Rescheduled from <D>`` note. ESPN, not a name or a time, says this game is the
one that was on D.

*Ghost*: same home and away team, no ESPN id, no final score, local (ET) date
D — and it must be the ONLY such row on D.

*Second, independent signal*: ESPN's board for D, READ (not dark), lists no game
between the two teams — so D is genuinely empty for this matchup, not a
doubleheader day and not a series whose other game we would be hiding.

Anything short of exactly one canonical and exactly one ghost is a refusal, not
a guess. Cubs @ Red Sox on the same day is the control: its game 1 is
"Rescheduled from Sep. 27", our Saturday row for that matchup is a real game
(ESPN lists it on the 26th), and D = the 27th holds no row — so nothing is
labelled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Mapping, Optional
from zoneinfo import ZoneInfo

from app.utils.soccer_ghost_twins import GhostTag

#: ESPN dates an MLB game's note in the home market's calendar; every row this
#: rule can act on is a US game, and ET is the date the note and the league use.
MLB_LOCAL_TZ = ZoneInfo("America/New_York")

_RESCHEDULED_RE = re.compile(r"rescheduled\s+from\s+([a-z]{3,9})\.?\s+(\d{1,2})", re.I)
_MONTHS = {
    m: i
    for i, m in enumerate(
        (
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ),
        start=1,
    )
}


def rescheduled_from(headlines: Iterable[object], *, played_on: date) -> Optional[date]:
    """The date a note says this game was moved FROM, or ``None``.

    ESPN writes no year ("Rescheduled from Sep. 26"), so the year is the one
    that puts D nearest the day the game is played. Two notes naming two
    different dates are ambiguous and read as ``None``.
    """
    found: set[date] = set()
    for headline in headlines:
        match = _RESCHEDULED_RE.search(str(headline or ""))
        if not match:
            continue
        month = _MONTHS.get(match.group(1)[:3].lower())
        if not month:
            continue
        day = int(match.group(2))
        candidates = []
        for year in (played_on.year - 1, played_on.year, played_on.year + 1):
            try:
                candidates.append(date(year, month, day))
            except ValueError:
                pass
        if candidates:
            found.add(min(candidates, key=lambda d: abs((d - played_on).days)))
    return found.pop() if len(found) == 1 else None


def local_date(moment: datetime) -> date:
    return moment.astimezone(MLB_LOCAL_TZ).date()


@dataclass(frozen=True)
class BoardGame:
    """One game on ESPN's MLB scoreboard, reduced to what the rule reads."""

    espn_id: str
    home_team_id: Optional[str]
    away_team_id: Optional[str]
    local_date: date
    rescheduled_from: Optional[date]


def board_game_from_espn(event: Mapping) -> Optional[BoardGame]:
    """Parse one raw ESPN scoreboard event. ``None`` when it is not readable."""
    try:
        espn_id = str(event["id"])
        start = datetime.fromisoformat(str(event["date"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return None
    competition = (event.get("competitions") or [{}])[0] or {}
    teams = {}
    for competitor in competition.get("competitors") or []:
        side = competitor.get("homeAway")
        team_id = (competitor.get("team") or {}).get("id") or competitor.get("id")
        if side in ("home", "away") and team_id is not None:
            teams[side] = str(team_id)
    headlines = [
        n.get("headline")
        for n in (competition.get("notes") or [])
        if isinstance(n, Mapping)
    ]
    played_on = local_date(start)
    return BoardGame(
        espn_id=espn_id,
        home_team_id=teams.get("home"),
        away_team_id=teams.get("away"),
        local_date=played_on,
        rescheduled_from=rescheduled_from(headlines, played_on=played_on),
    )


@dataclass(frozen=True)
class MlbRow:
    """One of our MLB rows, copied to scalars before judgement (gotcha #6)."""

    event_id: int
    home_team_name: str
    away_team_name: str
    commence_time: datetime
    espn_id: Optional[str]
    has_final_score: bool
    is_duplicate_tagged: bool


def _team(name: object) -> str:
    return " ".join(str(name or "").casefold().split())


@dataclass
class ReschedulePlan:
    tags: list[GhostTag] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    rows_considered: int = 0
    board_games_read: int = 0
    #: Board games whose ESPN id is carried by one of our rows — the join the
    #: canonical side stands on. Its collapse is the rule losing its population.
    anchored_board_games: int = 0
    rescheduled_games_seen: int = 0
    already_tagged: int = 0
    dark_days: list[date] = field(default_factory=list)


def plan_reschedule_ghosts(
    rows: Iterable[MlbRow],
    boards: Mapping[date, Optional[tuple[BoardGame, ...]]],
) -> ReschedulePlan:
    """Decide every reschedule ghost in the window. Pure.

    ``boards`` maps each ET date in the window to that day's games, or ``None``
    when ESPN did not answer — a dark board proves nothing and every decision
    that needs it is refused.
    """
    rows = list(rows)
    plan = ReschedulePlan(rows_considered=len(rows))
    plan.dark_days = sorted(d for d, games in boards.items() if games is None)

    by_espn: dict[str, list[MlbRow]] = {}
    for row in rows:
        if row.espn_id:
            by_espn.setdefault(str(row.espn_id), []).append(row)

    decided: dict[int, GhostTag] = {}
    contested: set[int] = set()

    for day, games in sorted(boards.items()):
        for game in games or ():
            plan.board_games_read += 1
            if game.espn_id in by_espn:
                plan.anchored_board_games += 1
            moved_from = game.rescheduled_from
            if moved_from is None:
                continue
            plan.rescheduled_games_seen += 1
            label = f"espn {game.espn_id} (from {moved_from.isoformat()})"

            canonicals = by_espn.get(game.espn_id, [])
            if len(canonicals) != 1:
                plan.refusals.append(
                    f"{label}: {len(canonicals)} rows carry this espn_id"
                )
                continue
            canonical = canonicals[0]
            if canonical.is_duplicate_tagged:
                plan.refusals.append(
                    f"{label}: canonical {canonical.event_id} is itself a duplicate"
                )
                continue
            if moved_from not in boards:
                plan.refusals.append(f"{label}: {moved_from} is outside the window")
                continue
            origin_board = boards[moved_from]
            if origin_board is None:
                plan.refusals.append(f"{label}: ESPN's board for {moved_from} is dark")
                continue
            if not (game.home_team_id and game.away_team_id):
                plan.refusals.append(f"{label}: the board game names no team ids")
                continue
            pair = {game.home_team_id, game.away_team_id}
            if any({g.home_team_id, g.away_team_id} == pair for g in origin_board):
                plan.refusals.append(
                    f"{label}: ESPN still lists the matchup on {moved_from}"
                )
                continue

            home, away = _team(canonical.home_team_name), _team(
                canonical.away_team_name
            )
            on_origin = [
                r
                for r in rows
                if r.event_id != canonical.event_id
                and _team(r.home_team_name) == home
                and _team(r.away_team_name) == away
                and local_date(r.commence_time) == moved_from
            ]
            if len(on_origin) != 1:
                plan.refusals.append(
                    f"{label}: {len(on_origin)} rows for the matchup on {moved_from}"
                )
                continue
            ghost = on_origin[0]
            if ghost.espn_id or ghost.has_final_score:
                plan.refusals.append(
                    f"{label}: row {ghost.event_id} on {moved_from} is anchored or scored"
                )
                continue
            if ghost.is_duplicate_tagged:
                plan.already_tagged += 1
                continue

            tag = GhostTag(
                ghost_id=ghost.event_id,
                canonical_id=canonical.event_id,
                reason=f"mlb_reschedule: {label}",
            )
            prior = decided.get(ghost.event_id)
            if prior and prior.canonical_id != tag.canonical_id:
                contested.add(ghost.event_id)
            decided.setdefault(ghost.event_id, tag)

    for ghost_id in sorted(contested):
        plan.refusals.append(f"row {ghost_id}: two rescheduled games claim it")
    plan.tags = [t for gid, t in sorted(decided.items()) if gid not in contested]
    return plan
