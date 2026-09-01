"""Every surface that ranks outcomes drops the duplicate leg — proved by RUNNING it.

The defect: a Polymarket parent market can hold both the bare rung for a
condition and that same condition's ``_yes``/``_no`` legs. The legs carry the
sub-market's own price, so a 64.5% "No" outranks every real answer and wins the
leader pick. Measured on production 2026-08-31: 1,455 affected markets, 2,910
duplicate rows, **188 of the 346 open ones currently crowning a leg**.

Six call sites read outcomes for display, across three modules. Enumerating
them is the whole job — gotcha #43 read the other way round: when you add a
filter, enumerate the SURFACES, not the code paths you happened to be editing.
Two of the six live inside route bodies too large to call here; those get an
AST guard anchored on their OWN function, so a sibling call in the same module
cannot satisfy it (a plain ``"drop_duplicate_legs" in source`` check would be
satisfied by any one of the other five).
"""

from __future__ import annotations

import ast
import inspect
from types import SimpleNamespace

import pytest

# The real bridesmaids rows (futures_markets 12194657). `Zoë Kravitz` and the
# two legs are one condition; the legs outrank all ten people.
_ZOE = "0xeda9eb14a054e234a72ab94dc45a6302ca702a6a8e5e7c270e7c91628ac8e084"


def _outcome(oid, name, external_id, prob):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=external_id,
        current_probability=prob,
        probability_change_24h=None,
        rank=None,
        rank_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        current_american_odds=None,
        is_winner=False,
        last_updated=None,
    )


def _contaminated_market():
    return SimpleNamespace(
        id=12194657,
        name="Who will Taylor Swift's bridesmaids be?",
        mutually_exclusive=False,
        outcomes=[
            _outcome(84318324, "No", f"{_ZOE}_no", 0.645),
            _outcome(84318323, "Yes", f"{_ZOE}_yes", 0.355),
            _outcome(69789474, "Gigi Hadid", "0xdc73650886" + "a" * 54, 0.0035),
            _outcome(69789475, "Zoë Kravitz", _ZOE, 0.0005),
            _outcome(69789473, "Selena Gomez", "0x5f731ad954" + "b" * 54, 0.0005),
        ],
    )


def _clean_market():
    """The same market with the legs already absent — the control.

    Every assertion below must hold here too, or it is measuring the fixture
    rather than the filter.
    """
    m = _contaminated_market()
    m.outcomes = [o for o in m.outcomes if not o.external_id.endswith(("_yes", "_no"))]
    return m


# ── surfaces that can be executed directly ────────────────────────────────────


@pytest.mark.parametrize("lean", [True, False])
def test_search_does_not_offer_the_leg_and_crowns_a_person(lean):
    from app.routes.events import _build_search_top_outcomes

    out = _build_search_top_outcomes(_contaminated_market(), limit=5, lean=lean)
    names = [o["name"] for o in out]
    assert "No" not in names and "Yes" not in names
    assert names[0] == "Gigi Hadid", f"search headlined {names[0]!r}"
    assert "Zoë Kravitz" in names


@pytest.mark.parametrize("lean", [True, False])
def test_search_is_unchanged_on_a_market_that_never_had_a_leg(lean):
    from app.routes.events import _build_search_top_outcomes

    assert _build_search_top_outcomes(
        _contaminated_market(), limit=5, lean=lean
    ) == _build_search_top_outcomes(_clean_market(), limit=5, lean=lean)


def test_the_feed_trace_does_not_show_a_row_the_card_no_longer_serves():
    from app.routes.feed import _top_outcomes_for_trace

    outcomes_data, leader_name, leader_prob = _top_outcomes_for_trace(
        _contaminated_market()
    )
    names = [o["name"] for o in outcomes_data]
    assert "No" not in names and "Yes" not in names
    assert leader_name == "Gigi Hadid"
    assert leader_prob == pytest.approx(0.0035)


def test_the_feed_trace_is_unchanged_on_a_clean_market():
    from app.routes.feed import _top_outcomes_for_trace

    assert _top_outcomes_for_trace(_contaminated_market()) == _top_outcomes_for_trace(
        _clean_market()
    )


def test_a_correctly_decomposed_sub_market_still_serves_both_its_legs():
    """The legs are only wrong BESIDE the rung they duplicate.

    On the sub-market that owns them there is no bare twin, and dropping them
    would serve an empty market. This is the assertion that stops the rule
    degenerating into "delete every Yes/No".
    """
    from app.routes.events import _build_search_top_outcomes

    sub = SimpleNamespace(
        id=13798072,
        name="Will Zoë Kravitz be one of Taylor Swift's bridesmaids?",
        mutually_exclusive=True,
        outcomes=[
            _outcome(125653873, "Yes", f"{_ZOE}_yes", 0.0005),
            _outcome(125653874, "No", f"{_ZOE}_no", 0.9995),
        ],
    )
    names = [o["name"] for o in _build_search_top_outcomes(sub, limit=5)]
    assert sorted(names) == ["No", "Yes"]


# ── the two sites inside route bodies too large to call here ──────────────────

_AST_GUARDED = [
    ("app.routes.feed", "_top_outcomes_for_trace"),
    ("app.routes.events", "_build_search_top_outcomes"),
    ("app.routes.futures", "_format_market_detail"),
]


def _calls_in(module_name: str, func_name: str) -> set[str]:
    import importlib
    import textwrap

    mod = importlib.import_module(module_name)
    # `textwrap.dedent`, not `inspect.cleandoc` — cleandoc leaves the `def` line
    # flush and re-indents the body, which is an IndentationError for any
    # function whose first statement is a docstring.
    tree = ast.parse(textwrap.dedent(inspect.getsource(getattr(mod, func_name))))
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


@pytest.mark.parametrize("module_name,func_name", _AST_GUARDED)
def test_the_surface_calls_the_filter_in_its_own_body(module_name, func_name):
    """Anchored on the AST Call inside THIS function.

    A substring check against the module would be satisfied by any of the other
    five call sites; walking only this function's own tree cannot be. The alias
    is accepted because `events.py` imports the whole shared display module
    under `_`-prefixed names and matching only the bare one would fail there for
    a naming reason rather than a behavioural one.
    """
    calls = _calls_in(module_name, func_name)
    assert calls & {"drop_duplicate_legs", "_drop_duplicate_legs"}, (
        f"{module_name}.{func_name} no longer drops duplicate legs — a market "
        "holding both a rung and its _yes/_no twin will crown the twin"
    )


def test_every_feed_site_that_sorts_market_outcomes_drops_legs_first():
    """The two large route bodies, by AST, without naming their enclosing function.

    Finds every ``sorted(...)`` whose first argument mentions ``market.outcomes``
    and asserts that argument also runs it through the filter. This is the guard
    that catches a SEVENTH site being added later: a new
    ``sorted(market.outcomes, ...)`` anywhere in the feed fails it.
    """
    import app.routes.feed as feed

    tree = ast.parse(inspect.getsource(feed))
    offenders = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != "sorted" or not node.args:
            continue
        arg_src = ast.dump(node.args[0])
        if "'outcomes'" not in arg_src:
            continue
        if "drop_duplicate_legs" not in arg_src:
            offenders.append(getattr(node, "lineno", "?"))
    assert not offenders, (
        f"feed.py sorts market outcomes without dropping duplicate legs at "
        f"line(s) {offenders} — that sort feeds a leader pick"
    )
