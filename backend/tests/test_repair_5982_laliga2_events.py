"""#5982 — guards on the repair that moves Kalshi-born LaLiga 2 rows off La Liga.

The repair itself is four lines of UPDATE. Everything that can go wrong with it
is around the edges: which app it writes from, whether an undo exists before the
write happens, whether the population it selects is the one the header
advertises, and whether the series it trusts are the ones the shipped map names.
Those are what this file tests.

It does NOT re-test `get_sport_key_from_ticker`; that is
`test_laliga2_is_not_la_liga_5982.py`. The one thing it does assert about the map
is the coupling: the script derives its series list from
`KALSHI_FUTURES_TICKER_TO_SPORT_KEY` and must keep doing so, because a script
that hardcodes a second opinion about which tickers name LaLiga 2 would
reproduce the exact failure it repairs.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import re
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REPAIR_PATH = _SCRIPTS / "repair_5982_laliga2_events_under_la_liga.py"
RESTORE_PATH = _SCRIPTS / "restore_5982_laliga2_events_under_la_liga.py"


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


class TestTheRunbookTargetsTheProducer:
    """The repair must write from the app that can put the defect back."""

    def test_the_producer_app_is_where_the_minting_task_runs(self, repair):
        """🔴 Catches a runbook aimed at the web app after a heavy split.

        `match_prediction_markets` mints these rows. If it is in HEAVY_TASKS the
        producer is `bainluck-heavy`; if it ever stops being heavy, this fires
        rather than leaving the header quietly lying (standing notice 48).
        """
        from app.tasks import HEAVY_TASKS

        is_heavy = "app.tasks.match_prediction_markets" in HEAVY_TASKS
        assert is_heavy, (
            "match_prediction_markets left HEAVY_TASKS — PRODUCER_APP and the "
            "runbook in the repair's header both need re-deciding"
        )
        assert repair.PRODUCER_APP == "bainluck-heavy"

    def test_the_header_tells_the_operator_to_check_the_heavy_release_first(self):
        """The map fix only stops the minting once heavy carries it."""
        header = REPAIR_PATH.read_text()
        assert "releases -a bainluck-heavy" in header, (
            "step 0 of the runbook — the heavy release check — is gone; without "
            "it the repair runs against a producer still minting the defect"
        )


class TestTheWriteRefusals:
    """`--backup` and `--apply` refuse off the producer app; a dry run does not."""

    class _Args:
        def __init__(self, **kw):
            self.apply = kw.get("apply", False)
            self.backup = kw.get("backup", False)
            self.dry_run = kw.get("dry_run", False)

    def test_a_dry_run_needs_no_app_at_all(self, repair, monkeypatch):
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        assert repair.wrong_app_refusal(self._Args(dry_run=True)) is None

    @pytest.mark.parametrize("flag", ["apply", "backup"])
    def test_an_unset_app_refuses_to_write(self, repair, monkeypatch, flag):
        """Unset means a laptop pointed at production. That is the case to stop."""
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        refusal = repair.wrong_app_refusal(self._Args(**{flag: True}))
        assert refusal and "HEROKU_APP_NAME is unset" in refusal

    @pytest.mark.parametrize("app", ["bainluck", "bainluck-staging", ""])
    def test_the_wrong_app_refuses_and_names_where_it_is(
        self, repair, monkeypatch, app
    ):
        monkeypatch.setenv("HEROKU_APP_NAME", app)
        refusal = repair.wrong_app_refusal(self._Args(apply=True))
        assert refusal and repair.PRODUCER_APP in refusal

    def test_the_producer_app_may_write(self, repair, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", repair.PRODUCER_APP)
        assert repair.wrong_app_refusal(self._Args(apply=True)) is None
        assert repair.wrong_app_refusal(self._Args(backup=True)) is None

    def test_the_gate_survives_a_caller_with_no_backup_flag(self, repair, monkeypatch):
        """The undo's parser has no `--backup`; reading it must not raise."""
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)

        class OnlyApply:
            apply = True

        refusal = repair.wrong_app_refusal(OnlyApply())
        assert refusal and "REFUSING" in refusal


