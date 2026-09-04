"""live/059 addendum (D59 = A′) — the score line is ATOMIC, and here is the proof.

The queue asks for "a test that a mixed line is impossible". Impossibility is not
one test, so this file states it three ways and each one fails differently:

  * **Structural** — `select_line` takes two whole payloads and returns one of
    them; there is no parameter through which a single field could travel.
  * **Exhaustive** — over every combination of two DELIBERATELY DISJOINT source
    payloads (no shared value anywhere), every score field in the output is
    traced back to exactly one input. A merge of any single field is caught.
  * **Runtime** — `assert_atomic` re-derives the check on the way out, so an
    edit that hand-copies a field raises at the line that wrote it.

The disjointness matters. Two fixtures that agree on `sets` cannot detect a
merge of `sets`, and a test that cannot fail is a test that says nothing.
"""

from datetime import datetime, timezone

import pytest

from app.utils.espn_tennis_anchor import SCORE_ORIENTATION_UNRESOLVED
from app.utils.tennis_linescore import LINESCORE_NO_LINE
from app.utils.tennis_line_source import (
    SCORE_FIELDS,
    SOURCE_ESPN,
    SOURCE_STATPAL,
    STATE_FIELDS,
    MixedLineError,
    _set_won_by,
    assert_atomic,
    select_line,
    statpal_linescore,
    statpal_state,
)

OBSERVED = datetime(2026, 9, 4, 2, 30, tzinfo=timezone.utc)


def espn_payload() -> dict:
    """An ESPN line: sets and games, never points, never a server."""
    return {
        "source": SOURCE_ESPN,
        "espn_competition_id": "184770",
        "unit": "games",
        "state": "in_progress",
        "completion": None,
        "status_detail": "Set 2",
        "was_suspended": False,
        "sets": [
            {"home": 6, "away": 4, "home_tiebreak": None,
             "away_tiebreak": None, "won_by": "home"},
            {"home": 3, "away": 3, "home_tiebreak": None,
             "away_tiebreak": None, "won_by": None},
        ],
        "current_set": 2,
        "sets_won": {"home": 1, "away": 0},
        "games": {"home": 9, "away": 7},
        "points": None,
        "serving": None,
        "line": "6-4, 3-3",
        "observed_at": "2026-09-04T02:44:02+00:00",
    }


def statpal_payload() -> dict:
    """A StatPal line for the SAME match, a minute later — one game further on.

    Every score value differs from the ESPN payload's. That is the point: a
    fixture pair that overlaps cannot detect a merge of the overlapping field.
    """
    return {
        "source": SOURCE_STATPAL,
        "statpal_fixture_id": "2631278",
        "unit": "games",
        "sets": [
            {"home": 6, "away": 4, "home_tiebreak": None,
             "away_tiebreak": None, "won_by": "home"},
            {"home": 4, "away": 3, "home_tiebreak": None,
             "away_tiebreak": None, "won_by": None},
        ],
        "current_set": 2,
        "sets_won": {"home": 1, "away": 0},
        "games": {"home": 10, "away": 7},
        "points": {"home": "40", "away": "30"},
        "serving": "home",
        "line": "6-4, 4-3",
        "observed_at": "2026-09-04T02:44:51+00:00",
        "reported_state": "in_progress",
    }


def _differing_score_fields(a: dict, b: dict) -> set:
    return {f for f in SCORE_FIELDS if a.get(f) != b.get(f)}


# ---------------------------------------------------------------------------
# A mixed line is impossible
# ---------------------------------------------------------------------------


