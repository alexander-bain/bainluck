"""The set-by-set score of a tennis match, in OUR home/away order — pure.

═══ WHY THIS EXISTS: A CARD THAT MOVES NINE TIMES IN FORTY-FIVE MINUTES ═══

live/057 put two observers on one clock over nine live US Open matches and
timed the live tennis card against its own upstream.  Two numbers came back.

The first is the latency: **median 131.9 s** from ESPN publishing a completed
set to ``GET /api/events/{id}`` showing it.

The second is the one that cannot be fixed by polling harder.  In the same 45
minutes **ESPN published 78 game-level score changes and our card moved 9
times** — because the only score field a tennis event has is
``home_score``/``away_score``, and for tennis that counts SETS.  The card was
blind to 88% of the movement its own authority published, and no cadence
changes that: there is nowhere for a game to land.

``events.home_score`` is not the wrong field, it is the wrong GRAIN.  This
module produces the missing grain — every published set, its games, its
tiebreak, and which set is being played right now — and :func:`authority_linescore`
is deliberately the twin of :func:`espn_tennis_anchor.authority_score`: same
input dict, same orientation rule, same "a refusal names itself" contract.  A
score and a scoreline that disagreed about who was ahead would be worse than
either alone.

═══ WHAT ESPN DOES NOT PUBLISH, SO THAT NOBODY LOOKS FOR IT HERE ═══

Measured over the whole US Open board, 2026-09-03: the tennis scoreboard carries
**no point score (0/15/30/40/Ad) and no server**.  Its finest published grain is
the GAME.  #2746's acceptance line asks the event header for "the current game
score and who is serving"; the first half is this module's ``current_set`` row,
and the second half **is not on the ESPN rail at all**.  StatPal carries both
(live/057 §"Is StatPal actually faster?" measured 322 point changes in 25
minutes) and D27 makes ESPN the state authority for tennis, so serving and
points are a separate decision, not an oversight of this one.

═══ THE ORIENTATION RULE IS BORROWED, NOT RE-DERIVED ═══

:func:`espn_tennis_anchor.orient_sides` already answers "which ESPN side is our
home", and it is imported rather than reimplemented.  A second copy of that rule
is a second chance to reverse a scoreline — and a reversed one is worse than a
blank, because a blank is visibly missing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.utils.espn_tennis_anchor import (
    SCORE_NO_LINE,
    SCORE_NOT_PLAYED,
    SCORE_ORIENTATION_UNRESOLVED,
    SCORED_STATES,
    orient_sides,
)

#: The refusals, and they are the same three words :func:`authority_score` uses.
#: Aliased rather than redefined so a caller can bucket both refusals on one key
#: — the two functions run on the same competition in the same pass, and two
#: vocabularies for one condition is how a stats dict comes to disagree with
#: itself.
LINESCORE_NOT_PLAYED = SCORE_NOT_PLAYED
LINESCORE_NO_LINE = SCORE_NO_LINE
LINESCORE_ORIENTATION_UNRESOLVED = SCORE_ORIENTATION_UNRESOLVED

#: What the numbers in a tennis linescore COUNT.  Carried in the payload beside
#: them because the whole defect this module closes was a units confusion:
#: ``home_score: 1`` is sets, ``sets[0]["home"]: 6`` is games, and
#: ``ScoreDifferentialChart`` plotted the first on an axis labelled the second
#: (#2555, #2746 B5).  A renderer should never have to know which by convention.
LINESCORE_UNIT = "games"

#: The state word for a match being played, from ``SLATE_STATE_BY_ESPN_STATE``.
#: Named because ``current_set`` is published on this word and no other.
IN_PROGRESS = "in_progress"


def _set_rows(
    home_sets: list[dict[str, Any]], away_sets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The two sides' published lines zipped into one row per set.

    ═══ PADDED, NOT ZIPPED, AND THE DIFFERENCE IS A WHOLE SET ═══

    ``zip`` truncates to the shorter side, and the sides are routinely uneven
    for a few seconds: ESPN writes the new set's line for the player who won a
    game before it writes the other's.  A truncating join would drop the set in
    play for exactly as long as that lasts, so the card would flicker the
    current set out of existence on every changeover — a defect that only ever
    appears live and never in a replay of a finished match.

    So the row count is the LONGER side and the missing cell is ``None``.
    ``None`` means "ESPN has not published this side's line", which is a true
    statement and a distinguishable one; ``0`` would be a score.

    Trailing rows where NEITHER side has a game count are dropped — an empty
    slot on both sides is a set nobody has played, and printing ", -" for it
    would be inventing a set out of the absence of one (gotcha #53).
    """
    rows: list[dict[str, Any]] = []
    for index in range(max(len(home_sets), len(away_sets))):
        home = home_sets[index] if index < len(home_sets) else {}
        away = away_sets[index] if index < len(away_sets) else {}
        home_games = home.get("games")
        away_games = away.get("games")
        rows.append({
            "home": home_games,
            "away": away_games,
            "home_tiebreak": home.get("tiebreak"),
            "away_tiebreak": away.get("tiebreak"),
            # WHO WON THE SET, OFF ESPN'S OWN PER-SET FLAG and never off a games
            # comparison — the same rule `competition_sides` counts `sets_won`
            # by, and for the same reason: an abandoned set is awarded to NOBODY
            # and a comparison would hand it to whoever was ahead in it.
            "won_by": (
                "home" if home.get("winner")
                else "away" if away.get("winner")
                else None
            ),
        })
    while rows and rows[-1]["home"] is None and rows[-1]["away"] is None:
        rows.pop()
    return rows


