"""#4365 part 2 — the two NHL prop rows, and the dependency whose failure made them.

Two subjects, and the second is the more valuable one.

1. **The rail must not become a second classifier**, and its id list must stay a
   bound. Same decay as the certed senate sibling, guarded the same way — with
   one deliberate difference noted at
   ``test_the_only_sport_word_in_this_module_is_the_target``: that module forbids
   every sport token in its literals, which this one cannot do, because its
   target IS a sport.

2. **The ticker branch must keep covering every NHL prop family.** This is the
   guard #4365 asked for, pointed somewhere different from where the issue
   pointed it.

   The issue proposed guarding the *fallback* — pinning that the name-only
   branch reads ``"… : Points"`` as basketball. A guard that asserts current
   wrong behaviour cements it: it goes red when somebody FIXES the defect, which
   is precisely backwards. And it would not have caught this incident, because
   the fallback did not change.

   What actually happened in April 2026 is that ``KXNHLPTS`` / ``KXNHLAST`` were
   not in the ticker map, so step 1 of the cascade declined and the rows fell
   through to a fallback that was always wrong. The silent dependency is
   *ticker coverage*, so that is what gets pinned. It goes red the way it went
   wrong.

The write itself needs no database here: the planning half is pure, and gate 2
is a function call. What a real Postgres adds is the UPDATE's rowcount, which is
the same one-statement shape the senate sibling already proves in CI.
"""

from __future__ import annotations

import inspect

import pytest

from app.tasks import repair_kalshi_nhl_prop_category as rail


#: Sport tokens that must not appear as string literals in the rail's CODE.
#: `hockey` is absent from this tuple on purpose — it is the target category and
#: has to be named. `test_the_only_sport_word_in_this_module_is_the_target`
#: covers it separately, by count.
_FOREIGN_SPORT_TOKENS = (
    "basketball",
    "baseball",
    "football",
    "soccer",
    "tennis",
    "golf",
    "nhl",
    "nba",
    "penguins",
    "flyers",
    "points",
    "assists",
)


