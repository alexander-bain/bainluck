"""#4788 (CAL-P1088) — the withdrawal, against a real Postgres.

The no-database file next door scans the rail's source. It cannot answer the
three questions that decide whether this rail is safe to run on 574,832 rows,
because all three are about what a SERVER does with the SQL:

1. **Does the market-level gate actually protect a graded market?** 854 resolved
   Polymarket markets have a crowned winner whose losing legs are un-badged.
   Those legs genuinely lost. A source scan proves the ``NOT EXISTS`` is
   present; only a server proves it EXCLUDES.
2. **Does withdrawing break ``pm-never-graded`` (#1912)?** That rail is the
   durable fix — it asks the CLOB venue and crowns a winner. This one runs first
   and must leave it able to do its job. Both of its predicates depend on
   three-valued logic over a column this rail sets to NULL:
   ``bool_or(NULL) IS NOT TRUE`` and ``NULL IS NOT TRUE``. Those are exactly the
   expressions a human reasons about wrongly, and they are imported here rather
   than restated so the gate cannot certify agreement with a copy.
3. **Is the result a fixed point?** A withdrawn row must leave its own bound, or
   the second page re-backs-up rows at their withdrawn value and the D51 undo
   silently becomes a no-op.
4. **Does it survive a grader writing underneath it?** (CERT-2524.) This rail
   pages, attended, over 574,832 legs while ``backfill_winners`` runs every six
   hours and ``pm-never-graded`` grades ONE LEG PER COMMIT. Everything about
   that failure is invisible to one session: it needs a real server, two real
   connections, and a real commit landing in the window between the backup and
   the write. A single-session test of a race is a test of the happy path with
   extra steps.

Opt-in on ``SEARCH_TEST_DATABASE_URL``, following its neighbours: ``initdb``
dies on ``shmget`` in the agent sandbox, so CI's ``search-recall`` job is the
only reader, and that job's skip-detector refuses to let an unrun gate read as a
passing one.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.tasks import repair_pm_ungraded_loss as rail
from app.tasks.repair_pm_never_graded import POPULATION_HAVING_SQL

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #4788 ungraded-loss "
            "withdrawal gate (CI job: search-recall)"
        ),
    ),
]


@pytest.fixture
async def db():
    """A real Postgres carrying the schema `create_all` builds from the model."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401  — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(f"DROP TABLE IF EXISTS {rail.BAK_TABLE}"))

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


async def _market(session, mid, source="polymarket", status="resolved",
                  external_id=None):
    await session.execute(
        text(
            "INSERT INTO futures_markets (id, source, external_id, name, "
            "category, status, mutually_exclusive) VALUES "
            "(:id, :src, :ext, :name, 'futures', :st, true)"
        ),
        {
            "id": mid,
            "src": source,
            "ext": external_id or f"0x{mid:04x}",
            "name": f"Market {mid}",
            "st": status,
        },
    )


async def _leg(session, oid, mid, name, is_winner, source, price=None):
    """Seed one leg.

    ``is_winner`` is named EXPLICITLY on every insert, including when it is
    NULL. A raw INSERT that omits it stores the server default `false`
    (`test_pg_gate_seed_completeness.py`), which is the very defect under test —
    a gate that forgot the column would seed the cohort by accident and then
    congratulate itself for finding it.
    """
    await session.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
            "is_winner, resolution_source, current_probability) VALUES "
            "(:id, :mid, :ext, :name, :w, :src, :p)"
        ),
        {
            "id": oid,
            "mid": mid,
            "ext": f"leg-{oid}",
            "name": name,
            "w": is_winner,
            "src": source,
            "p": price,
        },
    )


async def _is_winner(session, oid):
    return (
        await session.execute(
            text("SELECT is_winner FROM futures_outcomes WHERE id = :i"),
            {"i": oid},
        )
    ).scalar()


