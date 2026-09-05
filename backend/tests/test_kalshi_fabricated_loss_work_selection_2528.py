"""The drain's work selection: the two properties no fixture can prove.

CAL-P1013 (#2528) rewrote ``_WORK_SQL`` from a whole-table ``GROUP BY`` over
``futures_outcomes`` into a LATERAL probe driven from ``futures_markets`` in sort
order, because on 2026-09-05 the old form was cancelled at its own 18s bound on
every production call — unsharded, ``?sport=baseball`` and ``?sport=basketball``,
18.1-18.2s each — so the rail had never built a plan.

The row-level identity of that rewrite is proved where it can be: against real
Postgres, in ``tests/integration/test_kalshi_fabricated_loss_bind_contract_pg.py``,
by running the old statement and the new one over the same seeded population and
diffing the rows. **These two properties are not provable that way**, and that is
why they are here, in a file that runs in every shard with no database:

1. **The top-level ORDER BY.** A subquery's ordering is not contractually
   preserved through a join. Delete the outer ``ORDER BY`` and a small fixture
   still passes — the planner keeps the order anyway at that size — while
   production is free to choose a hash join and hand back an arbitrary 40
   markets with a cursor that skips everything it stepped over. The failure is
   invisible in the result set, because every row returned is still a genuine
   population member. Only the source text can be held.

2. **The refusal's advice.** The old ``hint`` told the operator to shard with
   ``?sport=``, and sharding by sport cannot reduce this cost: the sport
   predicate is on ``futures_markets`` and the cost is the per-market probe of
   ``futures_outcomes``. Nothing in a test fixture is slow, so no behavioural
   test can catch advice that does not work; the invariant is that the rail
   never advises a parameter its own measurement refuted.

Both guards are asserted to FIRE against the pre-fix text, immediately below the
assertion they guard. A guard that has never rejected anything is a comment.
"""

import re

from app.tasks import repair_kalshi_fabricated_loss as rail
from app.utils.kalshi_fabricated_loss import POPULATION_HAVING_SQL


