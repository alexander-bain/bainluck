"""#11152 — the playoff game left on the schedule after its series ended.

The specimen is production on 2026-10-16: the Odds API listed NLCS Game 5
(row 15330460, Oct 17 00:00Z, no ESPN id) before Game 4, Milwaukee won Game 4
(ESPN 401908033, our row 15330459) and the series 4-0, and Sports kept offering
Game 5. The boards are ESPN's real ones for Oct 13/15/16, trimmed
(``fixtures/espn_mlb_11152/boards.json``); the Oct 16 board carries the control
that must survive — Rays–Guardians ALCS Game 4 (15330795), a live series at 2-1.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.tasks import unplayed_series_game_sweep as sweep
from app.utils.unplayed_series_games import (
    SeriesBoardGame,
    SeriesRow,
    plan_unplayed_series_games,
    retirement_tag,
    series_board_game_from_espn,
    series_is_over,
)

FIXTURE = Path(__file__).parent / "fixtures" / "espn_mlb_11152" / "boards.json"
OCT13, OCT14, OCT15, OCT16, OCT17 = (date(2026, 10, d) for d in (13, 14, 15, 16, 17))
LAD, MIL, TB, CLE = "19", "8", "30", "5"


def _raw_boards() -> dict:
    return json.loads(FIXTURE.read_text())["boards"]


def _boards(**override) -> dict:
    raw = _raw_boards()
    boards = {
        date(int(k[:4]), int(k[4:6]), int(k[6:])): tuple(
            g for g in (series_board_game_from_espn(e) for e in v["events"]) if g
        )
        for k, v in raw.items()
    }
    boards[OCT14] = ()  # read, no game for either pair that day
    for k, v in override.items():
        boards[date.fromisoformat(k.replace("_", "-")[1:])] = v
    return boards


def _ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


def _row(eid, home, away, iso, espn_id=None, status="scheduled", score=None, tagged=False):
    return SeriesRow(
        event_id=eid,
        home_team_name=home,
        away_team_name=away,
        commence_time=_ts(iso),
        espn_id=espn_id,
        status=status,
        home_score=score[0] if score else None,
        away_score=score[1] if score else None,
        is_retirement_tagged=tagged,
    )


def _specimen_rows(changes: dict | None = None) -> list[SeriesRow]:
    """Production's MLB rows for the window, 2026-10-16 23:39Z."""
    rows = [
        _row(15329564, "Tampa Bay Rays", "Cleveland Guardians", "2026-10-14T00:00", "401908024", "completed", (3, 1)),
        _row(15329526, "Los Angeles Dodgers", "Milwaukee Brewers", "2026-10-15T00:00", "401908032", "completed", (2, 6)),
        _row(15329956, "Cleveland Guardians", "Tampa Bay Rays", "2026-10-15T17:00", "401908025", "completed", (3, 2)),
        _row(15330459, "Los Angeles Dodgers", "Milwaukee Brewers", "2026-10-16T00:00", "401908033", "completed", (4, 6)),
        _row(15330460, "Los Angeles Dodgers", "Milwaukee Brewers", "2026-10-17T00:00"),
        _row(15330795, "Cleveland Guardians", "Tampa Bay Rays", "2026-10-17T00:00", "401908026"),
        _row(15329975, "Cleveland Guardians", "Tampa Bay Rays", "2026-10-18T00:00", "401908027"),
    ]
    return [replace(r, **(changes or {}).get(r.event_id, {})) for r in rows]


def _game(espn_id, home, away, day, *, wins, total=7, completed, status="STATUS_FINAL", season=3):
    from app.utils.postseason_series import PlayoffSeries

    return SeriesBoardGame(
        espn_id=espn_id,
        home_team_id=home,
        away_team_id=away,
        local_date=day,
        status=status,
        season_type=season,
        series=PlayoffSeries(game_number=None, total_games=total, wins=wins, completed=completed),
    )