async def _seed_the_three_market_shapes(session):
    """The production classification, in miniature.

    Measured on production 2026-09-10: 277,519 markets with no winner and no
    badge (this rail's scope), 854 with a crowned winner, 118 with a badge but
    no winner. All three are seeded so the gate proves an EXCLUSION and not just
    an inclusion.
    """
    # 1. the cohort: nobody graded anything. Both legs read a fabricated loss.
    await _market(session, 8001)
    await _leg(session, 90011, 8001, "Yes", False, None, price=0.96)
    await _leg(session, 90012, 8001, "No", False, None, price=0.04)

    # 2. a crowned winner. The losing leg is un-badged but it REALLY LOST.
    await _market(session, 8002)
    await _leg(session, 90021, 8002, "Yes", True, "clean_resolution", price=1.0)
    await _leg(session, 90022, 8002, "No", False, None, price=0.0)

    # 3. no winner, but a leg carries a badge — something looked at this market.
    await _market(session, 8003)
    await _leg(session, 90031, 8003, "Yes", False, "all_losers", price=0.2)
    await _leg(session, 90032, 8003, "No", False, None, price=0.3)

    # 4. the same fabricated shape at ANOTHER VENUE. Kalshi's stock is real
    #    (26,675 legs / 2,174 markets, production 2026-09-10) and belongs to
    #    #4783, not here. A rail that quietly widened to every source would pass
    #    every other test in this file.
    await _market(session, 8004, source="kalshi")
    await _leg(session, 90041, 8004, "Yes", False, None, price=0.9)

    # 5. an OPEN market carrying the same shape. Pre-loaded to be wrong, but no
    #    reader sees a verdict on it yet and `pm-never-graded` scopes to
    #    resolved. Out of scope, deliberately.
    await _market(session, 8005, status="open")
    await _leg(session, 90051, 8005, "Yes", False, None, price=0.9)

    await session.commit()


async def test_the_bound_selects_only_the_ungraded_markets_legs(db):
    """Inclusion AND exclusion, on one seeded population."""
    await _seed_the_three_market_shapes(db)

    census = await rail.repair(db)

    assert census["terminal"] == "dry_run"
    assert {r["outcome_id"] for r in census["samples"]} == {90011, 90012}, (
        "the bound must take both legs of the ungraded market and nothing else"
    )
    assert census["markets"] == 1
    assert census["price_contradicted"] == 1  # the 0.96 leg


async def test_a_crowned_markets_losing_leg_is_never_withdrawn(db):
    """The 854-market class, stated as its own test because it is the harm.

    Withdrawing here would turn a genuine, correctly-rendered loss into
    "ungraded" — the same defect with the sign flipped, on the markets we got
    RIGHT.
    """
    await _seed_the_three_market_shapes(db)

    await rail.repair(db, apply=True)

    assert await _is_winner(db, 90022) is False, (
        "the losing leg of a crowned market lost, and must keep saying so"
    )
    assert await _is_winner(db, 90021) is True
    # ...and the badged-but-uncrowned market is left alone too.
    assert await _is_winner(db, 90032) is False


async def test_the_other_venues_stock_is_left_to_its_own_issue(db):
    """Kalshi (#4783) and open markets are out of scope, and stay out."""
    await _seed_the_three_market_shapes(db)

    await rail.repair(db, apply=True)

    assert await _is_winner(db, 90041) is False, "kalshi leg withdrawn — #4783's"
    assert await _is_winner(db, 90051) is False, "open market withdrawn"


async def test_the_apply_withdraws_and_the_result_is_a_fixed_point(db):
    """One pass writes; a second finds nothing left to do.

    If a withdrawn row stayed in the bound, the second pass would copy it into
    the backup at its NULL value — and `ON CONFLICT DO NOTHING` would be the
    only thing standing between the operator and an undo that restores nothing.
    """
    await _seed_the_three_market_shapes(db)

    first = await rail.repair(db, apply=True)
    assert first["terminal"] == "changed"
    assert first["changed"] == 2
    assert await _is_winner(db, 90011) is None
    assert await _is_winner(db, 90012) is None

    second = await rail.repair(db, apply=True)
    assert second["terminal"] == "nothing_to_do"
    assert second["changed"] == 0
    assert second["examined"] == 0


async def test_the_d51_undo_puts_the_verdict_back_exactly(db):
    """D51 is only satisfied if the restore is exact, so read the values back."""
    await _seed_the_three_market_shapes(db)
    await rail.repair(db, apply=True)

    dry = await rail.restore(db)
    assert dry["terminal"] == "dry_run"
    assert dry["backed_up_rows"] == 2
    assert dry["rows_differing_from_backup"] == 2
    assert dry["restored"] == 0

    done = await rail.restore(db, apply=True)
    assert done["terminal"] == "restored"
    assert done["restored"] == 2
    assert await _is_winner(db, 90011) is False
    assert await _is_winner(db, 90012) is False

    # Idempotent: nothing differs from the backup any more.
    again = await rail.restore(db, apply=True)
    assert again["restored"] == 0


