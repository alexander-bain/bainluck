"""SGA reaches actual destinations through real PostgreSQL and ASGI routes.

Uses the existing opt-in search-recall database, never production. Frozen small
inventory proves SQL semantics, not production-scale latency or phone acceptance.
"""

from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select

from app.config import person_aliases
from app.dependencies.auth import get_optional_user
from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport, Team
from app.routes import events, futures
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_search_grid_parity_11616 import _rows
from tests.integration.test_search_recall_contract import DB_URL
from tests.integration.test_search_recall_contract import seeded_db as seeded_db
from tests.test_search_detail_parity_11616 import FixedDatetime, STAMP
from tests.test_typeahead_retains_complete_answer_10225 import FakeRedis

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="set SEARCH_TEST_DATABASE_URL for real PG recall"
    ),
]

NAME = "Shai Gilgeous-Alexander"


@pytest.fixture
async def inventory(seeded_db, monkeypatch):
    engine, maker = seeded_db
    monkeypatch.setattr(events, "datetime", FixedDatetime)
    monkeypatch.setattr(futures, "datetime", FixedDatetime)
    monkeypatch.setattr(events, "_roster_index", {})
    monkeypatch.setattr(events, "_roster_index_expires_at", 0.0)
    monkeypatch.setattr(events, "_record_search_query", MagicMock())
    monkeypatch.setattr(events, "_record_trending", MagicMock())
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    cache = FakeRedis()
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **kw: cache
    )
    async with maker() as session:
        nba = (
            await session.execute(select(Sport).where(Sport.key == "basketball_nba"))
        ).scalar_one()
        team = Team(
            sport_id=nba.id,
            name="Oklahoma City Thunder",
            abbreviation="OKC",
            roster_players=[{"name": NAME, "espn_id": "4278073"}],
        )
        session.add(team)
        await session.flush()
        game = Event(
            sport_id=nba.id,
            home_team_id=team.id,
            home_team_name=team.name,
            away_team_name="Boston Celtics",
            commence_time=STAMP + timedelta(days=2),
            status="scheduled",
        )
        session.add(game)
        boards = []
        specs = [
            (
                "NBA MVP Winner 2027",
                [
                    "Victor Wembanyama",
                    "Nikola Jokic",
                    "Luka Doncic",
                    "Anthony Edwards",
                    "Jalen Brunson",
                    NAME,
                ],
            ),
            ("SGA regulatory decision", ["Yes", "No"]),
            ("Will Katie Zacharia become governor?", ["Yes", "No"]),
            # Archived Zacharia control reaches Branch through an outcome,
            # not an invented prefix-match title on the full-search name rail.
            (
                "Offensive Rookie of the Year Winner?",
                ["Zachariah Branch", "Carnell Tate"],
            ),
        ]
        for index, (title, names) in enumerate(specs):
            board = FuturesMarket(
                source="kalshi",
                external_id=f"alias-11617-{index}",
                name=title,
                status="open",
                mutually_exclusive=True,
                llm_sport_category="basketball" if index == 0 else "politics",
                market_tier=3,
                volume=900_000,
                updated_at=STAMP,
                resolution_date=STAMP + timedelta(days=90),
                outcomes=[],
                sport=None,
            )
            session.add(board)
            await session.flush()
            board.outcomes = [
                FuturesOutcome(
                    market_id=board.id,
                    external_id=f"alias-{index}-{i}",
                    name=name,
                    current_probability=p,
                    current_yes_bid=max(0, p - 0.01),
                    current_yes_ask=min(1, p + 0.01),
                    last_updated=STAMP,
                )
                for i, (name, p) in enumerate(
                    zip(names, [0.31, 0.26, 0.20, 0.18, 0.15, 0.10])
                )
            ]
            boards.append(board)
        await session.commit()
        ids = {
            "team": team.id,
            "event": game.id,
            "market": boards[0].id,
            "shai": boards[0].outcomes[-1].id,
        }
        expected = futures._format_market_detail(boards[0])

    from app.main import app

    async def db():
        async with maker() as session:
            yield session

    statements = []

    def count_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", count_sql)
    saved = app.dependency_overrides.copy()
    app.dependency_overrides.update(
        {get_db: db, get_db_rw: db, get_optional_user: lambda: None}
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def request(endpoint, query="SGA", **params):
                response = await client.get(
                    f"/api/events/{endpoint}", params={"q": query, **params}
                )
                assert response.status_code == 200, response.text
                return response.json()

            yield request, ids, expected, cache, statements, maker
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_sql)
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)


