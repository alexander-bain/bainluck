"""The identity quarantine is evaluated ONCE per unit, not once per outcome
(#6275, CAL-P1300).

## what stalled

#6275's quarantine reached ``bainluck-heavy`` at 11:48:44Z on 2026-09-15. Every
beat before it completed 6-10 units at a 116-165 s mean; every beat after ran
two units, completed **zero**, and cancelled both at the 483 s fence with the
bank pinned at 52/128 (``calibration:beat_gauge_history``, read 14:35Z). The
curve's date froze.

## why, read off the production planner

The chain :func:`app.utils.market_identity.identity_quarantine_ctes` renders is
referenced exactly once, and PostgreSQL 12+ INLINES a single-reference CTE. Its
one consumer sits deep inside ``ranked_outcomes``, so the inlined predicate
landed here (``EXPLAIN``, plan only, production schema, the real staged unit
statement)::

    Nested Loop Left   (eleven of them, twelve levels down inside
                        CTE ranked_outcomes)
      -> CTE Scan on market_info      Parent Relationship: INNER
         Filter: (event_commence_time IS NOT NULL)
             AND (substring((external_id)::text, '-([0-9]{2}[A-Z]{3}[0-9]{2})')
                  IS NOT NULL) AND make_date(...) <> (commence_time AT TIME ZONE
                  'America/New_York')::date

A ``CTE Scan`` on the inner side of a nested loop has no index, so EVERY outer
row rescans the whole materialised ``market_info`` and re-derives the regex and
the date arithmetic on every row of it — O(outcomes x markets) per unit instead
of O(markets). At the ~15 us/row the regex measures (4.6 s over 309,964 rows)
that is ~350 s of re-derivation on a roster-sized chunk, which is the entire gap
between a 130 s unit and one cancelled at 483 s.

``AS MATERIALIZED`` on the last CTE pins the whole chain to one evaluation.

## why this gate is a PLAN read and not a cost read

The planner's own estimate does not move: 29,205.65 inlined against 29,205.65
materialised on the production schema, because it has this chain at 1-5 rows
where production has thousands. That mis-estimate is WHY it chose the rescan, so
a gate that watched the cost would have watched the one number that cannot see
the defect. The shape is the fact: one ``CTE identity_disputed_markets`` node,
and the predicate inside it rather than inside ``ranked_outcomes``.

Nor can a string test carry this. ``"AS MATERIALIZED" in sql`` is true the
moment the keyword is typed and says nothing about where the predicate lands —
the keyword's whole purpose is a planner behaviour, so the planner is asked.

## red-first, executed here

:func:`_inlined` strips the keyword back out of the real built statement and the
second test asserts the defect returns in this very process: no CTE node, and
the predicate inside ``ranked_outcomes``. A green run therefore means the
inlined form was proved to reproduce the stall's shape, not that nothing
objected.

Needs a real server for ``EXPLAIN`` and nothing else — no rows are read, so
there is no fixture to seed. Opt-in on the same env vars as its neighbours and
NAMED IN ``ci.yml`` with the all-skipped detector, because a PG-gated file no
step invokes skips silently while pytest exits 0.
"""

from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("CALIBRATION_TEST_DATABASE_URL") or os.environ.get(
    "SEARCH_TEST_DATABASE_URL"
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL (CI's service container) or "
            "CALIBRATION_TEST_DATABASE_URL to run the #6275 single-evaluation gate"
        ),
    ),
]

#: The keyword under test, in the exact spelling the producer emits.
MATERIALIZED_CTE = "identity_disputed_markets AS MATERIALIZED ("
#: What it renders as once the keyword is stripped: a single-reference CTE, which
#: PostgreSQL inlines.
INLINED_CTE = "identity_disputed_markets AS ("

#: The node that carries the quarantine predicate is identified by two fragments
#: of the predicate itself rather than by a node type, because WHICH node holds
#: it is the thing under test.
PREDICATE_MARKS = ("America/New_York", "substring")

CTE_DISPUTED = "CTE identity_disputed_markets"
CTE_RANKED = "CTE ranked_outcomes"


