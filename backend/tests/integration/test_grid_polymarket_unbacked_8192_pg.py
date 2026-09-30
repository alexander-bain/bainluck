"""#8192's Polymarket champion arm, driven through the real grid on real PostgreSQL.

## what a reader saw

``/playoffs/ncaa-basketball``, Champion column: UConn ``P19``, Illinois ``P15``,
North Carolina ``P11``, VCU ``P8`` under headlines of 1-5%. Seventeen Polymarket
legs summed to 1.58 for one title, while the venue's own column (market
59698973) summed to 2.03 stored.

## why this gate is at the grid

``tests/test_grid_polymarket_unbacked_8192.py`` asserts the predicate. A mutant
that deletes its call site in ``get_playoff_grid`` leaves that file green. The
assertions here are read off the payload the page renders.

## two corpora, because the sum gate is the ship

``broken`` is the specimen: the same legs plus two legs that name teams with no
row on the grid (production has 25 of those), taking the venue column past 1.25.
``sound`` is byte-identical minus those two legs, so the venue column sums to
0.95. The same bidless VCU book is withheld in one and served in the other. A
mutant that drops the sum clause blanks VCU in ``sound``, which is the six
healthy boards' 25-26 honest longshots each, and only the pair can see it.

Books and trades are production's stored rows, read 2026-09-30 ~06:30Z.
"""

import os

import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the #8192 grid Polymarket gate "
        "against real PostgreSQL"
    ),
)

pytestmark.append(needs_postgres)

SPORT_ID = 981920
MARKET_KALSHI = 981920001
MARKET_PM = 981920002
_MARKETS = (MARKET_KALSHI, MARKET_PM)

#: Sentinel: seed NO snapshot row for this leg.
_NO_ROW = object()

#: ``(team, probability, bid, ask, newest last_price, withheld_when_broken)``.
#: last_price ``None`` seeds a snapshot whose ``last_price`` is NULL (the venue
#: reported no trade); ``_NO_ROW`` seeds none at all.
#:
#: 🔴 EVERY NAME IS IN ``NCAA_2026_BRACKET``. The grid drops any other team, and a
#: specimen dropped for that reason would pass every "the mark is gone" check
#: with the rule reverted. ``test_every_corpus_team_reached_the_payload`` holds
#: that shut.
_PM_LEGS = (
    # Withheld: no bid, one 18c offer, never looked up (no snapshot row).
    ("VCU Rams", 0.09, None, 0.18, _NO_ROW, True),
    # Withheld: a 4c bid is under the floor, and the venue reports no trade.
    ("North Carolina Tar Heels", 0.125, 0.04, 0.21, None, True),
    # Withheld: a trade exists, at 74c, and the leg serves 7%.
    ("Alabama Crimson Tide", 0.07, None, 0.14, 0.74, True),
    ("Houston Cougars", 0.115, 0.03, 0.20, None, True),
    # Kept: bid 1c / ask 59c, and a real trade at 22c that it serves.
    ("UConn Huskies", 0.22, 0.01, 0.59, 0.22, False),
    # Kept: buyers at 10c and 8c.
    ("Illinois Fighting Illini", 0.175, 0.10, 0.25, None, False),
    ("Florida Gators", 0.155, 0.08, 0.23, None, False),
)

#: Legs naming teams with no row on the grid. They never reach a cell, and they
#: are what makes the VENUE column (not our subset of it) fail to add up.
_OFF_GRID_LEGS = (
    ("Iowa State Cyclones", 0.32, None, 0.64, None, False),
    ("Creighton Bluejays", 0.35, None, 0.70, None, False),
)

_WITHHELD = {n for n, *_r, w in _PM_LEGS if w}
_KEPT = {n for n, *_r, w in _PM_LEGS if not w}
_ALL = {n for n, *_r in _PM_LEGS}


