"""#4229 — the parts of the Kalshi senate backfill that need no database.

The write itself is guarded by
`tests/integration/test_repair_kalshi_senate_category_4229_real_postgres.py`,
which only ever runs in CI's `search-recall` job. **These run everywhere**, and
they cover the two things that rot without a server's help:

1. **the rail must not become a second classifier.** This is how the Polymarket
   sibling's Q495 guard is written, and for the same reason: the realistic
   decay is somebody adding "just one" sport keyword here, after which the
   repair and the poller quietly disagree and nothing notices.
2. **the id list must stay a bound**, i.e. remain enumerated and small. A
   predicate smuggled in where the list is would sweep the 133 resolved
   Belleville/Ottawa rows whose names also match `senat*`.
"""

from __future__ import annotations

import inspect

import pytest

from app.tasks import repair_kalshi_senate_category as rail


#: Every sport token that could plausibly be smuggled into this module. If one
#: appears in the CODE, the rail has grown an opinion of its own.
_SPORT_TOKENS = (
    "hockey",
    "nhl",
    "ahl",
    "ottawa",
    "belleville",
    "basketball",
    "baseball",
    "football",
    "soccer",
    "tennis",
    "golf",
    "senator",
    "senate",
)


def _parsed():
    """The module's AST, with every docstring removed.

    🔴 Docstrings and comments are excluded because this file's whole subject is
    discussed in prose there — `senators`, `hockey`, `Ottawa` and `Belleville`
    all appear in the module docstring by necessity, and a naive substring scan
    over raw source fails on its own explanation.

    Uses `ast` rather than a regex: a regex that strips `#` to end-of-line also
    eats a `#` inside a string literal, which is exactly the trap that makes
    source-scan guards read as passing while scanning the wrong text.
    """
    import ast

    source = inspect.getsource(rail)
    assert source.strip(), "getsource returned nothing — the scan would be vacuous"

    tree = ast.parse(source)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body.pop(0)
    return tree


def _decision_strings() -> list[str]:
    """Every string LITERAL the code evaluates, docstrings excluded.

    Literals rather than identifiers, deliberately. `SENATE_ROW_IDS` is a
    perfectly good name for an enumerated bound and says nothing about how a
    row is judged; what would make this rail a second classifier is a *value*
    it compares against or matches on. Scanning identifiers instead flagged the
    constant's own name and would have forced a worse name to satisfy a test.
    """
    import ast

    return [
        n.value
        for n in ast.walk(_parsed())
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def test_repair_carries_no_sport_rules_of_its_own():
    """The rail asks the shipped classifier; it never decides a sport itself."""
    haystack = " ".join(_decision_strings()).lower()
    found = sorted(t for t in _SPORT_TOKENS if t in haystack)
    assert not found, (
        f"{found} appear as string literals in "
        "`repair_kalshi_senate_category`. This rail must ask "
        "`_categorize_kalshi_market` and nothing else — a sport keyword here is "
        "a second classifier that will drift from the poller silently."
    )


def test_the_rail_does_not_regex_market_names():
    """A second classifier needs pattern matching; deny it the import.

    Complements the literal scan: a rule could be assembled from fragments no
    single literal reveals, but it still needs `re` to apply it.
    """
    import ast

    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(_parsed())
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(_parsed())
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "re" not in imported, (
        "`repair_kalshi_senate_category` imports `re`. Matching a market name "
        "here is the second-classifier failure this module exists to avoid."
    )


def test_the_rail_actually_calls_the_shipped_classifier():
    """The complement of the scan above: absence of rules is not presence of a call.

    A module with no sport keywords and no classifier call would pass
    `test_repair_carries_no_sport_rules_of_its_own` while relabelling blindly.
    """
    import ast

    called = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(_parsed())
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert "_categorize_kalshi_market" in called, (
        "the repair no longer CALLS the shipped Kalshi classifier, so nothing "
        "gates its id list. (Asserted on the call graph, not a substring: an "
        "import or a mention in a comment is not a call.)"
    )


def test_the_id_list_is_an_enumerated_bound():
    ids = rail.SENATE_ROW_IDS
    assert isinstance(ids, tuple), "a mutable bound is not a bound"
    assert ids, "an empty bound would make the repair a silent no-op"
    assert len(ids) == len(set(ids)), "duplicate ids double-count the plan"
    assert all(isinstance(i, int) for i in ids)
    assert len(ids) <= 32, (
        f"the bound has grown to {len(ids)} ids. This repair is a one-shot "
        "correction for an enumerated set; a growing list means somebody wants "
        "a predicate, which is a different ship with a different blast radius."
    )


def test_only_politics_can_be_written():
    assert rail.TARGET_CATEGORY == "politics"


def test_the_restore_line_is_a_statement_not_a_dict_repr():
    """D51's undo must survive a paste.

    The first CI run logged `SET llm_sport_category = {109237: 'hockey'}` — the
    before-value map interpolated where the value belongs. It reads like a
    restore and is not one, which is worse than omitting it, because D51 is
    granted on the promise that a one-command restore exists.

    The real-Postgres gate executes the emitted text; this asserts the shape
    everywhere, including on a machine with no server.
    """
    sql = rail.restore_sql(
        [
            {"id": 109237, "before": "hockey"},
            {"id": 109373, "before": "hockey"},
        ]
    )
    assert sql == (
        "UPDATE futures_markets SET llm_sport_category = 'hockey' "
        "WHERE id IN (109237, 109373);"
    )
    assert "{" not in sql and "}" not in sql, "a dict repr leaked into the SQL"


def test_the_restore_splits_by_distinct_before_value():
    """One statement for all rows is only correct while they agree."""
    sql = rail.restore_sql(
        [
            {"id": 1, "before": "hockey"},
            {"id": 2, "before": "basketball"},
            {"id": 3, "before": None},
        ]
    )
    lines = sql.splitlines()
    assert len(lines) == 3, f"expected one statement per before-value, got {lines}"
    assert "= 'basketball' WHERE id IN (2)" in sql
    assert "= NULL WHERE id IN (3)" in sql, "a NULL before-value must not quote"


def test_an_empty_plan_produces_no_restore_statement():
    assert rail.restore_sql([]) == ""


@pytest.mark.parametrize(
    "name,ticker",
    [
        ("Which Senators will vote for Kevin Warsh as Fed chair?", "KXVOTEFEDCHAIR-27"),
        ("How many Republican senators will lose reelection in 2026?", "KXLOSEREELECTIONRSEN-2026"),
        ("Which Senators will vote for the Clarity Act?", "KXCLARITYACT-25"),
    ],
)
def test_shipped_classification_agrees_with_the_ship(name, ticker):
    """The rail's view of a production name is the poller's view of it."""
    assert rail._shipped_classification(name, ticker) == "politics"


@pytest.mark.parametrize(
    "name,ticker",
    [
        ("NHL: OTT Senators Total Points", "KXNHLPOINTS-26"),
        ("Belleville Senators vs Hartford Wolf Pack", "KXAHLGAME-26"),
    ],
)
def test_a_real_hockey_name_is_never_classified_politics(name, ticker):
    """The gate that makes the id list safe, asserted without a database."""
    assert rail._shipped_classification(name, ticker) != "politics"
