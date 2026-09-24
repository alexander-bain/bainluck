"""The #7878 evidence contract crosses the HTTP response. Real Postgres, real route.

Codex's exact-head review of PR #8438 (2026-09-24 19:43Z) reproduced that the
producer's `evidence_span` never reached a client: `_project_served_game_state`
(#6546) narrows each point's `game_state` to seven keys at the final response
boundary, so a stamped span arrived as `{period: 1H}` and backfill/final points
as `null`. Fourteen Postgres cases on the retention SQL could not see that — they
never crossed the route.

So this gate goes end to end, in one file: seed `win_prob_snapshots`, run the
REAL retention collapse so the span is the one the SQL writes, then GET
`/api/events/{id}/history` through the real FastAPI app and read the served JSON.
It covers every kind Codex named — genuine raw, compacted span, legacy unknown,
foreign stamp, candle and price-history backfill, synthetic live edge, synthetic
final, terminal row — and asserts the bulk metadata #6546 removed is still gone.
"""

from __future__ import annotations

import datetime as dt
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #7878 wire gate "
            "(CI's search-recall job provides it)"
        ),
    ),
]

UTC = dt.timezone.utc

#: Reserved ids, explicit so this gate never draws from the shared database's
#: sequences (the #6221 sibling records the CI failure that costs).
S_ID = 90_007_878
FINISHED = 90_007_878_1
LIVE = 90_007_878_2
SNAP_BASE = 2_007_878_000

SPAN_OK = {"contract": "7878.v1", "resolution_s": 300}


@pytest.fixture
async def pg_engine():
    """Whole metadata, as the #6975 route gate does: the history route reads
    eight tables. CI's service is Postgres 15 (one `NULLS NOT DISTINCT` index)."""
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, checkfirst=True))
    await _clear(engine)
    yield engine
    await _clear(engine)
    await engine.dispose()


async def _clear(engine):
    from app.models.models import Event, Sport, WinProbSnapshot

    async with AsyncSession(engine) as session:
        await session.execute(delete(WinProbSnapshot).where(WinProbSnapshot.event_id.in_([FINISHED, LIVE])))
        await session.execute(delete(Event).where(Event.id.in_([FINISHED, LIVE])))
        await session.execute(delete(Sport).where(Sport.id == S_ID))
        await session.commit()


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, k):
        return self.store.get(k)

    def setex(self, k, ttl, v):
        self.store[k] = v.encode() if isinstance(v, str) else v

    def set(self, k, v, nx=False, ex=None, **_):
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else v
        return True

    def delete(self, *keys):
        return sum(int(self.store.pop(k, None) is not None) for k in keys)

    def exists(self, k):
        return int(k in self.store)


@pytest.fixture
def fake_redis(monkeypatch):
    from app.routes import events as events_route
    from app.tasks import redis_state
    from app.utils import game_markets_cache as gmc

    rc = _FakeRedis()
    monkeypatch.setattr(gmc, "get_client", lambda: rc)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: rc)
    events_route._event_detail_cache.clear()
    yield rc
    events_route._event_detail_cache.clear()


