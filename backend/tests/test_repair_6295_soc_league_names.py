"""#6295 — guards on the repair that takes Bayer Leverkusen off La Liga.

The UPDATE is two columns. Everything that can go wrong with this repair is
around the edges, and each of those is a test here:

* it renames a row the defect did NOT write — the six ESPN-anchored rows whose
  names are already right are the control population, and they share their
  ticker with the three phantoms (`TestOnlyTheDefectIsRepaired`);
* it invents a name instead of replaying the fix (`TestTheNamesComeFromTheFix`);
* it writes from the wrong app, or before an undo exists
  (`TestTheWriteRefusals`, `TestTheBackupComesFirst`);
* it reverses a fixture whose row is stored opposite to its ticker
  (`test_a_swapped_row_keeps_its_orientation`);
* the undo cannot start, which retroactively removes the D51(b) permission the
  repair was applied under (`TestTheUndoTakesTheSameGate`).

The three specimens, their tickers and their market titles are production rows
read at 2026-09-17; the six controls are the rest of what the shipped resolver
answers differently, measured the same way.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REPAIR_PATH = _SCRIPTS / "repair_6295_soc_league_names.py"
RESTORE_PATH = _SCRIPTS / "restore_6295_soc_league_names.py"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def repair():
    return _load(REPAIR_PATH)


@pytest.fixture(scope="module")
def restore():
    return _load(RESTORE_PATH)


# ── the production rows, read 2026-09-17 ────────────────────────────────────

#: (event id, stored home, stored away, ticker, market title)
PHANTOMS = [
    (
        15312871,
        "Bayer Leverkusen",
        "Athletic Club",
        "KXLALIGAGAME-26SEP16LEVATH",
        "Levante vs Bilbao",
    ),
    (
        15312872,
        "Villarreal",
        "Bayer Leverkusen",
        "KXLALIGAGAME-26SEP20VILLEV",
        "Villarreal vs Levante",
    ),
    (
        15312896,
        "Paris Saint-Germain",
        "Genoa",
        "KXSERIEAGAME-26SEP20PARGEN",
        "Parma Calcio vs Genoa",
    ),
]

#: What each phantom must become — the matcher's own answer for that market.
EXPECTED_NAMES = {
    15312871: ("Levante", "Bilbao"),
    15312872: ("Villarreal", "Levante"),
    15312896: ("Parma Calcio", "Genoa"),
}

#: The control population: rows on the SAME colliding tickers whose stored names
#: came from ESPN and are already right. A repair that renames these is worse
#: than one that does nothing.
ALREADY_RIGHT = [
    (
        14970078,
        "Espanyol",
        "Levante",
        "KXLALIGAGAME-26AUG16ESPLEV",
        "Espanyol vs Levante",
    ),
    (
        15291307,
        "Parma",
        "Monza",
        "KXSERIEAGAME-26SEP06PARMON",
        "Parma Calcio vs Monza",
    ),
    (
        15298072,
        "Levante",
        "Barcelona",
        "KXLALIGAGAME-26SEP13LEVBAR",
        "Levante vs Barcelona",
    ),
]


class TestTheNamesComeFromTheFix:
    def test_each_phantom_becomes_the_matchers_own_answer(self, repair):
        """Not a hand-typed table: the plan is what the matcher writes today."""
        for event_id, home, away, ticker, title in PHANTOMS:
            row, reason = repair.plan_row(event_id, home, away, ticker, title)
            assert row is not None, f"{event_id} was skipped as {reason}"
            assert (row["new_home"], row["new_away"]) == EXPECTED_NAMES[event_id]

    def test_the_pre_fix_replay_reproduces_what_the_rows_actually_store(self, repair):
        """The evidence, asked directly.

        If this stops holding, the rows were not minted by #6295 and the whole
        repair loses its basis — which is why it is a test and not a comment.
        """
        assert repair.replay_pre_fix_names("KXLALIGAGAME-26SEP16LEVATH") == (
            "Bayer Leverkusen",
            "Athletic Club",
        )
        assert repair.replay_pre_fix_names("KXSERIEAGAME-26SEP20PARGEN") == (
            "Paris Saint-Germain",
            "Genoa",
        )

    def test_the_gate_is_deployed_in_the_tree_this_runs_in(self, repair):
        """🔴 The repair is inert without the fix, and silently so.

        `plan_row` refuses any ticker the shipped resolver still answers the
        pre-fix way (`FIX_AGREES`). Run this script on a tree without #6295 and
        every phantom is skipped and the run reports a clean zero — the failure
        most likely to be believed. So the coupling is asserted.
        """
        assert repair.shipped_names("KXLALIGAGAME-26SEP16LEVATH") != (
            "Bayer Leverkusen",
            "Athletic Club",
        )

    def test_the_title_is_the_only_possible_source_of_a_planned_rows_new_name(
        self, repair
    ):
        """Why passing the ticker to the fallback cannot change these answers.

        A mutant that calls `extract_matchup_with_ticker_fallback(...,
        external_id=None)` survives this file, and this test is why rather than a
        gap: a row only reaches the plan because the shipped resolver now REFUSES
        its ticker, so the ticker arm of that fallback has nothing to contribute
        and the title decides. The argument is kept because it is the matcher's
        real call signature, and because a future planned row whose ticker does
        resolve would need it.
        """
        for _, _, _, ticker, _ in PHANTOMS:
            assert repair.shipped_names(ticker) is None

    def test_a_swapped_row_keeps_its_orientation(self, repair):
        """Home stays home when a row is stored opposite to its ticker."""
        row, _ = repair.plan_row(
            999,
            "Genoa",
            "Paris Saint-Germain",
            "KXSERIEAGAME-26SEP20PARGEN",
            "Parma Calcio vs Genoa",
        )
        assert row["swapped"] is True
        assert (row["new_home"], row["new_away"]) == ("Genoa", "Parma Calcio")

    def test_orientation_reports_no_fit_rather_than_guessing(self, repair):
        assert repair.orientation("Levante", "Bilbao", ("Parma", "Genoa")) is None


class TestOnlyTheDefectIsRepaired:
    @pytest.mark.parametrize("row", ALREADY_RIGHT, ids=lambda r: str(r[0]))
    def test_a_row_espn_named_correctly_is_never_renamed(self, repair, row):
        """The six controls share the colliding tickers and are already right.

        `15298072` really is "Levante v Barcelona" and `15291307` really is
        "Parma v Monza": ESPN named them, the ticker did not. The pre-fix replay
        does not reproduce what they store, so they are refused by evidence
        rather than by a date filter or an allowlist.
        """
        planned, reason = repair.plan_row(*row)
        assert planned is None
        assert reason in {"NOT_MINTED_BY_THIS", "ALREADY_CORRECT"}

    def test_a_ticker_the_fix_does_not_move_is_refused(self, repair):
        """An EPL fixture: no collision, no change, nothing to repair."""
        planned, reason = repair.plan_row(
            1, "Arsenal", "Chelsea", "KXEPLGAME-26SEP20ARSCHE", "Arsenal vs Chelsea"
        )
        assert planned is None
        assert reason == "FIX_AGREES"

    def test_a_row_with_no_ticker_is_refused_rather_than_guessed_at(self, repair):
        planned, reason = repair.plan_row(
            1, "Levante", "Bilbao", "", "Levante vs Bilbao"
        )
        assert planned is None
        assert reason == "NO_TICKER"

    def test_the_repair_writes_only_the_two_name_columns(self):
        """No crest, no sport, no time, no market. The UPDATE says so."""
        source = REPAIR_PATH.read_text()
        updates = [line for line in source.splitlines() if "UPDATE events SET" in line]
        assert updates, "the UPDATE moved — re-read this guard"
        for line in updates:
            assert "home_team_name = :nh, away_team_name = :na" in line
            for column in ("sport_id", "commence_time", "home_team_id", "espn_id"):
                assert column not in line


# ── the write refusals ──────────────────────────────────────────────────────


class _Args:
    def __init__(self, **kw):
        self.apply = kw.get("apply", False)
        self.backup = kw.get("backup", False)


class TestTheWriteRefusals:
    def test_a_dry_run_needs_no_app_at_all(self, repair, monkeypatch):
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        assert repair.wrong_app_refusal(_Args()) is None

    @pytest.mark.parametrize("flag", ["apply", "backup"])
    def test_an_unset_app_refuses_to_write(self, repair, monkeypatch, flag):
        """Unset means a laptop pointed at production. That is the case to stop."""
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        refusal = repair.wrong_app_refusal(_Args(**{flag: True}))
        assert refusal and "HEROKU_APP_NAME is unset" in refusal

    @pytest.mark.parametrize("app", ["bainluck", "bainluck-staging", ""])
    def test_the_wrong_app_refuses_and_names_where_it_is(
        self, repair, monkeypatch, app
    ):
        monkeypatch.setenv("HEROKU_APP_NAME", app)
        refusal = repair.wrong_app_refusal(_Args(apply=True))
        assert refusal and repair.PRODUCER_APP in refusal

    def test_the_producer_app_may_write(self, repair, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", repair.PRODUCER_APP)
        assert repair.wrong_app_refusal(_Args(apply=True)) is None
        assert repair.wrong_app_refusal(_Args(backup=True)) is None

    def test_the_gate_survives_a_caller_with_no_backup_flag(self, repair, monkeypatch):
        """The undo's parser has no `--backup`; reading it must not raise."""
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)

        class OnlyApply:
            apply = True

        assert "REFUSING" in repair.wrong_app_refusal(OnlyApply())

    def test_the_producer_app_is_the_one_that_mints_these_rows(self, repair):
        """🔴 Catches a runbook aimed at the web app after the heavy split.

        `match_prediction_markets` mints these events. While it is in
        `HEAVY_TASKS` the producer is `bainluck-heavy`; if it ever stops being
        heavy this fires rather than leaving the header quietly lying
        (standing notice 48).
        """
        from app.tasks import HEAVY_TASKS

        assert "app.tasks.match_prediction_markets" in HEAVY_TASKS
        assert repair.PRODUCER_APP == "bainluck-heavy"

    def test_the_runbook_waits_for_the_heavy_release(self):
        header = REPAIR_PATH.read_text()
        assert "notice 48" in header
        assert "bainluck-heavy" in header


