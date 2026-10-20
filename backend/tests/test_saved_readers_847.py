"""#847 — the Correctness Console's matured-linkage and Source Intelligence readers,
served from saved evidence ONLY.

PILLAR: TRUTH. SHIP: the Correctness Console can show Source Intelligence and
Matching evidence without launching database computations when an operator opens
a tab.

``GET /api/admin/prediction-markets/matured-linkage/cached`` reads one fixed key.
``GET /api/admin/source-intelligence/cached`` reads the primary snapshot and, only
when it is MISSING, the retained ``:stale`` copy, and says which one answered.

HOW THE BINDING WORKS. Every saved value these tests serve is the exact bytes a
REAL writer put in Redis: ``_precompute_admin_matured_linkage`` (which runs the
real ``_compute_matured_linkage`` / ``summarize_matured_linkage`` /
``_compute_unlinked_held``), ``_compute_source_intelligence`` (which runs the real
four ``_query_*`` builders), and the public route's healthy inline build. Only the
database rows under them are faked. A malformed case is one named mutation of such
a payload, and the unmutated payload is asserted to pass in the same test, so a
refusal can only come from the mutation.

Every reader path runs with the computes, the producers, the session factories,
task dispatch and every cache write wired to explode. No Redis, database or
network is reached from this file.
"""

from __future__ import annotations

import asyncio
import copy
import importlib
import inspect
import json
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.routes import admin, admin_matching as am, source_intelligence as si
from app.routes.admin_utils import admin_account_identity
from app.utils import saved_snapshot_read as ssr

TOKEN = "test-admin-token-847-saved-readers"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
ML_PATH = "/api/admin/prediction-markets/matured-linkage/cached"
SI_PATH = "/api/admin/source-intelligence/cached"
ML_KEY = "bainluck:admin:matured_linkage"
SI_KEY = "bainluck:source_intelligence"
SI_STALE_KEY = "bainluck:source_intelligence:stale"
T0 = datetime(2026, 10, 20, 17, 0, 0, tzinfo=timezone.utc)

ENVELOPE_KEYS = {
    "schema_version", "cache_state", "reason", "freshness", "freshness_basis",
    "served_key", "served_from", "saved_bytes", "max_saved_bytes",
    "generated_at", "age_seconds", "payload",
}


# ---------------------------------------------------------------------------
# Producer side: fake rows under the REAL writers
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class FakeSession:
    """Answers each producer statement by what it selects; records every statement."""

    def __init__(self, router):
        self.router = router
        self.statements: list[str] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.statements.append(sql)
        if "SET LOCAL" in sql:
            return None
        return _Result(self.router(sql, params))


def _session_factory(router, sessions):
    @asynccontextmanager
    async def _get_task_session():
        session = FakeSession(router)
        sessions.append(session)
        yield session

    return _get_task_session


class RecordingRedis:
    """What a producer writes, byte for byte."""

    def __init__(self):
        self.store: dict = {}
        self.sets: list = []

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.sets.append((key, ex))
        self.store[key] = value


def _ns(**kw):
    return SimpleNamespace(**kw)


COMMENCE = T0 + timedelta(hours=2)


def _blend_row(event_id, source, linked, sport="baseball_mlb",
               matchup="Milwaukee Brewers @ New York Mets"):
    return _ns(event_id=event_id, sport_key=sport, matchup=matchup,
               commence_time=COMMENCE, source=source, linked=linked)


DEFAULT_BLEND = [
    _blend_row(101, "kalshi", True),
    _blend_row(101, "polymarket", False),
    _blend_row(102, "kalshi", True, sport="basketball_nba", matchup="Celtics @ 76ers"),
    _blend_row(103, "polymarket", False, sport="americanfootball_nfl", matchup="Bills @ Chiefs"),
]
DEFAULT_IMMINENT = [
    _ns(id=101, sport_key="baseball_mlb", home="New York Mets", away="Milwaukee Brewers",
        matchup="Milwaukee Brewers @ New York Mets", commence_time=COMMENCE),
]
DEFAULT_CANDIDATES = [
    _ns(id=9001, name="New York Mets vs. Milwaukee Brewers", external_id=None,
        source="polymarket", llm_sport_category="baseball_mlb"),
    _ns(id=9002, name="New York Mets vs. Milwaukee Brewers - Player Props", external_id=None,
        source="polymarket", llm_sport_category="baseball_mlb"),
]


def produce_matured_linkage(blend=DEFAULT_BLEND, imminent=DEFAULT_IMMINENT,
                            candidates=DEFAULT_CANDIDATES, held_error=None) -> bytes:
    """Run the REAL ``_precompute_admin_matured_linkage``; return the bytes it SET."""
    from app.tasks import precompute_admin_health as pah

    def router(sql, params):
        if "blend_pairs" in sql:
            return blend
        if "home_team_name AS home" in sql:
            return imminent
        if "futures_markets" in sql:
            if held_error:
                raise held_error
            return candidates
        raise AssertionError(f"unexpected producer statement: {sql[:80]}")

    redis = RecordingRedis()
    sessions: list = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.tasks.base.get_task_session", _session_factory(router, sessions))
        mp.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: redis)
        asyncio.run(pah._precompute_admin_matured_linkage())
    assert redis.sets == [(ML_KEY, 3600)]
    raw = redis.store[ML_KEY]
    return raw.encode() if isinstance(raw, str) else raw


def _series_rows(sources, n, base=0.4, step=0.0005, extra=()):
    rows = []
    for s_idx, src in enumerate(sources):
        for i in range(n):
            rows.append(_ns(source=src, captured_at=COMMENCE + timedelta(seconds=30 * i),
                            home_win_probability=base + s_idx * 0.05 + step * (i % 40)))
    rows.extend(extra)
    return rows


