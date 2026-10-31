"""#10090: warm Sports metadata saves the wide read, with current reader truth.

The actual ASGI route, PostgreSQL rows, personalization, both scorers, and display
chain run here. Only provider token verification and external Redis are replaced.
Every feed_cache response tier misses; the independent artifact key space survives.
The RED is a repeated wide market SELECT, rather than a missing new helper import.
"""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
import re
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DB_URL = os.environ.get("TASK10_TEST_DATABASE_URL") or os.environ.get(
    "SEARCH_TEST_DATABASE_URL"
)
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not DB_URL, reason="requires explicit disposable local PG"),
]

NOW = datetime(2026, 10, 31, 20, 14, tzinfo=timezone.utc)
FIRST_EVENT = 50000
NFL_MARKET = 10001
NBA_MARKET = 10002
WITHHELD_MARKET = 10009
SETTLED_MARKET = 10010
ACTOR_A = 901
ACTOR_B = 902


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.replace(tzinfo=None) if tz is None else NOW.astimezone(tz)


class _RedisMap:
    """Persistent artifact bytes; complete feed responses cannot answer a test."""

    def __init__(self):
        self.values: dict[str, object] = {}

    def get(self, key):
        if str(key).startswith("feed_cache:"):
            return None
        return self.values.get(str(key))

    def set(self, key, value, ex=None, nx=False, **kwargs):
        key = str(key)
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def setex(self, key, ttl, value):
        return self.set(key, value)

    def delete(self, *keys):
        return sum(self.values.pop(str(key), None) is not None for key in keys)

    def mget(self, keys, *extra):
        keys = [keys, *extra] if extra or isinstance(keys, str) else keys
        return [self.get(key) for key in keys]

    def exists(self, key):
        return int(self.get(key) is not None)

    def ping(self):
        return True


class _AsyncRedis:
    def __init__(self, store):
        self.store = store

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, **kwargs):
        return self.store.set(key, value, **kwargs)

    async def setex(self, key, ttl, value):
        return self.store.setex(key, ttl, value)

    async def mget(self, keys, *extra):
        return self.store.mget(keys, *extra)

    async def delete(self, *keys):
        return self.store.delete(*keys)

    async def exists(self, key):
        return self.store.exists(key)

    async def aclose(self):
        pass


def _table_closure(roots):
    tables = {}
    pending = list(roots)
    while pending:
        table = pending.pop()
        if table.key in tables:
            continue
        tables[table.key] = table
        pending.extend(fk.column.table for fk in table.foreign_keys)
    return list(tables.values())


def _public(payload):
    """Remove request/build bookkeeping; retain every reader-visible value."""
    return {
        key: value
        for key, value in payload.items()
        if key not in {"cache", "edition", "edition_status", "timings", "_timings_ms"}
    }


def _by_id(payload, kind):
    return {
        item["data"]["id"]: item for item in payload["items"] if item["type"] == kind
    }