class TestTheParse:
    def test_espns_real_game_4_reads_as_a_finished_series(self):
        game = next(g for g in _boards()[OCT15] if g.espn_id == "401908033")
        assert (game.home_team_id, game.away_team_id) == (LAD, MIL)
        assert game.series.completed is True and sorted(game.series.wins) == [0, 4]
        assert series_is_over(game) is True

    def test_espns_live_alcs_is_not_over(self):
        for day in (OCT13, OCT15, OCT16):
            for g in _boards()[day]:
                if g.pair == frozenset({TB, CLE}):
                    assert series_is_over(g) is False, g.espn_id

    @pytest.mark.parametrize(
        "change",
        [
            {"completed": False},           # ESPN does not say it is over
            {"completed": None},            # ESPN says nothing
            {"wins": (3, 0)},               # completed, but the arithmetic disagrees
            {"wins": (4,)},                 # not two win counts
            {"total": None},                # no series length
        ],
    )
    def test_any_gap_or_contradiction_is_not_over(self, change):
        kw = {"wins": (0, 4), "completed": True, "total": 7} | change
        game = _game("x", LAD, MIL, OCT15, **kw)
        assert series_is_over(game) is False

    def test_a_game_not_final_or_not_postseason_is_not_over(self):
        assert not series_is_over(_game("x", LAD, MIL, OCT15, wins=(0, 4), completed=True, status="STATUS_IN_PROGRESS"))
        assert not series_is_over(_game("x", LAD, MIL, OCT15, wins=(0, 4), completed=True, season=2))


class TestTheSpecimen:
    def test_game_5_is_retired_on_game_4s_clinch_and_nothing_else_is(self):
        plan = plan_unplayed_series_games(_specimen_rows(), _boards())
        assert [(r.event_id, r.clinching_espn_id, r.clinching_event_id) for r in plan.retirements] == [
            (15330460, "401908033", 15330459)
        ]
        assert plan.clinched_series_seen == 1
        assert plan.refusals == []

    def test_the_real_alcs_game_tonight_and_game_5_stay(self):
        retired = {r.event_id for r in plan_unplayed_series_games(_specimen_rows(), _boards()).retirements}
        assert not retired & {15330795, 15329975, 15330459}

    @pytest.mark.parametrize("status", ["live", "suspended"])
    def test_a_row_its_clock_already_promoted_is_still_retired(self, status):
        rows = _specimen_rows({15330460: {"status": status}})
        assert [r.event_id for r in plan_unplayed_series_games(rows, _boards()).retirements] == [15330460]

    def test_an_already_retired_row_is_counted_not_replanned(self):
        rows = _specimen_rows({15330460: {"is_retirement_tagged": True}})
        plan = plan_unplayed_series_games(rows, _boards())
        assert plan.retirements == [] and plan.already_retired == 1