def _top_level_order_by(sql: str) -> str | None:
    """The ORDER BY that governs the STATEMENT, or None if there isn't one.

    Structural rather than textual: it walks the parentheses and returns the
    clause of the last ``ORDER BY`` that sits at depth 0. An ``ORDER BY`` inside
    a derived table or a LATERAL is a hint to the planner; only one at depth 0
    is a promise to the caller, and this rail's cursor is a position in that
    promise.

    ``--`` comments are stripped FIRST, and that line is load-bearing rather than
    tidy: the statement this guards carries a comment explaining why the clause
    is there, so a version of this function that read comments found the words
    "ORDER BY ... resolution_date ... id" in the PROSE and passed a statement
    whose real clause had been deleted. Caught by mutating the shipped SQL and
    reading WHICH assertion fired. A guard that can be satisfied by a comment
    about the invariant, rather than the invariant, is worse than none — it
    reports green on the exact edit it exists to stop. Parentheses inside a
    comment would corrupt the depth count for the same reason.
    """
    sql = re.sub(r"--[^\n]*", "", sql)
    depth = 0
    found = None
    i = 0
    upper = sql.upper()
    while i < len(sql):
        ch = sql[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and upper.startswith("ORDER BY", i):
            end = upper.find("LIMIT", i)
            found = sql[i : end if end != -1 else len(sql)]
            i += len("ORDER BY")
            continue
        i += 1
    return found


def test_the_work_selection_declares_its_own_result_order():
    """Oldest-first-within-a-floor must be a promise, not a plan accident."""
    clause = _top_level_order_by(rail._WORK_SQL)

    assert clause is not None, (
        "_WORK_SQL has no top-level ORDER BY. The keyset cursor names a POSITION "
        "in the result order and the retention floor is only reached in time "
        "because the oldest rows come first; without this clause the planner may "
        "return any 40 population members and the drain will skip the rest "
        "silently."
    )
    positions = [
        clause.upper().find("RESOLUTION_DATE"),
        clause.upper().rfind(".ID "),
    ]
    assert -1 not in positions, f"the ordering must name resolution_date then id: {clause!r}"
    assert positions[0] < positions[1], "resolution_date is the MAJOR key, id breaks ties"
    assert clause.upper().count("DESC") == 0, (
        "newest-first never reaches the old tail (gotcha #41 / CAL-P009) and the "
        "at-risk band expires behind it"
    )


def test_that_order_by_guard_rejects_the_shape_it_exists_to_reject():
    """The mutation: an inner-only ordering, which is what a rewrite reaches for."""
    inner_only = """
        SELECT s.id FROM (
          SELECT fm.id FROM futures_markets fm ORDER BY fm.resolution_date ASC, fm.id ASC
        ) s CROSS JOIN LATERAL (SELECT COUNT(*) FROM futures_outcomes fo
          WHERE fo.market_id = s.id HAVING COUNT(*) >= 2) mx
        LIMIT :lim
    """
    assert _top_level_order_by(inner_only) is None, (
        "the guard cannot see the difference between an inner ORDER BY and a "
        "top-level one, so it would have passed the bug it is written for"
    )
    assert _top_level_order_by(rail._WORK_SQL) is not None


def test_the_population_predicate_is_the_shared_constant_not_a_copy():
    """One definition of the population, read by the census and the drain alike.

    The rewrite moved the predicate from a GROUP BY to a LATERAL HAVING. Moving
    it is fine; re-typing it is not — the census, the work selection and the
    after-check agreeing "by construction" is the property that lets a drain be
    called finished when the census reads zero.
    """
    assert POPULATION_HAVING_SQL.strip() in rail._WORK_SQL, (
        "the work selection no longer interpolates POPULATION_HAVING_SQL; a "
        "second copy of the population definition can drift from the census's"
    )
    assert POPULATION_HAVING_SQL.strip() in rail._CENSUS_SQL, (
        "the census no longer interpolates it either"
    )


def _refused_parameters(hint: str) -> set[str]:
    """Parameters the hint mentions inside a sentence that NEGATES them."""
    negated = set()
    for sentence in re.split(r"(?<=[.:;])\s+", hint):
        if re.search(r"\b(not|never|cannot|does not|do not)\b", sentence, re.I):
            negated.update(re.findall(r"\?(\w+)=", sentence))
    return negated


def test_the_work_selection_refusal_never_advises_what_was_measured_not_to_work():
    """A refusal whose advice does not work is the defect wearing a second coat.

    The hint may still MENTION ``?sport=`` — warning an operator off it is the
    useful thing to say, since it was the advice for three weeks — but only
    inside a sentence that denies it. And it has to offer something that does
    bound the scan, or it is a dead end with a friendly tone.
    """
    hint = _work_selection_refusal_hint()

    mentioned = set(re.findall(r"\?(\w+)=", hint))
    if "sport" in mentioned:
        assert "sport" in _refused_parameters(hint), (
            "the hint offers ?sport= as the remedy. Measured against production "
            "2026-09-05: unsharded 18.2s, ?sport=baseball 18.1s, "
            "?sport=basketball 18.2s — all three refused, because the sport "
            "predicate is on futures_markets and the cost is the per-market "
            "probe of futures_outcomes."
        )
    assert mentioned & {"limit", "after_date", "after_id"}, (
        "the refusal names no parameter that actually bounds the scan"
    )


def test_that_hint_guard_rejects_the_advice_it_replaced():
    """The mutation: the exact text this rail shipped until CAL-P1013."""
    old = (
        "Shard with ?sport=<llm_sport_category>. The global sort over the "
        "filtered market set is the cost; a sharded sort is not."
    )
    assert "sport" not in _refused_parameters(old), (
        "the guard reads the old advice as already negated, so it would have "
        "passed the text it exists to reject"
    )
    assert not set(re.findall(r"\?(\w+)=", old)) & {"limit", "after_date", "after_id"}


def _work_selection_refusal_hint() -> str:
    """The hint the rail actually returns, taken from the rail, never re-typed.

    Read out of the shipped source rather than restated: a guard that quotes its
    subject cannot detect a change in it.
    """
    import inspect

    source = inspect.getsource(rail._dry_run)
    start = source.index('"hint": (')
    end = source.index("),", start)
    return " ".join(re.findall(r'"([^"]*)"', source[start:end]))
