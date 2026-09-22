"""#8029 — the sport-to-sport correction rail.

🔴 EVERY fixture value in this file was READ from Kalshi and from production on
2026-09-22, not inferred. The sibling suite records why that rule exists: two of
its drafts GUESSED `Entertainment` for events the venue actually files under
`Social`, and the suite went green on a verdict production does not produce.
This row is one of those `Social` events, so the trap is live here too.

Reads, verbatim:

* ``GET /trade-api/v2/events/KXDONATEMRBEAST-27JAN`` ->
  ``category: "Social"``, ``series_ticker: "KXDONATEMRBEAST"``
* ``GET /trade-api/v2/series/KXDONATEMRBEAST`` ->
  ``category: "Sports"``, ``tags: ["Football"]``
* ``futures_markets`` id ``109401`` -> ``source='kalshi'``,
  ``category='other'``, ``llm_sport_category='baseball'``, ``status='open'``
"""

import ast
import asyncio
import inspect
from pathlib import Path

import pytest

from app.routes.admin_repairs import _REPAIRS
from app.tasks import repair_kalshi_venue_sport_correction as rail
from app.tasks import repair_kalshi_venue_topic_badges as sibling
from app.tasks.kalshi import _categorize_kalshi_market, _pick_series_tag

SPECIMEN_ID = 109401
TICKER = "KXDONATEMRBEAST-27JAN"
SERIES = "KXDONATEMRBEAST"
NAME = (
    "Will MrBeast donate to East Carolina University athletics NIL programs "
    "this year?"
)

EVENTS = {
    TICKER: {
        "event": {
            "event_ticker": TICKER,
            "series_ticker": SERIES,
            "category": "Social",
        }
    }
}
SERIES_PAYLOADS = {SERIES: {"category": "Sports", "tags": ["Football"]}}


class _Row:
    def __init__(
        self,
        id=SPECIMEN_ID,
        name=NAME,
        status="open",
        external_id=TICKER,
        category="other",
        llm_sport_category="baseball",
    ):
        self.id = id
        self.name = name
        self.status = status
        self.external_id = external_id
        self.category = category
        self.llm_sport_category = llm_sport_category


class _Result:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def all(self):
        return self._rows


