"""#2098 / ruling 125, sites TWO and THREE — the other two copies of the join.

CAL-P090 fixed the producer (``precompute_calibration._calibration_population_ctes``)
and reported, rather than fixed, the two remaining copies of the same CTE pair
(``cal-p090-2098-source-scope-fix.md`` §4). This file is the guard for both:

* ``app/routes/admin_data_quality.py`` — ``GET /api/admin/calibration-data``,
  the endpoint whose job is to audit the published population.
* ``scripts/audit_golf_hockey_calibration.py`` — the golf/hockey attribution
  audit, whose docstring claims to replicate "the EXACT inclusion logic" of the
  public curve.

THE DEFECT, identically in both. ``vm_id`` is source-blind on its ``e:`` arm
(``'e:' || mi.event_id``) while ``event_sizes`` counts per
``(event_id, source)``, so two sources each carrying >=3 resolved markets on
one event are handed the SAME ``vm_id``. Every neighbouring aggregate in both
chains is source-scoped on purpose — ``group_sizes``/``event_sizes`` GROUP BY
``(x, source)``, ``virtual_market`` joins ``AND gs.source = mi.source``,
``vm_stats`` GROUPs BY ``vm.source``, ``clean_vms`` is joined on both. These two
were the exception, and the exception was the defect: a modal price detected
among ONE source's legs deleted the OTHER source's legs sitting at that price.

WHY IT MATTERS THAT THESE TWO ARE FIXED TOO, and not merely tidied. Until they
were, the admin endpoint and the producer disagreed about the published
population on exactly the rows the fix restores — measured at roughly 23-35 rows
on the charter specimen ``e:14887630``. An auditing instrument that silently
measures a different population than the thing it audits is worse than no
instrument, because its agreement is read as corroboration.

WHY REAL POSTGRES AND NOT A STRING ASSERTION (the same reason cert
C-2098-SOURCE-1 §3d gives for the producer's guard): the claim is relational —
"one source's legs do not suppress another's" — so it is proved by seeding one
``event_id`` reachable from two sources and reading what each chain publishes.
String assertions over this SQL have already produced one false sense of
coverage in this program's history.

RED-FIRST, in the same run. Each chain has a second arm that EXECUTES the
reverted (pre-fix) statement and asserts the suppression comes back, because a
green regression guard proves the defect is absent and NOT that the guard would
have caught it — and there is no local Postgres in the agent sandbox
(``initdb`` dies on ``shmget``), so it cannot be run red by hand.

AND THE FALSIFIER, attacked first: the fix must SCOPE dedup, never disable it.
Each chain has a single-source control asserting a genuine within-source mode is
still deleted.

Gated on a throwaway Postgres, armed in CI by the ``search-recall`` job's
service container (``SEARCH_TEST_DATABASE_URL``) — the same job, and the same
skip-detection, as the producer's guard beside it.
"""

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import text as _sa_text

DB_URL = os.environ.get("CALIBRATION_TEST_DATABASE_URL") or os.environ.get(
    "SEARCH_TEST_DATABASE_URL"
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL (CI's service container) or "
            "CALIBRATION_TEST_DATABASE_URL to run the #2098 peer-site gates"
        ),
    ),
]

COMMENCE = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc).replace(tzinfo=None)

# Prices are all exactly representable in binary floating point on purpose: the
# predicate under test is an equality on ``adj_opening_probability``, and a gate
# that could fail on a representation artefact would be reporting on the wrong
# thing. Bucket index is ``LEAST(FLOOR(p * 10), 9)`` — 0.5 -> 5, 0.25 -> 2,
# 0.125 -> 1, 0.625 -> 6.
#
# Kalshi carries FIVE legs, TWO of them at Polymarket's modal price. Five legs
# means ``eligible = 5``, so Kalshi's own mode would need
# ``count > GREATEST(2.5, 2) = 2.5`` and 2 is not — Kalshi forms NO mode of its
# own and every one of its legs is publishable on its own merits. Anything that
# deletes them came from the other source.
#
# Polymarket carries FOUR legs, ALL at 0.5. ``eligible = 4``, so its mode needs
# ``count > GREATEST(2, 2) = 2`` and 4 is. Those four SHOULD be deleted — by
# their own mode, among themselves.
KALSHI_SHAPE = (0.5, 0.5, 0.25, 0.125, 0.625)
POLY_SHAPE = (0.5, 0.5, 0.5, 0.5)