def _si_router(n_case_studies=2, series_sources=("espn", "kalshi", "polymarket"),
               points=40, series_extra=()):
    peaks = [
        _ns(event_id=500 + i, max_div=0.21 - i * 0.01, min_pair_snaps=points,
            home_team_name=f"Home {i}", away_team_name=None if i == 1 else f"Away {i}",
            sport="baseball_mlb", home_score=5, away_score=3 + (i % 3),
            commence_time=COMMENCE - timedelta(days=i + 1),
            completed_at=COMMENCE - timedelta(days=i + 1) + timedelta(hours=3))
        for i in range(n_case_studies)
    ]

    def router(sql, params):
        if "AS espn" in sql:
            return [
                _ns(sport="baseball_mlb", total=40, betting=38, espn=30, stat_model=25,
                    kalshi=20, polymarket=18, mlb=36),
                _ns(sport="basketball_nba", total=12, betting=12, espn=10, stat_model=0,
                    kalshi=8, polymarket=6, mlb=0),
            ]
        if "AS source_count" in sql:
            return [_ns(sources=2, events=10), _ns(sources=3, events=22), _ns(sources=5, events=20)]
        if "AS brier_var" in sql:
            return [
                _ns(source="betting", idx=3, n=20, avg_prob=0.351, winners=7, mae=0.42,
                    brier=0.21, brier_var=0.01),
                _ns(source="betting", idx=7, n=30, avg_prob=0.729, winners=22, mae=0.31,
                    brier=0.18, brier_var=0.02),
                _ns(source="kalshi", idx=9, n=1, avg_prob=0.95, winners=1, mae=0.05,
                    brier=0.0025, brier_var=None),
            ]
        if "AS disagree_5pp" in sql:
            return [
                _ns(source_a="betting", source_b="kalshi", sport="baseball_mlb", comparisons=40,
                    disagree_5pp=14, disagree_10pp=5, disagree_20pp=1, avg_divergence=0.08,
                    a_closer=8, b_closer=6),
                _ns(source_a="espn", source_b="mlb", sport="baseball_mlb", comparisons=30,
                    disagree_5pp=3, disagree_10pp=0, disagree_20pp=0, avg_divergence=0.06,
                    a_closer=0, b_closer=0),
            ]
        if "event_divergence" in sql:
            return peaks
        if "SELECT source, captured_at, home_win_probability" in sql:
            return _series_rows(series_sources, points, extra=series_extra)
        raise AssertionError(f"unexpected producer statement: {sql[:80]}")

    return router


def produce_source_intelligence(**router_kw) -> dict:
    """Run the REAL ``_compute_source_intelligence``; return both keys' bytes."""
    # The package attribute of this name is the Celery task; take the module.
    psi = importlib.import_module("app.tasks.precompute_source_intelligence")

    redis = RecordingRedis()
    sessions: list = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.tasks.base.get_task_session",
                   _session_factory(_si_router(**router_kw), sessions))
        mp.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: redis)
        result = asyncio.run(psi._compute_source_intelligence())
    assert result["status"] == "ok", result
    assert [k for k, _ in redis.sets] == [SI_KEY, SI_STALE_KEY]
    assert redis.store[SI_KEY] == redis.store[SI_STALE_KEY]
    return {k: (v.encode() if isinstance(v, str) else v) for k, v in redis.store.items()}


def produce_si_via_public_inline_build() -> dict:
    """The other writer: a healthy inline build of ``GET /api/source-intelligence``."""
    redis = RecordingRedis()
    session = FakeSession(_si_router())
    prev = dict(si._cache)
    try:
        si._cache["data"], si._cache["timestamp"] = None, 0
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: redis)
            asyncio.run(si.source_intelligence(refresh=True, db=session))
    finally:
        si._cache.clear()
        si._cache.update(prev)
    assert [k for k, _ in redis.sets] == [SI_KEY, SI_STALE_KEY]
    return {k: (v.encode() if isinstance(v, str) else v) for k, v in redis.store.items()}


def _restamp(raw: bytes, generated_at: datetime) -> bytes:
    doc = json.loads(raw)
    doc["generated_at"] = generated_at.isoformat()
    return json.dumps(doc).encode()


# Producer runs happen ONCE, before any reader poison is armed (module scope is
# set up before function scope).


@pytest.fixture(scope="module")
def ml_raw():
    return produce_matured_linkage()


@pytest.fixture(scope="module")
def ml_empty_raw():
    return produce_matured_linkage(blend=[], imminent=[], candidates=[])


@pytest.fixture(scope="module")
def ml_held_error_raw():
    return produce_matured_linkage(held_error=RuntimeError("canceling statement due to timeout"))


@pytest.fixture(scope="module")
def si_raw():
    return produce_source_intelligence()


@pytest.fixture(scope="module")
def si_large_raw():
    return produce_source_intelligence(
        n_case_studies=5,
        series_sources=("betting", "espn", "kalshi", "mlb", "polymarket", "stat_model"),
        points=1500,
    )


@pytest.fixture(scope="module")
def si_unbounded_raw():
    # The series query filters only IS NOT NULL: endpoint and past-the-end values
    # reach the saved payload untouched.
    extra = tuple(_ns(source="espn", captured_at=COMMENCE + timedelta(hours=2, seconds=i),
                      home_win_probability=p)
                  for i, p in enumerate((0.0, 1.0, 1.0004)))
    return produce_source_intelligence(series_extra=extra)


@pytest.fixture(scope="module")
def si_inline_raw():
    return produce_si_via_public_inline_build()


