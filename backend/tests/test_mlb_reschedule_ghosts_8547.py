"""#8547 half 2 — the MLB reschedule ghost: judgement, sweep verdicts, wiring.

The specimen is production on 2026-09-25: ESPN moved Saturday's BAL @ NYY into a
Friday doubleheader (401817088, "Doubleheader - Game 1 - Rescheduled from
Sep. 26") and our Saturday row 15316409 (StatPal, no espn_id, holding Kalshi's
game market) stayed behind. The same board carried the control: CHC @ BOS game 1
"Rescheduled from Sep. 27", whose Saturday row 15316408 is a REAL game (ESPN
lists it on the 26th) and must never be labelled.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import date, datetime, timezone

import pytest

from app.tasks import mlb_reschedule_ghost_sweep as sweep
from app.utils.mlb_reschedule_ghosts import (
    BoardGame,
    MlbRow,
    board_game_from_espn,
    plan_reschedule_ghosts,
    rescheduled_from,
)

NYY, BAL, BOS, CHC = "10", "1", "2", "16"
FRI, SAT, SUN = date(2026, 9, 25), date(2026, 9, 26), date(2026, 9, 27)


def _espn(eid, iso, home, away, *notes):
    return {
        "id": eid,
        "date": iso,
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


BOARD_FRI = [
    _espn(
        "401817104",
        "2026-09-25T17:05Z",
        BOS,
        CHC,
        "Doubleheader - Game 1 - Rescheduled from Sep. 27",
    ),
    _espn(
        "401817088",
        "2026-09-25T20:05Z",
        NYY,
        BAL,
        "Doubleheader - Game 1 - Rescheduled from Sep. 26",
    ),
    _espn("401817074", "2026-09-25T22:00Z", BOS, CHC, "Doubleheader - Game 2"),
    _espn("401817073", "2026-09-25T23:05Z", NYY, BAL, "Doubleheader - Game 2"),
]
BOARD_SAT = [_espn("401817089", "2026-09-26T23:15Z", BOS, CHC)]
BOARD_SUN = [_espn("401817103", "2026-09-27T19:20Z", NYY, BAL)]


def _boards(**override):
    boards = {
        FRI: tuple(board_game_from_espn(e) for e in BOARD_FRI),
        SAT: tuple(board_game_from_espn(e) for e in BOARD_SAT),
        SUN: tuple(board_game_from_espn(e) for e in BOARD_SUN),
    }
    boards.update(override)
    return boards


def _row(eid, home, away, iso, espn_id=None, score=False, tagged=False):
    return MlbRow(
        event_id=eid,
        home_team_name=home,
        away_team_name=away,
        commence_time=datetime.fromisoformat(iso).replace(tzinfo=timezone.utc),
        espn_id=espn_id,
        has_final_score=score,
        is_duplicate_tagged=tagged,
    )


def _specimen_rows(**changes):
    rows = {
        15318549: _row(
            15318549, "Boston Red Sox", "Chicago Cubs", "2026-09-25T17:05", "401817104"
        ),
        15318575: _row(
            15318575,
            "New York Yankees",
            "Baltimore Orioles",
            "2026-09-25T20:05",
            "401817088",
        ),
        15318545: _row(
            15318545, "Boston Red Sox", "Chicago Cubs", "2026-09-25T22:00", "401817074"
        ),
        15316328: _row(
            15316328, "New York Yankees", "Baltimore Orioles", "2026-09-25T23:05"
        ),
        15316408: _row(15316408, "Boston Red Sox", "Chicago Cubs", "2026-09-26T23:15"),
        15316409: _row(
            15316409, "New York Yankees", "Baltimore Orioles", "2026-09-26T23:15"
        ),
        15316428: _row(
            15316428, "New York Yankees", "Baltimore Orioles", "2026-09-27T19:20"
        ),
    }
    rows.update(changes)
    return list(rows.values())


class TestTheNote:
    @pytest.mark.parametrize(
        "headline,played,expected",
        [
            ("Doubleheader - Game 1 - Rescheduled from Sep. 26", FRI, SAT),
            ("Rescheduled from Sept. 3", date(2026, 9, 5), date(2026, 9, 3)),
            ("Rescheduled from June 12", date(2026, 7, 1), date(2026, 6, 12)),
            ("Rescheduled from Dec. 30", date(2027, 1, 2), date(2026, 12, 30)),
            ("Doubleheader - Game 2", FRI, None),
            ("Rescheduled from Foo. 3", FRI, None),
        ],
    )
    def test_the_date_a_game_moved_from(self, headline, played, expected):
        assert rescheduled_from([headline], played_on=played) == expected

    def test_two_notes_naming_two_dates_are_ambiguous(self):
        notes = ["Rescheduled from Sep. 26", "Rescheduled from Sep. 27"]
        assert rescheduled_from(notes, played_on=FRI) is None

    def test_the_board_event_parses_to_the_et_day_and_team_ids(self):
        game = board_game_from_espn(BOARD_FRI[1])
        assert game == BoardGame("401817088", NYY, BAL, FRI, SAT)

    def test_a_late_utc_start_is_dated_on_its_et_day(self):
        # 23:15Z on the 26th is 19:15 ET on the 26th; 02:10Z on the 27th is still the 26th in ET.
        game = board_game_from_espn(_espn("1", "2026-09-27T02:10Z", NYY, BAL))
        assert game.local_date == SAT


class TestTheSpecimen:
    def test_only_the_saturday_orioles_row_is_labelled(self):
        plan = plan_reschedule_ghosts(_specimen_rows(), _boards())
        assert [(t.ghost_id, t.canonical_id) for t in plan.tags] == [
            (15316409, 15318575)
        ]

    def test_the_cubs_control_is_refused_because_its_origin_day_holds_no_row(self):
        plan = plan_reschedule_ghosts(_specimen_rows(), _boards())
        assert 15316408 not in {t.ghost_id for t in plan.tags}
        assert any("401817104" in r and "0 rows" in r for r in plan.refusals)

    def test_the_counts_report_the_join(self):
        plan = plan_reschedule_ghosts(_specimen_rows(), _boards())
        assert plan.board_games_read == 6
        assert plan.anchored_board_games == 3
        assert plan.rescheduled_games_seen == 2


class TestEveryRefusal:
    def _tags(self, rows=None, boards=None):
        plan = plan_reschedule_ghosts(rows or _specimen_rows(), boards or _boards())
        return {t.ghost_id for t in plan.tags}, plan

    def test_a_dark_origin_board_proves_nothing(self):
        tags, plan = self._tags(boards=_boards(**{}) | {SAT: None})
        assert tags == set()
        assert plan.dark_days == [SAT]

    def test_an_origin_board_still_listing_the_matchup_is_a_doubleheader_day(self):
        sat = _boards()[SAT] + (
            board_game_from_espn(_espn("9", "2026-09-26T23:15Z", NYY, BAL)),
        )
        tags, _ = self._tags(boards=_boards() | {SAT: sat})
        assert tags == set()

    def test_the_origin_day_outside_the_window_is_refused(self):
        boards = _boards()
        del boards[SAT]
        tags, _ = self._tags(boards=boards)
        assert tags == set()

    def test_two_rows_on_the_origin_day_are_not_guessed_between(self):
        extra = _row(1, "New York Yankees", "Baltimore Orioles", "2026-09-26T17:05")
        tags, _ = self._tags(rows=_specimen_rows() + [extra])
        assert tags == set()

    def test_an_anchored_origin_row_is_a_real_game(self):
        rows = _specimen_rows(**{})
        rows = [
            (
                r
                if r.event_id != 15316409
                else _row(
                    15316409,
                    "New York Yankees",
                    "Baltimore Orioles",
                    "2026-09-26T23:15",
                    "999",
                )
            )
            for r in rows
        ]
        tags, _ = self._tags(rows=rows)
        assert tags == set()

    def test_a_scored_origin_row_is_a_real_game(self):
        rows = [
            (
                r
                if r.event_id != 15316409
                else _row(
                    15316409,
                    "New York Yankees",
                    "Baltimore Orioles",
                    "2026-09-26T23:15",
                    score=True,
                )
            )
            for r in _specimen_rows()
        ]
        tags, _ = self._tags(rows=rows)
        assert tags == set()

    def test_no_row_carrying_the_espn_id_means_no_canonical(self):
        rows = [r for r in _specimen_rows() if r.event_id != 15318575]
        tags, _ = self._tags(rows=rows)
        assert tags == set()

    def test_two_rows_carrying_the_espn_id_are_not_guessed_between(self):
        twin = _row(
            2, "New York Yankees", "Baltimore Orioles", "2026-09-25T20:05", "401817088"
        )
        tags, _ = self._tags(rows=_specimen_rows() + [twin])
        assert tags == set()

    def test_an_already_labelled_ghost_is_counted_not_relabelled(self):
        rows = [
            (
                r
                if r.event_id != 15316409
                else _row(
                    15316409,
                    "New York Yankees",
                    "Baltimore Orioles",
                    "2026-09-26T23:15",
                    tagged=True,
                )
            )
            for r in _specimen_rows()
        ]
        tags, plan = self._tags(rows=rows)
        assert tags == set()
        assert plan.already_tagged == 1


# ── the sweep: real task body against a fake session ────────────────────────


class _Raw:
    def __init__(self, row: MlbRow, tags_text="[]"):
        self.id = row.event_id
        self.home_team_name = row.home_team_name
        self.away_team_name = row.away_team_name
        self.commence_time = row.commence_time
        self.home_score = 5 if row.has_final_score else None
        self.away_score = 3 if row.has_final_score else None
        self.espn_id = row.espn_id
        self.tags_text = tags_text


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows, self.rowcount = list(rows), rowcount

    def all(self):
        return self._rows


class _Id:
    def __init__(self, id):
        self.id = id


class _FakeSession:
    def __init__(self, rows, *, read_raises=False, write_silently_noops=False):
        self.rows, self.read_raises, self.noop = rows, read_raises, write_silently_noops
        self.calls: list[str] = []
        self.tagged: set[int] = set()

    async def execute(self, clause, params=None):
        sql = " ".join(str(clause).split())
        params = params or {}
        if "FROM events e" in sql:
            self.calls.append("population")
            if self.read_raises:
                raise RuntimeError("connection reset")
            assert params["sport_key"] == "baseball_mlb"
            return _Result(self.rows)
        if sql.startswith("CREATE TABLE IF NOT EXISTS bak_8547_"):
            self.calls.append("create_backup_table")
            return _Result()
        if sql.startswith("INSERT INTO bak_8547_"):
            self.calls.append("bank")
            return _Result(rowcount=1)
        if sql.startswith("UPDATE events"):
            self.calls.append("append_tag")
            assert "duplicate-of:15318575" in params["tag_array"]
            if not self.noop:
                self.tagged.add(params["eid"])
            return _Result(rowcount=0 if self.noop else 1)
        if sql.startswith("SELECT id FROM events"):
            self.calls.append("verify")
            return _Result([_Id(i) for i in params["ids"] if i in self.tagged])
        raise AssertionError(f"unexpected SQL: {sql[:120]}")

    async def commit(self):
        return None

    async def rollback(self):
        return None


def _filler_board(n):
    """n anchored games on the Sunday board, so the join floor is exercised."""
    return tuple(
        BoardGame(f"f{i}", str(100 + i), str(200 + i), SUN, None) for i in range(n)
    )


def _run(monkeypatch, *, rows=None, boards=None, apply=True, fold_live=True, **kw):
    rows = rows if rows is not None else [_Raw(r) for r in _specimen_rows()]
    session = _FakeSession(rows, **kw)

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    async def _boards_for(_days):
        return boards if boards is not None else _boards()

    async def _no_sleep(_s):
        return None

    import app.tasks.base as base
    import app.tasks.soccer_ghost_twin_sweep as soccer

    monkeypatch.setattr(base, "get_task_session", _fake_session)
    monkeypatch.setattr(sweep, "fetch_boards", _boards_for)
    monkeypatch.setattr(sweep, "fold_is_live", lambda: fold_live)
    monkeypatch.setattr(soccer.asyncio, "sleep", _no_sleep)
    return asyncio.run(sweep.run_mlb_reschedule_ghost_sweep(apply=apply)), session


class TestTheSweepVerdicts:
    def test_the_specimen_is_banked_then_tagged_and_read_back(self, monkeypatch):
        summary, session = _run(monkeypatch)
        assert summary["terminal"] == "complete"
        assert summary["written"] == 1
        assert session.tagged == {15316409}
        assert (
            session.calls.index("bank")
            < session.calls.index("append_tag")
            < session.calls.index("verify")
        )
        assert summary["undo"].endswith(
            "restore_8547_mlb_reschedule_ghost_tags.py --apply"
        )

    def test_a_quiet_window_reads_green(self, monkeypatch):
        rows = [_Raw(r) for r in _specimen_rows() if r.event_id != 15316409]
        summary, session = _run(monkeypatch, rows=rows)
        assert summary["terminal"] == "complete"
        assert "append_tag" not in session.calls

    def test_a_write_that_does_not_land_is_partial(self, monkeypatch):
        summary, _ = _run(monkeypatch, write_silently_noops=True)
        assert summary["terminal"] == "partial"
        assert summary["still_untagged"] == [15316409]

    def test_a_dark_day_makes_the_window_partial_not_complete(self, monkeypatch):
        summary, _ = _run(monkeypatch, boards=_boards() | {date(2026, 9, 24): None})
        assert summary["terminal"] == "partial"
        assert summary["written"] == 1

    def test_every_board_dark_is_failed_and_unmeasured(self, monkeypatch):
        summary, _ = _run(monkeypatch, boards={FRI: None, SAT: None, SUN: None})
        assert (summary["terminal"], summary["measured"]) == ("failed", False)

    def test_a_read_that_raises_is_failed_and_unmeasured(self, monkeypatch):
        summary, _ = _run(monkeypatch, read_raises=True)
        assert (summary["terminal"], summary["measured"]) == ("failed", False)

    def test_the_off_season_is_no_work(self, monkeypatch):
        summary, _ = _run(monkeypatch, rows=[], boards={FRI: (), SAT: (), SUN: ()})
        assert summary["terminal"] == "no_work"

    def test_a_collapsed_espn_id_join_on_busy_boards_is_failed(self, monkeypatch):
        boards = _boards() | {SUN: _filler_board(sweep.BUSY_BOARD_GAMES)}
        summary, session = _run(monkeypatch, boards=boards)
        assert summary["terminal"] == "failed"
        assert "espn_id" in summary["reason"]
        assert "append_tag" not in session.calls

    def test_the_join_floor_passes_when_busy_boards_do_join(self, monkeypatch):
        filler = _filler_board(sweep.BUSY_BOARD_GAMES)
        rows = [_Raw(r) for r in _specimen_rows()] + [
            _Raw(_row(900 + i, f"H{i}", f"A{i}", "2026-09-27T17:00", g.espn_id))
            for i, g in enumerate(filler[: sweep.MIN_ANCHORED_BOARD_GAMES])
        ]
        summary, _ = _run(monkeypatch, rows=rows, boards=_boards() | {SUN: filler})
        assert summary["terminal"] == "complete"
        assert summary["written"] == 1

    def test_tags_are_withheld_loudly_when_the_fold_is_gone(self, monkeypatch):
        summary, session = _run(monkeypatch, fold_live=False)
        assert summary["terminal"] == "failed"
        assert "folded_event_ids" in summary["reason"]
        assert "append_tag" not in session.calls

    def test_a_dry_run_withholds_and_says_so(self, monkeypatch):
        summary, session = _run(monkeypatch, apply=False)
        assert summary["terminal"] == "no_work"
        assert "append_tag" not in session.calls

    def test_a_plan_above_the_ceiling_is_refused(self):
        from app.utils.mlb_reschedule_ghosts import ReschedulePlan
        from app.utils.soccer_ghost_twins import GhostTag

        plan = ReschedulePlan(
            tags=[GhostTag(i, 0, "") for i in range(sweep.MAX_EXPECTED_TAGS + 1)]
        )
        assert "ceiling" in sweep.band_refusal_reason(plan)


class TestWiring:
    def test_the_beat_entry_applies_on_the_background_queue_with_the_modules_window(
        self,
    ):
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["mlb-reschedule-ghost-sweep"]
        assert entry["task"] == "app.tasks.mlb_reschedule_ghost_sweep"
        assert entry["kwargs"] == {"apply": True}
        assert entry["options"]["queue"] == "background"
        assert entry["task"] in celery_app.tasks

    def test_it_is_enrolled_in_enforced_tasks(self):
        from app.utils.task_verdict import ENFORCED_TASKS

        assert "mlb_reschedule_ghost_sweep" in ENFORCED_TASKS

    def test_the_fold_is_live_today(self):
        assert sweep.fold_is_live() is True

    def test_the_undo_reads_the_table_the_sweep_banks_into(self):
        import importlib.util
        import pathlib

        path = (
            pathlib.Path(__file__).resolve().parents[1]
            / "scripts"
            / "restore_8547_mlb_reschedule_ghost_tags.py"
        )
        spec = importlib.util.spec_from_file_location("restore_8547", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert (
            module.BAK_TABLE == sweep.BAK_TABLE == "bak_8547_mlb_reschedule_ghost_tags"
        )