class _StubSession:
    """The three statement shapes ``repair()`` issues, and nothing else."""

    def __init__(self, rows, moves=None, fail_update=False):
        self.rows = list(rows)
        self.moves = moves
        self.fail_update = fail_update
        self.updates: list[dict] = []
        self.selects: list[str] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        upper = sql.upper()
        if "SET LOCAL" in upper:
            return _Result()
        if "UPDATE" in upper:
            if self.fail_update:
                raise RuntimeError("canceling statement due to statement timeout")
            self.updates.append(dict(params))
            moved = self.moves is None or params["id"] in self.moves
            return _Result([(params["id"],)] if moved else [])
        if "SELECT" in upper:
            self.selects.append(sql)
            ids = set(params["ids"])
            return _Result(sorted((r for r in self.rows if r.id in ids), key=lambda r: r.id))
        raise AssertionError(f"unexpected statement:\n{sql}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _run(session, monkeypatch, events=None, series=None, apply=False):
    """Drive ``repair()`` with both venue doors stubbed."""
    events = EVENTS if events is None else events
    series = SERIES_PAYLOADS if series is None else series

    async def fake_event(_client, ticker):
        entry = events.get(ticker)
        if entry is None:
            return "indeterminate", None
        if entry == "404":
            return "not_found", None
        return "ok", entry

    async def fake_series(_client, ticker):
        entry = series.get(ticker)
        if entry is None:
            return "indeterminate", None
        if entry == "404":
            return "not_found", None
        return "ok", {"series": entry}

    monkeypatch.setattr(rail, "_fetch_event", fake_event)
    monkeypatch.setattr(rail, "_fetch_series", fake_series)
    monkeypatch.setattr(rail, "VENUE_PAUSE", 0)
    return asyncio.run(rail.repair(session, apply=apply))


# --------------------------------------------------------------------------
# The truth anchor: what the shipped classifier says, and WHY.
# --------------------------------------------------------------------------


def test_the_cascade_answers_football_only_because_the_venue_published_the_tag():
    """Both directions. Without this pair the rail's whole warrant is a guess.

    WITH the venue's tag the shipped cascade says `football` at step 1b. WITHOUT
    it, the same cascade on the same name says `baseball` — which is exactly the
    stored value, so this reproduces the defect rather than merely disagreeing
    with it.
    """
    assert _pick_series_tag(SERIES_PAYLOADS[SERIES]["tags"]) == "Football"
    assert (
        _categorize_kalshi_market(NAME, "Social", TICKER, "Football", "Sports")
        == "football"
    )
    assert _categorize_kalshi_market(NAME, "Social", TICKER) == "baseball"


def test_the_scorer_is_not_the_defect_and_must_not_be_touched():
    """`athletics` ties baseball and olympics at the AMBIGUOUS weight.

    The identical shape is produced by `Athletics vs. Detroit Tigers` (527
    markets) and `Avalanche vs. Blues` (244), both of which are RIGHT today. A
    scoring rule that refused the tie would break them. Pinned so a later
    session does not "fix" the scorer and call this issue closed.
    """
    from app.utils.futures_categorization import (
        _AMBIGUOUS_WEIGHT,
        score_sport_evidence,
    )

    scores = score_sport_evidence(NAME.lower())
    assert scores == {"baseball": _AMBIGUOUS_WEIGHT, "olympics": _AMBIGUOUS_WEIGHT}
    assert score_sport_evidence("athletics vs. detroit tigers") == scores


# --------------------------------------------------------------------------
# The plan, the write, the undo.
# --------------------------------------------------------------------------


def test_the_rail_plans_the_single_bound_row(monkeypatch):
    out = _run(_StubSession([_Row()]), monkeypatch)
    assert out["counts"]["changed"] == 1
    assert out["planned"] == [
        {
            "id": SPECIMEN_ID,
            "event_ticker": TICKER,
            "name": NAME,
            "status": "open",
            "before": "baseball",
            "after": "football",
        }
    ]


def test_a_dry_run_never_writes(monkeypatch):
    session = _StubSession([_Row()])
    out = _run(session, monkeypatch)
    assert session.updates == []
    assert session.commits == 0
    assert out["counts"]["rows_written"] == 0
    assert out["terminal"] == "dry_run"
    # An undo for a run that wrote nothing would be a lie.
    assert out["restore_sql"] == ""


def test_an_apply_compare_and_sets_on_the_value_it_read(monkeypatch):
    session = _StubSession([_Row()])
    out = _run(session, monkeypatch, apply=True)
    assert session.updates == [
        {"llm": "football", "id": SPECIMEN_ID, "before": "baseball"}
    ]
    assert out["counts"]["rows_written"] == 1
    assert out["applied"] == [SPECIMEN_ID]
    assert session.commits == 1


def test_the_undo_names_only_the_rows_that_actually_moved(monkeypatch):
    """A compare-and-set that matched nothing must not appear in the undo."""
    session = _StubSession([_Row()], moves=set())
    out = _run(session, monkeypatch, apply=True)
    assert out["counts"]["rows_written"] == 0
    assert out["applied"] == []
    assert out["restore_sql"] == ""
    assert session.rollbacks == 1


def test_the_restore_sql_is_runnable_and_restores_the_before_value(monkeypatch):
    out = _run(_StubSession([_Row()]), monkeypatch, apply=True)
    assert out["restore_sql"] == (
        "UPDATE futures_markets SET llm_sport_category = 'baseball' "
        f"WHERE id IN ({SPECIMEN_ID});"
    )


def test_a_write_failure_is_a_named_result_not_a_crash(monkeypatch):
    session = _StubSession([_Row()], fail_update=True)
    out = _run(session, monkeypatch, apply=True)
    assert out["counts"]["write_failed"] == 1
    assert out["counts"]["rows_written"] == 0
    assert session.rollbacks == 1


# --------------------------------------------------------------------------
# The gates. Each one is proved by a row that reaches it and is turned away.
# --------------------------------------------------------------------------


def test_a_name_derived_verdict_is_refused(monkeypatch):
    """🔴 GATE 4, the load-bearing one.

    The cascade can answer from the TICKER MAP (step 1) as well as from the tag,
    and it can answer from the NAME (step 2). Only the tag is this rail's
    warrant. Here the venue publishes `Soccer` but the ticker prefix `KXNHL`
    makes step 1 answer `hockey` first, so the cascade's answer is not the tag's
    answer and the row is refused rather than written.

    Without this gate the rail would overwrite one guess with another guess.
    """
    ticker = "KXNHLGAME-26"
    events = {ticker: {"event": {
        "event_ticker": ticker, "series_ticker": "KXNHLGAME", "category": "Sports"}}}
    series = {"KXNHLGAME": {"category": "Sports", "tags": ["Soccer"]}}
    session = _StubSession([_Row(external_id=ticker, llm_sport_category="baseball")])

    out = _run(session, monkeypatch, events=events, series=series)

    assert out["counts"]["verdict_not_from_tag"] == 1
    assert out["counts"]["changed"] == 0
    assert session.updates == []


def test_a_series_with_no_sport_tag_is_refused(monkeypatch):
    """GATE 3. `Television` is a real Kalshi tag that maps to no sport of ours."""
    series = {SERIES: {"category": "Entertainment", "tags": ["Television"]}}
    session = _StubSession([_Row()])
    out = _run(session, monkeypatch, series=series)
    assert out["counts"]["no_venue_sport_tag"] == 1
    assert out["counts"]["changed"] == 0
    assert session.updates == []


def test_the_venue_agreeing_is_refused(monkeypatch):
    """GATE 5. A row already carrying the venue's own word is left alone."""
    session = _StubSession([_Row(llm_sport_category="football")])
    out = _run(session, monkeypatch)
    assert out["counts"]["venue_agrees"] == 1
    assert out["counts"]["changed"] == 0
    assert session.updates == []


def test_a_ticker_the_venue_does_not_echo_is_refused(monkeypatch):
    """GATE 2. Membership is id identity; a fuzzy answer is never reasoned about."""
    events = {TICKER: {"event": {
        "event_ticker": "KXSOMETHINGELSE", "series_ticker": SERIES,
        "category": "Social"}}}
    session = _StubSession([_Row()])
    out = _run(session, monkeypatch, events=events)
    assert out["counts"]["not_our_ticker"] == 1
    assert session.updates == []


@pytest.mark.parametrize("door", ["event", "series"])
def test_a_venue_failure_never_becomes_a_verdict(monkeypatch, door):
    """Gotcha #53 / #36: a rate limit is not evidence, at EITHER door.

    The series door matters most: classifying without the tag is classifying on
    the very name guess this rail exists to overwrite, so even a 404 there is
    indeterminate rather than a licence to proceed tagless.
    """
    events = {} if door == "event" else EVENTS
    series = {} if door == "series" else SERIES_PAYLOADS
    session = _StubSession([_Row()])
    out = _run(session, monkeypatch, events=events, series=series, apply=True)
    assert out["counts"]["indeterminate"] == 1
    assert out["counts"]["changed"] == 0
    assert session.updates == []


def test_a_row_the_venue_has_dropped_is_refused(monkeypatch):
    session = _StubSession([_Row()])
    out = _run(session, monkeypatch, events={TICKER: "404"})
    assert out["counts"]["not_at_venue"] == 1
    assert session.updates == []


# --------------------------------------------------------------------------
# Shape guards.
# --------------------------------------------------------------------------


def test_the_bound_is_enumerated_and_small():
    """A bound that grew into a population would be a different, unmeasured rail."""
    assert rail.BOUND == (SPECIMEN_ID,)
    assert all(isinstance(i, int) for i in rail.BOUND)


def test_the_rail_uses_the_siblings_venue_doors_by_identity():
    """Not a re-spelling. `_fetch` there refuses to collapse 404 into 429 (#36)."""
    assert rail._fetch_event is sibling._fetch_event
    assert rail._fetch_series is sibling._fetch_series
    assert rail.WRITE_TIMEOUT_MS is sibling.WRITE_TIMEOUT_MS
    assert rail.VENUE_PAUSE is sibling.VENUE_PAUSE
    # The per-call timeout is NOT imported: this rail issues no raw HTTP call,
    # so it has no use for one, and `_fetch_event`/`_fetch_series` carry it by
    # identity already. CodeQL called the import unused and was right.


def test_the_rail_is_registered_and_named_once():
    assert _REPAIRS[rail.REPAIR_NAME] == (
        "app.tasks.repair_kalshi_venue_sport_correction",
        "repair",
    )


def _update_literals() -> list[str]:
    """Every `UPDATE futures_markets` string the module contains.

    🔴 There are TWO, and they are not interchangeable: the statement the rail
    EXECUTES, and the f-string fragment `restore_sql` builds the D51 undo from.
    An earlier draft of these guards took `next(...)` of this list and so
    asserted everything about the undo helper and nothing about the write —
    green, and blind to a mutation that deleted the compare-and-set.
    """
    source = Path(inspect.getfile(rail)).read_text()
    return [
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "UPDATE futures_markets" in node.value
    ]


def _executed_update() -> str:
    """The statement the rail actually issues, picked by its bound parameter."""
    executed = [s for s in _update_literals() if ":id" in s]
    assert len(executed) == 1, _update_literals()
    return executed[0]


def test_the_rail_writes_only_llm_sport_category():
    """A taxonomy badge is never a result — no price, outcome or `is_winner`.

    Checked over BOTH literals: the executed statement and the undo it hands an
    operator. An undo that touched a second column would be a second defect.
    """
    literals = _update_literals()
    assert len(literals) == 2, literals
    for body in literals:
        # The ASSIGNED COLUMNS, parsed — not a substring scan. `"category ="`
        # is a substring of `"llm_sport_category ="`, so the obvious spelling
        # of this guard fails on the one statement it is meant to bless.
        set_clause = body.split("SET", 1)[1].split("WHERE", 1)[0]
        assigned = [
            part.split("=", 1)[0].strip() for part in set_clause.split(",")
        ]
        assert assigned == ["llm_sport_category"], assigned


def test_the_update_is_a_compare_and_set_that_returns_what_moved():
    """The stub cannot enforce a WHERE clause, so the STATEMENT is asserted.

    Found by mutation: deleting `IS NOT DISTINCT FROM :before` left every other
    test in this file green. That predicate is the only thing standing between
    an apply and the Kalshi poller, which reaches this row every two hours; and
    RETURNING (not rowcount) is what lets the undo name the rows that actually
    moved rather than the rows we hoped would.
    """
    update = _executed_update()
    assert "IS NOT DISTINCT FROM :before" in update
    assert "RETURNING id" in update


def test_the_bound_is_read_scoped_to_kalshi():
    """The bound is ids, and an id alone does not say which venue filed the row.

    Also found by mutation: dropping `source = 'kalshi'` broke nothing, because
    the one bound id happens to be a Kalshi row. The scope is what keeps that a
    fact about the predicate rather than a coincidence of the bound.
    """
    source = Path(inspect.getfile(rail)).read_text()
    select = next(
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "FROM futures_markets" in node.value
    )
    assert "fm.source = 'kalshi'" in select
    assert "fm.id = ANY(:ids)" in select


def test_the_rail_carries_no_sport_vocabulary_of_its_own():
    """Every category word it can write comes from the venue, never a literal."""
    source = Path(inspect.getfile(rail)).read_text()
    tree = ast.parse(source)
    # Docstrings are prose and name the specimen's sports on purpose.
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    literals = {
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and n.value not in docstrings
    }
    for sport in ("football", "baseball", "hockey", "soccer", "basketball"):
        assert sport not in literals, f"{sport!r} is hard-coded in the rail"


def test_the_non_sport_destination_branch_is_defence_and_the_invariant_holds():
    """GATE 5's non-sport arm cannot fire today, and this is why it stays.

    `series_tag_to_category` can only return a value from the sport prefix map,
    and that map's range is disjoint from the non-sport set — so after GATE 4
    has forced the verdict to equal the tag's category, the non-sport arm is
    unreachable BY CONSTRUCTION. Writing a test that "proves" it fires would be
    vacuous. What is worth pinning is the invariant it rests on: if someone
    later maps a tag to a non-sport category, this fails and the branch, which
    is already there, becomes load-bearing.
    """
    from app.utils.sport_keys import (
        NON_SPORT_LLM_CATEGORIES,
        SPORT_PREFIX_TO_LLM_CATEGORY,
    )

    reachable = set(SPORT_PREFIX_TO_LLM_CATEGORY.values())
    assert reachable & set(NON_SPORT_LLM_CATEGORIES) == set()
    assert "other" not in reachable
