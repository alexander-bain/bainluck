"""#4865 — the MLB row left on the day a game was POSTPONED.

The specimen is production on 2026-09-22/23. ESPN listed TOR @ BAL 401817035 on
the 22nd as ``STATUS_POSTPONED`` ("Rain - Makeup date Sep 23") and played it on
the 23rd as 401923610, "Doubleheader - Game 1 - Makeup from Sep 22". Our
odds_api row 15316846 took 401817035 and moved to the makeup hour (final 4-2);
StatPal's pre-load row 15317711 stayed on the 22nd, ``suspended`` at 0-0, no
espn_id, and search for "blue jays" printed it as "No result reported · Sep 22".
The #8547 arms never saw it: there is no "Rescheduled from" note, and ESPN
still lists the pairing on the 22nd.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.tasks import mlb_reschedule_ghost_sweep as sweep
from app.utils.mlb_reschedule_ghosts import (
    ESPN_POSTPONED,
    MlbRow,
    board_game_from_espn,
    makeup_from,
    plan_reschedule_ghosts,
    score_is_placeholder,
)

BAL, TOR, NYY, BOS = "1", "14", "10", "2"
TUE, WED = date(2026, 9, 22), date(2026, 9, 23)


def _espn(eid, iso, home, away, *notes, status="STATUS_FINAL"):
    return {
        "id": eid,
        "date": iso,
        "status": {"type": {"name": status}},
        "competitions": [
            {
                "competitors": [
                    {"homeAway": "home", "id": home, "team": {"id": home}},
                    {"homeAway": "away", "id": away, "team": {"id": away}},
                ],
                "notes": [{"type": "event", "headline": n} for n in notes],
            }
        ],
    }


POSTPONED = _espn(
    "401817035",
    "2026-09-22T22:35Z",
    BAL,
    TOR,
    "Rain - Makeup date Sep 23",
    status=ESPN_POSTPONED,
)
BOARD_TUE = [POSTPONED, _espn("401817040", "2026-09-22T23:05Z", NYY, BOS)]
BOARD_WED = [
    _espn(
        "401923610",
        "2026-09-23T17:35Z",
        BAL,
        TOR,
        "Doubleheader - Game 1 - Makeup from Sep 22",
    ),
    _espn("401817050", "2026-09-23T22:35Z", BAL, TOR, "Doubleheader - Game 2"),
]


def _boards(tue=None, wed=None):
    return {
        TUE: tuple(board_game_from_espn(e) for e in (tue or BOARD_TUE)),
        WED: tuple(board_game_from_espn(e) for e in (wed or BOARD_WED)),
    }


def _row(eid, iso, espn_id=None, score=False, placeholder=False, tagged=False):
    return MlbRow(
        event_id=eid,
        home_team_name="Baltimore Orioles",
        away_team_name="Toronto Blue Jays",
        commence_time=datetime.fromisoformat(iso).replace(tzinfo=timezone.utc),
        espn_id=espn_id,
        has_final_score=score,
        is_duplicate_tagged=tagged,
        score_is_placeholder=placeholder,
    )


GHOST = _row(15317711, "2026-09-22T22:35", score=True, placeholder=True)
MADE_UP = _row(15316846, "2026-09-23T17:35", "401817035", score=True)
GAME_2 = _row(15317724, "2026-09-23T22:35", "401817050", score=True)


def _tags(rows, boards=None):
    plan = plan_reschedule_ghosts(rows, boards or _boards())
    return [(t.ghost_id, t.canonical_id) for t in plan.tags], plan


class TestTheSpecimen:
    def test_the_rained_out_row_is_labelled_a_duplicate_of_the_made_up_game(self):
        tags, plan = _tags([GHOST, MADE_UP, GAME_2])
        assert tags == [(15317711, 15316846)]
        assert plan.tags[0].reason.startswith("mlb_postponed: espn 401817035")
        assert plan.postponed_games_seen == 1

    def test_the_makeup_note_names_the_made_up_game_when_our_row_took_its_id(self):
        made_up = _row(15316846, "2026-09-23T17:35", "401923610", score=True)
        tags, _ = _tags([GHOST, made_up, GAME_2])
        assert tags == [(15317711, 15316846)]

    def test_a_ghost_with_no_score_at_all_is_labelled_too(self):
        ghost = _row(15317711, "2026-09-22T22:35")
        tags, _ = _tags([ghost, MADE_UP, GAME_2])
        assert tags == [(15317711, 15316846)]


class TestEveryRefusal:
    def test_a_row_with_a_real_result_on_the_postponed_day_is_left_alone(self):
        scored = _row(15317711, "2026-09-22T22:35", score=True, placeholder=False)
        tags, plan = _tags([scored, MADE_UP, GAME_2])
        assert tags == []
        assert any("anchored or scored" in r for r in plan.refusals)

    def test_an_anchored_row_on_the_postponed_day_is_left_alone(self):
        anchored = _row(15317711, "2026-09-22T22:35", "999", placeholder=True)
        tags, _ = _tags([anchored, MADE_UP, GAME_2])
        assert tags == []

    def test_the_postponed_game_held_on_its_own_day_is_not_a_ghost(self):
        # Our row kept 401817035 on the 22nd (correct: it WAS postponed). The
        # made-up game is found by its note, and the 22nd row is anchored.
        held = _row(15317711, "2026-09-22T22:35", "401817035")
        made_up = _row(15316846, "2026-09-23T17:35", "401923610", score=True)
        tags, plan = _tags([held, made_up, GAME_2])
        assert tags == []
        assert any("anchored or scored" in r for r in plan.refusals)

    def test_a_game_that_was_not_postponed_is_never_read_by_this_arm(self):
        played = dict(POSTPONED, status={"type": {"name": "STATUS_FINAL"}})
        tags, plan = _tags([GHOST, MADE_UP, GAME_2], _boards(tue=[played]))
        assert tags == []
        assert plan.postponed_games_seen == 0

    def test_a_doubleheader_day_with_one_game_postponed_is_refused(self):
        tue = BOARD_TUE + [_espn("401817036", "2026-09-22T17:05Z", BAL, TOR)]
        tags, plan = _tags([GHOST, MADE_UP, GAME_2], _boards(tue=tue))
        assert tags == []
        assert any("2 times on 2026-09-22" in r for r in plan.refusals)

    def test_two_rows_claiming_to_be_the_made_up_game_are_not_guessed_between(self):
        second = _row(15318000, "2026-09-23T17:35", "401923610", score=True)
        tags, plan = _tags([GHOST, MADE_UP, second, GAME_2])
        assert tags == []
        assert any("2 rows are the made-up game" in r for r in plan.refusals)

    def test_no_made_up_row_means_no_canonical(self):
        tags, plan = _tags([GHOST, GAME_2])
        assert tags == []
        assert any("0 rows are the made-up game" in r for r in plan.refusals)

    def test_a_dark_postponed_day_proves_nothing(self):
        boards = _boards() | {TUE: None}
        tags, _ = _tags([GHOST, MADE_UP, GAME_2], boards)
        assert tags == []

    def test_two_unanchored_rows_on_the_postponed_day_are_not_guessed_between(self):
        other = _row(15317999, "2026-09-22T17:05", placeholder=True)
        tags, _ = _tags([GHOST, other, MADE_UP, GAME_2])
        assert tags == []

    def test_an_already_labelled_ghost_is_counted_not_relabelled(self):
        tagged = _row(15317711, "2026-09-22T22:35", tagged=True)
        tags, plan = _tags([tagged, MADE_UP, GAME_2])
        assert tags == []
        assert plan.already_tagged == 1


class TestTheInputs:
    def test_the_board_reads_the_status_and_the_makeup_date(self):
        tue, wed = board_game_from_espn(POSTPONED), board_game_from_espn(BOARD_WED[0])
        assert (tue.status, tue.makeup_from) == (ESPN_POSTPONED, None)
        assert (wed.status, wed.makeup_from) == ("STATUS_FINAL", TUE)

    @pytest.mark.parametrize(
        "headline,expected",
        [
            ("Doubleheader - Game 1 - Makeup from Sep 22", TUE),
            ("Makeup from Sept. 22", TUE),
            ("Rain - Makeup date Sep 23", None),
            ("Doubleheader - Game 1 - Rescheduled from Sep. 22", None),
        ],
    )
    def test_the_makeup_note(self, headline, expected):
        assert makeup_from([headline], played_on=WED) == expected

    @pytest.mark.parametrize(
        "home,away,status,expected",
        [
            (0, 0, "suspended", True),
            (0, 0, "scheduled", True),
            (0, 0, "completed", False),
            (0, 0, "live", False),
            (0, 0, "closed", False),
            (1, 0, "suspended", False),
            (None, None, "suspended", False),
        ],
    )
    def test_a_zero_zero_is_a_result_only_on_a_completed_row(
        self, home, away, status, expected
    ):
        assert (
            score_is_placeholder(home_score=home, away_score=away, status=status)
            is expected
        )

    def test_the_sweep_reads_status_so_the_placeholder_reaches_the_rule(self):
        assert "e.status" in sweep._POPULATION_SQL

        class _Raw:
            id, home_team_name, away_team_name = (
                15317711,
                "Baltimore Orioles",
                "Toronto Blue Jays",
            )
            commence_time = GHOST.commence_time
            home_score = away_score = 0
            espn_id, status, tags_text = None, "suspended", "[]"

        (row,) = sweep.build_rows([_Raw])
        assert row.has_final_score and row.score_is_placeholder
        tags, _ = _tags([row, MADE_UP, GAME_2])
        assert tags == [(15317711, 15316846)]
