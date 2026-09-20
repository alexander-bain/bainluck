"""#7354 — the settled-orientation repair writes ONLY a proven slot copy.

The defect: a neutral-site game that settled before #7338 shipped is frozen
showing the losing team as the winner (`/events/15308929` — "Mountaineers 27 ·
Cavaliers 38", WON badge on the Cavaliers, when West Virginia won 38-27).

These tests hold the two lines that make the repair safe to run unattended:

1. **Only a positive `swapped` verdict is ever written**, and the verdict comes
   from #7338's own `espn_orientation_verdict` rather than a second
   implementation of the same judgement. `aligned` and `unresolved` write
   nothing — `unresolved` means "we could not read this row's names", which is
   not evidence of a swap.
2. **A swapped verdict is not enough.** The stored score must ALSO be ESPN's
   pair in ESPN's own slots, which is a complete description of the write that
   produced the defect. Without that second gate the rail would reach into
   #7147's `score_drifted` / `espn_id_drifted` population, where the remedy is
   different and, for 8 of 21 drifted rows in that census, the stored score is
   already correct — so "repairing" them writes another game's final onto the
   row.

The real specimen is pinned as a fixture in both directions, so a future change
that makes the planner stop writing it, or start writing its `aligned` control,
fails here.
"""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.espn_helpers import (  # noqa: E402
    ESPN_ORIENTATION_ALIGNED,
    ESPN_ORIENTATION_SWAPPED,
    ESPN_ORIENTATION_UNRESOLVED,
)
from scripts.repair_7354_settled_orientation_swap import (  # noqa: E402
    SLOT_COPY_PROOF,
    OrientationPlan,
    plan_orientation_repair,
)


def _espn_team(display_name, abbreviation=None, location=None, nickname=None):
    return types.SimpleNamespace(
        name=display_name,
        display_name=display_name,
        abbreviation=abbreviation,
        location=location,
        nickname=nickname,
        short_display_name=display_name,
    )


def _espn_event(home_name, away_name, home_score, away_score, status="post"):
    return types.SimpleNamespace(
        home_team=_espn_team(home_name),
        away_team=_espn_team(away_name),
        home_score=home_score,
        away_score=away_score,
        status=status,
    )


def _row(home_name, away_name, home_score, away_score,
         espn_win_prob_home=None, event_id=15308929):
    return types.SimpleNamespace(
        id=event_id,
        sport_key="americanfootball_ncaaf",
        home_team_name=home_name,
        away_team_name=away_name,
        home_team_normalized=None,
        away_team_normalized=None,
        home_team_alt_names=None,
        away_team_alt_names=None,
        home_score=home_score,
        away_score=away_score,
        espn_win_prob_home=espn_win_prob_home,
    )


# The production specimen, 2026-09-19. ESPN: Virginia (home) 27, West Virginia
# (away) 38, neutral site, status post. Our row: West Virginia home holding 27.
WVU = "West Virginia Mountaineers"
UVA = "Virginia Cavaliers"


def _specimen_row(**kw):
    return _row(WVU, UVA, 27, 38, **kw)


def _specimen_espn():
    return _espn_event(UVA, WVU, 27, 38)


class TestTheSpecimenIsRepaired:
    def test_the_real_swapped_row_is_planned_for_repair(self):
        plan = plan_orientation_repair(_specimen_row(), _specimen_espn())

        assert plan.verdict == ESPN_ORIENTATION_SWAPPED
        assert plan.action == "repair_orientation"
        assert plan.writes is True
        # The reason names the store that earned the write and only that store:
        # this specimen is passed no series and no leg, so neither may appear.
        assert plan.reason.startswith(SLOT_COPY_PROOF)
        assert "events score" in plan.reason
        for unproven in ("espn_snapshots", "score_snapshots", "espn leg"):
            assert unproven not in plan.reason, (
                f"{unproven!r} was never proven yet the reason claims it: "
                f"{plan.reason!r}"
            )

    def test_the_repaired_score_gives_the_winner_the_higher_number(self):
        """West Virginia is our home side and West Virginia scored 38."""
        plan = plan_orientation_repair(_specimen_row(), _specimen_espn())

        assert (plan.new_home_score, plan.new_away_score) == (38, 27)
        # The whole point: our home side now holds the winning score, so
        # `resolve_settled_hero` puts the WON badge on the team that won.
        assert plan.new_home_score > plan.new_away_score

    def test_the_espn_probability_leg_is_complemented_not_zeroed(self):
        plan = plan_orientation_repair(
            _specimen_row(espn_win_prob_home=0.0), _specimen_espn())

        assert plan.complement_espn_leg is True
        assert plan.new_espn_win_prob_home == 1.0

    def test_an_unreadable_probability_is_left_alone_rather_than_guessed(self):
        plan = plan_orientation_repair(
            _specimen_row(espn_win_prob_home="not-a-number"), _specimen_espn())

        assert plan.writes is True
        assert plan.new_espn_win_prob_home is None
        assert any("unreadable" in n for n in plan.series_notes)