def _parsed():
    """The module's AST, with every docstring removed.

    🔴 Docstrings and comments are excluded because this module's whole subject
    is discussed in prose there — `basketball`, `points`, `assists`, `NHL` and
    the team names all appear in the module docstring by necessity, and a naive
    substring scan over raw source fails on its own explanation.

    Uses `ast` rather than a regex: a regex that strips `#` to end-of-line also
    eats a `#` inside a string literal, which is the trap that makes source-scan
    guards read as passing while scanning the wrong text.
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

    Literals rather than identifiers, deliberately. `NHL_PROP_ROW_IDS` is a fine
    name for an enumerated bound and says nothing about how a row is judged;
    what would make this rail a second classifier is a *value* it compares
    against. Scanning identifiers would flag the constant's own name and force a
    worse name to satisfy a test.
    """
    import ast

    return [
        n.value
        for n in ast.walk(_parsed())
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def test_the_scan_actually_sees_the_code():
    """A source-scan guard that reads nothing passes everything.

    The literal scans below are all absence assertions. If `_decision_strings()`
    ever returns an empty list — a renamed module, a changed AST shape — every
    one of them goes green while checking nothing. This is the positive control
    that keeps them honest: the code demonstrably contains literals, and one we
    can name.
    """
    literals = _decision_strings()
    assert literals, "the AST walk found no string literals — the scans are vacuous"
    assert rail.TARGET_CATEGORY in literals, (
        "the target category is not among the scanned literals, so the scan is "
        "not reading the code it claims to read"
    )


def test_the_only_sport_word_in_this_module_is_the_target():
    """The senate sibling forbids every sport token. This one cannot.

    `repair_kalshi_senate_category` writes `politics`, so "no sport literal
    anywhere" is a clean rule there. Here the target IS `hockey`, so the same
    rule would be unsatisfiable, and the tempting fix — dropping the scan — would
    lose the guard that stops the rail growing an opinion.

    So the rule becomes: the target token appears EXACTLY ONCE (its own
    constant), and no other sport word appears at all. A second `hockey` literal
    means somebody has started comparing against it somewhere other than
    `TARGET_CATEGORY`, which is the first move of a second classifier.
    """
    literals = _decision_strings()
    occurrences = [s for s in literals if s.lower() == rail.TARGET_CATEGORY]
    assert len(occurrences) == 1, (
        f"`{rail.TARGET_CATEGORY}` appears as a string literal "
        f"{len(occurrences)} times in `repair_kalshi_nhl_prop_category`. It may "
        "appear exactly once, as TARGET_CATEGORY. A second occurrence is a "
        "comparison this rail should be asking the shipped classifier to make."
    )

    haystack = " ".join(literals).lower()
    found = sorted(t for t in _FOREIGN_SPORT_TOKENS if t in haystack)
    assert not found, (
        f"{found} appear as string literals in "
        "`repair_kalshi_nhl_prop_category`. This rail must ask "
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
        "`repair_kalshi_nhl_prop_category` imports `re`. Matching a market name "
        "here is the second-classifier failure this module exists to avoid."
    )


def test_the_rail_actually_calls_the_shipped_classifier():
    """Absence of rules is not presence of a call.

    A module with no sport keywords and no classifier call would pass the scans
    above while relabelling blindly.
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
    ids = rail.NHL_PROP_ROW_IDS
    assert isinstance(ids, tuple), "a mutable bound is not a bound"
    assert ids, "an empty bound would make the repair a silent no-op"
    assert len(ids) == len(set(ids)), "duplicate ids double-count the plan"
    assert all(isinstance(i, int) for i in ids)
    assert len(ids) <= 32, (
        f"the bound has grown to {len(ids)} ids. This repair is a one-shot "
        "correction for an enumerated set; a growing list means somebody wants "
        "a predicate, which is a different ship with a different blast radius."
    )


def test_only_hockey_can_be_written():
    assert rail.TARGET_CATEGORY == "hockey"


def test_the_dispatcher_can_actually_call_this_rail():
    """`routes/admin_repairs.py` calls `fn(db, apply, **extra)` — `apply` is
    POSITIONAL. A keyword-only `apply` would make the repair permanently
    un-appliable while looking perfectly correct in isolation."""
    params = list(inspect.signature(rail.repair).parameters.values())
    assert params[0].name == "session"
    assert params[1].name == "apply"
    assert params[1].kind is not inspect.Parameter.KEYWORD_ONLY


def test_the_rail_is_registered_and_the_catalog_did_not_drift():
    """The registry entry and the docstring catalog, in the commit that added them.

    The module docstring of `admin_repairs` says in so many words that a further
    drift would prove the warning was decoration.
    """
    import app.routes.admin_repairs as mod

    assert mod._REPAIRS["kalshi-nhl-prop-category"] == (
        "app.tasks.repair_kalshi_nhl_prop_category",
        "repair",
    )
    doc = mod.__doc__ or ""
    for name in mod._REPAIRS:
        assert name in doc, f"{name} missing from the docstring catalog"


# ---------------------------------------------------------------------------
# Gate 2, on the real classifier: the ship rows move, the control rows do not
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, ticker",
    [
        ("PIT Penguins at PHI Flyers: Points", "KXNHLPTS-26APR22PITPHI"),
        ("PIT Penguins at PHI Flyers: Assists", "KXNHLAST-26APR22PITPHI"),
    ],
)
def test_the_two_bound_rows_are_what_the_shipped_classifier_calls_hockey(name, ticker):
    """The ship. Both rows in the bound pass gate 2 on the shipped classifier.

    If this goes red the repair stops planning anything and becomes a silent
    no-op — which is the safe direction, but it is still a regression and it
    should be loud.
    """
    assert rail._shipped_classification(name, ticker) == rail.TARGET_CATEGORY


@pytest.mark.parametrize(
    "name, ticker",
    [
        # Real basketball props of the identical shape. These are the 1,607 rows
        # the census found stored `basketball` and correctly so.
        ("LAL Lakers at BOS Celtics: Points", "KXNBAPTS-26APR22LALBOS"),
        ("GSW Warriors at DEN Nuggets: Assists", "KXNBAAST-26APR22GSWDEN"),
    ],
)
def test_a_real_basketball_prop_is_refused_by_gate_2(name, ticker):
    """The control that makes the id list safe rather than merely short.

    Put one of these ids in the bound by mistake and the repair must REFUSE it,
    not relabel a real basketball market as hockey. Gate 2 is what draws that
    line, so it is asserted against the shipped classifier rather than described
    in the module docstring.
    """
    assert rail._shipped_classification(name, ticker) != rail.TARGET_CATEGORY


# ---------------------------------------------------------------------------
# The guard #4365 asked for, pointed at the dependency that actually failed
# ---------------------------------------------------------------------------


#: Every Kalshi NHL prop ticker family reachable today, including the two whose
#: absence in April 2026 produced this repair's entire population. The list is
#: the point: it is an inventory of what step 1 of the cascade must keep
#: covering, and adding a new NHL prop family without adding it here is how the
#: April defect recurs.
_NHL_PROP_TICKER_FAMILIES = (
    "KXNHLPTS",     # points   — MISSING in April 2026; made row 12508872
    "KXNHLAST",     # assists  — MISSING in April 2026; made row 12508876
    "KXNHLGOALS",
    "KXNHLSAVES",
    "KXNHLSOG",
    "KXNHLPOINTS",
)


@pytest.mark.parametrize("family", _NHL_PROP_TICKER_FAMILIES)
def test_every_nhl_prop_ticker_family_still_resolves_to_hockey(family):
    """Step 1 of the cascade must keep covering every NHL prop family.

    🔴 THIS IS THE GUARD, and it is deliberately not the one #4365 proposed.

    The issue suggested pinning the fallback's answer — that the name-only
    branch reads `"… : Points"` as basketball. Two things are wrong with that.
    It asserts a defect, so it goes red when somebody fixes it. And it would
    have caught nothing here: the fallback never changed. What changed is that
    the ticker map did not yet know `KXNHLPTS` / `KXNHLAST`, so the authoritative
    branch declined and a known-bad fallback answered.

    Pinned on the ticker ALONE — `event_ticker` supplied, name deliberately
    empty — so this cannot pass on name evidence and quietly stop testing step 1.
    That is the difference between guarding the dependency and guarding the
    outcome.
    """
    from app.tasks.kalshi import _categorize_kalshi_market

    assert _categorize_kalshi_market("", None, event_ticker=f"{family}-26APR22PITPHI") == (
        rail.TARGET_CATEGORY
    ), (
        f"the ticker family {family} no longer resolves to hockey through step 1 "
        "of the cascade. This is exactly how rows 12508872/12508876 were born: "
        "the ticker branch declined and `_STAT_TO_SPORT` answered `basketball` "
        "for `points`/`assists`, which are core NHL stats. Any NHL prop ingested "
        "while this is red is mis-tagged, and #1888's "
        "`coalesce(nullif(existing,'other'), new)` write then freezes it forever."
    )


def test_the_ticker_guard_is_not_passing_on_name_evidence():
    """The positive control for the guard above.

    A guard keyed on an unmapped ticker must FAIL, or the one above proves
    nothing — it would pass for any string. This pins that an unknown NHL-ish
    ticker with no name evidence does not reach `hockey` by some other route.
    """
    from app.tasks.kalshi import _categorize_kalshi_market

    assert _categorize_kalshi_market(
        "", None, event_ticker="KXNOTAREALFAMILY-26APR22PITPHI"
    ) != rail.TARGET_CATEGORY, (
        "an unmapped ticker with no name evidence classified as hockey, so "
        "`test_every_nhl_prop_ticker_family_still_resolves_to_hockey` would pass "
        "for a family that step 1 does not actually cover"
    )


# ---------------------------------------------------------------------------
# D51: the restore has to survive a paste
# ---------------------------------------------------------------------------


def test_the_restore_line_is_a_statement_not_a_dict_repr():
    """D51's undo must be runnable, not merely present.

    The senate sibling's first version emitted
    `SET llm_sport_category = {109237: 'hockey'}` — the before-value *map*
    interpolated where the value belongs. It reads like a restore and is not
    one, which is worse than omitting it, because D51 is granted on the promise
    that a one-command restore exists.
    """
    sql = rail.restore_sql(
        [
            {"id": 12508872, "before": "basketball"},
            {"id": 12508876, "before": "basketball"},
        ]
    )
    assert sql == (
        "UPDATE futures_markets SET llm_sport_category = 'basketball' "
        "WHERE id IN (12508872, 12508876);"
    )
    assert "{" not in sql and "}" not in sql, "a dict repr is not runnable SQL"


def test_the_restore_splits_by_distinct_before_value():
    """One statement per before-value. A single statement for two different
    prior categories would restore one of them to the wrong thing."""
    sql = rail.restore_sql(
        [
            {"id": 1, "before": "basketball"},
            {"id": 2, "before": None},
        ]
    )
    lines = sql.splitlines()
    assert len(lines) == 2, sql
    assert "= NULL WHERE id IN (2);" in sql
    assert "= 'basketball' WHERE id IN (1);" in sql


def test_an_empty_plan_produces_no_restore_statement():
    """A dry run that plans nothing must not log a statement that undoes nothing
    — an operator reading a restore line assumes there is something to restore."""
    assert rail.restore_sql([]) == ""
