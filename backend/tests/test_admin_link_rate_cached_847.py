"""#847 — the Correctness Console's link rate, served from the saved snapshot ONLY.

``GET /api/admin/prediction-markets/link-rate/cached`` reads ``_LINK_RATE_CACHE_KEY``
once, off the event loop, under a total deadline, and answers with a typed state.
Every path — hit, miss, read error, malformed, saved-stale, saved-unavailable,
``?bust=1`` — runs with the compute, the session factories, the producer, task
dispatch and every cache write wired to explode if touched. The legacy
``/prediction-markets/link-rate`` route is exercised only as the control that
proves the poison is armed and that its behaviour is unchanged.

No Redis, database or network is reached from this file.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import math
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.routes import admin, admin_matching as lr
from app.routes.admin_utils import admin_account_identity

TOKEN = "test-admin-token-847-link-rate"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PATH = "/api/admin/prediction-markets/link-rate/cached"
LEGACY = "/api/admin/prediction-markets/link-rate"
KEY = "bainluck:admin:link_rate"
T0 = datetime(2026, 10, 20, 2, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeRedis:
    def __init__(self, value=None, *, get_exc=None):
        self.value = value
        self.get_exc = get_exc
        self.gets = 0
        self.sets: list = []

    def get(self, key):
        self.gets += 1
        assert key == KEY
        if self.get_exc:
            raise self.get_exc
        return self.value

    def set(self, key, value, ex=None):
        self.sets.append((key, value, ex))
        self.value = value


class PoisonRedis(FakeRedis):
    """A cache the saved-only GET may read and must never write."""

    def set(self, *a, **k):
        raise AssertionError("GET wrote the cache")

    setex = delete = expire = getdel = getex = set


def _bucket(sport="basketball", league="NBA", total=10, linked=9, open_total=8, open_linked=7):
    return {
        "sport": sport, "league": league,
        "total": total, "linked": linked, "open_total": open_total, "open_linked": open_linked,
        "linked_anchored": linked, "linked_self_minted": 0,
        "open_linked_anchored": open_linked, "open_linked_self_minted": 0,
        "link_rate": round(open_linked / open_total * 100, 1) if open_total else 0,
        "link_rate_all": round(linked / total * 100, 1) if total else 0,
    }


def _totals(total=10, linked=9, open_total=8, open_linked=7):
    return {
        "total": total, "linked": linked, "open_total": open_total, "open_linked": open_linked,
        "link_rate_pct": 87.5, "link_rate_all_pct": 90.0, "link_rate_raw_pct": 80.0,
        "excluded_upstream_coverage_gap": 1, "excluded_open_upstream_coverage_gap": 1,
    }


def _payload(generated_at=T0, **override):
    p = {
        "generated_at": generated_at.isoformat(),
        "overall": {
            "total_game_markets": 20, "linked": 18,
            "link_rate_pct": 87.5, "link_rate_all_pct": 90.0, "link_rate_raw_pct": 80.0,
            "open_total": 16, "open_linked": 14,
            "denominator_note": "Headline rate uses open markets only.",
            "excluded_stale_open_unlinked": 3, "excluded_non_game_category": 2,
            "excluded_upstream_coverage_gap": 2, "excluded_open_upstream_coverage_gap": 2,
        },
        "kalshi": {"totals": _totals(), "by_sport": [_bucket()],
                   "excluded_from_denominator": {"note": "x", "total": 0, "by_category": {}}},
        "polymarket": {"totals": _totals(), "by_sport": [_bucket(league=None)],
                       "excluded_from_denominator": {"note": "x", "total": 0, "by_category": {}},
                       "denominator_diagnostics": {"note": "y", "sample_excluded_open": []}},
    }
    p.update(override)
    return p


def _blob(payload) -> bytes:
    return json.dumps(payload).encode()


@pytest.fixture
def poisoned(monkeypatch):
    """Everything that could compute, open a session, enqueue or write explodes."""

    def boom(name):
        def _raise(*a, **k):
            raise AssertionError(f"saved-only GET touched {name}")
        return _raise

    monkeypatch.setattr(lr, "_compute_link_rate", boom("_compute_link_rate"))
    monkeypatch.setattr("app.tasks.base.get_task_session", boom("get_task_session"))
    monkeypatch.setattr("app.services.database.async_session_maker", boom("async_session_maker"))
    monkeypatch.setattr("app.tasks.precompute_admin_health._precompute_admin_link_rate",
                        boom("precompute producer"))
    monkeypatch.setattr("app.routes.admin_utils._safe_send_task", boom("task dispatch"))
    from app.tasks import celery_app

    monkeypatch.setattr(celery_app, "send_task", boom("celery send_task"))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    app = FastAPI()
    # Same mount as main.py: admin.router carries admin_matching's router, and
    # every admin router gets the account-identity dependency.
    app.include_router(admin.router, prefix="/api/admin",
                       dependencies=[Depends(admin_account_identity)])

    def _no_db():
        raise AssertionError("GET opened a database session")

    app.dependency_overrides[lr.get_db] = _no_db
    return TestClient(app, raise_server_exceptions=False)


def _serve(monkeypatch, redis, now=T0):
    calls = []

    def factory(*a, **k):
        calls.append(k)
        return redis

    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", factory)
    monkeypatch.setattr(lr, "_link_rate_cached_now", lambda: now)
    return calls


def _get(client, monkeypatch, value, now=T0, query=""):
    redis = value if isinstance(value, FakeRedis) else PoisonRedis(value)
    _serve(monkeypatch, redis, now)
    resp = client.get(PATH + query, headers=AUTH)
    return resp, resp.json(), redis


ENVELOPE_KEYS = {"schema_version", "cache_state", "reason", "freshness", "freshness_basis",
                 "generated_at", "age_seconds", "payload"}


# ---------------------------------------------------------------------------
# Auth comes first; the handler has no database dependency
# ---------------------------------------------------------------------------


class TestAuth:
    def test_no_credentials_is_refused_before_the_cache_is_read(self, client, poisoned, monkeypatch):
        redis = PoisonRedis(_blob(_payload()))
        _serve(monkeypatch, redis)
        assert client.get(PATH).status_code == 403
        assert redis.gets == 0

    def test_a_wrong_token_is_refused_before_the_cache_is_read(self, client, poisoned, monkeypatch):
        redis = PoisonRedis(_blob(_payload()))
        _serve(monkeypatch, redis)
        # The router-level resolver tries the account path for a non-machine
        # token; its session factory is poisoned and it swallows that, so the
        # route's own gate decides — and refuses.
        assert client.get(PATH, headers={"Authorization": "Bearer nope"}).status_code == 403
        assert redis.gets == 0

    def test_a_query_secret_alone_is_refused(self, client, poisoned, monkeypatch):
        redis = PoisonRedis(_blob(_payload()))
        _serve(monkeypatch, redis)
        assert client.get(f"{PATH}?secret={TOKEN}").status_code == 403
        assert redis.gets == 0

    def test_the_machine_token_is_served(self, client, poisoned, monkeypatch):
        redis = PoisonRedis(_blob(_payload()))
        _serve(monkeypatch, redis)
        resp = client.get(PATH, headers=AUTH)
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "no-store"
        assert redis.gets == 1

    def test_a_resolved_admin_account_is_served_through_the_existing_gate(self, client, poisoned,
                                                                          monkeypatch):
        from app.routes import admin_utils

        async def _stamp(request: Request):
            setattr(request.state, admin_utils.ACCOUNT_ADMIN_STATE_ATTR, "alex@example.com")

        client.app.dependency_overrides[admin_account_identity] = _stamp
        redis = PoisonRedis(_blob(_payload()))
        _serve(monkeypatch, redis)
        resp = client.get(PATH, headers={"Authorization": "Bearer some-firebase-id-token"})
        assert resp.status_code == 200
        assert redis.gets == 1

    def test_the_handler_declares_no_database_dependency(self):
        params = inspect.signature(lr.prediction_market_link_rate_cached).parameters
        assert set(params) == {"request", "secret"}
        route = next(r for r in lr.router.routes
                     if getattr(r, "path", "") == "/prediction-markets/link-rate/cached")
        assert route.methods == {"GET"}
        assert route.dependant.dependencies == [] or all(
            d.call is not lr.get_db for d in route.dependant.dependencies)

    def test_the_cached_path_is_its_own_route_and_the_legacy_one_still_exists(self, client):
        paths = {r.path for r in client.app.routes}
        assert PATH in paths and LEGACY in paths


# ---------------------------------------------------------------------------
# Every state in the contract
# ---------------------------------------------------------------------------


class TestStates:
    def test_hit_serves_the_saved_payload_byte_for_byte_with_its_own_clock(self, client, poisoned,
                                                                           monkeypatch):
        saved = _payload()
        resp, body, redis = _get(client, monkeypatch, _blob(saved), now=T0 + timedelta(seconds=754))
        assert resp.status_code == 200
        assert set(body) == ENVELOPE_KEYS
        assert body["schema_version"] == 1
        assert (body["cache_state"], body["reason"], body["freshness"]) == (
            "hit", "saved_snapshot", "unreviewed")
        assert body["payload"] == saved
        assert body["generated_at"] == saved["generated_at"] == T0.isoformat()
        assert body["age_seconds"] == 754
        assert redis.gets == 1

    def test_a_str_value_from_a_decoding_client_is_read_the_same(self, client, poisoned, monkeypatch):
        saved = _payload()
        resp, body, _ = _get(client, monkeypatch, json.dumps(saved), now=T0 + timedelta(seconds=1))
        assert resp.status_code == 200 and body["payload"] == saved

    def test_an_old_snapshot_is_never_labelled_fresh_or_stale_by_an_invented_horizon(
            self, client, poisoned, monkeypatch):
        # No reviewed horizon exists for this payload: a five-hour-old snapshot
        # (impossible under the writers' 3600 s expiry, but bytes are bytes) is
        # still reported with its true age and no verdict.
        resp, body, _ = _get(client, monkeypatch, _blob(_payload()), now=T0 + timedelta(hours=5))
        assert resp.status_code == 200
        assert body["freshness"] == "unreviewed"
        assert body["age_seconds"] == 5 * 3600
        assert body["freshness_basis"] == "age_from_generated_at_stamped_when_compute_returned"

    def test_miss_is_202_with_no_numbers_and_no_repair(self, client, poisoned, monkeypatch):
        resp, body, redis = _get(client, monkeypatch, None)
        assert resp.status_code == 202
        assert set(body) == ENVELOPE_KEYS
        assert (body["cache_state"], body["reason"], body["freshness"]) == (
            "miss", "no_saved_snapshot", "unknown")
        assert body["payload"] is None and body["generated_at"] is None and body["age_seconds"] is None
        assert redis.gets == 1

    def test_an_empty_string_is_not_a_miss(self, client, poisoned, monkeypatch):
        resp, body, _ = _get(client, monkeypatch, b"")
        assert (resp.status_code, body["cache_state"], body["reason"]) == (503, "malformed", "not_json")

    @pytest.mark.parametrize("value", [None, _blob(_payload()), b"{bad", "error"])
    @pytest.mark.parametrize("query", ["?bust=1", "?bust=true&refresh=1", "?secret=x&bust=1"])
    def test_bust_and_refresh_arguments_change_nothing(self, client, poisoned, monkeypatch, value, query):
        import redis as redis_lib

        if value == "error":
            fake = PoisonRedis(get_exc=redis_lib.exceptions.ConnectionError("down"))
            expected = (503, "error")
        else:
            fake = PoisonRedis(value)
            expected = {None: (202, "miss"), b"{bad": (503, "malformed")}.get(value, (200, "hit"))
        resp, body, _ = _get(client, monkeypatch, fake, query=query)
        assert (resp.status_code, body["cache_state"]) == expected
        assert fake.gets == 1

    def test_cache_transport_error_is_503_with_a_safe_code(self, client, poisoned, monkeypatch):
        import redis as redis_lib

        fake = PoisonRedis(get_exc=redis_lib.exceptions.ConnectionError("rediss://user:pw@host secret"))
        resp, body, _ = _get(client, monkeypatch, fake)
        assert resp.status_code == 503
        assert (body["cache_state"], body["reason"], body["freshness"]) == (
            "error", "redis_unavailable", "unknown")
        assert body["payload"] is None
        assert "pw" not in resp.text and "rediss" not in resp.text and "secret" not in resp.text

    def test_a_saved_stale_marker_is_preserved_and_named(self, client, poisoned, monkeypatch):
        saved = _payload(stale=True, stale_reason="compute_timeout")
        resp, body, _ = _get(client, monkeypatch, _blob(saved), now=T0 + timedelta(seconds=60))
        assert resp.status_code == 200
        assert (body["cache_state"], body["reason"]) == ("hit", "saved_snapshot_marked_stale")
        assert body["payload"]["stale"] is True
        assert body["payload"]["stale_reason"] == "compute_timeout"

    def test_a_false_stale_marker_is_an_ordinary_hit(self, client, poisoned, monkeypatch):
        resp, body, _ = _get(client, monkeypatch, _blob(_payload(stale=False)))
        assert body["reason"] == "saved_snapshot" and body["payload"]["stale"] is False

    def test_the_legacy_no_data_shape_is_503_unavailable_with_its_markers_kept(self, client, poisoned,
                                                                                monkeypatch):
        # Exactly the dict the legacy GET degrades to when it has nothing.
        saved = {"generated_at": T0.isoformat(), "stale": True, "unavailable": True,
                 "stale_reason": "compute_error", "overall": {}, "kalshi": {}, "polymarket": {}}
        resp, body, _ = _get(client, monkeypatch, _blob(saved), now=T0 + timedelta(seconds=30))
        assert resp.status_code == 503
        assert (body["cache_state"], body["reason"], body["freshness"]) == (
            "unavailable", "saved_snapshot_unavailable", "unknown")
        assert body["payload"] == saved
        assert body["age_seconds"] == 30

    def test_a_generated_at_in_the_future_is_reported_not_trusted(self, client, poisoned, monkeypatch):
        resp, body, _ = _get(client, monkeypatch, _blob(_payload()), now=T0 - timedelta(seconds=5))
        assert (resp.status_code, body["cache_state"], body["freshness"], body["reason"]) == (
            200, "hit", "unknown", "generated_at_in_future")
        assert body["age_seconds"] == -5

    def test_a_real_zero_is_kept_as_a_zero(self, client, poisoned, monkeypatch):
        saved = _payload()
        saved["kalshi"]["by_sport"] = [_bucket(total=3, linked=0, open_total=0, open_linked=0)]
        resp, body, _ = _get(client, monkeypatch, _blob(saved))
        assert resp.status_code == 200
        assert body["payload"]["kalshi"]["by_sport"][0]["link_rate"] == 0
        assert body["payload"]["kalshi"]["by_sport"][0]["open_total"] == 0


# ---------------------------------------------------------------------------
# The contract: what the producer writes validates; broken bytes never 500
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ProducerSession:
    """Answers ``_compute_link_rate``'s three statements in order."""

    def __init__(self, kalshi_rows, poly_rows):
        self._results = [_Result([]), _Result(kalshi_rows), _Result(poly_rows)]
        self.statements = 0

    async def execute(self, stmt, *a, **k):
        self.statements += 1
        return self._results.pop(0)


