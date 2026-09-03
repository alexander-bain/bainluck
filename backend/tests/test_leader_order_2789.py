"""UX-P276 / #2789 — the pure ordering rule.

`tests/integration/test_route_grouped_feed_leader_order_2789.py` proves the
route ships leader-first rows; this file proves the RULE, including the cases
the route's own data does not currently exhibit (ties, unreadable values, the
ORM accessor). Both are kept: the route test is the ship, this one is what a
second call site can be pointed at.
"""

from decimal import Decimal

import pytest

from app.utils.leader_order import leader_first_outcomes


def _d(name, probability):
    return {"name": name, "probability": probability}


def _names(rows):
    return [r["name"] for r in rows]


# --------------------------------------------------------------------------
# the rule
# --------------------------------------------------------------------------


def test_the_highest_probability_leads():
    rows = [_d("a", 0.01), _d("b", 0.9), _d("c", 0.3)]
    assert _names(leader_first_outcomes(rows)) == ["b", "c", "a"]


def test_the_reported_card_orders_correctly():
    """The five rows production shipped for `Omega European Masters - Winner`."""
    rows = [
        _d("Yannik Paul", 0.000863),
        _d("Felix Mory", 0.000496),
        _d("Marco Penge", 0.007235),
        _d("Todd Clements", 0.038777),
        _d("Richard Sterne", 0.000174),
    ]
    assert _names(leader_first_outcomes(rows))[0] == "Todd Clements"


def test_ties_keep_their_incoming_order():
    """Stability is load-bearing: an upstream tie-break must survive.

    `sorted(..., reverse=True)` would REVERSE equal rows. The implementation
    negates the probability and leaves the index ascending precisely so this
    holds — so this test is what distinguishes the two.
    """
    rows = [_d("first", 0.5), _d("second", 0.5), _d("third", 0.5)]
    assert _names(leader_first_outcomes(rows)) == ["first", "second", "third"]


def test_an_unpriced_row_sorts_after_a_genuine_zero():
    """None is an absence of a quote; 0.0 is a quote. They must not tie.

    `key=lambda o: o["probability"] or 0` — the obvious spelling, and the one
    the sibling call site in `routes/futures.py` uses — collapses these two.
    """
    rows = [_d("unpriced", None), _d("priced_zero", 0.0)]
    assert _names(leader_first_outcomes(rows)) == ["priced_zero", "unpriced"]


def test_several_unpriced_rows_keep_their_incoming_order():
    rows = [_d("x", None), _d("leader", 0.4), _d("y", None)]
    assert _names(leader_first_outcomes(rows)) == ["leader", "x", "y"]


def test_a_decimal_probability_orders_as_a_number():
    """The column is `Numeric`, so an unconverted row arrives as `Decimal`."""
    rows = [_d("small", Decimal("0.01")), _d("big", Decimal("0.90"))]
    assert _names(leader_first_outcomes(rows)) == ["big", "small"]


def test_a_string_probability_orders_as_a_number():
    """#2554 served these as JSON strings from the cache for weeks.

    The two defects are independent and this one must not depend on that one
    being fixed first — `"0.9" > "0.10"` lexically but 0.9 > 0.10 numerically,
    and either way a string must never sort as "unpriced".
    """
    rows = [_d("small", "0.10"), _d("big", "0.9")]
    assert _names(leader_first_outcomes(rows)) == ["big", "small"]


def test_an_unreadable_probability_sorts_last_rather_than_raising():
    """A value we cannot parse is not evidence that this row leads."""
    rows = [_d("junk", "not a number"), _d("real", 0.2)]
    assert _names(leader_first_outcomes(rows)) == ["real", "junk"]


def test_an_orm_row_is_read_through_its_current_probability_column():
    """The route holds ORM rows whose column is `current_probability`.

    Reading only a `probability` key would silently sort every ORM row equal —
    which is the bug, wearing the fix's clothes.
    """
    from app.models import FuturesOutcome

    rows = [
        FuturesOutcome(id=1, name="low", current_probability=0.1),
        FuturesOutcome(id=2, name="high", current_probability=0.8),
    ]
    assert [r.name for r in leader_first_outcomes(rows)] == ["high", "low"]


# --------------------------------------------------------------------------
# CONTROLS — each verified GREEN on the parent commit as well as on the fix.
# (On the parent the module does not exist, so these run against the shipped
# helper only; they are controls in the sense that they pin behaviour the fix
# must NOT change about the data, not behaviour master already had.)
# --------------------------------------------------------------------------


def test_the_row_set_is_never_changed():
    rows = [_d("a", 0.1), _d("b", None), _d("c", 0.9)]
    out = leader_first_outcomes(rows)
    assert len(out) == len(rows)
    assert {id(r) for r in out} == {id(r) for r in rows}


def test_the_input_is_never_mutated():
    rows = [_d("a", 0.1), _d("b", 0.9)]
    before = list(rows)
    leader_first_outcomes(rows)
    assert rows == before
    assert _names(rows) == ["a", "b"]


def test_it_is_idempotent():
    """Safety argument for applying it at a shared renderer: a second pass over
    an already-ordered list changes nothing, so the three `FuturesCard` callers
    whose upstream already sorts are unaffected."""
    rows = [_d("a", 0.1), _d("b", None), _d("c", 0.9), _d("d", 0.9)]
    once = leader_first_outcomes(rows)
    assert leader_first_outcomes(once) == once


@pytest.mark.parametrize("rows", [[], [_d("only", 0.5)], [_d("only", None)]])
def test_degenerate_inputs_are_returned_intact(rows):
    assert leader_first_outcomes(rows) == rows