# ---------------------------------------------------------------------------
# Reader side
# ---------------------------------------------------------------------------


class ReaderRedis:
    """A cache the saved-only readers may GET and must never write."""

    def __init__(self, store=None, *, get_exc=None, block_on=None):
        self.store = dict(store or {})
        self.get_exc = get_exc
        self.block_on = block_on or {}
        self.gets: list[str] = []

    def get(self, key):
        self.gets.append(key)
        if key in self.block_on:
            self.block_on[key].wait(0.5)
        if self.get_exc:
            raise self.get_exc
        return self.store.get(key)

    def _write(self, *a, **k):
        raise AssertionError("a saved-only reader wrote the cache")

    set = setex = setnx = delete = expire = getdel = getex = mset = _write


@pytest.fixture
def poisoned(monkeypatch):
    """Everything that could compute, open a session, enqueue or write explodes."""

    def boom(name):
        def _raise(*a, **k):
            raise AssertionError(f"saved-only reader touched {name}")
        return _raise

    for name in ("_compute_matured_linkage", "_compute_unlinked_held", "_compute_link_rate"):
        monkeypatch.setattr(am, name, boom(name))
    for name in ("_query_coverage", "_query_source_accuracy", "_query_disagreements",
                 "_query_case_studies", "_set_timeout"):
        monkeypatch.setattr(si, name, boom(name))
    monkeypatch.setattr("app.tasks.precompute_admin_health._precompute_admin_matured_linkage",
                        boom("matured-linkage producer"))
    monkeypatch.setattr(importlib.import_module("app.tasks.precompute_source_intelligence"),
                        "_compute_source_intelligence", boom("source-intelligence producer"))
    monkeypatch.setattr("app.tasks.base.get_task_session", boom("get_task_session"))
    monkeypatch.setattr("app.services.database.async_session_maker", boom("async_session_maker"))
    monkeypatch.setattr("app.routes.admin_utils._safe_send_task", boom("task dispatch"))
    from app.tasks import celery_app

    monkeypatch.setattr(celery_app, "send_task", boom("celery send_task"))

    # The public route's process cache must neither answer nor be warmed.
    sentinel = {"generated_at": "2020-01-01T00:00:00+00:00", "process_cache": True}
    prev = dict(si._cache)
    si._cache["data"], si._cache["timestamp"] = sentinel, time.time()
    yield
    assert si._cache["data"] is sentinel, "a saved-only reader touched the process cache"
    si._cache.clear()
    si._cache.update(prev)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    app = FastAPI()
    # Same mount as main.py: admin.router carries admin_matching's router.
    app.include_router(admin.router, prefix="/api/admin",
                       dependencies=[Depends(admin_account_identity)])

    def _no_db():
        raise AssertionError("a saved-only reader opened a database session")

    app.dependency_overrides[am.get_db] = _no_db
    app.dependency_overrides[si.get_db] = _no_db
    return TestClient(app, raise_server_exceptions=False)


def _serve(monkeypatch, redis, now=T0):
    calls = []

    def factory(*a, **k):
        calls.append(k)
        return redis

    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", factory)
    monkeypatch.setattr(am, "_saved_reader_now", lambda: now)
    monkeypatch.setattr(si, "_si_saved_now", lambda: now)
    return calls


def _get(client, monkeypatch, path, redis, now=T0, query="", headers=AUTH):
    _serve(monkeypatch, redis, now)
    resp = client.get(path + query, headers=headers)
    return resp, resp.json()


def _ml(client, monkeypatch, value, **kw):
    redis = value if isinstance(value, ReaderRedis) else ReaderRedis({ML_KEY: value} if value is not None else {})
    resp, body = _get(client, monkeypatch, ML_PATH, redis, **kw)
    return resp, body, redis


def _si(client, monkeypatch, store, **kw):
    redis = store if isinstance(store, ReaderRedis) else ReaderRedis(store)
    resp, body = _get(client, monkeypatch, SI_PATH, redis, **kw)
    return resp, body, redis


def _generated_at(raw: bytes) -> datetime:
    return datetime.fromisoformat(json.loads(raw)["generated_at"])


# ---------------------------------------------------------------------------
# Auth comes first; neither handler has a database dependency or a work input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [ML_PATH, SI_PATH])
class TestAuth:
    def _redis(self, ml_raw, si_raw):
        return ReaderRedis({ML_KEY: ml_raw, **si_raw})

    def test_no_credentials_is_refused_before_evidence_is_read(self, client, poisoned, monkeypatch,
                                                                path, ml_raw, si_raw):
        redis = self._redis(ml_raw, si_raw)
        resp, _ = _get(client, monkeypatch, path, redis, headers={})
        assert resp.status_code == 403
        assert redis.gets == []

    def test_a_wrong_token_is_refused_before_evidence_is_read(self, client, poisoned, monkeypatch,
                                                              path, ml_raw, si_raw):
        redis = self._redis(ml_raw, si_raw)
        resp, _ = _get(client, monkeypatch, path, redis, headers={"Authorization": "Bearer nope"})
        assert resp.status_code == 403
        assert redis.gets == []

    def test_a_query_secret_alone_is_refused(self, client, poisoned, monkeypatch, path, ml_raw, si_raw):
        redis = self._redis(ml_raw, si_raw)
        resp, _ = _get(client, monkeypatch, path, redis, query=f"?secret={TOKEN}", headers={})
        assert resp.status_code == 403
        assert redis.gets == []

    def test_the_machine_token_is_served_with_no_store(self, client, poisoned, monkeypatch,
                                                       path, ml_raw, si_raw):
        redis = self._redis(ml_raw, si_raw)
        resp, body = _get(client, monkeypatch, path, redis,
                          now=_generated_at(ml_raw) + timedelta(seconds=5))
        assert resp.status_code == 200, body
        assert resp.headers["cache-control"] == "no-store"
        assert len(redis.gets) == 1

    def test_the_handler_takes_no_database_dependency_and_no_work_input(self, path):
        handler = (am.prediction_market_matured_linkage_cached if path == ML_PATH
                   else am.source_intelligence_cached)
        assert set(inspect.signature(handler).parameters) == {"request", "secret"}
        sub = path.removeprefix("/api/admin")
        route = next(r for r in am.router.routes if getattr(r, "path", "") == sub)
        assert route.methods == {"GET"}
        assert all(d.call not in (am.get_db, si.get_db) for d in route.dependant.dependencies)
        assert [p.name for p in route.dependant.query_params] == ["secret"]

    def test_the_legacy_route_still_exists_beside_it(self, client, path):
        paths = {r.path for r in client.app.routes}
        assert path in paths
        legacy = ("/api/admin/prediction-markets/matured-linkage" if path == ML_PATH
                  else None)
        if legacy:
            assert legacy in paths
        else:
            # The public Source Intelligence route lives on its own router, unchanged.
            assert any(getattr(r, "path", "") == "/source-intelligence" for r in si.router.routes)


