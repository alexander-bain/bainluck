"""D5 / ruling 125 with the sign reversed — the ``clean_vms`` join must carry
every dimension ``vm_stats`` is grouped on, or the curve publishes rows twice.

THE DEFECT. ``vm_stats`` GROUPs BY FIVE columns —
``(vm_id, source, category, is_grouped, mutually_exclusive)`` — while the join
that re-attaches those statistics to the outcomes carried TWO. A virtual market
whose member markets disagree on any of the other three therefore holds one
``clean_vms`` row PER VARIANT, and the two-column join matched every one of
them: every outcome in that virtual market was emitted once per variant.

Measured before the fix (``alex-inbox/calibration-911``, with
``artifacts/cal-p139``, ``cal-p141``, ``cal-p142``):

  * 18,363 of 18,378 groups of >=3 resolved markets — **99.9%** — carry mixed
    identity, covering 259,859 of 259,925 markets;
  * on the 13 cells folded exactly on the payload basis, **420,081 published
    rows are 266,137 distinct: 36.65% phantom, 1.5784x**, ranging from 0.35%
    (``polymarket/weather``) to 47.08% (``kalshi/hockey``);
  * ``polymarket/baseball`` alone: 45,240 published rows -> 25,107 distinct.

RULING 125, THE SAME CHAIN, THREE CTEs EARLIER. 125 ruled that a join whose key
is coarser than the identity of the rows it can DELETE silently picks a winner
across a dimension nobody declared. The same coarse key here MULTIPLIES instead.
The remedy is identical: carry every dimension the aggregate is grouped on.

🔴 WHY IT SURVIVED A DEDICATED AUDIT, and why this file exists rather than a
string assertion. The producer's own comment cited this pair as the model
citizen — *"``vm_stats`` GROUPs BY ``(vm_id, source)``, ``clean_vms`` JOINs on
both"* — and ruling 125's text repeated it. Both halves were false. The audit
read the first two columns of the ``GROUP BY`` and stopped. A string assertion
written from the same misreading would have been green throughout. The claim
under test is relational — *"one outcome, one published row"* — so it is proved
by seeding one virtual market whose members disagree and COUNTING.

RED-FIRST, EXECUTED IN THIS FILE. Like the two mode-price gates beside it this
module is two-armed: it builds the reverted (two-column) join by textual
surgery on the production string and EXECUTES it, asserting the duplication
comes back. A green run therefore means red-first was proved in CI, not that
nothing objected.

AND THE FALSIFIER, which matters more here than in a deletion defect. A
de-duplication that also LOSES rows is strictly worse than the duplication it
removes, and it would be invisible in any count that only checks "no row
appears twice". Every arm below asserts the published SET is unchanged and only
the MULTIPLICITY falls.

THE CRICKET REGRESSION CONTROL (directive 2026-08-30 item 1a). Cricket is under
re-investigation on the presumption that the defect is OURS (ruling D14, Alex:
*"Markets aren't wrong; calculations are"*), and this change moves the cricket
cell's population underneath that hunt. So one variant of the fixture is
seeded as cricket and graded on its own: cricket's outcomes must go from two
rows each to one row each with the SAME outcome set, which is what makes any
post-lift movement in the cricket cell attributable to re-weighting alone and
never to rows appearing or vanishing. A reinvestigation that cannot tell those
two apart is not a reinvestigation.

Gated on a throwaway Postgres. CI arms it through the ``search-recall`` job's
service container (``SEARCH_TEST_DATABASE_URL``). There is no local Postgres in
the agent sandbox (``initdb`` dies on ``shmget``), so CI is the only environment
that runs it — which is why this file is named in the job explicitly and in
``tests/test_pg_gate_seed_completeness.py``'s ``COVERED``.
"""

import os
from datetime import datetime, timezone

import pytest

DB_URL = os.environ.get("CALIBRATION_TEST_DATABASE_URL") or os.environ.get(
    "SEARCH_TEST_DATABASE_URL"
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL (CI's service container) or "
            "CALIBRATION_TEST_DATABASE_URL to run the D5 vm-variant join gate"
        ),
    ),
]

