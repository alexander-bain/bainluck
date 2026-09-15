"""#6211 — the DataGolf field-verification exclusion, proved on ROWS.

THE DEFECT
----------
``market_info`` drops a DataGolf market flagged ``datagolf_recovery_residual``
whole. Its comment said that flag "is expected to be ~0". Measured on production
2026-09-15 (``artifacts-calibration-1310/prod_datagolf_bisect.py``) it was 322 of
340 markets — 94.7% — leaving 18 markets, 36 priced truth-eligible outcomes, ALL
WINNERS, published as a 36.5pp accuracy figure about a named third-party provider.

The cause was upstream: ``get_historical_results`` folded 403 and ReadTimeout into
the same ``[]`` a 404 returns, and ``_recover_datagolf_participation`` wrote that
``[]`` — and any non-429 exception — as the same permanent boolean. So the fix
splits one flag into two claims:

    datagolf_recovery_residual    evidenced absence  (terminal)
    datagolf_recovery_unverified  our call failed    (retryable)

WHY THIS IS A POSTGRES TEST
---------------------------
The contract is about which ROWS survive a JSONB predicate inside a 3,000-line
CTE chain. ``tests/test_datagolf_recovery.py`` guards this area with
``inspect.getsource`` string assertions and every one of them was green for the
whole life of the defect — a string test cannot see a population. This executes
the REAL ``_calibration_population_ctes`` against seeded rows.

SYMMETRY IS THE ASSERTION, NOT THE COUNT
----------------------------------------
The point of the exclusion is that a withheld market loses its winners AND its
losers together. A test that only counted rows would pass on a filter that kept
the winners, which is exactly the defect. So the flagged market is asserted empty
of BOTH, and the clean control is asserted to carry BOTH — a control that
published only winners would make the whole file vacuous.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` and NAMED IN ``ci.yml``: a PG-gated file no
workflow step invokes skips silently while pytest still exits 0.
"""

from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6211 contract",
    ),
]

CLEAN_MID = 962201
RESIDUAL_MID = 962202
UNVERIFIED_MID = 962203

# A make-the-cut board: eight players, four made it. Prices straddle 0.5 so every
# row clears the multi arm's 0.005/0.98 band and nothing is dropped for shape —
# the only thing under test is the market-level verification flag.
BOARD = [
    ("Player A", 0.91, True),
    ("Player B", 0.84, True),
    ("Player C", 0.72, True),
    ("Player D", 0.61, True),
    ("Player E", 0.47, False),
    ("Player F", 0.36, False),
    ("Player G", 0.24, False),
    ("Player H", 0.13, False),
]


async def _seed_market(session, market_id, *, metadata: dict | None):
    """One resolved DataGolf make_cut market.

    ``category`` is NOT NULL with no server default and ``llm_sport_category`` is
    the CELL key the population groups on — omitting either kills the file with a
    NotNullViolation or an empty population rather than weakening one assertion.
    """
    await session.execute(
        text(
            "INSERT INTO futures_markets (id, external_id, name, source, status, "
            "category, mutually_exclusive, market_type, llm_sport_category, volume, "
            "market_metadata, resolution_date) VALUES "
            "(:id, :xid, :nm, 'datagolf', 'resolved', 'placement', false, "
            "'participation', 'golf', 100, CAST(:meta AS jsonb), "
            "NOW() - INTERVAL '7 days')"
        ),
        {
            "id": market_id,
            "xid": f"datagolf:pga:6211{market_id}:make_cut",
            "nm": f"Test Open {market_id} - Make the Cut",
            "meta": json.dumps(metadata) if metadata is not None else None,
        },
    )
    for idx, (name, prob, winner) in enumerate(BOARD):
        oid = market_id * 1000 + idx
        await session.execute(
            text(
                "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
                "opening_probability, calibration_probability, is_winner, "
                "resolution_source, volume) VALUES "
                "(:id, :mid, :xid, :nm, :p, :p, :win, 'leaderboard', 10)"
            ),
            {
                "id": oid,
                "mid": market_id,
                "xid": f"dg_{market_id}_{idx}",
                "nm": name,
                "p": prob,
                "win": winner,
            },
        )
        await session.execute(
            text(
                "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, "
                "probability, reading_count, last_price, yes_bid, yes_ask) VALUES "
                "(:oid, 'datagolf_model', :p, 1, :p, :p, :p)"
            ),
            {"oid": oid, "p": prob},
        )