def _market(**kw):
    base = dict(sport="basketball", league="NBA", event_id=None, status="open", category="game",
                event_espn_id=None, event_external_id=None)
    base.update(kw)
    return SimpleNamespace(**base)


async def _real_producer_bytes(kalshi_rows, poly_rows) -> bytes:
    # The producer's own compute and serialization (precompute_admin_link_rate
    # writes ``json.dumps(payload)``), with only the database faked.
    session = _ProducerSession(kalshi_rows, poly_rows)
    payload = await lr._compute_link_rate(session, stmt_timeout_s=90)
    assert session.statements == 3
    return json.dumps(payload).encode()


class TestProducerContract:
    async def test_the_real_producers_output_round_trips_as_a_hit(self, monkeypatch):
        today = datetime.now(timezone.utc).strftime("%y%b%d").upper()
        kalshi = [
            _market(event_id=1, external_id=f"KXNBAGAME-{today}BOSNYK", name="Celtics vs Knicks",
                    event_espn_id="401"),
            _market(external_id=f"KXNBAGAME-{today}LALGSW", name="Lakers vs Warriors"),
        ]
        poly = [_market(event_id=2, external_id="123", name="Celtics vs. Knicks", event_espn_id="401")]
        raw = await _real_producer_bytes(kalshi, poly)
        saved = json.loads(raw)
        assert saved["kalshi"]["totals"]["total"] == 2  # the fixture really reached the payload

        redis = PoisonRedis(raw)
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda **k: redis)
        status, body = await lr.read_link_rate_cache()
        assert (status, body["cache_state"]) == (200, "hit")
        assert body["payload"] == saved
        assert body["generated_at"] == saved["generated_at"]

    async def test_the_real_producers_empty_output_is_a_hit_not_a_miss(self, monkeypatch):
        raw = await _real_producer_bytes([], [])
        redis = PoisonRedis(raw)
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda **k: redis)
        status, body = await lr.read_link_rate_cache()
        assert (status, body["cache_state"]) == (200, "hit")
        assert body["payload"]["overall"]["total_game_markets"] == 0
        assert body["payload"]["kalshi"]["by_sport"] == []


