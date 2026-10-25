"""#847 — the Correctness Console's 14-day sport cards, served from saved evidence.

PILLAR: TRUTH. SHIP: an operator sees the complete Matching sport cards inside
the Correctness Console without triggering database calculations when the page
opens.

``GET /api/admin/schedule/accuracy/cached`` reads ONE fixed key. Its writer,
``_precompute_admin_schedule_accuracy``, is INERT (no task, no beat, no caller)
and runs the legacy calculation ``_compute_schedule_accuracy`` with days=14,
unchanged, inside one repeatable-read, read-only transaction.

HOW THE BINDING WORKS. The database is the only fake. ``EventStore`` answers
the two REAL compiled statements (asserted byte for byte) from a list of event
rows, applying the statement's own bound cutoff — so a window positive or
negative is decided by the parameter the real calculation sent. Every saved
value the reader is served is the exact bytes the real producer wrote from
those rows; the legacy route, run on the same rows at the same clock, must
return the same cards. A malformed case is one named mutation of those bytes,
and the unmutated bytes are asserted to pass in the same test, so a refusal
can only come from the mutation.

Every reader path runs with the calculation, the producer, the session
factories, task dispatch and every cache write wired to explode. No Redis,
database or network is reached from this file.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import threading
import time
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import TextClause

from app.routes import admin
from app.routes import admin_events as ae
from app.routes.admin_utils import admin_account_identity
from app.tasks import precompute_admin_health as cov
from app.utils import saved_snapshot_read as ssr

TOKEN = "test-admin-token-847-schedule-accuracy"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PATH = "/api/admin/schedule/accuracy/cached"
LEGACY_PATH = "/api/admin/schedule/accuracy"
KEY = "bainluck:admin:schedule_accuracy:14d:v1"
T0 = datetime(2026, 10, 20, 18, 0, 0, tzinfo=timezone.utc)
CUTOFF = T0 - timedelta(days=14)
BACKEND = Path(__file__).resolve().parents[1]
PRODUCER = "_precompute_admin_schedule_accuracy"

ENVELOPE_KEYS = {
    "schema_version", "cache_state", "reason", "freshness", "freshness_basis",
    "served_key", "served_from", "saved_bytes", "max_saved_bytes",
    "generated_at", "age_seconds", "payload",
}

# The two statements the legacy calculation compiles to. Pinned so the fake can
# never answer a different query than production would run.
LINKAGE_SQL = (
    "SELECT sports.key, count(events.id) AS total, count(events.external_id) AS odds_api, "
    "count(events.espn_id) AS espn, count(events.statpal_fixture_id) AS statpal \n"
    "FROM events JOIN sports ON events.sport_id = sports.id \n"
    "WHERE events.commence_time >= %(commence_time_1)s GROUP BY sports.key"
)
PROVENANCE_SQL = (
    "SELECT sports.key, events.commence_time_source, count(events.id) AS count \n"
    "FROM events JOIN sports ON events.sport_id = sports.id \n"
    "WHERE events.commence_time >= %(commence_time_1)s "
    "GROUP BY sports.key, events.commence_time_source "
    "ORDER BY sports.key, events.commence_time_source"
)


# ---------------------------------------------------------------------------
# The database fake: real statements, fake rows
# ---------------------------------------------------------------------------


def _ev(sport, at, *, odds=False, espn=False, statpal=False, cts="espn"):
    return {
        "sport": sport, "commence_time": at,
        "external_id": "oa" if odds else None,
        "espn_id": "e" if espn else None,
        "statpal_fixture_id": "sp" if statpal else None,
        "commence_time_source": cts,
    }


EVENTS = [
    # NBA: the inclusive edge, now, and a far-future game are IN; one
    # microsecond before the edge is OUT (its statpal provenance must vanish).
    _ev("basketball_nba", CUTOFF, odds=True, espn=True, cts="espn"),
    _ev("basketball_nba", T0, espn=True, cts="espn"),
    _ev("basketball_nba", T0 + timedelta(days=30), odds=True, cts="odds_api"),
    _ev("basketball_nba", CUTOFF - timedelta(microseconds=1), odds=True, espn=True,
        statpal=True, cts="statpal"),
    # NHL: a NULL commence_time_source is its own "null" bucket.
    _ev("icehockey_nhl", T0 - timedelta(days=1), odds=True, cts=None),
    _ev("icehockey_nhl", T0 + timedelta(days=1), odds=True, statpal=True, cts="espn"),
    # NFL: only an out-of-window game, so NFL has no card at all.
    _ev("americanfootball_nfl", CUTOFF - timedelta(days=3), odds=True, espn=True),
    # MLB: 4 of 5 linked = exactly 80% = HIGH.
    *[_ev("baseball_mlb", T0 - timedelta(days=i), odds=i < 4, espn=True) for i in range(5)],
    # EPL: 2 of 5 linked = exactly 40% = MEDIUM.
    *[_ev("soccer_epl", T0 + timedelta(hours=i), odds=i < 2, statpal=True, cts="statpal")
      for i in range(5)],
    # Tennis: linked to nothing = 0% = LOW (a real zero over a real denominator).
    _ev("tennis_atp_us_open", T0 - timedelta(days=2), cts="odds_api"),
]

EXPECTED_SPORTS = {
    "tennis_atp_us_open": {
        "total": 1, "sources": {"odds_api": 0, "espn": 0, "statpal": 0},
        "commence_time_sources": {"odds_api": 1}, "odds_api_linked_pct": 0, "reliability": "LOW",
    },
    "basketball_nba": {
        "total": 3, "sources": {"odds_api": 2, "espn": 2, "statpal": 0},
        "commence_time_sources": {"espn": 2, "odds_api": 1},
        "odds_api_linked_pct": 66.7, "reliability": "MEDIUM",
    },
    "soccer_epl": {
        "total": 5, "sources": {"odds_api": 2, "espn": 0, "statpal": 5},
        "commence_time_sources": {"statpal": 5}, "odds_api_linked_pct": 40.0, "reliability": "MEDIUM",
    },
    "baseball_mlb": {
        "total": 5, "sources": {"odds_api": 4, "espn": 5, "statpal": 0},
        "commence_time_sources": {"espn": 5}, "odds_api_linked_pct": 80.0, "reliability": "HIGH",
    },
    "icehockey_nhl": {
        "total": 2, "sources": {"odds_api": 2, "espn": 0, "statpal": 1},
        "commence_time_sources": {"espn": 1, "null": 1}, "odds_api_linked_pct": 100.0,
        "reliability": "HIGH",
    },
}


class EventStore:
    """Evaluates the two pinned statements over ``events`` with their own cutoff."""

    def __init__(self, events=EVENTS):
        self.events = events
        self.cutoffs: list[datetime] = []

    def answer(self, sql: str, params: dict):
        cutoff = params["commence_time_1"]
        self.cutoffs.append(cutoff)
        rows = [e for e in self.events if e["commence_time"] >= cutoff]
        if sql == LINKAGE_SQL:
            groups: dict[str, list] = {}
            for e in rows:
                groups.setdefault(e["sport"], []).append(e)
            out = [
                SimpleNamespace(
                    key=k, total=len(v),
                    odds_api=sum(e["external_id"] is not None for e in v),
                    espn=sum(e["espn_id"] is not None for e in v),
                    statpal=sum(e["statpal_fixture_id"] is not None for e in v),
                )
                for k, v in groups.items()
            ]
            # No ORDER BY: hand them back in an order nobody would choose.
            return sorted(out, key=lambda r: r.key, reverse=True)
        if sql == PROVENANCE_SQL:
            counts = Counter((e["sport"], e["commence_time_source"]) for e in rows)
            # Postgres ascending order puts NULL last.
            ordered = sorted(counts, key=lambda kc: (kc[0], kc[1] is None, kc[1] or ""))
            return [SimpleNamespace(key=k, commence_time_source=c, count=counts[(k, c)])
                    for k, c in ordered]
        raise AssertionError(f"unexpected statement: {sql!r}")


class _Result:
    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one

    def all(self):
        return list(self._rows)

    def one(self):
        assert self._one is not None
        return self._one


class FakeSession:
    """Answers text statements and the two compiled selects; records the order."""

    def __init__(self, store, *, isolation="repeatable read", read_only="on", fail_on=None):
        self.store = store
        self.isolation = isolation
        self.read_only = read_only
        self.fail_on = fail_on  # (substring, exception)
        self.log: list[str] = []
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        if isinstance(stmt, TextClause):
            sql, bound = stmt.text, {}
        else:
            compiled = stmt.compile(dialect=postgresql.dialect())
            sql, bound = str(compiled), compiled.params
        self.log.append(sql)
        if self.fail_on and self.fail_on[0] in sql:
            raise self.fail_on[1]
        if sql.startswith("SET "):
            return _Result()
        if sql == cov._SCHEDULE_ACCURACY_SETTINGS_SQL:
            return _Result(one=SimpleNamespace(isolation=self.isolation, read_only=self.read_only))
        return _Result(self.store.answer(sql, bound))

    async def rollback(self):
        self.rollbacks += 1

    async def commit(self):
        raise AssertionError("the producer committed")


class RecordingRedis:
    def __init__(self, store=None, *, set_exc=None):
        self.store = dict(store or {})
        self.set_exc = set_exc
        self.sets: list[tuple[str, int]] = []

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        if self.set_exc:
            raise self.set_exc
        self.sets.append((key, ex))
        self.store[key] = value


class Clock:
    def __init__(self, start=T0, step=0.5):
        self.now, self.step = start, timedelta(seconds=step)

    def __call__(self):
        current = self.now
        self.now += self.step
        return current


async def _produce(monkeypatch, *, session=None, redis=None, clock=None, open_exc=None):
    session = session or FakeSession(EventStore())
    redis = redis if redis is not None else RecordingRedis()
    sessions = []

    @asynccontextmanager
    async def _get_task_session():
        if open_exc:
            raise open_exc
        sessions.append(session)
        yield session

    monkeypatch.setattr("app.tasks.base.get_task_session", _get_task_session)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda **k: redis)
    monkeypatch.setattr(cov, "_schedule_accuracy_now", clock or Clock())
    result = await cov._precompute_admin_schedule_accuracy()
    return result, session, redis


def _produced_bytes(events=EVENTS, at=T0) -> str:
    redis = RecordingRedis()
    mp = pytest.MonkeyPatch()
    try:
        result = asyncio.run(_produce(mp, session=FakeSession(EventStore(events)),
                                      redis=redis, clock=Clock(at)))[0]
    finally:
        mp.undo()
    assert result["published"] is True, result
    return redis.store[KEY]


@pytest.fixture(scope="module")
def raw() -> str:
    return _produced_bytes()


@pytest.fixture(scope="module")
def raw_empty() -> str:
    return _produced_bytes([_ev("basketball_nba", CUTOFF - timedelta(days=1))])


@pytest.fixture(scope="module")
def legacy_cards() -> dict:
    mp = pytest.MonkeyPatch()
    try:
        return _legacy(mp)[0]
    finally:
        mp.undo()


# ---------------------------------------------------------------------------
# Reader harness
# ---------------------------------------------------------------------------


class ReaderRedis:
    """A cache the saved-only reader may GET and must never write."""

    def __init__(self, store=None, *, get_exc=None):
        self.store = dict(store or {})
        self.get_exc = get_exc
        self.gets: list[str] = []

    def get(self, key):
        self.gets.append(key)
        if self.get_exc:
            raise self.get_exc
        return self.store.get(key)

    def _write(self, *a, **k):
        raise AssertionError("the saved-only reader wrote the cache")

    set = setex = setnx = delete = expire = getdel = getex = mset = _write


@pytest.fixture
def poisoned(monkeypatch):
    """Everything that could compute, open a session, enqueue or write explodes."""

    def boom(name):
        def _raise(*a, **k):
            raise AssertionError(f"saved-only reader touched {name}")
        return _raise

    monkeypatch.setattr(ae, "_compute_schedule_accuracy", boom("the calculation"))
    monkeypatch.setattr(cov, PRODUCER, boom("the producer"))
    monkeypatch.setattr("app.tasks.base.get_task_session", boom("get_task_session"))
    monkeypatch.setattr("app.services.database.async_session_maker", boom("async_session_maker"))
    monkeypatch.setattr("app.routes.admin_utils._safe_send_task", boom("task dispatch"))
    from app.tasks import celery_app

    monkeypatch.setattr(celery_app, "send_task", boom("celery send_task"))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    app = FastAPI()
    # Same mount as main.py: admin.router carries admin_events' router.
    app.include_router(admin.router, prefix="/api/admin",
                       dependencies=[Depends(admin_account_identity)])

    def _no_db():
        raise AssertionError("the saved-only reader opened a database session")

    app.dependency_overrides[ae.get_db] = _no_db
    return TestClient(app, raise_server_exceptions=False)


def _get(client, monkeypatch, value, *, now=T0 + timedelta(minutes=5), query="", headers=AUTH):
    redis = value if isinstance(value, ReaderRedis) else ReaderRedis({KEY: value} if value is not None else {})
    calls = []

    def factory(**k):
        calls.append(k)
        return redis

    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", factory)
    monkeypatch.setattr(ae, "_schedule_accuracy_reader_now", lambda: now)
    resp = client.get(PATH + query, headers=headers)
    return resp, resp.json(), redis, calls


def _assert_no_numbers(body):
    assert set(body) == ENVELOPE_KEYS
    assert body["payload"] is None and body["generated_at"] is None and body["age_seconds"] is None
    assert body["freshness"] == "unknown"


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return T0 if tz is None else T0.astimezone(tz)


def _legacy(monkeypatch, events=EVENTS, days=14):
    """The UNCHANGED legacy route on the same rows at the same clock."""
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(ae, "datetime", _FrozenDatetime)
    store = EventStore(events)
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/admin",
                       dependencies=[Depends(admin_account_identity)])
    app.dependency_overrides[ae.get_db] = lambda: FakeSession(store)
    resp = TestClient(app).get(f"{LEGACY_PATH}?days={days}", headers=AUTH)
    assert resp.status_code == 200, resp.text
    return resp.json(), store


# ---------------------------------------------------------------------------
# The producer: legacy calculation, one snapshot, validated before publication
# ---------------------------------------------------------------------------


class TestProducer:
    async def test_one_repeatable_read_read_only_transaction_in_contract_order(self, monkeypatch):
        result, session, redis = await _produce(monkeypatch)
        assert result == {"status": "ok", "error": None, "published": True, "sports": 5}
        assert session.log == [
            "SET LOCAL statement_timeout = '10s'",
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY",
            cov._SCHEDULE_ACCURACY_SETTINGS_SQL,
            LINKAGE_SQL,
            PROVENANCE_SQL,
        ]
        assert session.rollbacks == 1
        assert [k for k, _ in redis.sets] == [KEY]

    async def test_both_counts_use_the_fourteen_day_cutoff_from_as_of(self, monkeypatch):
        store = EventStore()
        await _produce(monkeypatch, session=FakeSession(store))
        assert store.cutoffs == [CUTOFF, CUTOFF]

    async def test_every_card_count_and_denominator_is_published_exactly(self, monkeypatch):
        _, _, redis = await _produce(monkeypatch)
        snapshot = json.loads(redis.store[KEY])
        assert snapshot["accuracy"]["sports"] == EXPECTED_SPORTS
        assert snapshot["accuracy"]["summary"] == {
            "total_sports": 5, "high_reliability": 2, "medium_reliability": 2, "low_reliability": 1,
        }
        assert snapshot["accuracy"]["period_days"] == 14

    async def test_full_window_positives_and_out_of_window_negatives(self, monkeypatch):
        _, _, redis = await _produce(monkeypatch)
        sports = json.loads(redis.store[KEY])["accuracy"]["sports"]
        # The inclusive edge and a game 30 days AHEAD both count (no upper bound).
        assert sports["basketball_nba"]["total"] == 3
        assert sports["basketball_nba"]["commence_time_sources"] == {"espn": 2, "odds_api": 1}
        # One microsecond before the edge contributes nothing, not even provenance.
        assert "statpal" not in sports["basketball_nba"]["commence_time_sources"]
        assert sports["basketball_nba"]["sources"]["statpal"] == 0
        # A sport whose only game is out of window has no card, never a zero card.
        assert "americanfootball_nfl" not in sports

    async def test_the_saved_cards_are_the_legacy_routes_cards(self, monkeypatch):
        legacy, legacy_store = _legacy(monkeypatch)
        _, _, redis = await _produce(monkeypatch)
        snapshot = json.loads(redis.store[KEY])
        assert snapshot["accuracy"] == legacy
        # Same order too: LOW first, then by sport key — the legacy sort.
        assert list(snapshot["accuracy"]["sports"]) == list(legacy["sports"])
        assert list(legacy["sports"]) == [
            "tennis_atp_us_open", "basketball_nba", "soccer_epl", "baseball_mlb", "icehockey_nhl",
        ]
        assert legacy_store.cutoffs == [CUTOFF, CUTOFF]

    async def test_the_window_and_clock_survive_with_the_payload(self, monkeypatch):
        _, _, redis = await _produce(monkeypatch, clock=Clock(T0, step=0.5))
        snapshot = json.loads(redis.store[KEY])
        assert snapshot["as_of"] == snapshot["generated_at"] == T0.isoformat()
        assert snapshot["observation_finished_at"] == (T0 + timedelta(seconds=0.5)).isoformat()
        assert snapshot["window"] == {
            "column": "events.commence_time", "days": 14, "start": CUTOFF.isoformat(),
            "start_inclusive": True, "end": None,
        }
        assert snapshot["transaction"] == {"isolation": "repeatable read", "read_only": True}

    async def test_the_key_lives_only_as_long_as_its_observation(self, monkeypatch):
        _, _, redis = await _produce(monkeypatch, clock=Clock(T0, step=1.0))
        # as_of=T0, finished=T0+1, TTL computed at T0+2: retention runs from as_of.
        assert redis.sets == [(KEY, cov.SCHEDULE_ACCURACY_RETAIN_SECONDS - 2)]

    async def test_a_complete_empty_window_publishes_as_an_empty_answer(self, monkeypatch):
        old = [_ev("basketball_nba", CUTOFF - timedelta(days=1), odds=True)]
        _, _, redis = await _produce(monkeypatch, session=FakeSession(EventStore(old)))
        accuracy = json.loads(redis.store[KEY])["accuracy"]
        assert accuracy["sports"] == {}
        assert accuracy["summary"]["total_sports"] == 0

    async def test_a_full_slate_is_published_whole(self, monkeypatch):
        slate = [
            _ev(f"sport_{n:03d}", T0 - timedelta(hours=h), odds=h % 2 == 0, espn=h % 3 == 0,
                cts=("espn", "statpal", "odds_api", "kalshi", "polymarket", None)[h % 6])
            for n in range(150) for h in range(12)
        ]
        result, _, redis = await _produce(monkeypatch, session=FakeSession(EventStore(slate)))
        assert result["published"] is True and result["sports"] == 150
        raw = redis.store[KEY]
        assert len(raw.encode()) < ae.SCHEDULE_ACCURACY_MAX_BYTES
        assert len(json.loads(raw)["accuracy"]["sports"]) == 150

    @pytest.mark.parametrize("fail_on, kind, code", [
        (LINKAGE_SQL[:30], "query_error", "database_error"),
        (PROVENANCE_SQL[:40], "query_error", "database_error"),
        ("SET TRANSACTION", "query_error", "database_error"),
    ])
    async def test_a_failed_query_publishes_nothing_and_keeps_the_prior_bytes(self, monkeypatch, raw,
                                                                               fail_on, kind, code):
        redis = RecordingRedis({KEY: raw})
        session = FakeSession(EventStore(), fail_on=(fail_on, RuntimeError("dsn-sentinel-847 in the exception text")))
        result, session, redis = await _produce(monkeypatch, session=session, redis=redis)
        assert result == {"status": "error", "error": {"kind": kind, "code": code}, "published": False}
        assert redis.sets == [] and redis.store[KEY] == raw
        assert session.rollbacks == 1
        assert "dsn-sentinel-847" not in json.dumps(result)

    async def test_a_statement_timeout_is_named_as_one(self, monkeypatch):
        class QueryCanceledError(Exception):
            pass

        session = FakeSession(EventStore(), fail_on=(PROVENANCE_SQL[:40], QueryCanceledError("x")))
        result, _, redis = await _produce(monkeypatch, session=session)
        assert result["error"] == {"kind": "statement_timeout", "code": "query_canceled"}
        assert redis.sets == []

    async def test_a_session_that_cannot_open_publishes_nothing(self, monkeypatch, raw):
        redis = RecordingRedis({KEY: raw})
        result, _, redis = await _produce(monkeypatch, redis=redis, open_exc=OSError("no db"))
        assert result["published"] is False and result["error"]["kind"] == "query_error"
        assert redis.sets == [] and redis.store[KEY] == raw

    @pytest.mark.parametrize("isolation, read_only", [
        ("read committed", "on"), ("repeatable read", "off"), (None, "on"),
    ])
    async def test_a_transaction_that_is_not_one_read_only_snapshot_is_refused(self, monkeypatch, raw,
                                                                               isolation, read_only):
        redis = RecordingRedis({KEY: raw})
        session = FakeSession(EventStore(), isolation=isolation, read_only=read_only)
        result, _, redis = await _produce(monkeypatch, session=session, redis=redis)
        assert result["error"] == {"kind": "malformed_result", "code": "invalid_transaction"}
        assert redis.sets == [] and redis.store[KEY] == raw

    async def test_a_result_that_fails_the_reader_contract_never_replaces_evidence(self, monkeypatch, raw):
        real = ae._compute_schedule_accuracy

        async def corrupt(db, *, days, now):
            out = await real(db, days=days, now=now)
            out["sports"]["basketball_nba"]["sources"]["odds_api"] = 99
            return out

        monkeypatch.setattr(ae, "_compute_schedule_accuracy", corrupt)
        redis = RecordingRedis({KEY: raw})
        result, _, redis = await _produce(monkeypatch, redis=redis)
        assert result["error"] == {"kind": "malformed_result", "code": "count_exceeds_total"}
        assert redis.sets == [] and redis.store[KEY] == raw

    async def test_a_snapshot_larger_than_the_read_bound_is_not_published(self, monkeypatch, raw):
        monkeypatch.setattr(ae, "SCHEDULE_ACCURACY_MAX_BYTES", 512)
        redis = RecordingRedis({KEY: raw})
        result, _, redis = await _produce(monkeypatch, redis=redis)
        assert result["error"] == {"kind": "malformed_result", "code": "exceeds_read_bound"}
        assert redis.sets == []

    async def test_an_observation_that_outlived_retention_is_not_published(self, monkeypatch):
        clock = Clock(T0, step=cov.SCHEDULE_ACCURACY_RETAIN_SECONDS / 2)
        result, _, redis = await _produce(monkeypatch, clock=clock)
        assert result["error"] == {"kind": "malformed_result", "code": "observation_outlived_retention"}
        assert redis.sets == []

    async def test_a_failed_publication_does_not_claim_it_published(self, monkeypatch):
        redis = RecordingRedis(set_exc=ConnectionError("url-sentinel-847"))
        result, _, _ = await _produce(monkeypatch, redis=redis)
        assert result == {"status": "error", "published": False,
                          "error": {"kind": "cache_publish_error", "code": "redis_set_failed"}}


# ---------------------------------------------------------------------------
# Inert: implemented, exercised only here, reachable from nowhere
# ---------------------------------------------------------------------------


class TestInert:
    def test_the_producer_is_a_plain_coroutine_function_with_no_decorator(self):
        tree = ast.parse((BACKEND / "app/tasks/precompute_admin_health.py").read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == PRODUCER)
        assert fn.decorator_list == []
        assert not hasattr(getattr(cov, PRODUCER), "delay")

    def test_nothing_in_the_app_names_the_producer(self):
        hits = [
            str(p.relative_to(BACKEND)) for p in (BACKEND / "app").rglob("*.py")
            if PRODUCER in p.read_text(encoding="utf-8", errors="replace")
        ]
        assert sorted(hits) == ["app/routes/admin_events.py", "app/tasks/precompute_admin_health.py"]
        own = (BACKEND / "app/tasks/precompute_admin_health.py").read_text()
        assert own.count(f"async def {PRODUCER}(") == 1
        assert f"{PRODUCER}()" not in own.replace(f"async def {PRODUCER}()", "")
        # The route module names it in prose only.
        route_src = (BACKEND / "app/routes/admin_events.py").read_text()
        assert f"{PRODUCER}(" not in route_src and "precompute_admin_health" not in [
            n.module for n in ast.walk(ast.parse(route_src)) if isinstance(n, ast.ImportFrom)
        ]

    def test_no_celery_task_or_beat_entry_reaches_the_producer(self):
        from app.tasks import celery_app

        assert not any("schedule_accuracy" in n for n in celery_app.tasks)
        beat = celery_app.conf.beat_schedule or {}
        assert not any("schedule_accuracy" in str(v.get("task", "")) or "schedule_accuracy" in k
                       for k, v in beat.items())

    def test_the_legacy_route_still_computes_on_request(self, monkeypatch):
        body, store = _legacy(monkeypatch)
        assert body["sports"] == EXPECTED_SPORTS
        assert store.cutoffs == [CUTOFF, CUTOFF]
        # And its own ``days`` still moves the window (behaviour unchanged).
        body7, store7 = _legacy(monkeypatch, days=7)
        assert store7.cutoffs == [T0 - timedelta(days=7)] * 2
        assert body7["period_days"] == 7


# ---------------------------------------------------------------------------
# The reader: auth first, no database, no work input
# ---------------------------------------------------------------------------


class TestAuth:
    def test_no_credentials_is_refused_before_evidence_is_read(self, client, poisoned, monkeypatch, raw):
        resp, _, redis, _ = _get(client, monkeypatch, raw, headers={})
        assert resp.status_code == 403 and redis.gets == []

    def test_a_wrong_token_is_refused_before_evidence_is_read(self, client, poisoned, monkeypatch, raw):
        resp, _, redis, _ = _get(client, monkeypatch, raw, headers={"Authorization": "Bearer nope"})
        assert resp.status_code == 403 and redis.gets == []

    def test_a_query_secret_alone_is_refused(self, client, poisoned, monkeypatch, raw):
        resp, _, redis, _ = _get(client, monkeypatch, raw, query=f"?secret={TOKEN}", headers={})
        assert resp.status_code == 403 and redis.gets == []

    def test_the_machine_token_is_served_with_no_store(self, client, poisoned, monkeypatch, raw):
        resp, body, redis, _ = _get(client, monkeypatch, raw)
        assert resp.status_code == 200, body
        assert resp.headers["cache-control"] == "no-store"
        assert redis.gets == [KEY]

    def test_the_handler_takes_no_database_dependency_and_no_work_input(self):
        assert set(inspect.signature(ae.schedule_accuracy_cached).parameters) == {"request", "secret"}
        route = next(r for r in ae.router.routes if getattr(r, "path", "") == "/schedule/accuracy/cached")
        assert route.methods == {"GET"}
        assert all(d.call is not ae.get_db for d in route.dependant.dependencies)
        assert [p.name for p in route.dependant.query_params] == ["secret"]

    @pytest.mark.parametrize("query", ["?days=7", "?refresh=1", "?bust=1", "?days=0&refresh=true"])
    def test_window_and_refresh_inputs_change_nothing(self, client, poisoned, monkeypatch, raw, query):
        resp, body, redis, _ = _get(client, monkeypatch, raw, query=query)
        assert resp.status_code == 200
        assert body["payload"] == json.loads(raw)
        assert redis.gets == [KEY]


# ---------------------------------------------------------------------------
# The reader: bound to the producer's bytes
# ---------------------------------------------------------------------------


class TestBinding:
    def test_the_producers_bytes_are_served_whole_with_their_clock(self, client, poisoned, monkeypatch, raw):
        now = T0 + timedelta(minutes=7)
        resp, body, _, _ = _get(client, monkeypatch, raw, now=now)
        assert resp.status_code == 200
        assert set(body) == ENVELOPE_KEYS
        assert body["payload"] == json.loads(raw)
        assert body["payload"]["accuracy"]["sports"] == EXPECTED_SPORTS
        assert (body["cache_state"], body["reason"]) == ("hit", "saved_snapshot")
        assert (body["served_key"], body["served_from"]) == (KEY, "primary")
        assert body["saved_bytes"] == len(raw.encode())
        assert body["generated_at"] == T0.isoformat()
        assert body["age_seconds"] == 420.0
        assert body["freshness_basis"] == "age_from_as_of_the_window_was_cut_from"
        assert body["max_saved_bytes"] == ae.SCHEDULE_ACCURACY_MAX_BYTES

    def test_the_served_cards_equal_the_legacy_routes_cards(self, client, poisoned, monkeypatch, raw,
                                                            legacy_cards):
        _, body, _, _ = _get(client, monkeypatch, raw)
        legacy = legacy_cards
        assert body["payload"]["accuracy"] == legacy
        assert list(body["payload"]["accuracy"]["sports"]) == list(legacy["sports"])

    def test_a_complete_empty_window_is_served_as_a_measured_empty_answer(self, client, poisoned,
                                                                          monkeypatch, raw_empty):
        resp, body, _, _ = _get(client, monkeypatch, raw_empty)
        assert resp.status_code == 200 and body["cache_state"] == "hit"
        assert body["payload"]["accuracy"]["sports"] == {}

    @pytest.mark.parametrize("age", [0, 60, 3599, 86400 * 30])
    def test_a_hit_is_aged_but_never_called_fresh(self, client, poisoned, monkeypatch, raw, age):
        _, body, _, _ = _get(client, monkeypatch, raw, now=T0 + timedelta(seconds=age))
        assert body["freshness"] == "unreviewed" and body["age_seconds"] == age

    def test_a_clock_in_the_future_is_unknown(self, client, poisoned, monkeypatch, raw):
        resp, body, _, _ = _get(client, monkeypatch, raw, now=T0 - timedelta(seconds=1))
        assert resp.status_code == 200
        assert (body["freshness"], body["reason"]) == ("unknown", "generated_at_in_future")
        assert body["age_seconds"] == -1.0


# ---------------------------------------------------------------------------
# The reader: every non-evidence state is its own state and carries no numbers
# ---------------------------------------------------------------------------


def _sport(doc, name="basketball_nba"):
    return doc["accuracy"]["sports"][name]


MUTATIONS = {
    "unsupported_schema_version": lambda d: d.update(schema_version=2),
    "unsupported_schema_version:bool": lambda d: d.update(schema_version=True),
    "invalid_generated_at:naive": lambda d: d.update(as_of="2026-10-20T18:00:00",
                                                     generated_at="2026-10-20T18:00:00"),
    "invalid_generated_at:mismatch": lambda d: d.update(generated_at="2026-10-20T18:00:01+00:00"),
    "timestamps_out_of_order": lambda d: d.update(observation_finished_at="2026-10-20T17:59:59+00:00"),
    "invalid_window:days": lambda d: d["window"].update(days=7),
    "invalid_window:start": lambda d: d["window"].update(start="2026-10-06T18:00:01+00:00"),
    "invalid_window:end": lambda d: d["window"].update(end="2026-10-22T18:00:00+00:00"),
    "invalid_window:column": lambda d: d["window"].update(column="events.created_at"),
    "invalid_window:exclusive": lambda d: d["window"].update(start_inclusive=False),
    "invalid_window:period": lambda d: d["accuracy"].update(period_days=7),
    "invalid_transaction:isolation": lambda d: d["transaction"].update(isolation="read committed"),
    "invalid_transaction:writable": lambda d: d["transaction"].update(read_only=False),
    "invalid_payload:extra": lambda d: d.update(extra=1),
    "invalid_payload:missing": lambda d: d.pop("window"),
    "invalid_accuracy:extra": lambda d: d["accuracy"].update(note="x"),
    "invalid_accuracy:sports_list": lambda d: d["accuracy"].update(sports=[]),
    "invalid_sport:extra": lambda d: _sport(d).update(colour="red"),
    "invalid_sport:empty_name": lambda d: d["accuracy"]["sports"].update({"": _sport(d)}),
    "invalid_denominator:zero": lambda d: _sport(d).update(total=0),
    "invalid_denominator:string": lambda d: _sport(d).update(total="3"),
    "invalid_sources:missing": lambda d: _sport(d)["sources"].pop("statpal"),
    "invalid_count:negative": lambda d: _sport(d)["sources"].update(espn=-1),
    "invalid_count:null": lambda d: _sport(d)["sources"].update(espn=None),
    "count_exceeds_total": lambda d: _sport(d)["sources"].update(odds_api=4),
    "invalid_commence_time_sources:empty": lambda d: _sport(d).update(commence_time_sources={}),
    "invalid_commence_time_sources:zero": lambda d: _sport(d)["commence_time_sources"].update(kalshi=0),
    "counts_do_not_reconcile:provenance": lambda d: _sport(d)["commence_time_sources"].update(espn=3),
    "invalid_rate:pct": lambda d: _sport(d).update(odds_api_linked_pct=101),
    "invalid_rate:null": lambda d: _sport(d).update(odds_api_linked_pct=None),
    "invalid_rate:rating": lambda d: _sport(d).update(reliability="GREEN"),
    "counts_do_not_reconcile:summary": lambda d: d["accuracy"]["summary"].update(total_sports=6),
    "counts_do_not_reconcile:summary_bool": lambda d: d["accuracy"]["summary"].update(low_reliability=True),
    "invalid_summary": lambda d: d["accuracy"]["summary"].pop("low_reliability"),
}


class TestStates:
    def test_miss_is_202_with_no_numbers(self, client, poisoned, monkeypatch):
        resp, body, redis, _ = _get(client, monkeypatch, None)
        assert resp.status_code == 202
        assert (body["cache_state"], body["reason"]) == ("miss", "no_saved_snapshot")
        assert body["served_key"] is None and body["saved_bytes"] is None
        _assert_no_numbers(body)
        assert redis.gets == [KEY]

    def test_an_unreadable_cache_is_503_with_a_safe_code(self, client, poisoned, monkeypatch):
        redis = ReaderRedis(get_exc=ConnectionError("url-sentinel-847 in the exception text"))
        resp, body, _, _ = _get(client, monkeypatch, redis)
        assert resp.status_code == 503
        assert (body["cache_state"], body["reason"]) == ("error", "redis_unavailable")
        _assert_no_numbers(body)
        assert "url-sentinel-847" not in resp.text

    def test_oversized_bytes_are_refused_without_being_decoded(self, client, poisoned, monkeypatch, raw):
        monkeypatch.setattr(ae, "SCHEDULE_ACCURACY_MAX_BYTES", len(raw.encode()) - 1)

        def no_decode(*a, **k):
            raise AssertionError("oversized bytes were decoded")

        monkeypatch.setattr(ssr, "strict_loads", no_decode)
        resp, body, _, _ = _get(client, monkeypatch, raw)
        assert resp.status_code == 503
        assert (body["cache_state"], body["reason"]) == ("oversized", "saved_snapshot_exceeds_read_bound")
        assert body["saved_bytes"] == len(raw.encode()) and body["served_key"] == KEY
        _assert_no_numbers(body)

    def test_exactly_at_the_bound_is_read(self, client, poisoned, monkeypatch, raw):
        monkeypatch.setattr(ae, "SCHEDULE_ACCURACY_MAX_BYTES", len(raw.encode()))
        resp, body, _, _ = _get(client, monkeypatch, raw)
        assert resp.status_code == 200 and body["cache_state"] == "hit"

    @pytest.mark.parametrize("name", sorted(MUTATIONS))
    def test_each_named_mutation_is_refused_and_the_original_passes(self, client, poisoned, monkeypatch,
                                                                    raw, name):
        ok, ok_body, _, _ = _get(client, monkeypatch, raw)
        assert ok.status_code == 200 and ok_body["cache_state"] == "hit"
        doc = json.loads(raw)
        MUTATIONS[name](doc)
        resp, body, _, _ = _get(client, monkeypatch, json.dumps(doc))
        assert resp.status_code == 503, (name, body)
        assert (body["cache_state"], body["reason"]) == ("malformed", name.split(":")[0])
        assert body["served_key"] == KEY
        _assert_no_numbers(body)

    @pytest.mark.parametrize("bad, reason", [
        ("", "not_json"),
        ("{not json", "not_json"),
        (b"\xff\xfe", "not_json"),
        ("[" * 100000 + "]" * 100000, "not_json"),
        ("[]", "invalid_payload"),
        ("null", "invalid_payload"),
    ])
    def test_unusable_bytes_are_typed_refusals(self, client, poisoned, monkeypatch, bad, reason):
        resp, body, _, _ = _get(client, monkeypatch, bad)
        assert resp.status_code == 503
        assert (body["cache_state"], body["reason"]) == ("malformed", reason)
        _assert_no_numbers(body)

    @pytest.mark.parametrize("token", ["NaN", "Infinity", "1e400"])
    def test_a_non_finite_rate_is_refused_not_encoded(self, client, poisoned, monkeypatch, raw, token):
        doc_raw = raw.replace('"odds_api_linked_pct":66.7', f'"odds_api_linked_pct":{token}', 1)
        assert doc_raw != raw
        resp, body, _, _ = _get(client, monkeypatch, doc_raw)
        assert resp.status_code == 503
        assert (body["cache_state"], body["reason"]) == ("malformed", "non_finite_number")


class TestBoundedRead:
    def test_the_reader_reuses_the_existing_request_path_signature(self, client, poisoned, monkeypatch):
        _, _, _, calls = _get(client, monkeypatch, None)
        assert calls == [{"socket_timeout": 0.5, "fast_fail": True}]

    async def test_a_stall_inside_the_client_is_cut_at_the_deadline(self, monkeypatch):
        release = threading.Event()

        class Stalling:
            def get(self, key):
                release.wait(10)
                return None

        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda **k: Stalling())
        monkeypatch.setattr(ae, "SCHEDULE_ACCURACY_READ_DEADLINE_S", 0.2)
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        tick_task = asyncio.create_task(ticker())
        started = time.monotonic()
        try:
            status, body = await ae.read_schedule_accuracy_saved()
        finally:
            elapsed = time.monotonic() - started
            tick_task.cancel()
            release.set()
        assert (status, body["cache_state"], body["reason"]) == (503, "error", "read_deadline_exceeded")
        assert body["payload"] is None
        assert 0.2 <= elapsed < 0.6
        assert ticks >= 10  # the read is off the event loop

    def test_the_deadline_is_inside_the_console_page_budget(self):
        assert ae.SCHEDULE_ACCURACY_READ_DEADLINE_S == 1.0

    def test_the_reader_reads_one_fixed_key(self):
        src = inspect.getsource(ae.read_schedule_accuracy_saved)
        assert "(SCHEDULE_ACCURACY_CACHE_KEY,)" in src
        assert ae.SCHEDULE_ACCURACY_CACHE_KEY == KEY


def _code_without_docstrings(fn) -> str:
    tree = ast.parse(inspect.getsource(fn))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.body \
                and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
            node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_the_reader_source_has_no_compute_or_write_path():
    src = _code_without_docstrings(ae.read_schedule_accuracy_saved) \
        + _code_without_docstrings(ae.schedule_accuracy_cached)
    for forbidden in ("_compute_schedule_accuracy", "get_db", "get_task_session", ".set(",
                      "send_task", "delay(", PRODUCER):
        assert forbidden not in src, forbidden
    # The snapshot contract is the writer's own pre-publication check too.
    assert "check_schedule_accuracy_snapshot(strict_loads(raw))" in inspect.getsource(
        getattr(cov, PRODUCER))