# ── the plan, the disposition and the ordering, against a fake session ──────


class _Result:
    def __init__(self, rows):
        self._rows = rows
        self.rowcount = len(rows)

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one(self):
        return self._rows[0][0] if self._rows else 0


class _FakeSession:
    """Answers by looking at the SQL, so it is order-independent."""

    def __init__(self, events, backup_covered=None, updated=1):
        self.events = events
        self.backup_covered = backup_covered
        self.updated = updated
        self.statements: list[tuple[str, dict]] = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.statements.append((sql, params or {}))
        if "FROM events e JOIN sports s" in sql:
            return _Result(self.events)
        if "count(*)" in sql:
            covered = (
                self.backup_covered
                if self.backup_covered is not None
                else len(self.events)
            )
            return _Result([(covered,)])
        if sql.startswith("UPDATE events"):
            return _Result([("x",)] * self.updated)
        return _Result([])

    async def commit(self):
        pass


class _SessionFactory:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _rows(specimens=PHANTOMS, padding=600):
    """The three phantoms plus enough clean rows to clear the population floor.

    The padding is not decoration: `MIN_EXPECTED_POPULATION` refuses a run whose
    candidate population collapsed, and a fixture of three rows would trip it.
    """
    pad = [
        (
            9_000_000 + i,
            "Arsenal",
            "Chelsea",
            "KXEPLGAME-26SEP20ARSCHE",
            "Arsenal vs Chelsea",
        )
        for i in range(padding)
    ]
    return [(e, h, a, t, n) for e, h, a, t, n in specimens] + pad