# ---------------------------------------------------------------------------
# Matured linkage: bound to the real producer's bytes
# ---------------------------------------------------------------------------


class TestMaturedLinkageBinding:
    def test_the_producer_payload_is_served_whole_with_misses_and_unlinked_held(
            self, client, poisoned, monkeypatch, ml_raw):
        saved = json.loads(ml_raw)
        # The fixture is not vacuous: real phantoms and a real held miss exist.
        assert saved["phantom"] == 2 and len(saved["misses"]) == 2
        assert saved["unlinked_held"]["status"] == "ok"
        assert saved["unlinked_held"]["headline_unlinked_held"] == 1
        assert saved["unlinked_held"]["derivatives_excluded"] == 1

        now = _generated_at(ml_raw) + timedelta(seconds=754)
        resp, body, redis = _ml(client, monkeypatch, ml_raw, now=now)
        assert resp.status_code == 200
        assert set(body) == ENVELOPE_KEYS
        assert (body["cache_state"], body["reason"], body["freshness"]) == (
            "hit", "saved_snapshot", "unreviewed")
        assert body["payload"] == saved
        assert body["payload"]["misses"] == saved["misses"]
        assert body["payload"]["unlinked_held"]["misses"] == saved["unlinked_held"]["misses"]
        assert (body["served_key"], body["served_from"]) == (ML_KEY, "primary")
        assert body["saved_bytes"] == len(ml_raw)
        assert body["generated_at"] == saved["generated_at"]
        assert body["age_seconds"] == 754
        assert redis.gets == [ML_KEY]

    def test_a_measured_zero_slate_is_a_hit_not_a_miss(self, client, poisoned, monkeypatch,
                                                       ml_empty_raw):
        saved = json.loads(ml_empty_raw)
        assert saved["status"] == "insufficient_slate" and saved["headline_pct"] is None
        resp, body, _ = _ml(client, monkeypatch, ml_empty_raw,
                            now=_generated_at(ml_empty_raw) + timedelta(seconds=1))
        assert (resp.status_code, body["cache_state"]) == (200, "hit")
        assert body["payload"]["checkable_pairs"] == 0
        assert body["payload"]["unlinked_held"]["status"] == "insufficient_slate"

        miss_resp, miss, _ = _ml(client, monkeypatch, None)
        assert (miss_resp.status_code, miss["cache_state"], miss["payload"]) == (202, "miss", None)

    def test_the_producers_unlinked_held_error_is_served_and_named(self, client, poisoned,
                                                                   monkeypatch, ml_held_error_raw):
        saved = json.loads(ml_held_error_raw)
        assert saved["unlinked_held"]["status"] == "error"
        resp, body, _ = _ml(client, monkeypatch, ml_held_error_raw,
                            now=_generated_at(ml_held_error_raw) + timedelta(seconds=1))
        assert (resp.status_code, body["cache_state"], body["reason"]) == (
            200, "hit", "saved_snapshot_with_unlinked_held_error")
        assert body["payload"] == saved


def _ops_substitute(doc):
    # What ``/ops-snapshot``'s compaction turns the payload into.
    return admin._ops_compact(doc)


ML_MUTATIONS = {
    "ops_summary_count_substitute": (_ops_substitute, "invalid_section"),
    "misses_dropped": (lambda d: {**d, "misses": []}, "counts_do_not_reconcile"),
    "unlinked_held_dropped": (lambda d: {k: v for k, v in d.items() if k != "unlinked_held"},
                              "invalid_unlinked_held"),
    "held_misses_trimmed": (
        lambda d: {**d, "unlinked_held": {**d["unlinked_held"], "misses": []}},
        "counts_do_not_reconcile"),
    "phantom_off_by_one": (lambda d: {**d, "phantom": d["phantom"] + 1}, "counts_do_not_reconcile"),
    "headline_out_of_range": (lambda d: {**d, "headline_pct": 100.1}, "invalid_rate"),
    "status_unknown": (lambda d: {**d, "status": "fresh"}, "invalid_status"),
    "count_as_string": (lambda d: {**d, "backed": str(d["backed"])}, "invalid_count"),
    "naive_generated_at": (lambda d: {**d, "generated_at": d["generated_at"][:19]},
                           "invalid_generated_at"),
    "not_an_object": (lambda d: [d], "invalid_payload"),
}