class TestOnlyAPositiveSwapIsWritten:
    def test_an_aligned_row_is_never_touched(self):
        """The control. Same shape, same scores — ESPN's home is OUR home."""
        row = _row(UVA, WVU, 27, 38)
        plan = plan_orientation_repair(row, _specimen_espn())

        assert plan.verdict == ESPN_ORIENTATION_ALIGNED
        assert plan.action == "skip_aligned"
        assert plan.writes is False
        assert plan.new_home_score is None

    def test_an_unresolved_row_is_never_touched(self):
        """A row whose names we cannot read is not evidence of a swap."""
        row = _row(None, None, 27, 38)
        plan = plan_orientation_repair(row, _specimen_espn())

        assert plan.verdict == ESPN_ORIENTATION_UNRESOLVED
        assert plan.action == "skip_unresolved"
        assert plan.writes is False

    def test_the_judge_is_7338s_helper_and_not_a_local_reimplementation(self, monkeypatch):
        """Forcing the shared verdict to ALIGNED must stop the write.

        If a later change inlines its own orientation logic, this planner would
        keep repairing the specimen and this test fails — which is the only way
        to keep "use `espn_orientation_verdict`, not a second implementation"
        true over time rather than at review time.
        """
        import scripts.repair_7354_settled_orientation_swap as mod

        monkeypatch.setattr(
            mod, "espn_orientation_verdict",
            lambda event, ee: ESPN_ORIENTATION_ALIGNED)
        plan = plan_orientation_repair(_specimen_row(), _specimen_espn())

        assert plan.action == "skip_aligned"
        assert plan.writes is False


class TestTheSlotCopyProofSeparatesTwoDefectsWithOppositeRemedies:
    """A swapped verdict alone must not authorise a write — #7147's boundary.

    Each store carries its own positive proof, so a score that is neither
    ESPN's slot pair nor the true pair is score/espn_id drift and is left for
    #7147's rail even though this row's orientation IS swapped.
    """

    @pytest.mark.parametrize("stored", [(21, 38), (27, 40), (0, 0)])
    def test_a_score_that_is_neither_pair_is_left_for_the_other_rail(self, stored):
        row = _row(WVU, UVA, stored[0], stored[1])
        plan = plan_orientation_repair(row, _specimen_espn())

        assert plan.verdict == ESPN_ORIENTATION_SWAPPED
        assert plan.new_home_score is None, "drifted score must not be rewritten"
        assert any("7147" in n for n in plan.series_notes)

    def test_an_already_repaired_row_is_not_repaired_twice(self):
        """Idempotence: with every store correct there is nothing left to do."""
        plan = plan_orientation_repair(
            _row(WVU, UVA, 38, 27, espn_win_prob_home=1.0), _specimen_espn(),
            last_espn_snapshot=(38, 27), last_score_snapshot=(38, 27))

        assert plan.action == "skip_nothing_to_repair"
        assert plan.writes is False


