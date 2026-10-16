"""#11152 — a playoff game that will never be played stops being listed.

**SHIP: Sports stops offering Brewers–Dodgers Game 5 after the series ended.**
(Pillar: TRUTH — the schedule lifecycle.)

The Odds API lists a series' "if necessary" games before they are certain. On
2026-10-15 03:32Z it listed NLCS Game 5 (our row 15330460, Oct 17 00:00Z, no ESPN
id). Milwaukee won Game 4 that night and the series 4–0, and nothing retired the
row: no source ever reports on a game that is not played, so it sat on Sports and
Search as an upcoming game.

The judgement is here; :mod:`app.tasks.unplayed_series_game_sweep` reads our rows
and ESPN's boards and writes the retirement.

THE PROOF IS ESPN SAYING THE SERIES IS OVER
═══════════════════════════════════════════

ESPN's board carries each playoff game's series. Measured on
``baseball/mlb/scoreboard?dates=20261015``, 2026-10-16 23:4xZ, game 401908033
(NLCS Game 4, our row 15330459)::

    status.type.name   "STATUS_FINAL"
    season.type        3
    series             {"type": "playoff", "completed": true,
                        "summary": "MIL wins series 4-0", "totalCompetitions": 7,
                        "competitors": [{"id": "19", "wins": 0},
                                        {"id": "8",  "wins": 4}]}

A series is OVER only when every signal agrees: the game is final, it is a
postseason game, ESPN says ``completed: true``, AND the arithmetic agrees (the
leader has ``N // 2 + 1`` wins of a best-of-``N``). Any gap or contradiction is
"not over" — the rule fails closed, exactly as
:func:`app.utils.postseason_series.certain_to_be_played` does in the other
direction.

WHAT IS RETIRED, AND WHAT NEVER IS
══════════════════════════════════

The row that carries the clinching game's ESPN id is the anchor (ruling 048: an
id, not a name, says which pair this is). A row is retired only when it is:

* the same two teams, in either orientation (series alternate venues);
* dated on a LATER ET day than the clinching game;
* unanchored (no ESPN id — ESPN never vouched for it) and unscored;
* still on the schedule shelf (``scheduled``/``live``/``suspended``);
* on a day whose ESPN board was READ and lists no game for the pair.

And no board in the window may list the pair after the clinch at all — a listed
later game contradicts "the series is over", so the whole series is refused.

Two teams meet at most once in a postseason, so once their series is over a later
row for the pair inside a few days is a game that will not be played. An EMPTY
board on the row's own day is accepted, deliberately: the proof is the clinch,
read off a non-empty board that ESPN answered; the row's day is only asked to
not contradict it. A DARK board (``None``) is refused — it may hide a game.

Controls the tests pin: an open series needing Game 5 (3–1, not completed)
retires nothing; a doubleheader/rescheduled pair listed on the row's day is
refused; a dark board refuses; an anchored or scored row is refused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Mapping, Optional

from app.utils.mlb_reschedule_ghosts import local_date, score_is_placeholder
from app.utils.postseason_series import PlayoffSeries, parse_playoff_series

#: ESPN's ``season.type`` for the postseason.
ESPN_POSTSEASON = 3
ESPN_FINAL = "STATUS_FINAL"

#: The statuses a row can be retired FROM — the schedule shelf. A ``completed``
#: or ``closed`` row is the reader's "final", and retiring one is a different
#: question this rule does not ask.
RETIRABLE_STATUSES = frozenset({"scheduled", "live", "suspended"})

#: The element the retirement adds to ``event_tags``. ``provenance:`` so the
#: taxonomy rewrite carries it (``carry_provenance_tags``); the backup table, not
#: this tag, is the restore's scope.
TAG_PREFIX = "provenance:unplayed-series-game:espn:"


def retirement_tag(clinching_espn_id: str) -> str:
    return f"{TAG_PREFIX}{clinching_espn_id}"


@dataclass(frozen=True)
class SeriesBoardGame:
    """One game on ESPN's board, reduced to what this rule reads."""

    espn_id: str
    home_team_id: Optional[str]
    away_team_id: Optional[str]
    local_date: date
    status: Optional[str]
    season_type: Optional[int]
    series: Optional[PlayoffSeries]

    @property
    def pair(self) -> Optional[frozenset[str]]:
        if not (self.home_team_id and self.away_team_id):
            return None
        return frozenset({self.home_team_id, self.away_team_id})


def series_board_game_from_espn(event: Mapping) -> Optional[SeriesBoardGame]:
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
    status = ((event.get("status") or {}).get("type") or {}).get("name")
    try:
        season_type: Optional[int] = int((event.get("season") or {}).get("type"))
    except (TypeError, ValueError):
        season_type = None
    return SeriesBoardGame(
        espn_id=espn_id,
        home_team_id=teams.get("home"),
        away_team_id=teams.get("away"),
        local_date=local_date(start),
        status=str(status) if status else None,
        season_type=season_type,
        series=parse_playoff_series(competition),
    )


