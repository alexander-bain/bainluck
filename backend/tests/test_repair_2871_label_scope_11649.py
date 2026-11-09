"""#11649: the #2871 repair can be scoped to the labels a ruling cleared.

Ruling 97 cleared the attended repair of the "Exact Margin" and "First
Touchdown Scorer" games only. The script's full net held 820 rows in
Speed's Nov 8 census: those 283 plus 537 older closed or voided rows of other #2871
labels, which nobody ruled on. `--labels` narrows the POPULATION to the named
labels and nothing else: the counterpart exclusion keeps the whole vocabulary,
because an "Exact Score" row is never a real fixture whichever labels a run
repairs.
"""
import argparse
import asyncio
import contextlib
import importlib.util
import pathlib
import re
import sys
import types

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "repair_2871_phantom_derivative_events",
    _SCRIPTS / "repair_2871_phantom_derivative_events.py")
repair = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(repair)

RULED = ["Exact Margin", "First Touchdown Scorer"]


def test_no_labels_is_the_whole_vocabulary_so_the_default_run_is_unchanged():
    assert repair.label_scope_re([]) is repair.DERIV_RE


@pytest.mark.parametrize("name,inside", [
    ("Pistons - Exact Margin", True),
    ("Bucks – Exact Margin", True),
    ("Bears - First Touchdown Scorer", True),
    ("Bears - first  touchdown scorer", True),
    # Other #2871 labels in the same net: the 537 nobody ruled on.
    ("Lausanne-Sport - Exact Score", False),
    ("Lausanne-Sport - Halftime Result", False),
    ("Yankees - First 5 Innings Winner", False),
    # A period segment in front is a different label from the one named.
    ("Pistons - 1st Half Exact Margin", False),
    ("Lakers", False),
])
def test_the_scope_is_exactly_the_named_labels(name, inside):
    scope = repair.label_scope_re(RULED)
    assert bool(re.search(scope, name, re.IGNORECASE)) is inside


def test_a_scoped_row_is_still_inside_the_full_net():
    # The SQL ANDs the two, so this is belt and braces: every name the scope
    # admits is one the prevention refuses.
    for name in ("Pistons - Exact Margin", "Bears - First Touchdown Scorer"):
        assert re.search(repair.DERIV_RE, name, re.IGNORECASE)


@pytest.mark.parametrize("label", ["Moneyline", "Spread", "Game 3"])
def test_a_label_outside_the_vocabulary_is_refused(label):
    with pytest.raises(ValueError, match="not a derivative market type"):
        repair.label_scope_re([label])


def test_the_scope_travels_as_a_bind_and_has_no_noncapturing_group():
    # gotcha #45: it is bound as a value, but keep it plain anyway.
    assert "(?:" not in repair.label_scope_re(RULED)
    assert "~* :scope_re" in repair._POPULATION


def test_the_counterpart_exclusion_keeps_the_full_vocabulary():
    for sql in (repair._PLAN_SQL, repair._ALIAS_SQL):
        assert "r.away_team_name !~* :deriv_re" in sql
        assert "!~* :scope_re" not in sql
    assert ":scope_re" in repair._CENSUS_SQL


class _Recorder:
    def __init__(self, results):
        self.results, self.binds = list(results), []

    async def execute(self, _stmt, binds=None):
        self.binds.append(binds)
        rows = self.results.pop(0)
        return types.SimpleNamespace(mappings=lambda: types.SimpleNamespace(all=lambda: rows),
                                     all=lambda: rows)


def test_build_plan_binds_the_scope_on_both_reads():
    scope = repair.label_scope_re(RULED)
    s = _Recorder([[], []])
    asyncio.run(repair.build_plan(s, scope_re=scope))
    assert [b["scope_re"] for b in s.binds] == [scope, scope]
    assert all(b["deriv_re"] is repair.DERIV_RE for b in s.binds)


def test_run_binds_the_scope_on_the_census(monkeypatch, capsys):
    s = _Recorder([[]])

    @contextlib.asynccontextmanager
    async def session():
        yield s

    monkeypatch.setitem(sys.modules, "app.tasks.base",
                        types.SimpleNamespace(get_task_session=session))
    args = argparse.Namespace(labels="Exact Margin, First Touchdown Scorer",
                              allow_small=True, backup=False, apply=False,
                              include_live=False, limit=0)
    asyncio.run(repair.run(args))
    assert s.binds[0]["scope_re"] == repair.label_scope_re(RULED)
    out = capsys.readouterr().out
    assert "scoped to --labels: Exact Margin, First Touchdown Scorer" in out
    assert "population is 0" in out