@pytest.mark.parametrize("endpoint", ["search", "typeahead"])
async def test_alias_reaches_roster_game_and_market_without_repricing(
    inventory, endpoint
):
    request, ids, expected, cache, statements, _ = inventory
    body = await request(endpoint)
    assert body["query"] == "SGA"
    selected = list(_rows(body, ids["market"]))
    assert selected, body
    detail = {o["name"]: o for o in expected["outcomes"]}
    for rows in selected:
        shai = next(o for o in rows if o["name"] == NAME)
        assert shai["probability"] == detail[NAME]["probability"]
        assert shai["rendered_percent"] == detail[NAME]["rendered_percent"]
    if endpoint == "search":
        assert any(t["id"] == ids["team"] for t in body["teams"])
        assert any(g["id"] == ids["event"] for g in body["results"])
    else:
        assert any(
            s["type"] == "team" and s["team_id"] == ids["team"]
            for s in body["suggestions"]
        )
        assert any(
            s["type"] == "event" and s["event_id"] == ids["event"]
            for s in body["suggestions"]
        )
    count = len(statements)
    cached_bytes = dict(cache.store)
    cached_expiry = dict(cache.expires_at)
    assert await request(endpoint) == body
    assert len(statements) == count, "warm alias must not execute SQL"
    assert cache.store == cached_bytes and cache.expires_at == cached_expiry
    canonical = await request(endpoint, NAME)
    assert list(_rows(canonical, ids["market"])) == selected


@pytest.mark.parametrize("endpoint", ["search", "typeahead"])
async def test_alias_keeps_supported_unpriced_result(inventory, endpoint):
    request, ids, _, _, _, maker = inventory
    async with maker() as session:
        row = await session.get(FuturesOutcome, ids["shai"])
        row.current_probability = row.current_yes_bid = row.current_yes_ask = None
        row.is_winner = True
        row.resolution_source = "api_settlement"
        await session.commit()
    selected = list(_rows(await request(endpoint), ids["market"]))
    assert selected
    for rows in selected:
        shai = next(o for o in rows if o["name"] == NAME)
        assert shai["probability"] is None
        assert shai["rendered_percent"] is None
        assert shai["is_winner"] is True
        assert shai["resolution_source"] == "api_settlement"


@pytest.mark.parametrize("endpoint", ["search", "typeahead"])
async def test_alias_cache_refresh_preserves_live_entry_until_rebuild(
    inventory, endpoint, monkeypatch
):
    request, ids, _, cache, statements, _ = inventory
    aliases = person_aliases.REVIEWED_PERSON_ALIASES
    monkeypatch.setattr(person_aliases, "REVIEWED_PERSON_ALIASES", ())
    before = await request(endpoint)
    assert not list(_rows(before, ids["market"]))
    monkeypatch.setattr(person_aliases, "REVIEWED_PERSON_ALIASES", aliases)
    stored, expiry = dict(cache.store), dict(cache.expires_at)
    count = len(statements)
    assert await request(endpoint) == before
    assert len(statements) == count
    assert cache.store == stored and cache.expires_at == expiry
    force = (
        events._force_search_cache_rebuild
        if endpoint == "search"
        else events._force_cache_rebuild
    )
    token = force.set(True)
    try:
        rebuilt = await request(endpoint)
    finally:
        force.reset(token)
    assert list(_rows(rebuilt, ids["market"]))
    count = len(statements)
    assert await request(endpoint) == rebuilt
    assert len(statements) == count


@pytest.mark.parametrize("endpoint", ["search", "typeahead"])
async def test_conflicting_alias_refuses_shai_but_preserves_generic_recall(
    inventory, endpoint, monkeypatch
):
    request, ids, *_ = inventory
    original = person_aliases.REVIEWED_PERSON_ALIASES[0]
    monkeypatch.setattr(
        person_aliases,
        "REVIEWED_PERSON_ALIASES",
        (
            original,
            replace(original, provider_id="other-person"),
        ),
    )
    body = await request(endpoint)
    assert not list(_rows(body, ids["market"]))
    rows = body.get("futures", body.get("suggestions", []))
    assert any(
        "SGA regulatory decision" == r.get("name", r.get("text", "")) for r in rows
    )


