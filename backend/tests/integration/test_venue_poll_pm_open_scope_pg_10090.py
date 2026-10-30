"""#10090 — the 30-second poll takes what ``POLYMARKET_WS_OPEN_SCOPE=slate``
drops from the socket. Real Postgres.

The poll's Polymarket population is "shown, minus socket". With the open arm
on, "socket" was every market with a persisted token key, because the open arm
streamed all of them. Under ``slate`` the open arm keeps only a slate market's
dependencies, so that rendering would claim markets nobody streams, and they
would wait up to an hour for the hourly refresh. The rendering now follows the
flag: tokened AND the market's own event in the game socket's window.

Fixture 12: a market a reader holds (by the market, or by its event) is in
the population at any distance, linked or not, high-value or not, unless the
game socket carries it; nobody holding it, it is not.

Fixture 8: a market the scope drops (a linked game beyond the window; an
unlinked high-value market; a game in the hand-off band) is in the population
on the next read, and a slate market is not. Fixture 7: such a silent market
is repriced by a real ``poll_venue`` pass, and a venue-settled event is refused,
not written.

Its own variable, like the other real-Postgres gates. Run with a scratch
database: ``VENUE_POLL_SCOPE_DATABASE_URL=postgresql+asyncpg://localhost/<db>``.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("VENUE_POLL_SCOPE_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set VENUE_POLL_SCOPE_DATABASE_URL to run the poll scope contract",
    ),
]

TABLES = (
    "sports",
    "teams",
    "venues",
    "events",
    "futures_markets",
    "futures_outcomes",
    "futures_odds_snapshots",
)


@pytest.fixture
async def maker():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    wanted = [Base.metadata.tables[name] for name in TABLES]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _cid(n: int) -> str:
    return "0x" + f"{n:064x}"


CASES = {
    # case: (hours to kickoff or None for no event, tokened, gamma event id)
    "slate": (1, True, "9001"),
    "far_game": (30, True, "9002"),
    "unlinked": (None, True, "9003"),
    "band": (5.95, True, "9004"),
    "untokened_far": (30, False, "9005"),
}


async def _seed(maker):
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    now = datetime.now(timezone.utc)
    ids = {}
    async with maker() as session:
        sport = Sport(key="baseball_mlb", name="MLB")
        session.add(sport)
        await session.flush()
        for n, (case, (hours, tokened, gamma)) in enumerate(CASES.items(), start=1):
            event_id = None
            if hours is not None:
                event = Event(
                    sport_id=sport.id,
                    home_team_name=f"{case} Home",
                    away_team_name=f"{case} Away",
                    commence_time=now + timedelta(hours=hours),
                    status="scheduled",
                )
                session.add(event)
                await session.flush()
                event_id = event.id
            meta = {"polymarket_event_id": gamma}
            if tokened:
                meta["clob_token_ids"] = [f"{case}-yes", f"{case}-no"]
            market = FuturesMarket(
                source="polymarket",
                external_id=_cid(n),
                name=f"{case} Home vs. {case} Away",
                category="game",
                status="open",
                event_id=event_id,
                volume=50_000,
                resolution_date=now + timedelta(days=2),
                market_metadata=meta,
            )
            session.add(market)
            await session.flush()
            legs = [
                FuturesOutcome(
                    market_id=market.id,
                    external_id=_cid(n),
                    name=f"{case} Home",
                    is_winner=False,
                    current_probability=0.5,
                    last_updated=now - timedelta(hours=2),
                ),
                FuturesOutcome(
                    market_id=market.id,
                    external_id=f"{_cid(n)}_side1",
                    name=f"{case} Away",
                    is_winner=False,
                    current_probability=0.5,
                    last_updated=now - timedelta(hours=2),
                ),
            ]
            session.add_all(legs)
            await session.flush()
            ids[case] = (market.id, [leg.id for leg in legs])
        await session.commit()
    return ids


async def _population(maker, open_arm, scope, held=None, *, held_arm=None):
    """``held_arm`` (``VENUE_POLL_30S_HELD``) defaults to whether a held set is
    given."""
    from sqlalchemy import text

    from app.tasks import venue_poll_30s as v

    if held_arm is None:
        held_arm = held is not None
    async with maker() as session:
        rows = (
            await session.execute(
                text(v.polymarket_population_sql(open_arm, scope, held_arm)),
                v.population_binds([], held),
            )
        ).fetchall()
    return {row[0] for row in rows}


async def _extra_market(maker, n, *, hours, volume):
    """A tokened market; on an event ``hours`` ahead (None: event-less)."""
    from app.models.models import Event, FuturesMarket, Sport
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    async with maker() as session:
        sport_id = (await session.execute(select(Sport.id))).scalars().first()
        event_id = None
        if hours is not None:
            event = Event(
                sport_id=sport_id,
                home_team_name=f"x{n} Home",
                away_team_name=f"x{n} Away",
                commence_time=now + timedelta(hours=hours),
                status="scheduled",
            )
            session.add(event)
            await session.flush()
            event_id = event.id
        market = FuturesMarket(
            source="polymarket",
            external_id=_cid(n),
            name=f"x{n} market",
            category="futures",
            status="open",
            event_id=event_id,
            volume=volume,
            resolution_date=now + timedelta(days=30),
            market_metadata={
                "polymarket_event_id": str(9100 + n),
                "clob_token_ids": [f"x{n}-yes", f"x{n}-no"],
            },
        )
        session.add(market)
        await session.flush()
        from app.models.models import FuturesOutcome

        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=_cid(n),
                name="Yes",
                is_winner=False,
                current_probability=0.5,
            )
        )
        await session.commit()
        return market.id, event_id


async def test_a_held_market_is_in_the_population_at_any_distance(maker):
    """12. Held by market or by event: polled under `slate` (and with the open
    arm off) wherever its event is, unless the game socket carries it."""
    from app.utils.reader_presence import ReaderPresence

    ids = await _seed(maker)
    market = {case: mid for case, (mid, _legs) in ids.items()}
    far_mid, far_event = await _extra_market(maker, 41, hours=200, volume=50_000)
    quiet_mid, _ = await _extra_market(maker, 42, hours=None, volume=10)
    by_event_mid, by_event = await _extra_market(maker, 43, hours=400, volume=10)

    nobody = await _population(maker, True, "slate")
    assert not {far_mid, quiet_mid, by_event_mid} & nobody  # beyond 168 h / low value

    held = ReaderPresence(
        frozenset({far_mid, quiet_mid, market["slate"]}), frozenset({by_event})
    )
    polled = await _population(maker, True, "slate", held)
    assert {far_mid, quiet_mid, by_event_mid} <= polled
    assert market["slate"] not in polled  # the game socket carries it
    assert polled - {far_mid, quiet_mid, by_event_mid} == nobody

    # Open arm off: the same held arm. `all`: the open arm streams every
    # tokened market, so a held tokened market is not polled.
    off = await _population(maker, False, "all", held)
    assert {far_mid, quiet_mid, by_event_mid} <= off
    assert market["slate"] not in off  # held, but the game socket carries it
    assert not {far_mid, quiet_mid, by_event_mid} & await _population(
        maker, True, "all", held
    )
    assert far_event is not None


async def test_the_held_flag_unset_polls_no_held_market(maker):
    """12b (latency R1 on a792d96b). `all`, open arm on: a held, untokened,
    low-value, event-less market is polled only with ``VENUE_POLL_30S_HELD``
    on; unset, the population is exactly the no-reader one, held set or not."""
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.utils.reader_presence import ReaderPresence

    await _seed(maker)
    now = datetime.now(timezone.utc)
    async with maker() as session:
        market = FuturesMarket(
            source="polymarket",
            external_id=_cid(77),
            name="quiet untokened",
            category="futures",
            status="open",
            event_id=None,
            volume=10,
            resolution_date=now + timedelta(days=30),
            market_metadata={"polymarket_event_id": "9177"},
        )
        session.add(market)
        await session.flush()
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=_cid(77),
                name="Yes",
                is_winner=False,
                current_probability=0.5,
            )
        )
        await session.commit()
        mid = market.id
    held = ReaderPresence(frozenset({mid}), frozenset())

    nobody = await _population(maker, True, "all")
    assert mid not in nobody
    assert await _population(maker, True, "all", held, held_arm=False) == nobody
    assert mid in await _population(maker, True, "all", held, held_arm=True)


async def test_the_population_takes_what_the_slate_scope_drops(maker):
    ids = await _seed(maker)
    market = {case: mid for case, (mid, _legs) in ids.items()}

    every_off_window = {
        market[c] for c in ("far_game", "unlinked", "band", "untokened_far")
    }
    # Open arm off: everything the game socket does not hold.
    assert await _population(maker, False, "all") == every_off_window
    # `all`: the open arm streams every tokened market, so only the untokened.
    assert await _population(maker, True, "all") == {market["untokened_far"]}
    # `slate`: what the scope dropped is polled; the slate market is not.
    assert await _population(maker, True, "slate") == every_off_window
    assert market["slate"] not in await _population(maker, True, "slate")


async def test_a_descoped_silent_market_is_repriced_by_a_real_pass(maker, monkeypatch):
    from sqlalchemy import text

    from app.tasks import base as task_base
    from app.tasks import futures_price_refresh as fpr
    from app.tasks import venue_poll_30s as v

    ids = await _seed(maker)
    unlinked_mid, (home, away) = ids["unlinked"]
    _far_mid, (far_home, _far_away) = ids["far_game"]
    _slate_mid, (slate_home, _slate_away) = ids["slate"]

    class _Ctx:
        def __init__(self, **_budget):
            self.session = None

        async def __aenter__(self):
            self.session = maker()
            return await self.session.__aenter__()

        async def __aexit__(self, *exc):
            return await self.session.__aexit__(*exc)

    class _Service:
        async def close(self):
            return None

    asked = []

    async def fetch(_service, event_ids, *, stats=None):
        asked.extend(str(e) for e in event_ids)
        priced = {}
        for event_id in event_ids:
            if str(event_id) == "9003":
                priced["9003"] = [
                    {
                        "external_id": _cid(3),
                        "probability": 0.71,
                        "yes_bid": 0.70,
                        "yes_ask": 0.72,
                        "last_price": 0.71,
                        "no": {
                            "probability": 0.29,
                            "yes_bid": 0.28,
                            "yes_ask": 0.30,
                            "last_price": 0.29,
                        },
                    }
                ]
            elif str(event_id) == "9002":
                priced["9002"] = fpr.VENUE_SETTLED
        return priced, {}

    monkeypatch.setenv("POLYMARKET_WS_OPEN_SCOPE", "slate")
    monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.delenv("VENUE_POLL_30S_PM_SOURCE", raising=False)
    monkeypatch.setattr(task_base, "get_task_session", lambda **kw: _Ctx(**kw))
    monkeypatch.setattr(fpr, "_fetch_polymarket_prices", fetch)
    monkeypatch.setattr(v, "_new_service", lambda _venue: _Service())
    monkeypatch.setattr(v, "shown_market_ids", lambda: [])
    monkeypatch.setattr(v, "held_presence", lambda: None)
    monkeypatch.setattr(v, "backoff_remaining", lambda _venue: 0)
    monkeypatch.setattr(v, "read_cursor", lambda _name: None)
    monkeypatch.setattr(v, "write_cursor", lambda _name, _key: None)
    monkeypatch.setattr(v, "clear_backoff", lambda _venue: None)
    monkeypatch.setattr(v.DeferredPoints, "read", classmethod(lambda cls, ids: cls()))
    monkeypatch.setattr(v.DeferredPoints, "save", lambda self: None)
    v._POPULATION.clear()

    import time

    stats = await v.poll_venue("polymarket", deadline=time.monotonic() + 30)
    v._POPULATION.clear()

    assert not stats["errors"], stats
    assert "9001" not in asked  # the slate market is the socket's
    assert {"9002", "9003"} <= set(asked)
    assert stats.get("refused_settled_events") == 1

    async with maker() as session:
        probs = {
            oid: float(p)
            for oid, p in (
                await session.execute(
                    text(
                        "SELECT id, current_probability FROM futures_outcomes "
                        "WHERE id = ANY(:ids)"
                    ),
                    {"ids": [home, away, far_home, slate_home]},
                )
            ).fetchall()
        }
    assert probs[home] == pytest.approx(0.71)
    assert probs[away] == pytest.approx(0.29)
    assert probs[far_home] == pytest.approx(0.5)  # settled at the venue: refused
    assert probs[slate_home] == pytest.approx(0.5)  # never asked