class TestMaturedLinkageStates:
    @pytest.mark.parametrize("name", sorted(ML_MUTATIONS))
    def test_a_mutated_producer_payload_is_malformed_and_its_control_is_a_hit(
            self, client, poisoned, monkeypatch, ml_raw, name):
        mutate, reason = ML_MUTATIONS[name]
        now = _generated_at(ml_raw) + timedelta(seconds=1)
        control, cbody, _ = _ml(client, monkeypatch, ml_raw, now=now)
        assert (control.status_code, cbody["cache_state"]) == (200, "hit")

        bad = json.dumps(mutate(copy.deepcopy(json.loads(ml_raw)))).encode()
        resp, body, _ = _ml(client, monkeypatch, bad, now=now)
        assert (resp.status_code, body["cache_state"], body["reason"]) == (503, "malformed", reason)
        assert body["payload"] is None and body["age_seconds"] is None
        assert (body["served_key"], body["saved_bytes"]) == (ML_KEY, len(bad))

    def test_miss_is_202_with_no_numbers(self, client, poisoned, monkeypatch):
        resp, body, redis = _ml(client, monkeypatch, None)
        assert resp.status_code == 202
        assert set(body) == ENVELOPE_KEYS
        assert (body["cache_state"], body["reason"], body["freshness"]) == (
            "miss", "no_saved_snapshot", "unknown")
        assert body["payload"] is None and body["served_key"] is None and body["saved_bytes"] is None
        assert redis.gets == [ML_KEY]

    def test_an_empty_string_is_malformed_not_a_miss(self, client, poisoned, monkeypatch):
        resp, body, _ = _ml(client, monkeypatch, b"")
        assert (resp.status_code, body["cache_state"], body["reason"]) == (503, "malformed", "not_json")

    def test_a_non_finite_number_anywhere_is_malformed(self, client, poisoned, monkeypatch, ml_raw):
        doc = json.loads(ml_raw)
        doc["extra"] = {"x": 1e999}
        bad = json.dumps(doc).replace("Infinity", "1e400").encode()
        resp, body, _ = _ml(client, monkeypatch, bad)
        assert (resp.status_code, body["reason"]) == (503, "non_finite_number")

    def test_oversized_bytes_are_refused_without_decoding(self, client, poisoned, monkeypatch, ml_raw):
        monkeypatch.setattr(am, "_MATURED_LINKAGE_MAX_BYTES", len(ml_raw) - 1)
        monkeypatch.setattr(ssr, "strict_loads",
                            lambda *_: (_ for _ in ()).throw(AssertionError("decoded")))
        resp, body, _ = _ml(client, monkeypatch, ml_raw)
        assert (resp.status_code, body["cache_state"], body["reason"]) == (
            503, "oversized", "saved_snapshot_exceeds_read_bound")
        assert body["saved_bytes"] == len(ml_raw) and body["max_saved_bytes"] == len(ml_raw) - 1
        assert body["payload"] is None

    def test_at_the_bound_is_still_served(self, client, poisoned, monkeypatch, ml_raw):
        monkeypatch.setattr(am, "_MATURED_LINKAGE_MAX_BYTES", len(ml_raw))
        resp, body, _ = _ml(client, monkeypatch, ml_raw,
                            now=_generated_at(ml_raw) + timedelta(seconds=1))
        assert (resp.status_code, body["cache_state"]) == (200, "hit")

    def test_a_transport_error_is_503_with_a_safe_code(self, client, poisoned, monkeypatch, ml_raw):
        import redis as redis_lib

        fake = ReaderRedis({ML_KEY: ml_raw},
                           get_exc=redis_lib.exceptions.ConnectionError("rediss://u:pw@host"))
        resp, body, _ = _ml(client, monkeypatch, fake)
        assert (resp.status_code, body["cache_state"], body["reason"]) == (
            503, "error", "redis_unavailable")
        assert body["payload"] is None and body["served_key"] is None
        assert "pw" not in resp.text and "rediss" not in resp.text

    def test_a_slow_read_is_cut_at_the_deadline(self, client, poisoned, monkeypatch, ml_raw):
        gate = threading.Event()
        monkeypatch.setattr(am, "_MATURED_LINKAGE_READ_DEADLINE_S", 0.05)
        fake = ReaderRedis({ML_KEY: ml_raw}, block_on={ML_KEY: gate})
        try:
            resp, body, _ = _ml(client, monkeypatch, fake)
        finally:
            gate.set()
        assert (resp.status_code, body["cache_state"], body["reason"]) == (
            503, "error", "read_deadline_exceeded")

        # Timed inside the loop: a bare TestClient (and asyncio.run) waits for the
        # abandoned executor thread at teardown, which is not the request's wait.
        gate2 = threading.Event()
        _serve(monkeypatch, ReaderRedis({ML_KEY: ml_raw}, block_on={ML_KEY: gate2}))

        async def timed():
            started = time.monotonic()
            out = await am.read_matured_linkage_saved()
            elapsed = time.monotonic() - started
            gate2.set()
            return out, elapsed

        (status, direct), elapsed = asyncio.run(timed())
        assert (status, direct["reason"]) == (503, "read_deadline_exceeded")
        assert elapsed < 1.0

    def test_a_future_stamp_is_served_with_unknown_freshness(self, client, poisoned, monkeypatch,
                                                            ml_raw):
        resp, body, _ = _ml(client, monkeypatch, ml_raw,
                            now=_generated_at(ml_raw) - timedelta(seconds=30))
        assert (resp.status_code, body["reason"], body["freshness"]) == (
            200, "generated_at_in_future", "unknown")
        assert body["age_seconds"] == -30

    def test_an_old_snapshot_gets_its_true_age_and_no_invented_verdict(self, client, poisoned,
                                                                       monkeypatch, ml_raw):
        resp, body, _ = _ml(client, monkeypatch, ml_raw,
                            now=_generated_at(ml_raw) + timedelta(hours=5))
        assert body["freshness"] == "unreviewed" and body["age_seconds"] == 5 * 3600

    @pytest.mark.parametrize("query", ["?bust=1", "?bust=true&refresh=1", "?key=bainluck:other"])
    @pytest.mark.parametrize("state", ["hit", "miss", "malformed"])
    def test_bust_refresh_and_key_arguments_change_nothing(self, client, poisoned, monkeypatch,
                                                           ml_raw, query, state):
        value = {"hit": ml_raw, "miss": None, "malformed": b"{bad"}[state]
        resp, body, redis = _ml(client, monkeypatch, value, query=query,
                                now=_generated_at(ml_raw) + timedelta(seconds=1))
        assert body["cache_state"] == state
        assert resp.status_code == {"hit": 200, "miss": 202, "malformed": 503}[state]
        assert redis.gets == [ML_KEY]


