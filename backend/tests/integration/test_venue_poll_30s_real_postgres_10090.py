"""#10090 — the 30-second venue poll's population and write, against real Postgres.

Two contracts no mock can observe:

* WHO is polled — the population SQL renders the sockets' own predicates
  (`kalshi_ws._kalshi_slate_event_window`, `polymarket_ws._slate_event_window`,
  `kalshi_open_contract_stmt`) and the hand-off band, so only a real planner
  running the real text says which rows it admits.
* WHAT is written — `_write_prices` with a `PollWrite`: a changed leg moves and
  gains a point, an unchanged one writes nothing, a row a newer writer touched is
  left alone with no point, a move inside the history interval moves the row and
  gains its point on a later pass, and a settled leg is never written.

Opt-in on `SEARCH_TEST_DATABASE_URL` like `test_futures_price_refresh_writes_pg.py`
(CI job: search-recall).
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
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres 30-second venue "
            "poll gate (CI job: search-recall)"
        ),
    ),
]


@pytest.fixture
async def db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401
    from app.services.database import Base

    # Only the tables this gate touches, with their foreign-key closure: the
    # whole schema carries indexes a local PG14 cannot build, and nothing here
    # reads them.
    wanted = {"sports", "events", "futures_markets", "futures_outcomes", "futures_odds_snapshots"}
    tables, frontier = set(), set(wanted)
    while frontier:
        name = frontier.pop()
        tables.add(name)
        for fk in Base.metadata.tables[name].foreign_keys:
            if fk.column.table.name not in tables:
                frontier.add(fk.column.table.name)
    subset = [t for t in Base.metadata.sorted_tables if t.name in tables]

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=subset))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=subset))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


_NOW = datetime.now(timezone.utc)


async def _event(session, *, status="scheduled", starts_in=timedelta(days=2)):
    from app.models.models import Event, Sport

    sport = (
        await session.execute(text("SELECT id FROM sports WHERE key = 'nfl_test'"))
    ).scalar()
    if sport is None:
        row = Sport(key="nfl_test", name="NFL", group="American Football")
        session.add(row)
        await session.flush()
        sport = row.id
    event = Event(
        sport_id=sport,
        home_team_name="Home",
        away_team_name="Away",
        commence_time=_NOW + starts_in,
        status=status,
    )
    session.add(event)
    await session.flush()
    return event.id


async def _market(
    session,
    *,
    source,
    ext,
    legs,
    event_id=None,
    tier=1,
    metadata=None,
    status="open",
):
    """``legs``: [(external_id, is_winner, resolution_source)]."""
    from app.models.models import FuturesMarket, FuturesOutcome

    market = FuturesMarket(
        source=source,
        external_id=ext,
        name=f"{ext} market",
        category="futures",
        market_tier=tier,
        status=status,
        event_id=event_id,
        resolution_date=_NOW + timedelta(days=30),
        market_metadata=metadata or {},
    )
    session.add(market)
    await session.flush()
    ids = {}
    for leg_ext, is_winner, source_of_grade in legs:
        outcome = FuturesOutcome(
            market_id=market.id,
            external_id=leg_ext,
            name=leg_ext,
            is_winner=is_winner,
            resolution_source=source_of_grade,
            current_probability=0.40,
            current_yes_bid=0.39,
            current_yes_ask=0.41,
        )
        session.add(outcome)
        await session.flush()
        if is_winner is None:
            # The column's server default is FALSE, so the ORM's None does not
            # reach the row; the open arm's NULL leg is written as a raw
            # INSERT writes it.
            await session.execute(
                text("UPDATE futures_outcomes SET is_winner = NULL WHERE id = :o"),
                {"o": outcome.id},
            )
        ids[leg_ext] = outcome.id
    return market.id, ids


async def _population(session, venue, *, open_arm):
    from app.tasks import venue_poll_30s as v

    sql = v.kalshi_population_sql(open_arm) if venue == "kalshi" else v.polymarket_population_sql(open_arm)
    rows = (
        await session.execute(
            text(sql),
            v.population_binds([]),
        )
    ).fetchall()
    return {row[-1] for row in rows}


async def test_kalshi_population_is_shown_minus_both_socket_arms(db):
    await _market(
        db, source="kalshi", ext="KXFUT-1",
        legs=[("KXFUT-1-A", False, None), ("KXFUT-1-B", None, None),
              ("KXFUT-1-C", True, "api_settlement"), ("KXFUT-1-D", False, "api_settlement")],
    )
    await _market(db, source="kalshi", ext="KXLOW-1", tier=4, legs=[("KXLOW-1-A", False, None)])
    in_window = await _event(db, starts_in=timedelta(hours=2))
    in_band = await _event(db, starts_in=timedelta(hours=5, minutes=55))
    far = await _event(db, starts_in=timedelta(hours=30))
    live = await _event(db, status="live", starts_in=timedelta(hours=-1))
    for eid, tag in ((in_window, "WIN"), (in_band, "BAND"), (far, "FAR"), (live, "LIVE")):
        await _market(db, source="kalshi", ext=f"KXGAME-{tag}", event_id=eid, tier=5,
                      legs=[(f"KXGAME-{tag}-H", False, None)])
    await db.commit()

    polled = await _population(db, "kalshi", open_arm=True)
    # The open arm streams the NULL leg; settled legs and low-value unlinked
    # markets are not polled; the game socket keeps its window but not the band.
    assert polled == {"KXFUT-1-A", "KXGAME-BAND-H", "KXGAME-FAR-H"}

    polled_arm_off = await _population(db, "kalshi", open_arm=False)
    assert "KXFUT-1-B" in polled_arm_off
    assert "KXGAME-WIN-H" not in polled_arm_off and "KXGAME-LIVE-H" not in polled_arm_off


async def test_polymarket_population_drops_tokened_markets_only_while_the_open_arm_is_on(db):
    await _market(db, source="polymarket", ext="9001", legs=[("0xaaa", False, None)],
                  metadata={"polymarket_event_id": "9001"})
    await _market(db, source="polymarket", ext="9002", legs=[("0xbbb", False, None)],
                  metadata={"polymarket_event_id": "9002", "clob_token_ids": '["1","2"]'})
    await _market(db, source="polymarket", ext="9003", status="resolved",
                  legs=[("0xccc", False, None)], metadata={"polymarket_event_id": "9003"})
    await db.commit()

    assert await _population(db, "polymarket", open_arm=True) == {"0xaaa"}
    assert await _population(db, "polymarket", open_arm=False) == {"0xaaa", "0xbbb"}


async def _poll(db, outcome_ids, *, fetched_at=None):
    from app.tasks.venue_poll_30s import PollWrite, load_state

    stored, last_point = await load_state(db, list(outcome_ids))
    return PollWrite(
        fetched_at=fetched_at or datetime.now(timezone.utc),
        now=datetime.now(timezone.utc),
        stored=stored,
        last_point=last_point,
        allowed=frozenset(outcome_ids),
    )


async def _row(db, outcome_id):
    return (
        await db.execute(
            text("SELECT current_probability, (SELECT count(*) FROM futures_odds_snapshots "
                 "WHERE outcome_id = :o) FROM futures_outcomes WHERE id = :o"),
            {"o": outcome_id},
        )
    ).one()


def _item(ext, prob, bid, ask):
    return {"external_id": ext, "probability": prob, "yes_bid": bid, "yes_ask": ask,
            "last_price": prob}


async def test_a_changed_leg_moves_and_gains_a_point_an_unchanged_one_writes_nothing(db):
    from app.tasks.venue_poll_30s import write_market

    mid, ids = await _market(db, source="kalshi", ext="KXW",
                             legs=[("KXW-A", False, None), ("KXW-B", False, None)])
    await db.commit()
    stats = {"unknown_outcomes": 0}
    poll = await _poll(db, ids.values(), fetched_at=datetime.now(timezone.utc) + timedelta(seconds=5))
    await write_market(db, venue="kalshi", market_id=mid, poll=poll, stats=stats,
                       priced=[_item("KXW-A", 0.55, 0.54, 0.56), _item("KXW-B", 0.40, 0.39, 0.41)])
    assert float((await _row(db, ids["KXW-A"]))[0]) == pytest.approx(0.55)
    assert (await _row(db, ids["KXW-A"]))[1] == 1
    assert (await _row(db, ids["KXW-B"]))[1] == 0
    assert stats["rows_updated"] == 1 and stats["legs_unchanged"] == 1


async def test_a_row_a_newer_writer_touched_is_left_alone_with_no_point(db):
    from app.tasks.venue_poll_30s import write_market

    mid, ids = await _market(db, source="kalshi", ext="KXN", legs=[("KXN-A", False, None)])
    await db.commit()
    stats = {"unknown_outcomes": 0}
    # The venue read was sent an hour ago; the row was written since.
    poll = await _poll(db, ids.values(), fetched_at=datetime.now(timezone.utc) - timedelta(hours=1))
    await write_market(db, venue="kalshi", market_id=mid, poll=poll, stats=stats,
                       priced=[_item("KXN-A", 0.70, 0.69, 0.71)])
    prob, points = await _row(db, ids["KXN-A"])
    assert float(prob) == pytest.approx(0.40) and points == 0
    assert stats["legs_newer_writer"] == 1


async def test_a_move_inside_the_interval_moves_the_row_and_gains_its_point_later(db):
    from app.tasks.venue_poll_30s import HISTORY_MIN_INTERVAL_S, write_market

    mid, ids = await _market(db, source="kalshi", ext="KXH", legs=[("KXH-A", False, None)])
    oid = ids["KXH-A"]
    await db.execute(
        text("INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, probability, captured_at, "
             "reading_count) VALUES (:o, 'kalshi', 0.40, :t, 1)"),
        {"o": oid, "t": datetime.now(timezone.utc) - timedelta(seconds=10)},
    )
    await db.commit()
    future = datetime.now(timezone.utc) + timedelta(seconds=5)
    stats = {"unknown_outcomes": 0}
    poll = await _poll(db, [oid], fetched_at=future)
    await write_market(db, venue="kalshi", market_id=mid, poll=poll, stats=stats,
                       priced=[_item("KXH-A", 0.41, 0.40, 0.42)])
    prob, points = await _row(db, oid)
    assert float(prob) == pytest.approx(0.41) and points == 1  # row moved, no new point
    assert stats["history_deferred"] == 1

    # The next pass after the interval reads the same price: a trailing point.
    later = await _poll(db, [oid], fetched_at=future + timedelta(seconds=5))
    later.now = later.now + timedelta(seconds=HISTORY_MIN_INTERVAL_S + 1)
    await write_market(db, venue="kalshi", market_id=mid, poll=later, stats=stats,
                       priced=[_item("KXH-A", 0.41, 0.40, 0.42)])
    assert (await _row(db, oid))[1] == 2
    assert stats["history_trailing_points"] == 1


async def test_a_settled_leg_is_never_written(db):
    from app.tasks.venue_poll_30s import write_market

    mid, ids = await _market(db, source="kalshi", ext="KXS",
                             legs=[("KXS-A", True, "api_settlement"), ("KXS-B", False, "api_settlement")])
    await db.commit()
    stats = {"unknown_outcomes": 0}
    poll = await _poll(db, ids.values(), fetched_at=datetime.now(timezone.utc) + timedelta(seconds=5))
    await write_market(db, venue="kalshi", market_id=mid, poll=poll, stats=stats,
                       priced=[_item("KXS-A", 0.55, 0.54, 0.56), _item("KXS-B", 0.55, 0.54, 0.56)])
    for oid in ids.values():
        prob, points = await _row(db, oid)
        assert float(prob) == pytest.approx(0.40) and points == 0
    assert stats["unknown_outcomes"] == 2
