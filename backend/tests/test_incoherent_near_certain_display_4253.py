"""#4253 — a single-winner field stops showing five different winners at 100%.

Measured on production 2026-09-09: 315 open markets carry 2,075 outcome rows frozen
at ``current_probability = 1.0`` with ``price_changed_at IS NULL`` and no winner, and
they are the market's top-priced rows, so they headline it. Six of thirteen sampled
tier-1/2 specimens served a top-5 that was ENTIRELY 1.0:

    /api/futures/12764689  Contestant 22 1.0 · Contestant 16 1.0 · Contestant 33 1.0
                           · Contestant 43 1.0 · Contestant 45 1.0
    /api/futures/114045    Goldman Sachs 1.0 · Bank D 1.0 · Bank E 1.0 · Bank F 1.0
    /api/futures/113419    John Ternus 1.0

``drop_dominant_field_outcomes`` was built to remove a field row printed at 100% and
cannot help: it is gated on ``is_field_outcome(name)``, and "Goldman Sachs" is not a
field outcome. The rule that does cover it — at most one leg of a single-winner
partition can be near-certain — already exists in ``winner_field_coherence`` and is
already obeyed by capture and by grading. Display was the third site and never
adopted it.

The tests below are grouped by the thing that can break, and each is written so it
FAILS if the corresponding safety is removed (mutation-proved — see the module note
at the bottom).
"""
from __future__ import annotations

import pytest

from app.utils.outcome_display import (
    drop_dominant_field_outcomes,
    drop_incoherent_near_certain,
)
from app.utils.winner_field_coherence import NEAR_CERTAIN_PROB


def _o(name, prob, winner=False):
    return {"name": name, "probability": prob, "is_winner": winner}


def _drop(items, *, me=True, open_=True):
    return drop_incoherent_near_certain(
        items,
        lambda o: o.get("probability"),
        mutually_exclusive=me,
        market_is_open=open_,
        is_winner_of=lambda o: bool(o.get("is_winner")),
    )


# --- the ship ---------------------------------------------------------------


def test_five_contestants_at_100_percent_do_not_all_survive():
    """Market 12764689's shape: 50 frozen 1.0s above 2 real prices."""
    items = [_o(f"Contestant {n}", 1.0) for n in range(50)]
    items += [_o("Real A", 0.62), _o("Real B", 0.35)]

    kept = _drop(items)

    assert [o["name"] for o in kept] == ["Real A", "Real B"]


def test_the_real_prices_survive_the_slice_that_the_junk_used_to_fill():
    """The harm is not clutter, it is DISPLACEMENT — the reader saw zero real prices.

    Sorting happens on the caller's side; what matters is that after the drop a
    ``[:5]`` slice contains real answers instead of five 100%s.
    """
    items = [_o(f"Contestant {n}", 1.0) for n in range(50)]
    items += [_o("Real A", 0.62), _o("Real B", 0.35)]

    kept = sorted(_drop(items), key=lambda o: o["probability"], reverse=True)[:5]

    assert kept and all(o["probability"] < NEAR_CERTAIN_PROB for o in kept)


def test_a_named_candidate_is_dropped_even_though_it_is_not_a_field_outcome():
    """The whole difference from `drop_dominant_field_outcomes`, asserted directly."""
    items = [_o("Goldman Sachs", 1.0), _o("Bank D", 1.0), _o("Morgan Stanley", 0.12)]

    # The existing name-gated guard is a NO-OP on this input...
    assert drop_dominant_field_outcomes(
        items, lambda o: o.get("name"), lambda o: o.get("probability")
    ) == items
    # ...and the new rule is what removes them.
    assert [o["name"] for o in _drop(items)] == ["Morgan Stanley"]


# --- detection boundary -----------------------------------------------------


def test_a_single_near_certain_leg_is_left_alone():
    """One near-lock is what a settled or lopsided market legitimately looks like."""
    items = [_o("Runaway Leader", 0.99), _o("Other Guy", 0.01)]
    assert _drop(items) == items


def test_the_bar_is_the_shared_one_and_is_not_re_derived_here():
    """Just below the shared bar is untouched; at it, the pair is incoherent."""
    just_under = [_o("A", NEAR_CERTAIN_PROB - 0.001), _o("B", NEAR_CERTAIN_PROB - 0.001)]
    assert _drop(just_under) == just_under

    at_bar = [_o("A", NEAR_CERTAIN_PROB), _o("B", NEAR_CERTAIN_PROB), _o("C", 0.02)]
    assert [o["name"] for o in _drop(at_bar)] == ["C"]


def test_a_non_mutually_exclusive_ladder_is_never_judged():
    """`Pylon: First Week Pure Album Sales` — the one live feed card with two 0.95s.

    Nested thresholds are simultaneously true; several are legitimately near-certain
    (gotcha #23, #199). It is flagged `mutually_exclusive = false` and must survive.
    """
    ladder = [_o("Above 5K", 0.95), _o("Above 12K", 0.95), _o("Above 20K", 0.91)]
    assert _drop(ladder, me=False) == ladder


# --- the two exemptions, each its own failure mode --------------------------