def series_is_over(game: SeriesBoardGame) -> bool:
    """Every signal says this game's series is decided. Fails closed."""
    s = game.series
    if game.status != ESPN_FINAL or game.season_type != ESPN_POSTSEASON:
        return False
    if s is None or s.completed is not True:
        return False
    n = s.total_games
    if n is None or n < 1 or len(s.wins) != 2:
        return False
    return max(s.wins) >= n // 2 + 1


@dataclass(frozen=True)
class SeriesRow:
    """One of our rows, copied to scalars before judgement (gotcha #6)."""

    event_id: int
    home_team_name: str
    away_team_name: str
    commence_time: datetime
    espn_id: Optional[str]
    status: str
    home_score: Optional[int]
    away_score: Optional[int]
    is_retirement_tagged: bool = False

    @property
    def is_scored(self) -> bool:
        if self.home_score is None and self.away_score is None:
            return False
        return not score_is_placeholder(
            home_score=self.home_score,
            away_score=self.away_score,
            status=self.status,
        )


@dataclass(frozen=True)
class Retirement:
    event_id: int
    clinching_espn_id: str
    clinching_event_id: int
    reason: str


@dataclass
class UnplayedPlan:
    retirements: list[Retirement] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    rows_considered: int = 0
    board_games_read: int = 0
    clinched_series_seen: int = 0
    already_retired: int = 0
    dark_days: list[date] = field(default_factory=list)


def _team(name: object) -> str:
    return " ".join(str(name or "").casefold().split())


def plan_unplayed_series_games(
    rows: Iterable[SeriesRow],
    boards: Mapping[date, Optional[tuple[SeriesBoardGame, ...]]],
) -> UnplayedPlan:
    """Decide every row the window can prove is an unplayed series game. Pure.

    ``boards`` maps each ET date in the window to that day's games, or ``None``
    when ESPN did not answer.
    """
    rows = list(rows)
    plan = UnplayedPlan(rows_considered=len(rows))
    plan.dark_days = sorted(d for d, games in boards.items() if games is None)

    by_espn: dict[str, list[SeriesRow]] = {}
    for row in rows:
        if row.espn_id:
            by_espn.setdefault(str(row.espn_id), []).append(row)

    decided: dict[int, Retirement] = {}
    contested: set[int] = set()

    for day, games in sorted(boards.items()):
        for game in games or ():
            plan.board_games_read += 1
            if not series_is_over(game):
                continue
            plan.clinched_series_seen += 1
            label = f"espn {game.espn_id} (series over {day.isoformat()})"

            pair = game.pair
            if pair is None:
                plan.refusals.append(f"{label}: the board game names no team ids")
                continue
            anchors = by_espn.get(game.espn_id, [])
            if len(anchors) != 1:
                plan.refusals.append(f"{label}: {len(anchors)} rows carry this espn_id")
                continue
            anchor = anchors[0]
            names = frozenset({_team(anchor.home_team_name), _team(anchor.away_team_name)})

            later_listed = sorted(
                d.isoformat()
                for d, other in boards.items()
                if d > day
                for g in other or ()
                if g.pair == pair
            )
            if later_listed:
                plan.refusals.append(
                    f"{label}: ESPN still lists the pair on {later_listed} — "
                    f"the series is not over for the schedule"
                )
                continue

            for row in rows:
                if row.event_id == anchor.event_id:
                    continue
                if frozenset({_team(row.home_team_name), _team(row.away_team_name)}) != names:
                    continue
                row_day = local_date(row.commence_time)
                if row_day <= day:
                    continue
                where = f"{label}: row {row.event_id} on {row_day.isoformat()}"
                if row.is_retirement_tagged:
                    plan.already_retired += 1
                    continue
                if row.espn_id:
                    plan.refusals.append(f"{where} carries an ESPN id")
                    continue
                if row.is_scored:
                    plan.refusals.append(f"{where} carries a score")
                    continue
                if row.status not in RETIRABLE_STATUSES:
                    plan.refusals.append(f"{where} is {row.status!r}, not on the schedule shelf")
                    continue
                if row_day not in boards:
                    plan.refusals.append(f"{where} is outside the window")
                    continue
                if boards[row_day] is None:
                    plan.refusals.append(f"{where}: ESPN's board for that day is dark")
                    continue
                retirement = Retirement(
                    event_id=row.event_id,
                    clinching_espn_id=game.espn_id,
                    clinching_event_id=anchor.event_id,
                    reason=f"unplayed_series_game: {label}",
                )
                prior = decided.get(row.event_id)
                if prior and prior.clinching_espn_id != retirement.clinching_espn_id:
                    contested.add(row.event_id)
                decided.setdefault(row.event_id, retirement)

    for event_id in sorted(contested):
        plan.refusals.append(f"row {event_id}: two clinching games claim it")
    plan.retirements = [r for eid, r in sorted(decided.items()) if eid not in contested]
    return plan
