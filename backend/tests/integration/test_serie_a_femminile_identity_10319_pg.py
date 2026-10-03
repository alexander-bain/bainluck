"""#10319: the real related-futures queries admit competition, not club names.

PILLARS MATCHING / TRUTH. SHIP: women's Serie A fixtures stop offering men's
season context. These guards exercise the actual handler over PostgreSQL;
mocked SELECT responses cannot prove that refusals precede its candidate cap.
Set SEARCH_TEST_DATABASE_URL to a disposable PostgreSQL database. Each test
creates its own schema and drops only that schema, never existing tables.
Sport seeding/classification have separate owner tests; the Registry guard below
uses the real seed and id-less claim path in this same isolated schema.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set SEARCH_TEST_DATABASE_URL for the real-PG #10319 context guards",
)

WOMEN = "soccer_italy_serie_a_women"
MEN = "soccer_italy_serie_a"
WOMEN_EVENT, MEN_EVENT = 10319001, 10319002
NOW = datetime(2037, 1, 1, tzinfo=timezone.utc)
COMPETITION = {"competition": "Serie A Femminile"}


@pytest.fixture
async def pg_engine():
    """Use real model tables and their FK dependencies in an isolated schema.

    The route has no container-anchor read, so its unrelated PG15-only index
    is outside this schema; the actual route tables work on local PG14 too.
    """
    from app.models import models

    schema = "sol_10319_" + uuid.uuid4().hex
    admin = create_async_engine(DB_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": schema}}
    )
    tables = {
        models.Sport.__table__,
        models.Team.__table__,
        models.Event.__table__,
        models.FuturesMarket.__table__,
        models.FuturesOutcome.__table__,
        models.FuturesOddsSnapshot.__table__,
        models.LineMovementAnalysis.__table__,
    }
    pending = list(tables)
    while pending:
        for fk in pending.pop().foreign_keys:
            target = fk.column.table
            if target not in tables:
                tables.add(target)
                pending.append(target)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync: models.Sport.metadata.create_all(sync, tables=list(tables))
            )
        yield engine
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def _seed_events(engine):
    from app.models.models import Event, Sport

    async with engine.begin() as conn:
        for sid, key, name in [
            (1, WOMEN, "Serie A Femminile - Italy (Women)"),
            (2, MEN, "Serie A - Italy"),
            (3, "soccer", "Soccer"),
            (4, "soccer_other", "Other Soccer"),
            (5, "soccer_england_premier_league", "Premier League"),
        ]:
            await conn.execute(
                insert(Sport),
                {
                    "id": sid,
                    "key": key,
                    "name": name,
                    "group": "Soccer",
                    "active": True,
                },
            )
        for eid, sid in [(WOMEN_EVENT, 1), (MEN_EVENT, 2)]:
            await conn.execute(
                insert(Event),
                {
                    "id": eid,
                    "sport_id": sid,
                    "home_team_name": "Parma",
                    "away_team_name": "Ternana",
                    "commence_time": NOW + timedelta(days=1),
                    "status": "scheduled",
                },
            )


async def _market(
    engine,
    mid,
    *,
    name="Parma Conference Champion",
    sport_id=None,
    metadata=None,
    gender=None,
    tier=2,
    event_id=None,
    outcome="Parma",
):
    from app.models.models import FuturesMarket, FuturesOutcome

    async with engine.begin() as conn:
        await conn.execute(
            insert(FuturesMarket),
            {
                "id": mid,
                "source": "odds_api",
                "external_id": f"10319-{mid}",
                "name": name,
                "category": "conference",
                "mutually_exclusive": True,
                "status": "open",
                "llm_sport_category": "soccer",
                "sport_id": sport_id,
                "market_tier": tier,
                "market_metadata": metadata,
                "llm_gender": gender,
                "event_id": event_id,
                "updated_at": NOW,
            },
        )
        await conn.execute(
            insert(FuturesOutcome),
            {
                "id": mid * 10,
                "market_id": mid,
                "name": outcome,
                "external_id": f"10319-leg-{mid}",
                "current_probability": 0.4,
                "last_updated": NOW,
            },
        )


class _RecordingSession(AsyncSession):
    """Record actual selected candidate rows without replacing their SQL."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.season_rows = []

    async def execute(self, statement, *args, **kwargs):
        result = await super().execute(statement, *args, **kwargs)
        if str(statement).startswith(
            "SELECT futures_markets.id, futures_markets.market_tier"
        ):
            frozen = result.freeze()
            self.season_rows.append([row.id for row in frozen().all()])
            return frozen()
        return result


