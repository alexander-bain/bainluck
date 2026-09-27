"""#8952 — an MLB game moved to another hour of the SAME day stops showing twice.

Specimen, production 2026-09-26: ESPN moved Sunday's BAL @ NYY from 19:20Z to
17:05Z (401817103, no "Rescheduled from" note — the day did not change). The
odds_api row 15319530 took the 17:05 slot and ESPN's id; StatPal's pre-load row
15316428 stayed at 19:20 with no id, and search served both.
"""

from __future__ import annotations

from datetime import date, datetime, timezone


from app.tasks import mlb_reschedule_ghost_sweep as sweep
from app.utils.mlb_reschedule_ghosts import (
    MlbRow,
    board_game_from_espn,
    plan_reschedule_ghosts,
)

NYY, BAL, BOS, CHC = "10", "1", "2", "16"
SUN = date(2026, 9, 27)
GHOST, CANON, EID = 15316428, 15319530, "401817103"


def _espn(eid, iso, home, away):
    return {
        "id": eid,
        "date": iso,
        "competitions": [
            {
                "competitors": [
                    {"homeAway": "home", "team": {"id": home}},
                    {"homeAway": "away", "team": {"id": away}},
                ],
                "notes": [],
            }
        ],
    }


def _board(*events):
    return tuple(board_game_from_espn(e) for e in events)


SUN_BOARD = _board(
    _espn(EID, "2026-09-27T17:05Z", NYY, BAL),
    _espn("401817110", "2026-09-27T17:35Z", BOS, CHC),
)


def _row(
    eid,
    iso,
    espn_id=None,
    score=False,
    tagged=False,
    home="New York Yankees",
    away="Baltimore Orioles",
):
    return MlbRow(
        event_id=eid,
        home_team_name=home,
        away_team_name=away,
        commence_time=datetime.fromisoformat(iso).replace(tzinfo=timezone.utc),
        espn_id=espn_id,
        has_final_score=score,
        is_duplicate_tagged=tagged,
    )


def _rows(over=None):
    rows = {
        CANON: _row(CANON, "2026-09-27T17:05", EID),
        GHOST: _row(GHOST, "2026-09-27T19:20"),
        7: _row(
            7,
            "2026-09-27T17:35",
            "401817110",
            home="Boston Red Sox",
            away="Chicago Cubs",
        ),
    }
    rows.update(over or {})
    return [r for r in rows.values() if r is not None]


def _plan(rows=None, board=SUN_BOARD, boards=None):
    return plan_reschedule_ghosts(
        rows if rows is not None else _rows(), boards or {SUN: board}
    )


def _tags(plan):
    return [(t.ghost_id, t.canonical_id) for t in plan.tags]


class TestTheSpecimen:
    def test_the_1920_row_is_labelled_a_copy_of_the_row_holding_espns_id(self):
        plan = _plan()
        assert _tags(plan) == [(GHOST, CANON)]
        assert plan.tags[0].reason.startswith("mlb_same_day_move: espn 401817103")
        assert plan.same_day_games_with_extra_rows == 1

    def test_a_game_with_no_second_row_is_neither_labelled_nor_refused(self):
        plan = _plan(_rows({GHOST: None}))
        assert plan.tags == [] and plan.refusals == []
        assert plan.same_day_games_with_extra_rows == 0

    def test_the_same_minute_twin_is_the_same_evidence(self):
        plan = _plan(_rows({GHOST: _row(GHOST, "2026-09-27T17:05")}))
        assert _tags(plan) == [(GHOST, CANON)]