class TestEveryControl:
    def test_an_open_series_needing_game_5_retires_nothing(self):
        # Same rows, but Game 4 left the series at 3-1 to Milwaukee.
        open_g4 = _game("401908033", LAD, MIL, OCT15, wins=(1, 3), completed=False)
        boards = _boards() | {OCT15: tuple(g for g in _boards()[OCT15] if g.espn_id != "401908033") + (open_g4,)}
        plan = plan_unplayed_series_games(_specimen_rows(), boards)
        assert plan.retirements == [] and plan.clinched_series_seen == 0

    def test_a_pair_espn_lists_on_the_rows_day_is_refused(self):
        # A rescheduled game or doubleheader: ESPN lists the pair on Oct 16.
        listed = _game("401999999", LAD, MIL, OCT16, wins=(0, 4), completed=True, status="STATUS_SCHEDULED")
        boards = _boards() | {OCT16: _boards()[OCT16] + (listed,)}
        plan = plan_unplayed_series_games(_specimen_rows(), boards)
        assert plan.retirements == []
        assert any("still lists the pair" in r for r in plan.refusals)

    def test_a_dark_board_on_the_rows_day_is_refused(self):
        plan = plan_unplayed_series_games(_specimen_rows(), _boards() | {OCT16: None})
        assert plan.retirements == []
        assert any("dark" in r for r in plan.refusals)

    def test_a_dark_board_on_the_clinch_day_proves_nothing(self):
        plan = plan_unplayed_series_games(_specimen_rows(), _boards() | {OCT15: None})
        assert plan.retirements == [] and plan.clinched_series_seen == 0

    def test_a_row_outside_the_boards_read_is_refused(self):
        boards = {d: g for d, g in _boards().items() if d != OCT16}
        plan = plan_unplayed_series_games(_specimen_rows(), boards)
        assert plan.retirements == []
        assert any("outside the window" in r for r in plan.refusals)

    def test_an_anchored_row_is_refused(self):
        rows = _specimen_rows({15330460: {"espn_id": "401908034"}})
        plan = plan_unplayed_series_games(rows, _boards())
        assert plan.retirements == []
        assert any("ESPN id" in r for r in plan.refusals)

    def test_a_scored_row_is_refused_but_a_placeholder_0_0_is_not(self):
        scored = _specimen_rows({15330460: {"home_score": 3, "away_score": 2}})
        assert plan_unplayed_series_games(scored, _boards()).retirements == []
        placeholder = _specimen_rows({15330460: {"home_score": 0, "away_score": 0}})
        assert [r.event_id for r in plan_unplayed_series_games(placeholder, _boards()).retirements] == [15330460]

    @pytest.mark.parametrize("status", ["completed", "closed"])
    def test_a_row_off_the_schedule_shelf_is_refused(self, status):
        rows = _specimen_rows({15330460: {"status": status}})
        plan = plan_unplayed_series_games(rows, _boards())
        assert plan.retirements == []

    def test_a_row_on_the_clinch_day_is_not_this_rules(self):
        # A second unanchored row on Oct 15 ET is a same-day question.
        rows = _specimen_rows() + [_row(1, "Los Angeles Dodgers", "Milwaukee Brewers", "2026-10-16T02:00")]
        assert {r.event_id for r in plan_unplayed_series_games(rows, _boards()).retirements} == {15330460}

    def test_another_pair_is_never_retired(self):
        rows = _specimen_rows() + [_row(2, "Cleveland Guardians", "Tampa Bay Rays", "2026-10-17T05:00")]
        assert {r.event_id for r in plan_unplayed_series_games(rows, _boards()).retirements} == {15330460}

    def test_either_orientation_of_the_pair_is_retired(self):
        rows = _specimen_rows({15330460: {"home_team_name": "Milwaukee Brewers", "away_team_name": "Los Angeles Dodgers"}})
        assert [r.event_id for r in plan_unplayed_series_games(rows, _boards()).retirements] == [15330460]

    def test_no_anchor_row_for_the_clinching_game_refuses(self):
        rows = _specimen_rows({15330459: {"espn_id": None}})
        plan = plan_unplayed_series_games(rows, _boards())
        assert plan.retirements == []
        assert any("0 rows carry this espn_id" in r for r in plan.refusals)


# ── the sweep: real task body against a fake session ────────────────────────


class _Raw:
    def __init__(self, row: SeriesRow, tags_text="[]"):
        self.id = row.event_id
        self.home_team_name = row.home_team_name
        self.away_team_name = row.away_team_name
        self.commence_time = row.commence_time
        self.home_score = row.home_score
        self.away_score = row.away_score
        self.espn_id = row.espn_id
        self.status = row.status
        self.tags_text = tags_text


class _Result:
    def __init__(self, rows=(), rowcount=0, scalar=None):
        self._rows, self.rowcount, self._scalar = list(rows), rowcount, scalar

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._scalar