def _args(**kw):
    return argparse.Namespace(
        **{
            **dict(backup=False, apply=False, limit=0, expect_plan=None),
            **kw,
        }
    )


def _run(monkeypatch, repair, session, **kw):
    monkeypatch.setenv("HEROKU_APP_NAME", repair.PRODUCER_APP)
    monkeypatch.setattr(repair, "_session_factory", lambda: _SessionFactory(session))
    return asyncio.run(repair.run(_args(**kw)))


class TestThePlan:
    def test_the_plan_is_exactly_the_three_phantoms(self, repair):
        session = _FakeSession(_rows())
        plan, skipped = asyncio.run(repair.build_plan(session))
        assert sorted(row["id"] for row in plan) == sorted(repair.EXPECTED_IDS)
        assert len(skipped) == 600

    def test_the_ticker_and_the_title_come_from_ONE_market(self, repair):
        """The LATERAL join is load-bearing: two correlated subqueries could take
        the ticker from one market hanging off the event and the title from
        another, and the repair would rename a row from a market it never read.
        """
        session = _FakeSession(_rows())
        asyncio.run(repair.build_plan(session))
        sql = session.statements[0][0]
        assert "JOIN LATERAL" in sql
        assert sql.count("futures_markets") == 1

    def test_the_population_floor_refuses_a_collapsed_predicate(
        self, monkeypatch, repair
    ):
        """A repair that finds nothing and reports success is the worst outcome."""
        session = _FakeSession(_rows(padding=0))
        assert _run(monkeypatch, repair, session) == 2

    def test_a_dry_run_writes_nothing_at_all(self, monkeypatch, repair):
        session = _FakeSession(_rows())
        assert _run(monkeypatch, repair, session) == 0
        assert not [s for s, _ in session.statements if s.startswith("UPDATE")]
        assert not [s for s, _ in session.statements if "CREATE TABLE" in s]


