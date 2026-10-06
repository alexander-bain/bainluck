"""Which postseason games are CERTAIN to be played (#9216).

**SHIP: Braves–Phillies and Astros–White Sox Wild Card Game 2 (Wed 9/30) get a
page with their Kalshi price as soon as ESPN schedules them.** (Pillar: MATCHING.)
Kalshi listed both on 2026-09-28 02:48Z and they had nowhere to attach; ESPN had
listed them since the bracket was set, but our ESPN passes read only today's
board, and the Odds API lists a Game 2 only once Game 1 is played (#8956).

ESPN's board says which game of a series each game is, and how the series
stands. Measured on ``baseball/mlb/scoreboard?dates=20260930`` and ``20261001``,
2026-09-28 05:3xZ::

    competitions[0].notes[0].headline  "NLWC - Game 2"
                                       "NLWC - Game 3 If Necessary"
    competitions[0].series             {"type": "playoff", "completed": false,
                                        "totalCompetitions": 3,
                                        "competitors": [{"wins": 0}, {"wins": 0}]}

**The rule is arithmetic, never the label.** Game ``k`` of a best-of-``N`` is
certain when nobody can have clinched before it: the leader, winning every game
still to be played before it, stays short of the wins needed (``N // 2 + 1``)::

    max(wins) + (k - 1 - games played) < N // 2 + 1

Three cases of that one inequality, each its own reason: ``k`` at most the wins
needed (true at any standings), ``k`` the NEXT game of a series nobody has won
yet, and a later game the leader still cannot reach in time (#10625: Game 4 of
an LDS at 1–1 — Game 3 makes it 2–1, and Game 4 is played whoever wins).
ESPN's "If Necessary" is the schedule's label, and it can outlive the moment the
game became certain (a Wild Card at 1–1), so it is not read at all.

**Stale standings fail safe.** ESPN's win counts only ever lag the games. A
lagging count can make a game that already became certain look uncertain (we
create it an hour later), but never the reverse: every game played but not yet
counted adds at most one to the leader and exactly one to games played, so the
left side read off a lagging count is never below the true one.

Pure: imports nothing from the app, so both the ESPN parser and the pass that
creates rows can read it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

#: "NLWC - Game 2", "ALDS - Game 4 If Necessary", "West Finals - Game 7".
_GAME_NUMBER = re.compile(r"\bgame\s+(\d{1,2})\b", re.IGNORECASE)


@dataclass(frozen=True)
class PlayoffSeries:
    """What ESPN's board says about one game's place in its series."""

    game_number: Optional[int]
    total_games: Optional[int]
    wins: tuple[int, ...]
    completed: Optional[bool]


def game_number_from_headlines(headlines: Iterable[Any]) -> Optional[int]:
    """The one game number the headlines state, or None.

    Two headlines naming DIFFERENT numbers is not a game number, it is a
    contradiction, and a contradiction creates nothing.
    """
    found = set()
    for headline in headlines:
        if not isinstance(headline, str):
            continue
        for match in _GAME_NUMBER.finditer(headline):
            found.add(int(match.group(1)))
    if len(found) != 1:
        return None
    return found.pop()


def parse_playoff_series(competition: Any) -> Optional[PlayoffSeries]:
    """``competitions[0]`` → :class:`PlayoffSeries`, or None when it is not one.

    None for anything that is not ESPN's ``type: playoff`` series object. Every
    field that fails to read is left None/empty rather than guessed, and
    :func:`certain_to_be_played` refuses on any gap.
    """
    if not isinstance(competition, dict):
        return None
    series = competition.get("series")
    if not isinstance(series, dict) or series.get("type") != "playoff":
        return None

    headlines = [
        note.get("headline")
        for note in (competition.get("notes") or [])
        if isinstance(note, dict)
    ]

    total = series.get("totalCompetitions")
    total_games = total if isinstance(total, int) and not isinstance(total, bool) else None

    wins: list[int] = []
    for competitor in series.get("competitors") or []:
        value = competitor.get("wins") if isinstance(competitor, dict) else None
        if not isinstance(value, int) or isinstance(value, bool):
            wins = []
            break
        wins.append(value)

    completed = series.get("completed")
    return PlayoffSeries(
        game_number=game_number_from_headlines(headlines),
        total_games=total_games,
        wins=tuple(wins),
        completed=completed if isinstance(completed, bool) else None,
    )


def certain_to_be_played(series: Optional[PlayoffSeries]) -> tuple[bool, str]:
    """``(certain, reason)`` for one game of a series.

    Fails closed on every gap: no series, no game number, no length, not exactly
    two win counts, or ESPN not saying whether the series is over.
    """
    if series is None:
        return False, "not_a_series"
    k = series.game_number
    n = series.total_games
    if k is None or k < 1:
        return False, "no_game_number"
    if n is None or n < 1 or k > n:
        return False, "no_series_length"
    if len(series.wins) != 2:
        return False, "no_standings"
    if series.completed is None:
        return False, "no_completed_flag"

    needed = n // 2 + 1
    leader, played = max(series.wins), sum(series.wins)
    if series.completed or leader >= needed:
        return False, "series_over"
    if k <= needed:
        return True, "within_wins_needed"
    if k == played + 1:
        return True, "next_game_of_open_series"
    # A later game: the leader would have to win every game before it to
    # clinch first (#10625). A number at or below the games counted is a game
    # the standings say is already played — not this arm's to vouch for.
    if k > played and leader + (k - 1 - played) < needed:
        return True, "leader_cannot_clinch_before_it"
    return False, "if_necessary"