async def _build(engine, monkeypatch, eid=WOMEN_EVENT, *, debug=True):
    from app.routes.events import _build_related_futures

    monkeypatch.setattr(
        "app.services.league_context.enrich_event_with_context",
        AsyncMock(return_value=None),
    )
    async with _RecordingSession(engine, expire_on_commit=False) as session:
        body, status, ids, cacheable = await _build_related_futures(
            eid, session, debug=debug
        )
        return body, set(ids), session.season_rows, cacheable


def _served_ids(body):
    return {
        row["market_id"]
        for key in ("home_team_futures", "away_team_futures")
        for row in body[key]
    }


@pytest.mark.parametrize(
    "sport_id,metadata,name",
    [
        (1, None, "Parma Conference Champion"),
        (3, COMPETITION, "Parma Conference Champion"),
        (None, COMPETITION, "Parma Conference Champion"),
        (None, None, "Serie A Femminile: Parma Conference Champion"),
        (4, None, "Women's Serie A: Parma Conference Champion"),
    ],
)
async def test_affirmative_competition_context_is_reachable(
    pg_engine,
    monkeypatch,
    sport_id,
    metadata,
    name,
):
    await _seed_events(pg_engine)
    await _market(pg_engine, 500, sport_id=sport_id, metadata=metadata, name=name)
    await _market(
        pg_engine,
        510,
        name="Parma vs Ternana match result",
        tier=5,
        sport_id=1,
        event_id=WOMEN_EVENT,
    )
    body, ids, selected, cacheable = await _build(pg_engine, monkeypatch)
    assert selected == [[500]], selected
    assert ids == {500, 510} and cacheable
    assert 500 in _served_ids(body), body
    assert body["_debug"]["game_prop_count"] == 1


@pytest.mark.parametrize(
    "sport_id,metadata,name,gender",
    [
        (2, None, "Parma Conference Champion", None),
        (3, None, "Parma Conference Champion", None),
        (None, None, "Parma Conference Champion", None),
        (
            None,
            {"product_metadata": {"competition": "Serie A Femminile"}},
            "Parma Conference Champion",
            None,
        ),
        (2, COMPETITION, "Parma Conference Champion", None),
        (5, COMPETITION, "Serie A Femminile: Parma Champion", "women"),
        (
            1,
            {"competition": "Serie A"},
            "Parma Champion",
            "women",
        ),
        (
            1,
            {"competition": "Premier League"},
            "Serie A Femminile: Parma Champion",
            "women",
        ),
        (1, None, "Serie A: Parma Conference Champion", "women"),
        (1, COMPETITION, "Men's Serie A: Parma Conference Champion", "women"),
        (1, COMPETITION, "Parma Conference Champion", "men"),
    ],
)
async def test_unknown_and_conflicting_identity_never_enters_the_season_pool(
    pg_engine,
    monkeypatch,
    sport_id,
    metadata,
    name,
    gender,
):
    await _seed_events(pg_engine)
    await _market(
        pg_engine, 500, sport_id=sport_id, metadata=metadata, name=name, gender=gender
    )
    body, ids, selected, cacheable = await _build(pg_engine, monkeypatch)
    assert selected == [[]], selected
    assert not ids and not cacheable
    assert not _served_ids(body)