class TestTheDisposition:
    def test_the_pre_registered_ids_are_the_three_production_rows(self, repair):
        assert sorted(repair.EXPECTED_IDS) == [15312871, 15312872, 15312896]

    def test_a_plan_matching_the_pre_registration_may_proceed(self, repair):
        plan = [{"id": i} for i in repair.EXPECTED_IDS]
        assert repair.disposition_drift(plan) is None

    def test_a_fourth_phantom_stops_the_apply_and_says_which_row(self, repair):
        plan = [{"id": i} for i in (*repair.EXPECTED_IDS, 15399999)]
        drift = repair.disposition_drift(plan)
        assert drift and "15399999" in drift

    def test_expect_plan_restates_the_count_deliberately(self, repair):
        plan = [{"id": i} for i in (*repair.EXPECTED_IDS, 15399999)]
        assert repair.disposition_drift(plan, expect_plan=4) is None
        assert repair.disposition_drift(plan, expect_plan=3) is not None

    def test_the_apply_refuses_on_drift(self, monkeypatch, repair):
        extra = (
            15399999,
            "Villarreal",
            "Bayer Leverkusen",
            "KXLALIGAGAME-26SEP20VILLEV",
            "Villarreal vs Levante",
        )
        session = _FakeSession(_rows([*PHANTOMS, extra]))
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 6
        assert not [s for s, _ in session.statements if s.startswith("UPDATE")]


class TestTheBackupComesFirst:
    def test_apply_without_backup_refuses(self, monkeypatch, repair):
        session = _FakeSession(_rows())
        assert _run(monkeypatch, repair, session, apply=True) == 4
        assert not [s for s, _ in session.statements if s.startswith("UPDATE")]

    def test_limit_and_apply_together_refuse(self, monkeypatch, repair):
        session = _FakeSession(_rows())
        assert _run(monkeypatch, repair, session, backup=True, apply=True, limit=5) == 7

    def test_every_rename_is_backed_up_before_the_first_write(
        self, monkeypatch, repair
    ):
        """🔴 The ordering IS the D51(b) permission.

        `repair_2947` wrote a backup below its own refusals and renamed rows it
        disagreed with (CERT-903). Here the claim is narrower and stronger: no
        UPDATE may appear before the three INSERTs into the backup table.
        """
        session = _FakeSession(_rows())
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 0

        kinds = [
            "backup" if repair.BACKUP_TABLE in sql else "update"
            for sql, _ in session.statements
            if repair.BACKUP_TABLE in sql or sql.startswith("UPDATE events")
        ]
        assert kinds.count("update") == 3
        assert kinds.index("update") > kinds.count("backup") - 1
        assert "backup" not in kinds[kinds.index("update") :]

    def test_a_backup_that_does_not_cover_the_plan_stops_the_apply(
        self, monkeypatch, repair
    ):
        session = _FakeSession(_rows(), backup_covered=2)
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 3
        assert not [s for s, _ in session.statements if s.startswith("UPDATE")]

    def test_the_update_is_guarded_on_the_old_names(self, monkeypatch, repair):
        """A row somebody else has renamed since is left alone, never stomped."""
        session = _FakeSession(_rows())
        _run(monkeypatch, repair, session, backup=True, apply=True)
        updates = [
            (sql, params)
            for sql, params in session.statements
            if sql.startswith("UPDATE events")
        ]
        for sql, params in updates:
            assert "AND home_team_name = :oh AND away_team_name = :oa" in sql
            assert params["oh"] and params["oa"]

    def test_a_partial_write_is_reported_rather_than_called_success(
        self, monkeypatch, repair
    ):
        session = _FakeSession(_rows(), updated=0)
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 5


