"""#1523 — the producer's real main statement counts what the bid-support test
removes from the PUBLISHED curve, against a real Postgres.

The unit file (``tests/test_calibration_poly_unsupported_midpoint_1523.py``)
runs the placeholder expression on SQLite. This runs the whole
``_main_futures_sql`` — the ``deduped_eligible`` / ``deduped`` split, the
``poly_unsupported_bid_summary`` CTE and its ``jsonb_object_agg`` — because
those only exist on Postgres and only mean something inside the full chain.

Four resolved two-leg Polymarket markets in one category, each leg at 0.50:

* WIDE — bid 0.03 / ask 0.97 for life, no trade (the #1523 specimen shape):
  the new rule removes both legs, the #151 rule kept them. COUNTED.
* TIGHT — bid 0.47 / ask 0.53, no trade: a real coin flip. PUBLISHED.
* NO_BID — no bid, ask 1.00, no trade: #151 already excluded it. Removed, but
  NOT counted — a row the old rule excluded must never excuse a new loss.
* TRADED — bid 0.08 / ask 0.69, last_price 0.50. PUBLISHED.
"""

import json
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
            "CALIBRATION_TEST_DATABASE_URL to run the #1523 producer gate"
        ),
    ),
]

# int32-safe ids, far from every other gate's block.
# A category no other gate seeds: CI runs every `_pg` file against one shared
# database, so assertions read this cell only.
CATEGORY = "test_1523_table_tennis"

#: market id -> (snapshot (yes_bid, yes_ask, last_price), name)
MARKETS = {
    91523101: ((0.03, 0.97, None), "wide"),
    91523102: ((0.47, 0.53, None), "tight"),
    91523103: ((None, 1.0, None), "no_bid"),
    91523104: ((0.08, 0.69, 0.5), "traded"),
}


def _outcome_ids(market_id):
    return (market_id * 10 + 1, market_id * 10 + 2)


ALL_OUTCOMES = sorted(o for m in MARKETS for o in _outcome_ids(m))


async def _seed(session):
    from sqlalchemy import text

    for market_id, ((bid, ask, last), name) in MARKETS.items():
        await session.execute(
            text(
                "INSERT INTO futures_markets (id, external_id, name, source, status, "
                "category, event_id, mutually_exclusive, market_type, "
                "llm_sport_category, volume, resolution_date) "
                "VALUES (:id, :xid, :nm, 'polymarket', 'resolved', 'championship', "
                "NULL, true, 'binary', :cat, 100, :rd)"
            ),
            # No shared event: each market is its own question. On one event
            # the four would merge into a single 8-leg question priced all at
            # 0.50, and the mode-price rung (not this rule) would remove it.
            {"id": market_id, "xid": f"test-1523-{market_id}", "nm": f"1523 {name}",
             "cat": CATEGORY,
             "rd": datetime(2026, 9, 14, 6, 0, tzinfo=timezone.utc).replace(tzinfo=None)},
        )
        for idx, outcome_id in enumerate(_outcome_ids(market_id)):
            await session.execute(
                text(
                    "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
                    "opening_probability, calibration_probability, is_winner, "
                    "resolution_source, volume) VALUES "
                    "(:id, :mid, :xid, :nm, 0.5, 0.5, :w, 'api_settlement', 10)"
                ),
                {"id": outcome_id, "mid": market_id, "xid": f"test-1523-out-{outcome_id}",
                 "nm": ("Yes", "No")[idx], "w": idx == 0},
            )
            await session.execute(
                text(
                    "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, "
                    "probability, reading_count, last_price, yes_bid, yes_ask) VALUES "
                    "(:oid, 'test-1523', 0.5, 1, :l, :b, :a)"
                ),
                {"oid": outcome_id, "l": last, "b": bid, "a": ask},
            )
    await session.commit()


async def _cleanup(session):
    from sqlalchemy import text

    await session.execute(
        text("DELETE FROM futures_odds_snapshots WHERE outcome_id = ANY(:ids)"),
        {"ids": ALL_OUTCOMES},
    )
    await session.execute(
        text("DELETE FROM futures_outcomes WHERE id = ANY(:ids)"), {"ids": ALL_OUTCOMES}
    )
    await session.execute(
        text("DELETE FROM futures_markets WHERE id = ANY(:ids)"), {"ids": list(MARKETS)}
    )
    await session.commit()


async def _run(sql_text, params=None):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            await _cleanup(session)
            await _seed(session)
            try:
                return (await session.execute(text(sql_text), params or {})).all()
            finally:
                await session.rollback()
                await _cleanup(session)
    finally:
        await engine.dispose()


async def test_the_published_curve_keeps_the_supported_pairs_only():
    from app.tasks.precompute_calibration import _calibration_population_ctes

    rows = await _run(
        "WITH " + _calibration_population_ctes()
        + " SELECT outcome_id, is_poly_placeholder, is_poly_placeholder_pre1523"
        " FROM deduped_eligible WHERE outcome_id = ANY(:ids) ORDER BY outcome_id",
        {"ids": ALL_OUTCOMES},
    )
    flags = {r.outcome_id: (r.is_poly_placeholder, r.is_poly_placeholder_pre1523) for r in rows}
    # A binary question publishes ONE representative leg (`rn = 1`: nearest
    # 0.50, ties by outcome id), so each market reaches the eligible set once.
    # Every market does reach it: no OTHER rung is what removes them.
    wide, tight, no_bid, traded = (_outcome_ids(m)[0] for m in MARKETS)
    assert set(flags) == {wide, tight, no_bid, traded}, flags
    assert flags[wide] == (True, False)
    assert flags[tight] == (False, False) and flags[traded] == (False, False)
    assert flags[no_bid] == (True, True)

    published = await _run(
        "WITH " + _calibration_population_ctes()
        + " SELECT outcome_id FROM deduped WHERE outcome_id = ANY(:ids) ORDER BY outcome_id",
        {"ids": ALL_OUTCOMES},
    )
    assert [r.outcome_id for r in published] == sorted([tight, traded])


@pytest.mark.parametrize("frozen", [False])
async def test_the_main_statement_states_the_delta_per_cell(frozen):
    from app.tasks.precompute_calibration import _main_futures_sql

    rows = await _run(_main_futures_sql(frozen=frozen))
    assert rows, "the statement returned no rows at all"
    first = rows[0]
        # WIDE's representative only. NO_BID's was excluded by #151 already and is
    # deliberately not in the count.
    by_cell = json.loads(first.poly_unsupported_bid_by_cell)
    assert by_cell[f"polymarket/{CATEGORY}"] == 1
    assert first.poly_unsupported_bid_excluded == sum(by_cell.values())
    published = sum(r.n for r in rows if r.source == "polymarket" and r.category == CATEGORY)
    assert published == 2