class TestEveryRefusal:
    def test_a_doubleheader_day_is_left_alone(self):
        board = SUN_BOARD + _board(_espn("401817111", "2026-09-27T23:05Z", NYY, BAL))
        assert _plan(board=board).tags == []

    def test_a_dark_board_proves_nothing(self):
        assert _plan(boards={SUN: None}).tags == []

    def test_a_scored_second_row_is_a_real_game(self):
        plan = _plan(_rows({GHOST: _row(GHOST, "2026-09-27T19:20", score=True)}))
        assert plan.tags == []
        assert any("anchored or scored" in r for r in plan.refusals)

    def test_an_anchored_second_row_is_a_real_game(self):
        plan = _plan(_rows({GHOST: _row(GHOST, "2026-09-27T19:20", "999")}))
        assert plan.tags == []

    def test_two_other_rows_are_not_guessed_between(self):
        plan = _plan(_rows({1: _row(1, "2026-09-27T21:00")}))
        assert plan.tags == []
        assert any("2 rows for the matchup" in r for r in plan.refusals)

    def test_no_row_carrying_the_id_means_no_canonical(self):
        assert _plan(_rows({CANON: _row(CANON, "2026-09-27T17:05")})).tags == []

    def test_two_rows_carrying_the_id_are_not_guessed_between(self):
        assert _plan(_rows({2: _row(2, "2026-09-27T17:05", EID)})).tags == []

    def test_a_canonical_dated_another_day_is_not_trusted(self):
        plan = _plan(_rows({CANON: _row(CANON, "2026-09-26T17:05", EID)}))
        assert plan.tags == []

    def test_a_canonical_that_is_itself_a_copy_is_not_trusted(self):
        plan = _plan(_rows({CANON: _row(CANON, "2026-09-27T17:05", EID, tagged=True)}))
        assert plan.tags == []

    def test_each_pairing_is_labelled_onto_its_own_game(self):
        plan = _plan(
            _rows(
                {
                    8: _row(
                        8,
                        "2026-09-27T20:00",
                        home="Boston Red Sox",
                        away="Chicago Cubs",
                    )
                }
            )
        )
        assert _tags(plan) == [(8, 7), (GHOST, CANON)]

    def test_home_and_away_reversed_is_a_different_pairing_row(self):
        flipped = _row(
            3, "2026-09-27T19:20", home="Baltimore Orioles", away="New York Yankees"
        )
        plan = _plan(_rows({GHOST: None, 3: flipped}))
        assert plan.tags == []

    def test_an_already_labelled_copy_is_counted_not_relabelled(self):
        plan = _plan(_rows({GHOST: _row(GHOST, "2026-09-27T19:20", tagged=True)}))
        assert plan.tags == [] and plan.already_tagged == 1


class TestTheSweepReportsTheArm:
    def test_the_summary_carries_the_same_day_count(self, monkeypatch):
        import asyncio
        import contextlib

        class _R:
            def __init__(self, r):
                self.id, self.home_team_name, self.away_team_name = (
                    r.event_id,
                    r.home_team_name,
                    r.away_team_name,
                )
                self.commence_time, self.espn_id = r.commence_time, r.espn_id
                self.home_score = self.away_score = None
                self.status = "scheduled"
                self.tags_text = "[]"

        class _Res:
            def __init__(self, rows=(), rowcount=0):
                self._rows, self.rowcount = list(rows), rowcount

            def all(self):
                return self._rows

        class _S:
            async def execute(self, clause, params=None):
                sql = " ".join(str(clause).split())
                if "FROM events e" in sql:
                    return _Res([_R(r) for r in _rows()])
                raise AssertionError("dry run must not write")

            async def commit(self):
                return None

            async def rollback(self):
                return None

        @contextlib.asynccontextmanager
        async def _sess():
            yield _S()

        async def _boards(_days):
            return {SUN: SUN_BOARD}

        import app.tasks.base as base

        monkeypatch.setattr(base, "get_task_session", _sess)
        monkeypatch.setattr(sweep, "fetch_boards", _boards)
        monkeypatch.setattr(sweep, "fold_is_live", lambda: True)
        summary = asyncio.run(sweep.run_mlb_reschedule_ghost_sweep(apply=False))
        assert summary["same_day_games_with_extra_rows"] == 1
        assert summary["tags_to_write"] == 1
        assert summary["tag_sample"][0]["ghost"] == GHOST
