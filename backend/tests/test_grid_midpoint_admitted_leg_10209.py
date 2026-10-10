"""#10209 — one leg with a bid/ask but no stored price 500'd a whole playoff grid.

WHAT A READER SAW: Sentry BAINLUCK-1HG, 2026-10-02 03:00:24Z, ``GET
/api/playoffs/nhl`` → 500, ``TypeError: float() argument must be a string or a
real number, not 'NoneType'``. Not one blank cell — the whole NHL page.

THE CAUSE: ``get_playoff_grid`` admits a leg on ``current_probability`` or, when
that column is NULL, on the bid/ask midpoint. ~200 lines later the cell builder
re-read the NULL column and called ``float()`` on it. #7387 guarded the GRADED
leg (a terminal cell carries no number) and its comment named the ungraded leg
as a known neighbour it left alone. This file is that neighbour.

THE FIX: ``_grid_admitted_price`` is the one definition of "the price this leg
was admitted on", read at both sites, so the cell publishes the number every
filter in the admission loop already judged it on.
"""

import ast
import inspect

import pytest

from app.routes import playoffs as playoffs_mod
from app.routes.playoffs import _grid_admitted_price


@pytest.mark.parametrize(
    "current, bid, ask, expected, why",
    [
        (0.42, 0.40, 0.44, 0.42, "a stored price wins over the book"),
        (0.0, 0.40, 0.44, 0.0, "a stored 0.0 is a price, not an absence"),
        (None, 0.40, 0.44, 0.42, "BAINLUCK-1HG's shape: no stored price, a two-sided book"),
        (None, 0.0, 0.06, 0.03, "a zero bid is still a bid"),
        (None, None, 0.44, None, "ask-only: nothing to admit on"),
        (None, 0.40, None, None, "bid-only: nothing to admit on"),
        (None, 0.0, 0.0, None, "an empty book is not a 0% price"),
        (None, None, None, None, "no price at all"),
    ],
)
def test_the_admitted_price(current, bid, ask, expected, why):
    got = _grid_admitted_price(
        current, bid, ask, price_changed_at=None, book_updated_at=None
    )
    if expected is None:
        assert got is None, why
    else:
        assert got == pytest.approx(expected), why


def test_decimal_columns_come_back_as_floats():
    """The ORM hands ``Numeric`` columns over as ``Decimal``; the cell's number
    is JSON-serialised and compared against floats downstream."""
    from decimal import Decimal

    got = _grid_admitted_price(
        None, Decimal("0.40"), Decimal("0.44"), price_changed_at=None, book_updated_at=None
    )
    assert isinstance(got, float)
    assert got == pytest.approx(0.42)


def _grid_function():
    tree = ast.parse(inspect.getsource(playoffs_mod))
    return next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "get_playoff_grid"
    )


def _names_current_probability(node) -> bool:
    return any(
        isinstance(n, ast.Attribute) and n.attr == "current_probability"
        for n in ast.walk(node)
    )


def _none_checks_current_probability(node) -> bool:
    """``<x>.current_probability is [not] None`` somewhere inside ``node``, or
    the bare column as a truthiness test (the debug block's form)."""
    if isinstance(node, ast.Attribute) and node.attr == "current_probability":
        return True
    return any(
        isinstance(n, ast.Compare)
        and any(isinstance(op, (ast.Is, ast.IsNot)) for op in n.ops)
        and any(isinstance(c, ast.Constant) and c.value is None for c in n.comparators)
        and _names_current_probability(n.left)
        for n in ast.walk(node)
    )


def test_the_grid_never_floats_an_unchecked_stored_price():
    """🔴 THE WIRING GUARD. The helper's own arms would all stay green if the
    cell builder went back to ``float(outcome.current_probability)`` — which is
    exactly the line that 500'd. So: every ``float()`` of a stored price inside
    ``get_playoff_grid`` must sit in a conditional expression or short-circuit
    that None-checks that price first. Anything else is BAINLUCK-1HG again.

    (Also catches the pre-fix laundered form, ``_raw_p = outcome.current_probability``
    then ``float(_raw_p)``, by refusing any ``float(<Name>)`` whose Name was
    bound straight from the column.)
    """
    fn = _grid_function()

    parents = {}
    for parent in ast.walk(fn):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    laundered = {
        t.id
        for n in ast.walk(fn)
        if isinstance(n, ast.Assign)
        and isinstance(n.value, ast.Attribute)
        and n.value.attr == "current_probability"
        for t in n.targets
        if isinstance(t, ast.Name)
    }

    floats = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "float"
        and len(n.args) == 1
    ]
    stored = [
        c for c in floats
        if (isinstance(c.args[0], ast.Attribute) and c.args[0].attr == "current_probability")
        or (isinstance(c.args[0], ast.Name) and c.args[0].id in laundered)
    ]
    assert stored, "no float() of a stored price left — re-point this guard"

    for call in stored:
        if isinstance(call.args[0], ast.Name):
            pytest.fail(
                f"line {call.lineno}: float({call.args[0].id}) of a name bound from "
                "current_probability — the #10209 shape; read _grid_admitted_price"
            )
        node, guarded = call, False
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.IfExp, ast.BoolOp, ast.If)):
                test = node.test if isinstance(node, (ast.IfExp, ast.If)) else node
                if _none_checks_current_probability(test):
                    guarded = True
                    break
        assert guarded, (
            f"line {call.lineno}: float() of current_probability with no None check — "
            "a leg admitted on its bid/ask midpoint 500s the whole grid (#10209)"
        )


def test_both_sites_read_the_one_definition():
    """Admission and the cell builder must agree on a leg's price. Two copies of
    the midpoint formula is how they drifted apart in the first place."""
    fn = _grid_function()
    calls = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_grid_admitted_price"
    ]
    assert len(calls) >= 2, (
        f"_grid_admitted_price is read {len(calls)}x in get_playoff_grid; the "
        "admission loop and the cell builder must both read it"
    )
