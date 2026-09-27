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

A SAME-DAY move (#8952) carries no note: ESPN just lists the game at a new hour.
That arm reads one board: ESPN lists the pairing exactly once on D, exactly one
row carries that game's id and is dated D, and the ONE other row for the teams
on D has no id and no score. See the loop at the end of the planner.

A POSTPONED game (#4865) carries no "Rescheduled from" note either. On
2026-09-22 ESPN listed TOR @ BAL (401817035) as ``STATUS_POSTPONED`` ("Rain -
Makeup date Sep 23") and made it up as 401923610, "Doubleheader - Game 1 -
Makeup from Sep 22". Our odds_api row took 401817035 and moved to the makeup
hour (15316846, final 4-2); StatPal's pre-load row stayed on the 22nd at 0-0,
``suspended``, and search printed it as "No result reported". That arm reads:
ESPN lists the pairing on D exactly once and that game is postponed; exactly
one of our rows is the made-up game — it carries the postponed game's id and is
dated off D, or it carries the id of a game whose note says "Makeup from D";
and the one other row for the teams on D has no id and no result. A 0-0 on a
row that is not completed is not a result (StatPal writes it on a rain-out).

An UNLISTED ADJACENT-DAY row (#9187) is the same shape one day over, and it
is not MLB's: on 2026-09-27 the Odds API listed Chicago @ Vegas twice — its real
event at 2026-09-30T02:40Z and a phantom ``ec5a4b4a…`` at 21:30:10Z, nineteen
hours later — while ESPN listed ONE game (401891775, 02:30Z, the 29th in ET).
Our row for the phantom (15320181) has no ESPN id, and search showed the game on
two days. That arm reads two boards: ESPN lists the pairing exactly once on D
and exactly one row carries that game's id, dated D; ESPN's board for the
neighbouring day, READ and listing other games, lists no game between the two
teams in either orientation; and the one row for the same home and away team on that
neighbouring day has no id and no score. It is enabled per sport by the caller
(``adjacent_day_arm``), and it refuses any board game that is not preseason or
regular season — ESPN lists a postseason's "If Necessary" games, but a series is
where consecutive-day games between one pair are real, so it is not asked.

Anything short of exactly one canonical and exactly one ghost is a refusal, not
a guess. Cubs @ Red Sox on the same day is the control: its game 1 is
"Rescheduled from Sep. 27", our Saturday row for that matchup is a real game
(ESPN lists it on the 26th), and D = the 27th holds no row — so nothing is
labelled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, Mapping, Optional
from zoneinfo import ZoneInfo

from app.utils.soccer_ghost_twins import GhostTag

#: ESPN dates an MLB game's note in the home market's calendar; every row this
#: rule can act on is a US game, and ET is the date the note and the league use.
MLB_LOCAL_TZ = ZoneInfo("America/New_York")

_RESCHEDULED_RE = re.compile(r"rescheduled\s+from\s+([a-z]{3,9})\.?\s+(\d{1,2})", re.I)
_MAKEUP_RE = re.compile(r"makeup\s+from\s+([a-z]{3,9})\.?\s+(\d{1,2})", re.I)

#: ESPN's status for a game called off on its day and owed a makeup.
ESPN_POSTPONED = "STATUS_POSTPONED"
#: ESPN's ``season.type``: 1 preseason, 2 regular season, 3 postseason. The
#: adjacent-day arm (#9187) acts only on the first two.
ESPN_UNSERIALISED_SEASON_TYPES = frozenset({1, 2})

#: Statuses on which a 0-0 is a placeholder, not a result: StatPal leaves a
#: rained-out row ``suspended`` at 0-0 (15317711, 2026-09-22).
_PLACEHOLDER_SCORE_STATUSES = frozenset({"suspended", "scheduled"})
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
    return _note_date(headlines, played_on=played_on, pattern=_RESCHEDULED_RE)


def makeup_from(headlines: Iterable[object], *, played_on: date) -> Optional[date]:
    """The date a "Makeup from Sep 22" note says this game was postponed ON."""
    return _note_date(headlines, played_on=played_on, pattern=_MAKEUP_RE)


def _note_date(
    headlines: Iterable[object], *, played_on: date, pattern: re.Pattern
) -> Optional[date]:
    found: set[date] = set()
    for headline in headlines:
        match = pattern.search(str(headline or ""))
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


def score_is_placeholder(
    *, home_score: object, away_score: object, status: object
) -> bool:
    """A 0-0 on a row that was never completed — not a result."""
    return (
        home_score == 0
        and away_score == 0
        and str(status or "") in _PLACEHOLDER_SCORE_STATUSES
    )


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
    status: Optional[str] = None
    makeup_from: Optional[date] = None
    season_type: Optional[int] = None


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
    status = ((event.get("status") or {}).get("type") or {}).get("name")
    try:
        season_type: Optional[int] = int((event.get("season") or {}).get("type"))
    except (TypeError, ValueError):
        season_type = None
    return BoardGame(
        espn_id=espn_id,
        home_team_id=teams.get("home"),
        away_team_id=teams.get("away"),
        local_date=played_on,
        rescheduled_from=rescheduled_from(headlines, played_on=played_on),
        status=str(status) if status else None,
        makeup_from=makeup_from(headlines, played_on=played_on),
        season_type=season_type,
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
    score_is_placeholder: bool = False


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
    #: Sole-on-its-board games that had a second row for the pairing that day.
    same_day_games_with_extra_rows: int = 0
    postponed_games_seen: int = 0
    #: Sole-on-its-board games with a row for the pairing on a neighbouring day
    #: whose board lists no game between the two teams (#9187).
    adjacent_day_games_with_extra_rows: int = 0
    already_tagged: int = 0
    dark_days: list[date] = field(default_factory=list)


def _decide(
    plan: ReschedulePlan,
    rows: list[MlbRow],
    decided: dict[int, GhostTag],
    contested: set[int],
    canonical: MlbRow,
    day: date,
    label: str,
    *,
    reason: str,
    refuse_empty: bool,
    placeholder_score_ok: bool = False,
) -> bool:
    """Label the ONE other row for ``canonical``'s pairing on ``day``, or refuse.

    Returns whether any other row existed. ``refuse_empty`` is False for the
    same-day arm, where no second row is simply the normal case.
    """
    home, away = _team(canonical.home_team_name), _team(canonical.away_team_name)
    others = [
        r
        for r in rows
        if r.event_id != canonical.event_id
        and _team(r.home_team_name) == home
        and _team(r.away_team_name) == away
        and local_date(r.commence_time) == day
    ]
    if not others and not refuse_empty:
        return False
    if len(others) != 1:
        plan.refusals.append(f"{label}: {len(others)} rows for the matchup on {day}")
        return bool(others)
    ghost = others[0]
    scored = ghost.has_final_score and not (
        placeholder_score_ok and ghost.score_is_placeholder
    )
    if ghost.espn_id or scored:
        plan.refusals.append(
            f"{label}: row {ghost.event_id} on {day} is anchored or scored"
        )
        return True
    if ghost.is_duplicate_tagged:
        plan.already_tagged += 1
        return True
    tag = GhostTag(
        ghost_id=ghost.event_id, canonical_id=canonical.event_id, reason=reason
    )
    prior = decided.get(ghost.event_id)
    if prior and prior.canonical_id != tag.canonical_id:
        contested.add(ghost.event_id)
    decided.setdefault(ghost.event_id, tag)
    return True


def plan_reschedule_ghosts(
    rows: Iterable[MlbRow],
    boards: Mapping[date, Optional[tuple[BoardGame, ...]]],
    *,
    adjacent_day_arm: bool = False,
) -> ReschedulePlan:
    """Decide every reschedule ghost in the window. Pure.

    ``boards`` maps each ET date in the window to that day's games, or ``None``
    when ESPN did not answer — a dark board proves nothing and every decision
    that needs it is refused. ``adjacent_day_arm`` enables the #9187 arm; the
    caller names the sports it is for.
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

            _decide(
                plan,
                rows,
                decided,
                contested,
                canonical,
                moved_from,
                label,
                reason=f"mlb_reschedule: {label}",
                refuse_empty=True,
            )

    # THE SAME-DAY ARM (#8952). A game moved to another hour of the SAME day
    # carries no "Rescheduled from" note, so the loop above never sees it. On
    # 2026-09-27 ESPN moved BAL @ NYY from 19:20Z to 17:05Z; the odds_api row at
    # 17:05 took ESPN's id, and StatPal's pre-load row stayed at 19:20. The
    # evidence is the same shape, read off one board instead of two: ESPN lists
    # the pairing EXACTLY ONCE on D (so D is not a doubleheader), exactly one of
    # our rows carries that game's id and is dated D, and one other row for the
    # same teams on D has no id and no score. Anything else is left alone.
    for day, games in sorted(boards.items()):
        games = games or ()
        for game in games:
            if not (game.home_team_id and game.away_team_id):
                continue
            pair = {game.home_team_id, game.away_team_id}
            if sum({g.home_team_id, g.away_team_id} == pair for g in games) != 1:
                continue
            canonicals = by_espn.get(game.espn_id, [])
            if len(canonicals) != 1:
                continue
            canonical = canonicals[0]
            if (
                canonical.is_duplicate_tagged
                or local_date(canonical.commence_time) != day
            ):
                continue
            label = f"espn {game.espn_id} (sole {day.isoformat()} game for the pair)"
            if _decide(
                plan,
                rows,
                decided,
                contested,
                canonical,
                day,
                label,
                reason=f"mlb_same_day_move: {label}",
                refuse_empty=False,
            ):
                plan.same_day_games_with_extra_rows += 1

    # THE POSTPONED ARM (#4865) — see the module docstring for the specimen.
    for day, games in sorted(boards.items()):
        games = games or ()
        for game in games:
            if game.status != ESPN_POSTPONED:
                continue
            if not (game.home_team_id and game.away_team_id):
                continue
            plan.postponed_games_seen += 1
            label = f"espn {game.espn_id} (postponed {day.isoformat()})"
            pair = {game.home_team_id, game.away_team_id}
            listed = sum({g.home_team_id, g.away_team_id} == pair for g in games)
            if listed != 1:
                plan.refusals.append(
                    f"{label}: ESPN lists the matchup {listed} times on {day}"
                )
                continue
            made_up = {
                r.event_id: r
                for r in by_espn.get(game.espn_id, [])
                if local_date(r.commence_time) != day
            }
            for other in boards.values():
                for makeup in other or ():
                    if (
                        makeup.makeup_from == day
                        and {makeup.home_team_id, makeup.away_team_id} == pair
                    ):
                        for r in by_espn.get(makeup.espn_id, []):
                            made_up[r.event_id] = r
            if len(made_up) != 1:
                plan.refusals.append(
                    f"{label}: {len(made_up)} rows are the made-up game"
                )
                continue
            canonical = next(iter(made_up.values()))
            if canonical.is_duplicate_tagged:
                plan.refusals.append(
                    f"{label}: canonical {canonical.event_id} is itself a duplicate"
                )
                continue
            _decide(
                plan,
                rows,
                decided,
                contested,
                canonical,
                day,
                label,
                reason=f"mlb_postponed: {label}",
                refuse_empty=False,
                placeholder_score_ok=True,
            )

    # THE ADJACENT-DAY ARM (#9187) — see the module docstring for the specimen.
    # The same-day arm's evidence with the ghost one ET day over, plus the
    # second board: ESPN's board for that neighbouring day is READ and lists no
    # game between the two teams, in either orientation, so the row there is
    # not a home-and-home, a series game or a doubleheader ESPN knows about.
    for day, games in sorted(boards.items()) if adjacent_day_arm else ():
        games = games or ()
        for game in games:
            if not (game.home_team_id and game.away_team_id):
                continue
            if game.season_type not in ESPN_UNSERIALISED_SEASON_TYPES:
                continue
            pair = {game.home_team_id, game.away_team_id}
            if sum({g.home_team_id, g.away_team_id} == pair for g in games) != 1:
                continue
            canonicals = by_espn.get(game.espn_id, [])
            if len(canonicals) != 1:
                continue
            canonical = canonicals[0]
            if (
                canonical.is_duplicate_tagged
                or local_date(canonical.commence_time) != day
            ):
                continue
            for neighbour in (day - timedelta(days=1), day + timedelta(days=1)):
                board = boards.get(neighbour)
                # Dark proves nothing, and neither does an EMPTY board: ESPN's
                # answer for "no games that day" and "nothing to report" is the
                # same body (gotcha #53), and here that absence is the licence.
                if not board:
                    continue
                if any({g.home_team_id, g.away_team_id} == pair for g in board):
                    continue
                label = (
                    f"espn {game.espn_id} (sole {day.isoformat()} game for the pair; "
                    f"none on {neighbour.isoformat()})"
                )
                if _decide(
                    plan,
                    rows,
                    decided,
                    contested,
                    canonical,
                    neighbour,
                    label,
                    reason=f"unlisted_adjacent_day: {label}",
                    refuse_empty=False,
                ):
                    plan.adjacent_day_games_with_extra_rows += 1

    for ghost_id in sorted(contested):
        plan.refusals.append(f"row {ghost_id}: two canonical games claim it")
    plan.tags = [t for gid, t in sorted(decided.items()) if gid not in contested]
    return plan