# Ids far from every other gate in this job, and inside int32 — `events.id` is
# `Mapped[int]`, i.e. INTEGER, and an out-of-range literal makes every INSERT
# and the cleanup DELETE raise asyncpg DataError. That trap has already cost
# this suite one silently-collected-never-executed gate (CAL-P090 -> CAL-P091).
EVENT_ID = 771500001
SPORT_ID = 77150

# One event, one source, FOUR resolved markets -> `event_sizes` counts 4 for
# (event_id, source), the >=3 gate fires, and all four are assigned the SAME
# `vm_id = 'e:<event_id>'` with `is_grouped = true`. That is one virtual market.
#
# They disagree on `category`, which is one of the three dimensions `vm_stats`
# groups on and the join did not carry. Two categories => TWO `clean_vms` rows
# for one virtual market => every outcome matched twice by the old join.
#
# `category` is the dimension exercised because it is the one that can be varied
# without leaving the market shape this job has already proved reaches
# `deduped`: single outcome, `mutually_exclusive = false`, `market_type =
# 'binary'`, a real trade. Varying `mutually_exclusive` instead would change the
# normalization arm as well and the gate would no longer be measuring one thing.
# `is_grouped` cannot vary within a virtual market at all — every member of an
# `e:` or `g:` vm derives the same value — and is carried in the fix for
# completeness rather than because a fixture can exercise it.
CRICKET_LEGS = {771501: 0.20, 771502: 0.40}
BASEBALL_LEGS = {771503: 0.60, 771504: 0.80}
LEG_CATEGORY = {
    **{mid: "cricket" for mid in CRICKET_LEGS},
    **{mid: "baseball" for mid in BASEBALL_LEGS},
}
ALL_LEGS = {**CRICKET_LEGS, **BASEBALL_LEGS}
ALL_IDS = sorted(ALL_LEGS)

# ── CERT-485 P1-a: the ASYMMETRIC fixture ────────────────────────────────────
# The fixture above cannot see the residual class, and the cert said so by line
# number: every variant it seeds has ``has_winner == 2``, so every variant is
# admitted to `clean_vms` on its own and the five-column join can only ever
# REMOVE a duplicate. The class D5 changes is the one where a variant is NOT
# admitted and the old two-column join let its outcomes ride a SIBLING
# variant's admission row.
#
# So: one more virtual market, on its own event, whose two variants are
# asymmetric.
#
#   * the LOSS variant — two one-outcome markets, both graded FALSE by an
#     eligible authority. `has_winner = 0`, so the `has_winner >= 1` arm
#     refuses it; `market_count = 2`, so D13's lone-claim arm
#     (`market_count = 1 AND total_outcomes = 1 AND graded >= 1`) refuses it
#     too — the counts in `vm_stats` are per VARIANT, not per market.
#   * the WINNER variant — two one-outcome markets that won, so it IS admitted.
#
# Single-outcome markets on purpose: `no_winner_markets` (Queue 299 rung 1)
# needs `n_outcomes >= 2`, and `malformed_binaries` needs exactly 2. Neither
# fires here, so what these rows do or do not do is attributable to the join
# and to `clean_vms`, and to nothing else.
ASYM_EVENT_ID = 771500011
ASYM_SPORT_ID = 77151
ASYM_LOSS_LEGS = {771511: 0.15, 771512: 0.35}
ASYM_WIN_LEGS = {771513: 0.55, 771514: 0.75}
ASYM_LEG_CATEGORY = {
    **{mid: "cricket" for mid in ASYM_LOSS_LEGS},
    **{mid: "baseball" for mid in ASYM_WIN_LEGS},
}
ASYM_LEGS = {**ASYM_LOSS_LEGS, **ASYM_WIN_LEGS}
ASYM_IDS = sorted(ASYM_LEGS)

# Four DISTINCT prices on purpose. `mode_prices` deletes a price shared by more
# than GREATEST(eligible/2, 2) legs; with every price unique no mode can form,
# so nothing this gate publishes or withholds is attributable to that mechanism.
# A gate whose subject can be confused with its neighbour's is not a gate.

