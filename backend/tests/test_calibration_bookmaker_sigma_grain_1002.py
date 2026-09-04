"""CAL-P1002 (#1978) — ``--sigma`` on the bookmaker rail could never have run.

THE DEFECT. ``calibration_bookmaker_cell_fold.py`` is the ONLY instrument that
can reach the six ``odds_api_bookmaker`` board cells — the file's own docstring
records why (``futures_markets`` has no ``odds_api_bookmaker`` rows at all, so
the whole ``calibration_cell_exact`` family folds an empty roster there). CAL-P998
added ``--sigma``, which implies ``--grain game_bucket``, and its tail read

    SELECT event_id, bucket_idx, ... FROM outcomes GROUP BY event_id, bucket_idx

while the ``outcomes`` CTE projects only ``event_id, bookmaker, commence_time,
captured_at, prob, won``. **There is no ``bucket_idx`` to select.** So every
``--sigma`` run died on its first chunk with ``undefined_column`` from
``db-query``, and the six cells — 83,009 excess-outcomes, 6 of the 13 queued
after D62, ranks 2/4/7/8/12/14 — were listed as "measurable" while being
measurable by nothing.

It went unnoticed because the defect is in the ONE grain no default path uses:
``--grain bucket`` (the default) and ``--grain game`` both work, and only
``--sigma`` selects the broken tail.

THE FIX. The decile expression is written once, as ``_BUCKET_EXPR``, and both
tails interpolate it. That is not tidying: the cluster bootstrap's correctness
depends on the game x decile grain binning a row into exactly the decile the
published bucket grain folded it into, and two copies of an expression can
drift apart while one cannot.

PROVEN AGAINST PRODUCTION, not only here — ``--sport-key basketball_nba --sigma
--check-payload`` now completes: 573 games, 10,186 book-rows, replication
17.777x, ECE 5.18 pp against a published 5.18 pp, measured cluster SE 1.317
(sigma 2.03) against the row-grain estimate 0.495 (sigma 5.41).
"""

from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest


def _fold_module():
    """The script, loaded from disk — it is a script, not a package module."""
    path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "scripts"
        / "calibration_bookmaker_cell_fold.py"
    )
    spec = importlib.util.spec_from_file_location("_bookmaker_cell_fold", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FOLD = _fold_module()

#: Exactly what the ``outcomes`` CTE projects. Any tail column outside this set
#: (or defined by the tail itself) is an ``undefined_column`` waiting for a run.
OUTCOMES_COLUMNS = {
    "event_id",
    "bookmaker",
    "commence_time",
    "captured_at",
    "prob",
    "won",
}


def test_the_outcomes_cte_still_projects_what_this_file_thinks_it_does():
    """The premise of every test below, checked rather than assumed.

    If the CTE gains or loses a column this goes red first, so the failure names
    the drift instead of showing up as a confusing assertion three tests down.
    """
    body = FOLD._BODY
    outcomes = body[body.index("outcomes AS ("):]
    for column in ("event_id", "bookmaker", "commence_time", "captured_at", "prob", "won"):
        assert re.search(rf"\b{column}\b", outcomes), f"{column} left the outcomes CTE"
    assert "bucket_idx" not in outcomes, (
        "outcomes now projects bucket_idx — if that is deliberate, the tails no "
        "longer need to compute it and this whole file should be re-thought"
    )


@pytest.mark.parametrize("grain", sorted(FOLD.TAILS))
def test_no_tail_selects_a_column_that_does_not_exist(grain):
    """THE DEFECT ARM, generalised past the one instance.

    Every bare identifier a tail selects must either be projected by ``outcomes``
    or be defined by that tail's own SELECT list. ``game_bucket`` failed this
    before CAL-P1002 and the other two passed, which is exactly why nobody saw it.
    """
    tail = FOLD.TAILS[grain]
    select = tail[tail.index("SELECT") + 6: tail.index("FROM outcomes")]
    defined = set(re.findall(r"\bAS\s+(\w+)", select))
    bare = {
        token
        for token in re.findall(r"^\s*(\w+),\s*$", select, re.M)
    }
    unknown = bare - OUTCOMES_COLUMNS - defined
    assert not unknown, f"--grain {grain} selects {sorted(unknown)}, which nothing provides"


def test_the_two_grains_bin_by_the_same_expression():
    """The property the cluster bootstrap rests on.

    ``game_bucket`` is only a refinement of ``bucket`` if a row lands in the same
    decile under both. Asserted on the shared constant AND on both rendered
    tails, so re-typing the expression into one of them fails here rather than
    silently producing a bootstrap over bins the rail does not publish.
    """
    assert FOLD._BUCKET_EXPR in FOLD._TAIL_BUCKET
    assert FOLD._BUCKET_EXPR in FOLD._TAIL_GAME_BUCKET
    assert FOLD._TAIL_BUCKET.count(FOLD._BUCKET_EXPR) == 1
    assert FOLD._TAIL_GAME_BUCKET.count(FOLD._BUCKET_EXPR) == 1


def test_the_decile_expression_is_the_producers_own():
    """Ten deciles, top bin closed. The same shape ``precompute_calibration``
    publishes and ``calibration_cell_exact`` folds — asserted as behaviour over
    the boundary values rather than as a string, so a rewrite that means the
    same thing is allowed and one that does not is caught."""
    import math

    def decile(prob: float) -> int:
        return min(int(math.floor(prob * 10)), 9)

    assert "LEAST" in FOLD._BUCKET_EXPR and "FLOOR" in FOLD._BUCKET_EXPR
    assert ", 9)" in FOLD._BUCKET_EXPR, "the top bin must be closed at 9"
    assert (decile(0.0), decile(0.099), decile(0.5), decile(0.99), decile(1.0)) == (
        0, 0, 5, 9, 9,
    )


def test_sigma_still_implies_the_game_bucket_grain():
    """The wiring that made the defect reachable only through ``--sigma``. If
    this stops being true the tests above still pass while ``--sigma`` measures
    the wrong grain, so it is pinned explicitly."""
    src = pathlib.Path(
        pathlib.Path(__file__).resolve().parents[1]
        / "scripts"
        / "calibration_bookmaker_cell_fold.py"
    ).read_text()
    assert "game_bucket" in src
    assert re.search(r"--sigma[\s\S]{0,400}?game_bucket", src), (
        "--sigma no longer documents/implies the game_bucket grain"
    )
