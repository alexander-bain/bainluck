"""The "Biggest Movers" strip stops being cold on every open. LAT-P115.

WHY THIS FILE EXISTS.

`GET /api/futures/movers?hours=24&limit=10` is the iOS Futures tab's Biggest
Movers strip (`Views/FuturesListView.swift:51` ->
`FuturesListViewModel.loadMovers`). LAT-P108 took its cold build from 11,129 ms
to sub-second and cached it for 60 s. It never gave it a warmer, so on a site
with no steady traffic the 60 s window is almost always expired and the strip is
cold essentially every time anyone opens the tab. Measured on production slug
`b8ee7e14`, 2026-08-29: **1,404 ms cold, 16-20 ms warm, cold again a minute
later** — two independent cold hits ten minutes apart.

`update_max_movement` already runs every ten minutes and already computes the
column the answer is RANKED by, so it publishes the answer now. The route is
otherwise untouched: same key, same payload, same 60 s on its own writes.

WHAT THIS FILE ASSERTS, AND WHY EACH ONE IS HERE.

1. **The warmer writes the key the route READS.** This is the whole failure mode
   of a warmer and it is invisible from either side alone: a producer that mints
   `movers:24:0010` while the consumer reads `movers:24:10` warms nothing,
   raises nothing and reports success. `test_a_warmed_shape_is_served_without_
   touching_the_database` proves the two agree by making the database FATAL on
   the read path — the only way to be sure the hit came from the warm entry and
   not from a rebuild that happened to be fast.
2. **The warmed bytes are the served bytes.** `build_and_cache_movers` was
   extracted rather than copied precisely so this cannot drift; the guard pins
   that it stayed extracted, and `test_the_payload_is_spelled_exactly_once`
   fails if a second copy of the dict appears.
3. **The declared shape is the shape the shipped client actually asks for.**
   Read out of the iOS source, not hard-coded twice. This is the gate P114-1
   said was missing between two vocabularies maintained in two places — if
   `loadMovers` starts asking for a different limit, the warmer is warming a key
   nobody reads and this fails instead of going quietly cold.
4. **A pass that warmed nothing reads `failed`, never green** (gotcha #53), and
   one bad shape does not wipe the pass (gotcha #42).
5. **The warmer can never fail the column update.** `update_max_movement`'s job
   is the column; the cache write is a passenger.
6. **The two TTLs stay different on purpose** — a reader's 60 s and a producer's
   30 min answer different questions, and collapsing them is how the strip goes
   cold through `background`'s measured delivery jitter.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, FuturesMarket, FuturesOutcome  # noqa: E402
from app.routes import futures as futures_routes  # noqa: E402
from app.routes.futures import (  # noqa: E402
    MOVERS_ROUTE_TTL_SECONDS,
    get_futures_movers,
    movers_cache_key,
)
from app.tasks import futures_movers_warm as warm_mod  # noqa: E402
from app.tasks.futures_movers_warm import (  # noqa: E402
    PER_SHAPE_TIMEOUT_SECONDS,
    WARM_TTL_SECONDS,
    WARMED_MOVERS_SHAPES,
    warm_futures_movers,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
IOS_VIEWMODEL = (
    REPO_ROOT
    / "ios"
    / "Bain Luck"
    / "Bain Luck"
    / "ViewModels"
    / "FuturesListViewModel.swift"
)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


class FakeRedis:
    """Dict-backed Redis double that RECORDS TTLs.

    The TTL is the point of half this file, so a double that accepts `setex` and
    throws the expiry away would make those assertions vacuous.
    """

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value
        self.ttls[key] = ttl


class AsyncDB:
    """Minimal async facade over a sync Session.

    `build_and_cache_movers` awaits exactly one thing — `db.execute(query)` — so
    this shim exercises the real query builder against a real (SQLite) database
    rather than mocking the answer. `fatal` turns any read into a failure, which
    is how a cache HIT is distinguished from a fast rebuild.
    """

    def __init__(self, session: Session, *, fatal: bool = False):
        self._session = session
        self.fatal = fatal
        self.calls = 0

    async def execute(self, query):
        self.calls += 1
        if self.fatal:
            raise AssertionError(
                "the database was read on what must have been a cache hit"
            )
        return self._session.execute(query)


def _market(mid: int, max_movement) -> FuturesMarket:
    return FuturesMarket(
        id=mid,
        source="kalshi",
        external_id=f"MKT-{mid}",
        name=f"market {mid}",
        status="open",
        max_movement_24h=max_movement,
    )


def _outcome(oid: int, mid: int, change) -> FuturesOutcome:
    return FuturesOutcome(
        id=oid,
        market_id=mid,
        external_id=f"OUT-{oid}",
        name=f"outcome {oid}",
        current_probability=0.5,
        probability_change_24h=change,
    )


@pytest.fixture()
def session():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(
        eng, tables=[FuturesMarket.__table__, FuturesOutcome.__table__]
    )
    s = Session(eng)
    for mid in range(1, 13):
        change = round(0.90 - 0.05 * mid, 4)
        s.add(_market(mid, abs(change)))
        s.add(_outcome(mid * 1000, mid, change))
    s.commit()
    return s


@pytest.fixture()
def rc():
    return FakeRedis()


def _route(db, rc_, monkeypatch, *, hours=24, limit=10):
    """Call the real route handler with `rc_` as its Redis client."""
    import app.tasks.redis_state as redis_state

    monkeypatch.setattr(redis_state, "get_redis_client", lambda: rc_)
    return asyncio.run(get_futures_movers(hours=hours, limit=limit, db=db))


# --------------------------------------------------------------------------
# 1 — the warmer writes the key the route reads
# --------------------------------------------------------------------------


def test_a_warmed_shape_is_served_without_touching_the_database(
    session, rc, monkeypatch
):
    """The one assertion that catches a key-format drift, from end to end."""
    hours, limit = WARMED_MOVERS_SHAPES[0]
    summary = asyncio.run(warm_futures_movers(AsyncDB(session), rc))
    assert summary["terminal"] == "complete"

    # FATAL database: if the route rebuilds instead of reading the warm entry,
    # this raises rather than quietly passing on a fast rebuild.
    served = _route(
        AsyncDB(session, fatal=True), rc, monkeypatch, hours=hours, limit=limit
    )

    assert served["movers"], "the warmed payload must not be empty"
    assert served == json.loads(rc.store[movers_cache_key(hours, limit)])


def test_the_warmer_writes_exactly_the_declared_shapes(session, rc):
    asyncio.run(warm_futures_movers(AsyncDB(session), rc))
    assert set(rc.store) == {movers_cache_key(h, n) for h, n in WARMED_MOVERS_SHAPES}


# --------------------------------------------------------------------------
# 2 — the warmed bytes ARE the served bytes
# --------------------------------------------------------------------------


def test_the_warmed_payload_equals_the_cold_built_payload(session, rc, monkeypatch):
    hours, limit = WARMED_MOVERS_SHAPES[0]

    cold = _route(AsyncDB(session), FakeRedis(), monkeypatch, hours=hours, limit=limit)
    asyncio.run(warm_futures_movers(AsyncDB(session), rc))
    warmed = json.loads(rc.store[movers_cache_key(hours, limit)])

    assert warmed == json.loads(json.dumps(cold, default=str))


def test_the_payload_is_spelled_exactly_once():
    """A second copy of the dict is the drift this extraction exists to prevent.

    `timeframe_hours` is the canary because it is the field a re-implementation
    is most likely to omit — and omitting it throws on decode in every shipped
    iOS build (`Models/SearchModels.swift:146` types it non-optional).
    """
    src = inspect.getsource(futures_routes)
    assert src.count('"timeframe_hours":') == 1

    warm_src = inspect.getsource(warm_mod)
    assert '"timeframe_hours"' not in warm_src
    assert "build_and_cache_movers" in warm_src


def test_the_route_still_calls_the_shared_builder():
    """A guard that exercises only the helper stays green if the route stops
    calling it — LAT-P108's lesson, restated for the warm path."""
    assert "build_and_cache_movers" in inspect.getsource(get_futures_movers)


