"""Guards for the tennis linescore — the grain the live card was missing.

live/058, #2746. Every fixture below is a REAL competition off the US Open
board (2026-09-03), trimmed to the fields the reader touches, so a guard that
passes here passes against what ESPN actually publishes rather than against
what this module wishes it published.

Each guard names the specific wrong reading it exists to catch. The mutation
column in the queue report says which mutant each one killed.
"""

from datetime import datetime, timezone

import pytest

from app.services.espn_tennis import competition_sides, scoreboard_competitions
from app.utils.tennis_linescore import (
    LINESCORE_NO_LINE,
    LINESCORE_NOT_PLAYED,
    LINESCORE_ORIENTATION_UNRESOLVED,
    authority_linescore,
    format_line,
    format_set,
)

OBSERVED = datetime(2026, 9, 3, 21, 30, 0, tzinfo=timezone.utc)


def _competition(competitors, *, state="in_progress", completion="unknown", **extra):
    """A normalized `scoreboard_competitions` entry around raw competitors."""
    return {
        "espn_competition_id": extra.pop("comp_id", "182709"),
        "state": state,
        "completion": completion,
        "status_detail": extra.pop("status_detail", "3rd Set"),
        "was_suspended": extra.pop("was_suspended", False),
        "sides": competition_sides({"competitors": competitors}),
        **extra,
    }


def _competitor(name, lines, *, winner=None):
    comp = {"athlete": {"displayName": name}, "linescores": lines}
    if winner is not None:
        comp["winner"] = winner
    return comp


# ── ESPN competition 182709, live, 2026-09-03T21:2xZ ────────────────────────
# Popyrin leads Tabilo 6-2 6-7(4) 6-5 — the second set went to a tiebreak.
POPYRIN_TABILO = [
    _competitor("Alejandro Tabilo", [
        {"value": 2.0, "winner": False},
        {"value": 7.0, "tiebreak": 7, "winner": True},
        {"value": 5.0},
    ]),
    _competitor("Alexei Popyrin", [
        {"value": 6.0, "winner": True},
        {"value": 6.0, "tiebreak": 4, "winner": False},
        {"value": 6.0},
    ]),
]

# ── ESPN competition 184599, STATUS_RETIRED ─────────────────────────────────
# "Dusan Lajovic (SER) bt SoonWoo Kwon (KOR) 4-6 7-5 3-1 ret"
LAJOVIC_KWON_RETIRED = [
    _competitor("Dusan Lajovic", [
        {"value": 4.0, "winner": False},
        {"value": 7.0, "winner": True},
        {"value": 3.0, "winner": False},
    ], winner=True),
    _competitor("SoonWoo Kwon", [
        {"value": 6.0, "winner": True},
        {"value": 5.0, "winner": False},
        {"value": 1.0, "winner": False},
    ], winner=False),
]

# ── ESPN competition 184769, STATUS_WALKOVER ────────────────────────────────
# A winner flag and NO `linescores` key at all.
DIMITROV_VIRTANEN_WALKOVER = [
    _competitor("Grigor Dimitrov", [], winner=True),
    _competitor("Otto Virtanen", [], winner=False),
]


class TestTheLineItself:
    def test_a_live_match_prints_every_set_home_first(self):
        """THE SHIP. `1-1` becomes `6-2, 6-7(4), 6-5`.

        Our home is Popyrin, who is ESPN's SECOND competitor here — the whole
        reason orientation is not read off ESPN's own `homeAway`.
        """
        verdict = authority_linescore(
            ["Alexei Popyrin", "Alejandro Tabilo"],
            _competition(POPYRIN_TABILO),
            observed_at=OBSERVED,
        )
        assert verdict["reason"] is None
        assert verdict["linescore"]["line"] == "6-2, 6-7(4), 6-5"

    def test_the_line_reverses_when_our_home_is_the_other_player(self):
        """A CONTROL ON THE ORIENTATION, not a restatement of it.

        Without this, a formatter that ignored `ours` entirely and always
        printed ESPN's first competitor first would pass the test above on the
        50% of fixtures where the orderings happen to agree.
        """
        verdict = authority_linescore(
            ["Alejandro Tabilo", "Alexei Popyrin"],
            _competition(POPYRIN_TABILO),
            observed_at=OBSERVED,
        )
        assert verdict["linescore"]["line"] == "2-6, 7-6(4), 5-6"

    def test_the_set_in_play_is_named_and_it_is_the_last_unwon_one(self):
        """`current_set` is 3 — the set nobody has won, not `period`, not 2.

        live/057 measured `status.period` trailing ESPN's own linescores badly
        enough to produce NEGATIVE latencies against them. This is derived from
        the lines, so it cannot lag them.
        """
        verdict = authority_linescore(
            ["Alexei Popyrin", "Alejandro Tabilo"],
            _competition(POPYRIN_TABILO),
            observed_at=OBSERVED,
        )
        assert verdict["linescore"]["current_set"] == 3
        assert verdict["linescore"]["sets"][2]["won_by"] is None

    def test_sets_and_games_are_counted_separately(self):
        """Two statements, two numbers: 1-1 in sets, 19-14 in games.

        #2746 B5 — `ScoreDifferentialChart` needs the games total, and has been
        plotting the SET count on an axis labelled games (#2555).
        """
        line = authority_linescore(
            ["Alexei Popyrin", "Alejandro Tabilo"],
            _competition(POPYRIN_TABILO),
            observed_at=OBSERVED,
        )["linescore"]
        assert line["sets_won"] == {"home": 1, "away": 1}
        assert line["games"] == {"home": 6 + 6 + 6, "away": 2 + 7 + 5}
        assert line["unit"] == "games"