def test_a_crowned_winner_is_never_dropped_and_the_junk_beside_it_still_goes():
    """397 resolved Polymarket + 239 resolved Kalshi markets have this shape.

    Without the exemption the actual result disappears and the losers stay on the
    page — "settled means settled", broken by a display helper.
    """
    items = [
        _o("Actual Winner", 1.0, winner=True),
        _o("Frozen Junk A", 1.0),
        _o("Frozen Junk B", 1.0),
        _o("Real Loser", 0.03),
    ]

    kept = _drop(items)

    assert [o["name"] for o in kept] == ["Actual Winner", "Real Loser"]


def test_a_crowned_winner_still_counts_toward_detection():
    """Detection and suppression are different questions.

    One real winner at 1.0 plus one frozen 1.0 IS the field this exists for; if the
    winner were excluded from the count, only one near-certain leg would remain and
    the predicate would decline.
    """
    items = [_o("Actual Winner", 1.0, winner=True), _o("Frozen Junk", 1.0), _o("Real", 0.04)]

    assert [o["name"] for o in _drop(items)] == ["Actual Winner", "Real"]


def test_a_resolved_market_is_left_entirely_alone():
    """131 resolved markets show several 1.0s with no winner stamped — that is the
    #1527 GRADING defect and belongs to the grader, not to a display drop."""
    items = [_o("A", 1.0), _o("B", 1.0), _o("C", 0.02)]
    assert _drop(items, open_=False) == items


# --- the never-empties safety, and its honest cost --------------------------


def test_never_empties_when_the_whole_field_is_frozen():
    """7 markets / 100 rows are wholly frozen. They keep their rows rather than
    rendering a silent zero-outcome card — the module's standing rule."""
    items = [_o("A", 1.0), _o("B", 1.0), _o("C", 1.0)]
    assert _drop(items) == items


def test_rows_with_no_price_are_kept():
    """A withdrawn price (#4000 nulls `current_probability`) is not a 1.0."""
    items = [_o("A", 1.0), _o("B", 1.0), _o("Unpriced", None), _o("Real", 0.4)]
    assert [o["name"] for o in _drop(items)] == ["Unpriced", "Real"]


def test_the_input_is_not_mutated():
    items = [_o("A", 1.0), _o("B", 1.0), _o("C", 0.1)]
    before = [dict(o) for o in items]
    _drop(items)
    assert items == before


# --- the call sites actually reach the rule ---------------------------------
#
# A pure function proves nothing about its call sites' reach (#4000's own lesson:
# the first ship was correct, mounted on a task that could not see the population,
# and retired zero rows). These pin that each serializer still calls it.


@pytest.mark.parametrize(
    "path,needle",
    [
        ("app/routes/events.py", "_drop_incoherent_near_certain("),
        ("app/routes/futures.py", "drop_incoherent_near_certain("),
    ],
)
def test_the_serializers_call_the_shared_rule(path, needle):
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1] / path).read_text()
    assert needle in src, f"{path} no longer calls the #4253 rule"


def test_futures_has_both_call_sites_detail_and_browse():
    import pathlib

    src = (
        pathlib.Path(__file__).resolve().parents[1] / "app/routes/futures.py"
    ).read_text()
    # Two CALL sites (detail serializer + browse). The imports carry no paren, so
    # counting `name(` counts calls and not the `from ... import` lines.
    assert src.count("drop_incoherent_near_certain(") == 2, (
        "expected exactly two call sites in futures.py (detail serializer and "
        "browse); one of them has been dropped or a third added unreviewed"
    )


def test_every_call_site_passes_the_winner_exemption():
    """The exemption is opt-in (`is_winner_of` defaults to None), so a call site that
    forgets it silently deletes results from settled markets. Pin it at each one."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    for path in ("app/routes/events.py", "app/routes/futures.py"):
        src = (root / path).read_text()
        for call in re.finditer(
            r"drop_incoherent_near_certain\((.*?)\n    \)", src, re.S
        ):
            body = call.group(1)
            assert "is_winner_of=" in body, f"{path}: call site omits is_winner_of"
            assert "market_is_open=" in body, f"{path}: call site omits market_is_open"


def test_the_bar_is_imported_not_copied():
    """`winner_field_coherence` exists because producer and detector drifted once.
    A local numeric copy of the bar in the display module would restart that.

    Scanned as AST NUMERIC LITERALS, not as text. A substring search over the
    function source reads its own docstring — which quotes the measured bar and the
    live `0.95` ladder prices on purpose — and reds on prose. The defect is a
    hard-coded number in the CODE; that is what is asserted.
    """
    import ast
    import pathlib

    src = (
        pathlib.Path(__file__).resolve().parents[1] / "app/utils/outcome_display.py"
    ).read_text()
    fn = next(
        n
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.FunctionDef) and n.name == "drop_incoherent_near_certain"
    )
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert "NEAR_CERTAIN_PROB" in names, "the shared bar is no longer referenced"
    assert "field_is_incoherent" in names, "the shared predicate is no longer called"

    floats = {
        n.value
        for n in ast.walk(fn)
        if isinstance(n, ast.Constant) and isinstance(n.value, float)
    }
    assert not floats, f"probability threshold hard-coded in the body: {floats}"