def format_set(row: dict[str, Any]) -> str:
    """One set as a reader writes it — ``6-3``, ``7-6(4)``, ``6-?``.

    ═══ THE PARENTHESIS NAMES THE LOSER'S POINTS, SO IT NEEDS A LOSER ═══

    ``7-6(4)`` means the tiebreak finished 7-4, and the convention is that the
    number in the bracket is the LOSING side's.  ESPN publishes both sides'
    tiebreak points, so the bracket is only printable once the set has a winner
    to subtract.

    A tiebreak still in progress therefore prints ``6-6`` and no bracket.  That
    is deliberate: with no winner flag yet, either number could be the loser's,
    and a bracket on the wrong side of a 7-5 tiebreak reads as the opposite
    result.  The raw points survive in ``home_tiebreak``/``away_tiebreak`` for a
    renderer that wants to show a live tiebreak properly; what this string
    refuses to do is guess.

    A cell we could not read prints ``?`` rather than ``0``.  The set is on the
    board — dropping it would slide every later set one place left.
    """
    home = row.get("home")
    away = row.get("away")
    text = f"{'?' if home is None else home}-{'?' if away is None else away}"
    won_by = row.get("won_by")
    if won_by == "home":
        loser_points = row.get("away_tiebreak")
    elif won_by == "away":
        loser_points = row.get("home_tiebreak")
    else:
        loser_points = None
    if loser_points is not None:
        text = f"{text}({loser_points})"
    return text


def format_line(rows: list[dict[str, Any]]) -> str:
    """Every set, home first — ``6-2, 6-7(4), 6-5``.

    HOME FIRST, NOT WINNER FIRST, and that is the one way this differs from
    :func:`espn_tennis.format_score`.  That function serves a RESULTS list,
    where the winner leads because the row says who won and reading "3-6, 6-7"
    under "Fearnley won" asks the reader to reverse it in their head.  This one
    serves a LIVE card, which has two named sides in a fixed order and no winner
    at all — orienting to the winner mid-match would silently swap the columns
    the moment somebody took a set.
    """
    return ", ".join(format_set(row) for row in rows)


