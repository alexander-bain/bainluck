"""#6317 — a settled field whose winner has no usable forecast publishes NOTHING.

THE DEFECT, on rows. A proved single-winner field (a Vuelta stage, a draft slot,
a "who wins" board) can carry its one winner with no curve price — no opening
was ever captured for that leg, or the leg we hold is one the published
eligibility refuses. Its priced legs are then all losers by construction, and
before this rung they published anyway: the sample was censored ON THE OUTCOME,
because the missing leg is missing precisely because it is the winner.

The only guard that asked "did the winner survive" (``survivor_win_n = 1`` in
``normalized``) sat behind ``mnm_cp_sum > MEX_NORMALIZE_THRESHOLD``. A field
missing its winner's price mass sums LOW, so that defence was weakest exactly
where the censoring is guaranteed.

WHY POSTGRES. The defect is which ROWS the real ``_calibration_population_ctes``
selects, so this executes it against seeded rows (the #5305 ladder file is the
template). Opt-in on ``SEARCH_TEST_DATABASE_URL`` and named in ``ci.yml``.

THE CONTROLS ARE HALF THE TEST. A rung that drops every low-sum field would also
pass the defect arm, so each control pins a population that must KEEP publishing:

* a low-sum field whose winner IS priced (a thin field is not a wrong one);
* a winner priced only by its opening (``COALESCE(calibration, opening)`` is the
  curve price — the fallback is a valid forecast, not a missing one);
* a complete, normalised field (sum > 1.15) — unchanged, still sums to ~1.0.

And one more defect arm: a winner that HAS an opening but which the published
eligibility refuses (a never-bid Kalshi leg). Its losers are the same censored
sample, so "usable forecast" is judged by the same survivor test the curve
publishes on, not by "an opening exists".
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
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6317 field contract",
    ),
]

# Market ids well clear of anything the sibling PG gates seed.
UNPRICED_WINNER_MID = 963171
PRICED_WINNER_MID = 963172
OPENING_ONLY_WINNER_MID = 963173
COMPLETE_FIELD_MID = 963174
REFUSED_WINNER_MID = 963175
ALL_MIDS = [
    UNPRICED_WINNER_MID,
    PRICED_WINNER_MID,
    OPENING_ONLY_WINNER_MID,
    COMPLETE_FIELD_MID,
    REFUSED_WINNER_MID,
]

#: The persisted shape evidence ``exclusivity_proved_sql`` requires. Without it a
#: market never reaches ``mex_field_candidates`` and every assertion below would
#: be about the multi pool instead of a proved field.
PROVED_FIELD_METADATA = json.dumps(
    {"shape": {"exhaustive": True, "expected_winners": 1, "outcome_relation": "competitors"}}
)


async def _seed_market(session, market_id):
    """One resolved Kalshi proved single-winner FIELD.

    ``futures_markets.category`` is NOT NULL with no default and is seeded with a
    constant; ``llm_sport_category`` is the cell key the population groups on.
    """
    await session.execute(
        text(
            "INSERT INTO futures_markets (id, external_id, name, source, status, "
            "category, mutually_exclusive, market_type, llm_sport_category, volume, "
            "market_metadata) VALUES (:id, :xid, :nm, 'kalshi', 'resolved', "
            "'championship', true, 'field', 'cycling', 100, CAST(:meta AS JSONB))"
        ),
        {
            "id": market_id,
            "xid": f"test-6317-{market_id}",
            "nm": f"Stage winner {market_id}",
            "meta": PROVED_FIELD_METADATA,
        },
    )


async def _seed_outcome(
    session,
    market_id,
    idx,
    name,
    *,
    opening,
    calibration="same",
    winner,
    book=True,
):
    """One resolved outcome.

    ``opening=None`` is the unpriced leg: no opening, no calibration price, no
    snapshot — the shape the issue measured on Kalshi Vuelta stages.
    ``book=False`` keeps the opening but seeds a snapshot with NO bid, so the
    leg fails the Kalshi liquidity / writer-bar evidence the curve requires.
    Otherwise both sides are seeded (``yes_ask = yes_bid`` is a zero spread), so
    each priced leg clears #940's bid test and #5401's two-sided writer bar and
    the file measures the #6317 rung and only that.
    """
    oid = market_id * 100 + idx
    cal = opening if calibration == "same" else calibration
    await session.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
            "opening_probability, calibration_probability, is_winner, "
            "resolution_source, volume) VALUES "
            "(:id, :mid, :xid, :nm, :op, :cal, :win, 'api_settlement', 10)"
        ),
        {
            "id": oid,
            "mid": market_id,
            "xid": f"test-6317-out-{oid}",
            "nm": name,
            "op": opening,
            "cal": cal,
            "win": winner,
        },
    )
    if opening is not None:
        bid = opening if book else 0
        ask = opening if book else None
        await session.execute(
            text(
                "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, "
                "probability, reading_count, last_price, yes_bid, yes_ask) VALUES "
                "(:oid, 'test-6317', :p, 1, :lp, :bid, :ask)"
            ),
            {"oid": oid, "p": opening, "lp": opening if book else 0, "bid": bid, "ask": ask},
        )
    return oid


async def _seeded_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return engine, Session


async def _populate(session):
    # (A) DEFECT: the winner was never priced; three priced losers sum 0.60.
    await _seed_market(session, UNPRICED_WINNER_MID)
    await _seed_outcome(session, UNPRICED_WINNER_MID, 0, "Rider W", opening=None, winner=True)
    for idx, (name, p) in enumerate([("Rider A", 0.31), ("Rider B", 0.18), ("Rider C", 0.11)], 1):
        await _seed_outcome(session, UNPRICED_WINNER_MID, idx, name, opening=p, winner=False)

    # (B) CONTROL: the same thin field, but the winner IS priced. Sum 0.80.
    await _seed_market(session, PRICED_WINNER_MID)
    for idx, (name, p, win) in enumerate(
        [("Rider W", 0.21, True), ("Rider A", 0.29, False), ("Rider B", 0.17, False), ("Rider C", 0.13, False)]
    ):
        await _seed_outcome(session, PRICED_WINNER_MID, idx, name, opening=p, winner=win)

    # (C) CONTROL: the winner has no calibration price, only an opening. The
    # curve price is COALESCE(calibration, opening), so this IS a usable forecast.
    await _seed_market(session, OPENING_ONLY_WINNER_MID)
    await _seed_outcome(
        session, OPENING_ONLY_WINNER_MID, 0, "Rider W", opening=0.22, calibration=None, winner=True
    )
    for idx, (name, p) in enumerate([("Rider A", 0.33), ("Rider B", 0.16), ("Rider C", 0.12)], 1):
        await _seed_outcome(session, OPENING_ONLY_WINNER_MID, idx, name, opening=p, winner=False)

    # (D) CONTROL: a complete field whose prices sum past 1.15 — normalised and
    # published whole, exactly as before.
    await _seed_market(session, COMPLETE_FIELD_MID)
    for idx, (name, p, win) in enumerate(
        [("Rider W", 0.42, True), ("Rider A", 0.38, False), ("Rider B", 0.26, False), ("Rider C", 0.14, False)]
    ):
        await _seed_outcome(session, COMPLETE_FIELD_MID, idx, name, opening=p, winner=win)

    # (E) DEFECT: the winner has an opening, but no order book ever stood behind
    # it (never bid), so the curve refuses that leg. Its three losers are the
    # same outcome-censored sample as (A). Sum of the publishable legs 0.62.
    await _seed_market(session, REFUSED_WINNER_MID)
    await _seed_outcome(session, REFUSED_WINNER_MID, 0, "Rider W", opening=0.24, winner=True, book=False)
    for idx, (name, p) in enumerate([("Rider A", 0.30), ("Rider B", 0.19), ("Rider C", 0.13)], 1):
        await _seed_outcome(session, REFUSED_WINNER_MID, idx, name, opening=p, winner=False)

    await session.commit()


async def _published(session, market_id):
    from app.tasks.precompute_calibration import _calibration_population_ctes

    ctes = _calibration_population_ctes()
    result = await session.execute(
        text(
            "WITH "
            + ctes
            + " SELECT outcome_id, outcome_name, is_winner, adj_opening_probability AS p"
            " FROM deduped WHERE market_id = :mid ORDER BY outcome_id"
        ),
        {"mid": market_id},
    )
    return result.all()


async def _normalized_count(session, market_id):
    from app.tasks.precompute_calibration import _calibration_population_ctes

    ctes = _calibration_population_ctes()
    return (
        await session.execute(
            text("WITH " + ctes + " SELECT COUNT(*) FROM normalized WHERE market_id = :mid"),
            {"mid": market_id},
        )
    ).scalar_one()


async def _with_rows(test_body):
    engine, Session = await _seeded_session()
    try:
        await _cleanup(Session)
        async with Session() as session:
            await _populate(session)
            await test_body(session)
        await _cleanup(Session)
    finally:
        await engine.dispose()


async def test_a_field_whose_winner_was_never_priced_publishes_none_of_its_losers():
    async def body(session):
        # NON-VACUITY FIRST: the three losers must be live candidates. If the
        # fixture failed liquidity or truth gates, ``deduped`` would be empty for
        # reasons unrelated to this rung and the assertion below proves nothing.
        assert await _normalized_count(session, UNPRICED_WINNER_MID) == 3, (
            "fixture is not exercising the rung: expected 3 priced losers in normalized"
        )
        published = await _published(session, UNPRICED_WINNER_MID)
        assert published == [], (
            "a field whose one winner carries no price must not publish its priced "
            f"losers as confident misses; got {[(r.outcome_name, float(r.p)) for r in published]}"
        )

    await _with_rows(body)


async def test_a_winner_the_curve_refuses_takes_its_field_out_with_it():
    async def body(session):
        assert await _normalized_count(session, REFUSED_WINNER_MID) == 4, (
            "fixture is not exercising the rung: all four legs must reach normalized"
        )
        published = await _published(session, REFUSED_WINNER_MID)
        assert published == [], (
            "the winner's only quote fails the published book evidence, so its losers "
            "are an outcome-censored sample too; got "
            f"{[(r.outcome_name, float(r.p)) for r in published]}"
        )

    await _with_rows(body)


async def test_a_thin_field_with_a_priced_winner_still_publishes_every_leg():
    async def body(session):
        published = await _published(session, PRICED_WINNER_MID)
        assert len(published) == 4, (
            "a low-sum field whose winner is priced is a thin field, not a censored one; "
            f"got {[r.outcome_name for r in published]}"
        )
        assert sum(1 for r in published if r.is_winner) == 1

    await _with_rows(body)


async def test_a_winner_priced_only_by_its_opening_is_a_usable_forecast():
    async def body(session):
        published = await _published(session, OPENING_ONLY_WINNER_MID)
        names = [r.outcome_name for r in published]
        assert len(published) == 4 and "Rider W" in names, (
            "COALESCE(calibration, opening) is the curve price, so an opening-only winner "
            f"keeps its field publishable; got {names}"
        )

    await _with_rows(body)


async def test_a_complete_normalised_field_is_unchanged():
    async def body(session):
        published = await _published(session, COMPLETE_FIELD_MID)
        assert len(published) == 4, [r.outcome_name for r in published]
        total = sum(float(r.p) for r in published)
        assert 0.98 < total < 1.02, f"a complete field still normalises to ~1.0; got {total}"

    await _with_rows(body)


async def test_the_rung_names_its_own_rows_and_nothing_else():
    """gotcha #53: the exclusion must be visible as itself, not as a silent drop.

    Exactly the two defect fields carry the flag, on every one of their rows that
    reached ``normalized``; no control row carries it.
    """

    async def body(session):
        from app.tasks.precompute_calibration import _calibration_population_ctes

        ctes = _calibration_population_ctes()
        rows = (
            await session.execute(
                text(
                    "WITH "
                    + ctes
                    + " SELECT market_id, COUNT(*) AS n,"
                    " COUNT(*) FILTER (WHERE is_field_winner_unpublished) AS flagged"
                    " FROM normalized WHERE market_id = ANY(:mids) GROUP BY market_id"
                ),
                {"mids": ALL_MIDS},
            )
        ).all()
        by_market = {r.market_id: (r.n, r.flagged) for r in rows}
        assert by_market[UNPRICED_WINNER_MID] == (3, 3)
        assert by_market[REFUSED_WINNER_MID] == (4, 4)
        for control in (PRICED_WINNER_MID, OPENING_ONLY_WINNER_MID, COMPLETE_FIELD_MID):
            assert by_market[control][1] == 0, f"control market {control} was flagged"

    await _with_rows(body)


async def _cleanup(Session):
    async with Session() as session:
        await session.execute(
            text(
                "DELETE FROM futures_odds_snapshots WHERE outcome_id IN "
                "(SELECT id FROM futures_outcomes WHERE market_id = ANY(:ids))"
            ),
            {"ids": ALL_MIDS},
        )
        await session.execute(
            text("DELETE FROM futures_outcomes WHERE market_id = ANY(:ids)"),
            {"ids": ALL_MIDS},
        )
        await session.execute(
            text("DELETE FROM futures_markets WHERE id = ANY(:ids)"),
            {"ids": ALL_MIDS},
        )
        await session.commit()