class _FakeSession:
    def __init__(self, rows, *, read_raises=False, write_silently_noops=False, backup_table=True):
        self.rows = {r.id: r for r in rows}
        self.read_raises, self.noop = read_raises, write_silently_noops
        self.backup_table = backup_table
        self.calls: list[str] = []
        self.banked: dict[int, dict] = {}

    async def execute(self, clause, params=None):
        sql = " ".join(str(clause).split())
        params = params or {}
        if "FROM events e" in sql:
            self.calls.append("population")
            if self.read_raises:
                raise RuntimeError("connection reset")
            assert params["sport_key"] == "baseball_mlb"
            return _Result(list(self.rows.values()))
        if re.search(r"\b(CREATE|ALTER|DROP)\b", sql, re.IGNORECASE):
            raise AssertionError(f"the sweep ran DDL: {sql[:120]}")
        if sql == "SELECT to_regclass('bak_11152_unplayed_series_games') IS NOT NULL":
            self.calls.append("backup_exists")
            return _Result(scalar=self.backup_table)
        if sql.startswith("INSERT INTO bak_11152_"):
            self.calls.append("bank")
            self.banked[params["eid"]] = params
            return _Result(rowcount=1)
        if sql.startswith("UPDATE events"):
            self.calls.append("void")
            row = self.rows[params["eid"]]
            assert params["tag_array"] == json.dumps([retirement_tag("401908033")])
            assert params["status"] == row.status and params["commence_time"] == row.commence_time
            if self.noop:
                return _Result(rowcount=0)
            row.status = "voided"
            return _Result(rowcount=1)
        if sql.startswith("SELECT id, status, espn_id, home_score, away_score, commence_time"):
            self.calls.append("read_back")
            return _Result([r for i, r in self.rows.items() if i in params["ids"]])
        raise AssertionError(f"unexpected SQL: {sql[:120]}")

    async def commit(self):
        return None

    async def rollback(self):
        return None


def _run(monkeypatch, *, rows=None, boards=None, apply=True, **kw):
    rows = rows if rows is not None else [_Raw(r) for r in _specimen_rows()]
    session = _FakeSession(rows, **kw)
    fetched: list = []

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    async def _boards_for(days, _sport_key=sweep.SPORT_KEY):
        fetched.append(days)
        return boards if boards is not None else _boards()

    import app.tasks.base as base

    monkeypatch.setattr(base, "get_task_session", _fake_session)
    monkeypatch.setattr(sweep, "fetch_boards", _boards_for)
    summary = asyncio.run(sweep.run_unplayed_series_game_sweep(apply=apply))
    return summary, session, fetched