# ---------------------------------------------------------------------------
# Source Intelligence: bound to both real writers' bytes
# ---------------------------------------------------------------------------


class TestSourceIntelligenceBinding:
    def test_the_producer_snapshot_is_served_whole_from_the_primary(self, client, poisoned,
                                                                   monkeypatch, si_raw):
        saved = json.loads(si_raw[SI_KEY])
        assert saved["coverage"]["total_events"] == 52 and len(saved["case_studies"]) == 2
        assert saved["case_studies"][1]["away_team"] is None  # a real nullable field
        now = _generated_at(si_raw[SI_KEY]) + timedelta(seconds=90)
        resp, body, redis = _si(client, monkeypatch, si_raw, now=now)
        assert resp.status_code == 200, body
        assert set(body) == ENVELOPE_KEYS
        assert (body["cache_state"], body["reason"], body["freshness"]) == (
            "hit", "saved_snapshot", "unreviewed")
        assert (body["served_key"], body["served_from"]) == (SI_KEY, "primary")
        assert body["payload"] == saved
        assert body["saved_bytes"] == len(si_raw[SI_KEY])
        assert body["age_seconds"] == 90
        assert redis.gets == [SI_KEY]  # the retained copy is not even read

    def test_the_public_routes_inline_build_is_read_the_same(self, client, poisoned, monkeypatch,
                                                            si_inline_raw):
        resp, body, _ = _si(client, monkeypatch, si_inline_raw,
                            now=_generated_at(si_inline_raw[SI_KEY]) + timedelta(seconds=1))
        assert (resp.status_code, body["cache_state"]) == (200, "hit")
        assert body["payload"] == json.loads(si_inline_raw[SI_KEY])

    def test_primary_missing_serves_the_retained_copy_labelled_with_its_own_clock(
            self, client, poisoned, monkeypatch, si_raw):
        stale_at = _generated_at(si_raw[SI_STALE_KEY]) - timedelta(hours=7)
        stale = _restamp(si_raw[SI_STALE_KEY], stale_at)
        now = stale_at + timedelta(hours=7, seconds=12)
        resp, body, redis = _si(client, monkeypatch, {SI_STALE_KEY: stale}, now=now)
        assert resp.status_code == 200
        assert (body["cache_state"], body["reason"]) == ("hit", "primary_missing_served_retained_copy")
        assert (body["served_key"], body["served_from"]) == (SI_STALE_KEY, "retained_stale")
        assert body["generated_at"] == stale_at.isoformat() == body["payload"]["generated_at"]
        assert body["age_seconds"] == 7 * 3600 + 12
        # A stale record is never called fresh because the read succeeded.
        assert body["freshness"] == "unreviewed"
        assert body["payload"] == json.loads(stale)
        assert redis.gets == [SI_KEY, SI_STALE_KEY]

    def test_control_primary_present_wins_over_a_different_retained_copy(self, client, poisoned,
                                                                        monkeypatch, si_raw):
        older = _restamp(si_raw[SI_STALE_KEY], T0 - timedelta(days=3))
        resp, body, redis = _si(client, monkeypatch, {SI_KEY: si_raw[SI_KEY], SI_STALE_KEY: older},
                                now=_generated_at(si_raw[SI_KEY]) + timedelta(seconds=1))
        assert (body["served_from"], body["reason"]) == ("primary", "saved_snapshot")
        assert body["payload"] == json.loads(si_raw[SI_KEY])
        assert redis.gets == [SI_KEY]

    @pytest.mark.parametrize("primary,state,reason", [
        (b"{bad", "malformed", "not_json"),
        (b"", "malformed", "not_json"),
        (b'{"generated_at": "2026-10-20T17:00:00+00:00"}', "malformed", "invalid_section"),
    ])
    def test_a_present_but_unusable_primary_is_reported_and_the_copy_never_stands_in(
            self, client, poisoned, monkeypatch, si_raw, primary, state, reason):
        resp, body, redis = _si(client, monkeypatch,
                                {SI_KEY: primary, SI_STALE_KEY: si_raw[SI_STALE_KEY]})
        assert (resp.status_code, body["cache_state"], body["reason"]) == (503, state, reason)
        assert (body["served_key"], body["served_from"]) == (SI_KEY, "primary")
        assert body["payload"] is None
        assert redis.gets == [SI_KEY]

    def test_an_oversized_primary_is_reported_and_the_copy_never_stands_in(self, client, poisoned,
                                                                           monkeypatch, si_raw):
        monkeypatch.setattr(si, "_SI_SAVED_MAX_BYTES", len(si_raw[SI_KEY]) - 1)
        resp, body, redis = _si(client, monkeypatch, si_raw)
        assert (resp.status_code, body["cache_state"], body["served_from"]) == (
            503, "oversized", "primary")
        assert body["saved_bytes"] == len(si_raw[SI_KEY]) and body["payload"] is None
        assert redis.gets == [SI_KEY]

    def test_an_oversized_retained_copy_is_reported_as_the_copy(self, client, poisoned, monkeypatch,
                                                                si_raw):
        monkeypatch.setattr(si, "_SI_SAVED_MAX_BYTES", len(si_raw[SI_STALE_KEY]) - 1)
        resp, body, _ = _si(client, monkeypatch, {SI_STALE_KEY: si_raw[SI_STALE_KEY]})
        assert (resp.status_code, body["cache_state"], body["served_key"], body["served_from"]) == (
            503, "oversized", SI_STALE_KEY, "retained_stale")

    def test_a_malformed_retained_copy_is_reported_as_the_copy(self, client, poisoned, monkeypatch):
        resp, body, _ = _si(client, monkeypatch, {SI_STALE_KEY: b"[]"})
        assert (resp.status_code, body["cache_state"], body["reason"], body["served_from"]) == (
            503, "malformed", "invalid_payload", "retained_stale")

    def test_both_missing_is_a_202_miss(self, client, poisoned, monkeypatch):
        resp, body, redis = _si(client, monkeypatch, {})
        assert (resp.status_code, body["cache_state"], body["reason"]) == (
            202, "miss", "no_saved_snapshot_or_retained_copy")
        assert body["payload"] is None and body["served_key"] is None
        assert redis.gets == [SI_KEY, SI_STALE_KEY]

    def test_a_transport_error_on_the_primary_never_falls_back(self, client, poisoned, monkeypatch,
                                                              si_raw):
        import redis as redis_lib

        fake = ReaderRedis(si_raw, get_exc=redis_lib.exceptions.TimeoutError("rediss://u:pw@h"))
        resp, body, _ = _si(client, monkeypatch, fake)
        assert (resp.status_code, body["cache_state"], body["reason"]) == (
            503, "error", "redis_unavailable")
        assert fake.gets == [SI_KEY]
        assert "pw" not in resp.text

    def test_one_total_deadline_covers_both_keys(self, client, poisoned, monkeypatch, si_raw):
        # The primary answers at once (missing); the copy's GET hangs. A per-key
        # budget would wait twice; the request's single budget cuts it.
        gate = threading.Event()
        monkeypatch.setattr(si, "_SI_SAVED_READ_DEADLINE_S", 0.05)
        fake = ReaderRedis({SI_STALE_KEY: si_raw[SI_STALE_KEY]}, block_on={SI_STALE_KEY: gate})
        try:
            resp, body, _ = _si(client, monkeypatch, fake)
        finally:
            gate.set()
        assert (resp.status_code, body["cache_state"], body["reason"]) == (
            503, "error", "read_deadline_exceeded")
        assert body["served_key"] is None and body["payload"] is None

    def test_a_primary_that_times_out_is_not_missing_and_the_copy_never_stands_in(
            self, client, poisoned, monkeypatch, si_raw):
        # A timed-out primary may exist; serving the copy would present an
        # unknown primary as absent. The single budget ends the request instead.
        gate = threading.Event()
        monkeypatch.setattr(si, "_SI_SAVED_READ_DEADLINE_S", 0.05)
        fake = ReaderRedis(si_raw, block_on={SI_KEY: gate})
        try:
            resp, body, _ = _si(client, monkeypatch, fake)
        finally:
            gate.set()
        assert (resp.status_code, body["cache_state"], body["reason"]) == (
            503, "error", "read_deadline_exceeded")
        assert body["served_from"] is None and body["payload"] is None

    def test_the_full_view_is_kept_no_case_study_or_point_is_dropped(self, client, poisoned,
                                                                     monkeypatch, si_large_raw):
        saved = json.loads(si_large_raw[SI_KEY])
        points = sum(len(p) for cs in saved["case_studies"] for p in cs["series"].values())
        assert len(saved["case_studies"]) == 5 and points == 5 * 6 * 1500
        resp, body, _ = _si(client, monkeypatch, si_large_raw,
                            now=_generated_at(si_large_raw[SI_KEY]) + timedelta(seconds=1))
        assert (resp.status_code, body["cache_state"]) == (200, "hit")
        assert body["payload"] == saved
        assert body["saved_bytes"] == len(si_large_raw[SI_KEY]) < si._SI_SAVED_MAX_BYTES

    def test_unbounded_series_values_the_producer_passes_through_are_served(self, client, poisoned,
                                                                           monkeypatch,
                                                                           si_unbounded_raw):
        raw = si_unbounded_raw
        served = json.loads(raw[SI_KEY])
        assert any(pt["p"] == 1.0004 for cs in served["case_studies"]
                   for pt in cs["series"].get("espn", []))
        resp, body, _ = _si(client, monkeypatch, raw,
                            now=_generated_at(raw[SI_KEY]) + timedelta(seconds=1))
        assert (resp.status_code, body["cache_state"]) == (200, "hit")


