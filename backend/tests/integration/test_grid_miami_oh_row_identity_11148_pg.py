"""#11148 — the unbound ``Miami (OH)`` grid row wore the Hurricanes' identity,
driven through the real route on real PostgreSQL.

## what a reader saw

``/events/14957338`` (Miami v Florida State), 390px, 2026-10-16 ~23:00Z:
Bigger Picture → Season outcomes → Hurricanes **Make Playoff 3%, Champion 1%**,
on a 5-0 team the venues price at ~89% to make the playoff.

``/api/playoffs/ncaa-football`` served TWO rows named "Miami Hurricanes", both
``team_id 15264``: one with Miami (FL)'s legs (Kalshi 0.905 / Polymarket 0.885)
and one with Miami (OH)'s (Kalshi 0.015 / Polymarket 0.05). ``league_context``
keys its rows by name, so the second overwrote the first and the event page
served the RedHawks' prices as the Hurricanes'.

## the mechanism

#7829 keeps ``Miami (OH)`` on its own key and, when no RedHawks row is priced
(the odds_api RedHawks leg carries no price on production), leaves it unbound —
correctly. The ROW it then builds looked its metadata up by the label with the
qualifier stripped: ``Miami (OH)`` → ``miami``, an alias the Hurricanes own. So
the RedHawks' row carried the Hurricanes' crest and ``team_id``, and #11065's
city-label rename (``Miami`` is a whole-word prefix of ``Miami Hurricanes`` once
the qualifier is stripped) printed their name too.

## the corpus — production's shape, 2026-10-16

* teams: Miami Hurricanes ``MIA`` (alternate names ``Miami``, ``Hurricanes``),
  Miami (OH) RedHawks ``M-OH`` (``RedHawks``, ``Miami OH``), and Ohio State as
  a control.
* odds_api championship: the Hurricanes and Ohio State priced; the RedHawks leg
  present with NO price, so no RedHawks-named row exists for ``Miami (OH)`` to
  join.
* Kalshi make_playoffs: ``Miami (FL)`` ``MIA`` 0.905, ``Miami (OH)`` ``MOH``
  0.015; Polymarket make_playoffs: ``Miami (FL)`` 0.885, ``Miami (OH)`` 0.05,
  condition ids (no ticker), exactly as production spells them.
"""

import os

import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the #11148 Miami (OH) row identity "
        "grid gate against real PostgreSQL"
    ),
)

pytestmark.append(needs_postgres)

SPORT_ID = 1114801
MARKET_CHAMP = 1114801001      # odds_api, championship column
MARKET_KALSHI = 1114801002     # kalshi, make_playoffs column
MARKET_POLY = 1114801003       # polymarket, make_playoffs column
_MARKETS = (MARKET_CHAMP, MARKET_KALSHI, MARKET_POLY)
_TEAM_ID_BASE = 1114801100

HURRICANES = _TEAM_ID_BASE + 0
REDHAWKS = _TEAM_ID_BASE + 1
OHIO_STATE = _TEAM_ID_BASE + 2

#: (id, name, abbreviation, alternate_names) — production's values.
TEAMS = (
    (HURRICANES, "Miami Hurricanes", "MIA", '["Miami", "Hurricanes"]'),
    (REDHAWKS, "Miami (OH) RedHawks", "M-OH", '["RedHawks", "Miami OH"]'),
    (OHIO_STATE, "Ohio State Buckeyes", "OSU", None),
)


@pytest.fixture
async def engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    eng = create_async_engine(DB_URL)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _clear(conn)
        await _seed(conn)
    yield eng
    async with eng.begin() as conn:
        await _clear(conn)
    await eng.dispose()


async def _clear(conn) -> None:
    await conn.execute(
        text("DELETE FROM futures_outcomes WHERE market_id = ANY(:ids)"),
        {"ids": list(_MARKETS)},
    )
    await conn.execute(
        text("DELETE FROM futures_markets WHERE id = ANY(:ids)"),
        {"ids": list(_MARKETS)},
    )
    await conn.execute(
        text("DELETE FROM teams WHERE id >= :lo AND id < :hi"),
        {"lo": _TEAM_ID_BASE, "hi": _TEAM_ID_BASE + 100},
    )
    await conn.execute(text("DELETE FROM sports WHERE id = :id"), {"id": SPORT_ID})