def authority_linescore(
    ours: list[str],
    competition: dict[str, Any],
    *,
    observed_at: datetime,
) -> dict[str, Any]:
    """The set-by-set score ESPN states for this match, in our home/away order.

    Returns ``{"linescore": dict | None, "reason": str | None}`` — never both,
    never neither.  ``competition`` is one entry from
    :func:`espn_tennis.scoreboard_competitions`, the same normalized dict
    :func:`authority_score` reads, so the score and the scoreline always come
    off ONE read of the board.

    The three refusals are :data:`LINESCORE_NOT_PLAYED` (ESPN has this fixture
    as upcoming, or in a state we hold no word for), :data:`LINESCORE_NO_LINE`
    (in play or decided with no set line at all — the walkover shape, and the
    first seconds of a match) and :data:`LINESCORE_ORIENTATION_UNRESOLVED`.

    ═══ WHAT IT DOES *NOT* REFUSE, AND THIS IS THE POINT ═══

    :func:`authority_score` holds a decided match to a legality test — the
    winner's set count must be 2 or 3 and must lead — and refuses 5 of the 6
    retirements on the board, because ``1-0`` for the player who LOST is an
    inverted result arriving through a column nothing downstream doubts.

    A LINESCORE has no such failure mode.  ``4-6, 7-5, 3-1`` for Lajovic over
    Kwon is true, is what happened, and is what the reader wants; it is only the
    SET COUNT derived from it that is unsafe, because ESPN awards the abandoned
    set to nobody.  So this function publishes the line for those matches and
    carries ``completion`` beside it — the marker, travelling with the score,
    which is the arrangement ``format_score``'s docstring already settled on.

    A card can then print "4-6, 7-5, 3-1 · retired" where today it prints
    nothing at all.
    """
    if competition.get("state") not in SCORED_STATES:
        return {"linescore": None, "reason": LINESCORE_NOT_PLAYED}

    oriented = orient_sides(ours, competition.get("sides") or [])
    if oriented is None:
        return {"linescore": None, "reason": LINESCORE_ORIENTATION_UNRESOLVED}
    home, away = oriented

    rows = _set_rows(home.get("sets") or [], away.get("sets") or [])
    if not rows:
        # NO LINE AT ALL — not 0-0. The two are the same silence to a reader and
        # only one of them is a score (gotcha #53). Competition 184769 is the
        # shape: a walkover carries a winner flag and no `linescores` key.
        return {"linescore": None, "reason": LINESCORE_NO_LINE}

    state = competition.get("state")
    # THE SET BEING PLAYED — the last row nobody has won, and ONLY while ESPN
    # says the match is in progress. A decided match's trailing unwon row is an
    # abandoned set, not a live one, and labelling it "current" would put a
    # retired match back on court.
    current_set: Optional[int] = None
    if state == IN_PROGRESS:
        for index in range(len(rows) - 1, -1, -1):
            if rows[index]["won_by"] is None:
                current_set = index + 1
                break

    return {
        "linescore": {
            "source": "espn",
            "espn_competition_id": competition.get("espn_competition_id"),
            # See LINESCORE_UNIT: the payload states what it counts.
            "unit": LINESCORE_UNIT,
            "state": state,
            "completion": competition.get("completion"),
            "status_detail": competition.get("status_detail"),
            "was_suspended": competition.get("was_suspended") is True,
            "sets": rows,
            "current_set": current_set,
            # SETS OFF THE FLAGS, GAMES OFF THE VALUES — the same two statements
            # `competition_sides` counts separately, kept separate here so a
            # consumer never has to re-derive either from the other.
            "sets_won": {
                "home": int(home.get("sets_won") or 0),
                "away": int(away.get("sets_won") or 0),
            },
            # The cumulative games total both sides have won across every
            # published set. #2746 B5: this is the quantity
            # `ScoreDifferentialChart` needs for tennis, where it has been
            # plotting sets on an axis labelled games.
            "games": {
                "home": sum(r["home"] for r in rows if r["home"] is not None),
                "away": sum(r["away"] for r in rows if r["away"] is not None),
            },
            "line": format_line(rows),
            # WHEN WE READ IT, not when ESPN wrote it — ESPN publishes no write
            # timestamp per competition. A consumer measuring freshness is
            # measuring our read, and should be told so by the field name.
            "observed_at": observed_at.isoformat(),
        },
        "reason": None,
    }
