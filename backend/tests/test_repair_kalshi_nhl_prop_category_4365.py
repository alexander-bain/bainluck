"""#4365 part 2 — the two NHL prop rows, and the dependency whose failure made them.

Two subjects, and the second is the more valuable one.

1. **The rail must not become a second classifier**, and its id list must stay a
   bound. Same decay as the certed senate sibling, guarded the same way — with
   one deliberate difference noted at
   ``test_the_only_sport_word_in_this_module_is_the_target``: that module forbids
   every sport token in its literals, which this one cannot do, because its
   target IS a sport.

2. **The ticker must keep outranking the name rules.** This is the guard #4365
   asked for, pointed somewhere different from where the issue pointed it.

   The issue proposed guarding the *fallback* — pinning that the name-only
   branch reads ``"… : Points"`` as basketball. A guard that asserts current
   wrong behaviour cements it: it goes red when somebody FIXES the defect, which
   is precisely backwards.

   What actually happened, dated from the history rather than guessed: the rows
   were ingested 2026-04-22 16:45:24 UTC, and ``97862989`` *"Fix Kalshi sport
   misclassification: ticker before name rules"* is dated 2026-04-22 17:34:44
   −0700 = 2026-04-23 00:34 UTC — about eight hours later. The ticker was in the
   map the whole time (``kxnhlpts`` since 2026-03-30, ``2e2b2dba``); it just ran
   SECOND. So the silent dependency is cascade ORDER, and that is what gets
   pinned. It goes red the way it went wrong.

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


def _catalog_names() -> set[str]:
    """The names inside `admin_repairs`' ``name ∈ { … }`` block, and only those.

    🔴 NOT a substring scan of the whole docstring. That is how the sibling
    guards are written and it passes for the wrong reason: the docstring also
    carries a running re-sync log ("…adding kalshi-nhl-prop-category in the
    commit that registered it…"), so a name deleted from the catalog is still
    found in the prose about it. Mutation-proven — removing this name from the
    catalog block left the substring form green.
    """
    import app.routes.admin_repairs as mod

    doc = mod.__doc__ or ""
    start = doc.index("name ∈ {")
    end = doc.index("}", start)
    block = doc[start:end]
    return {part.strip() for part in block.split("{", 1)[1].split("|")}


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

    catalog = _catalog_names()
    assert "kalshi-nhl-prop-category" in catalog, (
        "this rail is registered but absent from the docstring catalog block"
    )
    missing = sorted(set(mod._REPAIRS) - catalog)
    assert not missing, f"{missing} registered but missing from the catalog block"


def test_the_catalog_parser_is_not_matching_everything():
    """Positive control for `_catalog_names`.

    An over-greedy parse — one that swallowed the whole docstring — would make
    the drift assertion above vacuous in exactly the way it was written to
    avoid. So: the block is a real, bounded set, and a name that appears in the
    docstring's PROSE but not in the catalog is not reported as present.
    """
    catalog = _catalog_names()
    assert 20 < len(catalog) < 100, f"implausible catalog size {len(catalog)}"
    assert all(" " not in n and n for n in catalog), (
        f"the parse produced non-name fragments: "
        f"{sorted(n for n in catalog if ' ' in n or not n)}"
    )
    assert "commit" not in catalog and "registered" not in catalog, (
        "the parse is reaching into the re-sync prose, which is the failure "
        "this parser exists to avoid"
    )


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


#: The specimen. Row 12508872's own stored name and ticker.
_SHIP_NAME = "PIT Penguins at PHI Flyers: Points"
_SHIP_TICKER = "KXNHLPTS-26APR22PITPHI"


def test_the_ticker_outranks_the_name_rules():
    """🔴 THIS IS THE GUARD, and it is deliberately not the one #4365 proposed.

    The issue suggested pinning the fallback's answer — that the name-only
    branch reads ``"… : Points"`` as basketball. That asserts a defect, so it
    goes red when somebody FIXES it, which is backwards.

    What actually made these two rows, dated from the history rather than
    guessed:

    * the rows were ingested **2026-04-22 16:45:24 UTC**;
    * ``97862989`` *"Fix Kalshi sport misclassification: ticker before name
      rules"* is dated **2026-04-22 17:34:44 −0700**, i.e. 2026-04-23 00:34 UTC —
      about eight hours AFTER the rows existed, and that is the commit date, not
      the deploy;
    * before it, step 2 (name rules) ran BEFORE the ticker. So ``: Points`` →
      ``basketball`` won over an NHL ticker that was already in the map
      (``kxnhlpts`` landed 2026-03-30 in ``2e2b2dba``).

    That commit's own message describes the identical symptom for a different
    market: ``KXNHLEAST-26`` stored ``basketball`` and invisible in the NHL grid.

    So the dependency is **cascade ORDER**, not ticker coverage, and order is
    what this pins. Revert ``97862989`` and this goes red. It is also why the
    fallback is deliberately left alone: with the order correct, the fallback
    cannot reach a Kalshi NHL prop at all.
    """
    from app.tasks.kalshi import _categorize_kalshi_market

    assert _categorize_kalshi_market(
        _SHIP_NAME, None, event_ticker=_SHIP_TICKER
    ) == rail.TARGET_CATEGORY, (
        "the name rules have overtaken the ticker in `_categorize_kalshi_market` "
        "again. This is exactly how rows 12508872/12508876 were born on "
        "2026-04-22, hours before `97862989` put the ticker first: "
        "`_STAT_TO_SPORT` answers `basketball` for `points`/`assists`, which are "
        "core NHL stats. Any NHL prop ingested while this is red is mis-tagged, "
        "and #1888's `coalesce(nullif(existing,'other'), new)` write then freezes "
        "it forever."
    )


def test_the_ordering_guard_above_still_has_teeth():
    """The mutation anchor for the guard above.

    ``test_the_ticker_outranks_the_name_rules`` only proves something while the
    two branches DISAGREE about this specimen. If the name-only branch ever
    returns hockey too, that test passes no matter which branch ran, and the
    ordering invariant silently stops being tested.

    🔴 A red here is not "the fallback broke" — it is most likely somebody
    fixing `_STAT_TO_SPORT` to be team-aware, which is welcome. It means: pick a
    new specimen where the branches still disagree, or retire the ordering guard
    because the fallback is no longer dangerous.

    Asserted as ``!= hockey`` rather than ``== basketball`` on purpose: pinning
    the exact wrong answer would cement it, and a fallback repaired to `other`
    or `None` should not fail anything.
    """
    from app.utils.futures_categorization import categorize_by_rules

    assert categorize_by_rules(_SHIP_NAME) != rail.TARGET_CATEGORY, (
        "the name-only branch now agrees with the ticker for "
        f"{_SHIP_NAME!r}, so `test_the_ticker_outranks_the_name_rules` would "
        "pass whichever branch answered. Re-point it at a specimen where they "
        "still disagree, or retire it."
    )


def test_ticker_resolution_is_prefix_based_not_per_family():
    """Why there is no per-family inventory in this file.

    The first draft of this guard parametrized over six NHL prop ticker families
    (`KXNHLPTS`, `KXNHLAST`, `KXNHLGOALS`, …) and asserted each resolved to
    hockey. All six passed — and all six were the SAME assertion, because
    `get_sport_key_from_ticker` matches on the `kxnhl` prefix: `KXNHLBANANA`
    resolves to `icehockey_nhl` too. Such a list cannot detect a lost family, so
    it was documentation wearing a test's clothes.

    This records the real behaviour instead, so the next person does not rebuild
    that inventory. If resolution ever becomes per-family, this goes red and a
    real inventory guard becomes both possible and necessary.
    """
    from app.utils.sport_keys import get_sport_key_from_ticker

    assert get_sport_key_from_ticker("KXNHLPTS-26APR22PITPHI") == "icehockey_nhl"
    assert get_sport_key_from_ticker("KXNHLBANANA-26APR22PITPHI") == "icehockey_nhl", (
        "ticker resolution is no longer `kxnhl`-prefix based. A per-family "
        "inventory guard is now meaningful and this cohort wants one."
    )
    assert get_sport_key_from_ticker("KXNOTAREALPREFIX-26APR22PITPHI") is None, (
        "an arbitrary ticker resolves to a sport, so no ticker-keyed assertion "
        "in this file proves anything"
    )


# ---------------------------------------------------------------------------
# D51: the restore has to survive a paste
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# `repair()`'s own branching — the safety gate, exercised rather than described
# ---------------------------------------------------------------------------
#
# 🔴 These exist because mutation testing found the hole. Every gate-2 assertion
# above calls `_shipped_classification` DIRECTLY, so replacing the gate inside
# `repair()` with `elif False:` — disabling the safety gate entirely — left all
# 18 tests green. A test of the predicate is not a test of the branch that uses
# it.


class _Row:
    """One `futures_markets` row as the repair reads it (attribute access)."""

    def __init__(self, id, name, source, external_id, llm_sport_category):
        self.id = id
        self.name = name
        self.source = source
        self.external_id = external_id
        self.llm_sport_category = llm_sport_category


class _FakeSession:
    """Enough session to run the PLAN half. It refuses to write.

    `apply=True` is deliberately not exercised here: the UPDATE's rowcount is
    the one thing that needs a real server, and the senate sibling already
    proves that one-statement shape in CI's real-Postgres job. What is proven
    here is the decision — which rows reach the UPDATE at all.
    """

    def __init__(self, rows):
        self._rows = rows
        self.executed_writes = 0

    async def execute(self, statement):
        # A SELECT returns the rows; anything else is a write this test forbids.
        if statement.__visit_name__ != "select":
            self.executed_writes += 1
            raise AssertionError(
                "the plan half issued a write — `apply=False` must never reach "
                "the UPDATE"
            )
        rows = self._rows

        class _Result:
            def all(self):
                return rows

        return _Result()

    async def commit(self):  # pragma: no cover - reaching this is the failure
        raise AssertionError("`apply=False` committed")


_SHIP_ROW = _Row(
    12508872, _SHIP_NAME, "kalshi", _SHIP_TICKER, "basketball",
)
#: A REAL basketball prop, wrongly present in the bound. Gate 2 must refuse it.
_CONTROL_ROW = _Row(
    999_999_001, "LAL Lakers at BOS Celtics: Points", "kalshi",
    "KXNBAPTS-26APR22LALBOS", "basketball",
)
#: Right name, wrong venue. Gate 3 must refuse it.
_FOREIGN_VENUE_ROW = _Row(
    999_999_002, _SHIP_NAME, "polymarket", _SHIP_TICKER, "basketball",
)
#: Already correct. Must be refused rather than re-written.
_ALREADY_ROW = _Row(
    999_999_003, _SHIP_NAME, "kalshi", _SHIP_TICKER, "hockey",
)


async def _plan(rows):
    session = _FakeSession(rows)
    return await rail.repair(session, apply=False)


@pytest.mark.asyncio
async def test_the_ship_row_is_planned():
    out = await _plan([_SHIP_ROW])
    assert [p["id"] for p in out["planned"]] == [12508872]
    assert out["refused"] == []
    assert out["changed"] == 0, "a dry run must change nothing"
    assert out["terminal"] == "dry_run"


@pytest.mark.asyncio
async def test_gate_2_refuses_a_real_basketball_prop_inside_repair():
    """THE SAFETY GATE, exercised through `repair()` rather than around it.

    A mislisted id must be REFUSED by name, not relabelled. Mutating the gate to
    `elif False:` makes this test — and only this class of test — go red.
    """
    out = await _plan([_CONTROL_ROW])
    assert out["planned"] == [], (
        "a genuine basketball prop was planned for relabelling as hockey; the "
        "shipped-classifier gate is not being consulted inside `repair()`"
    )
    assert [r["reason"] for r in out["refused"]] == ["classifier_disagrees"]


@pytest.mark.asyncio
async def test_gate_3_refuses_another_venue_and_an_already_correct_row():
    out = await _plan([_FOREIGN_VENUE_ROW, _ALREADY_ROW])
    assert out["planned"] == []
    assert sorted(r["reason"] for r in out["refused"]) == [
        "already_correct",
        "not_kalshi",
    ]


@pytest.mark.asyncio
async def test_the_gates_hold_when_the_rows_arrive_together():
    """The mixed batch — one row moving must not carry its neighbours.

    Asserted separately because a gate can be correct per row and still be
    written outside the loop, in which case one qualifying row admits the lot.
    """
    out = await _plan([_SHIP_ROW, _CONTROL_ROW, _FOREIGN_VENUE_ROW, _ALREADY_ROW])
    assert [p["id"] for p in out["planned"]] == [12508872]
    assert len(out["refused"]) == 3
    assert out["examined"] == 4


@pytest.mark.asyncio
async def test_a_missing_id_is_reported_not_silently_dropped():
    """The bound names two rows. If one is gone, the payload must say so —
    otherwise a repair that reached half its population reads as a full run."""
    out = await _plan([_SHIP_ROW])
    assert out["missing_ids"] == [12508876]


@pytest.mark.asyncio
async def test_the_restore_travels_on_the_dry_run():
    """D51: an operator must be able to read the undo BEFORE deciding to apply."""
    out = await _plan([_SHIP_ROW])
    assert out["restore_sql"] == (
        "UPDATE futures_markets SET llm_sport_category = 'basketball' "
        "WHERE id IN (12508872);"
    )


# ---------------------------------------------------------------------------
# The write is a compare-and-set (the CERT-2394 lesson, applied here)
# ---------------------------------------------------------------------------


class _ApplySession:
    """A session that lets the write run and records what it was asked to do.

    ``matched`` is the rowcount the UPDATE will report, so a drift — somebody
    moving the row between the scan and the write — can be simulated without a
    server.
    """

    def __init__(self, rows, matched=None):
        self._rows = rows
        self._matched = matched
        self.updates = []
        self.committed = False

    async def execute(self, statement):
        rows = self._rows
        if statement.__visit_name__ == "select":
            class _Result:
                def all(self):
                    return rows
            return _Result()

        self.updates.append(statement)
        matched = self._matched
        if matched is None:
            matched = len(self._rows)

        class _Written:
            rowcount = matched

        return _Written()

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_the_update_constrains_the_column_it_is_about_to_overwrite():
    """🔴 The CERT-2394 lesson, as a test rather than a paragraph.

    That cert blocked this lane's #4253 for a write that re-asserted less than
    its scan had tested. Here the gate reads `llm_sport_category`, so a write
    keyed on `id` alone would not notice that column moving between the scan and
    the commit. Asserted on the statement's WHERE clause, so deleting the
    compare-and-set fails even though the repair still "works".
    """
    session = _ApplySession([_SHIP_ROW])
    await rail.repair(session, apply=True)

    assert len(session.updates) == 1
    where = str(session.updates[0].whereclause)
    assert "llm_sport_category" in where, (
        "the UPDATE is keyed on id alone. A row whose category moved between "
        "the scan and the write would be overwritten on a stale decision, and "
        "its recorded `before` — the D51 restore — would be wrong."
    )
    assert session.committed


@pytest.mark.asyncio
async def test_a_healthy_apply_reports_every_planned_row_changed():
    session = _ApplySession([_SHIP_ROW])
    out = await rail.repair(session, apply=True)
    assert out["changed"] == 1
    assert out["drifted"] == []
    assert out["terminal"] == "changed"


@pytest.mark.asyncio
async def test_a_row_that_drifted_is_named_not_silently_missing():
    """`planned 1, changed 0` must never arrive unexplained.

    A bare count shortfall reads as the write half-failing. It is the opposite:
    the compare-and-set noticed a stale plan and declined. The payload has to
    say which row and what value it expected.
    """
    session = _ApplySession([_SHIP_ROW], matched=0)
    out = await rail.repair(session, apply=True)

    assert out["changed"] == 0
    assert out["drifted"] == [
        {"before": "basketball", "ids": [12508872], "matched": 0}
    ]
    assert len(out["planned"]) == 1, (
        "the plan should still report what it intended — the drift is a write-"
        "time refusal, not a planning error"
    )


@pytest.mark.asyncio
async def test_a_dry_run_still_issues_no_write():
    """The apply-capable session makes it possible to write by accident; prove
    `apply=False` does not, now that nothing raises to stop it."""
    session = _ApplySession([_SHIP_ROW])
    out = await rail.repair(session, apply=False)
    assert session.updates == []
    assert session.committed is False
    assert out["changed"] == 0
    assert out["drifted"] == []


@pytest.mark.asyncio
async def test_nothing_is_written_when_every_row_is_refused():
    """An all-refused plan must not issue an empty UPDATE — a statement with an
    empty id list is a write nobody reviewed."""
    session = _ApplySession([_CONTROL_ROW])
    out = await rail.repair(session, apply=True)
    assert session.updates == []
    assert out["planned"] == []
    assert out["changed"] == 0


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
