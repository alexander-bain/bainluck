"""#2098 / ruling 125 — the mode-price dedup join must carry ``source``.

THE DEFECT. ``vm_id`` is source-blind on its ``e:`` arm: ``virtual_market``
builds it as ``'e:' || event_id`` while ``event_sizes`` counts per
``(event_id, source)``. So when two sources each carry >=3 resolved markets on
the SAME ``event_id``, they are assigned the SAME ``vm_id`` while every
neighbouring aggregate around them stays source-scoped (``vm_stats`` groups by
``(vm_id, source)``; ``clean_vms`` joins on both). ``mode_prices`` was the one
aggregate that did not: it grouped by ``vm_id`` alone and ``deduped`` joined it
on ``vm_id`` alone. A modal price detected among ONE source's legs therefore
deleted the OTHER source's legs that happened to sit at the same price.

Measured on production (``artifacts/cal-p087/ARTIFACT-CAL-P087-2098-CROSS-
SUPPRESSION.json``): on ``e:14887630``, FOUR Polymarket legs formed a mode that
deleted TWENTY-THREE Kalshi legs. 35 rows over 2 ``vm_id``s, whole domain.

WHY THIS TEST IS A REAL-POSTGRES FIXTURE AND NOT A STRING ASSERTION ON THE SQL
(cert C-2098-SOURCE-1 §3d, and it is written that way BY NAME): string
assertions on this module's frozen SQL have already produced one false sense of
coverage in its history. The claim under test is relational — "one source's
legs do not suppress another's" — so it is proved by seeding one ``event_id``
reachable from two sources and reading ``deduped``.

RED-FIRST. Revert either half of the fix (the ``source`` in ``mode_prices``'
GROUP BY, or the ``mp.source = ro.source`` conjunct in ``deduped``'s join) and
``test_one_sources_mode_does_not_delete_another_sources_legs`` fails: the two
Kalshi legs sitting at Polymarket's modal price vanish from ``deduped``.

AND THE FALSIFIER, in the same test: the fix must SCOPE dedup, never disable
it. Polymarket's own four legs must still be deleted by their own mode. A fix
that restores rows by breaking the mechanism is worse than the defect.

Gated on a throwaway Postgres. CI arms it through the ``search-recall`` job's
service container (``SEARCH_TEST_DATABASE_URL``), which is why this file lives
under ``tests/integration/`` beside the other real-driver gates rather than
next to ``tests/test_calibration_canonical_pg.py``: that file's own env var
(``CALIBRATION_TEST_DATABASE_URL``) is set nowhere, so a gate placed there
would have been a gate that never ran. There is no local Postgres in the agent
sandbox (``initdb`` dies on ``shmget``), so CI is the environment that runs it.
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
            "CALIBRATION_TEST_DATABASE_URL to run the #2098 source-scope gate"
        ),
    ),
]

# One shared event, two sources. The id is arbitrary but deliberately far from
# anything another gate in this job seeds — and it must fit in int32, because
# `events.id` is `Mapped[int]`, i.e. INTEGER and not BIGINT. The original value
# here was 8814887630, which is 4.1x over the 2147483647 ceiling, so every INSERT
# and the DELETE in `_cleanup` raised asyncpg DataError "value out of int32 range"
# and all three tests in this file failed the moment they met a real Postgres.
# Nothing local catches that: this module is skipped without
# SEARCH_TEST_DATABASE_URL, so the CI `search-recall` job is its only reader.
EVENT_ID = 881488763
SPORT_ID = 88148

# Kalshi: five legs, TWO of them at Polymarket's modal price. Five legs at
# eligible=5 means Kalshi's own mode needs count > GREATEST(2.5, 2) = 2.5, and
# 2 is not > 2.5 — so Kalshi forms NO mode of its own and every one of its legs
# is publishable on its own merits. Anything that deletes them came from the
# other source.
KALSHI_LEGS = {
    8814001: 0.5,
    8814002: 0.5,
    8814003: 0.25,
    8814004: 0.125,
    8814005: 0.625,
}
# Polymarket: four legs, ALL at 0.5. eligible=4, so its mode needs
# count > GREATEST(2, 2) = 2, and 4 is. These four SHOULD be deleted — by their
# own mode, among themselves.
POLY_LEGS = {8814101: 0.5, 8814102: 0.5, 8814103: 0.5, 8814104: 0.5}

ALL_IDS = sorted(list(KALSHI_LEGS) + list(POLY_LEGS))

# Prices are all exactly representable in binary floating point on purpose: the
# join predicate under test is an equality on ``adj_opening_probability``, and a
# gate that could fail on a representation artefact would be reporting on the
# wrong thing.


async def _seed_leg(session, market_id, *, source, price):
    """One resolved single-outcome market on the shared event.

    Each leg is its own market carrying its own winner, so no market "graded
    nobody" (``is_no_winner_market``) and none is a 2-outcome mex binary with a
    bad winner count (``is_malformed_binary``). ``mutually_exclusive`` false and
    ``market_type='binary'`` keep every leg out of the mex/field normalization
    arm, which is exempt from mode dedup — the arm under test is the ordinary
    non-partition multi pool, which is where the defect acts.
    """
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO futures_markets (id, external_id, name, source, status, "
            "category, event_id, mutually_exclusive, market_type, "
            "llm_sport_category, volume) "
            "VALUES (:id, :xid, :nm, :src, 'resolved', 'championship', :ev, "
            "false, 'binary', 'politics', 100)"
        ),
        {
            "id": market_id,
            "xid": f"test-2098-{market_id}",
            "nm": f"market-{market_id}",
            "src": source,
            "ev": EVENT_ID,
        },
    )
    await session.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
            "opening_probability, calibration_probability, is_winner, "
            "resolution_source, volume) VALUES "
            "(:id, :mid, :xid, :nm, :p, :p, true, 'api_settlement', 10)"
        ),
        {
            "id": market_id,
            "mid": market_id,
            "xid": f"test-2098-out-{market_id}",
            "nm": f"leg-{market_id}",
            "p": price,
        },
    )
    # A real trade, so the Kalshi legs clear the bid/trade liquidity predicate
    # (#940) AND the Polymarket legs are NOT never-traded placeholders. Both
    # matter: if either source's legs were excluded by some OTHER rule, the
    # assertion below would pass for a reason that has nothing to do with the
    # join under test.
    await session.execute(
        text(
            "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, probability, "
            "reading_count, last_price, yes_bid) VALUES "
            "(:oid, 'test-2098', :p, 1, :p, :p)"
        ),
        {"oid": market_id, "p": price},
    )


async def _seed_shared_event(session):
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO sports (id, key, name, active) "
            "VALUES (:id, :k, :n, true)"
        ),
        {"id": SPORT_ID, "k": f"test_2098_{SPORT_ID}", "n": "Test 2098"},
    )
    await session.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status) VALUES "
            "(:id, :sid, 'Home 2098', 'Away 2098', :ct, 'completed')"
        ),
        {
            "id": EVENT_ID,
            "sid": SPORT_ID,
            "ct": datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc).replace(tzinfo=None),
        },
    )
    for mid, price in KALSHI_LEGS.items():
        await _seed_leg(session, mid, source="kalshi", price=price)
    for mid, price in POLY_LEGS.items():
        await _seed_leg(session, mid, source="polymarket", price=price)
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


async def test_one_sources_mode_does_not_delete_another_sources_legs():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base
    from app.tasks.precompute_calibration import _calibration_population_ctes

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            await _cleanup(session)
            await _seed_shared_event(session)

            ctes = _calibration_population_ctes()

            # (a) THE PREMISE, asserted rather than assumed. Both sources really
            #     do collide on one source-blind vm_id, and each really does
            #     carry its OWN source-scoped ``eligible``. If a later change
            #     makes vm_id source-carrying, this test's whole subject
            #     disappears and it must say so out loud instead of passing
            #     vacuously.
            shape = (
                await session.execute(
                    text(
                        "WITH "
                        + ctes
                        + " SELECT source, vm_id, MIN(eligible) AS eligible, "
                        "COUNT(*) AS n FROM normalized "
                        "WHERE outcome_id = ANY(:ids) GROUP BY source, vm_id "
                        "ORDER BY source"
                    ),
                    {"ids": ALL_IDS},
                )
            ).all()
            by_source = {r.source: r for r in shape}
            assert set(by_source) == {"kalshi", "polymarket"}, (
                "both sources must reach `normalized`; the collision cannot be "
                f"exercised otherwise (got {shape!r})"
            )
            assert by_source["kalshi"].vm_id == by_source["polymarket"].vm_id, (
                "PREMISE GONE: the two sources no longer share a vm_id, so this "
                "gate is no longer testing #2098. Do not delete it — find out "
                "what changed in `virtual_market` and re-aim it."
            )
            assert by_source["kalshi"].eligible == 5
            assert by_source["polymarket"].eligible == 4
            assert by_source["kalshi"].n == 5 and by_source["polymarket"].n == 4

            # (b) THE FIX. Every Kalshi leg publishes — including the two at
            #     0.5, Polymarket's modal price. Revert either half of the join
            #     fix and 8814001/8814002 vanish here.
            published = {
                r.outcome_id
                for r in (
                    await session.execute(
                        text(
                            "WITH "
                            + ctes
                            + " SELECT outcome_id FROM deduped "
                            "WHERE outcome_id = ANY(:ids)"
                        ),
                        {"ids": ALL_IDS},
                    )
                ).all()
            }
            assert published == set(KALSHI_LEGS), (
                "#2098: one source's mode price must not delete another "
                "source's legs, and the other source's own mode must still "
                f"fire. published={sorted(published)} "
                f"expected={sorted(KALSHI_LEGS)}"
            )

            # (c) THE FALSIFIER, stated separately so a failure names which half
            #     broke. Polymarket's four legs are STILL deduped among
            #     themselves — the fix scopes the mechanism, it does not
            #     disable it. A fix that restores rows by turning dedup off is
            #     worse than the defect it removes.
            assert not (published & set(POLY_LEGS)), (
                "dedup was DISABLED, not scoped: Polymarket's own 4-leg mode "
                f"must still delete its own legs (leaked {sorted(published & set(POLY_LEGS))})"
            )

            # (d) The restored rows are CORRECT, not merely present (cert §3b):
            #     the published Kalshi legs carry the values the source
            #     published, not nulls extended by a changed join shape.
            rows = (
                await session.execute(
                    text(
                        "WITH "
                        + ctes
                        + " SELECT outcome_id, source, is_winner, "
                        "adj_opening_probability AS p FROM deduped "
                        "WHERE outcome_id = ANY(:ids) ORDER BY outcome_id"
                    ),
                    {"ids": ALL_IDS},
                )
            ).all()
            assert [r.source for r in rows] == ["kalshi"] * len(KALSHI_LEGS)
            assert all(r.is_winner for r in rows), "is_winner must survive the join"
            assert {r.outcome_id: float(r.p) for r in rows} == {
                oid: float(p) for oid, p in KALSHI_LEGS.items()
            }, "prices must be the published values, unchanged by the join shape"
    finally:
        async with Session() as session:
            await _cleanup(session)
        await engine.dispose()


#: The exact reverts, as (fixed, broken) pairs. Applied to the SQL string and
#: then EXECUTED — this is not a string assertion standing in for behaviour, it
#: is the pre-fix statement run against a real database.
_REVERTS = (
    (
        "SELECT vm_id, source, adj_opening_probability AS mode_price",
        "SELECT vm_id, adj_opening_probability AS mode_price",
    ),
    (
        "GROUP BY vm_id, source, adj_opening_probability, eligible",
        "GROUP BY vm_id, adj_opening_probability, eligible",
    ),
    ("                  AND mp.source = ro.source\n", ""),
)


def _revert_the_fix(ctes: str) -> str:
    """The pre-#2098 CTE chain, or a loud failure.

    Every substitution must match EXACTLY ONCE. A revert arm that silently
    failed to revert would execute the FIXED sql, observe no suppression, and
    report that red-first was proved — the empty-200 failure shape (gotcha #53)
    wearing a test's clothes. So the count is asserted, not assumed.
    """
    out = ctes
    for fixed, broken in _REVERTS:
        n = out.count(fixed)
        assert n == 1, (
            f"cannot revert the #2098 fix: expected exactly one occurrence of "
            f"{fixed!r}, found {n}. The SQL moved — re-aim this arm rather than "
            "deleting it, or the red-first proof becomes vacuous."
        )
        out = out.replace(fixed, broken, 1)
    assert "mp.source" not in out, "revert incomplete"
    return out


async def test_red_first_the_reverted_join_still_reproduces_the_suppression():
    """RED-FIRST, proved in the same run (the two-armed pattern already used by
    ``test_create_wave_insert_bind_contract.py``).

    A green regression guard proves the defect is absent. It does NOT prove the
    guard would have caught it — and this file cannot be run red on the lane's
    own machine, because there is no local Postgres in the agent sandbox
    (``initdb`` dies on ``shmget``). So the pre-fix statement is reconstructed
    and executed here: with ``source`` removed from ``mode_prices``' projection
    and GROUP BY and from ``deduped``'s join, Polymarket's four-leg mode must
    delete the two Kalshi legs sitting at its modal price.

    If this arm ever fails, the defect is no longer reproducible by this
    fixture and the guard beside it is no longer known to be load-bearing.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base
    from app.tasks.precompute_calibration import _calibration_population_ctes

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            await _cleanup(session)
            await _seed_shared_event(session)

            broken = _revert_the_fix(_calibration_population_ctes())
            published = {
                r.outcome_id
                for r in (
                    await session.execute(
                        text(
                            "WITH "
                            + broken
                            + " SELECT outcome_id FROM deduped "
                            "WHERE outcome_id = ANY(:ids)"
                        ),
                        {"ids": ALL_IDS},
                    )
                ).all()
            }
            suppressed = {8814001, 8814002}
            assert published == set(KALSHI_LEGS) - suppressed, (
                "the #2098 defect is NO LONGER REPRODUCIBLE by this fixture, so "
                "the guard beside it is no longer known to catch anything. "
                f"reverted-SQL published={sorted(published)}, expected the two "
                f"Kalshi legs at Polymarket's modal price to be deleted: "
                f"{sorted(suppressed)}"
            )
    finally:
        async with Session() as session:
            await _cleanup(session)
        await engine.dispose()


async def test_a_single_source_event_is_unaffected_by_the_source_scoping():
    """THE CONTROL (cert §3a, the falsifier attacked first).

    Adding ``source`` to a GROUP BY and to a join can only change behaviour
    where more than one source is present. Where exactly one is, the fix must
    be a no-op — mode dedup still deletes a genuine within-source mode. If this
    ever fails, the join predicate is doing something other than what is
    claimed and the 0.000-pp control-cell prediction is wrong.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base
    from app.tasks.precompute_calibration import _calibration_population_ctes

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            await _cleanup(session)
            from sqlalchemy import text as _t

            await session.execute(
                _t(
                    "INSERT INTO sports (id, key, name, active) "
                    "VALUES (:id, :k, :n, true)"
                ),
                {"id": SPORT_ID, "k": f"test_2098_{SPORT_ID}", "n": "Test 2098"},
            )
            await session.execute(
                _t(
                    "INSERT INTO events (id, sport_id, home_team_name, "
                    "away_team_name, commence_time, status) VALUES "
                    "(:id, :sid, 'Home 2098', 'Away 2098', :ct, 'completed')"
                ),
                {
                    "id": EVENT_ID,
                    "sid": SPORT_ID,
                    "ct": datetime(2026, 1, 2, 3, 4),
                },
            )
            # Kalshi alone, four legs, three of them at 0.5: count 3 >
            # GREATEST(4*0.5, 2) = 2, so this IS a genuine within-source mode
            # and those three must still be deleted.
            solo = {8814001: 0.5, 8814002: 0.5, 8814003: 0.5, 8814004: 0.25}
            for mid, price in solo.items():
                await _seed_leg(session, mid, source="kalshi", price=price)
            await session.commit()

            published = {
                r.outcome_id
                for r in (
                    await session.execute(
                        text(
                            "WITH "
                            + _calibration_population_ctes()
                            + " SELECT outcome_id FROM deduped "
                            "WHERE outcome_id = ANY(:ids)"
                        ),
                        {"ids": sorted(solo)},
                    )
                ).all()
            }
            assert published == {8814004}, (
                "single-source behaviour must be untouched by source-scoping: "
                f"the 3-leg mode at 0.5 must still be deleted (got {sorted(published)})"
            )
    finally:
        async with Session() as session:
            await _cleanup(session)
        await engine.dispose()