def _inlined(sql: str) -> str:
    """The built statement with ONLY the materialisation removed."""
    assert sql.count(MATERIALIZED_CTE) == 1, (
        "PREMISE GONE: the built population SQL does not define "
        f"{MATERIALIZED_CTE!r} exactly once. Do not delete this gate — re-aim it "
        "at the new shape, or the red-first arm stops reverting anything and "
        "both assertions below pass vacuously."
    )
    return sql.replace(MATERIALIZED_CTE, INLINED_CTE, 1)


def _statement() -> str:
    """The real published chain, selected from at its last population CTE."""
    from app.tasks.precompute_calibration import _calibration_population_ctes

    return (
        "WITH " + _calibration_population_ctes() + " SELECT market_id FROM deduped"
    )


async def _plan(sql: str) -> dict:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as session:
            row = await session.execute(
                text("EXPLAIN (FORMAT JSON) " + sql)
            )
            plan = row.scalar_one()
    finally:
        await engine.dispose()
    if isinstance(plan, str):
        plan = json.loads(plan)
    return plan[0]["Plan"]


def _subtree_names(node: dict, ancestry: tuple[str, ...] = ()) -> list[tuple]:
    """Every node as ``(ancestry of CTE names, is-the-predicate-node, node)``.

    ``ancestry`` carries only the ``Subplan Name`` of enclosing CTE definitions,
    which is the one fact both assertions need: a node is "inside
    ``ranked_outcomes``" exactly when that name encloses it.
    """
    here = ancestry
    name = node.get("Subplan Name")
    if name:
        here = ancestry + (name,)
    body = json.dumps({k: v for k, v in node.items() if k != "Plans"})
    out = [(here, all(m in body for m in PREDICATE_MARKS), node)]
    for child in node.get("Plans") or []:
        out.extend(_subtree_names(child, here))
    return out


async def test_the_quarantine_is_one_cte_node_and_not_a_per_outcome_rescan():
    """The materialised chain: one evaluation, outside ``ranked_outcomes``."""
    sql = _statement()
    _inlined(sql)  # premise pin: the keyword is there to be removed

    nodes = _subtree_names(await _plan(sql))

    cte_nodes = [n for n in nodes if n[2].get("Subplan Name") == CTE_DISPUTED]
    assert len(cte_nodes) == 1, (
        "the quarantine chain is not a CTE node in the plan, so PostgreSQL "
        "inlined it into its consumer and it is re-derived per outer row. "
        f"CTE nodes present: {[n[2].get('Subplan Name') for n in nodes if n[2].get('Subplan Name')]}"
    )

    predicate = [n for n in nodes if n[1]]
    assert predicate, (
        "no node in the plan carries the quarantine predicate — the gate is "
        "aimed at a chain that is no longer in the statement"
    )
    for ancestry, _, node in predicate:
        assert CTE_DISPUTED in ancestry, (
            f"the quarantine predicate is evaluated at {ancestry}, outside its "
            "own CTE: something reads an intermediate link of the chain "
            "directly, so that link is single-reference again and inlines"
        )
        assert CTE_RANKED not in ancestry, (
            "the quarantine predicate is inside `ranked_outcomes` — this is the "
            "#6275 stall shape: it is re-derived once per outcome over every "
            f"market in the chunk (node {node.get('Node Type')}, ancestry {ancestry})"
        )


async def test_stripping_materialized_puts_the_predicate_back_in_the_loop():
    """Red-first, executed: the inlined form reproduces the stall's shape."""
    nodes = _subtree_names(await _plan(_inlined(_statement())))

    assert not [n for n in nodes if n[2].get("Subplan Name") == CTE_DISPUTED], (
        "removing MATERIALIZED left a CTE node standing, so the keyword is not "
        "what produces it and the other test proves nothing"
    )

    predicate = [n for n in nodes if n[1]]
    assert predicate, "the inlined statement lost the predicate entirely"
    assert any(CTE_RANKED in ancestry for ancestry, _, _ in predicate), (
        "the inlined predicate did not land inside `ranked_outcomes` here, so "
        "this server's planner is not reproducing the production shape and the "
        f"red-first arm is not proving the repair. Ancestries: "
        f"{[a for a, _, _ in predicate]}"
    )