# The two Kalshi legs sitting at Polymarket's modal price. Post-fix they
# publish; pre-fix they are deleted by a mode they had no part in forming.
KALSHI_AT_POLY_MODE = 2


# ---------------------------------------------------------------------------
# Seeding. One event, N legs, each leg its own single-outcome resolved market.
#
# Each leg is its own market carrying its own outcome, so no market "graded
# nobody" and none is a 2-outcome mex binary with a bad winner count.
# ``mutually_exclusive`` false and ``market_type='binary'`` keep every leg out
# of the mex/field normalization arm; the arm under test is the ordinary
# non-partition multi pool, which is where the defect acts.
#
# EVERY NOT-NULL COLUMN IS SUPPLIED EXPLICITLY, in two flavours, and the second
# is the one that bites. A raw ``INSERT`` obviously has to supply columns with no
# default at all (``futures_markets.external_id``, ``.name``,
# ``futures_outcomes.external_id``) — but it must ALSO supply columns whose only
# default is a Python-side ``default=``, because ``text("INSERT ...")`` never
# runs those: ``events.status``, ``futures_markets.category``,
# ``futures_odds_snapshots.reading_count``. An ORM insert would have filled all
# six and taught you nothing.
#
# -88's guard omitted five of the six and was never executed, so nobody found
# out; its first real CI run would have died on ``NotNullViolationError`` at the
# first INSERT and turned a DEPLOY-GATING job red for a reason with nothing to do
# with #2098. ``tests/test_pg_gate_seed_completeness.py`` now asserts this
# statically, in the ordinary suite, because that is the arm of this failure
# class that can be checked without a database — and it is what found the
# Python-default three, which reading the seed by eye had missed.
#
# No ``futures_odds_snapshots`` row is seeded: neither chain under test reads
# that table. Seeding rows a query cannot see is how a fixture starts describing
# a different population than the one it certifies.
# ---------------------------------------------------------------------------


async def _seed(session, *, event_id, sport_id, category, legs):
    """``legs`` maps market_id -> (source, price, is_winner)."""
    await session.execute(
        _sa_text("INSERT INTO sports (id, key, name, active) VALUES (:id, :k, :n, true)"),
        {"id": sport_id, "k": f"test_2098_{sport_id}", "n": f"Test 2098 {sport_id}"},
    )
    await session.execute(
        _sa_text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status) VALUES "
            "(:id, :sid, 'Home 2098', 'Away 2098', :ct, 'completed')"
        ),
        {"id": event_id, "sid": sport_id, "ct": COMMENCE},
    )
    for market_id, (source, price, is_winner) in legs.items():
        await session.execute(
            _sa_text(
                "INSERT INTO futures_markets (id, external_id, name, source, status, "
                "category, event_id, mutually_exclusive, market_type, "
                "llm_sport_category, volume) VALUES "
                "(:id, :xid, :nm, :src, 'resolved', 'championship', :ev, false, "
                "'binary', :cat, 100)"
            ),
            {
                "id": market_id,
                "xid": f"test-2098-peers-{market_id}",
                "nm": f"market-{market_id}",
                "src": source,
                "ev": event_id,
                "cat": category,
            },
        )
        await session.execute(
            _sa_text(
                "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
                "opening_probability, calibration_probability, current_probability, "
                "is_winner, resolution_source, volume) VALUES "
                "(:id, :mid, :xid, :nm, :p, :p, :cp, :win, 'api_settlement', 10)"
            ),
            {
                "id": market_id,
                "mid": market_id,
                "xid": f"test-2098-peers-out-{market_id}",
                "nm": f"leg-{market_id}",
                "p": price,
                # The admin chain derives its own winner from
                # ``current_probability`` (>= 0.95) and gates ``clean_vms`` on
                # ``(near_one + near_zero) >= total * 0.8 AND near_one >= 1``.
                # The golf chain reads ``fo.is_winner`` and gates on
                # ``has_winner >= 1``. Setting BOTH consistently is what lets one
                # fixture shape serve both chains.
                "cp": 1.0 if is_winner else 0.0,
                "win": is_winner,
            },
        )
    await session.commit()