class TestTheUndoTakesTheSameGate:
    def test_the_restore_imports_the_repairs_gate_rather_than_copying_it(
        self, repair, restore
    ):
        """One refusal, two programs.

        A copied refusal is a refusal that can drift, and the drifting one is
        always the undo — the write typed in a hurry by someone who has just
        decided the repair went wrong.

        Asserted on the code object's FILE, not with `is` against this file's
        own `repair` fixture. The fixture loads the repair through its own
        import spec, so the two module objects are different by construction and
        an identity check would be measuring the harness (it did, on the first
        run of this file). Where the function was DEFINED is the fact that
        matters — the sibling `test_repair_5821_listing_dates.py` learned this
        first.
        """
        assert restore.wrong_app_refusal.__code__.co_filename == str(REPAIR_PATH)
        assert (
            "def wrong_app_refusal" not in RESTORE_PATH.read_text()
        ), "the restore grew its own copy of the app gate"
        assert restore.PRODUCER_APP == repair.PRODUCER_APP

    def test_the_restore_actually_calls_the_gate(self, restore, monkeypatch):
        """🔴 Catches an undo that imports the gate and forgets to invoke it.

        Every other test in this class passes with the gate call DELETED from
        `run()`: they assert what the shared function does and that the restore
        has not grown its own copy, and neither is a claim that the restore
        invokes it. So this one RUNS the program — on the wrong app with
        `--apply` it must exit 2, which it can only do by refusing before it
        opens a session.
        """
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        assert asyncio.run(restore.run(argparse.Namespace(apply=True))) == 2

    def test_the_repair_actually_calls_the_gate(self, repair, monkeypatch):
        """Same claim, aimed at the repair. Same reason it is separate."""
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        assert (
            asyncio.run(
                repair.run(argparse.Namespace(apply=True, backup=False, dry_run=False))
            )
            == 2
        )

    def test_the_restore_reads_the_table_the_repair_writes(self, repair, restore):
        assert restore.BACKUP_TABLE is repair.BACKUP_TABLE
        assert repair.BACKUP_TABLE == "backup_5982_event_sports"

    def test_the_restore_replays_the_recorded_sport_not_a_constant(self):
        """The undo must not 'set them back to La Liga'.

        It replays `backup.sport_id` per row, so a row that was somewhere else
        goes back to somewhere else. A restore that hardcoded the wrong key
        would be a second repair wearing an undo's name.
        """
        source = RESTORE_PATH.read_text()
        assert "SET sport_id = b.sport_id" in source
        assert "WRONG_SPORT_KEY" not in source, (
            "the undo names a competition — it must replay the recorded id"
        )


class TestTheSeriesComeFromTheShippedMap:
    def test_the_series_are_derived_and_are_the_laliga2_five(self, repair):
        """Still five, now read out of BOTH maps (#3813).

        The population did not change; where it is written down did. #3813 moved
        the four FIXTURE families to the game map to make them game-level — a key
        in both maps is a tie, and a tie is not game-level — so a futures-only
        derivation now yields `kxlaliga2promo` alone and this repair would find
        none of the fixtures it exists to retag. It would not crash; it would
        report a small clean number, which is the failure most likely to be
        believed.
        """
        from app.utils.sport_keys import (
            KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
            KALSHI_TICKER_TO_SPORT_KEY,
        )

        series = repair.segunda_series()
        assert series == sorted(
            p
            for mapping in (
                KALSHI_TICKER_TO_SPORT_KEY,
                KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
            )
            for p, k in mapping.items()
            if k == "soccer_spain_segunda_division"
        )
        assert set(series) == {
            "kxlaliga2game",
            "kxlaliga2spread",
            "kxlaliga2total",
            "kxlaliga2btts",
            "kxlaliga2promo",
        }

    def test_the_derivation_reads_both_maps_not_just_the_one_it_started_in(
        self, repair
    ):
        """#3813's rider, asserted so a revert to one map cannot pass quietly.

        The five are SPLIT: four game-level, one season. Naming which side each
        comes from is what makes a single-map derivation fail here instead of
        silently shrinking the repair's reach.
        """
        from app.utils.sport_keys import (
            KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
            KALSHI_TICKER_TO_SPORT_KEY,
        )

        series = set(repair.segunda_series())
        assert series & set(KALSHI_TICKER_TO_SPORT_KEY) == {
            "kxlaliga2game",
            "kxlaliga2spread",
            "kxlaliga2total",
            "kxlaliga2btts",
        }
        assert series & set(KALSHI_FUTURES_TICKER_TO_SPORT_KEY) == {
            "kxlaliga2promo"
        }

    def test_the_second_half_family_is_not_in_the_repair_population(self, repair):
        """The trap, stated where the repair can trip on it.

        `kxlaliga2h*` are La Liga second-half markets. If one ever appeared in
        this list the repair would march top-flight fixtures onto the Segunda
        page — the same defect, aimed the other way.
        """
        assert not [s for s in repair.segunda_series() if s.startswith("kxlaliga2h")]

    def test_the_script_hardcodes_no_series_list(self):
        """🔴 Catches someone pasting the five prefixes into the SQL."""
        body = REPAIR_PATH.read_text().split('_POPULATION_SQL = """')[1]
        assert "kxlaliga" not in body.lower(), (
            "a ticker prefix is spelled below the population SQL — the series "
            "must come from segunda_series(), which reads the shipped map"
        )

    def test_an_empty_series_list_refuses_rather_than_moving_nothing_quietly(self):
        """An unfixed/reverted map must stop the program, not make it a no-op.

        A silent 0-row run reads exactly like "already repaired", which is the
        report most likely to be believed.
        """
        source = REPAIR_PATH.read_text()
        assert "if not series:" in source and "REFUSING" in source