async def _seed(conn) -> None:
    """Insert the corpus. Every NOT NULL column is spelled out — a raw INSERT
    does not apply the ORM's client-side defaults (see
    ``tests/test_pg_gate_seed_completeness.py``, which covers this file)."""
    await conn.execute(
        text("INSERT INTO sports (id, key, name, active) VALUES (:id, :k, :n, true)"),
        {"id": SPORT_ID, "k": f"test_11148_{SPORT_ID}", "n": "Test 11148"},
    )
    for team_id, name, abbreviation, alternates in TEAMS:
        await conn.execute(
            text(
                "INSERT INTO teams (id, sport_id, name, abbreviation, alternate_names) "
                "VALUES (:id, :sid, :name, :ab, CAST(:alt AS JSONB))"
            ),
            {"id": team_id, "sid": SPORT_ID, "name": name, "ab": abbreviation,
             "alt": alternates},
        )

    markets = (
        (MARKET_CHAMP, "odds_api", "americanfootball_ncaaf_championship_winner_t11148",
         "NCAAF Championship Winner"),
        (MARKET_KALSHI, "kalshi", "KXCFPMAKE-T11148",
         "Will a team Make the College Football Playoff"),
        (MARKET_POLY, "polymarket", "t11148-poly-make-cfp",
         "Which teams will Make the College Football Playoff"),
    )
    for market_id, source, external_id, name in markets:
        await conn.execute(
            text(
                "INSERT INTO futures_markets (id, source, external_id, name, "
                "category, mutually_exclusive, status, market_tier, "
                "llm_sport_category) VALUES "
                "(:id, :src, :ext, :name, 'championship', false, "
                "'open', 5, 'football')"
            ),
            {"id": market_id, "src": source, "ext": external_id, "name": name},
        )

    async def _leg(market_id, ext, name, p):
        bid = None if p is None else p - 0.005
        ask = None if p is None else p + 0.005
        await conn.execute(
            text(
                "INSERT INTO futures_outcomes (market_id, external_id, name, "
                "current_probability, current_yes_bid, current_yes_ask, "
                "is_winner, last_updated) VALUES "
                "(:mid, :ext, :name, :p, :bid, :ask, false, NOW())"
            ),
            {"mid": market_id, "ext": ext, "name": name, "p": p, "bid": bid, "ask": ask},
        )

    await _leg(MARKET_CHAMP, "Miami Hurricanes", "Miami Hurricanes", 0.0973)
    await _leg(MARKET_CHAMP, "Miami (OH) RedHawks", "Miami (OH) RedHawks", None)
    await _leg(MARKET_CHAMP, "Ohio State Buckeyes", "Ohio State Buckeyes", 0.21)
    await _leg(MARKET_KALSHI, "KXCFPMAKE-T11148-MIA", "Miami (FL)", 0.905)
    await _leg(MARKET_KALSHI, "KXCFPMAKE-T11148-MOH", "Miami (OH)", 0.015)
    await _leg(MARKET_KALSHI, "KXCFPMAKE-T11148-OSU", "Ohio State", 0.83)
    await _leg(MARKET_POLY, "0xt11148fl", "Miami (FL)", 0.885)
    await _leg(MARKET_POLY, "0xt11148oh", "Miami (OH)", 0.05)


async def _grid(engine) -> dict:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.routes.playoffs import get_playoff_grid

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        return await get_playoff_grid(
            league_slug="ncaa-football", hours=None, top=50, debug=False, db=session
        )


def _teams(grid: dict) -> list[dict]:
    teams = list(grid.get("teams") or [])
    if not teams:
        for group in (grid.get("grouped_teams") or {}).values():
            teams.extend(group)
    return teams


def _playoff(team: dict):
    cell = (team.get("cells") or {}).get("make_playoffs") or {}
    p = cell.get("merged_probability")
    return None if p is None else round(float(p), 4)


def _ours(grid: dict) -> list[dict]:
    return [t for t in _teams(grid) if t.get("team_id") in (HURRICANES, REDHAWKS)
            or "miami" in (t.get("name") or "").lower()]


@needs_postgres
async def test_no_two_grid_rows_claim_the_same_team(engine):
    """The served defect: two rows, one ``team_id``. Any consumer that joins a
    row to a team — ``league_context``, the iPhone Championship Path — then
    picks one by dict order."""
    grid = await _grid(engine)
    ids = [t.get("team_id") for t in _teams(grid) if t.get("team_id") is not None]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert dupes == [], (
        f"team_ids served on more than one row: {dupes}; rows: "
        f"{[(t.get('name'), t.get('team_id'), _playoff(t)) for t in _ours(grid)]}"
    )


@needs_postgres
async def test_the_hurricanes_row_is_the_one_carrying_miami_fl_prices(engine):
    grid = await _grid(engine)
    rows = [t for t in _teams(grid) if t.get("team_id") == HURRICANES]
    assert [(t.get("name"), _playoff(t)) for t in rows] == [("Miami Hurricanes", 0.895)], (
        f"rows claiming the Hurricanes: {[(t.get('name'), _playoff(t)) for t in rows]}"
    )


@needs_postgres
async def test_the_miami_oh_row_is_the_redhawks_and_never_named_hurricanes(engine):
    """The row carrying Miami (OH)'s 0.015 / 0.05 is the RedHawks' — by the
    textual identity ``miami (oh)`` → ``miami (oh) redhawks`` — and prints
    their name, not the Hurricanes'."""
    grid = await _grid(engine)
    oh = [t for t in _teams(grid) if _playoff(t) == 0.0325]
    assert len(oh) == 1, [(t.get("name"), t.get("team_id"), _playoff(t)) for t in _ours(grid)]
    row = oh[0]
    assert row.get("team_id") == REDHAWKS, (row.get("name"), row.get("team_id"))
    assert row.get("name") == "Miami (OH) RedHawks", row.get("name")
    assert row.get("short_name") != "MIA", row.get("short_name")


@needs_postgres
async def test_the_control_is_unmoved(engine):
    grid = await _grid(engine)
    osu = [t for t in _teams(grid) if t.get("team_id") == OHIO_STATE]
    assert [(t.get("name"), _playoff(t)) for t in osu] == [("Ohio State Buckeyes", 0.83)]