async def _cleanup(session, *, event_id, sport_id, market_ids):
    ids = sorted(market_ids)
    await session.execute(
        _sa_text("DELETE FROM futures_outcomes WHERE id = ANY(:ids)"), {"ids": ids}
    )
    await session.execute(
        _sa_text("DELETE FROM futures_markets WHERE id = ANY(:ids)"), {"ids": ids}
    )
    await session.execute(_sa_text("DELETE FROM events WHERE id = :id"), {"id": event_id})
    await session.execute(_sa_text("DELETE FROM sports WHERE id = :id"), {"id": sport_id})
    await session.commit()


def _two_source_legs(base):
    """Kalshi's five legs and Polymarket's four, on one event.

    Exactly one leg per source is a winner, so each source's ``(vm_id, source)``
    row clears ``clean_vms`` on both chains' winner gates. The Kalshi winner is
    deliberately the 0.625 leg — NOT one of the two legs under test — so a
    suppression cannot be confused with a winner-gate effect.
    """
    legs = {}
    for i, price in enumerate(KALSHI_SHAPE):
        legs[base + 1 + i] = ("kalshi", price, price == 0.625)
    for i, price in enumerate(POLY_SHAPE):
        legs[base + 101 + i] = ("polymarket", price, i == 0)
    return legs


async def _engine_and_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# The reverts. Applied to the production SQL string and then EXECUTED — this is
# not a string assertion standing in for behaviour, it is the pre-fix statement
# run against a real database.
#
# Every substitution must match EXACTLY ONCE. A revert arm that silently failed
# to revert would execute the FIXED sql, observe no suppression, and report that
# red-first was proved — the empty-200 failure shape (gotcha #53) wearing a
# test's clothes. So the count is asserted, not assumed.
# ---------------------------------------------------------------------------

_ADMIN_REVERTS = (
    (
        "            SELECT vm_id, source, adj_opening_probability AS mode_price",
        "            SELECT vm_id, adj_opening_probability AS mode_price",
    ),
    (
        "            GROUP BY vm_id, source, adj_opening_probability, eligible",
        "            GROUP BY vm_id, adj_opening_probability, eligible",
    ),
    ("              AND mp.source = ro.source\n", ""),
)

_GOLF_REVERTS = (
    (
        "    SELECT vm_id, source, adj_opening_probability AS mode_price",
        "    SELECT vm_id, adj_opening_probability AS mode_price",
    ),
    (
        "    GROUP BY vm_id, source, adj_opening_probability, eligible",
        "    GROUP BY vm_id, adj_opening_probability, eligible",
    ),
    ("  AND mp.source = ro.source\n", ""),
)


def _revert(sql: str, reverts, what: str) -> str:
    out = sql
    for fixed, broken in reverts:
        n = out.count(fixed)
        assert n == 1, (
            f"cannot revert the #2098 fix in {what}: expected exactly one "
            f"occurrence of {fixed!r}, found {n}. The SQL moved — re-aim this "
            "arm rather than deleting it, or the red-first proof becomes vacuous."
        )
        out = out.replace(fixed, broken, 1)
    assert "mp.source" not in out, f"revert incomplete in {what}"
    return out


# ---------------------------------------------------------------------------
# SITE 2 — GET /api/admin/calibration-data
#
# The whole shipped statement is executed, aggregation and all: no CTE surgery,
# so what runs here is byte-for-byte what the endpoint runs. Rows are isolated
# by a category value no other fixture uses, and the assertion is over
# ``(bucket_idx, source) -> n``, since this chain's ``deduped`` carries no
# outcome id to name rows by.
# ---------------------------------------------------------------------------

ADMIN_EVENT_ID = 8815887630
ADMIN_SPORT_ID = 88158
ADMIN_CATEGORY = "cal2098peers"
ADMIN_LEGS = _two_source_legs(8815000)

