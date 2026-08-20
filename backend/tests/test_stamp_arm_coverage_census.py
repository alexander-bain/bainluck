"""The coverage census stays wired — Fable's LAT-P075 item 4, banked as doctrine.

**The finding this guards.** LAT-P074's stamp-arm read showed the headline number
(`above_ceiling_total`) holding rock-steady at 39 while `enrich_snippet_angles`
quietly fell out of the stamp arm — the entry moved `graded` -> `unmapped`, so the
DENOMINATOR shrank and the headline improved by going blinder. LAT-P075's read was
worse: **seven distinct coverage values spanning 24 to 32**, a quarter of the arm
churning, with `above_ceiling_total` never moving off 39.

Fable banked the general clause: **a metric that improves while its denominator
shrinks is a defect until proven otherwise** — and ruled the census stays on as a
standing guard on every latency stamp read.

**Why a test and not just a habit.** The census was, until this file, an unguarded
field on a script. Deleting `stamp_tasks_covered_per_sample` would restore exactly
the blindness it exists to detect, and nothing would go red — the grade would still
print, still say `above_ceiling_stable: true`, and still be believed.

**What this would have to SEE to go red** (Fable's standing rule of 2026-08-19 —
name the failing input, do not merely claim coverage):

* the per-sample coverage field removed from, or renamed in, `grade_series`;
* `above_ceiling_stable` computed without the census being reported alongside it,
  i.e. a stability verdict published with no way to check its denominator;
* a series in which coverage moves being graded as though it had not.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "stamp_arm_read.py"


def _load():
    spec = importlib.util.spec_from_file_location("stamp_arm_read", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _series(tmp_path, samples):
    p = tmp_path / "series.jsonl"
    p.write_text("".join(json.dumps(s) + "\n" for s in samples), encoding="utf-8")
    return str(p)


def _sample(read_at, covered_names, ceiling_total):
    return {
        "read_at": read_at,
        "above_ceiling_total": ceiling_total,
        "stamp_rows": {n: {"verdict": "on_schedule"} for n in covered_names},
    }


def test_the_script_still_exists_and_reports_the_census():
    assert _SCRIPT.is_file(), f"the census script is gone: {_SCRIPT}"
    mod = _load()
    assert hasattr(mod, "grade_series")


def test_a_shrinking_denominator_is_visible_even_when_the_headline_holds():
    """THE named failure, reproduced: the exact LAT-P074 shape.

    A task drops out of the stamp arm between samples. `above_ceiling_total` does
    not move, so every headline reads identical and stable. The only signal that
    anything happened is the coverage list carrying more than one value.
    """
    import tempfile

    mod = _load()
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        path = _series(
            tmp,
            [
                _sample("2026-08-19T23:00:00Z", ["a", "b", "c", "enrich_snippet_angles"], 39),
                # enrich_snippet_angles falls out; the ceiling total is UNCHANGED.
                _sample("2026-08-20T00:00:00Z", ["a", "b", "c"], 39),
            ],
        )
        graded = mod.grade_series(path)

    assert graded["above_ceiling_total_values"] == [39]
    assert graded["above_ceiling_stable"] is True, (
        "the headline is stable — which is precisely why it is not sufficient"
    )
    assert graded["stamp_tasks_covered_per_sample"] == [3, 4], (
        "the census must show BOTH coverage values; collapsing this to a single "
        "number is how the instrument went blind in the first place"
    )
    assert len(graded["stamp_tasks_covered_per_sample"]) > 1, (
        "more than one coverage value in a series is a FINDING, not noise"
    )


def test_a_stable_series_reports_a_single_coverage_value():
    """The negative control: no churn, one value. Without this the test above
    could pass on a script that always returned a multi-element list."""
    import tempfile

    mod = _load()
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        path = _series(
            tmp,
            [
                _sample("2026-08-19T23:00:00Z", ["a", "b", "c"], 39),
                _sample("2026-08-20T00:00:00Z", ["a", "b", "c"], 39),
            ],
        )
        graded = mod.grade_series(path)

    assert graded["stamp_tasks_covered_per_sample"] == [3]
    assert graded["above_ceiling_stable"] is True


def test_the_census_is_reported_alongside_every_stability_verdict():
    """`above_ceiling_stable` must never be publishable without its denominator.

    A stability claim whose population is unreported is unfalsifiable, which is
    the whole defect. Asserted structurally so the two cannot be separated.
    """
    import tempfile

    mod = _load()
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        path = _series(tmp, [_sample("2026-08-19T23:00:00Z", ["a"], 39)])
        graded = mod.grade_series(path)

    assert "above_ceiling_stable" in graded
    assert "stamp_tasks_covered_per_sample" in graded, (
        "the stability verdict is present but its denominator is not — this is "
        "the shape Fable banked as a defect until proven otherwise"
    )
    assert "span_h" in graded and "samples" in graded, (
        "a grade must carry the span it actually reached; LAT-P075 could only "
        "take 3.16h of a 24h read and had to say so"
    )


def test_an_empty_series_refuses_rather_than_grading_nothing():
    """A grade over zero samples must not read as a clean grade (gotcha #53)."""
    import tempfile

    mod = _load()
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        path = _series(tmp, [])
        with pytest.raises(SystemExit):
            mod.grade_series(path)