async def test_refused_rows_cannot_consume_the_global_or_per_tier_cap(
    pg_engine, monkeypatch
):
    from app.models.models import FuturesMarket

    await _seed_events(pg_engine)
    async with pg_engine.begin() as conn:
        await conn.execute(
            insert(FuturesMarket),
            [
                {
                    "id": mid,
                    "source": "odds_api",
                    "external_id": f"10319-blocker-{mid}",
                    "name": "Parma Conference Champion",
                    "category": "conference",
                    "status": "open",
                    "llm_sport_category": "soccer",
                    "sport_id": 2,
                    "market_tier": 1,
                    "updated_at": NOW,
                }
                for mid in range(1, 402)
            ],
        )
    await _market(pg_engine, 500, sport_id=1, tier=1)
    body, ids, selected, cacheable = await _build(pg_engine, monkeypatch)
    assert selected == [[500]], selected
    assert ids == {500} and cacheable
    assert 500 in _served_ids(body), body


async def test_series_pool_has_the_same_fence_and_game_linked_tier5_survives(
    pg_engine,
    monkeypatch,
):
    await _seed_events(pg_engine)
    await _market(
        pg_engine,
        500,
        name="Parma vs Ternana win series",
        tier=5,
        sport_id=3,
        metadata=COMPETITION,
    )
    await _market(
        pg_engine, 501, name="Parma vs Ternana win series", tier=5, sport_id=2
    )
    await _market(pg_engine, 502, name="Parma vs Ternana win series", tier=5)
    await _market(
        pg_engine,
        503,
        name="Serie A Femminile: Parma vs Ternana win series",
        tier=5,
        sport_id=2,
        metadata=COMPETITION,
    )
    # Linked game membership remains event-id authoritative. No competition
    # marker is invented for this neutral linked question.
    await _market(
        pg_engine,
        510,
        name="Parma vs Ternana match result",
        tier=5,
        sport_id=1,
        event_id=WOMEN_EVENT,
    )
    body, ids, selected, cacheable = await _build(pg_engine, monkeypatch)
    assert ids == {500, 510} and cacheable, (ids, body)
    assert {row["market_id"] for row in body["series_markets"]} == {500}, body
    assert body["_debug"]["game_prop_count"] == 1


async def test_contaminated_cached_ids_trigger_fenced_rediscovery(
    pg_engine, monkeypatch
):
    from app.utils import season_market_discovery

    await _seed_events(pg_engine)
    await _market(pg_engine, 500, sport_id=2)
    await _market(pg_engine, 501, sport_id=3)
    await _market(pg_engine, 502, sport_id=1)
    writes = []
    monkeypatch.setattr(season_market_discovery, "read", lambda *args: [500, 501])
    monkeypatch.setattr(
        season_market_discovery, "write", lambda key, finished, ids: writes.append(ids)
    )
    body, ids, selected, cacheable = await _build(pg_engine, monkeypatch, debug=False)
    assert selected == [[502]], selected
    assert ids == {502} and cacheable
    assert writes == [[502]]
    assert _served_ids(body) == {502}, body


async def test_mens_route_retains_its_existing_predicates_and_payload(
    pg_engine, monkeypatch
):
    from app.utils import serie_a_femminile_context

    await _seed_events(pg_engine)
    await _market(pg_engine, 500, sport_id=2)
    await _market(
        pg_engine, 501, name="Parma vs Ternana win series", tier=5, sport_id=2
    )
    with_guard, ids, _, cacheable = await _build(pg_engine, monkeypatch, MEN_EVENT)
    assert ids == {500, 501} and cacheable
    assert 500 in _served_ids(with_guard)
    assert {row["market_id"] for row in with_guard["series_markets"]} == {501}
    monkeypatch.setattr(
        serie_a_femminile_context, "admission_condition", lambda key: None
    )
    without_guard, baseline_ids, _, baseline_cacheable = await _build(
        pg_engine, monkeypatch, MEN_EVENT
    )
    assert baseline_ids == ids and baseline_cacheable == cacheable
    assert without_guard == with_guard