@dataclass
class _Rig:
    client: AsyncClient
    maker: object
    statements: list[str]
    monkeypatch: object
    store: _RedisMap
    last_headers: dict[str, str] | None = None

    async def read(
        self, actor=None, *, reuse=True, limit=20, offset=0, allow_degraded=False
    ):
        if reuse is None:
            self.monkeypatch.delenv("FEED_SPORTS_METADATA_REUSE", raising=False)
        else:
            self.monkeypatch.setenv("FEED_SPORTS_METADATA_REUSE", "1" if reuse else "0")
        headers = {"Authorization": f"Bearer task10-{actor}"} if actor else {}
        self.statements.clear()
        response = await self.client.get(
            "/api/feed",
            params={"mode": "sports", "limit": limit, "offset": offset},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        self.last_headers = dict(response.headers)
        payload = response.json()
        assert payload.get("cache", {}).get("status") not in {
            "hit",
            "stale_hit",
            "shared_hit",
            "base_hit",
            "last_good",
            "unavailable",
        }, payload.get("cache")
        if not allow_degraded:
            assert payload.get("build_quality", "complete") == "complete", payload
        await asyncio.sleep(0)  # let independent artifact publication finish
        return payload, list(self.statements)


def _wide_markets(statements):
    """The source's wide Sports carrier, not its current-id/version probes."""
    full_metadata = re.compile(
        r"(?:[a-z_][a-z_0-9]*\.)?market_metadata(?:\s+as\s+[a-z_][a-z_0-9]*)?(?=\s*(?:,|$))"
    )
    return [
        sql
        for sql in statements
        if sql.lstrip().startswith("select ")
        and "from futures_markets" in sql
        and full_metadata.search(sql.split(" from ", 1)[0])
    ]


def _outcome_reads(statements):
    return [
        sql
        for sql in statements
        if sql.lstrip().startswith("select ")
        and "from futures_outcomes" in sql
        and "current_probability" in sql.split(" from ", 1)[0]
    ]


@pytest.fixture
async def rig(monkeypatch):
    # Never inherit the application DATABASE_URL or any non-loopback test URL.
    url = make_url(DB_URL)
    assert url.host in {
        "127.0.0.1",
        "localhost",
        "::1",
    }, "explicit loopback test PG only"
    assert url.query.get("host", url.host) in {"127.0.0.1", "localhost", "::1"}
    schema = "task10_sports_" + uuid4().hex
    admin = create_async_engine(DB_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": schema}}
    )
    statements = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.lower().split()))

    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    # Response lookup is blocked in the fake; do not disable artifact sharing.
    from app.dependencies import auth
    from app.main import app
    from app.models import models as m
    from app.routes import feed
    from app.services.database import Base, get_db, get_db_rw
    from app.services import database
    from app.tasks import redis_state
    from app.utils import golf_base
    from app.utils import request_cache as rc

    monkeypatch.setattr(feed, "datetime", _FixedDateTime)
    monkeypatch.setattr(
        auth,
        "verify_id_token",
        lambda token: {"uid": token} if token in {"task10-901", "task10-902"} else None,
    )
    store = _RedisMap()
    # The golf listing is an external precomputed base. This fixture has no golf
    # tournament; its honest empty base prevents a DataGolf request on cache miss.
    store.set(
        golf_base.GOLF_BASE_FRESH_KEY, json.dumps(golf_base.build_envelope(NOW, []))
    )
    async_redis = _AsyncRedis(store)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: store)
    monkeypatch.setattr(redis_state, "get_async_redis_client", lambda: async_redis)

    async def _redis():
        return async_redis

    monkeypatch.setattr(rc, "get_shared_async_redis", _redis)
    monkeypatch.setattr(rc, "recall_last_good", lambda *args, **kwargs: None)

    # Core feed tables plus empty golf/concept/review readers; FK closure keeps
    # schema creation scoped, rather than touching unrelated registered tables.
    names = {
        "sports",
        "teams",
        "events",
        "odds_snapshots",
        "win_prob_snapshots",
        "futures_markets",
        "futures_outcomes",
        "futures_odds_snapshots",
        "users",
        "user_favorites",
        "user_preferences",
        "user_pins",
        "discover_interactions",
        "user_seen_markets",
        "ranking_judgments",
        "discover_review_decisions",
        "settlement_captures",
    }
    roots = [
        table
        for name, table in Base.metadata.tables.items()
        if name in names or name.startswith(("golf_", "event_concept"))
    ]
    tables = _table_closure(roots)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session_maker", maker)

    async def _db():
        async with maker() as session:
            yield session

    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_rw] = _db
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        await _seed(maker, m)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield _Rig(client, maker, statements, monkeypatch, store)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def _seed(maker, m):
    league_rows = [
        (
            1,
            "americanfootball_nfl",
            "NFL",
            "football",
            "NFL Super Bowl Champion 2027",
            ["New England Patriots", "Buffalo Bills", "Kansas City Chiefs"],
        ),
        (
            2,
            "basketball_nba",
            "NBA",
            "basketball",
            "NBA Champion 2027",
            ["Boston Celtics", "Los Angeles Lakers", "Denver Nuggets"],
        ),
        (
            3,
            "icehockey_nhl",
            "NHL",
            "hockey",
            "NHL Stanley Cup Champion 2027",
            ["Boston Bruins", "Florida Panthers", "Toronto Maple Leafs"],
        ),
        (
            4,
            "baseball_mlb",
            "MLB",
            "baseball",
            "MLB World Series Champion 2027",
            ["Boston Red Sox", "New York Yankees", "Los Angeles Dodgers"],
        ),
        (
            5,
            "soccer_epl",
            "EPL",
            "soccer",
            "English Premier League Champion 2027",
            ["Arsenal", "Liverpool", "Manchester City"],
        ),
        (
            6,
            "americanfootball_ncaaf",
            "NCAAF",
            "football",
            "College Football Champion 2027",
            ["Michigan Wolverines", "Ohio State Buckeyes", "Georgia Bulldogs"],
        ),
        (
            7,
            "basketball_ncaab",
            "NCAAB",
            "basketball",
            "College Basketball Champion 2027",
            ["Duke Blue Devils", "Kansas Jayhawks", "UConn Huskies"],
        ),
        (
            8,
            "soccer_uefa_champs_league",
            "UCL",
            "soccer",
            "UEFA Champions League Winner 2027",
            ["Real Madrid", "Barcelona", "Bayern Munich"],
        ),
    ]
    async with maker() as session:
        for sid, key, display, category, name, clubs in league_rows:
            session.add(m.Sport(id=sid, key=key, name=display, active=True))
            for pos, club in enumerate(clubs):
                session.add(
                    m.Team(
                        id=sid * 100 + pos,
                        sport_id=sid,
                        name=club,
                        espn_id=str(sid * 100 + pos),
                        current_record="6-2",
                    )
                )
        session.add_all(
            [
                m.User(
                    id=ACTOR_A, firebase_uid="task10-901", display_name="Task Ten A"
                ),
                m.User(
                    id=ACTOR_B, firebase_uid="task10-902", display_name="Task Ten B"
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                m.UserFavorite(
                    user_id=ACTOR_A, team_id=100, relation_type="follow", weight=1
                ),
                m.UserFavorite(
                    user_id=ACTOR_B, team_id=200, relation_type="follow", weight=1
                ),
                m.UserPreference(
                    user_id=ACTOR_A, sport_affinities={"americanfootball_nfl": 1}
                ),
                m.UserPreference(
                    user_id=ACTOR_B, sport_affinities={"basketball_nba": 1}
                ),
                m.UserPin(user_id=ACTOR_A, pin_type="event", target_id=FIRST_EVENT + 6),
            ]
        )
        for sid, key, display, category, name, clubs in league_rows:
            mid = 10000 + sid
            session.add(
                m.FuturesMarket(
                    id=mid,
                    sport_id=sid,
                    source="polymarket",
                    external_id=f"task10-market-{mid}",
                    name=name,
                    status="open",
                    market_type="field",
                    category="championship",
                    market_tier=1,
                    llm_sport_category=category,
                    mutually_exclusive=True,
                    resolution_date=NOW + timedelta(days=150),
                    updated_at=NOW,
                    created_at=NOW - timedelta(days=3),
                    volume_24h=8_000_000 - sid * 100_000,
                    volume=100_000_000,
                    image_url=f"https://example.test/task10/{mid}.jpg",
                    market_metadata={
                        "task10_revision": "initial",
                        "mutually_exclusive": True,
                        "fixture_blob": "task10-plain-metadata " * 300,
                    },
                )
            )
            await session.flush()
            probabilities = [0.4, 0.4, 0.2] if sid == 2 else [0.4, 0.35, 0.25]
            for pos, (club, probability) in enumerate(zip(clubs, probabilities)):
                session.add(
                    m.FuturesOutcome(
                        id=mid * 10 + pos,
                        market_id=mid,
                        external_id=f"task10-{mid}-{pos}",
                        name=club,
                        team_id=sid * 100 + pos,
                        current_probability=probability,
                        opening_probability=probability - 0.03,
                        probability_change_24h=0.03 if pos == 0 else -0.015,
                        current_yes_bid=probability - 0.01,
                        current_yes_ask=probability + 0.01,
                        last_updated=NOW,
                        price_changed_at=NOW,
                        volume_24h=1000,
                        volume_24h_at=NOW,
                        rank=pos + 1,
                        is_winner=False,
                    )
                )
        # A refused whole field and an actual graded result are in the candidate
        # universe; their omission must survive both reuse and later price edits.
        for mid, settled in [(WITHHELD_MARKET, False), (SETTLED_MARKET, True)]:
            session.add(
                m.FuturesMarket(
                    id=mid,
                    sport_id=1,
                    source="polymarket",
                    external_id=f"task10-market-{mid}",
                    name=(
                        "NFL Offensive Player of the Year 2027"
                        if not settled
                        else "NFL AFC Champion 2027"
                    ),
                    status="open",
                    market_type="field",
                    category="award",
                    market_tier=1,
                    llm_sport_category="football",
                    resolution_date=NOW + timedelta(days=150),
                    updated_at=NOW,
                    created_at=NOW - timedelta(days=3),
                    mutually_exclusive=True,
                    market_metadata={},
                    volume_24h=7_000_000,
                )
            )
            await session.flush()
            for pos, club in enumerate(["New England Patriots", "Buffalo Bills"]):
                probability = (1 if pos == 0 else 0) if settled else 0.5
                session.add(
                    m.FuturesOutcome(
                        id=mid * 10 + pos,
                        market_id=mid,
                        external_id=f"task10-{mid}-{pos}",
                        name=club,
                        team_id=100 + pos,
                        current_probability=probability,
                        opening_probability=0.5,
                        probability_change_24h=0,
                        current_yes_bid=0.01,
                        current_yes_ask=0.99,
                        last_updated=NOW,
                        price_changed_at=NOW,
                        volume_24h=1000,
                        volume_24h_at=NOW,
                        is_winner=(pos == 0) if settled else False,
                        resolution_source="api_settlement" if settled else None,
                        rank=pos + 1,
                    )
                )
        for pos in range(18):
            eid = FIRST_EVENT + pos
            status = "live" if pos < 3 else "completed" if pos < 6 else "scheduled"
            start = (
                NOW - timedelta(hours=1 if pos < 3 else 3)
                if pos < 6
                else NOW + timedelta(minutes=20 + pos * 5)
            )
            session.add(
                m.Event(
                    id=eid,
                    sport_id=1,
                    external_id=f"task10-event-{eid}",
                    espn_id=str(110090000 + pos),
                    home_team_id=100 + pos % 3,
                    away_team_id=100 + (pos + 1) % 3,
                    home_team_name=league_rows[0][5][pos % 3],
                    away_team_name=league_rows[0][5][(pos + 1) % 3],
                    commence_time=start,
                    status=status,
                    completed_at=(
                        NOW - timedelta(minutes=10 + pos)
                        if status == "completed"
                        else None
                    ),
                    opening_home_probability=0.55,
                    opening_away_probability=0.45,
                    opening_favorite="home",
                    home_score=24 if pos < 6 else None,
                    away_score=21 if pos < 6 else None,
                    raw_ei=70,
                    llm_importance="regular",
                    period="Q3" if status == "live" else None,
                    game_clock="5:00" if status == "live" else None,
                    win_probability_sources={
                        "betting": {"value": 0.55, "updated_at": NOW.isoformat()}
                    },
                )
            )
        session.add_all(
            [
                m.DiscoverInteraction(
                    user_id=ACTOR_A,
                    session_id="task10-a",
                    item_type="event",
                    item_id=str(FIRST_EVENT + 6),
                    action="impression",
                    category="football",
                    item_name="New England Patriots vs Buffalo Bills",
                    created_at=NOW - timedelta(hours=2),
                ),
                m.DiscoverInteraction(
                    user_id=ACTOR_A,
                    session_id="task10-a",
                    item_type="event",
                    item_id=str(FIRST_EVENT),
                    action="unlike",
                    category="football",
                    item_name="New England Patriots vs Buffalo Bills",
                    created_at=NOW - timedelta(days=3),
                ),
                m.DiscoverInteraction(
                    user_id=ACTOR_B,
                    session_id="task10-b",
                    item_type="event",
                    item_id=str(FIRST_EVENT + 7),
                    action="impression",
                    category="football",
                    item_name="Buffalo Bills vs Kansas City Chiefs",
                    created_at=NOW - timedelta(hours=49),
                ),
                m.DiscoverInteraction(
                    user_id=ACTOR_B,
                    session_id="task10-b",
                    item_type="event",
                    item_id=str(FIRST_EVENT + 1),
                    action="unlike",
                    category="football",
                    item_name="Buffalo Bills vs Kansas City Chiefs",
                    created_at=NOW - timedelta(days=15),
                ),
                m.UserSeenMarket(
                    user_id=ACTOR_A,
                    session_id="task10-a",
                    item_type="futures",
                    item_id=NFL_MARKET,
                    seen_at=NOW - timedelta(hours=2),
                ),
            ]
        )
        await session.commit()


async def test_warm_signed_in_sports_reuses_metadata_with_the_same_reader_page(rig):
    full, _ = await rig.read(limit=200)
    assert (
        len(_by_id(full, "futures")) > 6
    ), "the cap fixture must contain surplus fields"
    prime, _ = await rig.read()
    assert _by_id(prime, "event"), "the real event scorer must contribute Sports games"
    baseline, cold_sql = await rig.read(ACTOR_A, reuse=False)
    warm, warm_sql = await rig.read(ACTOR_A)
    assert _public(warm) == _public(baseline)
    assert _wide_markets(cold_sql), "OFF must execute the current wide market reader"
    assert _outcome_reads(warm_sql), "live outcome prices/grades must still be read"
    assert FIRST_EVENT in _by_id(warm, "event"), "Sports retains a Discover-swiped game"
    assert FIRST_EVENT + 6 in _by_id(
        warm, "event"
    ), "Sports retains a Discover-seen game"
    assert len(_by_id(warm, "futures")) <= 6
    assert WITHHELD_MARKET not in _by_id(warm, "futures")
    assert SETTLED_MARKET not in _by_id(warm, "futures")
    assert not _wide_markets(warm_sql), (
        "warm signed-in Sports repeated the wide FuturesMarket metadata SELECT; "
        f"expected shared metadata reuse, got {len(_wide_markets(warm_sql))} reads"
    )


async def test_metadata_reuse_is_off_without_the_explicit_switch(rig):
    await rig.read()
    control, _ = await rig.read(ACTOR_A, reuse=False, limit=200)
    default, sql = await rig.read(ACTOR_A, reuse=None, limit=200)
    assert _public(default) == _public(control)
    assert _wide_markets(sql), "an unset switch must use the original wide reader"


async def test_another_worker_reuses_the_same_plain_metadata_from_redis(rig):
    from app.utils import principal_independent_cache as pic
    from app.utils import request_cache as rc

    await rig.read(limit=200)
    if rc._background_tasks:
        await asyncio.gather(*tuple(rc._background_tasks))
    # Existing test cleanup drops L1 only; the external Redis bytes remain. The
    # next request therefore exercises metadata serialization and L2 hydration.
    pic.clear_shared_builds()
    warm, sql = await rig.read(ACTOR_A, limit=200)
    control, _ = await rig.read(ACTOR_A, reuse=False, limit=200)
    assert _public(warm) == _public(control)
    assert _outcome_reads(sql)
    assert not _wide_markets(sql), "a cold worker must reuse the shared metadata bytes"


@pytest.mark.parametrize("tier", ["local", "redis"])
async def test_an_invalid_cached_resolution_timestamp_rebuilds_the_full_signed_in_page(
    rig, tier
):
    """Valid cache identity/proof cannot make a wrongly typed column trustworthy.

    The source bug accepts this string, marks a reuse, and later drops the entire
    futures stage when the Sports scorer asks the supposed datetime for tzinfo.
    Refusing that artifact must run the original wide read and keep the page.
    """
    from app.utils import principal_independent_cache as pic
    from app.utils import request_cache as rc

    await rig.read(limit=200)
    reference, _ = await rig.read(ACTOR_A, reuse=False, limit=200)
    assert NFL_MARKET in _by_id(
        reference, "futures"
    ), "the control must contain the affected field"
    if rc._background_tasks:
        await asyncio.gather(*tuple(rc._background_tasks))

    entries = pic._store["sports_metadata"]
    key, (stored_at, original) = next(iter(entries.items()))
    bad = copy.deepcopy(original)
    timestamp_column = bad["columns"].index("resolution_date")
    row = next(row for row in bad["rows"] if row[0] == NFL_MARKET)
    assert isinstance(
        row[timestamp_column], datetime
    ), "prime must hold an actual PG datetime"
    row[timestamp_column] = "invalid-cached-timestamp"
    assert (bad["scope"], bad["versions"]) == (original["scope"], original["versions"])

    if tier == "local":
        entries[key] = (stored_at, bad)
    else:
        redis_key = pic.redis_key_for("sports_metadata", key)
        wire_json = pic.wire_decode(rig.store.values[redis_key])
        assert wire_json is not None, "prime must have published a valid Redis envelope"
        envelope = json.loads(wire_json)
        # Keep version, namespace, key and stored age exactly as published. The
        # existing lossless codec permits strings; column semantics must refuse it.
        envelope["payload"] = pic.encode_shared_payload(bad)
        rig.store.values[redis_key] = pic.wire_encode(json.dumps(envelope))
        pic.clear_shared_builds("sports_metadata")

    rebuilt, sql = await rig.read(ACTOR_A, limit=200, allow_degraded=True)
    assert _by_id(rebuilt, "futures") == _by_id(reference, "futures"), (
        f"{tier} accepted a string resolution_date from a valid cache envelope "
        "and lost signed-in Sports futures instead of rebuilding their current rows"
    )
    assert _public(rebuilt) == _public(reference)
    assert rig.last_headers is not None
    assert "sports_metadata" not in rig.last_headers.get("x-feed-shared", "").split(
        ","
    ), "a rejected artifact must not be reported as a validated metadata reuse"
    assert _wide_markets(
        sql
    ), "rejecting the column type must run the fresh wide fallback"
    assert _outcome_reads(
        sql
    ), "the fallback must still load current whole-field prices and grades"


async def test_warm_metadata_does_not_freeze_prices_or_graded_results(rig):
    from app.models.models import FuturesOutcome

    await rig.read(limit=200)
    # New transaction IDs matter: cache priming and updates are committed apart.
    async with rig.maker() as session:
        for pos, probability in enumerate([0.50, 0.30, 0.20]):
            await session.execute(
                update(FuturesOutcome)
                .where(FuturesOutcome.id == NFL_MARKET * 10 + pos)
                .values(
                    current_probability=probability,
                    current_yes_bid=probability - 0.01,
                    current_yes_ask=probability + 0.01,
                    last_updated=NOW,
                )
            )
        for pos in range(3):
            await session.execute(
                update(FuturesOutcome)
                .where(FuturesOutcome.id == NBA_MARKET * 10 + pos)
                .values(
                    current_probability=1 if pos == 0 else 0,
                    is_winner=pos == 0,
                    resolution_source="api_settlement",
                    last_updated=NOW,
                )
            )
        await session.commit()
    baseline, _ = await rig.read(ACTOR_A, reuse=False, limit=200)
    warm, sql = await rig.read(ACTOR_A, limit=200)
    assert _public(warm) == _public(baseline)
    assert (
        _by_id(warm, "futures")[NFL_MARKET]["data"]["top_outcomes"][0]["probability"]
        == 0.5
    )
    assert NBA_MARKET not in _by_id(
        warm, "futures"
    ), "the newly graded result leaves the live feed"
    assert _outcome_reads(sql)
    assert not _wide_markets(
        sql
    ), "a price-only edit must not invalidate unchanged market metadata"


@pytest.mark.parametrize("mutation", ["metadata", "status", "candidate"])
async def test_current_market_versions_and_candidate_membership_invalidate_metadata(
    rig, mutation
):
    from app.models.models import FuturesMarket, FuturesOutcome

    await rig.read(limit=200)
    async with rig.maker() as session:
        if mutation == "metadata":
            await session.execute(
                update(FuturesMarket)
                .where(FuturesMarket.id == NFL_MARKET)
                .values(
                    market_metadata={
                        "task10_revision": "changed",
                        "mutually_exclusive": True,
                    },
                    image_url="https://example.test/task10/changed.jpg",
                    updated_at=NOW,
                )
            )
        elif mutation == "status":
            await session.execute(
                update(FuturesMarket)
                .where(FuturesMarket.id == NFL_MARKET)
                .values(
                    status="resolved",
                    settled_at=NOW,
                    updated_at=NOW,
                )
            )
        else:
            session.add(
                FuturesMarket(
                    id=20001,
                    sport_id=1,
                    source="polymarket",
                    external_id="task10-new-candidate",
                    name="NFL Defensive Player of the Year Winner 2027",
                    status="open",
                    market_type="field",
                    category="award",
                    market_tier=1,
                    llm_sport_category="football",
                    resolution_date=NOW + timedelta(days=150),
                    updated_at=NOW,
                    created_at=NOW - timedelta(days=1),
                    volume_24h=9_000_000,
                    mutually_exclusive=True,
                    market_metadata={"task10_revision": "new"},
                )
            )
            await session.flush()
            for pos, (name, probability) in enumerate(
                [("Myles Garrett", 0.4), ("T.J. Watt", 0.35), ("Micah Parsons", 0.25)]
            ):
                session.add(
                    FuturesOutcome(
                        id=200010 + pos,
                        market_id=20001,
                        external_id=f"task10-new-{pos}",
                        name=name,
                        current_probability=probability,
                        opening_probability=probability - 0.03,
                        probability_change_24h=0.03,
                        current_yes_bid=probability - 0.01,
                        current_yes_ask=probability + 0.01,
                        last_updated=NOW,
                        volume_24h=1000,
                        volume_24h_at=NOW,
                        rank=pos + 1,
                    )
                )
        await session.commit()
    warm, sql = await rig.read(ACTOR_A, limit=200)
    baseline, _ = await rig.read(ACTOR_A, reuse=False, limit=200)
    assert _public(warm) == _public(baseline)
    assert _wide_markets(
        sql
    ), "a changed row/version or candidate set must rebuild the metadata"
    futures = _by_id(warm, "futures")
    if mutation == "metadata":
        assert (
            futures[NFL_MARKET]["data"]["image_url"]
            == "https://example.test/task10/changed.jpg"
        )
    elif mutation == "status":
        assert NFL_MARKET not in futures
    else:
        assert 20001 in futures


async def test_two_readers_keep_their_own_scores_and_tied_outcome_order(rig):
    await rig.read(limit=200)
    control_a, _ = await rig.read(ACTOR_A, reuse=False, limit=200)
    control_b, _ = await rig.read(ACTOR_B, reuse=False, limit=200)
    warm_a, sql_a = await rig.read(ACTOR_A, limit=200)
    warm_b, sql_b = await rig.read(ACTOR_B, limit=200)
    assert _public(warm_a) == _public(control_a)
    assert _public(warm_b) == _public(control_b)
    a, b = _by_id(warm_a, "futures"), _by_id(warm_b, "futures")
    assert a[NFL_MARKET]["score"] > b[NFL_MARKET]["score"]
    assert b[NBA_MARKET]["score"] > a[NBA_MARKET]["score"]
    tied = b[NBA_MARKET]["data"]["top_outcomes"]
    assert {outcome["id"] for outcome in tied[:2]} == {
        NBA_MARKET * 10,
        NBA_MARKET * 10 + 1,
    }
    assert tied[0]["probability"] == tied[1]["probability"] == 0.4
    assert tied == _by_id(control_b, "futures")[NBA_MARKET]["data"]["top_outcomes"]
    assert not _wide_markets(sql_a) and not _wide_markets(sql_b)


async def test_warm_signed_in_sports_keeps_the_empty_offset_end_state(rig):
    await rig.read()
    control, _ = await rig.read(ACTOR_A, reuse=False, offset=1000)
    warm, sql = await rig.read(ACTOR_A, offset=1000)
    assert _public(warm) == _public(control)
    assert warm["items"] == [] and warm["has_more"] is False
    assert warm["offset"] == 1000 and warm["total"] > 0
    assert _outcome_reads(sql), "the empty page still reads current candidate truth"
    assert not _wide_markets(sql)


async def test_a_failing_helper_statement_falls_back_in_a_clean_transaction(
    rig, monkeypatch
):
    """An SQL error inside the reuse helper must not poison the fallback read.

    Without the savepoint (or with a narrower except), the aborted transaction
    makes the original loader fail too and signed-in Sports loses its futures.
    """
    from sqlalchemy import literal_column

    from app.utils import sports_market_metadata_reuse as reuse

    await rig.read(limit=200)
    control, _ = await rig.read(ACTOR_A, reuse=False, limit=200)
    original = reuse._proof_columns
    monkeypatch.setattr(
        reuse,
        "_proof_columns",
        lambda: (*original(), literal_column("(1/0)").label("task10_boom")),
    )
    warm, sql = await rig.read(ACTOR_A, limit=200)
    assert _public(warm) == _public(control)
    assert _wide_markets(sql), "the original loader must run after the SQL error"
    assert rig.last_headers is not None
    assert "sports_metadata" not in rig.last_headers.get("x-feed-shared", "").split(",")