def _set(path, value):
    def mutate(p):
        target = p
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    return mutate


def _drop(path):
    def mutate(p):
        target = p
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]
    return mutate


# Every field the reader validates, at every level it validates it.
VALIDATED_PATHS = [
    ("generated_at",),
    ("overall",),
    ("kalshi",), ("polymarket",),
    ("kalshi", "totals"), ("polymarket", "totals"),
    ("kalshi", "by_sport"), ("polymarket", "by_sport"),
    ("kalshi", "by_sport", 0), ("polymarket", "by_sport", 0),
    *[("overall", k) for k in ("total_game_markets", "linked", "open_total", "open_linked",
                               "link_rate_pct", "link_rate_all_pct")],
    *[(v, "totals", k) for v in ("kalshi", "polymarket")
      for k in ("total", "linked", "open_total", "open_linked", "link_rate_pct", "link_rate_all_pct")],
    *[(v, "by_sport", 0, k) for v in ("kalshi", "polymarket")
      for k in ("sport", "total", "linked", "open_total", "open_linked", "link_rate", "link_rate_all")],
]
# Wrong at EVERY validated field (a bool is never a count, a rate or a name);
# ``[]`` too, except as ``by_sport`` itself, where an empty list is a real answer.
ALWAYS_BAD = [{}, None, True, False]
# ``10**400`` is past float range: a rate check that converts before comparing
# raises OverflowError instead of rejecting it.
BAD_VALUES = [*ALWAYS_BAD, [], "x", -1, 1.5, 101, 10**30, 10**400, -(10**400)]