#: The production join, post-fix, as `_calibration_population_ctes` emits it.
#: Pinned so the reverted arm below fails LOUDLY if the fix is reshaped rather
#: than silently reverting nothing and passing.
FIXED_JOIN = (
    "                JOIN clean_vms cv\n"
    "                  ON cv.vm_id = vm.vm_id\n"
    "                 AND cv.source = vm.source\n"
    "                 AND cv.category IS NOT DISTINCT FROM vm.category\n"
    "                 AND cv.is_grouped IS NOT DISTINCT FROM vm.is_grouped\n"
    "                 AND cv.mutually_exclusive"
    " IS NOT DISTINCT FROM vm.mutually_exclusive\n"
)

#: The pre-fix join, verbatim from the file's history. Executing this is what
#: makes the run red-first rather than merely green.
REVERTED_JOIN = (
    "                JOIN clean_vms cv ON cv.vm_id = vm.vm_id"
    " AND cv.source = vm.source\n"
)


def _reverted(ctes: str) -> str:
    """The production chain with ONLY the D5 conjuncts removed.

    Textual surgery on the real string, not a hand-copied chain: a second copy
    of 4,000 lines of SQL would drift, and a drifted copy that still reproduced
    the duplication would prove nothing about the producer.
    """
    assert FIXED_JOIN in ctes, (
        "PREMISE GONE: the D5 five-column `clean_vms` join is not in the built "
        "SQL in the shape this gate reverts. Do not delete this gate — re-aim "
        "it at the new shape, or the red-first arm silently stops reverting "
        "anything and every assertion below passes vacuously."
    )
    return ctes.replace(FIXED_JOIN, REVERTED_JOIN, 1)


async def _seed_leg(session, market_id, *, price, category, event_id=None, winner=True):
    """One resolved single-outcome market on the shared event.

    ``winner`` is the CERT-485 P1-a parameter. At its default the leg carries
    its own winner, so it is not a market that "graded nobody"
    (`is_no_winner_market` requires n_outcomes >= 2 anyway) and not a 2-outcome
    mex binary with a bad winner count. `mutually_exclusive` false and
    `market_type='binary'` keep it out of the mex/field normalization arm.

    ``winner=False`` writes `is_winner = false` — an AFFIRMATIVE graded loss,
    not the nullable default. That distinction is the whole point of the
    asymmetric fixture: `vm_stats.graded` counts `is_winner IS NOT NULL`, so a
    row nothing ever graded and a row graded a loss are different rows, and only
    the second may be published (gotcha #21).
    """
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO futures_markets (id, external_id, name, source, status, "
            "category, event_id, mutually_exclusive, market_type, "
            "llm_sport_category, volume) "
            "VALUES (:id, :xid, :nm, 'polymarket', 'resolved', 'championship', "
            ":ev, false, 'binary', :cat, 100)"
        ),
        {
            "id": market_id,
            "xid": f"test-d5-{market_id}",
            "nm": f"market-{market_id}",
            "ev": EVENT_ID if event_id is None else event_id,
            "cat": category,
        },
    )
    await session.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
            "opening_probability, calibration_probability, is_winner, "
            "resolution_source, volume) VALUES "
            "(:id, :mid, :xid, :nm, :p, :p, :win, 'api_settlement', 10)"
        ),
        {
            "id": market_id,
            "mid": market_id,
            "xid": f"test-d5-out-{market_id}",
            "nm": f"leg-{market_id}",
            "p": price,
            "win": winner,
        },
    )
    # A real trade: without it the Polymarket legs are never-traded placeholders
    # and `POLY_PLACEHOLDER_EXCLUDE` removes them. The assertions below would
    # then pass for a reason with nothing to do with the join under test.
    await session.execute(
        text(
            "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, probability, "
            "reading_count, last_price, yes_bid) VALUES "
            "(:oid, 'test-d5', :p, 1, :p, :p)"
        ),
        {"oid": market_id, "p": price},
    )