class TestThePopulationIsTheOneTheHeaderAdvertises:
    @pytest.mark.parametrize(
        "clause,why",
        [
            ("e.external_id IS NULL", "a schedule provider assigned the competition"),
            ("e.espn_id IS NULL", "ESPN assigned the competition"),
            ("s.key = :wrong_key", "only rows on the wrong competition move"),
        ],
    )
    def test_each_promised_fence_is_still_a_clause(self, repair, clause, why):
        assert clause in repair._POPULATION_SQL, f"fence dropped: {why}"

    def test_the_mixed_evidence_fence_is_two_sided(self, repair):
        """Both halves of the HAVING, or the fence is not a fence.

        With only the `> 0` half, a row holding one LaLiga 2 prop AND a real La
        Liga market would be moved — an identity question answered by a guess.
        """
        sql = repair._POPULATION_SQL
        assert "= ANY(:series)\n           ) > 0" in sql
        assert "<> ALL(:series)\n           ) = 0" in sql

    def test_the_mixed_rows_are_reported_not_silently_skipped(self, repair):
        assert "= ANY(:series)" in repair._MIXED_SQL
        assert "<> ALL(:series)" in repair._MIXED_SQL
        assert "REFUSED (mixed evidence)" in REPAIR_PATH.read_text()

    def test_the_binds_the_caller_passes_are_the_binds_the_sql_wants(self, repair):
        """🔴 Catches a renamed bind — psycopg reports it only at runtime."""
        for sql in (repair._POPULATION_SQL, repair._MIXED_SQL):
            wanted = set(re.findall(r":([a-z_]+)", sql))
            assert wanted <= {"wrong_key", "series"}, (
                f"SQL wants binds {sorted(wanted)}; run() supplies "
                "{'wrong_key', 'series'}"
            )

    def test_apply_refuses_without_a_live_backup_row_for_every_event(self):
        """An undo that covers only some rows is not an undo."""
        source = REPAIR_PATH.read_text()
        assert "REFUSING --apply" in source
        assert "restored_at IS NULL" in source, (
            "the backup check must ignore rows already restored, or a second "
            "repair run after a restore would pass on stale receipts"
        )

    def test_the_update_is_bounded_by_the_selected_ids(self, repair):
        """🔴 Catches an UPDATE that keys on the sport instead of the population.

        `UPDATE events SET sport_id = ... WHERE sport_id = <la liga>` would move
        all 1,357 La Liga rows. The write must name the ids the population
        returned.
        """
        source = REPAIR_PATH.read_text()
        update = source[source.index("UPDATE events SET sport_id") :][:220]
        assert "id = ANY(:ids)" in update


class TestTheRunbookMatchesTheProgram:
    """A runbook is a promise about a CLI. These two drift silently."""

    @staticmethod
    def _declared(path: Path) -> set[str]:
        return set(re.findall(r'add_argument\(\s*"(--[a-z-]+)"', path.read_text()))

    @staticmethod
    def _used(path: Path) -> set[str]:
        used = set()
        for line in path.read_text().splitlines():
            if path.stem in line and ".py" in line:
                used |= set(re.findall(r"(--[a-z-]+)", line))
        return used

    @pytest.mark.parametrize("path", [REPAIR_PATH, RESTORE_PATH])
    def test_every_flag_the_runbook_uses_exists(self, path):
        declared, used = self._declared(path), self._used(path)
        assert used, f"{path.name}'s header stopped showing any command line"
        assert used <= declared, (
            f"the runbook passes {sorted(used - declared)}, which the parser "
            f"does not accept (it declares {sorted(declared)})"
        )

    def test_the_repair_points_at_a_restore_script_that_exists(self, repair):
        printed = re.findall(
            r"scripts/(restore_[a-z0-9_]+\.py)", REPAIR_PATH.read_text()
        )
        assert printed, "the repair never names its undo"
        for name in set(printed):
            assert (_SCRIPTS / name).exists(), f"runbook names a missing script: {name}"
            assert name == RESTORE_PATH.name
