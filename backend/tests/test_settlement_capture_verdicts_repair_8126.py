"""#8126 — the apply/restore scripts' guards that need no database.

The SQL itself (bank-before-write, compare-and-swap, row locks, drift refusal,
exact undo) is proven against a real Postgres by
``artifacts/calibration-8126-consumer/test_settlement_capture_verdicts_repair_8126_pg.py``
— staged there until its CI wiring is in scope, so it is NOT run by this suite.
This file holds what CI can check without a server, and must stay that way: a
guard for a skip-gated gate's defects cannot itself be skip-gated.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND / "scripts"
APPLY = SCRIPTS / "apply_settlement_capture_verdicts_8126.py"
RESTORE = SCRIPTS / "restore_settlement_capture_verdicts_8126.py"
CONSUMER = BACKEND / "app" / "utils" / "settlement_capture_consumer.py"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f"{path.stem}_unit", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # a dataclass resolves its module by name
    spec.loader.exec_module(mod)
    return mod


apply_m = _load(APPLY)
restore_m = _load(RESTORE)


class _NoSql:
    """A session that fails the test if any SQL is issued."""

    async def execute(self, *a, **k):  # pragma: no cover - reaching it is the failure
        raise AssertionError("SQL issued before the bound was checked")


class TestOnlyProductionRuns:
    @pytest.mark.parametrize("mod", [apply_m, restore_m])
    @pytest.mark.parametrize("app", ["", "bainluck-staging", "local", "BAINLUCK"])
    def test_anything_but_the_named_apps_refuses(self, mod, app):
        with pytest.raises(mod.Refused):
            mod.refuse_unless_production({"HEROKU_APP_NAME": app})

    @pytest.mark.parametrize("mod", [apply_m, restore_m])
    @pytest.mark.parametrize("app", ["bainluck", "bainluck-heavy"])
    def test_the_named_apps_pass(self, mod, app):
        mod.refuse_unless_production({"HEROKU_APP_NAME": app})

    @pytest.mark.parametrize(
        "script,args",
        [(APPLY, ["--capture-id", "107429", "--apply"]), (RESTORE, ["--run-id", "x", "--apply"])],
    )
    def test_off_production_the_cli_refuses_before_touching_a_database(self, script, args):
        env = {k: v for k, v in os.environ.items() if k not in {"HEROKU_APP_NAME", "DATABASE_URL"}}
        proc = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert proc.stdout.startswith("REFUSED: HEROKU_APP_NAME=''")


class TestSelectionIsBounded:
    async def test_too_many_ids_refuse_before_any_sql(self):
        ids = list(range(1, apply_m.MAX_CAPTURES + 2))
        with pytest.raises(apply_m.Refused, match="capture ids"):
            await apply_m.select_captures(_NoSql(), capture_ids=ids, since=None, limit=50)

    @pytest.mark.parametrize("limit", [0, -1, apply_m.MAX_CAPTURES + 1])
    async def test_an_out_of_range_window_refuses_before_any_sql(self, limit):
        with pytest.raises(apply_m.Refused, match="--limit"):
            await apply_m.select_captures(
                _NoSql(), capture_ids=None, since=datetime.now(timezone.utc), limit=limit
            )

    def test_since_needs_a_timezone(self):
        import argparse

        with pytest.raises(argparse.ArgumentTypeError):
            apply_m._parse_since("2026-09-28T00:00")
        assert apply_m._parse_since("2026-09-28T00:00Z").tzinfo is not None


class TestRestoreClassification:
    PRE, POST = (False, None), (True, "api_settlement")
    LEG = (60534962, "KXNASDAQ100U-26AUG17H1200-T27999.99")

    def _b(self, oid=1):
        return restore_m.Banked(oid, self.LEG, self.PRE, self.POST)

    def test_a_row_still_at_the_post_image_is_restorable(self):
        r, a, d = restore_m.classify([self._b()], {1: (self.LEG, self.POST)})
        assert (len(r), len(a), len(d)) == (1, 0, 0)

    def test_a_row_already_back_at_the_pre_image_is_closed_not_rewritten(self):
        r, a, d = restore_m.classify([self._b()], {1: (self.LEG, self.PRE)})
        assert (len(r), len(a), len(d)) == (0, 1, 0)

    @pytest.mark.parametrize(
        "now",
        [(True, "settlement_sync"), (False, "api_settlement"), (None, None), (True, None)],
    )
    def test_any_other_state_is_drift(self, now):
        r, a, d = restore_m.classify([self._b()], {1: (self.LEG, now)})
        assert (len(r), len(a)) == (0, 0) and d == [(self._b(), (self.LEG, now))]

    @pytest.mark.parametrize(
        "leg",
        [(60534963, LEG[1]), (LEG[0], "KXOTHER-LEG"), (LEG[0], LEG[1].lower())],
        ids=["market_id", "external_id", "ticker_case"],
    )
    @pytest.mark.parametrize("grade", [POST, PRE], ids=["at_post", "at_pre"])
    def test_a_repointed_leg_is_drift_whatever_its_grade_reads(self, leg, grade):
        # #8126 review P2: the banked pre-image belongs to the leg the run wrote,
        # so neither restoring onto a changed leg nor closing it as already_pre.
        now = (leg, grade)
        r, a, d = restore_m.classify([self._b()], {1: now})
        assert (len(r), len(a)) == (0, 0) and d == [(self._b(), now)]

    def test_a_deleted_row_is_drift(self):
        _, _, d = restore_m.classify([self._b()], {})
        assert d == [(self._b(), None)]


def test_a_jsonb_handed_back_as_text_is_parsed_and_garbage_is_not_guessed():
    assert apply_m._derived('{"protocol_version": 2, "legs": []}') == {
        "protocol_version": 2,
        "legs": [],
    }
    assert apply_m._derived("not json") == "not json"
    assert apply_m._derived(None) is None


def test_run_ids_are_unique_per_microsecond_and_utc():
    a = apply_m.new_run_id(datetime(2026, 9, 30, 10, 40, 0, 1, tzinfo=timezone.utc))
    b = apply_m.new_run_id(datetime(2026, 9, 30, 10, 40, 0, 2, tzinfo=timezone.utc))
    assert a == "8126-20260930T104000000001Z" and a != b


def _sql_strings(path: Path) -> list[str]:
    """Every string literal (f-strings flattened) in the script, joined per call."""
    out = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "text":
            out.append(ast.unparse(node.args[0]) if node.args else "")
    return out


class TestTheWriteSurfaceIsTwoColumns:
    """No server needed to see WHAT the scripts can write — and that is the risk."""

    @pytest.mark.parametrize("path", [APPLY, RESTORE])
    def test_futures_outcomes_updates_set_only_is_winner_and_resolution_source(self, path):
        updates = [s for s in _sql_strings(path) if "UPDATE futures_outcomes" in s]
        assert updates, "the guard found no UPDATE to check"
        for sql in updates:
            set_clause = re.search(r"SET (.*?)(?:FROM|WHERE)", sql, re.S).group(1)
            cols = set(re.findall(r"(\w+)\s*=", set_clause))
            assert cols == {"is_winner", "resolution_source"}, sql

    def test_the_apply_update_compares_and_swaps_on_a_blank_result(self):
        (sql,) = [s for s in _sql_strings(APPLY) if "UPDATE futures_outcomes" in s]
        assert "o.resolution_source IS NULL" in sql
        assert "o.is_winner IS NOT DISTINCT FROM p.pre_is_winner" in sql

    @pytest.mark.parametrize("path", [APPLY, RESTORE])
    def test_no_delete_and_no_other_table_is_written(self, path):
        for sql in _sql_strings(path):
            assert "DELETE" not in sql.upper(), sql
            for verb in ("UPDATE", "INSERT INTO"):
                for target in re.findall(rf"{verb}\s+(\{{?\w+\}}?)", sql):
                    assert target in {
                        "futures_outcomes",
                        "{REPAIR_BACKUP_TABLE}",
                    }, sql

    def test_the_consumer_module_stays_pure(self):
        tree = ast.parse(CONSUMER.read_text())
        imported = {
            (n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        } | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not any(
            m.startswith(("sqlalchemy", "app.models", "app.tasks", "app.services", "httpx"))
            for m in imported
        ), imported