def _set_path(doc, path, value):
    target = doc
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = value
    return doc


SI_MUTATIONS = {
    "coverage_total_off_by_one": (("coverage", "total_events"), lambda v: v + 1,
                                  "counts_do_not_reconcile"),
    "multi_source_off_by_one": (("coverage", "multi_source_events"), lambda v: v + 1,
                                "counts_do_not_reconcile"),
    "brier_out_of_range": (("source_accuracy", 0, "brier"), lambda v: 1.5, "invalid_number"),
    "bucket_index_out_of_range": (("source_accuracy", 0, "buckets", 0, "idx"), lambda v: 10,
                                  "invalid_row"),
    "rate_out_of_range": (("disagreements", "rate_5pp"), lambda v: 1.01, "invalid_number"),
    "pair_split_not_an_object": (("disagreements", "pairwise", 0, "by_sport"), lambda v: [],
                                 "invalid_row"),
    "case_study_series_dropped": (("case_studies", 0, "series"), lambda v: None, "invalid_series"),
    "series_point_as_string": (("case_studies", 0, "series", "espn", 0, "p"), str,
                               "invalid_series"),
    "home_won_as_int": (("case_studies", 0, "home_won"), lambda v: 1, "invalid_row"),
    "case_studies_not_a_list": (("case_studies",), lambda v: {}, "invalid_section"),
    "count_negative": (("disagreements", "total_comparisons"), lambda v: -1, "invalid_count"),
    "generated_at_unparseable": (("generated_at",), lambda v: "yesterday", "invalid_generated_at"),
}