class TestAMixedLineIsImpossible:
    def test_the_fixtures_actually_disagree_so_this_file_can_fail(self):
        """The control for every test below it.

        If these two payloads agreed on a field, no assertion in this file could
        detect that field being merged. `points` and `serving` are excluded:
        ESPN never publishes them, so they cannot disagree, and the merge that
        would take them from StatPal is caught by `source` instead.
        """
        differing = _differing_score_fields(espn_payload(), statpal_payload())
        assert differing >= {"sets", "games", "line", "observed_at"}

    @pytest.mark.parametrize("anchored", [True, False])
    def test_every_score_field_traces_to_exactly_one_source(self, anchored):
        espn, statpal = espn_payload(), statpal_payload()
        out = select_line(espn=espn, statpal=statpal, has_statpal_anchor=anchored)
        chosen = statpal if anchored else espn
        other = espn if anchored else statpal
        for field in _differing_score_fields(espn, statpal):
            assert out[field] == chosen[field], f"{field} did not come from the source"
            assert out[field] != other[field], f"{field} came from BOTH sources"

    def test_the_anchor_takes_the_points_and_the_server_with_the_rest(self):
        """The whole line moves, or none of it does. Points are not a bolt-on."""
        out = select_line(
            espn=espn_payload(), statpal=statpal_payload(), has_statpal_anchor=True
        )
        assert out["source"] == SOURCE_STATPAL
        assert out["points"] == {"home": "40", "away": "30"}
        assert out["serving"] == "home"
        assert out["line"] == "6-4, 4-3"

    def test_without_an_anchor_the_line_stays_espn_and_stays_pointless(self):
        """🔴 THE MERGE THIS MODULE EXISTS TO REFUSE.

        StatPal has points; ESPN does not. Taking them anyway is the tempting
        build and it prints a game score belonging to a different game.
        """
        out = select_line(
            espn=espn_payload(), statpal=statpal_payload(), has_statpal_anchor=False
        )
        assert out["source"] == SOURCE_ESPN
        assert out["points"] is None, "points were borrowed from an unanchored source"
        assert out["serving"] is None
        assert out["line"] == "6-4, 3-3"

    def test_a_hand_copied_field_raises_at_the_composition(self):
        """The runtime half. `assert_atomic` is what an edit runs into."""
        out = select_line(
            espn=espn_payload(), statpal=statpal_payload(), has_statpal_anchor=False
        )
        out["points"] = statpal_payload()["points"]   # the edit, made by hand
        with pytest.raises(MixedLineError, match="points"):
            assert_atomic(out, espn=espn_payload(), statpal=statpal_payload())

    def test_a_line_naming_a_source_that_never_answered_raises(self):
        out = select_line(
            espn=espn_payload(), statpal=None, has_statpal_anchor=False
        )
        out["source"] = SOURCE_STATPAL
        with pytest.raises(MixedLineError, match="produced no payload"):
            assert_atomic(out, espn=espn_payload(), statpal=None)

    def test_the_score_and_state_field_sets_do_not_overlap(self):
        """A field in both sets could be taken from either side and be 'atomic'
        under both readings — the partition is what makes the check total."""
        assert SCORE_FIELDS.isdisjoint(STATE_FIELDS)


# ---------------------------------------------------------------------------
# ESPN keeps the state
# ---------------------------------------------------------------------------