class TestTiebreakEncoding:
    def test_the_bracket_holds_the_losers_points(self):
        """`7-6(4)`, never `7-6(7)` — the bracket is the LOSING side's."""
        assert format_set({
            "home": 7, "away": 6,
            "home_tiebreak": 7, "away_tiebreak": 4,
            "won_by": "home",
        }) == "7-6(4)"
        assert format_set({
            "home": 6, "away": 7,
            "home_tiebreak": 4, "away_tiebreak": 7,
            "won_by": "away",
        }) == "6-7(4)"

    def test_a_tiebreak_still_being_played_prints_no_bracket(self):
        """6-6 with points on the board and NO winner yet.

        With no winner flag, either number could be the loser's, and a bracket
        on the wrong side of a 7-5 tiebreak reads as the opposite result. The
        points survive in the structured row for a renderer that wants them.
        """
        row = {
            "home": 6, "away": 6,
            "home_tiebreak": 5, "away_tiebreak": 3,
            "won_by": None,
        }
        assert format_set(row) == "6-6"
        assert row["home_tiebreak"] == 5

    def test_a_set_with_no_tiebreak_prints_plain(self):
        assert format_set({
            "home": 6, "away": 3,
            "home_tiebreak": None, "away_tiebreak": None,
            "won_by": "home",
        }) == "6-3"


class TestRetirementsAndWalkovers:
    def test_a_retirement_publishes_its_line_and_says_how_it_ended(self):
        """4-6, 7-5, 3-1 · retired — the score `authority_score` must REFUSE.

        `authority_score` refuses this fixture (`not-a-completed-result`: sets
        are 1-1 because ESPN awards the abandoned set to nobody), and it is
        right to — `1-1` next to a winner is an inverted result. The LINE has no
        such failure mode: it is what happened. This is the case where the two
        functions deliberately disagree, and if they ever stop, one of them has
        been made wrong.
        """
        verdict = authority_linescore(
            ["Dusan Lajovic", "SoonWoo Kwon"],
            _competition(LAJOVIC_KWON_RETIRED, state="decided", completion="retired"),
            observed_at=OBSERVED,
        )
        assert verdict["reason"] is None
        assert verdict["linescore"]["line"] == "4-6, 7-5, 3-1"
        assert verdict["linescore"]["completion"] == "retired"

    def test_a_decided_match_has_no_current_set_even_with_an_unwon_one(self):
        """The abandoned third set is NOT "the set being played".

        Naming it current puts a retired match back on court, and the live pill
        is drawn off exactly this field.
        """
        verdict = authority_linescore(
            ["Dusan Lajovic", "SoonWoo Kwon"],
            _competition(LAJOVIC_KWON_RETIRED, state="decided", completion="retired"),
            observed_at=OBSERVED,
        )
        assert verdict["linescore"]["current_set"] is None

    def test_a_walkover_refuses_rather_than_printing_zero_zero(self):
        """No `linescores` at all is UNPUBLISHED, not 0-0 (gotcha #53)."""
        verdict = authority_linescore(
            ["Grigor Dimitrov", "Otto Virtanen"],
            _competition(
                DIMITROV_VIRTANEN_WALKOVER, state="decided", completion="walkover"
            ),
            observed_at=OBSERVED,
        )
        assert verdict["linescore"] is None
        assert verdict["reason"] == LINESCORE_NO_LINE