class TestTheSweepVerdicts:
    def test_the_specimen_is_banked_then_voided_and_read_back(self, monkeypatch):
        summary, session, _ = _run(monkeypatch)
        assert summary["terminal"] == "complete"
        assert (summary["written"], summary["voided"]) == (1, [15330460])
        assert session.rows[15330460].status == "voided"
        assert session.rows[15330795].status == "scheduled"
        assert session.banked[15330460]["status"] == "scheduled"
        assert (
            session.calls.index("backup_exists")
            < session.calls.index("bank")
            < session.calls.index("void")
            < session.calls.index("read_back")
        )
        assert summary["undo"].endswith("restore_11152_unplayed_series_games.py --apply")

    def test_no_backup_table_writes_nothing_and_is_failed(self, monkeypatch):
        """Notice 47(c): the table is the attended packet's; the sweep never makes it."""
        summary, session, _ = _run(monkeypatch, backup_table=False)
        assert (summary["terminal"], summary["refused"]) == ("failed", "no_backup_table")
        assert (summary["written"], summary["banked"]) == (0, 0)
        assert "bank" not in session.calls and "void" not in session.calls
        assert session.rows[15330460].status == "scheduled"
        assert "apply_15330460.sql" in summary["reason"]

    def test_the_sweep_source_holds_no_ddl(self):
        source = Path(sweep.__file__).read_text()
        assert not re.search(r"\b(CREATE|ALTER|DROP)\s+(TABLE|INDEX)\b", source, re.IGNORECASE)
        assert "to_regclass" in source

    def test_a_write_that_does_not_land_is_partial(self, monkeypatch):
        summary, _, _ = _run(monkeypatch, write_silently_noops=True)
        assert summary["terminal"] == "partial"
        assert summary["not_voided"] == [15330460]

    def test_a_row_that_moved_under_us_is_left_alone_not_failed(self):
        observed = sweep.observed_state([_Raw(r) for r in _specimen_rows()])
        rows = [_Raw(r) for r in _specimen_rows({15330460: {"espn_id": "401908034"}})]
        session = _FakeSession(rows)
        voided, changed = asyncio.run(sweep.read_back(session, [15330460], observed))
        assert (voided, changed) == ([], [15330460])

    def test_no_candidate_rows_reads_no_board(self, monkeypatch):
        rows = [_Raw(r) for r in _specimen_rows() if r.event_id != 15330460]
        rows = [r for r in rows if r.espn_id]
        summary, session, fetched = _run(monkeypatch, rows=rows)
        assert summary["terminal"] == "no_work"
        assert fetched == [] and "void" not in session.calls

    def test_a_quiet_window_reads_green(self, monkeypatch):
        rows = [_Raw(r) for r in _specimen_rows({15330460: {"status": "completed", "home_score": 1, "away_score": 0}})]
        rows.append(_Raw(_row(3, "Seattle Mariners", "Houston Astros", "2026-10-17T02:00")))
        summary, session, _ = _run(monkeypatch, rows=rows)
        assert summary["terminal"] == "complete"
        assert "void" not in session.calls

    def test_a_dark_day_makes_the_window_partial(self, monkeypatch):
        summary, _, _ = _run(monkeypatch, boards=_boards() | {date(2026, 10, 12): None})
        assert summary["terminal"] == "partial"
        assert summary["written"] == 1

    def test_every_board_dark_is_failed_and_unmeasured(self, monkeypatch):
        summary, session, _ = _run(monkeypatch, boards={OCT15: None, OCT16: None})
        assert (summary["terminal"], summary["measured"]) == ("failed", False)
        assert "void" not in session.calls

    def test_a_read_that_raises_is_failed_and_unmeasured(self, monkeypatch):
        summary, _, _ = _run(monkeypatch, read_raises=True)
        assert (summary["terminal"], summary["measured"]) == ("failed", False)

    def test_a_dry_run_withholds_and_says_so(self, monkeypatch):
        summary, session, _ = _run(monkeypatch, apply=False)
        assert summary["terminal"] == "no_work"
        assert "void" not in session.calls

    def test_a_plan_above_the_ceiling_is_refused_whole(self, monkeypatch):
        extra = [
            _Raw(_row(100 + i, "Los Angeles Dodgers", "Milwaukee Brewers", f"2026-10-16T{12 + i}:00"))
            for i in range(sweep.MAX_EXPECTED_RETIREMENTS)
        ]
        rows = [_Raw(r) for r in _specimen_rows()] + extra
        summary, session, _ = _run(monkeypatch, rows=rows)
        assert summary["terminal"] == "failed"
        assert "ceiling" in summary["reason"]
        assert "void" not in session.calls


class TestWiring:
    def test_the_beat_entry_applies_on_the_background_queue(self):
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["unplayed-series-game-sweep"]
        assert entry["task"] == "app.tasks.unplayed_series_game_sweep"
        assert entry["kwargs"] == {"apply": True}
        assert entry["options"]["queue"] == "background"
        assert entry["task"] in celery_app.tasks

    def test_it_is_enrolled_in_enforced_tasks(self):
        from app.utils.task_verdict import ENFORCED_TASKS, verdict_for

        assert "unplayed_series_game_sweep" in ENFORCED_TASKS
        assert not verdict_for("unplayed_series_game_sweep", {"terminal": "failed", "measured": False}).is_green

    def test_the_undo_reads_the_table_the_sweep_banks_into(self):
        import importlib.util

        path = Path(__file__).resolve().parents[1] / "scripts" / "restore_11152_unplayed_series_games.py"
        spec = importlib.util.spec_from_file_location("restore_11152", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.BAK_TABLE == sweep.BAK_TABLE == "bak_11152_unplayed_series_games"
        assert "status = 'voided'" in module._RESTORE_SQL

    def test_the_retirement_tag_survives_the_taxonomy_rewrite(self):
        from app.utils.event_taxonomy import carry_provenance_tags

        tag = retirement_tag("401908033")
        assert tag in carry_provenance_tags([tag, "stakes:playoff_race"], ["status:upcoming"])

    def test_voided_is_a_retired_status_the_detail_route_refuses(self):
        from app.utils.event_completion import is_retired_event_status

        assert is_retired_event_status("voided") is True
