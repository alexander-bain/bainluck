"""#8430 — the group-sibling lookup's SQL half, EXECUTED against real PostgreSQL.

`_polymarket_group_sibling_event_id` is a predicate over `futures_markets`, and
every way it can be wrong is invisible to a session double: dropping the
`group_id` equality links a child to ANOTHER Polymarket event's row; dropping
the `group_type` scope lets a linked neg-risk parent container answer for a
game; `DISTINCT … LIMIT 2` + `len != 1` is what refuses a group whose children
disagree; `id != market.id` stops a row finding itself; and the venue-fixture
guard (#4965) is a second query against `events.commence_time`. The unit half,
and the reader-visible specimen (Boyer v Gorzny, 14 rows), live in
`tests/test_polymarket_group_sibling_8430.py`.

Named by its own `search-recall` step in ci.yml, which refuses a skip, a zero
count and a short count — a PG gate nobody names is collected by CI and
executed by nothing. Locally it runs on PostgreSQL 14 only with the one-index
shim for `uq_container_anchor … NULLS NOT DISTINCT`; CI's postgres:15 is
canonical.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import prediction_market_matching as pmm

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

#: The production group, with its real Gamma event id.
GROUP = "polymarket:1067623"
#: A second group whose one linked child sits on a DIFFERENT event.
OTHER_GROUP = "polymarket:8430002"
#: A group whose children disagree about which event they are on.
SPLIT_GROUP = "polymarket:8430003"
#: A group where only the PARENT container is linked.
PARENT_ONLY_GROUP = "polymarket:8430004"
#: A group whose one linked child sits on a row dated far from the venue fixture.
STALE_GROUP = "polymarket:8430005"

VENUE_START = datetime(2026, 9, 24, 17, 0, tzinfo=timezone.utc)
SEEDED_SPORT = "tennis_other_8430"
SEEDED_HOME = "Boyer 8430"
SEEDED_NAME_PREFIX = "8430 probe:"


class _Market:
    """The attributes the lookup and the fixture guard read, and nothing else."""

    def __init__(
        self,
        *,
        id,
        group_id=GROUP,
        source="polymarket",
        group_type="polymarket_sub_market",
        venue_game_start=VENUE_START,
    ):
        self.id = id
        self.name = f"{SEEDED_NAME_PREFIX} Set 1 Winner: Boyer vs Gorzny"
        self.source = source
        self.group_id = group_id
        self.group_type = group_type
        self.external_id = f"0x8430{id}"
        self.market_metadata = (
            {"venue_game_start": venue_game_start.isoformat()}
            if venue_game_start
            else {}
        )


@pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8430 group "
        "sibling lookup gate (CI job `search-recall` provides one)"
    ),
)
@pytest.mark.asyncio
class TestTheLookupOnRealPostgres:
    async def test_a_child_finds_the_row_its_sibling_already_holds(self, seeded):
        session, ids = seeded
        probe = _Market(id=ids["probe_id"])
        assert (
            await pmm._polymarket_group_sibling_event_id(session, probe)
            == ids["event"]
        )

    async def test_a_child_of_another_group_finds_nothing_here(self, seeded):
        """`group_id` is the key: OTHER_GROUP's linked child is on a different
        event, and a probe in a group with no linked child must not find it."""
        session, ids = seeded
        probe = _Market(id=ids["probe_id"], group_id="polymarket:8430999")
        assert await pmm._polymarket_group_sibling_event_id(session, probe) is None

    async def test_two_distinct_events_in_one_group_is_not_guessed(self, seeded):
        session, ids = seeded
        probe = _Market(id=ids["probe_id"], group_id=SPLIT_GROUP)
        assert await pmm._polymarket_group_sibling_event_id(session, probe) is None, (
            "the group's children disagree about their event and the lookup "
            "picked one"
        )

    async def test_a_linked_parent_container_is_not_a_sibling_child(self, seeded):
        session, ids = seeded
        probe = _Market(id=ids["probe_id"], group_id=PARENT_ONLY_GROUP)
        assert await pmm._polymarket_group_sibling_event_id(session, probe) is None

    async def test_a_row_never_finds_itself(self, seeded):
        session, ids = seeded
        own = _Market(id=ids["linked_child"])
        assert await pmm._polymarket_group_sibling_event_id(session, own) is None

    async def test_a_sibling_row_the_fixture_guard_refuses_is_not_linked(
        self, seeded
    ):
        """STALE_GROUP's linked child sits on a row dated a day before the venue
        fixture — the pre-postponement shape 15317735 had. The matched path
        refuses that row (#4965); the sibling path must refuse it too."""
        session, ids = seeded
        probe = _Market(id=ids["probe_id"], group_id=STALE_GROUP)
        assert await pmm._polymarket_group_sibling_event_id(session, probe) is None

    async def test_the_same_stale_row_is_found_when_the_venue_agrees(self, seeded):
        """The control for the refusal above: same group, a venue fixture on the
        stale row's own date — so the guard, not the group, did the refusing."""
        session, ids = seeded
        probe = _Market(
            id=ids["probe_id"],
            group_id=STALE_GROUP,
            venue_game_start=VENUE_START - timedelta(days=1),
        )
        assert (
            await pmm._polymarket_group_sibling_event_id(session, probe)
            == ids["stale_event"]
        )


@pytest.fixture
async def seeded():
    """Real Postgres, torn down by this file's own name prefix and sport key."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Event, FuturesMarket, Sport
    from app.services.database import Base

    def _closure(*roots):
        seen: dict = {}
        pending = list(roots)
        while pending:
            table = pending.pop()
            if table.key in seen:
                continue
            seen[table.key] = table
            for fk in table.foreign_keys:
                pending.append(fk.column.table)
        return list(seen.values())

    engine = create_async_engine(DB_URL)
    like = f"{SEEDED_NAME_PREFIX}%"
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=_closure(
                    Sport.__table__, Event.__table__, FuturesMarket.__table__
                ),
                checkfirst=True,
            )
        )
        await conn.execute(
            text("DELETE FROM futures_markets WHERE name LIKE :n"), {"n": like}
        )
        await conn.execute(
            text("DELETE FROM events WHERE home_team_name = :h"), {"h": SEEDED_HOME}
        )
        await conn.execute(
            text("DELETE FROM sports WHERE key = :k"), {"k": SEEDED_SPORT}
        )

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        sport_id = (
            await session.execute(
                text(
                    "INSERT INTO sports (key, name, active) "
                    "VALUES (:k, :k, TRUE) RETURNING id"
                ),
                {"k": SEEDED_SPORT},
            )
        ).scalar()

        async def _event(start):
            return (
                await session.execute(
                    text(
                        "INSERT INTO events (sport_id, home_team_name, "
                        "away_team_name, commence_time, status) "
                        "VALUES (:sp, :h, 'Gorzny', :s, 'scheduled') RETURNING id"
                    ),
                    {"sp": sport_id, "h": SEEDED_HOME, "s": start},
                )
            ).scalar()

        n = 0

        async def _market(group_id, event_id, group_type="polymarket_sub_market"):
            nonlocal n
            n += 1
            return (
                await session.execute(
                    text(
                        "INSERT INTO futures_markets (source, external_id, name, "
                        "category, mutually_exclusive, group_id, group_type, "
                        "event_id, status, market_metadata) VALUES "
                        "('polymarket', :x, :nm, 'game_prop', TRUE, :g, :gt, "
                        ":e, 'open', CAST(:md AS jsonb)) "
                        "RETURNING id"
                    ),
                    {
                        "x": f"0x8430seed{n}",
                        "nm": f"{SEEDED_NAME_PREFIX} child {n}",
                        "g": group_id,
                        "gt": group_type,
                        "e": event_id,
                        "md": '{"venue_game_start": "%s"}' % VENUE_START.isoformat(),
                    },
                )
            ).scalar()

        event = await _event(VENUE_START)
        other_event = await _event(VENUE_START + timedelta(hours=1))
        stale_event = await _event(VENUE_START - timedelta(days=1))

        linked_child = await _market(GROUP, event)
        await _market(GROUP, None)  # an unlinked sibling must not answer NULL
        await _market(OTHER_GROUP, other_event)
        await _market(SPLIT_GROUP, event)
        await _market(SPLIT_GROUP, other_event)
        await _market(PARENT_ONLY_GROUP, event, group_type="polymarket_event")
        await _market(STALE_GROUP, stale_event)
        await session.commit()

        ids = {
            "event": event,
            "stale_event": stale_event,
            "linked_child": linked_child,
            # An id no seeded row carries, so `id != market.id` is not what
            # decides any probe but the self-probe.
            "probe_id": 2_000_000_000,
        }
        try:
            yield session, ids
        finally:
            await session.rollback()
            await session.execute(
                text("DELETE FROM futures_markets WHERE name LIKE :n"), {"n": like}
            )
            await session.execute(
                text("DELETE FROM events WHERE home_team_name = :h"),
                {"h": SEEDED_HOME},
            )
            await session.execute(
                text("DELETE FROM sports WHERE key = :k"), {"k": SEEDED_SPORT}
            )
            await session.commit()
    await engine.dispose()