class TestInterruptedAndUnknownStates:
    def test_an_interrupted_match_keeps_its_line_and_is_not_called_final(self):
        """Rain stops play at 6-4, 3-2.

        ESPN carries the stoppage as its own status, which `completion_of` does
        not hold a word for and degrades to `unknown` — never to `final`, the
        one direction that would let a card caption a match nobody has finished.
        The line is still true and is still published.
        """
        interrupted = [
            _competitor("Iga Swiatek", [{"value": 6.0, "winner": True}, {"value": 3.0}]),
            _competitor("Coco Gauff", [{"value": 4.0, "winner": False}, {"value": 2.0}]),
        ]
        verdict = authority_linescore(
            ["Iga Swiatek", "Coco Gauff"],
            _competition(
                interrupted,
                completion="unknown",
                status_detail="Interrupted",
                was_suspended=True,
            ),
            observed_at=OBSERVED,
        )
        assert verdict["linescore"]["line"] == "6-4, 3-2"
        assert verdict["linescore"]["completion"] != "final"
        assert verdict["linescore"]["status_detail"] == "Interrupted"
        assert verdict["linescore"]["was_suspended"] is True

    def test_an_upcoming_fixture_says_nothing(self):
        verdict = authority_linescore(
            ["Alexei Popyrin", "Alejandro Tabilo"],
            _competition(POPYRIN_TABILO, state="upcoming"),
            observed_at=OBSERVED,
        )
        assert verdict["linescore"] is None
        assert verdict["reason"] == LINESCORE_NOT_PLAYED

    def test_a_state_espn_gives_us_no_word_for_says_nothing(self):
        """`state=None` is `scoreboard_competitions`' honest carry of an ESPN
        state we hold no mapping for. It must not fall through to a score."""
        verdict = authority_linescore(
            ["Alexei Popyrin", "Alejandro Tabilo"],
            _competition(POPYRIN_TABILO, state=None),
            observed_at=OBSERVED,
        )
        assert verdict["reason"] == LINESCORE_NOT_PLAYED


class TestRaggedAndUnreadableLines:
    def test_the_side_espn_has_not_written_yet_does_not_truncate_the_set(self):
        """THE CHANGEOVER FLICKER.

        ESPN writes the new set's line for the player who won a game before it
        writes the other's. A zip-shaped join drops the set in play for exactly
        as long as that lasts — a defect that only ever appears live.
        """
        ragged = [
            _competitor("Alexei Popyrin", [{"value": 6.0, "winner": True}, {"value": 1.0}]),
            _competitor("Alejandro Tabilo", [{"value": 3.0, "winner": False}]),
        ]
        line = authority_linescore(
            ["Alexei Popyrin", "Alejandro Tabilo"],
            _competition(ragged),
            observed_at=OBSERVED,
        )["linescore"]
        assert len(line["sets"]) == 2
        assert line["sets"][1] == {
            "home": 1, "away": None,
            "home_tiebreak": None, "away_tiebreak": None,
            "won_by": None,
        }
        assert line["line"] == "6-3, 1-?"

    def test_an_unreadable_line_holds_its_place_instead_of_sliding_the_rest(self):
        """`6-3, ?-7, 7-6` — never `6-3, 7-6`.

        A lossy skip shortens the list, so set three takes set two's place and
        the reader is shown a scoreline that never happened, with no marker that
        anything was dropped. This is why `sets` exists beside `games`.
        """
        broken = [
            _competitor("A Player", [
                {"value": 6.0, "winner": True},
                {"value": None, "winner": False},
                {"value": 7.0, "tiebreak": 7, "winner": True},
            ]),
            _competitor("B Player", [
                {"value": 3.0, "winner": False},
                {"value": 7.0, "winner": True},
                {"value": 6.0, "tiebreak": 3, "winner": False},
            ]),
        ]
        line = authority_linescore(
            ["A Player", "B Player"], _competition(broken), observed_at=OBSERVED
        )["linescore"]
        assert line["line"] == "6-3, ?-7, 7-6(3)"
        assert len(line["sets"]) == 3

    def test_a_trailing_slot_neither_side_has_played_is_not_a_set(self):
        empty_tail = [
            _competitor("A Player", [{"value": 6.0, "winner": True}, {"value": None}]),
            _competitor("B Player", [{"value": 3.0, "winner": False}, {"value": None}]),
        ]
        line = authority_linescore(
            ["A Player", "B Player"], _competition(empty_tail), observed_at=OBSERVED
        )["linescore"]
        assert line["line"] == "6-3"
        assert len(line["sets"]) == 1


class TestOrientation:
    def test_two_strangers_refuse_rather_than_guess(self):
        """A reversed scoreline is worse than a blank: a blank is visibly
        missing and a reversed one is confidently wrong."""
        verdict = authority_linescore(
            ["Somebody Else", "Another Person"],
            _competition(POPYRIN_TABILO),
            observed_at=OBSERVED,
        )
        assert verdict["linescore"] is None
        assert verdict["reason"] == LINESCORE_ORIENTATION_UNRESOLVED

    def test_one_name_agreeing_is_enough_because_the_other_is_forced(self):
        """`Aleksandr`/`Alexander` defeats `names_agree` outright while the
        opponent agrees cleanly — the class `orient_sides` exists to keep."""
        verdict = authority_linescore(
            ["Alexei Popyrin", "Alejandro Tabilo Zapata"],
            _competition(POPYRIN_TABILO),
            observed_at=OBSERVED,
        )
        assert verdict["reason"] is None
        assert verdict["linescore"]["line"].startswith("6-2")