async def test_the_anti_join_agrees_with_pm_never_graded_s_cohort_having(db):
    """Two definitions of one cohort is how a repair writes to rows a census
    never counted — `pm-never-graded` says so in its own comment.

    This rail pages by leg id, so it cannot use a `HAVING` without grouping the
    whole population per page. It uses an anti-join instead, and this is the
    proof the two select the same markets. `POPULATION_HAVING_SQL` is IMPORTED,
    never restated.
    """
    await _seed_the_three_market_shapes(db)

    having_markets = {
        r[0]
        for r in (
            await db.execute(
                text(f"""
                    SELECT fm.id
                    FROM futures_markets fm
                    JOIN futures_outcomes fo ON fo.market_id = fm.id
                    WHERE fm.source = 'polymarket' AND fm.status = 'resolved'
                    GROUP BY fm.id
                    {POPULATION_HAVING_SQL}
                """)
            )
        ).all()
    }

    census = await rail.repair(db)
    anti_join_markets = {r["market_id"] for r in census["samples"]}

    assert anti_join_markets == having_markets == {8001}


async def test_pm_never_graded_still_selects_a_withdrawn_market(db):
    """The interaction that makes withdrawal safe rather than merely appealing.

    `pm-never-graded` is the durable fix and it must still be able to grade what
    this rail withdrew. Its cohort turns on `bool_or(fo.is_winner) IS NOT TRUE`
    — and after a withdrawal every member is NULL, so `bool_or` yields NULL.
    `NULL IS NOT TRUE` is TRUE in Postgres, but that is precisely the kind of
    claim that should be asked of a server rather than reasoned about.
    """
    await _seed_the_three_market_shapes(db)
    await rail.repair(db, apply=True)

    still_in_cohort = {
        r[0]
        for r in (
            await db.execute(
                text(f"""
                    SELECT fm.id
                    FROM futures_markets fm
                    JOIN futures_outcomes fo ON fo.market_id = fm.id
                    WHERE fm.source = 'polymarket' AND fm.status = 'resolved'
                    GROUP BY fm.id
                    {POPULATION_HAVING_SQL}
                """)
            )
        ).all()
    }

    assert 8001 in still_in_cohort, (
        "the withdrawal removed a market from pm-never-graded's reach — the "
        "durable fix can no longer grade it"
    )


async def test_pm_never_graded_s_compare_and_set_still_matches_a_withdrawn_leg(db):
    """Its write is guarded by `resolution_source IS NULL AND is_winner IS NOT
    TRUE`. A withdrawn leg satisfies both — asserted by running the guard's own
    WHERE clause, because a CAS that silently matches nothing reports the same
    zero rowcount as a CAS that was beaten by another writer.
    """
    await _seed_the_three_market_shapes(db)
    await rail.repair(db, apply=True)

    matched = (
        await db.execute(
            text("""
                SELECT count(*) FROM futures_outcomes
                WHERE id IN (90011, 90012)
                  AND resolution_source IS NULL
                  AND is_winner IS NOT TRUE
            """)
        )
    ).scalar_one()

    assert matched == 2


# ---------------------------------------------------------------------------
# CERT-2524 — a grader committing underneath the apply
# ---------------------------------------------------------------------------