@pytest.fixture
async def client(pg_engine, fake_redis, monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    async def _real_get_db():
        async with AsyncSession(pg_engine, expire_on_commit=False) as session:
            yield session

    async def _no_user():
        return None

    app.dependency_overrides[get_db] = _real_get_db
    app.dependency_overrides[get_db_rw] = _real_get_db
    app.dependency_overrides[get_optional_user] = _no_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                yield ac
    finally:
        app.dependency_overrides.clear()


def _gs(**extra):
    return {"market_id": 555, "market_name": "Home v Away", "outcome_name": "Home",
            "poll_type": "live_fast", "yes_probability": 0.6, **extra}


async def _seed(engine):
    """FINISHED: every stored kind, 72h old so the collapse ages them. LIVE: a
    stamped last reading 10 min old on a live game, so the route adds a live edge
    that COPIES that stamp."""
    from app.models.models import Event, Sport, WinProbSnapshot

    now = dt.datetime.now(UTC).replace(microsecond=0)
    base = now - dt.timedelta(hours=72)
    at = lambda m: base + dt.timedelta(minutes=m)  # noqa: E731
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(Sport(id=S_ID, key="baseball_mlb_w7878", name="MLB 7878", active=True))
        await session.flush()
        session.add(Event(
            id=FINISHED, sport_id=S_ID, home_team_name="Home Wire", away_team_name="Away Wire",
            commence_time=at(-10), status="completed", completed_at=at(400),
            home_score=5, away_score=3,
        ))
        session.add(Event(
            id=LIVE, sport_id=S_ID, home_team_name="Home Live", away_team_name="Away Live",
            commence_time=now - dt.timedelta(hours=1), status="live",
            win_probability_sources={"kalshi": {"value": 0.62, "updated_at": now.isoformat()}},
        ))
        await session.flush()
        rows = {
            # name: (minute, home, game_state, extra columns)
            "raw_keeper": (0, 0.60, _gs(), {}),
            "raw_merged": (1, 0.60, _gs(), {}),
            "raw_gap": (120, 0.61, _gs(), {}),
            "legacy": (200, 0.62, _gs(), {"reading_count": 120, "valid_until": at(320)}),
            "foreign": (330, 0.63, _gs(evidence_span={
                **SPAN_OK, "contract": "7878.v0", "covered_through": "2099-01-01T00:00:00.000000Z"}), {}),
            "candle": (340, 0.64, {"market_id": 555, "outcome_name": "Home",
                                   "poll_type": "history_backfill", "backfill_source": "kalshi_candlesticks"}, {}),
            "clob": (350, 0.65, {"market_id": 555, "backfill": True}, {}),
            "last_stored": (360, 0.66, _gs(), {}),
        }
        ids = {}
        for n, (name, (minute, home, state, extra)) in enumerate(rows.items()):
            snap = WinProbSnapshot(
                id=SNAP_BASE + n, event_id=FINISHED, source="kalshi", captured_at=at(minute),
                home_win_probability=home, away_win_probability=round(1 - home, 4),
                game_state=state, reading_count=extra.get("reading_count", 1),
                valid_until=extra.get("valid_until"),
            )
            session.add(snap)
            await session.flush()
            ids[name] = snap.id
        live_stamp = (now - dt.timedelta(minutes=9)).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
        session.add(WinProbSnapshot(
            id=SNAP_BASE + 50, event_id=LIVE, source="kalshi",
            captured_at=now - dt.timedelta(minutes=10),
            home_win_probability=0.62, away_win_probability=0.38,
            game_state=_gs(evidence_span={**SPAN_OK, "covered_through": live_stamp}),
            reading_count=1,
        ))
        await session.commit()
    return base, ids


async def _collapse(engine, event_id):
    from app.tasks.retention import _TABLE_CONFIG, _collapse_partition_sql

    async with AsyncSession(engine) as session:
        out = await _collapse_partition_sql(
            session, _TABLE_CONFIG["winprob"], event_id,
            dt.datetime.now(UTC) - dt.timedelta(hours=48),
        )
        await session.commit()
    return out


def _at(base, minute):
    return base + dt.timedelta(minutes=minute)


def _ts(point):
    return dt.datetime.fromisoformat(point["timestamp"])


BULK = {"market_id", "market_name", "outcome_name", "poll_type", "yes_probability",
        "backfill", "backfill_source", "evidence_span", "final"}


async def test_the_finished_game_serves_every_kind_across_the_route(pg_engine, client):
    base, ids = await _seed(pg_engine)
    assert await _collapse(pg_engine, FINISHED) == (1, 1), "only raw_keeper/raw_merged may merge"

    resp = await client.get(f"/api/events/{FINISHED}/history?hours=168&range=all")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["evidence_contract"] == {"v": "7878.v1", "resolution_s": 300}
    series = body["win_prob_history"]["kalshi"]
    by_minute = {}
    for p in series:
        minute = round((_ts(p) - base).total_seconds() / 60)
        by_minute.setdefault(minute, []).append(p)

    keeper = by_minute[0][0]
    assert keeper["evidence"] == {"kind": "observed",
                                  "covered_through": _at(base, 1).isoformat()}, keeper
    assert 1 not in by_minute, "the merged reading is gone"
    for plain in (120, 200, 330):  # raw gap, legacy compacted, foreign stamp
        assert "evidence" not in by_minute[plain][0], (plain, by_minute[plain][0])
    assert by_minute[340][0]["evidence"] == {"kind": "candle"}
    assert by_minute[350][0]["evidence"] == {"kind": "price_history"}
    assert by_minute[360][0]["evidence"] == {"kind": "terminal_row"}
    finals = [p for p in series if (p.get("evidence") or {}).get("kind") == "final"]
    assert len(finals) == 1, [p.get("evidence") for p in series]

    # #6546's reduction stands: no provenance or stamp key reaches the wire.
    for p in series:
        assert not (set(p.get("game_state") or {}) & BULK), p["game_state"]


async def test_a_live_edge_does_not_carry_the_span_it_copied(pg_engine, client):
    await _seed(pg_engine)
    resp = await client.get(f"/api/events/{LIVE}/history?hours=48&range=all")
    assert resp.status_code == 200, resp.text
    series = resp.json()["win_prob_history"]["kalshi"]
    assert series[0]["evidence"]["kind"] == "observed", series[0]
    edges = [p for p in series if p.get("live_edge")]
    assert len(edges) == 1, series
    assert edges[0]["evidence"] == {"kind": "live_edge"}
    assert "covered_through" not in edges[0]["evidence"]