class TestEspnOwnsTheState:
    def test_state_is_espns_even_when_the_score_is_statpals(self):
        espn = espn_payload()
        espn["state"] = "final"
        espn["completion"] = "retired"
        out = select_line(espn=espn, statpal=statpal_payload(), has_statpal_anchor=True)
        assert out["source"] == SOURCE_STATPAL
        assert out["state"] == "final"
        assert out["completion"] == "retired"
        assert out["state_source"] == SOURCE_ESPN

    def test_a_disagreement_is_reported_with_the_scores_own_stamp(self):
        """Alex's rule for the disagreement, exactly: ESPN's state, the linked
        source's last score, and that source's own "as of"."""
        espn = espn_payload()
        espn["state"] = "final"                    # ESPN: the match is over
        statpal = statpal_payload()
        statpal["reported_state"] = "in_progress"  # StatPal: still on court
        out = select_line(espn=espn, statpal=statpal, has_statpal_anchor=True)
        assert out["state"] == "final"
        assert out["line"] == statpal["line"], "the last linked score was discarded"
        assert out["score_as_of"] == statpal["observed_at"]
        assert out["state_disagrees"] is True

    def test_agreement_does_not_raise_a_caveat(self):
        out = select_line(
            espn=espn_payload(), statpal=statpal_payload(), has_statpal_anchor=True
        )
        assert out["state_disagrees"] is False

    def test_silence_is_not_disagreement(self):
        out = select_line(espn=espn_payload(), statpal=None, has_statpal_anchor=True)
        assert out["state_disagrees"] is False

    def test_a_statpal_only_line_never_borrows_statpals_state(self):
        """🔴 The least visible place a mix could hide. With no ESPN payload the
        state is absent, not StatPal's — D27 makes ESPN the state authority, and
        a state word from elsewhere under `state_source: espn` would be a lie in
        the one field nothing downstream doubts."""
        out = select_line(
            espn=None, statpal=statpal_payload(), has_statpal_anchor=True
        )
        assert out["source"] == SOURCE_STATPAL
        assert out["state"] is None
        assert out["state_source"] is None

    def test_a_statpal_payload_carrying_state_words_still_supplies_none(self):
        """🔴 The version of the test above that BITES.

        `statpal_payload()` has no state keys at all, so the guard above passes
        whether the composition reads the state off ESPN or off "whichever
        source answered" — a mutant writing `espn or statpal or {}` survives it
        untouched (measured: it did). StatPal's board DOES publish a status
        word; it arrives as `reported_state`, deliberately outside
        :data:`STATE_FIELDS`, and one rename on the reader's side would put it
        under a state key. This fixture is that future — every state field
        populated and contradicting ESPN's absence — and the composition must
        still take none of them.
        """
        theirs = statpal_payload()
        theirs.update({
            "state": "decided",
            "completion": "final",
            "status_detail": "Finished",
            "was_suspended": True,
        })

        out = select_line(espn=None, statpal=theirs, has_statpal_anchor=True)

        assert out["source"] == SOURCE_STATPAL
        assert out["line"] == "6-4, 4-3", "the SCORE is theirs, whole"
        for field in sorted(STATE_FIELDS):
            assert out[field] is None, f"borrowed StatPal's {field}"
        assert out["state_source"] is None

    def test_the_statpal_reader_publishes_no_state_field_at_all(self):
        """The same invariant held at the SOURCE instead of at the composition.

        Both halves are asserted because either one alone can be edited away: if
        the reader never emits a state field there is nothing for a loosened
        composition to borrow, and if the composition never reads one it does
        not matter what the reader emits. The pair is what makes the state
        unborrowable.
        """
        line = statpal_linescore(
            ["Alexander Zverev", "Quentin Halys"], LIVE_MATCH,
            observed_at=OBSERVED,
        )["linescore"]

        assert STATE_FIELDS.isdisjoint(line), (
            f"the reader emitted a state field: "
            f"{sorted(STATE_FIELDS.intersection(line))}"
        )
        assert line["reported_state"] == "in_progress", (
            "and it still reports the state it read, for the disagreement check"
        )


# ---------------------------------------------------------------------------
# Fallbacks
# ---------------------------------------------------------------------------


class TestFallback:
    def test_an_anchored_source_that_refused_falls_back_to_espn_whole(self):
        out = select_line(
            espn=espn_payload(), statpal=None, has_statpal_anchor=True
        )
        assert out["source"] == SOURCE_ESPN
        assert out["line"] == "6-4, 3-3"
        assert out["points"] is None

    def test_no_source_at_all_is_none_not_an_empty_line(self):
        """An empty line renders as a match with no score; None renders as
        nothing at all, which is the true statement (gotcha #53)."""
        assert select_line(espn=None, statpal=None, has_statpal_anchor=True) is None

    def test_statpal_alone_is_used_when_espn_refuses(self):
        out = select_line(
            espn=None, statpal=statpal_payload(), has_statpal_anchor=False
        )
        assert out is not None and out["source"] == SOURCE_STATPAL


# ---------------------------------------------------------------------------
# The StatPal reader
# ---------------------------------------------------------------------------


LIVE_MATCH = {
    "date": "03.09.2026", "id": "2631278", "status": "Set 2", "tb": "False",
    "player": [
        {"name": "A. Zverev", "id": "1", "game_score": "40", "serve": "True",
         "s1": "6", "s2": "3", "s3": "", "s4": "", "s5": "",
         "totalscore": "1", "winner": "False"},
        {"name": "Q. Halys", "id": "2", "game_score": "30", "serve": "False",
         "s1": "4", "s2": "4", "s3": "", "s4": "", "s5": "",
         "totalscore": "0", "winner": "False"},
    ],
}


