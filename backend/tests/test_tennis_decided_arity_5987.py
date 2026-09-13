"""#5987 — a best-of-five cannot be won in two sets, so we stop saying it did.

THE DEFECT, on the day's marquee event.  At 20:21Z on 2026-09-13 ESPN's board
briefly published the US Open men's singles final (competition ``182677``) as a
completed result while the third set was being played, and we took it:
``/events/15310688`` read ``Final · Zverev WON · 6-3, 7-6 · 2 – 0`` with the full
settled treatment — winner in the hero, markets labelled ``settled``, props on
``last quote``.  It healed ~30 minutes later when the board went back to ``in``
and :func:`authority_write`'s revoke clause pulled the row live again.  Found by
ux/1240; the settled *rendering* was correct, the settlement was not.

THE FIXTURE IS THE BOARD ITSELF.  ``espn_tennis_scoreboard_20260913_usopen.json``
is ESPN's own ATP scoreboard, read at 20:57Z while the final was still being
played and trimmed to nine real competitions — one of every
(draw × status × main-draw/qualifying) shape it carried.  The glitch payload is
not invented either: it is competition ``182677`` from that same read with the
two fields ESPN itself moved (``status.type`` and the winner flag) set to what
the board said at 20:21Z, and nothing else touched.

WHY THE ROUND IS LOAD-BEARING.  ESPN files Slam qualifying under the same
``mens-singles`` grouping as the main draw, and qualifying is best-of-three.
Over the whole 20:57Z board the split is exact — 124 of 124 main-draw finals won
in three sets, 107 of 107 qualifying finals won in two — so a rule keyed on the
draw alone would refuse 107 real results to catch one glitch.  The qualifying
cases below are that guard, not decoration.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.services.espn_tennis import scoreboard_competitions
from app.utils.espn_tennis_anchor import (
    authority_write,
    result_refuted_by_format,
    sets_to_win,
)

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "espn_tennis_scoreboard_20260913_usopen.json"
)

MENS_FINAL_ID = "182677"


@pytest.fixture(scope="module")
def board() -> dict[str, dict]:
    """The real board, through the real parser, keyed by competition id."""
    payload = json.loads(FIXTURE.read_text())
    return {
        c["espn_competition_id"]: c
        for c in scoreboard_competitions([payload])
    }


def _as_glitch(competition: dict) -> dict:
    """The men's final as ESPN published it at 20:21Z — FINAL, at two sets.

    Exactly the two fields the board moved: the status word, and the winner
    flag on the side that was two sets up.  The set lines are untouched.
    """
    glitched = copy.deepcopy(competition)
    glitched["state"] = "decided"
    glitched["status_name"] = "STATUS_FINAL"
    for side in glitched["sides"]:
        side["winner"] = side["sets_won"] == 2
    return glitched


# ═══════════════════════════════════════════════════════════════════════════
# THE PLUMBING — the refusal cannot fire on a field that never arrives
# ═══════════════════════════════════════════════════════════════════════════


def test_the_parser_carries_espns_own_result_word_and_round(board):
    """``status_name`` and ``espn_round`` reach the anchor, off the real board.

    The rule is decided by two fields the anchor's competition dict did not
    carry before this ship.  If either stops travelling, every assertion below
    still passes while the guard silently never fires — so this is checked
    against the parser's real output, not a hand-built dict.
    """
    final = board[MENS_FINAL_ID]
    assert final["status_name"] == "STATUS_IN_PROGRESS"
    assert final["espn_round"] == "Final"

    assert {c["status_name"] for c in board.values()} == {
        "STATUS_FINAL",
        "STATUS_RETIRED",
        "STATUS_WALKOVER",
        "STATUS_IN_PROGRESS",
    }
    assert all(c["espn_round"] for c in board.values())


# ═══════════════════════════════════════════════════════════════════════════
# THE DISTANCE
# ═══════════════════════════════════════════════════════════════════════════


def test_a_slam_mens_main_draw_match_needs_three_sets(board):
    assert sets_to_win(board[MENS_FINAL_ID]) == 3
    assert sets_to_win(board["182656"]) == 3  # Lehecka d. Carreno Busta, R1


@pytest.mark.parametrize(
    "comp_id, why",
    [
        ("184607", "mens qualifying is best-of-three"),
        ("182632", "the women's main draw is best-of-three"),
        ("184694", "women's qualifying is best-of-three"),
    ],
)
def test_everything_else_needs_two(board, comp_id, why):
    assert sets_to_win(board[comp_id]) == 2, why


def test_a_missing_round_answers_two_because_silence_refuses_nothing(board):
    """No round ⇒ we do not know the distance ⇒ the short answer.

    The dangerous direction is the other one: reading an absent round as main
    draw would refuse all 107 real qualifying results on this one board.
    """
    roundless = {**board[MENS_FINAL_ID], "espn_round": None}
    assert sets_to_win(roundless) == 2


# ═══════════════════════════════════════════════════════════════════════════
# THE REFUSAL
# ═══════════════════════════════════════════════════════════════════════════


def test_the_glitch_is_refuted_from_the_row_alone(board):
    assert result_refuted_by_format(_as_glitch(board[MENS_FINAL_ID])) is True


def test_the_glitch_no_longer_crowns_a_champion(board):
    """The whole ship: no ``completed`` on a row ESPN cannot have finished."""
    changes = authority_write(
        now=None,
        our_status="live",
        our_completed_at=None,
        our_commence_time=None,
        our_commence_time_source="odds_api",
        competition=_as_glitch(board[MENS_FINAL_ID]),
        our_sources={},
        our_home_score=2,
        our_away_score=0,
    )
    assert "status" not in changes


def test_the_same_payload_at_three_sets_still_settles(board):
    """NOT A BLANKET REFUSAL. The real result must still land.

    The glitch specimen with one more set won — which is how this match
    actually ends — settles exactly as it did before the ship.
    """
    won = _as_glitch(board[MENS_FINAL_ID])
    for side in won["sides"]:
        if side["winner"]:
            side["sets_won"] = 3
    assert result_refuted_by_format(won) is False

    changes = authority_write(
        now=None,
        our_status="live",
        our_completed_at=None,
        our_commence_time=None,
        our_commence_time_source="odds_api",
        competition=won,
        our_sources={},
        our_home_score=3,
        our_away_score=0,
    )
    assert changes["status"] == "completed"


@pytest.mark.parametrize(
    "comp_id, shape",
    [
        ("182706", "RETIRED in the third with the winner two sets up"),
        ("184599", "RETIRED with the flagged winner holding ONE set"),
        ("184769", "WALKOVER, no line at all"),
        ("184744", "RETIRED with no set awarded to anybody"),
    ],
)
def test_a_match_that_ended_early_is_never_refused(board, comp_id, shape):
    """ESPN names these, so we do not have to guess them from the count.

    Sweeny was two sets up when Moutet retired in the third (``182706``): the
    match is genuinely over at ``2-0`` in a best-of-five, and refusing it would
    leave a finished match reading ``live`` for the sake of a glitch.
    """
    assert result_refuted_by_format(board[comp_id]) is False, shape


def test_every_real_final_on_the_board_survives(board):
    """The population test. One refusal on a real result is one too many."""
    finals = [
        c for c in board.values()
        if c["state"] == "decided" and c["status_name"] == "STATUS_FINAL"
    ]
    assert len(finals) == 4
    assert [result_refuted_by_format(c) for c in finals] == [False] * 4


# ═══════════════════════════════════════════════════════════════════════════
# THE THREE SILENCES — none of them is evidence (gotcha #53)
# ═══════════════════════════════════════════════════════════════════════════


def test_a_competition_still_in_play_is_not_refused(board):
    """Two sets to love IS the live card. Only the word FINAL is refused."""
    assert board[MENS_FINAL_ID]["state"] == "in_progress"
    assert result_refuted_by_format(board[MENS_FINAL_ID]) is False


def test_no_winner_flag_refuses_nothing(board):
    nobody = _as_glitch(board[MENS_FINAL_ID])
    for side in nobody["sides"]:
        side["winner"] = False
    assert result_refuted_by_format(nobody) is False


def test_no_set_line_refuses_nothing(board):
    blank = _as_glitch(board[MENS_FINAL_ID])
    for side in blank["sides"]:
        side["games"] = []
    assert result_refuted_by_format(blank) is False


def test_an_espn_word_we_do_not_have_refuses_nothing(board):
    """An unknown status name is silence, not a short final."""
    unknown = _as_glitch(board[MENS_FINAL_ID])
    unknown["status_name"] = None
    assert result_refuted_by_format(unknown) is False