async def _seed(session):
    from sqlalchemy import text

    await session.execute(
        text("INSERT INTO sports (id, key, name, active) VALUES (:id, :k, :n, true)"),
        {"id": SPORT_ID, "k": f"test_d5_{SPORT_ID}", "n": "Test D5"},
    )
    await session.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status) VALUES "
            "(:id, :sid, 'Home D5', 'Away D5', :ct, 'completed')"
        ),
        {
            "id": EVENT_ID,
            "sid": SPORT_ID,
            "ct": datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc).replace(tzinfo=None),
        },
    )
    for mid, price in ALL_LEGS.items():
        await _seed_leg(session, mid, price=price, category=LEG_CATEGORY[mid])
    await session.commit()


async def _cleanup(session):
    from sqlalchemy import text

    await session.execute(
        text("DELETE FROM futures_odds_snapshots WHERE outcome_id = ANY(:ids)"),
        {"ids": ALL_IDS},
    )
    await session.execute(
        text("DELETE FROM futures_outcomes WHERE id = ANY(:ids)"), {"ids": ALL_IDS}
    )
    await session.execute(
        text("DELETE FROM futures_markets WHERE id = ANY(:ids)"), {"ids": ALL_IDS}
    )
    await session.execute(text("DELETE FROM events WHERE id = :id"), {"id": EVENT_ID})
    await session.execute(text("DELETE FROM sports WHERE id = :id"), {"id": SPORT_ID})
    await session.commit()


async def _rows(session, ctes, ids):
    """``(outcome_id, category)`` per published row — MULTIPLICITY PRESERVED.

    Deliberately not a set and not a COUNT: the whole subject is how many rows
    one outcome produces, so an instrument that collapsed them could not see
    the defect it exists to catch.
    """
    from sqlalchemy import text

    return [
        (r.outcome_id, r.category)
        for r in (
            await session.execute(
                text(
                    "WITH "
                    + ctes
                    + " SELECT outcome_id, category FROM deduped "
                    "WHERE outcome_id = ANY(:ids) ORDER BY outcome_id, category"
                ),
                {"ids": ids},
            )
        ).all()
    ]


async def _seed_asym(session):
    """The CERT-485 P1-a fixture: one vm, a LOSS-ONLY variant and a WINNER variant."""
    from sqlalchemy import text

    await session.execute(
        text("INSERT INTO sports (id, key, name, active) VALUES (:id, :k, :n, true)"),
        {"id": ASYM_SPORT_ID, "k": f"test_d5_{ASYM_SPORT_ID}", "n": "Test D5 asym"},
    )
    await session.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status) VALUES "
            "(:id, :sid, 'Home D5a', 'Away D5a', :ct, 'completed')"
        ),
        {
            "id": ASYM_EVENT_ID,
            "sid": ASYM_SPORT_ID,
            "ct": datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc).replace(tzinfo=None),
        },
    )
    for mid, price in ASYM_LEGS.items():
        await _seed_leg(
            session,
            mid,
            price=price,
            category=ASYM_LEG_CATEGORY[mid],
            event_id=ASYM_EVENT_ID,
            winner=mid in ASYM_WIN_LEGS,
        )
    await session.commit()


async def _cleanup_asym(session):
    from sqlalchemy import text

    await session.execute(
        text("DELETE FROM futures_odds_snapshots WHERE outcome_id = ANY(:ids)"),
        {"ids": ASYM_IDS},
    )
    await session.execute(
        text("DELETE FROM futures_outcomes WHERE id = ANY(:ids)"), {"ids": ASYM_IDS}
    )
    await session.execute(
        text("DELETE FROM futures_markets WHERE id = ANY(:ids)"), {"ids": ASYM_IDS}
    )
    await session.execute(
        text("DELETE FROM events WHERE id = :id"), {"id": ASYM_EVENT_ID}
    )
    await session.execute(
        text("DELETE FROM sports WHERE id = :id"), {"id": ASYM_SPORT_ID}
    )
    await session.commit()


async def _with_seeded_db(body, *, seed=None, cleanup=None):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    seed = seed or _seed
    cleanup = cleanup or _cleanup
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            await cleanup(session)
            await seed(session)
            try:
                await body(session)
            finally:
                await cleanup(session)
    finally:
        await engine.dispose()