class TestStatpalReader:
    """Fixtures transcribed from the live board, 2026-09-04 — not invented."""

    def test_reads_sets_games_points_and_the_server(self):
        out = statpal_linescore(["Alexander Zverev", "Quentin Halys"],
                                LIVE_MATCH, observed_at=OBSERVED)
        line = out["linescore"]
        assert out["reason"] is None
        assert line["line"] == "6-4, 3-4"
        assert line["points"] == {"home": "40", "away": "30"}
        assert line["serving"] == "home"
        assert line["games"] == {"home": 9, "away": 8}
        assert line["current_set"] == 2

    def test_orientation_is_ours_and_a_reversed_match_reverses_the_line(self):
        out = statpal_linescore(["Quentin Halys", "Alexander Zverev"],
                                LIVE_MATCH, observed_at=OBSERVED)
        assert out["linescore"]["line"] == "4-6, 4-3"
        assert out["linescore"]["serving"] == "away"

    def test_an_unresolvable_orientation_refuses_rather_than_guesses(self):
        out = statpal_linescore(["Nobody At All", "Someone Else"],
                                LIVE_MATCH, observed_at=OBSERVED)
        assert out["linescore"] is None
        assert out["reason"] == SCORE_ORIENTATION_UNRESOLVED

    def test_an_unplayed_set_is_absent_not_zero_zero(self):
        out = statpal_linescore(["Alexander Zverev", "Quentin Halys"],
                                LIVE_MATCH, observed_at=OBSERVED)
        assert len(out["linescore"]["sets"]) == 2, "an empty set was published as 0-0"

    def test_a_finished_match_publishes_no_current_set_and_no_points(self):
        match = {
            "id": "2631263", "status": "Finished",
            "player": [
                {"name": "G. Monfils", "game_score": "", "serve": "False",
                 "s1": "3", "s2": "4", "s3": "3", "s4": "", "s5": "",
                 "totalscore": "0", "winner": "False"},
                {"name": "L. Tien", "game_score": "", "serve": "False",
                 "s1": "6", "s2": "6", "s3": "6", "s4": "", "s5": "",
                 "totalscore": "3", "winner": "True"},
            ],
        }
        line = statpal_linescore(["Gael Monfils", "Learner Tien"],
                                 match, observed_at=OBSERVED)["linescore"]
        assert line["current_set"] is None
        assert line["points"] is None
        assert line["serving"] is None
        assert line["line"] == "3-6, 4-6, 3-6"

    def test_a_match_with_no_line_refuses_rather_than_publishing_nothing(self):
        match = {"id": "1", "status": "Not Started", "player": [
            {"name": "A. Zverev", "s1": "", "s2": "", "s3": "", "s4": "", "s5": ""},
            {"name": "Q. Halys", "s1": "", "s2": "", "s3": "", "s4": "", "s5": ""},
        ]}
        out = statpal_linescore(["Alexander Zverev", "Quentin Halys"],
                                match, observed_at=OBSERVED)
        assert out["linescore"] is None
        assert out["reason"] == LINESCORE_NO_LINE

    def test_a_malformed_match_is_a_refusal_not_a_crash(self):
        for bad in ({}, {"player": []}, {"player": [{"name": "A"}]}, {"player": "x"}):
            out = statpal_linescore(["A", "B"], bad, observed_at=OBSERVED)
            assert out["linescore"] is None and out["reason"]


class TestSetWinnerDerivation:
    """🔴 The inversion `authority_score` refuses 5 of 6 retirements over.

    StatPal publishes no per-set winner flag, so it has to be derived, and the
    derivation is fenced by the rules of tennis rather than by a comparison.
    """

    @pytest.mark.parametrize("home,away,expected", [
        (6, 4, "home"), (4, 6, "away"),
        (7, 5, "home"), (7, 6, "home"), (6, 7, "away"),
        (6, 0, "home"),
    ])
    def test_a_completed_set_is_awarded(self, home, away, expected):
        assert _set_won_by(home, away) == expected

    @pytest.mark.parametrize("home,away", [
        (3, 1),    # a retirement mid-set — awarded to NOBODY
        (6, 5), (5, 4), (0, 0), (6, 6),
        (8, 6),    # no advantage-set final at the US Open; unknown stays unknown
    ])
    def test_an_unfinished_or_unrecognised_set_is_not_awarded(self, home, away):
        assert _set_won_by(home, away) is None

    def test_a_missing_side_is_never_awarded(self):
        assert _set_won_by(6, None) is None
        assert _set_won_by(None, None) is None


class TestStatpalStateWords:
    @pytest.mark.parametrize("raw,expected", [
        ("Set 2", "in_progress"), ("Set 5", "in_progress"),
        ("Finished", "final"), ("Retired", "final"), ("Walkover", "final"),
        ("Not Started", "scheduled"),
        ("", None), (None, None), ("Something New", None),
    ])
    def test_maps_the_measured_vocabulary(self, raw, expected):
        assert statpal_state(raw) == expected