async def test_explicit_wrong_sport_does_not_expand_person_alias(inventory):
    request, ids, *_ = inventory
    assert not list(
        _rows(await request("search", sport="americanfootball_nfl"), ids["market"])
    )


@pytest.mark.parametrize("endpoint", ["search", "typeahead"])
async def test_katie_and_branch_remain_distinct_search_destinations(
    inventory, endpoint
):
    request, _, *_ = inventory
    body = await request(endpoint, "Zacharia")
    rows = body.get("futures", body.get("suggestions", []))
    names = [r.get("name", r.get("text", "")) for r in rows]
    assert "Will Katie Zacharia become governor?" in names
    assert "Offensive Rookie of the Year Winner?" in names
    assert names.index("Will Katie Zacharia become governor?") < names.index(
        "Offensive Rookie of the Year Winner?"
    )
    branch = await request(endpoint, "Zachariah Branch")
    rows = branch.get("futures", branch.get("suggestions", []))
    assert any(
        "Offensive Rookie of the Year Winner?" == r.get("name", r.get("text", ""))
        for r in rows
    )


@pytest.mark.parametrize("endpoint", ["search", "typeahead"])
async def test_july_queries_and_registry_keep_same_inventory_answers(
    inventory, endpoint, monkeypatch
):
    """Regression material, not an unseen or production-accuracy benchmark.

    Keep all July queries, including those without a stable expected entity,
    and the current registry's later additions. The small SQL fixture does not
    contain every historical destination: count empty answers explicitly.
    """
    from scripts.evals.build_search_gold_registry import GOLD_ROWS, MC_CANDIDATES

    registry = json.loads(
        (
            Path(__file__).parents[2] / "scripts/evals/search_gold_probes.json"
        ).read_text()
    )
    queries = list(
        dict.fromkeys(
            [
                *(row[0] for row in GOLD_ROWS),
                *(q for group, _ in MC_CANDIDATES for q in group),
                *(row["presentation"]["query"] for row in registry["probes"]),
            ]
        )
    )
    request, _, _, _, _, _ = inventory
    aliases = person_aliases.REVIEWED_PERSON_ALIASES
    # Freeze only route-local clocks. This is response equivalence, not a
    # timing gate; asyncio and the real SQL engine keep their actual clocks.
    monkeypatch.setattr(
        events,
        "time",
        SimpleNamespace(
            monotonic=lambda: 1000.0,
            perf_counter=lambda: 1000.0,
        ),
    )
    force = (
        events._force_search_cache_rebuild
        if endpoint == "search"
        else events._force_cache_rebuild
    )
    token = force.set(True)
    comparisons = []
    try:
        for query in queries:
            bodies = []
            for enabled in (False, True):
                monkeypatch.setattr(
                    person_aliases,
                    "REVIEWED_PERSON_ALIASES",
                    aliases if enabled else (),
                )
                monkeypatch.setattr(events, "_roster_index", {})
                monkeypatch.setattr(events, "_roster_index_expires_at", 0.0)
                bodies.append(await request(endpoint, query))
            sections = (
                ("suggestions",)
                if endpoint == "typeahead"
                else (
                    "results",
                    "teams",
                    "futures",
                    "futures_families",
                    "event_concepts",
                )
            )
            counts = [
                {key: len(body.get(key) or []) for key in sections} for body in bodies
            ]
            comparisons.append(
                {
                    "query": query,
                    "identical": bodies[0] == bodies[1],
                    "before_counts": counts[0],
                    "after_counts": counts[1],
                    "degraded": bodies[1].get("degraded", []),
                    "no_results": not any(counts[1].values())
                    and not bodies[1].get("degraded"),
                }
            )
    finally:
        force.reset(token)
    print(
        "ALIAS_QUERY_COMPARISON "
        + json.dumps(
            {
                "endpoint": endpoint,
                "scope": "same seeded inventory; no accuracy claim",
                "queries": comparisons,
            },
            sort_keys=True,
        )
    )
    assert all(row["identical"] for row in comparisons), [
        row for row in comparisons if not row["identical"]
    ]