async def test_the_premise_one_virtual_market_really_does_hold_two_variants():
    """Asserted, not assumed — and it is the assumption the audit got wrong.

    If a later change makes `vm_id` carry `category`, or drops `category` from
    `vm_stats`' GROUP BY, this gate's subject disappears. It must say so out
    loud rather than pass vacuously, which is exactly how the original defect
    survived: a check that reads the first two columns and stops.
    """
    from sqlalchemy import text

    from app.tasks.precompute_calibration import _calibration_population_ctes

    async def body(session):
        ctes = _calibration_population_ctes()
        variants = (
            await session.execute(
                text(
                    "WITH "
                    + ctes
                    + " SELECT vm_id, source, category, is_grouped, "
                    "mutually_exclusive, market_count, total_outcomes, "
                    "has_winner, eligible FROM clean_vms "
                    "WHERE vm_id = :vm ORDER BY category"
                ),
                {"vm": f"e:{EVENT_ID}"},
            )
        ).all()

        assert len(variants) == 2, (
            "PREMISE GONE: one virtual market must hold TWO `clean_vms` rows "
            f"for this gate to have a subject (got {variants!r})"
        )
        assert [v.category for v in variants] == ["baseball", "cricket"]
        # Both variants pass the gate on their own, so neither is admitted or
        # refused because of the other. Without this the row count below could
        # move for a reason that is not the join.
        for v in variants:
            assert v.is_grouped is True
            assert v.market_count == 2 and v.total_outcomes == 2
            assert v.has_winner == 2 and v.eligible == 2

    await _with_seeded_db(body)


async def test_every_outcome_publishes_exactly_once():
    """THE FIX, and its falsifier, in one reading.

    Four outcomes in one virtual market of two variants. Post-fix each publishes
    ONCE. The reverted arm publishes each TWICE — and publishes the same four
    outcomes, which is what proves the defect was duplication rather than
    anything about which rows are eligible.
    """
    from app.tasks.precompute_calibration import _calibration_population_ctes

    async def body(session):
        ctes = _calibration_population_ctes()

        fixed = await _rows(session, ctes, ALL_IDS)
        assert sorted(oid for oid, _ in fixed) == ALL_IDS, (
            "THE FALSIFIER: de-duplication must not LOSE a row. Every seeded "
            f"outcome must still publish exactly once. got={fixed!r}"
        )
        assert len(fixed) == len(ALL_IDS), (
            "an outcome still publishes more than once — the five-column join "
            f"is not doing its job. got={fixed!r}"
        )
        # And each row carries ITS OWN market's category, not the other
        # variant's. Under the old join an outcome was emitted once per variant
        # and therefore appeared under a category its market never had, which is
        # a mis-attribution as well as a duplication.
        for oid, category in fixed:
            assert category == LEG_CATEGORY[oid], (
                f"outcome {oid} published under category {category!r}; its "
                f"market's category is {LEG_CATEGORY[oid]!r}"
            )

        # RED-FIRST, EXECUTED. The pre-fix chain, on the same seed, in the same
        # session.
        before = await _rows(session, _reverted(ctes), ALL_IDS)
        assert len(before) == 2 * len(ALL_IDS), (
            "the reverted arm did not reproduce the duplication, so this run "
            "proves nothing about the fix. Either the revert no longer reverts "
            f"the defect or the fixture no longer exercises it. got={before!r}"
        )
        assert sorted({oid for oid, _ in before}) == ALL_IDS, (
            "the defect is duplication, not exclusion: the reverted arm must "
            f"publish the SAME four outcomes, twice each. got={before!r}"
        )


    await _with_seeded_db(body)