def _bad_cases():
    cases = []
    for path in VALIDATED_PATHS:
        for bad in BAD_VALUES:
            p = _payload()
            _set(path, bad)(p)
            if p == _payload():
                continue
            try:
                lr._validate_link_rate_payload(json.loads(json.dumps(p)))
            except lr._LinkRatePayloadInvalid:
                cases.append(("/".join(map(str, path)), bad))
                continue
            # A value the contract legitimately allows at that spot (a rate of
            # 1.5, a count of 10**30 with totals that still cover it, …).
    return cases


class TestMalformed:
    def test_the_fuzz_corpus_actually_rejects_something_at_every_validated_path(self):
        rejected = {path for path, _ in _bad_cases()}
        assert rejected == {"/".join(map(str, p)) for p in VALIDATED_PATHS}

    @pytest.mark.parametrize("path", VALIDATED_PATHS, ids=lambda p: "/".join(map(str, p)))
    def test_every_wrong_type_at_every_validated_field_is_a_typed_503_never_a_500(
            self, client, poisoned, monkeypatch, path):
        for bad in BAD_VALUES:
            p = _payload()
            _set(path, bad)(p)
            resp, body, redis = _get(client, monkeypatch, _blob(p))
            assert resp.status_code in (200, 503), (path, bad, resp.status_code)
            if any(bad is b for b in ALWAYS_BAD) or (bad == [] and path[-1] != "by_sport"):
                assert resp.status_code == 503, (path, bad)
            if resp.status_code == 503:
                assert body["cache_state"] == "malformed" and body["payload"] is None, (path, bad)
                assert set(body) == ENVELOPE_KEYS

    @pytest.mark.parametrize("path", [p for p in VALIDATED_PATHS if p not in {("overall",)}],
                             ids=lambda p: "/".join(map(str, p)))
    def test_every_required_field_missing_is_malformed(self, client, poisoned, monkeypatch, path):
        p = _payload()
        if path[-1] == 0:
            p[path[0]]["by_sport"] = ["not a bucket"]
        else:
            _drop(path)(p)
        resp, body, _ = _get(client, monkeypatch, _blob(p))
        assert (resp.status_code, body["cache_state"]) == (503, "malformed"), path

    @pytest.mark.parametrize("raw,reason", [
        (b"{not json", "not_json"),
        (b"\xff\xfe", "not_json"),
        (b"[" * 100000 + b"]" * 100000, "not_json"),
        (b"[1, 2]", "invalid_payload"),
        (b'"a string"', "invalid_payload"),
        (_blob({**_payload(), "generated_at": "yesterday"}), "invalid_generated_at"),
        (_blob({**_payload(), "generated_at": "2026-10-20T02:00:00"}), "invalid_generated_at"),
        (_blob({**_payload(), "generated_at": 1760925600}), "invalid_generated_at"),
        (_blob({**_payload(), "stale": "yes"}), "invalid_marker"),
        (_blob({**_payload(), "unavailable": 1}), "invalid_marker"),
        (_blob({**_payload(), "stale_reason": ["compute_error"]}), "invalid_marker"),
        (_blob(_payload(overall={**_payload()["overall"], "linked": True})), "invalid_count"),
        (_blob({**_payload(), "kalshi": {"totals": _totals(), "by_sport": [_bucket(open_linked=False)]}}),
         "invalid_count"),
        (_blob(_payload(overall={**_payload()["overall"], "linked": 21})), "count_exceeds_total"),
        (_blob(_payload(overall={**_payload()["overall"], "open_linked": 17})), "count_exceeds_total"),
        (_blob(_payload(overall={**_payload()["overall"], "open_total": 21})), "count_exceeds_total"),
        (_blob(_payload(overall={**_payload()["overall"], "link_rate_raw_pct": "80"})), "invalid_rate"),
        (_blob(_payload(overall={**_payload()["overall"], "link_rate_raw_pct": -0.1})), "invalid_rate"),
        (_blob({**_payload(), "kalshi": {"totals": _totals(), "by_sport": [_bucket(sport="")]}}),
         "invalid_bucket"),
        (_blob({**_payload(), "kalshi": {"totals": _totals(), "by_sport": [_bucket(league=7)]}}),
         "invalid_bucket"),
        (_blob({**_payload(), "kalshi": {"totals": _totals(), "by_sport": {"a": 1}}}), "invalid_section"),
    ])
    def test_named_malformed_bytes(self, client, poisoned, monkeypatch, raw, reason):
        resp, body, _ = _get(client, monkeypatch, raw)
        assert resp.status_code == 503
        assert (body["cache_state"], body["reason"], body["freshness"]) == ("malformed", reason, "unknown")
        assert body["payload"] is None and body["generated_at"] is None

    @pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
    def test_a_non_finite_number_anywhere_is_malformed_not_an_encoder_500(self, client, poisoned,
                                                                          monkeypatch, token):
        # Placed in a field the reader does NOT validate: without strict parsing
        # it would reach the response encoder, which refuses it.
        raw = json.dumps(_payload()).replace('"excluded_non_game_category": 2',
                                             f'"excluded_non_game_category": {token}').encode()
        assert token.encode() in raw
        resp, body, _ = _get(client, monkeypatch, raw)
        assert (resp.status_code, body["cache_state"], body["reason"]) == (
            503, "malformed", "non_finite_number")

    @pytest.mark.parametrize("path", [("overall", "link_rate_pct"), ("kalshi", "totals", "link_rate_pct"),
                                      ("polymarket", "by_sport", 0, "link_rate"),
                                      ("overall", "link_rate_raw_pct")],
                             ids=lambda p: "/".join(map(str, p)))
    @pytest.mark.parametrize("huge", [10**400, -(10**400)])
    def test_an_integer_rate_past_float_range_is_invalid_not_an_overflow_500(
            self, client, poisoned, monkeypatch, path, huge):
        p = _payload()
        _set(path, huge)(p)
        with pytest.raises(OverflowError):
            math.isfinite(huge)  # the conversion the reader must never reach
        resp, body, _ = _get(client, monkeypatch, _blob(p))
        assert (resp.status_code, body["cache_state"], body["reason"]) == (
            503, "malformed", "invalid_rate")
        assert body["payload"] is None

    # ``1e400`` is a valid JSON number token, not a NaN/Infinity literal, so
    # ``parse_constant`` never sees it; ``float`` makes it infinity.
    @pytest.mark.parametrize("where", ["extra", "nested_extra", "list_extra", "required_rate"])
    @pytest.mark.parametrize("token", ["1e400", "-1e400", "1.5E+999"])
    def test_an_exponent_overflow_anywhere_is_malformed_not_an_encoder_500(
            self, client, poisoned, monkeypatch, where, token):
        p = _payload()
        sentinel = "EXPONENT_SENTINEL"
        if where == "extra":
            p["extension"] = sentinel
        elif where == "nested_extra":
            p["polymarket"]["denominator_diagnostics"]["spread"] = {"max": sentinel}
        elif where == "list_extra":
            p["kalshi"]["by_sport"][0]["history"] = [1.5, sentinel]
        else:
            p["overall"]["link_rate_pct"] = sentinel
        raw = json.dumps(p).replace(f'"{sentinel}"', token).encode()
        assert token.encode() in raw and math.isinf(float(token))
        resp, body, _ = _get(client, monkeypatch, raw)
        assert (resp.status_code, body["cache_state"], body["reason"]) == (
            503, "malformed", "non_finite_number")
        assert body["payload"] is None and set(body) == ENVELOPE_KEYS

    def test_legitimate_finite_extensions_are_preserved_exactly(self, client, poisoned, monkeypatch):
        # The control for both corrections: big-but-finite floats, an integer
        # past float range OUTSIDE a rate field, negatives and exponents all
        # survive the strict parse unchanged — nothing is dropped or coerced.
        saved = _payload(extension={"max_float": 1.7976931348623157e308, "tiny": -2.5e-10,
                                    "big_int": 10**400, "neg": -3, "series": [0.0, 1e300]})
        saved["overall"]["link_rate_pct"] = 100
        saved["kalshi"]["by_sport"][0]["link_rate"] = 0
        raw = json.dumps(saved).replace("1e+300", "1E300").encode()
        assert b"1E300" in raw
        resp, body, _ = _get(client, monkeypatch, raw)
        assert (resp.status_code, body["cache_state"]) == (200, "hit")
        assert body["payload"] == saved
        assert body["payload"]["extension"]["big_int"] == 10**400

    def test_unknown_extra_fields_pass_through_untouched(self, client, poisoned, monkeypatch):
        saved = _payload(future_field={"nested": [1, 2]})
        saved["kalshi"]["by_sport"][0]["new_split"] = 4
        resp, body, _ = _get(client, monkeypatch, _blob(saved))
        assert resp.status_code == 200 and body["payload"] == saved