#: Post-fix. Every Kalshi leg publishes, including BOTH at 0.5 (bucket 5);
#: Polymarket's four are deleted by their own mode.
ADMIN_EXPECTED_FIXED = {(1, "kalshi"): 1, (2, "kalshi"): 1, (5, "kalshi"): 2, (6, "kalshi"): 1}
#: Pre-fix. Bucket 5 disappears entirely — Polymarket's four-leg mode at 0.5
#: deletes Kalshi's two legs at 0.5 as well as its own.
ADMIN_EXPECTED_REVERTED = {(1, "kalshi"): 1, (2, "kalshi"): 1, (6, "kalshi"): 1}


async def _admin_counts(session, sql):
    rows = (await session.execute(_sa_text(sql))).all()
    return {
        (r.bucket_idx, r.source): r.n for r in rows if r.category == ADMIN_CATEGORY
    }


async def test_admin_calibration_data_does_not_cross_suppress_sources():
    from app.routes.admin_data_quality import _CALIBRATION_AUDIT_POPULATION_SQL as SQL

    engine, Session = await _engine_and_session()
    try:
        async with Session() as session:
            await _cleanup(
                session,
                event_id=ADMIN_EVENT_ID,
                sport_id=ADMIN_SPORT_ID,
                market_ids=ADMIN_LEGS,
            )
            await _seed(
                session,
                event_id=ADMIN_EVENT_ID,
                sport_id=ADMIN_SPORT_ID,
                category=ADMIN_CATEGORY,
                legs=ADMIN_LEGS,
            )

            # (a) THE PREMISE, asserted rather than assumed. Both sources really
            #     do collide on one source-blind vm_id and each really does carry
            #     its OWN source-scoped ``eligible``. If a later change makes
            #     vm_id source-carrying, this gate's whole subject disappears and
            #     it must say so out loud instead of passing vacuously.
            cut = SQL.index("        -- #2098 / RULING 125")
            probe = SQL[:cut].rstrip().rstrip(",") + (
                "\nSELECT source, vm_id, MIN(eligible) AS eligible, COUNT(*) AS n "
                "FROM ranked_outcomes WHERE category = :cat "
                "GROUP BY source, vm_id ORDER BY source"
            )
            shape = (
                await session.execute(_sa_text(probe), {"cat": ADMIN_CATEGORY})
            ).all()
            by_source = {r.source: r for r in shape}
            assert set(by_source) == {"kalshi", "polymarket"}, (
                "both sources must reach `ranked_outcomes`; the collision cannot "
                f"be exercised otherwise (got {shape!r})"
            )
            assert by_source["kalshi"].vm_id == by_source["polymarket"].vm_id, (
                "PREMISE GONE: the two sources no longer share a vm_id, so this "
                "gate is no longer testing #2098. Do not delete it — find out "
                "what changed in `virtual_market` and re-aim it."
            )
            assert by_source["kalshi"].eligible == 5
            assert by_source["polymarket"].eligible == 4

            # (b) THE FIX, and (c) the falsifier in the same assertion: Kalshi's
            #     bucket-5 pair survives AND Polymarket contributes nothing,
            #     because its own mode still deletes its own legs. A fix that
            #     restored rows by turning dedup off is worse than the defect.
            got = await _admin_counts(session, SQL)
            assert got == ADMIN_EXPECTED_FIXED, (
                "#2098 at the admin audit endpoint: one source's mode price must "
                "not delete another source's legs, and the other source's own "
                f"mode must still fire. got={sorted(got.items())} "
                f"expected={sorted(ADMIN_EXPECTED_FIXED.items())}"
            )
    finally:
        async with Session() as session:
            await _cleanup(
                session,
                event_id=ADMIN_EVENT_ID,
                sport_id=ADMIN_SPORT_ID,
                market_ids=ADMIN_LEGS,
            )
        await engine.dispose()