class TestTheBoardReaderCarriesWhatTheLineNeeds:
    def test_scoreboard_competitions_publishes_tiebreaks_and_completion(self):
        """The parser reads ONE normalized dict, so the board reader has to put
        the tiebreak on it — `competition_sides.games` never carried one."""
        payload = {
            "events": [{
                "name": "US Open",
                "groupings": [{
                    "grouping": {"slug": "mens-singles"},
                    "competitions": [{
                        "id": "182709",
                        "date": "2026-09-03T18:45Z",
                        "status": {
                            "period": 3,
                            "type": {
                                "name": "STATUS_IN_PROGRESS",
                                "state": "in",
                                "detail": "3rd Set",
                                "shortDetail": "3rd",
                            },
                        },
                        "competitors": POPYRIN_TABILO,
                    }],
                }],
            }]
        }
        competition = scoreboard_competitions([payload])[0]
        assert competition["completion"] == "unknown"
        assert competition["status_detail"] == "3rd Set"
        assert competition["was_suspended"] is False
        assert competition["sides"][0]["sets"][1]["tiebreak"] == 7

        verdict = authority_linescore(
            ["Alexei Popyrin", "Alejandro Tabilo"], competition, observed_at=OBSERVED
        )
        assert verdict["linescore"]["line"] == "6-2, 6-7(4), 6-5"
        assert verdict["linescore"]["espn_competition_id"] == "182709"

    def test_a_refuted_row_is_captioned_by_its_set_and_not_by_its_schedule(self):
        """lane1/054's row, one reader further on.

        ESPN flips `state` to `in` on a cadence of its own and can lag by SETS,
        so a match two hours old and three sets deep is still `pre` with
        `detail` = "Wed, September 2nd at 3:30 PM EDT". `play_refutes_upcoming`
        already fixes the STATE here; without the same `set_label` substitution
        `parse_results` does, this reader would carry a date into a live card's
        caption — the exact thing `liveMatchLabel` refuses on the client.
        """
        payload = {
            "events": [{
                "name": "US Open",
                "groupings": [{
                    "grouping": {"slug": "mens-singles"},
                    "competitions": [{
                        "id": "182711",
                        "date": "2026-09-02T19:30Z",
                        "status": {
                            "period": 4,
                            "type": {
                                "name": "STATUS_SCHEDULED",
                                "state": "pre",
                                "detail": "Wed, September 2nd at 3:30 PM EDT",
                                "shortDetail": "9/2 - 3:30 PM EDT",
                            },
                        },
                        "competitors": [
                            _competitor("Carlos Taberner", [
                                {"value": 6.0, "winner": True},
                                {"value": 3.0, "winner": False},
                                {"value": 6.0, "winner": True},
                                {"value": 2.0},
                            ]),
                            _competitor("Zizou Bergs", [
                                {"value": 3.0, "winner": False},
                                {"value": 6.0, "winner": True},
                                {"value": 2.0, "winner": False},
                                {"value": 1.0},
                            ]),
                        ],
                    }],
                }],
            }]
        }
        competition = scoreboard_competitions([payload])[0]
        assert competition["state"] == "in_progress"
        assert competition["status_detail"] == "4th Set"

        line = authority_linescore(
            ["Carlos Taberner", "Zizou Bergs"], competition, observed_at=OBSERVED
        )["linescore"]
        assert line["line"] == "6-3, 3-6, 6-2, 2-1"
        assert line["current_set"] == 4
        assert "September" not in (line["status_detail"] or "")

    def test_the_lossy_games_list_is_left_exactly_as_it_was(self):
        """A CONTROL ON THE EDIT. `games` is a set TOTAL's input and its skip is
        deliberate; `sets` was added beside it, not in place of it."""
        broken = [_competitor("A Player", [
            {"value": 6.0, "winner": True},
            {"value": None, "winner": True},
        ])]
        side = competition_sides({"competitors": broken})[0]
        assert side["games"] == [6]
        assert side["sets_won"] == 2
        assert [s["games"] for s in side["sets"]] == [6, None]


class TestFormatLine:
    @pytest.mark.parametrize("rows,expected", [
        ([], ""),
        ([{"home": 6, "away": 0, "home_tiebreak": None, "away_tiebreak": None,
           "won_by": "home"}], "6-0"),
    ])
    def test_edges(self, rows, expected):
        assert format_line(rows) == expected
