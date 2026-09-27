"""#9187 — an NHL game stops appearing on two days.

Specimen, production 2026-09-27: the Odds API listed Chicago @ Vegas twice —
``deceabd9…`` at 2026-09-30T02:40Z (the real game) and a phantom ``ec5a4b4a…``
at 21:30:10Z. ESPN listed ONE game, 401891775 at 02:30Z (the 29th in ET). Row
15168035 holds ESPN's id; row 15320181 mirrors the phantom with no id, and
search showed the game on Sep 29 and again on Sep 30. Run over production's
NHL rows and live ESPN boards (-7d/+3d) the arm labels exactly that one row;
the MLB control with the arm forced on labels nothing.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import date, datetime, timezone

from app.tasks import mlb_reschedule_ghost_sweep as sweep
from app.utils.mlb_reschedule_ghosts import (
    MlbRow,
    board_game_from_espn,
    plan_reschedule_ghosts,
)

VGK, CHI, CAR, FLA = "37", "4", "7", "26"
TUE, WED = date(2026, 9, 29), date(2026, 9, 30)
GHOST, CANON, EID = 15320181, 15168035, "401891775"


def _espn(eid, iso, home, away, season_type=2):
    return {
        "id": eid,
        "date": iso,
        "season": {"year": 2027, "type": season_type},
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


TUE_BOARD = _board(
    _espn(EID, "2026-09-30T02:30Z", VGK, CHI),
    _espn("401891773", "2026-09-29T21:00Z", CAR, FLA),
)
WED_BOARD = _board(_espn("401891800", "2026-09-30T23:00Z", CAR, "15"))


def _row(eid, iso, espn_id=None, score=False, tagged=False,
         home="Vegas Golden Knights", away="Chicago Blackhawks"):
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
        CANON: _row(CANON, "2026-09-30T02:30", EID),
        GHOST: _row(GHOST, "2026-09-30T21:30:10"),
        7: _row(7, "2026-09-29T21:00", "401891773",
                home="Carolina Hurricanes", away="Florida Panthers"),
    }
    rows.update(over or {})
    return [r for r in rows.values() if r is not None]


def _plan(rows=None, boards=None, arm=True):
    return plan_reschedule_ghosts(
        rows if rows is not None else _rows(),
        boards if boards is not None else {TUE: TUE_BOARD, WED: WED_BOARD},
        adjacent_day_arm=arm,
    )


def _tags(plan):
    return [(t.ghost_id, t.canonical_id) for t in plan.tags]


class TestTheSpecimen:
    def test_the_phantom_row_is_labelled_a_copy_of_the_row_holding_espns_id(self):
        plan = _plan()
        assert _tags(plan) == [(GHOST, CANON)]
        assert plan.tags[0].reason.startswith("unlisted_adjacent_day: espn 401891775")
        assert plan.adjacent_day_games_with_extra_rows == 1

    def test_the_arm_is_off_unless_the_caller_asks_for_it(self):
        plan = _plan(arm=False)
        assert plan.tags == [] and plan.adjacent_day_games_with_extra_rows == 0

    def test_a_ghost_the_day_before_is_the_same_evidence(self):
        mon = date(2026, 9, 28)
        plan = _plan(
            _rows({GHOST: _row(GHOST, "2026-09-28T21:30:10")}),
            boards={mon: _board(_espn("401891700", "2026-09-28T23:00Z", CAR, FLA)),
                    TUE: TUE_BOARD, WED: WED_BOARD},
        )
        assert _tags(plan) == [(GHOST, CANON)]

    def test_the_season_type_is_read_off_the_board(self):
        assert TUE_BOARD[0].season_type == 2
        bare = board_game_from_espn({**_espn(EID, "2026-09-30T02:30Z", VGK, CHI), "season": None})
        assert bare.season_type is None


class TestEveryRefusal:
    def test_espn_listing_the_pair_on_the_next_day_is_a_real_game(self):
        wed = WED_BOARD + _board(_espn("401891801", "2026-09-30T21:30Z", VGK, CHI))
        assert _plan(boards={TUE: TUE_BOARD, WED: wed}).tags == []

    def test_a_home_and_home_on_the_next_day_is_a_real_game(self):
        wed = WED_BOARD + _board(_espn("401891801", "2026-10-01T02:00Z", CHI, VGK))
        assert _plan(boards={TUE: TUE_BOARD, WED: wed}).tags == []

    def test_a_dark_neighbouring_board_proves_nothing(self):
        assert _plan(boards={TUE: TUE_BOARD, WED: None}).tags == []

    def test_an_empty_neighbouring_board_proves_nothing(self):
        assert _plan(boards={TUE: TUE_BOARD, WED: ()}).tags == []

    def test_an_unread_neighbouring_day_proves_nothing(self):
        assert _plan(boards={TUE: TUE_BOARD}).tags == []

    def test_a_postseason_game_is_never_asked(self):
        tue = _board(_espn(EID, "2026-09-30T02:30Z", VGK, CHI, season_type=3))
        assert _plan(boards={TUE: tue, WED: WED_BOARD}).tags == []

    def test_an_unreadable_season_type_is_never_asked(self):
        tue = _board({**_espn(EID, "2026-09-30T02:30Z", VGK, CHI), "season": {}})
        assert _plan(boards={TUE: tue, WED: WED_BOARD}).tags == []

    def test_preseason_is_asked(self):
        tue = _board(_espn(EID, "2026-09-30T02:30Z", VGK, CHI, season_type=1))
        assert _tags(_plan(boards={TUE: tue, WED: WED_BOARD})) == [(GHOST, CANON)]

    def test_espn_listing_the_pair_twice_on_the_day_is_left_alone(self):
        tue = TUE_BOARD + _board(_espn("401891802", "2026-09-29T17:00Z", VGK, CHI))
        assert _plan(boards={TUE: tue, WED: WED_BOARD}).tags == []

    def test_a_scored_ghost_is_a_real_game(self):
        plan = _plan(_rows({GHOST: _row(GHOST, "2026-09-30T21:30:10", score=True)}))
        assert plan.tags == []
        assert any("anchored or scored" in r for r in plan.refusals)

    def test_an_anchored_ghost_is_a_real_game(self):
        assert _plan(_rows({GHOST: _row(GHOST, "2026-09-30T21:30:10", "999")})).tags == []

    def test_two_rows_on_the_neighbouring_day_are_not_guessed_between(self):
        plan = _plan(_rows({1: _row(1, "2026-09-30T23:00")}))
        assert plan.tags == []
        assert any("2 rows for the matchup" in r for r in plan.refusals)

    def test_no_row_carrying_the_id_means_no_canonical(self):
        assert _plan(_rows({CANON: _row(CANON, "2026-09-30T02:30")})).tags == []

    def test_two_rows_carrying_the_id_are_not_guessed_between(self):
        assert _plan(_rows({2: _row(2, "2026-09-30T02:30", EID)})).tags == []

    def test_a_canonical_dated_off_its_board_day_is_not_trusted(self):
        # 15:00Z on the 30th is the 30th in ET; ESPN put the game on the 29th.
        assert _plan(_rows({CANON: _row(CANON, "2026-09-30T15:00", EID)})).tags == []

    def test_a_canonical_that_is_itself_a_copy_is_not_trusted(self):
        plan = _plan(_rows({CANON: _row(CANON, "2026-09-30T02:30", EID, tagged=True)}))
        assert plan.tags == []

    def test_home_and_away_reversed_is_a_different_pairing_row(self):
        flipped = _row(3, "2026-09-30T21:30:10",
                       home="Chicago Blackhawks", away="Vegas Golden Knights")
        assert _plan(_rows({GHOST: None, 3: flipped})).tags == []

    def test_an_already_labelled_copy_is_counted_not_relabelled(self):
        plan = _plan(_rows({GHOST: _row(GHOST, "2026-09-30T21:30:10", tagged=True)}))
        assert plan.tags == [] and plan.already_tagged == 1


class TestTheSweep:
    def test_only_the_nhl_pass_runs_the_arm(self):
        assert sweep.ADJACENT_DAY_SPORTS == frozenset({"icehockey_nhl"})
        assert sweep.SPORT_KEY not in sweep.ADJACENT_DAY_SPORTS

    def _run(self, monkeypatch, sport_key):
        seen = {}

        class _R:
            def __init__(self, r):
                self.id, self.home_team_name, self.away_team_name = (
                    r.event_id, r.home_team_name, r.away_team_name)
                self.commence_time, self.espn_id = r.commence_time, r.espn_id
                self.home_score = self.away_score = None
                self.status = "scheduled"
                self.tags_text = "[]"

        class _Res:
            def __init__(self, rows=()):
                self._rows, self.rowcount = list(rows), 0

            def all(self):
                return self._rows

        class _S:
            async def execute(self, clause, params=None):
                sql = " ".join(str(clause).split())
                if "FROM events e" in sql:
                    seen["sql_sport"] = params["sport_key"]
                    return _Res([_R(r) for r in _rows()])
                raise AssertionError("dry run must not write")

            async def commit(self):
                return None

            async def rollback(self):
                return None

        @contextlib.asynccontextmanager
        async def _sess():
            yield _S()

        async def _boards(_days, sport_key=sweep.SPORT_KEY):
            seen["board_sport"] = sport_key
            return {TUE: TUE_BOARD, WED: WED_BOARD}

        import app.tasks.base as base

        monkeypatch.setattr(base, "get_task_session", _sess)
        monkeypatch.setattr(sweep, "fetch_boards", _boards)
        monkeypatch.setattr(sweep, "fold_is_live", lambda: True)
        summary = asyncio.run(
            sweep.run_mlb_reschedule_ghost_sweep(apply=False, sport_key=sport_key)
        )
        return summary, seen

    def test_the_nhl_pass_reads_nhl_and_plans_the_phantom(self, monkeypatch):
        summary, seen = self._run(monkeypatch, sweep.NHL_SPORT_KEY)
        assert seen == {"sql_sport": "icehockey_nhl", "board_sport": "icehockey_nhl"}
        assert summary["task"] == "nhl_adjacent_day_ghost_sweep"
        assert summary["adjacent_day_games_with_extra_rows"] == 1
        assert summary["tag_sample"][0]["ghost"] == GHOST
        assert summary["terminal"] == "no_work"  # dry run withholds

    def test_the_mlb_pass_on_the_same_rows_plans_nothing(self, monkeypatch):
        summary, seen = self._run(monkeypatch, sweep.SPORT_KEY)
        assert seen["board_sport"] == "baseball_mlb"
        assert summary["task"] == "mlb_reschedule_ghost_sweep"
        assert summary["tags_to_write"] == 0

    def test_the_task_is_scheduled_on_the_background_queue(self):
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["nhl-adjacent-day-ghost-sweep"]
        assert entry["task"] == "app.tasks.nhl_adjacent_day_ghost_sweep"
        assert entry["kwargs"] == {"apply": True}
        assert entry["options"] == {"queue": "background"}

    def test_the_task_is_enrolled_in_the_verdict_contract(self):
        from app.utils.task_verdict import ENFORCED_TASKS

        assert "nhl_adjacent_day_ghost_sweep" in ENFORCED_TASKS

    def test_the_real_board_read_asks_espn_for_the_passs_sport(self, monkeypatch):
        import app.services.espn_api as espn_api

        asked = []

        class _Svc:
            async def get_combat_card_board(self, sport_key, dates=None):
                asked.append((sport_key, dates))
                return {"events": [_espn(EID, "2026-09-30T02:30Z", VGK, CHI)]} if dates == "20260929" else None

        monkeypatch.setattr(espn_api, "get_espn_service", lambda: _Svc())
        boards = asyncio.run(sweep.fetch_boards([TUE, WED], sweep.NHL_SPORT_KEY))
        assert asked == [("icehockey_nhl", "20260929"), ("icehockey_nhl", "20260930")]
        assert boards[TUE][0].espn_id == EID and boards[WED] is None