@pytest.fixture(params=["broken", "sound"])
async def grid(request):
    """Real Postgres, real schema, one corpus; returns ``(corpus, pm_marks)``.

    ``create_all`` only, never ``drop_all``: the database is shared and this gate
    owns nothing but its own id block.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _clear(conn)
        await _seed(conn, with_off_grid=request.param == "broken")
    try:
        yield request.param, await _served(engine)
    finally:
        async with engine.begin() as conn:
            await _clear(conn)
        await engine.dispose()


async def _clear(conn) -> None:
    # Snapshots first: `futures_odds_snapshots.outcome_id` is a foreign key.
    await conn.execute(
        text(
            "DELETE FROM futures_odds_snapshots WHERE outcome_id IN ("
            "SELECT id FROM futures_outcomes WHERE market_id = ANY(:ids))"
        ),
        {"ids": list(_MARKETS)},
    )
    await conn.execute(
        text("DELETE FROM futures_outcomes WHERE market_id = ANY(:ids)"),
        {"ids": list(_MARKETS)},
    )
    await conn.execute(
        text("DELETE FROM futures_markets WHERE id = ANY(:ids)"),
        {"ids": list(_MARKETS)},
    )
    await conn.execute(text("DELETE FROM sports WHERE id = :id"), {"id": SPORT_ID})


async def _seed(conn, *, with_off_grid: bool) -> None:
    """Insert the corpus.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT (``sports.active``,
    ``futures_markets.category`` / ``.mutually_exclusive`` / ``.status``,
    ``futures_odds_snapshots.reading_count``): each carries a client-side
    ``default=`` a raw INSERT never runs. ``tests/test_pg_gate_seed_completeness.py``
    lists this file in ``COVERED``.

    The Kalshi market gives every corpus team a Champion cell of its own, so a
    withheld Polymarket leg means "this row lost its P mark", never "this row
    vanished". ``last_updated`` and ``captured_at`` come from the server so the
    seven-day stale cutoff can never be the reason a leg is absent.
    """
    await conn.execute(
        text("INSERT INTO sports (id, key, name, active) VALUES (:id, :k, :n, true)"),
        {"id": SPORT_ID, "k": f"test_8192_{SPORT_ID}", "n": "Test 8192"},
    )
    for market_id, source, external_id, name in (
        (MARKET_KALSHI, "kalshi", "KXMARMAD-27", "Men's College Basketball Champion"),
        (
            MARKET_PM,
            "polymarket",
            "8192-927445",
            "2027 Men's College Basketball National Champion",
        ),
    ):
        await conn.execute(
            text(
                "INSERT INTO futures_markets (id, source, external_id, name, "
                "category, mutually_exclusive, status, market_tier, "
                "llm_sport_category) VALUES "
                "(:id, :src, :ext, :name, 'championship', true, "
                "'open', 1, 'basketball')"
            ),
            {"id": market_id, "src": source, "ext": external_id, "name": name},
        )

    kalshi_legs = tuple((n, 0.05, 0.04, 0.06, _NO_ROW, False) for n in sorted(_ALL))
    pm_legs = _PM_LEGS + (_OFF_GRID_LEGS if with_off_grid else ())
    for market_id, bookmaker, legs in (
        (MARKET_KALSHI, "kalshi", kalshi_legs),
        (MARKET_PM, "polymarket", pm_legs),
    ):
        for name, prob, bid, ask, last_price, _w in legs:
            outcome_id = (
                await conn.execute(
                    text(
                        "INSERT INTO futures_outcomes (market_id, external_id, name, "
                        "current_probability, current_yes_bid, current_yes_ask, "
                        "is_winner, last_updated) VALUES "
                        "(:mid, :ext, :name, :p, :bid, :ask, false, NOW()) "
                        "RETURNING id"
                    ),
                    {
                        "mid": market_id,
                        "ext": f"{market_id}-{name.replace(' ', '')[:12].upper()}",
                        "name": name,
                        "p": prob,
                        "bid": bid,
                        "ask": ask,
                    },
                )
            ).scalar_one()
            if last_price is _NO_ROW:
                continue
            await conn.execute(
                text(
                    "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, "
                    "probability, yes_bid, yes_ask, last_price, captured_at, "
                    "reading_count) "
                    "VALUES (:oid, :bm, :p, :bid, :ask, :last, NOW(), 1)"
                ),
                {
                    "oid": outcome_id,
                    "bm": bookmaker,
                    "p": prob,
                    "bid": bid,
                    "ask": ask,
                    "last": last_price,
                },
            )


async def _served(engine) -> dict[str, dict[str, float]]:
    """Drive the real route; ``{team: {source: probability}}`` on the Champion column."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.routes.playoffs import get_playoff_grid

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        payload = await get_playoff_grid(
            league_slug="ncaa-basketball", hours=None, top=50, debug=False, db=session
        )

    teams = list(payload.get("teams") or [])
    for group in (payload.get("grouped_teams") or {}).values():
        teams.extend(group)
    out: dict[str, dict[str, float]] = {}
    for team in teams:
        cell = (team.get("cells") or {}).get("championship") or {}
        out[team.get("name") or ""] = {
            s["source"]: float(s["probability"]) for s in cell.get("sources") or []
        }
    return out


