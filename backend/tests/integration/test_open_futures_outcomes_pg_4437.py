"""#4437 Decide 89-A on real Postgres: the copy's maintainer and its readers.

THE SHIP. "chi" and "mid" match outcome names over `open_futures_outcomes`
(open markets only) instead of `futures_outcomes`, and the dropdown and the
Search page answer exactly as they did. These run the real maintainer SQL and
the real routes against a real schema, then compare each route's answer with
the copy against its answer without it.

    SEARCH_TEST_DATABASE_URL=postgresql+asyncpg://localhost/bl_oo_4437 \\
        python3 -m pytest tests/integration/test_open_futures_outcomes_pg_4437.py -v
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the #4437 open-outcomes real-Postgres gate",
    ),
    pytest.mark.asyncio,
]


class _FakeRedis:
    def __init__(self):
        self.data: dict[str, str] = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    def setex(self, key, ttl, value):
        self.data[key] = value
        return True

    def delete(self, key):
        self.data.pop(key, None)
        return 1


@pytest.fixture
async def rig():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401  — registers every table on Base
    import app.services.database as database
    from app.models.models import FuturesMarket, FuturesOutcome, Sport
    from app.services.database import Base
    from app.utils import open_futures_outcomes as reader

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with maker() as s:
        nfl = Sport(key="americanfootball_nfl", name="NFL")
        s.add(nfl)
        await s.flush()

        def market(name, status="open", **kw):
            m = FuturesMarket(
                source="kalshi",
                external_id=f"K-{name}",
                name=name,
                market_type="championship",
                status=status,
                sport_id=nfl.id,
                market_tier=1,
                resolution_date=now + timedelta(days=60),
                **kw,
            )
            s.add(m)
            return m

        title = market("Pro Football Champion 2027")
        cubs = market("World Series 2025", status="closed")
        award = market("Rookie of the Year")
        await s.flush()
        for m, names in (
            (title, ["Chicago Bears", "Kansas City Chiefs", "Midland Rockhounds"]),
            (cubs, ["Chicago Cubs"]),
            (award, ["Chiara Rossi", "Ben Midgley"]),
        ):
            for i, n in enumerate(names):
                s.add(
                    FuturesOutcome(
                        market_id=m.id,
                        external_id=f"{m.external_id}:{i}",
                        name=n,
                        current_probability=0.2,
                    )
                )
        await s.commit()
        ids = {"title": title.id, "cubs": cubs.id, "award": award.id, "sport": nfl.id}

    fake = _FakeRedis()

    def _fresh_reader():
        reader._memo["at"] = None

    with patch("app.tasks.redis_state.get_redis_client", return_value=fake), patch.object(
        database, "async_session_maker", maker
    ):
        _fresh_reader()
        yield {"maker": maker, "ids": ids, "redis": fake, "fresh": _fresh_reader, "now": now}
    reader._memo["at"] = None
    await engine.dispose()


async def _pass(rig, **kw):
    from app.tasks.open_futures_outcomes import _refresh_open_futures_outcomes

    out = await _refresh_open_futures_outcomes(**kw)
    rig["fresh"]()
    return out


async def _copy_rows(rig):
    from sqlalchemy import text

    async with rig["maker"]() as s:
        return sorted(
            (r.market_id, r.name)
            for r in (await s.execute(text("SELECT market_id, name FROM open_futures_outcomes"))).all()
        )


async def _matched(rig, term):
    from sqlalchemy import select

    from app.models.models import FuturesOutcome
    from app.routes.events import _outcome_market_ids

    async with rig["maker"]() as s:
        stmt = _outcome_market_ids(FuturesOutcome.name.ilike(f"%{term}%"))
        return sorted(set((await s.execute(select(stmt.subquery()))).scalars().all()))


async def test_the_first_pass_fills_open_markets_only_and_says_so(rig):
    out = await _pass(rig)
    assert out["terminal"] == "complete" and out["cycle_complete"] is True
    ids = rig["ids"]
    rows = await _copy_rows(rig)
    assert {m for m, _ in rows} == {ids["title"], ids["award"]}
    assert (ids["cubs"], "Chicago Cubs") not in rows


async def test_with_no_state_the_lookup_is_the_original(rig):
    from app.utils.open_futures_outcomes import open_outcomes_floor

    assert open_outcomes_floor() is None
    # The original reads every market's outcomes, closed ones included.
    assert rig["ids"]["cubs"] in await _matched(rig, "chi")


async def test_the_copy_answers_and_misses_no_new_outcome(rig):
    from app.models.models import FuturesOutcome

    await _pass(rig)
    ids = rig["ids"]
    assert await _matched(rig, "chi") == sorted([ids["title"], ids["award"]])
    # An outcome written AFTER the pass, on an open market: read directly,
    # above the reader floor, before any pass has copied it.
    async with rig["maker"]() as s:
        s.add(FuturesOutcome(market_id=ids["award"], external_id="late", name="Chimamanda Adichie"))
        await s.commit()
    assert "Chimamanda" not in str(await _copy_rows(rig))
    async with rig["maker"]() as s:
        from sqlalchemy import select

        from app.routes.events import _outcome_market_ids

        stmt = _outcome_market_ids(FuturesOutcome.name.ilike("%chimamanda%"))
        assert (await s.execute(select(stmt.subquery()))).scalars().all() == [ids["award"]]


async def test_a_closed_market_leaves_the_copy_on_the_next_pass(rig):
    from sqlalchemy import update

    from app.models.models import FuturesMarket

    await _pass(rig)
    async with rig["maker"]() as s:
        await s.execute(
            update(FuturesMarket).where(FuturesMarket.id == rig["ids"]["award"]).values(status="closed")
        )
        await s.commit()
    await _pass(rig)
    assert {m for m, _ in await _copy_rows(rig)} == {rig["ids"]["title"]}


async def test_a_renamed_outcome_is_reconciled_within_one_rotation(rig):
    from sqlalchemy import update

    from app.models.models import FuturesOutcome
    from app.tasks.open_futures_outcomes import SLICES

    await _pass(rig)
    async with rig["maker"]() as s:
        await s.execute(
            update(FuturesOutcome).where(FuturesOutcome.name == "Chicago Bears").values(name="Bears")
        )
        await s.commit()
    for _ in range(SLICES):
        await _pass(rig)
    names = [n for _, n in await _copy_rows(rig)]
    assert "Bears" in names and "Chicago Bears" not in names


async def test_a_stale_state_is_not_read(rig):
    import json

    from app.utils.open_futures_outcomes import STALE_AFTER_SECONDS, STATE_KEY, open_outcomes_floor

    await _pass(rig)
    assert open_outcomes_floor() is not None
    state = json.loads(rig["redis"].data[STATE_KEY])
    state["pass_at"] -= STALE_AFTER_SECONDS + 1
    rig["redis"].data[STATE_KEY] = json.dumps(state)
    rig["fresh"]()
    assert open_outcomes_floor() is None


async def test_a_partial_first_fill_is_not_read_and_resumes(rig):
    from app.utils.open_futures_outcomes import open_outcomes_floor

    out = await _pass(rig, budget_seconds=0)
    assert out["terminal"] == "partial" and out["cycle_complete"] is False
    assert open_outcomes_floor() is None
    out = await _pass(rig)
    assert out["cycle_complete"] is True and open_outcomes_floor() is not None


async def test_both_routes_answer_the_same_with_the_copy(rig):
    """The ship's own check: what a reader sees is unchanged, only how it is read."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from app.services.database import get_db, get_db_rw

    async def _override():
        async with rig["maker"]() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override

    def _futures(path, body):
        if path == "typeahead":
            return sorted(
                (r.get("market_id") or r.get("id"), r.get("type"))
                for r in body.get("suggestions", [])
                if r.get("type") in ("futures", "market", "future")
            )
        return sorted(f.get("id") for f in body.get("futures", []))

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

            async def _ask(path, q):
                r = await client.get(f"/api/events/{path}", params={"q": q, "debug_timing": 1})
                assert r.status_code == 200, (path, q, r.status_code)
                return _futures(path, r.json())

            import app.routes.events as events_mod
            from app.utils.open_futures_outcomes import STATE_KEY, open_outcomes_floor

            terms = ("chi", "mid", "chicago", "rossi")
            before = {(p, q): await _ask(p, q) for p in ("typeahead", "search") for q in terms}
            await _pass(rig)
            # Nothing a route cached may answer the second round.
            rig["redis"].data = {k: v for k, v in rig["redis"].data.items() if k == STATE_KEY}
            assert open_outcomes_floor() is not None
            served = []
            real = events_mod.market_ids_with_outcome

            def _spy(*a, **k):
                out = real(*a, **k)
                served.append(out is not None)
                return out

            with patch.object(events_mod, "market_ids_with_outcome", _spy):
                after = {(p, q): await _ask(p, q) for p in ("typeahead", "search") for q in terms}
    finally:
        app.dependency_overrides.clear()
    assert any(served), "CONTROL: no lookup read the copy, so this compared the original with itself"
    assert after == before
    assert any(before.values()), "CONTROL: the routes returned no futures at all"