class TestSourceIntelligenceStates:
    @pytest.mark.parametrize("name", sorted(SI_MUTATIONS))
    @pytest.mark.parametrize("key", [SI_KEY, SI_STALE_KEY])
    def test_a_mutated_producer_payload_is_malformed_and_its_control_is_a_hit(
            self, client, poisoned, monkeypatch, si_raw, name, key):
        path, change, reason = SI_MUTATIONS[name]
        store = {key: si_raw[key]}
        now = _generated_at(si_raw[key]) + timedelta(seconds=1)
        control, cbody, _ = _si(client, monkeypatch, store, now=now)
        assert (control.status_code, cbody["cache_state"]) == (200, "hit")

        doc = json.loads(si_raw[key])
        target = doc
        for step in path[:-1]:
            target = target[step]
        _set_path(doc, path, change(target[path[-1]]))
        bad = json.dumps(doc).encode()
        resp, body, _ = _si(client, monkeypatch, {key: bad}, now=now)
        assert (resp.status_code, body["cache_state"], body["reason"]) == (503, "malformed", reason)
        assert body["served_key"] == key and body["payload"] is None

    def test_a_future_stamp_is_served_with_unknown_freshness(self, client, poisoned, monkeypatch,
                                                            si_raw):
        resp, body, _ = _si(client, monkeypatch, si_raw,
                            now=_generated_at(si_raw[SI_KEY]) - timedelta(seconds=5))
        assert (resp.status_code, body["reason"], body["freshness"]) == (
            200, "generated_at_in_future", "unknown")

    @pytest.mark.parametrize("query", ["?refresh=true", "?refresh=1&bust=1", "?key=bainluck:other"])
    @pytest.mark.parametrize("state", ["hit", "retained", "miss"])
    def test_refresh_bust_and_key_arguments_change_nothing(self, client, poisoned, monkeypatch,
                                                           si_raw, query, state):
        store = {"hit": si_raw, "retained": {SI_STALE_KEY: si_raw[SI_STALE_KEY]}, "miss": {}}[state]
        resp, body, redis = _si(client, monkeypatch, store, query=query,
                                now=_generated_at(si_raw[SI_KEY]) + timedelta(seconds=1))
        expected = {"hit": (200, "primary"), "retained": (200, "retained_stale"),
                    "miss": (202, None)}[state]
        assert (resp.status_code, body["served_from"]) == expected
        assert set(redis.gets) <= {SI_KEY, SI_STALE_KEY}


# ---------------------------------------------------------------------------
# The shared read: fixed keys, one deadline, no writes, no computes
# ---------------------------------------------------------------------------


class TestSharedRead:
    def test_the_reader_keys_are_the_producers_keys(self):
        from app.tasks import precompute_admin_health as pah

        assert am._MATURED_LINKAGE_CACHE_KEY == ML_KEY
        assert ML_KEY in inspect.getsource(pah._precompute_admin_matured_linkage)
        assert (si._REDIS_KEY, si._REDIS_STALE_KEY) == (SI_KEY, SI_STALE_KEY)
        assert si._SI_SERVED_FROM == {SI_KEY: "primary", SI_STALE_KEY: "retained_stale"}

    def test_the_request_path_client_signature_is_reused(self, monkeypatch, ml_raw):
        calls = _serve(monkeypatch, ReaderRedis({ML_KEY: ml_raw}))
        asyncio.run(ssr.read_first_saved((ML_KEY,), deadline_s=1.0))
        assert calls == [{"socket_timeout": 0.5, "fast_fail": True}]

    def test_a_str_value_from_a_decoding_client_is_measured_in_bytes(self, monkeypatch):
        _serve(monkeypatch, ReaderRedis({ML_KEY: '{"é": 1}'}))
        found = asyncio.run(ssr.read_first_saved((ML_KEY,), deadline_s=1.0))
        assert (found.key, found.size) == (ML_KEY, len('{"é": 1}'.encode()))

    def test_the_read_module_has_no_write_session_or_task_verb(self):
        src = inspect.getsource(ssr)
        for verb in (".set(", "setex", ".delete(", ".expire(", "get_db", "session",
                     "send_task", ".delay(", "apply_async"):
            assert verb not in src.replace("opens a session", ""), verb

    def test_strict_loads_refuses_absurd_nesting_as_not_json(self):
        with pytest.raises(ssr.SavedPayloadInvalid) as exc:
            ssr.strict_loads("[" * 200_000 + "]" * 200_000)
        assert exc.value.reason == "not_json"