# ---------------------------------------------------------------------------
# Bounded, off-loop IO
# ---------------------------------------------------------------------------


class TestBoundedRead:
    def test_the_reader_reuses_the_existing_request_path_signature(self, client, poisoned, monkeypatch):
        calls = _serve(monkeypatch, PoisonRedis(None))
        client.get(PATH, headers=AUTH)
        assert calls == [{"socket_timeout": 0.5, "fast_fail": True}]

    def test_that_signature_is_fast_fail_with_one_retry_and_a_short_pool_wait(self, monkeypatch):
        # What the client is made of (factory patched, no connection opened).
        # Its CONNECT timeout is still the 5 s default — which is why the reader
        # carries its own total deadline.
        from app.tasks import redis_state

        built = {}

        def factory(url, **kwargs):
            built.update(kwargs)
            return object()

        redis_state.reset_redis_client_cache()
        monkeypatch.setattr(redis_state.redis, "from_url", factory)
        try:
            lr._link_rate_cached_client()
        finally:
            redis_state.reset_redis_client_cache()
        assert built["socket_timeout"] == 0.5
        assert built["socket_connect_timeout"] == 5.0
        assert built["retry"]._retries == 1
        assert built["health_check_interval"] == 25
        assert redis_state._REDIS_POOL_WAIT_FAST_FAIL < 0.5
        assert lr._LINK_RATE_CACHED_READ_DEADLINE_S < built["socket_connect_timeout"]

    @pytest.mark.parametrize("stall", ["pool_wait", "connect", "health_check_ping", "get_then_retry"])
    async def test_any_stall_inside_the_client_is_cut_at_the_deadline(self, monkeypatch, stall):
        release = threading.Event()
        entered = []

        class Stalling(PoisonRedis):
            def get(self, key):
                entered.append(stall)
                release.wait(10)  # stands in for a blocked socket/pool in that stage
                return None

        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda **k: Stalling())
        monkeypatch.setattr(lr, "_compute_link_rate", None)
        monkeypatch.setattr(lr, "_LINK_RATE_CACHED_READ_DEADLINE_S", 0.2)
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        tick_task = asyncio.create_task(ticker())
        started = time.monotonic()
        try:
            status, body = await lr.read_link_rate_cache()
        finally:
            elapsed = time.monotonic() - started
            tick_task.cancel()
            release.set()
        assert entered == [stall]
        assert (status, body["cache_state"], body["reason"]) == (503, "error", "read_deadline_exceeded")
        assert 0.2 <= elapsed < 0.6
        # The loop kept serving others for the whole wait: the read is off-loop.
        assert ticks >= 10

    async def test_client_construction_is_inside_the_deadline_too(self, monkeypatch):
        release = threading.Event()

        def slow_factory(**k):
            release.wait(10)
            return PoisonRedis(None)

        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", slow_factory)
        monkeypatch.setattr(lr, "_LINK_RATE_CACHED_READ_DEADLINE_S", 0.15)
        started = time.monotonic()
        try:
            status, body = await lr.read_link_rate_cache()
        finally:
            release.set()
        assert status == 503 and body["reason"] == "read_deadline_exceeded"
        assert time.monotonic() - started < 0.5

    def test_the_whole_authenticated_request_is_bounded_by_the_deadline(self, client, poisoned,
                                                                         monkeypatch):
        release = threading.Event()

        class Stalling(PoisonRedis):
            def get(self, key):
                release.wait(10)
                return _blob(_payload())

        _serve(monkeypatch, Stalling())
        monkeypatch.setattr(lr, "_LINK_RATE_CACHED_READ_DEADLINE_S", 0.2)
        # A long-lived loop, as in the server. A bare TestClient closes its loop
        # after every request, and closing waits for the still-blocked executor
        # thread — that would time the harness's teardown, not the response.
        with client:
            client.get(PATH, headers=AUTH)  # warm the portal outside the clock
            started = time.monotonic()
            try:
                resp = client.get(PATH, headers=AUTH)
            finally:
                elapsed = time.monotonic() - started
                release.set()
        assert resp.status_code == 503 and resp.json()["reason"] == "read_deadline_exceeded"
        assert elapsed < 1.0

    @pytest.mark.parametrize("exc_name", ["ConnectionError", "TimeoutError", "MaxConnectionsError"])
    async def test_client_errors_are_a_typed_cache_error(self, monkeypatch, exc_name):
        import redis as redis_lib

        exc_cls = getattr(redis_lib.exceptions, exc_name)
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client",
                            lambda **k: PoisonRedis(get_exc=exc_cls("Timeout connecting to server")))
        status, body = await lr.read_link_rate_cache()
        assert (status, body["cache_state"], body["reason"]) == (503, "error", "redis_unavailable")

    def test_the_production_deadline_leaves_room_in_the_console_budget(self):
        assert 0 < lr._LINK_RATE_CACHED_READ_DEADLINE_S <= 1.0