async def test_the_cricket_shape_deduplicates_and_loses_nothing():
    """THE CRICKET REGRESSION CONTROL (directive 2026-08-30 item 1a).

    Cricket is being re-investigated under D14 on the presumption that the
    defect is ours, and this change moves cricket's population underneath that
    hunt. The control the reinvestigation needs is narrow and it is this: the
    dedup may change cricket's row MULTIPLICITY and nothing else.

    Graded on its own rather than folded into the arm above so that a failure
    names cricket. If cricket's published outcome SET ever moves under this
    change, every subsequent cricket measurement is comparing two populations
    and the "is it us?" question becomes unanswerable — which is the one
    outcome the overrule was issued to prevent.
    """
    from app.tasks.precompute_calibration import _calibration_population_ctes

    async def body(session):
        ctes = _calibration_population_ctes()
        cricket = sorted(CRICKET_LEGS)

        before = await _rows(session, _reverted(ctes), cricket)
        after = await _rows(session, ctes, cricket)

        assert sorted({oid for oid, _ in before}) == cricket
        assert sorted(oid for oid, _ in after) == cricket, (
            "cricket LOST a published outcome to the dedup. Any cell "
            "measurement across this change is now comparing two populations."
        )
        assert len(before) == 2 * len(cricket) and len(after) == len(cricket), (
            f"cricket multiplicity did not fall 2x -> 1x (before={before!r} "
            f"after={after!r})"
        )
        assert {c for _, c in after} == {"cricket"}

    await _with_seeded_db(body)


# =============================================================================
# CERT-485 P1-a — the residual class, seeded and RULED.
#
# THE FINDING. `clean_vms` admits a variant only when it has a winner, or when
# D13's lone-claim arm fires (`market_count = 1 AND total_outcomes = 1 AND
# graded >= 1`). Those counts are per VARIANT. So a variant holding TWO
# independently-graded lone claims that both LOST is admitted by neither arm,
# and D5's exact five-column join — correctly — finds no `clean_vms` row for
# it. Under the old two-column join those rows published anyway, by matching a
# SIBLING variant's admission row. D5 does not create the exclusion; it removes
# the accident that was hiding it.
#
# 🔴 WHY THE GATE ABOVE CANNOT SEE THIS, quoted from the cert: every variant the
# main fixture seeds has `has_winner == 2`
# (`test_the_premise_one_virtual_market_really_does_hold_two_variants`, the
# `for v in variants` block). A fixture in which every variant is admitted can
# only ever exercise de-duplication. This section is the asymmetric case, and it
# is deliberately NOT a narrowing of the fixture above — the cert named that
# escape by name and refused it in advance.
#
# THE RULING (alex-inbox/calibration-919, option B — the lane's recommendation,
# taken on the "if you say nothing" default). The exclusion STANDS and is
# written down as ruled rather than accidental:
#
#   * Per-VARIANT is the shipped behaviour. A variant is the unit `vm_stats`
#     aggregates and the unit `clean_vms` admits; admitting a lone claim
#     per-MARKET instead would change the published population by an unmeasured
#     amount, and the freeze-lift it would ride is mid-cert.
#   * Per-MARKET (option A) is arguably more correct by D13's own argument —
#     each of these rows IS "a complete, scoreable prediction" — and it is
#     staged as its own queue, behind its own rebuild, not smuggled in here.
#   * What is NOT acceptable is either one being true by accident. Hence this
#     gate: if the arm is ever changed to per-market, the assertion below fails
#     and names the ruling it is reversing.
# =============================================================================


