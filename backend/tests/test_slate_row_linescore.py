"""The tournament hub's slate row carries the set-by-set score (live/061, #2746).

THE SHIP: a reader opening the US Open hub during the men's semifinals sees
``6-4 4-6 2-1`` on the row, not just the words "3rd Set".

═══ WHY THIS FILE GUARDS BOTH DIRECTIONS (gotcha #43) ═══

A guard that only proves the line APPEARS is half a guard, and it is the half
that lets the other half regress silently. Two failures are possible here and
they are opposite:

1. **The line does not appear** when ESPN states one — the ship is not shipped.
2. **A line appears when ESPN states none** — every upcoming row on a card that
   has not started grows a ``0-0``-shaped artefact, or a ``"linescore": null``
   that costs bytes on all 32 rows to say nothing.

Direction 2 is the one that would ship by accident, because the natural way to
write this emits the key unconditionally. So the absence cases outnumber the
presence cases below, deliberately.

═══ THE CADENCE THIS ROW INHERITS, STATED RATHER THAN CLAIMED ═══

The ingredients come off the ``order_of_play`` entry, refreshed by
``sync-tournament-results`` every **180 seconds**. This file does not assert a
30-second SLA and the ship does not claim one: a slate is a list of what is on,
and the live-cadence answer lives on the match page one tap away. What IS
asserted is atomicity — the line and the caption beside it come off ONE read,
so they cannot describe two different moments of the same match.
"""

from datetime import datetime, timezone

import pytest

from app.utils.tournament_slate import _slate_linescore

NOW = datetime(2026, 9, 4, 19, 30, tzinfo=timezone.utc)

SINNER = "Jannik Sinner"
DJOKOVIC = "Novak Djokovic"


def _side(name, games, winners, tiebreaks=None):
    """One side of an ESPN competition, in ``competition_sides`` shape."""
    tiebreaks = tiebreaks or [None] * len(games)
    return {
        "name": name,
        "sets_won": sum(1 for w in winners if w),
        "games": [g for g in games if g is not None],
        "sets": [
            {"games": g, "tiebreak": t, "winner": bool(w)}
            for g, t, w in zip(games, tiebreaks, winners)
        ],
        "winner": None,
    }


def _listed(state="in_progress", *, sides=None, completion="unknown", detail="3rd Set"):
    return {
        "espn_competition_id": "182710",
        "state": state,
        "status_detail": detail,
        "completion": completion,
        "was_suspended": False,
        "sides": sides
        if sides is not None
        else [
            _side(SINNER, [6, 4, 2], [True, False, False]),
            _side(DJOKOVIC, [4, 6, 1], [False, True, False]),
        ],
    }


def _matchup(players=(SINNER, DJOKOVIC)):
    return {"players": list(players)}


# ═══════════════════ DIRECTION 1 — THE LINE APPEARS ═══════════════════


def test_a_match_in_play_puts_its_set_line_on_the_slate_row():
    """THE SHIP. A live semifinal's row states the score of every set."""
    row = _slate_linescore(_matchup(), _listed(), now=NOW)

    assert "linescore" in row, "a match in play must put its line on the row"
    line = row["linescore"]
    assert line["line"] == "6-4, 4-6, 2-1"
    assert line["sets_won"] == {"home": 1, "away": 1}
    # THE SET IN PLAY, so the renderer can mark it. A finished set and the one
    # being played must not read the same on a scannable list.
    assert line["current_set"] == 3


def test_the_line_is_oriented_to_OUR_pairing_and_not_to_espns_column_order():
    """A linescore with the columns swapped is an inverted result.

    Nothing downstream doubts a scoreline, so this is the failure that would
    reach a reader looking entirely plausible. The register's pairing decides
    which side is home; ESPN's own column order does not.
    """
    forward = _slate_linescore(_matchup((SINNER, DJOKOVIC)), _listed(), now=NOW)
    reversed_ = _slate_linescore(_matchup((DJOKOVIC, SINNER)), _listed(), now=NOW)

    assert forward["linescore"]["line"] == "6-4, 4-6, 2-1"
    assert reversed_["linescore"]["line"] == "4-6, 6-4, 1-2"
    assert forward["linescore"]["sets_won"] == {"home": 1, "away": 1}


