"""#12340: a staged-futures pass releases its roster once the units are planned.

The roster (2,162,152 slim tuples on the Nov 10 beat, ~184 MB of heap in the lab)
used to stay alive through the unit loop and ``staged:finalize``, so finalize's
allocations stacked on it. Nothing after planning reads it: the units run off
``assignment`` and ``chunks``. Lab, Nov 10 (the real ``generation_fingerprint``
and ``plan_units`` at production size): RSS at a finalize stand-in 1,023 MB with
the roster kept, 971 MB with it released.
"""
import ast
import inspect
import textwrap

from app.tasks import precompute_calibration as pc


def _function():
    return ast.parse(textwrap.dedent(inspect.getsource(pc._run_staged_futures))).body[0]


def test_the_roster_is_deleted_after_planning():
    fn = _function()
    dels = [n for n in ast.walk(fn) if isinstance(n, ast.Delete)
            and any(isinstance(t, ast.Name) and t.id == "roster" for t in n.targets)]
    assert len(dels) == 1, "exactly one `del roster`"
    plan = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
            and getattr(n.func, "id", None) == "plan_units"]
    assert plan and dels[0].lineno > plan[0].lineno, "released after the units are planned"


def test_nothing_reads_the_roster_after_it_is_released():
    fn = _function()
    released = next(n.lineno for n in ast.walk(fn) if isinstance(n, ast.Delete)
                    and any(isinstance(t, ast.Name) and t.id == "roster" for t in n.targets))
    late = sorted({n.lineno for n in ast.walk(fn)
                   if isinstance(n, ast.Name) and n.id == "roster" and n.lineno > released})
    assert late == [], f"`roster` read after release at lines {late}"
