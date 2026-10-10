"""#10839 — the grid revived a Polymarket price the socket had WITHDRAWN.

WHAT A READER SAW: ``/playoffs/wnba`` 2026-10-10 11:33Z, Champion column, Las
Vegas Aces **4.8%** (P8.7 · K0.9). The Aces were swept 3-0 in the semifinal,
final 04:01Z. ``/api/futures/9413479`` served the same Polymarket leg as null.

THE CAUSE: ``polymarket_ws.withdraw_book_refuted_prices`` (#9934) set the leg's
``current_probability`` to NULL at 08:22:35Z, moving ``price_changed_at`` and —
by design — not ``last_updated``, and leaving the stored bid/ask (0.09/0.10,
``last_updated`` 2026-10-09 22:50:58Z, before Game 3 tipped). The grid's
#10209 fallback reads a NULL price as "never written" and admits the bid/ask
midpoint, so the pre-elimination 0.095 came back.

THE FIX: ``_grid_admitted_price`` refuses the midpoint when the price's last
change is no older than the stored book — the book the withdrawn price came
from. A price that was never written (no ``price_changed_at``) still falls back,
which is the case #10209 exists for.
"""

import ast
import inspect
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.routes import playoffs as playoffs_mod
from app.routes.playoffs import _grid_admitted_price

#: The specimen's stored stamps (db-query 2026-10-10 ~11:3xZ, outcome 51753355).
WITHDRAWN_AT = datetime(2026, 10, 10, 8, 22, 35, tzinfo=timezone.utc)
BOOK_AT = datetime(2026, 10, 9, 22, 50, 58, tzinfo=timezone.utc)


def test_the_specimen_is_not_admitted():
    """Outcome 51753355 as stored: NULL price, 0.09/0.10 book from before the
    deciding game, withdrawn ten hours after it."""
    got = _grid_admitted_price(
        None,
        Decimal("0.0900"),
        Decimal("0.1000"),
        price_changed_at=WITHDRAWN_AT,
        book_updated_at=BOOK_AT,
    )
    assert got is None


@pytest.mark.parametrize(
    "current, changed_at, book_at, expected, why",
    [
        (None, None, BOOK_AT, 0.095,
         "never written (no price_changed_at): #10209's migration case still falls back"),
        (None, None, None, 0.095,
         "never written and never stamped: still the #10209 fallback"),
        (None, WITHDRAWN_AT, None, None,
         "withdrawn, and nothing says when the book is from: refuse"),
        (None, WITHDRAWN_AT, WITHDRAWN_AT, None,
         "price cleared in the same write as the book (the poller itself declined "
         "this book): the book is not fresher than the refusal"),
        (None, WITHDRAWN_AT, WITHDRAWN_AT + timedelta(seconds=1), 0.095,
         "a book stored AFTER the withdrawal is not the refuted one"),
        (0.03, WITHDRAWN_AT, BOOK_AT, 0.03,
         "a stored price is served as stored whatever its stamps say"),
        (0.0, WITHDRAWN_AT, BOOK_AT, 0.0,
         "a stored 0.0 is a price, not an absence"),
    ],
)
def test_the_withdrawal_rule(current, changed_at, book_at, expected, why):
    got = _grid_admitted_price(
        current, 0.09, 0.10, price_changed_at=changed_at, book_updated_at=book_at
    )
    if expected is None:
        assert got is None, why
    else:
        assert got == pytest.approx(expected), why


def test_the_stamps_cannot_be_omitted():
    """Keyword-only and required: a call site that forgets them raises at the
    first grid build instead of silently reviving withdrawn prices."""
    with pytest.raises(TypeError):
        _grid_admitted_price(None, 0.09, 0.10)  # type: ignore[call-arg]


def _grid_function():
    tree = ast.parse(inspect.getsource(playoffs_mod))
    return next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "get_playoff_grid"
    )


def test_every_grid_site_passes_the_outcomes_own_stamps():
    """🔴 THE WIRING GUARD. The rule's arms all stay green if a call site passes
    ``price_changed_at=None`` — which is the pre-fix behaviour exactly. So each
    ``_grid_admitted_price`` call in ``get_playoff_grid`` must pass the OUTCOME's
    ``price_changed_at`` and its ``last_updated`` (the column every PM book write
    stamps beside the bid/ask)."""
    calls = [
        n for n in ast.walk(_grid_function())
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_grid_admitted_price"
    ]
    assert len(calls) >= 2, "admission loop and cell builder must both read the helper"
    for call in calls:
        kw = {k.arg: k.value for k in call.keywords}
        for arg, attr in (
            ("price_changed_at", "price_changed_at"),
            ("book_updated_at", "last_updated"),
        ):
            value = kw.get(arg)
            assert isinstance(value, ast.Attribute) and value.attr == attr, (
                f"line {call.lineno}: {arg}= must be <outcome>.{attr} — anything "
                "else serves a withdrawn price's stale midpoint (#10839)"
            )