class TestTheHalfHealedRowIsStillRepaired:
    """The case that drove the per-store design, measured on production.

    #7338 released on 2026-09-20 and its live sweep reached ev15308929 inside
    the 6h post-commence window. It corrected `events.home_score` to 38-27 and
    appended one correctly-oriented `score_snapshots` row, while
    `espn_snapshots` stayed frozen at 102 swapped rows and the ESPN probability
    leg stayed at 0.0 for the side that won — which is what still renders
    "Bigger Picture: Cavaliers" over a game West Virginia won.

    A rail with one global gate keyed on `events.home_score` reads that row as
    "not slot copied" and walks away from the half still on the page.
    """

    def _half_healed(self):
        return plan_orientation_repair(
            _row(WVU, UVA, 38, 27, espn_win_prob_home=0.0), _specimen_espn(),
            last_espn_snapshot=(27, 38),   # frozen, still swapped
            last_score_snapshot=(38, 27),  # healed by #7338's sweep
        )

    def test_the_half_healed_row_is_still_repairable(self):
        plan = self._half_healed()

        assert plan.verdict == ESPN_ORIENTATION_SWAPPED
        assert plan.action == "repair_orientation"
        assert plan.writes is True

    def test_the_already_correct_score_is_not_rewritten(self):
        plan = self._half_healed()

        assert plan.new_home_score is None
        assert any("already correct" in n for n in plan.series_notes)

    def test_the_already_correct_series_is_not_swapped_back_into_the_defect(self):
        plan = self._half_healed()

        assert plan.swap_score_snapshots is False
        assert plan.swap_espn_snapshots is True

    def test_the_frozen_probability_leg_is_complemented(self):
        plan = self._half_healed()

        assert plan.complement_espn_leg is True
        assert plan.new_espn_win_prob_home == 1.0

    def test_the_reason_names_the_proven_stores_and_claims_no_others(self):
        """The operator's line has to survive being read against the row.

        The reason used to be the flat sentence "stored score is ESPN's pair in
        ESPN's slots" — the last trace of the one-global-gate design. On this
        row the stored score is 38-27, the TRUE pair, so the dry-run printed a
        claim the same line disproves, next to a destructive apply.
        """
        plan = self._half_healed()

        assert "espn_snapshots" in plan.reason
        assert "espn leg" in plan.reason
        # The two stores #7338 already healed are not written, so the reason
        # must not say they carried the proof.
        assert "events score" not in plan.reason, plan.reason
        assert "score_snapshots" not in plan.reason, plan.reason


class TestTheProbabilityLegCarriesItsOwnProof:
    def test_a_leg_already_reading_for_the_winner_is_left_alone(self):
        plan = plan_orientation_repair(
            _row(WVU, UVA, 38, 27, espn_win_prob_home=1.0), _specimen_espn(),
            last_espn_snapshot=(27, 38))

        assert plan.complement_espn_leg is False
        assert any("already reads for the side that won" in n
                   for n in plan.series_notes)

    @pytest.mark.parametrize("value", [0.5, 0.4, 0.62])
    def test_an_undecided_leg_is_not_evidence_of_an_inversion(self, value):
        plan = plan_orientation_repair(
            _row(WVU, UVA, 38, 27, espn_win_prob_home=value), _specimen_espn(),
            last_espn_snapshot=(27, 38))

        assert plan.complement_espn_leg is False
        assert plan.new_espn_win_prob_home is None
        assert any("undecided" in n for n in plan.series_notes)


class TestEspnMustBeAbleToAdjudicate:
    def test_a_game_espn_does_not_call_final_is_refused(self):
        ee = _espn_event(UVA, WVU, 27, 38, status="in")
        plan = plan_orientation_repair(_specimen_row(), ee)

        assert plan.action == "skip_espn_not_final"
        assert plan.writes is False

    def test_a_missing_espn_score_is_not_a_score_of_zero(self):
        ee = _espn_event(UVA, WVU, None, 38)
        plan = plan_orientation_repair(_specimen_row(), ee)

        assert plan.action == "skip_espn_no_score"
        assert plan.writes is False

    def test_an_absent_espn_answer_is_not_a_fact_about_the_row(self):
        plan = plan_orientation_repair(_specimen_row(), None)

        assert plan.action == "skip_espn_not_found"
        assert plan.writes is False


class TestEachSeriesIsGatedOnItsOwnLastPoint:
    """A series is swapped only if IT is demonstrably in the swapped orientation.

    The event row being wrong does not prove a given series is wrong, and
    swapping a correct series would create the defect this repair removes.
    """

    def test_both_series_in_the_swapped_orientation_are_swapped(self):
        plan = plan_orientation_repair(
            _specimen_row(), _specimen_espn(),
            last_espn_snapshot=(27, 38), last_score_snapshot=(27, 38))

        assert plan.swap_espn_snapshots is True
        assert plan.swap_score_snapshots is True

    def test_a_series_that_is_already_correct_is_left_alone(self):
        plan = plan_orientation_repair(
            _specimen_row(), _specimen_espn(),
            last_espn_snapshot=(38, 27), last_score_snapshot=(27, 38))

        assert plan.swap_espn_snapshots is False
        assert plan.swap_score_snapshots is True
        assert any("already correct" in n for n in plan.series_notes)

    def test_a_series_matching_neither_orientation_is_left_alone(self):
        plan = plan_orientation_repair(
            _specimen_row(), _specimen_espn(),
            last_espn_snapshot=(14, 7), last_score_snapshot=None)

        assert plan.swap_espn_snapshots is False
        assert any("neither orientation" in n for n in plan.series_notes)

    def test_an_absent_series_is_reported_and_not_swapped(self):
        plan = plan_orientation_repair(
            _specimen_row(), _specimen_espn(),
            last_espn_snapshot=None, last_score_snapshot=None)

        assert plan.swap_espn_snapshots is False
        assert plan.swap_score_snapshots is False
        assert sum("no rows" in n for n in plan.series_notes) == 2
        # The row half still repairs — an event with no series is exactly the
        # case where the event row IS what the hero falls through to.
        assert plan.writes is True