async def test_registry_resolves_seeded_womens_identity_without_idless_absorption(
    pg_engine, monkeypatch
):
    """Actual seed + Registry; even a second id-less claim creates with provenance.

    Men's identical clubs/clock stay untouched. The first women's create also
    supplies a same-sport name/time candidate for the second claim: separating
    only the men's row would not discriminate id-less absorption within a sport.
    """
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import select

    from app.models.models import Event, Sport
    from app.services import event_registry

    migration = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/serie_a_femminile_sport.py"
    )
    spec = importlib.util.spec_from_file_location(
        "serie_a_registry_seed_10319", migration
    )
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)

    def apply_seed(connection):
        monkeypatch.setattr(
            seed, "op", Operations(MigrationContext.configure(connection))
        )
        seed.upgrade()

    # Registry's process-wide id cache must not carry another test schema's id.
    # Matching and all database resolution remain the real implementation.
    monkeypatch.setattr(event_registry, "_sport_id_cache", {})
    start = NOW + timedelta(days=1)
    async with pg_engine.begin() as conn:
        await conn.run_sync(apply_seed)
        seeded = (
            await conn.execute(
                select(Sport.id, Sport.key, Sport.name).where(Sport.key == WOMEN)
            )
        ).one()
        await conn.execute(
            insert(Sport),
            {
                "id": 100,
                "key": MEN,
                "name": "Serie A - Italy",
                "group": "Soccer",
                "active": True,
            },
        )
        await conn.execute(
            insert(Event),
            {
                "id": MEN_EVENT,
                "sport_id": 100,
                "home_team_name": "Parma",
                "away_team_name": "Ternana",
                "commence_time": start,
                "status": "scheduled",
            },
        )
        mens_before = dict(
            (await conn.execute(select(Event.__table__).where(Event.id == MEN_EVENT)))
            .mappings()
            .one()
        )

    identity = event_registry.EventIdentity(
        sport_key=WOMEN,
        home_team_name="Parma",
        away_team_name="Ternana",
        commence_time=start,
        claim=event_registry.EventClaim(
            source="kalshi",
            source_id=None,
            schedule_derived=False,
        ),
    )
    async with AsyncSession(pg_engine, expire_on_commit=False) as session:
        first, first_created = await event_registry.find_or_create_event(
            session, identity
        )
        first_id = first.id
        await session.commit()
        second, second_created = await event_registry.find_or_create_event(
            session, identity
        )
        second_id = second.id
        await session.commit()

    assert first_created and second_created
    assert len({MEN_EVENT, first_id, second_id}) == 3
    assert seeded.key == WOMEN
    assert seeded.name == "Serie A Femminile - Italy (Women)"
    async with AsyncSession(pg_engine) as session:
        rows = (
            await session.execute(
                select(Event, Sport.key, Sport.name)
                .join(Sport, Event.sport_id == Sport.id)
                .where(Event.id.in_([first_id, second_id]))
            )
        ).all()
        assert len(rows) == 2
        for event, key, name in rows:
            assert event.sport_id == seeded.id
            assert (key, name) == (WOMEN, "Serie A Femminile - Italy (Women)")
            assert (event.home_team_name, event.away_team_name) == ("Parma", "Ternana")
            assert event.commence_time == start and event.status == "scheduled"
            assert set(event.event_tags) == {
                "provenance:source:kalshi",
                "provenance:unanchored",
            }
            assert event.external_id is None and event.espn_id is None
        mens_after = dict(
            (
                await session.execute(
                    select(Event.__table__).where(Event.id == MEN_EVENT)
                )
            )
            .mappings()
            .one()
        )
        assert mens_after == mens_before