def test_a_retired_match_still_shows_the_line_it_was_retired_from():
    """`4-6, 7-5, 3-1 ret.` is true, is what happened, and is what a reader wants.

    Only the SET COUNT derived from it is unsafe, and this row does not derive
    one. A card that prints nothing for a retirement is the defect
    `authority_linescore`'s docstring exists to refuse.
    """
    row = _slate_linescore(
        _matchup(),
        _listed(
            state="decided",
            completion="retired",
            detail="Retired",
            sides=[
                _side(SINNER, [4, 7, 3], [False, True, False]),
                _side(DJOKOVIC, [6, 5, 1], [True, False, False]),
            ],
        ),
        now=NOW,
    )

    assert row["linescore"]["line"] == "4-6, 7-5, 3-1"
    assert row["linescore"]["completion"] == "retired"
    # NOT captioned as a live set — a retired match's trailing unwon row is an
    # abandoned set, not one being played.
    assert row["linescore"]["current_set"] is None


def test_the_line_and_its_caption_come_off_one_read():
    """ATOMICITY, which is the whole reason the ingredients ride the board entry.

    A score fetched separately from the state that captions it could describe a
    different moment of the same match. Both fields here trace to the same
    `order_of_play` dict, so they cannot disagree.
    """
    listed = _listed(detail="3rd Set")
    row = _slate_linescore(_matchup(), listed, now=NOW)

    assert row["linescore"]["status_detail"] == listed["status_detail"]
    assert row["linescore"]["state"] == listed["state"]
    assert row["linescore"]["espn_competition_id"] == listed["espn_competition_id"]


# ═══════════════ DIRECTION 2 — THE ROW STAYS QUIET (gotcha #43) ═══════════════
#
# Every case below must contribute NO KEY — not `None`, no key. A
# `"linescore": null` on all 32 rows of a card that has not started is 32 nulls
# a reader's browser downloads in order to learn nothing.


def test_an_upcoming_match_carries_no_linescore_key_at_all():
    """The ordinary case, and the one that would bloat the payload."""
    row = _slate_linescore(_matchup(), _listed(state="upcoming"), now=NOW)
    assert row == {}, "an upcoming row must not carry a linescore key"


def test_a_fixture_the_scoreboard_never_mentioned_carries_no_key():
    """No `order_of_play` entry is silence, and silence is not a score."""
    assert _slate_linescore(_matchup(), None, now=NOW) == {}


def test_a_walkover_with_no_set_line_carries_no_key_rather_than_zeroes():
    """A walkover has a winner flag and NO `linescores` — gotcha #53.

    "No line at all" and "0-0" are the same silence to a reader and only one of
    them is a score.
    """
    row = _slate_linescore(
        _matchup(),
        _listed(
            state="decided",
            completion="walkover",
            sides=[_side(SINNER, [], []), _side(DJOKOVIC, [], [])],
        ),
        now=NOW,
    )
    assert row == {}


def test_an_unresolvable_pairing_refuses_the_line_rather_than_guessing_it():
    """Orientation we cannot establish is refused, never guessed.

    Q503's defect was a register pairing naming a player who had withdrawn. The
    right answer there is no line, because the alternative is a real scoreline
    attached to the wrong two people.
    """
    row = _slate_linescore(_matchup(("Someone Else", "Nobody Here")), _listed(), now=NOW)
    assert row == {}


@pytest.mark.parametrize(
    "players",
    [[], [SINNER], [SINNER, DJOKOVIC, "Third Person"], None, "not-a-list"],
)
def test_a_matchup_that_is_not_a_pair_never_produces_a_line(players):
    """Doubles teams and malformed register rows must not crash the slate.

    One bad item never costs the rest of the pass (gotcha #42) — and the way
    this loop is written, an exception here would empty the whole card.
    """
    assert _slate_linescore({"players": players}, _listed(), now=NOW) == {}


def test_a_healthy_row_survives_a_broken_sibling():
    """Gotcha #42, asserted rather than assumed.

    The broken row is evaluated FIRST so an exception, if one were possible,
    would be raised before the healthy row is reached.
    """
    broken = _slate_linescore({"players": None}, _listed(), now=NOW)
    healthy = _slate_linescore(_matchup(), _listed(), now=NOW)

    assert broken == {}
    assert healthy["linescore"]["line"] == "6-4, 4-6, 2-1"