# ---------------------------------------------------------------------------
# Controls: the poison is armed, and the legacy route is unchanged
# ---------------------------------------------------------------------------


class TestLegacyControl:
    def test_the_poison_is_armed_the_legacy_route_trips_it_on_a_miss(self, client, poisoned, monkeypatch):
        # Same fixture, same miss — the legacy route computes inline, so it hits
        # the poisoned database dependency. If this ever passes quietly, the
        # saved-only tests above prove nothing.
        redis = FakeRedis(None)
        _serve(monkeypatch, redis)
        resp = client.get(LEGACY, headers=AUTH)
        assert resp.status_code == 500
        assert redis.sets == []

    def test_the_legacy_route_still_computes_and_rewarms_on_a_miss(self, client, monkeypatch):
        computed = _payload()
        calls = []

        async def fake_compute(db):
            calls.append(db)
            return computed

        client.app.dependency_overrides[lr.get_db] = lambda: "db"
        monkeypatch.setattr(lr, "_compute_link_rate", fake_compute)
        redis = FakeRedis(None)
        _serve(monkeypatch, redis)
        resp = client.get(LEGACY, headers=AUTH)
        assert resp.status_code == 200 and resp.json() == computed
        assert calls == ["db"]
        assert redis.sets == [(KEY, json.dumps(computed), 3600)]

    def test_the_legacy_route_still_serves_a_warm_cache_without_computing(self, client, poisoned,
                                                                          monkeypatch):
        saved = _payload()
        client.app.dependency_overrides[lr.get_db] = lambda: "db"
        redis = PoisonRedis(_blob(saved))
        _serve(monkeypatch, redis)
        resp = client.get(LEGACY, headers=AUTH)
        assert resp.status_code == 200 and resp.json() == saved

    def test_the_cache_key_is_the_one_both_writers_use(self):
        import ast
        from pathlib import Path

        src = Path(inspect.getsourcefile(lr)).read_text()
        assert lr._LINK_RATE_CACHE_KEY == KEY
        producer = Path(inspect.getsourcefile(lr)).parents[1] / "tasks" / "precompute_admin_health.py"
        assert f'"{KEY}"' in producer.read_text()
        # The saved-only reader reads the shared constant and writes nothing.
        tree = ast.parse(src)
        fns = {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        reader_names = ("_blocking_link_rate_get", "_read_link_rate_cache_raw", "read_link_rate_cache",
                        "prediction_market_link_rate_cached", "_validate_link_rate_payload",
                        "_link_rate_cached_response", "_link_rate_cached_client")
        for name in reader_names:
            fn = fns[name]
            stmts = fn.body
            if stmts and isinstance(stmts[0], ast.Expr) and isinstance(stmts[0].value, ast.Constant):
                stmts = stmts[1:]  # the docstring may NAME what the code must not do
            body = "\n".join(ast.unparse(st) for st in stmts) + "".join(
                ast.unparse(d) for d in fn.decorator_list) + ast.unparse(fn.args)
            for forbidden in (".set(", "setex", ".delete(", "_compute_link_rate", "get_db",
                              "send_task", "delay(", "apply_async", "session"):
                assert forbidden not in body, (name, forbidden)
        assert "_LINK_RATE_CACHE_KEY" in ast.unparse(fns["_blocking_link_rate_get"])


def test_age_is_measured_from_the_saved_clock_only(monkeypatch):
    # The request clock ages the snapshot; it never replaces the saved stamp.
    saved = _payload(generated_at=T0.astimezone(timezone(timedelta(hours=-7))))
    redis = PoisonRedis(_blob(saved))
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda **k: redis)
    monkeypatch.setattr(lr, "_link_rate_cached_now", lambda: T0 + timedelta(seconds=90))
    status, body = asyncio.run(lr.read_link_rate_cache())
    assert status == 200
    assert body["generated_at"] == saved["generated_at"]  # original offset kept verbatim
    assert body["generated_at"].endswith("-07:00")
    assert math.isclose(body["age_seconds"], 90)
