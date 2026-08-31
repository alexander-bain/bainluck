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
# So: one more virtual market, on its own event, whose variants are asymmetric.
#
#   * the LOSS variant — two one-outcome markets, both graded FALSE by an
#     eligible authority. `has_winner = 0`, so the `has_winner >= 1` arm
#     refuses it. Under the RETIRED per-variant arm
#     (`market_count = 1 AND total_outcomes = 1 AND graded >= 1`) D13's arm
#     refused it too, because those counts were per VARIANT.
#   * the WINNER variant — two one-outcome markets that won, so it IS admitted.
#   * the MIXED variant (CAL-P155) — one graded loss beside one lone claim
#     nothing ever graded.
#
# 🔴 CAL-P155 — ALEX RULED OPTION A AND THIS SECTION IS INVERTED, NOT DELETED.
# `alex-inbox/calibration-919`, 2026-08-30: the arm counts PER MARKET, so each of
# those two graded lone claims is admitted on its own account. The LOSS variant
# now publishes. Every assertion below moved with the ruling and each one names
# it, because what is not acceptable is either behaviour being true by accident.
#
# 🔴 CAL-P156 / CERT-514 — AND THE MIXED VARIANT'S EXPECTATION IS INVERTED IN
# TURN. CAL-P155 refused it whole, on `ungraded_lone_claims = 0`, and the cert
# blocked that: refusing the variant to keep ONE ungraded row out also withheld
# the graded loss beside it, so a scoreable claim's fate still hung on a SIBLING
# market — the coupling option A exists to remove. The variant is now ADMITTED
# and the refusal moved down a grain to rung 1b
# (`ungraded_lone_claim_markets`), which removes the ungraded member per market.
# This fixture is the only thing that executes that SPLIT against a real
# Postgres, and it takes two tests to pin it honestly: one for the published
# rows and one for the flag, because "the row is absent" is equally true of the
# residue that was removed.
#
# Single-outcome markets on purpose: `no_winner_markets` (Queue 299 rung 1)
# needs `n_outcomes >= 2`, and `malformed_binaries` needs exactly 2. Neither
# fires here — rung 1b is the ONLY rung that touches these rows, so what they do
# or do not do is attributable to it, to the join and to `clean_vms`, and to
# nothing else.
ASYM_EVENT_ID = 771500011
ASYM_SPORT_ID = 77151
ASYM_LOSS_LEGS = {771511: 0.15, 771512: 0.35}
ASYM_WIN_LEGS = {771513: 0.55, 771514: 0.75}
#: The MIXED variant (CAL-P155; CERT-514 inverted what it proves). One
#: AFFIRMATIVE graded loss beside one lone claim whose `is_winner` was never
#: written — seeded NULL, not the False default, which is the ambiguity
#: gotcha #21 is about. Rung 1b must SPLIT this pair.
ASYM_UNKNOWN_LEGS = {771515: 0.45, 771516: 0.65}
#: The scoreable half of the mixed variant: option A says it publishes on its
#: own account, whatever its ungraded neighbour's state.
ASYM_MIXED_GRADED_LEG = 771515
#: The unknown-truth half: admitted with its variant, then removed by rung 1b.
ASYM_UNGRADED_LEG = 771516
ASYM_LEG_CATEGORY = {
    **{mid: "cricket" for mid in ASYM_LOSS_LEGS},
    **{mid: "baseball" for mid in ASYM_WIN_LEGS},
    **{mid: "tennis" for mid in ASYM_UNKNOWN_LEGS},
}
#: `None` means seed `is_winner` NULL. `False` is an affirmative graded loss.
ASYM_LEG_WINNER = {
    **{mid: False for mid in ASYM_LOSS_LEGS},
    **{mid: True for mid in ASYM_WIN_LEGS},
    ASYM_MIXED_GRADED_LEG: False,
    ASYM_UNGRADED_LEG: None,
}
ASYM_LEGS = {**ASYM_LOSS_LEGS, **ASYM_WIN_LEGS, **ASYM_UNKNOWN_LEGS}
ASYM_IDS = sorted(ASYM_LEGS)
#: What the RULED producer publishes from this fixture (CERT-514): both admitted
#: variants whole, PLUS the graded member of the mixed variant — and NOT its
#: ungraded neighbour, which rung 1b removes at market grain. The whole point of
#: option A is that this list SPLITS a variant instead of taking or leaving it.
ASYM_PUBLISHED = sorted(
    {*ASYM_LOSS_LEGS, *ASYM_WIN_LEGS, ASYM_MIXED_GRADED_LEG}
)

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