async def test_red_first_admin_reverted_join_reproduces_the_suppression():
    """RED-FIRST for site 2, proved in the same run."""
    from app.routes.admin_data_quality import _CALIBRATION_AUDIT_POPULATION_SQL as SQL

    engine, Session = await _engine_and_session()
    try:
        async with Session() as session:
            await _cleanup(
                session,
                event_id=ADMIN_EVENT_ID,
                sport_id=ADMIN_SPORT_ID,
                market_ids=ADMIN_LEGS,
            )
            await _seed(
                session,
                event_id=ADMIN_EVENT_ID,
                sport_id=ADMIN_SPORT_ID,
                category=ADMIN_CATEGORY,
                legs=ADMIN_LEGS,
            )

            got = await _admin_counts(
                session, _revert(SQL, _ADMIN_REVERTS, "admin_data_quality.py")
            )
            assert got == ADMIN_EXPECTED_REVERTED, (
                "the #2098 defect is NO LONGER REPRODUCIBLE at the admin "
                "endpoint by this fixture, so the guard beside it is no longer "
                "known to catch anything. reverted-SQL "
                f"got={sorted(got.items())} expected the bucket-5 pair to be "
                f"deleted: {sorted(ADMIN_EXPECTED_REVERTED.items())}"
            )
    finally:
        async with Session() as session:
            await _cleanup(
                session,
                event_id=ADMIN_EVENT_ID,
                sport_id=ADMIN_SPORT_ID,
                market_ids=ADMIN_LEGS,
            )
        await engine.dispose()


# ---------------------------------------------------------------------------
# SITE 3 — scripts/audit_golf_hockey_calibration.py
#
# ``BUILD_TEMP_SQL`` is a ``CREATE TEMP TABLE ... AS`` wrapper around the same
# chain. Only the ``CREATE TEMP TABLE`` line is stripped, and the strip is
# asserted to match exactly once; everything executed below is the script's own
# statement. Its ``market_info`` restricts to golf/hockey, so the fixture must
# be golf — rows are named by ``outcome_id``, which this chain does carry.
# ---------------------------------------------------------------------------

GOLF_EVENT_ID = 8816887630
GOLF_SPORT_ID = 88168
GOLF_LEGS = _two_source_legs(8816000)
GOLF_KALSHI_IDS = {mid for mid, (src, _, _) in GOLF_LEGS.items() if src == "kalshi"}
#: The two Kalshi legs at Polymarket's modal price, in seeded order.
GOLF_SUPPRESSED = {8816001, 8816002}

_CREATE_TEMP = "CREATE TEMP TABLE audit_rows AS\n"


def _golf_select() -> str:
    from scripts.audit_golf_hockey_calibration import BUILD_TEMP_SQL

    n = BUILD_TEMP_SQL.count(_CREATE_TEMP)
    assert n == 1, (
        f"expected exactly one {_CREATE_TEMP.strip()!r} in BUILD_TEMP_SQL, found "
        f"{n}; the script's shape moved and this gate must be re-aimed"
    )
    return BUILD_TEMP_SQL.replace(_CREATE_TEMP, "", 1)


async def _golf_published(session, sql):
    rows = (await session.execute(_sa_text(sql))).all()
    return {r.outcome_id for r in rows} & set(GOLF_LEGS)


async def test_golf_hockey_audit_does_not_cross_suppress_sources():
    engine, Session = await _engine_and_session()
    try:
        async with Session() as session:
            await _cleanup(
                session,
                event_id=GOLF_EVENT_ID,
                sport_id=GOLF_SPORT_ID,
                market_ids=GOLF_LEGS,
            )
            await _seed(
                session,
                event_id=GOLF_EVENT_ID,
                sport_id=GOLF_SPORT_ID,
                category="golf",
                legs=GOLF_LEGS,
            )

            published = await _golf_published(session, _golf_select())
            assert published == GOLF_KALSHI_IDS, (
                "#2098 in the golf/hockey attribution audit: one source's mode "
                "price must not delete another source's legs, and the other "
                f"source's own mode must still fire. published={sorted(published)} "
                f"expected={sorted(GOLF_KALSHI_IDS)}"
            )
    finally:
        async with Session() as session:
            await _cleanup(
                session,
                event_id=GOLF_EVENT_ID,
                sport_id=GOLF_SPORT_ID,
                market_ids=GOLF_LEGS,
            )
        await engine.dispose()