async def test_the_asymmetric_premise_a_loss_only_variant_is_not_admitted():
    """CERT-485 P1-a, the premise — asserted, because it is what the cert found.

    Two variants of one virtual market. One is admitted, one is refused, and the
    refused one is refused for the stated reason and no other: `has_winner = 0`
    closes the first arm, `market_count = 2` closes D13's. `graded = 2` is
    asserted too — these are AFFIRMATIVE losses, so the row is not being
    excluded as unknown truth (Queue 299 rung 1), which is a different and
    already-ruled exclusion.
    """
    from sqlalchemy import text

    from app.tasks.precompute_calibration import _calibration_population_ctes

    async def body(session):
        ctes = _calibration_population_ctes()
        stats = (
            await session.execute(
                text(
                    "WITH "
                    + ctes
                    + " SELECT category, market_count, total_outcomes, has_winner, "
                    "graded, eligible FROM vm_stats WHERE vm_id = :vm "
                    "ORDER BY category"
                ),
                {"vm": f"e:{ASYM_EVENT_ID}"},
            )
        ).all()
        assert [s.category for s in stats] == ["baseball", "cricket"], (
            "PREMISE GONE: the asymmetric vm must still hold two variants "
            f"(got {stats!r})"
        )
        loss = {s.category: s for s in stats}["cricket"]
        win = {s.category: s for s in stats}["baseball"]

        assert loss.has_winner == 0 and loss.graded == 2, (
            "the loss variant must carry two AFFIRMATIVE graded losses and no "
            f"winner, or this gate is testing unknown truth instead (got {loss!r})"
        )
        assert loss.market_count == 2 and loss.total_outcomes == 2, (
            "the loss variant must hold TWO lone claims — one would be admitted "
            f"by D13's arm and there would be no finding (got {loss!r})"
        )
        assert loss.eligible == 2
        assert win.has_winner == 2 and win.market_count == 2

        admitted = [
            r.category
            for r in (
                await session.execute(
                    text(
                        "WITH "
                        + ctes
                        + " SELECT category FROM clean_vms WHERE vm_id = :vm "
                        "ORDER BY category"
                    ),
                    {"vm": f"e:{ASYM_EVENT_ID}"},
                )
            ).all()
        ]
        assert admitted == ["baseball"], (
            "PREMISE GONE: `clean_vms` must admit exactly the winner variant. "
            "If the loss variant is now admitted, D13's arm was changed to "
            "per-market (option A of alex-inbox/calibration-919) — that is a "
            "ruling reversal and a published-population change, and it must be "
            f"landed with a rebuild and a measured headline, not here. got={admitted!r}"
        )

    await _with_seeded_db(body, seed=_seed_asym, cleanup=_cleanup_asym)


async def test_loss_only_variant_rows_are_excluded_and_the_old_join_published_them():
    """CERT-485 P1-a, the behaviour — and the row loss stated out loud.

    RED-FIRST IN REVERSE. Every other arm in this file executes the reverted
    join to prove the DEFECT comes back. Here the reverted join is what proves
    the finding is real: under the two-column key the loss-only variant's rows
    published, riding the sibling variant's admission row. So this arm is the
    evidence for the cert's claim and the fixed arm is the disclosed
    consequence — the population D5 ships is two rows smaller on this fixture,
    on purpose.

    THE FALSIFIER, and it is the one that matters. D5 must not lose the WINNER
    variant's rows. A join that removes duplicates by removing rows nobody
    ruled on is the failure mode this whole file is written against, so the
    surviving set is asserted exactly, not merely counted.
    """
    from app.tasks.precompute_calibration import _calibration_population_ctes

    async def body(session):
        ctes = _calibration_population_ctes()

        before = await _rows(session, _reverted(ctes), ASYM_IDS)
        after = await _rows(session, ctes, ASYM_IDS)

        assert sorted(oid for oid, _ in before) == ASYM_IDS, (
            "the two-column join must publish ALL FOUR outcomes — the loss-only "
            "variant's two rows ride the winner variant's `clean_vms` row. If "
            "they do not, the P1-a finding is no longer reproducible by this "
            f"fixture and the disclosure below is describing nothing. got={before!r}"
        )
        # Multiplicity, so the two effects are not confused. The loss rows match
        # exactly ONE clean_vms row (the sibling), so nothing here is doubled —
        # this fixture isolates row LOSS from row duplication.
        assert len(before) == len(ASYM_IDS), (
            f"the asymmetric fixture must not also duplicate (got {before!r})"
        )
        # And they published under the SIBLING's category, which is the tell:
        # the row was admitted by a variant its market is not a member of.
        assert {oid: cat for oid, cat in before if oid in ASYM_LOSS_LEGS} == {
            oid: "baseball" for oid in ASYM_LOSS_LEGS
        }, (
            "the loss rows must publish under the sibling variant's category "
            f"under the old join — that IS the accident. got={before!r}"
        )

        assert sorted(oid for oid, _ in after) == sorted(ASYM_WIN_LEGS), (
            "RULED (alex-inbox/calibration-919, option B): the loss-only variant "
            "is excluded per-VARIANT and the winner variant is untouched. A "
            "change here is a change to the published population — if the loss "
            "rows came back, D13's arm went per-market; if a winner row went "
            f"missing, D5 is losing rows nobody ruled on. got={after!r}"
        )
        assert all(cat == "baseball" for _, cat in after)

    await _with_seeded_db(body, seed=_seed_asym, cleanup=_cleanup_asym)