# --------------------------------------------------------------------------
# 3 — the declared shape is the shape the shipped client asks for
# --------------------------------------------------------------------------


def test_the_declared_shape_matches_what_shipped_ios_requests():
    """Read out of the iOS source rather than written down twice.

    P114-1 found two vocabularies maintained in two places with no gate holding
    them together, and the page went quietly wrong. This is that gate for this
    surface: if `loadMovers` changes its ask, the warmer is warming a key nobody
    reads, and that must be a red test rather than a silent return to cold.
    """
    src = IOS_VIEWMODEL.read_text()
    m = re.search(r"fetchFuturesMovers\(hours:\s*(\d+),\s*limit:\s*(\d+)\)", src)
    assert m, f"could not find the movers call in {IOS_VIEWMODEL}"

    asked = (int(m.group(1)), int(m.group(2)))
    assert asked in WARMED_MOVERS_SHAPES, (
        f"shipped iOS asks for {asked} but the warmer warms "
        f"{WARMED_MOVERS_SHAPES} — the strip is cold on every open"
    )


def test_the_shape_list_is_a_frozen_literal_not_a_range():
    assert isinstance(WARMED_MOVERS_SHAPES, tuple)
    assert all(isinstance(s, tuple) and len(s) == 2 for s in WARMED_MOVERS_SHAPES)


# --------------------------------------------------------------------------
# 4 — a pass that warmed nothing must not read green
# --------------------------------------------------------------------------