async def test_red_first_golf_reverted_join_reproduces_the_suppression():
    """RED-FIRST for site 3, proved in the same run."""
    engine, Session = await _engine_and_session()
    try:
        async with Session() as session:
            await _cleanup(
                session,
                event_id=GOLF_EVENT_ID,
                sport_id=GOLF_SPORT_ID,
                market_ids=GOLF_LEGS,
            )
            await _seed(
                session,
                event_id=GOLF_EVENT_ID,
                sport_id=GOLF_SPORT_ID,
                category="golf",
                legs=GOLF_LEGS,
            )

            published = await _golf_published(
                session,
                _revert(
                    _golf_select(), _GOLF_REVERTS, "audit_golf_hockey_calibration.py"
                ),
            )
            assert published == GOLF_KALSHI_IDS - GOLF_SUPPRESSED, (
                "the #2098 defect is NO LONGER REPRODUCIBLE in the golf/hockey "
                "audit by this fixture, so the guard beside it is no longer known "
                f"to catch anything. reverted-SQL published={sorted(published)}, "
                "expected the two Kalshi legs at Polymarket's modal price to be "
                f"deleted: {sorted(GOLF_SUPPRESSED)}"
            )
    finally:
        async with Session() as session:
            await _cleanup(
                session,
                event_id=GOLF_EVENT_ID,
                sport_id=GOLF_SPORT_ID,
                market_ids=GOLF_LEGS,
            )
        await engine.dispose()


# ---------------------------------------------------------------------------
# THE CONTROL, for both sites. Adding ``source`` to a GROUP BY and to a join can
# only change behaviour where more than one source is present. Where exactly one
# is, the fix must be a no-op — a genuine within-source mode is still deleted.
# If this fails, the join predicate is doing something other than what is
# claimed.
# ---------------------------------------------------------------------------

CTL_EVENT_ID = 8817887630
CTL_SPORT_ID = 88178
#: Four Kalshi legs, three at 0.5: count 3 > GREATEST(4 * 0.5, 2) = 2, so this
#: IS a genuine within-source mode and those three must still be deleted.
CTL_LEGS = {
    8817001: ("kalshi", 0.5, False),
    8817002: ("kalshi", 0.5, False),
    8817003: ("kalshi", 0.5, False),
    8817004: ("kalshi", 0.25, True),
}


async def test_single_source_behaviour_is_unchanged_at_both_peer_sites():
    from app.routes.admin_data_quality import _CALIBRATION_AUDIT_POPULATION_SQL as SQL

    engine, Session = await _engine_and_session()
    try:
        # -- the admin chain, isolated by its own category --------------------
        async with Session() as session:
            await _cleanup(
                session,
                event_id=CTL_EVENT_ID,
                sport_id=CTL_SPORT_ID,
                market_ids=CTL_LEGS,
            )
            await _seed(
                session,
                event_id=CTL_EVENT_ID,
                sport_id=CTL_SPORT_ID,
                category=ADMIN_CATEGORY,
                legs=CTL_LEGS,
            )
            got = await _admin_counts(session, SQL)
            assert got == {(2, "kalshi"): 1}, (
                "single-source behaviour must be untouched by source-scoping at "
                "the admin endpoint: the 3-leg mode at 0.5 must still be deleted "
                f"(got {sorted(got.items())})"
            )
            await _cleanup(
                session,
                event_id=CTL_EVENT_ID,
                sport_id=CTL_SPORT_ID,
                market_ids=CTL_LEGS,
            )

        # -- the golf chain, which must be seeded as golf ----------------------
        async with Session() as session:
            await _seed(
                session,
                event_id=CTL_EVENT_ID,
                sport_id=CTL_SPORT_ID,
                category="golf",
                legs=CTL_LEGS,
            )
            rows = (
                await session.execute(_sa_text(_golf_select()))
            ).all()
            published = {r.outcome_id for r in rows} & set(CTL_LEGS)
            assert published == {8817004}, (
                "single-source behaviour must be untouched by source-scoping in "
                "the golf/hockey audit: the 3-leg mode at 0.5 must still be "
                f"deleted (got {sorted(published)})"
            )
    finally:
        async with Session() as session:
            await _cleanup(
                session,
                event_id=CTL_EVENT_ID,
                sport_id=CTL_SPORT_ID,
                market_ids=CTL_LEGS,
            )
        await engine.dispose()