async def _match_production_is_winner_nullability(session):
    """Make `futures_outcomes.is_winner` NULLABLE, the way production has it.

    🔴 THE MODEL AND PRODUCTION DISAGREE, AND THIS GATE IS THE ONLY PLACE IT
    MATTERS. `models.py:849` declares ``is_winner: Mapped[bool] =
    mapped_column(Boolean, default=False)`` — a non-Optional annotation, so
    SQLAlchemy infers ``nullable=False`` and ``Base.metadata.create_all`` builds
    the column **NOT NULL**. Production has it **NULLABLE with a False default**
    (`information_schema.columns`, measured 2026-08-31: `is_nullable = YES`,
    `column_default = false`).

    That drift is not cosmetic here. The entire 12-CAL argument, gotcha #21 and
    D13's `graded` conjunct rest on "not a winner" spanning a graded loss AND a
    row nothing ever graded — a distinction that **cannot exist** in a schema
    built from the model. So a metadata-built test database cannot represent
    ungraded truth at all, and a fixture seeded into one would prove the
    conjunct works by never exercising it.

    CAL-P152's lesson, in a new place: *a fixture that cannot come from the
    writer proves nothing about the reader.* The gate therefore matches the
    schema the producer actually runs against, and ASSERTS the change took
    rather than assuming the DDL did what it says.

    The relaxation is safe for neighbouring tests — it removes a constraint, so
    nothing that inserted a non-null value can start failing — and the CI
    database is an ephemeral service container.

    The model itself is NOT changed here. Widening `Mapped[bool]` touches every
    reader of the attribute and is not this queue's cargo; it is reported.
    """
    from sqlalchemy import text

    await session.execute(
        text("ALTER TABLE futures_outcomes ALTER COLUMN is_winner DROP NOT NULL")
    )
    await session.commit()
    nullable = (
        await session.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'futures_outcomes' AND column_name = 'is_winner'"
            )
        )
    ).scalar()
    assert nullable == "YES", (
        "the test database still has is_winner NOT NULL, so the ungraded lone "
        "claim below cannot be seeded and the fail-closed conjunct would be "
        f"proved by a case that does not exist (got {nullable!r})"
    )


async def _seed_asym(session):
    """The CERT-485 P1-a fixture: a LOSS-ONLY, a WINNER and an UNKNOWN variant."""
    from sqlalchemy import text

    await _match_production_is_winner_nullability(session)

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
            # Three-valued on purpose (CAL-P155): True / False / None is
            # winner / graded loss / never graded, and the last two are the
            # pair `is_winner`'s False default cannot tell apart.
            winner=ASYM_LEG_WINNER[mid],
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
# THE RULING (alex-inbox/calibration-919, option A — Alex, 2026-08-30, reversing
# CAL-P151's option B). The exclusion is LIFTED and the arm counts per MARKET:
#
#   * Per-MARKET is the shipped behaviour. Each of these rows IS "a complete,
#     scoreable prediction" by D13's own argument, and they were excluded only
#     because they were counted together. Alex was given the choice with the
#     population cost declared UNMEASURED and took it knowingly; the freeze-lift
#     batch rebuilds on the new population.
#   * Per-VARIANT (option B) is what shipped from CAL-P151 to CAL-P154 and is
#     now retired. It is pinned as ABSENT, not merely un-asserted.
#   * What is NOT acceptable is either one being true by accident. Hence this
#     gate: it executes the reverted two-column join as well, so a green here
#     means the two mechanisms — D5's exact join and D13's per-market arm — are
#     each doing their own work and neither is covering for the other.
# =============================================================================