def test_a_pass_that_warms_nothing_reports_failed(session, rc, monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("build exploded")

    monkeypatch.setattr(warm_mod, "build_and_cache_movers", _boom, raising=False)
    monkeypatch.setattr("app.routes.futures.build_and_cache_movers", _boom)

    summary = asyncio.run(warm_futures_movers(AsyncDB(session), rc))

    assert summary["terminal"] == "failed"
    assert summary["completed"] == 0
    assert summary["errors"]
    assert rc.store == {}


def test_one_bad_shape_does_not_wipe_the_pass(session, rc, monkeypatch):
    """gotcha #42 — the healthy sibling must survive."""
    good = (24, 10)
    bad = (24, 11)
    monkeypatch.setattr(warm_mod, "WARMED_MOVERS_SHAPES", (bad, good))

    real = futures_routes.build_and_cache_movers

    async def _selective(hours, limit, db, redis=None, *, ttl=60):
        if limit == bad[1]:
            raise RuntimeError("this shape is broken")
        return await real(hours, limit, db, redis, ttl=ttl)

    monkeypatch.setattr("app.routes.futures.build_and_cache_movers", _selective)

    summary = asyncio.run(warm_futures_movers(AsyncDB(session), rc))

    assert summary["terminal"] == "partial"
    assert summary["completed"] == 1
    assert list(rc.store) == [movers_cache_key(*good)]


def test_the_warmer_never_raises(session, rc, monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("build exploded")

    monkeypatch.setattr("app.routes.futures.build_and_cache_movers", _boom)
    asyncio.run(warm_futures_movers(AsyncDB(session), rc))  # must not raise


# --------------------------------------------------------------------------
# 5 — the warmer can never fail the column update
# --------------------------------------------------------------------------


def test_the_column_update_guards_its_warm_call():
    """The warm is a passenger on `update_max_movement`, not part of its job."""
    import app.tasks as tasks_mod

    src = inspect.getsource(tasks_mod.update_max_movement)
    assert "warm_futures_movers" in src
    # The commit must come BEFORE the warm: a cache write must not be able to
    # roll back the column this task exists to maintain.
    assert src.index("await session.commit()") < src.index("warm_futures_movers")
    assert "except Exception" in src


# --------------------------------------------------------------------------
# 6 — the two TTLs answer different questions
# --------------------------------------------------------------------------


def test_the_route_keeps_lat_p108s_sixty_seconds(session, rc, monkeypatch):
    hours, limit = 24, 10
    _route(AsyncDB(session), rc, monkeypatch, hours=hours, limit=limit)
    assert rc.ttls[movers_cache_key(hours, limit)] == MOVERS_ROUTE_TTL_SECONDS == 60


def test_the_warmer_writes_the_long_ttl(session, rc):
    asyncio.run(warm_futures_movers(AsyncDB(session), rc))
    for hours, limit in WARMED_MOVERS_SHAPES:
        assert rc.ttls[movers_cache_key(hours, limit)] == WARM_TTL_SECONDS


def test_the_warm_ttl_covers_several_producer_deliveries():
    """Read the producer's period off the beat schedule, not off a magic number.

    `background` delivered p50 138-152 s against a declared 120 s and a max of
    2,511 s when LAT-P112 measured it, so a TTL at one beat period would uncover
    the strip on every late delivery.
    """
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["update-max-movement"]
    minutes = sorted(entry["schedule"].minute)
    period_s = (minutes[1] - minutes[0]) * 60

    assert period_s == 600
    assert WARM_TTL_SECONDS >= 3 * period_s


def test_the_two_ttls_are_not_the_same_number():
    assert WARM_TTL_SECONDS != MOVERS_ROUTE_TTL_SECONDS


# --------------------------------------------------------------------------
# 7 — the inner operation is bounded inside the CALLER's budget
# --------------------------------------------------------------------------


def test_the_warm_pass_fits_inside_the_column_updates_budget():
    """Added because mutant M7 SURVIVED the first battery.

    Nothing here pinned `PER_SHAPE_TIMEOUT_SECONDS` to anything, so raising it to
    100,000 s passed every other assertion in this file. That is not a
    theoretical hole: `update_max_movement` carries `soft_time_limit=120`, and a
    warm that can outlast it converts a slow cache write into a SIGKILL of the
    column update — which is recorded as `no_data` rather than as a failure
    (project_celery_sigkill_untracked), so the task that maintains
    `max_movement_24h` would stop running and nothing would say so.

    The caller's budget is READ off the task, not written down twice: if someone
    lowers `soft_time_limit`, this fails instead of silently going out of bounds.
    """
    from app.tasks import celery_app, update_max_movement

    soft = update_max_movement.soft_time_limit
    assert soft, "update_max_movement must declare a soft_time_limit"
    assert celery_app  # the task is registered, not a bare function

    worst_case = PER_SHAPE_TIMEOUT_SECONDS * len(WARMED_MOVERS_SHAPES)

    # Half the caller's budget: the column UPDATE is that task's actual job and
    # must keep the larger share. The warm is a passenger.
    assert worst_case * 2 <= soft, (
        f"a worst-case warm pass is {worst_case}s against a "
        f"soft_time_limit of {soft}s — the passenger can starve the driver"
    )
