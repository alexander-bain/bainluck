"""#9653 — the discovery producer's ONE statement, on a real server.

SHIP: readers find the correct published NFL-week/MLB-playoff hub from
Search/Browse/Discover (#9653). Pillar: MATCHING / DISCOVER.

WHY THIS NEEDS A REAL DATABASE. The unit file grades the pure check against a
session double, and a double agrees with whatever statement the code built.
What only a server can say: that the eligibility filters in the SQL actually
exclude (so an ineligible row cannot consume the LIMIT), that a member whose
row is gone is not counted, that a withdrawn draw's members do not count, that
the matched-games aggregate and its ordering are what the docstring claims,
and that asyncpg binds the array parameters at all.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.services import container_discovery as discovery

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "needs a real PostgreSQL: set SEARCH_TEST_DATABASE_URL (the "
        "search-recall CI job does)"
    ),
)


@pytest.fixture
async def pg_session(monkeypatch):
    """Real Postgres, real schema, #9651's migration applied from its own DDL."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base
    from app.utils.container_corrections import UPGRADE_STATEMENTS

    monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        # The ledger references `containers`, so it goes first (as in the
        # assembly gate) or `drop_all` wedges on a crashed run's leftovers.
        await conn.execute(text("DROP TABLE IF EXISTS container_corrections"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        for statement in UPGRADE_STATEMENTS:
            await conn.execute(text(statement))

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS container_corrections"))
    await engine.dispose()


async def _seed(session):
    """A small world with one collection of every eligibility shape.

    Returns ``{name: id}`` for containers and ``{name: id}`` for events.
    """
    from app.models.models import Container, Event, EventEdge, FuturesMarket, Sport

    nfl = Sport(key="americanfootball_nfl", name="NFL", active=True)
    mlb = Sport(key="baseball_mlb", name="MLB", active=True)
    session.add_all([nfl, mlb])
    await session.flush()

    start = datetime(2026, 10, 4, 17, 0, tzinfo=timezone.utc)
    events = {}
    for name, sport in (
        ("wk5_a", nfl), ("wk5_b", nfl), ("wk6_a", nfl), ("wk4_a", nfl),
        ("unpub", nfl), ("withdrawn", nfl), ("wrong", nfl), ("nested", nfl),
        ("mlb_a", mlb), ("gone", nfl), ("draw_only", nfl),
    ):
        ev = Event(
            sport_id=sport.id,
            home_team_name=f"Home {name}",
            away_team_name=f"Away {name}",
            commence_time=start,
            status="scheduled",
        )
        session.add(ev)
        events[name] = ev
    await session.flush()

    market = FuturesMarket(
        source="kalshi", external_id="KXNFLGAME-9653", sport_id=nfl.id,
        name="Week 5 question", category="sports", status="open",
        commence_time=start, event_id=events["wk5_a"].id,
    )
    session.add(market)
    await session.flush()

    def container(slug, name, window_days, parent=None):
        return Container(
            kind="season", name=name, slug=slug, status="scheduled",
            window_start=start + timedelta(days=window_days),
            window_end=start + timedelta(days=window_days + 7),
            parent_container_id=parent,
        )

    hubs = {
        "wk5": container("nfl-2026-week-5", "NFL 2026 · Week 5", 0),
        "wk6": container("nfl-2026-week-6", "NFL 2026 · Week 6", 7),
        "wk4_empty": container("nfl-2026-week-4", "NFL 2026 · Week 4", -7),
        "unpub": container("nfl-2026-week-7", "NFL 2026 · Week 7", 14),
        "withdrawn": container("nfl-2026-week-8", "NFL 2026 · Week 8", 21),
        "wrong": container("nfl-2026-week-09", "wrong edition", 28),
        "season": container("nfl-2026", "NFL 2026", -30),
        "mlb": container("mlb-2026-postseason", "MLB 2026 · Postseason", 2),
        "mlb_2025": container("mlb-2025-postseason", "MLB 2025 · Postseason", -360),
        "gone_only": container("nfl-2026-week-10", "NFL 2026 · Week 10", 35),
    }
    session.add_all(hubs.values())
    await session.flush()
    # A published nested draw under week 5, and a withdrawn one under week 6.
    hubs["nested"] = container("nfl-2026-week-11", "nested", 0, parent=hubs["wk5"].id)
    hubs["wk6_draw"] = container("nfl-2026-week-12", "withdrawn draw", 7, parent=hubs["wk6"].id)
    session.add_all([hubs["nested"], hubs["wk6_draw"]])
    await session.flush()

    def edge(hub, child_type, child_id):
        return EventEdge(
            parent_type="container", parent_id=hubs[hub].id,
            child_type=child_type, child_id=child_id, kind="contains",
            edge_class="match_winner", source="register", confidence=1,
        )

    session.add_all([
        edge("wk5", "event", events["wk5_a"].id),
        edge("wk5", "event", events["wk5_b"].id),
        edge("wk5", "market", market.id),
        edge("nested", "event", events["nested"].id),
        edge("wk6", "event", events["wk6_a"].id),
        edge("wk6_draw", "event", events["draw_only"].id),
        edge("unpub", "event", events["unpub"].id),
        edge("withdrawn", "event", events["withdrawn"].id),
        edge("wrong", "event", events["wrong"].id),
        edge("season", "event", events["wk5_a"].id),
        edge("mlb", "event", events["mlb_a"].id),
        edge("mlb_2025", "event", events["mlb_a"].id),
        edge("gone_only", "event", events["gone"].id),
    ])
    await session.flush()

    states = {
        "wk5": ("published", 4), "wk6": ("published", 2), "wk4_empty": ("published", 1),
        "unpub": ("unpublished", 0), "withdrawn": ("withdrawn", 3), "wrong": ("published", 1),
        "season": ("published", 1), "mlb": ("published", 5), "mlb_2025": ("published", 9),
        "gone_only": ("published", 1), "nested": ("published", 1), "wk6_draw": ("withdrawn", 1),
    }
    for key, (state, rev) in states.items():
        await session.execute(
            text(
                "UPDATE containers SET publication_state = :s, membership_revision = :r "
                "WHERE id = :id"
            ),
            {"s": state, "r": rev, "id": hubs[key].id},
        )
    # A member whose row is gone: the edge stays, the event does not.
    gone_id = events["gone"].id
    await session.execute(text("DELETE FROM events WHERE id = :id"), {"id": gone_id})
    await session.commit()
    return {k: v.id for k, v in hubs.items()}, {k: v.id for k, v in events.items()}


class _Counting:
    """Counts statements on a real session without changing what runs."""

    def __init__(self, session):
        self._session = session
        self.count = 0

    async def execute(self, *args, **kwargs):
        self.count += 1
        return await self._session.execute(*args, **kwargs)


class TestOnlyEligibleCollections:
    async def test_browse_all_offers_exactly_the_eligible_roots(self, pg_session):
        hubs, _ = await _seed(pg_session)
        read = await discovery.discover_collections(pg_session)
        assert read.excluded == {}, "the SQL let an ineligible row through"
        # Most recent window first. Refused: empty, unpublished, withdrawn,
        # wrong-edition, season, nested, and the hub whose only member is gone.
        assert [c["id"] for c in read.collections] == [
            hubs["wk6"], hubs["mlb"], hubs["wk5"], hubs["mlb_2025"],
        ]

    async def test_counts_are_rows_we_hold_and_a_withdrawn_draw_adds_nothing(self, pg_session):
        hubs, _ = await _seed(pg_session)
        cards = {c["id"]: c for c in (await discovery.discover_collections(pg_session)).collections}
        # Week 5: two games + one question of its own, one game in its
        # published draw.
        assert (cards[hubs["wk5"]]["game_count"], cards[hubs["wk5"]]["question_count"]) == (3, 1)
        # Week 6: its withdrawn draw's game is not counted.
        assert cards[hubs["wk6"]]["game_count"] == 1
        assert cards[hubs["wk5"]]["revision"] == 4


class TestRelevance:
    async def test_given_games_only_hubs_holding_them_come_back_most_matched_first(self, pg_session):
        hubs, ev = await _seed(pg_session)
        read = await discovery.discover_collections(
            pg_session, event_ids=[ev["wk5_a"], ev["wk5_b"], ev["wk6_a"], ev["unpub"], ev["wrong"]]
        )
        assert [c["id"] for c in read.collections] == [hubs["wk5"], hubs["wk6"]]
        assert read.collections[0]["matched_event_ids"] == sorted([ev["wk5_a"], ev["wk5_b"]])
        assert read.collections[1]["matched_event_ids"] == [ev["wk6_a"]]

    async def test_a_game_in_a_published_draw_finds_the_root(self, pg_session):
        hubs, ev = await _seed(pg_session)
        read = await discovery.discover_collections(pg_session, event_ids=[ev["nested"]])
        assert [c["id"] for c in read.collections] == [hubs["wk5"]]

    async def test_a_game_only_in_a_withdrawn_draw_finds_nothing(self, pg_session):
        _, ev = await _seed(pg_session)
        read = await discovery.discover_collections(pg_session, event_ids=[ev["draw_only"]])
        assert read.collections == []

    async def test_a_deleted_game_matches_nothing(self, pg_session):
        _, ev = await _seed(pg_session)
        read = await discovery.discover_collections(pg_session, event_ids=[ev["gone"]])
        assert read.collections == []


class TestFilters:
    async def test_league_and_season(self, pg_session):
        hubs, _ = await _seed(pg_session)
        mlb = await discovery.discover_collections(pg_session, league="mlb")
        assert [c["id"] for c in mlb.collections] == [hubs["mlb"], hubs["mlb_2025"]]
        mlb_2026 = await discovery.discover_collections(pg_session, league="mlb", season=2026)
        assert [c["id"] for c in mlb_2026.collections] == [hubs["mlb"]]
        assert mlb_2026.excluded == {}

    async def test_slugs_exact(self, pg_session):
        hubs, _ = await _seed(pg_session)
        read = await discovery.discover_collections(
            pg_session, slugs=["nfl-2026-week-5", "nfl-2026-week-7", "nfl-2026"]
        )
        assert [c["id"] for c in read.collections] == [hubs["wk5"]]

    async def test_the_limit_is_spent_on_eligible_rows_only(self, pg_session):
        hubs, _ = await _seed(pg_session)
        read = await discovery.discover_collections(pg_session, limit=1)
        assert [c["id"] for c in read.collections] == [hubs["wk6"]]


class TestBounded:
    async def test_two_statements_on_a_real_server(self, pg_session):
        _, ev = await _seed(pg_session)
        counting = _Counting(pg_session)
        await discovery.discover_collections(counting, event_ids=list(ev.values()))
        assert counting.count == 2