def _row(served: dict, wanted: str):
    w = wanted.lower().replace(".", "").replace(" ", "")
    for name, marks in served.items():
        if w in name.lower().replace(".", "").replace(" ", ""):
            return marks
    return None


@needs_postgres
async def test_every_corpus_team_reached_the_payload(grid):
    """🔴 THE ANTI-VACUITY GUARD: each team is on the page with its Kalshi mark,
    so a missing P mark below can only mean the P leg was withheld."""
    _corpus, served = grid
    missing = sorted(n for n in _ALL if not (_row(served, n) or {}).get("kalshi"))
    assert missing == [], f"never reached the Champion column: {missing} ({served})"


@needs_postgres
async def test_the_polymarket_market_reached_the_column(grid):
    """The other half of anti-vacuity: without a P mark on the legs that keep one,
    "the P mark is gone" would pass because the market never matched."""
    _corpus, served = grid
    lost = sorted(n for n in _KEPT if "polymarket" not in (_row(served, n) or {}))
    assert lost == [], (
        f"legs with a buyer or a trade behind them lost their P mark: {lost} "
        f"({served})"
    )


@needs_postgres
async def test_unbacked_legs_follow_the_venue_columns_sum(grid):
    """The ship and its control in one assertion per corpus.

    broken (venue column 1.63): the four legs nothing stands behind lose their
    P mark. sound (0.95): the identical books keep theirs.
    """
    corpus, served = grid
    with_p = {n for n in _WITHHELD if "polymarket" in (_row(served, n) or {})}
    if corpus == "broken":
        assert with_p == set(), (
            f"legs with no buyer and no trade still print a P mark: {sorted(with_p)} "
            f"({served})"
        )
    else:
        assert with_p == _WITHHELD, (
            "a column that adds up lost bidless legs "
            f"{sorted(_WITHHELD - with_p)}: the sum gate did not hold ({served})"
        )


@needs_postgres
async def test_a_trade_that_prints_as_the_price_keeps_the_leg(grid):
    """UConn and Alabama both carry a trade. UConn's prints as its price (22c)
    and it keeps its mark; Alabama's is 74c against 7% and it does not. Asserted
    as a pair so a mutant that ignores the trade, or trusts any trade, is caught."""
    corpus, served = grid
    uconn = "polymarket" in (_row(served, "UConn Huskies") or {})
    alabama = "polymarket" in (_row(served, "Alabama Crimson Tide") or {})
    assert uconn is True, f"UConn's 22c trade did not back its 0.22 ({served})"
    assert alabama is (corpus == "sound"), (
        f"Alabama's 74c trade was read as backing a 7% price ({served})"
    )


@needs_postgres
async def test_the_withheld_row_keeps_its_name_and_headline(grid):
    """Withholding, never deleting (gotcha #21): VCU is still on the page with a
    Champion number, only without the P mark."""
    _corpus, served = grid
    vcu = _row(served, "VCU Rams")
    assert vcu is not None and vcu.get("kalshi") is not None, served