async def _published(session, market_id):
    from app.tasks.precompute_calibration import _calibration_population_ctes

    rows = await session.execute(
        text(
            "WITH "
            + _calibration_population_ctes()
            + " SELECT outcome_name, is_winner FROM deduped WHERE market_id = :mid"
        ),
        {"mid": market_id},
    )
    return rows.all()


@pytest.fixture
async def session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        for mid in (CLEAN_MID, RESIDUAL_MID, UNVERIFIED_MID):
            await s.execute(
                text(
                    "DELETE FROM futures_odds_snapshots WHERE outcome_id IN "
                    "(SELECT id FROM futures_outcomes WHERE market_id = :mid)"
                ),
                {"mid": mid},
            )
            await s.execute(
                text("DELETE FROM futures_outcomes WHERE market_id = :mid"), {"mid": mid}
            )
            await s.execute(
                text("DELETE FROM futures_markets WHERE id = :mid"), {"mid": mid}
            )
        await _seed_market(s, CLEAN_MID, metadata=None)
        await _seed_market(
            s, RESIDUAL_MID, metadata={"datagolf_recovery_residual": True}
        )
        await _seed_market(
            s,
            UNVERIFIED_MID,
            metadata={
                "datagolf_recovery_unverified": {
                    "attempts": 2,
                    "last_status": 403,
                    "last_error": "HTTPStatusError 403",
                    "at": "2026-09-15T19:00:00+00:00",
                }
            },
        )
        await s.commit()
        yield s
    await engine.dispose()


async def test_an_unflagged_market_publishes_its_winners_AND_its_losers(session):
    """NON-VACUITY FIRST. Without this the two exclusion assertions prove nothing:
    an empty published set is the expected result of a broken fixture too."""
    rows = await _published(session, CLEAN_MID)
    assert len(rows) == len(BOARD), (
        f"the control must publish its whole board; got {len(rows)}: "
        f"{[r.outcome_name for r in rows]}"
    )
    winners = [r for r in rows if r.is_winner]
    losers = [r for r in rows if not r.is_winner]
    assert winners and losers, (
        "the control published a one-sided population, so this file cannot "
        f"distinguish the defect from the fix: {len(winners)}W/{len(losers)}L"
    )


async def test_an_evidenced_absence_withholds_the_market_WHOLE(session):
    rows = await _published(session, RESIDUAL_MID)
    assert rows == [], (
        "a market DataGolf has no record of must lose winners and losers "
        f"together; these survived: {[(r.outcome_name, r.is_winner) for r in rows]}"
    )


async def test_an_UNVERIFIED_market_is_withheld_just_as_symmetrically(session):
    """The new state must not become a one-sided admission.

    An unverified market's leaderboard winners are truth-eligible while an unknown
    number of its real losers still sit under ``did_not_play``. Publishing it would
    be the same censoring in the other direction — D112's measured lesson.
    """
    rows = await _published(session, UNVERIFIED_MID)
    assert rows == [], (
        "an unverified market leaked into the curve; the winners it admits have "
        "no matching losers: "
        f"{[(r.outcome_name, r.is_winner) for r in rows]}"
    )


async def test_the_exclusion_does_not_leak_across_markets(session):
    """A market-level flag must not remove its neighbours.

    The three markets share a source, a category and a shape and differ only in
    ``market_metadata``; if the predicate were written against the wrong scope the
    control would empty too — and the assertion above would still pass.
    """
    clean = await _published(session, CLEAN_MID)
    assert len(clean) == len(BOARD)