async def _grade_in_a_second_session(winner_id):
    """Commit a grade from a SEPARATE connection, exactly as a grader does.

    `pm-never-graded` writes one leg and commits it (`repair_pm_never_graded.py:
    1364-1382`), which is why a market is observable half-graded at all. The
    write here is a copy of its shape, not a call into it: this file's subject is
    what OUR statements do when somebody else's commit lands, and importing the
    grader would couple this gate to that rail's plan-and-approve machinery.

    The sibling leg is deliberately LEFT ALONE — an untouched sibling on a
    now-graded market is the row CERT-2524 said could be withdrawn to NULL.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as other:
            await other.execute(
                text(
                    "UPDATE futures_outcomes "
                    "SET is_winner = true, resolution_source = 'clob_never_graded' "
                    "WHERE id = :i"
                ),
                {"i": winner_id},
            )
            await other.commit()
    finally:
        await engine.dispose()


async def test_apply_cannot_withdraw_or_unback_a_page_when_a_grader_commits_between_backup_and_update(db):  # noqa: E501
    """The CERT-2524 race, run for real: two sessions, one commit, one window.

    The old apply re-ran a ``LIMIT``ed scope four times. Grading market 8001
    pushes both of its legs out of the bound, so the third and fourth runs of
    that query returned market 8006's legs instead — rows the backup step never
    saw. The write then changed them, and the "one command puts it back" promise
    in the module docstring quietly stopped being true for exactly the rows it
    had just altered.

    Two assertions, because the finding had two halves:

    * **no unbacked id changes** — 8006's legs were never planned, never backed
      up, and must not be touched however far the bound has moved.
    * **no leg of the newly graded market becomes NULL** — 90012 is the sibling
      the grader did not reach. It is now a genuine loss on a market with a
      crowned winner, which is the ONE shape this rail must never withdraw.
    """
    await _seed_the_three_market_shapes(db)
    # A second cohort market, further down the id order. Under the old code this
    # is what the re-run LIMIT reached for once 8001 left the bound.
    await _market(db, 8006)
    await _leg(db, 90061, 8006, "Yes", False, None, price=0.7)
    await _leg(db, 90062, 8006, "No", False, None, price=0.3)
    await db.commit()

    # limit=2 makes the page exactly market 8001's two legs, so a grade on 8001
    # empties the page and the LIMIT has somewhere to move to.
    census = await rail.repair(
        db,
        apply=True,
        limit=2,
        _between_backup_and_update=lambda: _grade_in_a_second_session(90011),
    )

    # -- the market the grader took --------------------------------------
    assert await _is_winner(db, 90011) is True, "the grader's verdict was clobbered"
    assert await _is_winner(db, 90012) is False, (
        "the untouched sibling of a newly graded market was withdrawn to NULL — "
        "a genuine loss re-rendered as ungraded, which is CERT-2524's harm"
    )

    # -- the rows the moving LIMIT used to reach --------------------------
    assert await _is_winner(db, 90061) is False, (
        "an id the plan never saw was changed — it has no backup row, so the "
        "D51 undo cannot reach it"
    )
    assert await _is_winner(db, 90062) is False

    # -- and the backup describes exactly what happened -------------------
    assert census["changed"] == 0
    assert census["conceded_to_a_grader"] == 2, (
        "the concession must be reported: a page that quietly wrote nothing "
        "reads identically to a page that had nothing to do"
    )
    backed_up = (
        await db.execute(text(f"SELECT count(*) FROM {rail.BAK_TABLE}"))
    ).scalar_one()
    assert backed_up == 0, (
        "a backup row survived for a leg we did not change — a later undo would "
        "push our remembered `false` over the grader's verdict"
    )


async def test_every_row_the_apply_changed_is_recoverable_from_the_backup(db):
    """The invariant the join buys, asserted as set equality on real rows.

    Not "the counts match" — two counts can agree while naming different rows,
    which is the same reasoning `_BAK_MISSING` is written as a COUNT OVER THE
    BOUND for.
    """
    await _seed_the_three_market_shapes(db)

    await rail.repair(db, apply=True)

    withdrawn = {
        r[0]
        for r in (
            await db.execute(
                text("SELECT id FROM futures_outcomes WHERE is_winner IS NULL")
            )
        ).all()
    }
    backed = {
        r[0]
        for r in (
            await db.execute(text(f"SELECT outcome_id FROM {rail.BAK_TABLE}"))
        ).all()
    }

    assert withdrawn == backed == {90011, 90012}


async def test_the_undo_leaves_alone_a_leg_somebody_graded_after_the_withdrawal(db):
    """A late undo must not overwrite a verdict written since the apply.

    This is CERT-2516's `4745-RESTORE-PRESERVES-POST-REPAIR-REPRICING` arriving
    at this rail by construction: the withdrawal is what MAKES the leg gradeable
    by `pm-never-graded`, so "graded after the withdrawal" is the expected
    sequence, not an edge case. Restoring `false` over it would re-create the
    fabricated `Lost` on a market that has since been graded honestly.
    """
    await _seed_the_three_market_shapes(db)
    await rail.repair(db, apply=True)
    assert await _is_winner(db, 90011) is None

    # `pm-never-graded` does its job on the market this rail just withdrew.
    await db.execute(
        text(
            "UPDATE futures_outcomes "
            "SET is_winner = true, resolution_source = 'clob_never_graded' "
            "WHERE id = :i"
        ),
        {"i": 90011},
    )
    await db.commit()

    census = await rail.restore(db, apply=True)

    assert await _is_winner(db, 90011) is True, "the undo clobbered a real verdict"
    assert await _is_winner(db, 90012) is False, "the ungraded leg was not put back"
    assert census["restored"] == 1
    assert census["skipped_now_graded"] == 1, (
        "the skip has to be a number an operator can see, not a shortfall they "
        "have to work out by subtracting"
    )


async def test_the_page_boundary_does_not_strand_a_half_withdrawn_market(db):
    """A market whose legs straddle two pages must stay in scope for the second.

    The gate asks whether any leg carries a GRADE; a half-withdrawn market still
    carries none, so the remaining legs stay selectable. If the gate had been
    written as "no leg is false" instead, page two would have skipped them and
    the market would print one `Lost` for ever.
    """
    await _seed_the_three_market_shapes(db)

    first = await rail.repair(db, apply=True, limit=1)
    assert first["changed"] == 1
    assert first["scan_exhausted"] is False

    second = await rail.repair(db, apply=True, limit=1)
    assert second["changed"] == 1

    assert await _is_winner(db, 90011) is None
    assert await _is_winner(db, 90012) is None