async def test_the_asymmetric_premise_every_scoreable_variant_is_admitted():
    """CERT-485 P1-a, the premise — RE-ASSERTED under the ruling that reversed it.

    Three variants of one virtual market:

    * ``baseball`` — two winners. Admitted by the ``has_winner >= 1`` arm, and
      untouched by any of this.
    * ``cricket`` — two AFFIRMATIVE graded losses, ``has_winner = 0``. This is
      the variant CERT-485 found. The retired per-variant arm refused it for
      ``market_count = 2``; the ruled per-market arm admits it, because
      ``graded_lone_claims = 2`` and nothing in it is ungraded.
    * ``tennis`` — one graded loss and one lone claim nothing ever graded.
      ADMITTED (CERT-514), and then SPLIT: rung 1b removes the ungraded member
      at market grain while the graded one publishes.

    🔴 THE THIRD VARIANT IS THE CERT-514 CASE AND ITS EXPECTATION IS INVERTED.
    CAL-P155 refused it whole — ``ungraded_lone_claims = 1`` — and the cert
    blocked that: the graded loss beside the ungraded row is independently
    scoreable, and option A says it publishes on its own account. Refusing the
    variant made its fate depend on a SIBLING market, which is the coupling the
    ruling removes.

    So the variant is admitted and the refusal moves DOWN a grain. That is only
    safe because rung 1b exists; ``test_the_mixed_variant_publishes_only_its_
    graded_member`` below is the assertion that the split actually happens,
    and without it this change would be a straight relaxation that publishes
    unknown truth as a confident loss off ``is_winner``'s False default.
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
                    "graded, eligible, graded_lone_claims, ungraded_lone_claims "
                    "FROM vm_stats WHERE vm_id = :vm ORDER BY category"
                ),
                {"vm": f"e:{ASYM_EVENT_ID}"},
            )
        ).all()
        assert [s.category for s in stats] == ["baseball", "cricket", "tennis"], (
            "PREMISE GONE: the asymmetric vm must still hold three variants "
            f"(got {stats!r})"
        )
        by_cat = {s.category: s for s in stats}
        loss, win, unknown = by_cat["cricket"], by_cat["baseball"], by_cat["tennis"]

        assert loss.has_winner == 0 and loss.graded == 2, (
            "the loss variant must carry two AFFIRMATIVE graded losses and no "
            f"winner, or this gate is testing unknown truth instead (got {loss!r})"
        )
        assert loss.market_count == 2 and loss.total_outcomes == 2, (
            "the loss variant must hold TWO lone claims — one would have been "
            f"admitted by the RETIRED arm and there would be no finding to "
            f"reverse (got {loss!r})"
        )
        assert (loss.graded_lone_claims, loss.ungraded_lone_claims) == (2, 0), (
            "the per-MARKET counts are what the ruled arm reads; if they do not "
            f"see two graded lone claims here the columns are wrong (got {loss!r})"
        )
        assert loss.eligible == 2
        assert win.has_winner == 2 and win.market_count == 2

        assert unknown.has_winner == 0 and unknown.graded == 1, (
            "the unknown variant must carry exactly one AFFIRMATIVE grade — the "
            f"other leg's is_winner must be NULL, not False (got {unknown!r})"
        )
        assert (unknown.graded_lone_claims, unknown.ungraded_lone_claims) == (1, 1), (
            "the CERT-514 case needs BOTH: a scoreable claim that publishes on "
            "its own account, and an ungraded one beside it that must NOT — and "
            "must be removed per market rather than by refusing the variant. "
            f"got={unknown!r}"
        )

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
        assert admitted == ["baseball", "cricket", "tennis"], (
            "RULED (alex-inbox/calibration-919 option A; CERT-514): `clean_vms` "
            "admits ALL THREE — the winner variant, the two-graded-losses "
            "variant, and the MIXED one. If `cricket` is missing, D13's arm went "
            "back to per-VARIANT and that is a ruling reversal. If `tennis` is "
            "missing, the fail-closed residue is back and a graded lone claim is "
            "again being refused for an ungraded SIBLING's sake — CERT-514 [P1]. "
            "Admission is NOT publication here: `tennis`'s ungraded leg is "
            "removed one grain down by rung 1b, which "
            "test_the_mixed_variant_publishes_only_its_graded_member proves. "
            f"got={admitted!r}"
        )

    await _with_seeded_db(body, seed=_seed_asym, cleanup=_cleanup_asym)


async def test_the_graded_losses_publish_under_their_own_category_not_a_siblings():
    """CERT-485 P1-a, the behaviour — under option A, and it is NOT the accident.

    🔴 THE POINT OF THIS ARM IS THAT TWO DIFFERENT MECHANISMS PUBLISH THE SAME
    FOUR OUTCOME IDS, AND ONLY ONE OF THEM IS CORRECT. Before D5, the two-column
    join published the loss legs by matching a SIBLING variant's admission row —
    so they published **under the sibling's category, `baseball`**, a bucket
    their markets are not members of. Under the ruled per-market arm they
    publish because their own variant is admitted, **under `cricket`**.

    Counting rows cannot tell those apart. The category can, and does: a test
    that asserted only `sorted(ids) == ASYM_IDS` would go green if D5 were
    reverted, which is the whole finding undone. So the assertion is on the
    (id, category) pairs.

    ⚠️ AND THE REVERTED ARM CHANGED SHAPE UNDER THE RULING — measured in CI, not
    predicted. While the cricket variant was REFUSED, the coarse key had exactly
    one admission row to match, so the loss legs were misfiled and not doubled;
    the first cut of this test asserted "no duplication" on that basis and CI
    correctly failed it. Option A admits that variant, so the coarse key now
    matches BOTH and every outcome is emitted once per admitted variant. The
    accident and the duplication are the same defect seen from two population
    states, and this arm now asserts the one that is actually there.

    THE FALSIFIER, unchanged and still the one that matters: the WINNER
    variant's rows must survive intact. A join that removes duplicates by
    removing rows nobody ruled on is the failure mode this file is written
    against.

    AND THE UNKNOWN VARIANT MUST NOT APPEAR. `tennis` holds a scoreable graded
    loss beside a never-graded lone claim; the arm refuses the pair. If a
    `tennis` row publishes, an ungraded outcome just entered the curve as a
    confident loss and no downstream rung will remove it.
    """
    from app.tasks.precompute_calibration import _calibration_population_ctes

    async def body(session):
        ctes = _calibration_population_ctes()

        before = await _rows(session, _reverted(ctes), ASYM_IDS)
        after = await _rows(session, ctes, ASYM_IDS)

        # THE ACCIDENT, still reproducible: under the two-column key the loss
        # legs match the SIBLING variant's admission row and land in the
        # SIBLING'S bucket, which is a bucket their markets are not members of.
        assert {(oid, "baseball") for oid in ASYM_LOSS_LEGS} <= set(before), (
            "the loss rows must ALSO publish under the sibling variant's "
            f"category under the old join — that IS the accident. got={before!r}"
        )
        # 🔴 AND UNDER OPTION A THE OLD JOIN NOW *DUPLICATES* RATHER THAN
        # MISPLACES. Before the ruling the cricket variant was refused, so the
        # two-column key had exactly one `clean_vms` row to match and the loss
        # legs were merely misfiled. The ruling admits that variant, so the same
        # coarse key matches BOTH — every outcome of this virtual market is
        # emitted once per admitted variant. That is D5's own defect, and this
        # fixture now reproduces it on rows the ruling put there.
        assert len(before) > len({oid for oid, _ in before}), (
            "the reverted two-column join must now DUPLICATE — with two admitted "
            "variants sharing one vm_id, a join carrying only (vm_id, source) "
            f"cannot pick one. If it does not, D5 is not being reverted. got={before!r}"
        )
        # Nothing is LOST under the old join either; the failure is additive.
        assert {oid for oid, _ in before} == set(ASYM_IDS), (
            "every seeded outcome should appear under the coarse join, including "
            f"the unknown-truth variant's. got={before!r}"
        )

        # THE RULING. Same four ids as the accident produced — and a different,
        # correct bucketing.
        assert sorted(oid for oid, _ in after) == ASYM_PUBLISHED, (
            "RULED (alex-inbox/calibration-919 option A; CERT-514): the two "
            "graded lone claims publish on their own account, the winner variant "
            "is untouched, and the mixed variant contributes its GRADED member "
            "only. If the loss rows are missing, D13's arm went back to "
            "per-VARIANT. If a winner row is missing, D5 is losing rows nobody "
            f"ruled on. If {ASYM_MIXED_GRADED_LEG} is missing, the fail-closed "
            f"residue is back. If {ASYM_UNGRADED_LEG} is HERE, rung 1b is not "
            f"catching unknown truth. got={after!r}"
        )
        assert {oid: cat for oid, cat in after} == {
            **{oid: "cricket" for oid in ASYM_LOSS_LEGS},
            **{oid: "baseball" for oid in ASYM_WIN_LEGS},
            ASYM_MIXED_GRADED_LEG: "tennis",
        }, (
            "🔴 EVERY ROW MUST PUBLISH UNDER ITS OWN VARIANT'S CATEGORY. The "
            "loss legs under `baseball` would mean D5 was reverted and these "
            "rows are riding the sibling again — the same ids, the wrong "
            f"mechanism, and the accident back in the curve. got={after!r}"
        )
        assert ASYM_UNGRADED_LEG not in {oid for oid, _ in after}, (
            "the never-graded leg published. `is_winner` is nullable with a "
            "False default, so it is now a confident loss in the calibration "
            "curve (gotcha #21). Its variant is admitted on purpose since "
            "CERT-514 — rung 1b is what must remove THIS row, and it did not. "
            f"got={after!r}"
        )

    await _with_seeded_db(body, seed=_seed_asym, cleanup=_cleanup_asym)


async def test_the_mixed_variant_publishes_only_its_graded_member():
    """🔴 CERT-514's [P1], as the behaviour it demanded — the SPLIT.

    This is the assertion the block was withheld for, and it is deliberately
    scoped to ONE variant so it cannot be satisfied by the other two.

    CAL-P155 admitted or refused a variant WHOLE. Its arm carried
    ``ungraded_lone_claims = 0``, so a variant holding one graded lone claim
    beside one ungraded lone claim was refused entirely — and the graded claim,
    which option A says publishes on its own account, was withheld because of a
    SIBLING market's grade state. The cert called that the same coupling the
    ruling removes, on a smaller population, and blocked it.

    The repair is a change of GRAIN, not a relaxation, and this test is the only
    place both halves are executed together against real rows:

      * the variant is ADMITTED — the graded loss reaches the curve; and
      * the ungraded member is REMOVED anyway, by rung 1b, at market grain.

    Take either half away and this fails. Drop rung 1b and 771516 publishes as a
    confident loss off ``is_winner``'s False default (gotcha #21); restore the
    residue conjunct and 771515 disappears with it.

    ``_match_production_is_winner_nullability`` is why this can be seeded at all:
    the ORM declares ``is_winner`` non-Optional, so a metadata-built database
    makes it NOT NULL and "nobody graded this" is not expressible in it.
    """
    from app.tasks.precompute_calibration import _calibration_population_ctes

    async def body(session):
        published = await _rows(
            session, _calibration_population_ctes(), sorted(ASYM_UNKNOWN_LEGS)
        )

        assert published == [(ASYM_MIXED_GRADED_LEG, "tennis")], (
            "the mixed variant must contribute EXACTLY its graded member. "
            f"Missing {ASYM_MIXED_GRADED_LEG} means a graded lone claim is "
            "still being refused for an ungraded sibling's sake — CERT-514 "
            f"[P1], unrepaired. Present {ASYM_UNGRADED_LEG} means the arm was "
            "relaxed without rung 1b behind it and unknown truth is now a "
            f"confident loss in the curve. got={published!r}"
        )

    await _with_seeded_db(body, seed=_seed_asym, cleanup=_cleanup_asym)


async def test_rung_1b_is_what_removes_the_ungraded_member_not_the_arm():
    """ATTRIBUTION. The row is gone — prove WHICH mechanism took it.

    ``test_the_mixed_variant_publishes_only_its_graded_member`` asserts the
    outcome; a passing outcome is consistent with the residue conjunct never
    having been removed at all, because refusing the variant ALSO keeps 771516
    out. So that test alone cannot tell the repair from the thing it replaced.

    This one reads the flag directly. ``is_ungraded_lone_claim`` must be TRUE for
    the never-graded leg and FALSE for every other seeded row — including its own
    variant's graded sibling, which is the pair rung 1b has to separate.
    """
    from sqlalchemy import text

    from app.tasks.precompute_calibration import _calibration_population_ctes

    async def body(session):
        flags = {
            r.outcome_id: r.is_ungraded_lone_claim
            for r in (
                await session.execute(
                    text(
                        "WITH "
                        + _calibration_population_ctes()
                        + " SELECT outcome_id, is_ungraded_lone_claim "
                        "FROM ranked_outcomes WHERE outcome_id = ANY(:ids)"
                    ),
                    {"ids": ASYM_IDS},
                )
            ).all()
        }

        assert flags.get(ASYM_UNGRADED_LEG) is True, (
            "rung 1b did not flag the never-graded lone claim, so whatever kept "
            "it out of the curve was NOT the per-market rung — most likely the "
            f"variant-wide residue is still in the arm. got={flags!r}"
        )
        assert flags.get(ASYM_MIXED_GRADED_LEG) is False, (
            "rung 1b flagged the GRADED member of the mixed variant. It keys on "
            "`graded_count = 0`; if this is True it is keying on winner "
            f"cardinality and every honest lone-claim loss is about to be "
            f"dropped from the curve. got={flags!r}"
        )
        assert not any(
            flags.get(oid) for oid in (*ASYM_LOSS_LEGS, *ASYM_WIN_LEGS)
        ), (
            "rung 1b reached beyond the mixed variant. Those four legs are all "
            f"affirmatively graded, so none is unknown truth. got={flags!r}"
        )

    await _with_seeded_db(body, seed=_seed_asym, cleanup=_cleanup_asym)
