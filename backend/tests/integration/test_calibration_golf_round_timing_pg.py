"""#938 — a Kalshi golf ROUND market's price cannot be placed before its round.

THE DEFECT
----------
Kalshi gives a round market (``KXPGAR3TOP10-…``, ``KXDPWORLDTOURR1LEAD-…``) one
time, the round's CLOSE, and it is stored as ``futures_markets.commence_time``.
Every closing-line selector bounds on that column, so on a round market "the
last quote before commence" is a quote from inside the round, and a later
writer filled the rest from post-settlement snapshots. The specimen,
``KXPGAR3TOP10-THOC26`` (The Open, round 3 top 10), stores 0.99 on all ten
winners and 0.01 on every loser, against pre-round quotes of 0.10–0.18 (bid
0.02–0.03, ask 0.17–0.33): those are the values of snapshots captured on and
after 07-23, five days after the round settled. Its tournament sibling
``KXPGATOP10-THOC26`` keeps genuine pre-tournament prices.

THE RULE
--------
Keyed on STRUCTURE, never on the outcome: a Kalshi golf market whose ticker's
first segment names a round (``R[0-9]+(LEAD|TOP[0-9]+)$``) leaves the curve
whole. No stored time places a round's start, so no price on it can be proved to
precede the round. The fixtures below therefore carry ORDINARY, plausible
pre-round prices on the withheld boards: the rule must drop them anyway, and a
rule that only caught 0.99/0.01 rows would be selecting on the answer.

WHY THIS IS A POSTGRES TEST
---------------------------
The contract is which ROWS survive a correlated ticker predicate inside the
canonical population chain. This executes the REAL ``_calibration_population_ctes``
and the REAL coverage-bridge rung predicates against seeded rows.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` and NAMED IN ``ci.yml``: a PG-gated file no
workflow step invokes skips silently while pytest still exits 0.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #938 contract",
    ),
]

# Fixed once per run: offset FIRST, never branch on the clock (gotcha #44).
NOW = datetime.now(timezone.utc).replace(microsecond=0)
COMMENCE = NOW - timedelta(days=10)

# Distinct prices inside 0.005..0.98 so the multi arm's mode/tail heuristics
# drop nothing. Top-N boards are independent binaries (not a partition), so the
# controls cannot be taken down by field completeness.
TOPN_BOARD = [
    ("Leader A", 0.83, True),
    ("Leader B", 0.64, True),
    ("Chaser C", 0.41, False),
    ("Chaser D", 0.27, False),
    ("Field E", 0.12, False),
]

#: (market id, ticker, source, category) — the WITHHELD boards first.
ROUND_TOPN_MID = 938001  # the specimen's shape: round 3 top 10
ROUND_LEAD_MID = 938002  # round leader on another tour
ROUND_TOP5_MID = 938003  # round 1 top 5
#: Controls.
TOURNEY_TOPN_MID = 938011  # the specimen's tournament sibling
TOURNEY_LEAD_MID = 938012  # tournament-long market whose code holds an R
OTHER_SOURCE_MID = 938013  # a polymarket golf market with a round-shaped id
OTHER_SPORT_MID = 938014  # a Kalshi round-leader series outside golf
TOURNEY_YEAR_MID = 938015  # a tournament series whose code carries a year
MARGIN_PROP_MID = 938016  # a prop that merely mentions a round lead

MARKETS = [
    (ROUND_TOPN_MID, "KXPGAR3TOP10-THOC26", "kalshi", "golf"),
    (ROUND_LEAD_MID, "KXDPWORLDTOURR1LEAD-HEIO26", "kalshi", "golf"),
    (ROUND_TOP5_MID, "KXPGAR1TOP5-THOC26", "kalshi", "golf"),
    (TOURNEY_TOPN_MID, "KXPGATOP10-THOC26", "kalshi", "golf"),
    # ``KXPGAROUNDSCORE`` carries an R that is not a round: the anchor needs a
    # digit and a LEAD/TOPn tail, so it must stay.
    (TOURNEY_LEAD_MID, "KXPGAROUNDSCORE-THOC26", "kalshi", "golf"),
    (OTHER_SOURCE_MID, "KXPGAR2TOP10-THOC26", "polymarket", "golf"),
    (OTHER_SPORT_MID, "KXMLBHRDERBYR1LEAD-26", "kalshi", "baseball"),
    # ``…TOUR2026`` holds ``R2`` but names no round: the tail anchor is what
    # keeps it (the false-positive class ``ROUND_SERIES_PATTERN`` records).
    (TOURNEY_YEAR_MID, "KXPGATOUR2026-THOC26", "kalshi", "golf"),
    # The END anchor: a margin prop that only mentions a round lead is not a
    # round market (the reason ``calibration_cell_exact`` anchors its family test).
    (MARGIN_PROP_MID, "KXPGAR1LEADMARGIN-THOC26", "kalshi", "golf"),
]
WITHHELD_MIDS = {ROUND_TOPN_MID, ROUND_LEAD_MID, ROUND_TOP5_MID}
KEPT_MIDS = {m for m, *_r in MARKETS} - WITHHELD_MIDS
ALL_MIDS = tuple(m for m, *_r in MARKETS)


async def _seed_market(session, mid, ticker, source, category):
    await session.execute(
        text(
            "INSERT INTO futures_markets (id, external_id, name, source, status, "
            "category, mutually_exclusive, market_type, llm_sport_category, volume, "
            "commence_time, resolution_date) VALUES "
            "(:id, :xid, :nm, :src, 'resolved', 'placement', false, "
            "'participation', :cat, 100, :ct, :rd)"
        ),
        {
            "id": mid,
            "xid": ticker,
            "nm": f"Test {ticker}",
            "src": source,
            "cat": category,
            "ct": COMMENCE,
            "rd": COMMENCE + timedelta(hours=1),
        },
    )


async def _seed_outcome(session, oid, mid, source, name, price, winner):
    await session.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
            "opening_probability, calibration_probability, is_winner, "
            "resolution_source, volume) VALUES "
            "(:id, :mid, :xid, :nm, :p, :p, :win, 'api_settlement', 10)"
        ),
        {
            "id": oid,
            "mid": mid,
            "xid": f"t938_{oid}",
            "nm": name,
            "p": price,
            "win": winner,
        },
    )
    # A real two-sided book well before commence: it clears the Kalshi
    # liquidity and writer-bar rungs, so a withheld row is withheld by THIS
    # rule and not by a neighbour.
    await session.execute(
        text(
            "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, "
            "probability, reading_count, last_price, yes_bid, yes_ask, "
            "captured_at) VALUES "
            "(:oid, :bk, :p, 1, :p, :bid, :ask, :at)"
        ),
        {
            "oid": oid,
            "bk": source,
            "p": price,
            "bid": round(price - 0.01, 4),
            "ask": round(price + 0.01, 4),
            "at": COMMENCE - timedelta(days=2),
        },
    )


async def _clear(session):
    for mid in ALL_MIDS:
        await session.execute(
            text(
                "DELETE FROM futures_odds_snapshots WHERE outcome_id IN "
                "(SELECT id FROM futures_outcomes WHERE market_id = :mid)"
            ),
            {"mid": mid},
        )
        await session.execute(
            text("DELETE FROM futures_outcomes WHERE market_id = :mid"), {"mid": mid}
        )
        await session.execute(text("DELETE FROM futures_markets WHERE id = :mid"), {"mid": mid})


@pytest.fixture
async def session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await _clear(s)
        for mid, ticker, source, category in MARKETS:
            await _seed_market(s, mid, ticker, source, category)
            for idx, (name, price, win) in enumerate(TOPN_BOARD):
                await _seed_outcome(s, mid * 100 + idx, mid, source, name, price, win)
        await s.commit()
        yield s
        await _clear(s)
        await s.commit()
    await engine.dispose()


async def _published(session):
    from app.tasks.precompute_calibration import _calibration_population_ctes

    rows = await session.execute(
        text(
            "WITH "
            + _calibration_population_ctes()
            + " SELECT market_id, outcome_name, raw_cp FROM deduped"
            " WHERE market_id = ANY(:mids)"
        ),
        {"mids": list(ALL_MIDS)},
    )
    out: dict[int, dict[str, float]] = {}
    for r in rows.all():
        out.setdefault(r.market_id, {})[r.outcome_name] = float(r.raw_cp)
    return out


async def test_the_controls_publish_whole_at_their_own_prices(session):
    """NON-VACUITY FIRST: an empty published set is also what a broken fixture
    yields, so the withheld assertion means nothing until every control board
    publishes, every row, unchanged."""
    published = await _published(session)
    board = {name: price for name, price, _w in TOPN_BOARD}
    for mid in KEPT_MIDS:
        assert published.get(mid) == pytest.approx(board), (mid, published.get(mid))


async def test_a_round_market_is_not_scored_whatever_its_prices(session):
    published = await _published(session)
    leaked = {mid: sorted(published[mid]) for mid in WITHHELD_MIDS if mid in published}
    assert not leaked, (
        "a Kalshi golf round market reached the accuracy curve although no stored "
        f"time places its price before the round: {leaked}"
    )


async def test_withheld_rows_are_accounted_on_their_own_rung(session):
    """The coverage bridge's catch-all is where a new ``deduped`` filter lands
    silently. Every withheld row must be claimed by the new rung, using the
    production rung predicates verbatim (first match wins), and every control
    row must be plotted."""
    from app.tasks.precompute_calibration import (
        _COVERAGE_RUNG_PREDICATES,
        _calibration_population_ctes,
        _coverage_universe_cte,
    )

    branches = " ".join(
        f"WHEN {sql} THEN '{key}'" for key, sql in _COVERAGE_RUNG_PREDICATES if sql
    )
    terminal = _COVERAGE_RUNG_PREDICATES[-1][0]
    rows = await session.execute(
        text(
            "WITH "
            + _calibration_population_ctes()
            + ","
            + _coverage_universe_cte(chunk_scoped=False)
            + f"""
            SELECT cu.market_id, fo.name AS outcome_name,
                CASE {branches} ELSE '{terminal}' END AS rung
            FROM coverage_universe cu
            JOIN futures_outcomes fo ON fo.id = cu.outcome_id
            LEFT JOIN market_info mi ON mi.market_id = cu.market_id
            LEFT JOIN normalized n ON n.outcome_id = cu.outcome_id
            LEFT JOIN deduped d ON d.outcome_id = cu.outcome_id
            LEFT JOIN market_result_shape mrs_cov ON mrs_cov.market_id = cu.market_id
            WHERE cu.market_id = ANY(:mids)
            """
        ),
        {"mids": list(ALL_MIDS)},
    )
    rungs = {(r.market_id, r.outcome_name): r.rung for r in rows.all()}
    assert len(rungs) == len(ALL_MIDS) * len(TOPN_BOARD), sorted(rungs)
    wrong = {
        key: rung
        for key, rung in rungs.items()
        if rung != ("golf_round_price_unanchored" if key[0] in WITHHELD_MIDS else "plotted_on_curve")
    }
    assert not wrong, f"rows on the wrong rung: {wrong}"