class TestOneBadRowDoesNotEndThePass:
    """Gotcha #42, and on a resumable rail it is worse than usual.

    A raise on row 3 of 50 does not merely lose 47 scans: it leaves the offset
    cursor unadvanced, so the next invocation re-reads the same poison row and
    the walk never finishes. The row must be counted, named, and stepped over.
    """

    def test_a_raising_row_is_isolated_and_its_siblings_are_still_judged(self):
        import asyncio

        import scripts.repair_7354_settled_orientation_swap as mod

        rows = [
            {"id": 1, "espn_id": "a", "sport_key": "x"},
            {"id": 2, "espn_id": "b", "sport_key": "x"},  # this one explodes
            {"id": 3, "espn_id": "c", "sport_key": "x"},
        ]
        judged = []

        async def fake_scan(session, client, row, res, apply):
            if row["id"] == 2:
                raise RuntimeError("ESPN said no")
            judged.append(row["id"])
            res["aligned"] += 1

        class _Result:
            def scalar(self):
                return len(rows)

            def mappings(self):
                return self

            def all(self):
                return rows

        class _Session:
            async def execute(self, *a, **kw):
                return _Result()

            async def rollback(self):
                pass

            async def commit(self):
                pass

        monkey = {}
        monkey["scan"] = mod._scan_one
        mod._scan_one = fake_scan
        mod_service = mod.__dict__.get("ESPNAPIService")
        try:
            import app.services.espn_api as espn_mod
            real = espn_mod.ESPNAPIService
            espn_mod.ESPNAPIService = lambda *a, **kw: object()
            try:
                res = asyncio.run(mod.repair(_Session(), apply=False))
            finally:
                espn_mod.ESPNAPIService = real
        finally:
            mod._scan_one = monkey["scan"]
            if mod_service is not None:
                mod.__dict__["ESPNAPIService"] = mod_service

        assert judged == [1, 3], "the siblings of the bad row were not judged"
        assert res["errors"] == 1
        assert any("ev2" in line and "ESPN said no" in line
                   for line in res["error_rows"]), res["error_rows"]

    def test_a_raised_row_is_never_counted_as_a_clean_skip(self):
        """Folding a raise into `aligned` would make the rail lie about its
        own coverage — the row was not judged at all."""
        import inspect

        import scripts.repair_7354_settled_orientation_swap as mod

        src = inspect.getsource(mod.repair)
        handler = src[src.index("except Exception"):]
        for bucket in ("aligned", "unresolved", "nothing_to_repair"):
            assert f'res["{bucket}"]' not in handler, (
                f"the error handler increments {bucket!r} — a row that raised "
                f"was not judged and must not be counted as one that was"
            )
        assert 'res["errors"]' in handler