# ── the undo ────────────────────────────────────────────────────────────────


class TestTheUndoTakesTheSameGate:
    def test_the_restore_imports_the_gate_rather_than_copying_it(self, restore):
        """One refusal, two programs — a copied gate is one that can drift.

        Asserted on where the function was DEFINED rather than with `is`: the
        fixtures load each file through its own import spec, so two module
        objects are different by construction and an identity check would be
        measuring the harness.
        """
        assert restore.wrong_app_refusal.__code__.co_filename == str(REPAIR_PATH)
        assert "def wrong_app_refusal" not in RESTORE_PATH.read_text()

    def test_the_restore_actually_calls_the_gate(self, restore, monkeypatch):
        """🔴 Catches an undo that imports the gate and forgets to invoke it."""
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        assert (
            asyncio.run(restore.run(argparse.Namespace(apply=True, drop_backups=False)))
            == 2
        )

    def test_the_repair_actually_calls_the_gate(self, repair, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        assert asyncio.run(repair.run(_args(apply=True, backup=True))) == 2

    def test_the_restore_reads_the_table_the_repair_writes(self, repair, restore):
        assert restore.BACKUP_TABLE == repair.BACKUP_TABLE == "backup_6295_event_names"

    def test_the_restore_replays_the_recorded_name_not_a_constant(self):
        """The undo must not 'set them back to Bayer Leverkusen'.

        It replays `backup.home_team_name` per row, so a row that was something
        else goes back to something else. A restore that hardcoded a name would
        be a second repair wearing an undo's name.
        """
        source = RESTORE_PATH.read_text()
        assert "SET home_team_name = :oh, away_team_name = :oa" in source
        assert "Bayer Leverkusen" not in source

    def test_the_restore_leaves_a_row_renamed_since_alone(self, restore, monkeypatch):
        """DIVERGED, not stomped: an undo that overwrites a later decision is
        not an undo."""

        class _RestoreSession:
            def __init__(self):
                self.statements = []

            async def execute(self, stmt, params=None):
                sql = " ".join(str(stmt).split())
                self.statements.append((sql, params or {}))
                if "to_regclass" in sql:
                    return _Result([("public.backup_6295_event_names",)])
                if sql.startswith("SELECT b.event_id"):
                    return _Result(
                        [
                            # repaired, and still as the repair left it -> restore
                            (
                                15312872,
                                "Villarreal",
                                "Bayer Leverkusen",
                                "Villarreal",
                                "Levante",
                                "Villarreal",
                                "Levante",
                            ),
                            # renamed again by somebody else -> DIVERGED
                            (
                                15312896,
                                "Paris Saint-Germain",
                                "Genoa",
                                "Parma Calcio",
                                "Genoa",
                                "Parma",
                                "Genoa CFC",
                            ),
                        ]
                    )
                return _Result([("x",)])

            async def commit(self):
                pass

        session = _RestoreSession()
        monkeypatch.setenv("HEROKU_APP_NAME", restore.PRODUCER_APP)
        monkeypatch.setattr(
            restore, "_session_factory", lambda: _SessionFactory(session)
        )
        code = asyncio.run(
            restore.run(argparse.Namespace(apply=True, drop_backups=False))
        )

        assert code == 0
        updates = [
            (s, p) for s, p in session.statements if s.startswith("UPDATE events")
        ]
        assert [p["eid"] for _, p in updates] == [15312872]
        for sql, _ in updates:
            # The SELECT decided which rows to restore; this guard is what makes
            # the WRITE safe against a rename landing between the two. Without it
            # the undo stomps whatever arrived in that window and no test above
            # can see the difference, because the todo list is computed in Python.
            assert "AND home_team_name = :nh AND away_team_name = :na" in sql

    @pytest.mark.parametrize("module", ["repair", "restore"])
    def test_the_real_session_factory_resolves(self, repair, restore, module):
        """🔴 CERT-903: `repair_2947` imported `app.database`, a module that has
        never existed. Every unit test passed against a fake session while the
        entrypoint died on import, and an undo that cannot start retroactively
        removes the permission its repair was run under.
        """
        target = repair if module == "repair" else restore
        assert callable(target._session_factory())