class TestTheUndoObservesEveryColumnItRestores:
    """A restore that writes a column it does not compare is a blind overwrite.

    That is the CERT-3141 lesson. Every column the repair can write has a
    routine newer-value case — the blend is rewritten by `backfill_winners` and
    by any re-resolve WITHOUT touching the score — so a compare-and-swap that
    observes only the score passes on exactly the rows where the undo would
    replace a newer, better value with the pre-repair one.

    Checked structurally rather than by eye, so a column added to the repair
    later cannot quietly miss the WHERE.
    """

    def _restore_sql(self):
        from scripts.restore_7354_settled_orientation_swap import _RESTORE_EVENT_SQL
        return _RESTORE_EVENT_SQL

    def test_every_restored_column_is_also_compared(self):
        import re

        sql = self._restore_sql()
        set_clause, where_clause = sql.split("WHERE", 1)
        restored = set(re.findall(r"b\.old_(\w+)", set_clause))
        compared = set(re.findall(r"b\.new_(\w+)", where_clause))

        assert restored, "the restore writes nothing — the parse is wrong"
        assert restored == compared, (
            f"restored but not compared: {sorted(restored - compared)}; "
            f"compared but not restored: {sorted(compared - restored)}"
        )

    def test_the_comparison_is_null_safe(self):
        """`= NULL` is never true, so a plain `=` CAS can never restore a row
        whose banked value is NULL — and on a half-healed row the score half of
        the manifest is exactly that until the stamp fills it in."""
        sql = self._restore_sql()
        _, where_clause = sql.split("WHERE", 1)

        assert "IS NOT DISTINCT FROM" in where_clause
        for bad in ("= b.new_home_score", "= b.new_win_probability_sources"):
            assert bad not in where_clause, f"null-unsafe comparison: {bad}"

    def test_the_backup_banks_an_old_value_for_every_column_the_repair_writes(self):
        import re

        from scripts.repair_7354_settled_orientation_swap import _BAK_CREATE_SQL

        banked_old = set(re.findall(r"old_(\w+)\s", _BAK_CREATE_SQL))
        restored = set(re.findall(r"b\.old_(\w+)", self._restore_sql()))

        assert restored <= banked_old, (
            f"the undo restores columns the backup never banks: "
            f"{sorted(restored - banked_old)}"
        )


class TestEveryLazyImportInTheRailResolves:
    """A function-local import is not exercised by importing the module.

    This rail's ESPN client, session factory and SQLAlchemy handles are all
    imported inside the functions that use them — correctly, to keep a script
    importable without a database. The cost is that a wrong symbol name is
    invisible until the moment the rail runs against production, which is the
    worst possible time to discover it. `ESPNAPIClient` (the class is
    `ESPNAPIService`) shipped that way and got this far.

    So the names are resolved here, statically, for both halves of the pair.
    """

    @pytest.mark.parametrize("module_name", [
        "scripts.repair_7354_settled_orientation_swap",
        "scripts.restore_7354_settled_orientation_swap",
    ])
    def test_every_function_local_import_names_something_that_exists(self, module_name):
        import ast
        import importlib

        mod = importlib.import_module(module_name)
        tree = ast.parse(open(mod.__file__).read())

        checked = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.col_offset == 0:
                continue  # module-level imports already ran at import time
            target = importlib.import_module(node.module)
            for alias in node.names:
                assert hasattr(target, alias.name), (
                    f"{module_name} imports {alias.name!r} from {node.module!r} "
                    f"inside a function, and it does not exist"
                )
                checked += 1

        assert checked, f"{module_name}: no function-local imports found to check"


class TestBothHalvesOfThePairAnswerHelpWithoutADatabase:
    """`--help` is the only invocation that must work on any machine.

    The undo shipped without one, so a bare run — the thing a reader reaches for
    first to find out what the script does — opened a connection and died in a
    60-line asyncpg traceback. The repair half already had the guard; this is the
    pair, so the guard is asserted on the pair.
    """

    @pytest.mark.parametrize("script", [
        "repair_7354_settled_orientation_swap.py",
        "restore_7354_settled_orientation_swap.py",
    ])
    def test_help_exits_zero_and_opens_no_database(self, script):
        import subprocess

        backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ)
        # A URL nothing can connect to: reaching the DB at all becomes a failure
        # rather than an accident of whatever this machine happens to be running.
        env["DATABASE_URL"] = "postgresql+asyncpg://nobody@127.0.0.1:1/nothing"

        proc = subprocess.run(
            [sys.executable, os.path.join("scripts", script), "--help"],
            cwd=backend, env=env, capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, (
            f"{script} --help exited {proc.returncode}\n{proc.stderr[-2000:]}"
        )
        assert "--apply" in proc.stdout, (
            f"{script} --help printed no usage naming --apply:\n{proc.stdout}"
        )


class TestThePlanCarriesItsOwnEvidence:
    def test_a_skipped_plan_names_why_in_words_a_reader_can_check(self):
        for row, ee in (
            (_row(UVA, WVU, 27, 38), _specimen_espn()),
            (_row(None, None, 27, 38), _specimen_espn()),
            (_row(WVU, UVA, 21, 38), _specimen_espn()),
        ):
            plan = plan_orientation_repair(row, ee)
            assert plan.reason, f"{plan.action} carries no reason"
            assert plan.writes is False

    def test_the_default_plan_writes_nothing(self):
        """A plan nobody filled in must never read as repairable (gotcha #53)."""
        assert OrientationPlan(event_id=1).writes is False
