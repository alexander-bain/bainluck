"""#847 — the Correctness Console's event-source coverage, served from saved evidence.

Two halves, both exercised only against in-process fakes (no Redis, database or
network is ever reached from this file):

* ``GET /api/admin/event-source-coverage/cached`` reads ONE cache key under a
  total deadline, off the event loop, and answers with a typed state. Every
  path — miss, error, malformed, partial, stale, expired, ``?bust=1`` — is run
  with the coverage helper, the task session, the dashboard builders, the
  producer, task dispatch and every cache write wired to explode if touched.
* ``_precompute_admin_event_source_coverage`` is INERT: the guards below pin
  that nothing registers, schedules or calls it. Run here against a fake
  session, it must execute READ ONLY + the 10 s bound + the window metadata +
  the accepted helper exactly once in ONE transaction, roll back on both
  paths, validate before it publishes, and — on a later failure — keep the
  earlier observation byte-for-byte with its original expiry.
"""

from __future__ import annotations

import asyncio
import ast
import inspect
import json
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.routes import admin
from app.routes.admin_utils import admin_account_identity
from app.tasks import precompute_admin_health as cov
from app.utils import admin_dashboard

TOKEN = "test-admin-token-847"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PATH = "/api/admin/event-source-coverage/cached"
KEY = "bainluck:admin:event_source_coverage:v1"
T0 = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
SOURCES = cov.COVERAGE_SOURCE_KEYS
BACKEND = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeRedis:
    def __init__(self, value=None, *, get_exc=None, set_exc=None):
        self.value = value
        self.get_exc = get_exc
        self.set_exc = set_exc
        self.gets = 0
        self.sets: list[tuple[str, str, int | None]] = []

    def get(self, key):
        self.gets += 1
        assert key == KEY
        if self.get_exc:
            raise self.get_exc
        return self.value

    def set(self, key, value, ex=None):
        if self.set_exc:
            raise self.set_exc
        self.sets.append((key, value, ex))
        self.value = value


class PoisonRedis(FakeRedis):
    """A cache the GET may read and must never write."""

    def set(self, *a, **k):
        raise AssertionError("GET wrote the cache")

    setex = delete = expire = set


class Clock:
    def __init__(self, start=T0, step=0.0):
        self.now = start
        self.step = timedelta(seconds=step)

    def __call__(self):
        current = self.now
        self.now = self.now + self.step
        return current


def _row(sport="basketball_nba", total=10, **override):
    row = {
        "sport": sport, "total": total, "live": 1,
        "odds_api": 9, "espn": 8, "statpal": 7, "espn_wp": 6,
        "model": 5, "mlb": 0, "kalshi": 4, "polymarket": 3,
        "expected_sources": {k: True for k in SOURCES},
    }
    row.update(override)
    return row


def _last_good(obs=T0, rows=None, **override):
    lg = {
        "complete": True,
        "rows": [_row()] if rows is None else rows,
        "unit": "events",
        "rows_scope": "all sports returned by the accepted helper",
        "observation_started_at": obs.isoformat(),
        "observation_finished_at": (obs + timedelta(seconds=1)).isoformat(),
        "computed_at": (obs + timedelta(seconds=2)).isoformat(),
        "published_at": (obs + timedelta(seconds=3)).isoformat(),
        "window": {
            "window_anchor": obs.isoformat(),
            "window_start": (obs - timedelta(days=7)).isoformat(),
            "window_end": (obs + timedelta(days=2)).isoformat(),
            "database_timezone": "UTC",
            "transaction_isolation": "read committed",
            "start_inclusive": True,
            "end_inclusive": True,
        },
        "source_provenance": {
            "accepted_semantic_reference": cov.EVENT_SOURCE_COVERAGE_ACCEPTED_REFERENCE,
            "reference_is_production_adoption": False,
            "executing_source_revision": "a" * 40,
            "executing_release_version": "v5805",
            "provenance_status": "deployment_reported",
            "helper_file_sha256": "b" * 64,
            "sql_literal_sha256": "c" * 64,
            "expected_source_mapping_sha256": "d" * 64,
            "source_last_updated_at": None,
            "source_last_updated_status": "not_supplied_by_helper",
        },
        "fresh_for_seconds": 1800,
        "freshness_policy_status": "approved",
        "retained_until": (obs + timedelta(seconds=3600)).isoformat(),
    }
    lg.update(override)
    return lg


def _envelope(last_good="default", *, outcome="ok", started=None, finished=None, error=None):
    if last_good == "default":
        last_good = _last_good()
    started = started or (T0 - timedelta(seconds=1))
    finished = finished or (T0 + timedelta(seconds=4))
    if outcome == "error" and error is None:
        error = {"kind": "statement_timeout", "code": "query_canceled"}
    return {
        "schema_version": 1,
        "last_good": last_good,
        "latest_attempt": {
            "outcome": outcome, "started_at": started.isoformat(),
            "finished_at": finished.isoformat(), "error": error,
        },
    }


def _blob(envelope):
    return json.dumps(envelope).encode()


# Every GET case runs with all of these wired to explode.
@pytest.fixture
def poisoned(monkeypatch):
    def boom(name):
        def _raise(*a, **k):
            raise AssertionError(f"GET path touched {name}")
        return _raise

    monkeypatch.setattr("app.tasks.base.get_task_session", boom("get_task_session"))
    monkeypatch.setattr(admin_dashboard, "_query_event_source_coverage", boom("coverage helper"))
    monkeypatch.setattr(admin_dashboard, "build_source_coverage_section", boom("dashboard section"))
    monkeypatch.setattr(admin_dashboard, "run_db_panel", boom("run_db_panel"))
    monkeypatch.setattr(cov, "_precompute_admin_event_source_coverage", boom("producer"))
    monkeypatch.setattr(cov, "_executing_source_identity", boom("producer provenance"))
    monkeypatch.setattr("app.routes.admin_utils._safe_send_task", boom("task dispatch"))
    monkeypatch.setattr("app.services.database.async_session_maker", boom("account session"))
    from app.tasks import celery_app

    monkeypatch.setattr(celery_app, "send_task", boom("celery send_task"))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/admin",
                       dependencies=[Depends(admin_account_identity)])

    def _no_db():
        raise AssertionError("GET opened a database session")

    app.dependency_overrides[admin.get_db] = _no_db
    return TestClient(app)


def _serve(monkeypatch, redis, now=T0):
    calls = []

    def factory(*a, **k):
        calls.append(k)
        return redis

    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", factory)
    monkeypatch.setattr(cov, "_coverage_now", lambda: now)
    return calls


# ---------------------------------------------------------------------------
# GET: auth, then every state in the contract table
# ---------------------------------------------------------------------------


class TestAuth:
    def test_no_credentials_is_refused_before_the_cache_is_read(self, client, poisoned, monkeypatch):
        redis = PoisonRedis(_blob(_envelope()))
        _serve(monkeypatch, redis)
        assert client.get(PATH).status_code == 403
        assert redis.gets == 0

    def test_a_query_secret_alone_is_refused(self, client, poisoned, monkeypatch):
        redis = PoisonRedis(_blob(_envelope()))
        _serve(monkeypatch, redis)
        assert client.get(f"{PATH}?secret={TOKEN}").status_code == 403
        assert redis.gets == 0

    def test_the_machine_token_is_served(self, client, poisoned, monkeypatch):
        redis = PoisonRedis(_blob(_envelope()))
        _serve(monkeypatch, redis)
        resp = client.get(PATH, headers=AUTH)
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "no-store"
        assert redis.gets == 1

    def test_a_resolved_admin_account_is_served_through_the_existing_gate(self, client, monkeypatch):
        # Stand in for the router-level resolver's decision (the existing account
        # path) and prove the route's gate honours it unchanged.
        from app.routes import admin_utils

        async def _stamp(request: Request):
            setattr(request.state, admin_utils.ACCOUNT_ADMIN_STATE_ATTR, "alex@example.com")

        client.app.dependency_overrides[admin_account_identity] = _stamp
        redis = PoisonRedis(_blob(_envelope()))
        _serve(monkeypatch, redis)
        resp = client.get(PATH, headers={"Authorization": "Bearer some-firebase-id-token"})
        assert resp.status_code == 200
        assert redis.gets == 1

    def test_the_handler_declares_no_database_dependency(self):
        params = inspect.signature(admin.event_source_coverage_cached).parameters
        assert set(params) == {"request", "secret"}
        route = next(r for r in admin.router.routes if getattr(r, "path", "") == "/event-source-coverage/cached")
        assert route.methods == {"GET"}
        assert all(d.call is not admin.get_db for d in route.dependant.dependencies)


def _get(client, monkeypatch, value, now=T0, query=""):
    redis = value if isinstance(value, FakeRedis) else PoisonRedis(value)
    _serve(monkeypatch, redis, now)
    resp = client.get(PATH + query, headers=AUTH)
    return resp, resp.json(), redis


class TestStates:
    def test_fresh_hit_serves_the_stored_observation_unchanged(self, client, poisoned, monkeypatch):
        env = _envelope()
        resp, body, _ = _get(client, monkeypatch, _blob(env), now=T0 + timedelta(seconds=600))
        assert resp.status_code == 200
        assert (body["cache_state"], body["freshness"], body["reason"]) == ("hit", "fresh", "observed")
        assert body["last_good"] == env["last_good"]
        assert body["latest_attempt"] == env["latest_attempt"]
        assert body["age_seconds"] == 600
        assert body["fresh_until"] == (T0 + timedelta(seconds=1800)).isoformat()
        assert body["retained_until"] == (T0 + timedelta(seconds=3600)).isoformat()
        assert body["producer_error"] is None

    def test_miss_is_202_with_no_counts_and_no_repair(self, client, poisoned, monkeypatch):
        resp, body, _ = _get(client, monkeypatch, None)
        assert resp.status_code == 202
        assert (body["cache_state"], body["freshness"]) == ("miss", "unknown")
        assert body["last_good"] is None and body["latest_attempt"] is None
        assert all(r["row_state"] == "missing_evidence" and r["denominator"] is None
                   for r in body["tier1"])

    @pytest.mark.parametrize("query", ["?bust=1", "?refresh=1", "?bust=true&refresh=true"])
    def test_bust_and_refresh_arguments_change_nothing(self, client, poisoned, monkeypatch, query):
        resp, body, redis = _get(client, monkeypatch, None, query=query)
        assert resp.status_code == 202 and body["cache_state"] == "miss"
        assert redis.gets == 1 and redis.sets == []

    def test_cache_transport_error_is_503_with_a_safe_code(self, client, poisoned, monkeypatch):
        import redis as redis_lib

        boom = PoisonRedis(get_exc=redis_lib.exceptions.ConnectionError("rediss://user:pw@host secret"))
        resp, body, _ = _get(client, monkeypatch, boom)
        assert resp.status_code == 503
        assert (body["cache_state"], body["reason"]) == ("error", "redis_unavailable")
        assert "pw" not in resp.text and "rediss" not in resp.text
        assert body["last_good"] is None

    def test_stale_within_retention_is_200_and_never_fresh(self, client, poisoned, monkeypatch):
        resp, body, _ = _get(client, monkeypatch, _blob(_envelope()), now=T0 + timedelta(seconds=1800))
        assert resp.status_code == 200
        assert (body["cache_state"], body["freshness"]) == ("hit", "stale")
        assert body["last_good"]["rows"] == [_row()]

    def test_expired_is_202_and_withholds_the_counts(self, client, poisoned, monkeypatch):
        resp, body, _ = _get(client, monkeypatch, _blob(_envelope()), now=T0 + timedelta(seconds=3600))
        assert resp.status_code == 202
        assert (body["cache_state"], body["freshness"]) == ("expired", "unknown")
        assert body["last_good"] is None
        assert body["expired_observation"]["observation_started_at"] == T0.isoformat()
        assert body["tier1"][0]["row_state"] == "missing_evidence"

    @pytest.mark.parametrize("mutate,reason", [
        (lambda lg: lg.update(fresh_for_seconds=None, freshness_policy_status="unreviewed"),
         "freshness_policy_unreviewed"),
        (lambda lg: lg["source_provenance"].update(executing_source_revision=None, provenance_status="unknown"),
         "source_identity_unknown"),
    ])
    def test_unreviewed_horizon_or_unknown_identity_is_hit_unknown(self, client, poisoned, monkeypatch,
                                                                   mutate, reason):
        lg = _last_good()
        mutate(lg)
        resp, body, _ = _get(client, monkeypatch, _blob(_envelope(lg)), now=T0 + timedelta(seconds=60))
        assert resp.status_code == 200
        assert (body["cache_state"], body["freshness"], body["reason"]) == ("hit", "unknown", reason)
        assert body["last_good"] == lg

    def test_an_observation_in_the_future_is_never_fresh(self, client, poisoned, monkeypatch):
        resp, body, _ = _get(client, monkeypatch, _blob(_envelope()), now=T0 - timedelta(seconds=5))
        assert (resp.status_code, body["freshness"], body["reason"]) == (
            200, "unknown", "observation_clock_in_future")

    def test_producer_error_with_retained_evidence_keeps_both_visible(self, client, poisoned, monkeypatch):
        env = _envelope(outcome="error", started=T0 + timedelta(seconds=900),
                        finished=T0 + timedelta(seconds=911))
        resp, body, _ = _get(client, monkeypatch, _blob(env), now=T0 + timedelta(seconds=1000))
        assert resp.status_code == 200
        assert (body["cache_state"], body["freshness"], body["reason"]) == ("hit", "fresh", "latest_attempt_failed")
        assert body["producer_error"] == {"kind": "statement_timeout", "code": "query_canceled"}
        assert body["last_good"] == env["last_good"]

    def test_producer_error_without_evidence_is_503(self, client, poisoned, monkeypatch):
        env = _envelope(None, outcome="error", error={"kind": "query_error", "code": "database_error"})
        resp, body, _ = _get(client, monkeypatch, _blob(env))
        assert resp.status_code == 503
        assert (body["cache_state"], body["freshness"]) == ("producer_error", "unknown")
        assert body["latest_attempt"] == env["latest_attempt"]
        assert body["last_good"] is None

    def test_complete_empty_rows_is_a_real_answer_not_a_miss(self, client, poisoned, monkeypatch):
        resp, body, _ = _get(client, monkeypatch, _blob(_envelope(_last_good(rows=[]))),
                             now=T0 + timedelta(seconds=60))
        assert resp.status_code == 200 and body["cache_state"] == "hit"
        assert body["last_good"]["rows"] == []
        assert [r["row_state"] for r in body["tier1"]] == ["no_in_window_events"] * 6

    def test_a_real_zero_is_a_zero_over_that_sports_own_denominator(self, client, poisoned, monkeypatch):
        rows = [_row("basketball_nba", total=10, kalshi=0),
                _row("golf_pga", total=4, odds_api=4, espn=0, statpal=0, espn_wp=0, model=0,
                     kalshi=1, polymarket=2, live=0, expected_sources={k: k != "mlb" for k in SOURCES})]
        resp, body, _ = _get(client, monkeypatch, _blob(_envelope(_last_good(rows=rows))),
                             now=T0 + timedelta(seconds=60))
        tier1 = {r["sport"]: r for r in body["tier1"]}
        nba, golf = tier1["basketball_nba"], tier1["golf_pga"]
        assert nba["sources"]["kalshi"] == {"count": 0, "expected": True, "share": 0.0}
        assert golf["denominator"] == 4 and golf["sources"]["polymarket"]["share"] == 0.5
        assert golf["sources"]["mlb"]["expected"] is False
        assert tier1["americanfootball_nfl"]["row_state"] == "no_in_window_events"
        assert all(r["health_verdict"] == "unverified" for r in body["tier1"])
        # The full population stays in last_good, not just Tier 1.
        assert [r["sport"] for r in body["last_good"]["rows"]] == ["basketball_nba", "golf_pga"]


def _with_row(**override):
    return _envelope(_last_good(rows=[_row(**override)]))


def _without(key):
    row = _row()
    del row[key]
    return _envelope(_last_good(rows=[row]))


def _expected_without(key):
    row = _row()
    del row["expected_sources"][key]
    return _envelope(_last_good(rows=[row]))


MALFORMED = [
    ("not_json", b"{not json"),
    ("not_json", b"\xff\xfe"),
    ("invalid_envelope", _blob([1, 2])),
    ("unsupported_schema_version", _blob({**_envelope(), "schema_version": 2})),
    ("unsupported_schema_version", _blob({**_envelope(), "schema_version": True})),
    ("missing_latest_attempt", _blob({**_envelope(), "latest_attempt": None})),
    ("invalid_latest_attempt", _blob(_envelope(outcome="maybe"))),
    ("invalid_latest_attempt", _blob(_envelope(outcome="error", error={"kind": "boom", "code": "x"}))),
    ("invalid_latest_attempt", _blob(_envelope(outcome="error",
                                               error={"kind": "query_error", "code": "Traceback: dsn=..."}))),
    ("invalid_count", _blob(_with_row(kalshi=-1))),
    ("invalid_count", _blob(_with_row(kalshi=True))),
    ("invalid_count", _blob(_with_row(kalshi=1.5))),
    ("count_exceeds_total", _blob(_with_row(kalshi=11))),
    ("count_exceeds_total", _blob(_with_row(live=11))),
    ("invalid_denominator", _blob(_with_row(total=0))),
    ("invalid_denominator", _blob(_with_row(total=False))),
    ("invalid_sport", _blob(_with_row(sport=""))),
    ("duplicate_sport", _blob(_envelope(_last_good(rows=[_row(), _row()])))),
    ("unexpected_field", _blob(_with_row(snapshots_24h=5))),
    ("invalid_expected_sources", _blob(_with_row(expected_sources={k: "yes" for k in SOURCES}))),
    ("invalid_timestamp", _blob(_envelope(_last_good(observation_started_at="2026-10-20T12:00:00")))),
    ("timestamps_out_of_order", _blob(_envelope(_last_good(published_at=(T0 - timedelta(1)).isoformat())))),
    ("retention_not_from_observation",
     _blob(_envelope(_last_good(retained_until=(T0 + timedelta(seconds=7200)).isoformat())))),
    ("invalid_provenance", _blob(_envelope(_last_good(source_provenance={
        **_last_good()["source_provenance"], "accepted_semantic_reference": "deadbeef"})))),
    ("invalid_provenance", _blob(_envelope(_last_good(source_provenance={
        **_last_good()["source_provenance"], "reference_is_production_adoption": True})))),
    ("invalid_provenance", _blob(_envelope(_last_good(source_provenance={
        **_last_good()["source_provenance"], "executing_source_revision": None})))),
    ("invalid_window", _blob(_envelope(_last_good(window={
        **_last_good()["window"], "window_start": (T0 + timedelta(days=3)).isoformat()})))),
    ("inconsistent_success_envelope", _blob(_envelope(None))),
    ("inconsistent_success_envelope", _blob(_envelope(started=T0 + timedelta(seconds=10),
                                                      finished=T0 + timedelta(seconds=20)))),
    ("inconsistent_error_envelope", _blob(_envelope(outcome="error", started=T0, finished=T0 + timedelta(1)))),
]

PARTIAL = [
    ("missing_field", _blob(_without("kalshi"))),
    ("missing_field", _blob(_without("total"))),
    ("missing_field", _blob(_without("expected_sources"))),
    ("missing_field", _blob(_expected_without("polymarket"))),
    ("supplied_unknown", _blob(_with_row(kalshi=None))),
    ("supplied_unknown", _blob(_with_row(total=None))),
    ("supplied_unknown", _blob(_with_row(expected_sources={**{k: True for k in SOURCES}, "mlb": None}))),
]


class TestRefusals:
    @pytest.mark.parametrize("reason,raw", MALFORMED)
    def test_malformed_is_503_and_salvages_nothing(self, client, poisoned, monkeypatch, reason, raw):
        resp, body, _ = _get(client, monkeypatch, raw, now=T0 + timedelta(seconds=60))
        assert resp.status_code == 503
        assert (body["cache_state"], body["freshness"], body["reason"]) == ("malformed", "unknown", reason)
        assert body["last_good"] is None and body["latest_attempt"] is None

    @pytest.mark.parametrize("reason,raw", PARTIAL)
    def test_partial_is_503_and_null_differs_from_absent(self, client, poisoned, monkeypatch, reason, raw):
        resp, body, _ = _get(client, monkeypatch, raw, now=T0 + timedelta(seconds=60))
        assert resp.status_code == 503
        assert (body["cache_state"], body["reason"]) == ("partial", reason)
        assert body["last_good"] is None

    def test_malformed_outranks_partial_in_one_result(self):
        rows = [_row("a", kalshi=None), _row("b", kalshi=-1)]
        with pytest.raises(cov.CoverageEnvelopeInvalid) as exc:
            cov.validate_coverage_rows(rows)
        assert (exc.value.state, exc.value.reason) == ("malformed", "invalid_count")


def _aged(seconds):
    return T0 + timedelta(seconds=seconds)


def _retained_error_envelope(lg=None):
    # A later failed run that kept the earlier observation (attempt after it).
    return _envelope(_last_good() if lg is None else lg, outcome="error",
                     started=_aged(900), finished=_aged(911))


class TestFreshnessPolicy:
    """"approved" is the reviewed 1800 s from observation start and nothing else."""

    @pytest.mark.parametrize("age,freshness,reason", [
        (1799, "fresh", "observed"),
        (1800, "stale", "observation_older_than_horizon"),
        (1801, "stale", "observation_older_than_horizon"),
        (2000, "stale", "observation_older_than_horizon"),
        (3599, "stale", "observation_older_than_horizon"),
    ])
    def test_the_reviewed_horizon_ages_from_the_observation(self, client, poisoned, monkeypatch,
                                                           age, freshness, reason):
        env = _envelope()
        resp, body, _ = _get(client, monkeypatch, _blob(env), now=_aged(age))
        assert resp.status_code == 200
        assert (body["cache_state"], body["freshness"], body["reason"]) == ("hit", freshness, reason)
        assert body["age_seconds"] == age
        assert body["fresh_until"] == _aged(1800).isoformat()
        assert body["last_good"] == env["last_good"]

    def test_retention_still_ends_at_observation_plus_3600(self, client, poisoned, monkeypatch):
        resp, body, _ = _get(client, monkeypatch, _blob(_envelope()), now=_aged(3600))
        assert (resp.status_code, body["cache_state"], body["freshness"]) == (202, "expired", "unknown")
        assert body["last_good"] is None

    # Root's specimen (cf00, age 2000 s): 3500 was served as fresh, 1800 as stale.
    @pytest.mark.parametrize("horizon", [3500, 3600, 1801, 1799, 1, 10**400])
    @pytest.mark.parametrize("age", [60, 2000])
    def test_an_approved_horizon_other_than_the_reviewed_one_is_refused(self, client, poisoned,
                                                                       monkeypatch, horizon, age):
        resp, body, _ = _get(client, monkeypatch, _blob(_envelope(_last_good(fresh_for_seconds=horizon))),
                             now=_aged(age))
        assert resp.status_code == 503
        assert (body["cache_state"], body["freshness"], body["reason"]) == (
            "malformed", "unknown", "incompatible_freshness_policy")
        # Nothing of the refused envelope is served as evidence, and no age is.
        assert body["last_good"] is None and body["latest_attempt"] is None
        assert body["age_seconds"] is None and body["fresh_until"] is None

    def test_the_reviewed_horizon_control_at_the_same_age(self, client, poisoned, monkeypatch):
        resp, body, _ = _get(client, monkeypatch, _blob(_envelope(_last_good(fresh_for_seconds=1800))),
                             now=_aged(2000))
        assert (resp.status_code, body["freshness"], body["age_seconds"]) == (200, "stale", 2000)

    @pytest.mark.parametrize("fresh,policy", [
        (None, "approved"), (1800.0, "approved"), (True, "approved"), (0, "approved"),
        (-1800, "approved"), ("1800", "approved"), (1800, "unreviewed"), (1800, "APPROVED"),
        (1800, ["approved"]), (1800, None),
    ])
    def test_a_policy_of_the_wrong_shape_stays_invalid(self, client, poisoned, monkeypatch, fresh, policy):
        lg = _last_good(fresh_for_seconds=fresh, freshness_policy_status=policy)
        resp, body, _ = _get(client, monkeypatch, _blob(_envelope(lg)), now=_aged(60))
        assert (resp.status_code, body["cache_state"], body["reason"]) == (
            503, "malformed", "invalid_freshness_policy")

    @pytest.mark.parametrize("age", [60, 1799, 2000, 3599])
    def test_the_unreviewed_path_is_never_aged_into_fresh_or_stale(self, client, poisoned, monkeypatch, age):
        lg = _last_good(fresh_for_seconds=None, freshness_policy_status="unreviewed")
        resp, body, _ = _get(client, monkeypatch, _blob(_envelope(lg)), now=_aged(age))
        assert resp.status_code == 200
        assert (body["freshness"], body["reason"], body["fresh_until"]) == (
            "unknown", "freshness_policy_unreviewed", None)
        assert body["last_good"] == lg

    @pytest.mark.parametrize("age,freshness", [(1000, "fresh"), (1799, "fresh"), (1800, "stale"), (3599, "stale")])
    def test_a_later_error_retaining_old_evidence_never_extends_it(self, client, poisoned, monkeypatch,
                                                                  age, freshness):
        env = _retained_error_envelope()
        resp, body, _ = _get(client, monkeypatch, _blob(env), now=_aged(age))
        assert resp.status_code == 200
        assert (body["freshness"], body["reason"]) == (freshness, "latest_attempt_failed")
        assert body["fresh_until"] == _aged(1800).isoformat()
        assert body["last_good"] == env["last_good"]

    def test_retained_evidence_with_an_incompatible_horizon_is_refused(self, client, poisoned, monkeypatch):
        env = _retained_error_envelope(_last_good(fresh_for_seconds=3500))
        resp, body, _ = _get(client, monkeypatch, _blob(env), now=_aged(2000))
        assert (resp.status_code, body["cache_state"], body["reason"]) == (
            503, "malformed", "incompatible_freshness_policy")
        assert body["last_good"] is None

    def test_retained_evidence_expires_at_its_own_retention_after_an_error(self, client, poisoned, monkeypatch):
        resp, body, _ = _get(client, monkeypatch, _blob(_retained_error_envelope()), now=_aged(3600))
        assert (resp.status_code, body["cache_state"]) == (202, "expired")
        assert body["producer_error"] == {"kind": "statement_timeout", "code": "query_canceled"}
        assert body["last_good"] is None


# Every JSON value type, including the ones Python's decoder adds (NaN, huge ints).
_JSON_PROBES = ([], {}, 1.5, float("nan"), True, None, 10**400, -1, "x", "")


def _leaf_paths(node, path=()):
    yield path
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaf_paths(value, path + (key,))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _leaf_paths(value, path + (i,))


def _substituted(base, path, value):
    env = json.loads(json.dumps(base))
    node = env
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return env


def _json_kind(value):
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return type(value).__name__


class TestMalformedTypes:
    @pytest.mark.parametrize("kind", [[], {}, 1, 1.5, True, None])
    def test_a_non_string_error_kind_is_a_typed_refusal(self, client, poisoned, monkeypatch, kind):
        env = _envelope(None, outcome="error", error={"kind": kind, "code": "database_error"})
        resp, body, _ = _get(client, monkeypatch, _blob(env))
        assert (resp.status_code, body["cache_state"], body["reason"]) == (
            503, "malformed", "invalid_latest_attempt")
        assert body["latest_attempt"] is None

    @pytest.mark.parametrize("kind,status,state", [
        ("query_error", 503, "producer_error"),
        ("unsupported_kind", 503, "malformed"),
    ])
    def test_string_error_kind_controls(self, client, poisoned, monkeypatch, kind, status, state):
        env = _envelope(None, outcome="error", error={"kind": kind, "code": "database_error"})
        resp, body, _ = _get(client, monkeypatch, _blob(env))
        assert (resp.status_code, body["cache_state"]) == (status, state)

    def test_an_observation_too_late_to_retain_is_a_typed_refusal(self, client, poisoned, monkeypatch):
        late = "9999-12-31T23:59:59+00:00"
        lg = _last_good(observation_started_at="9999-12-31T23:30:00+00:00", observation_finished_at=late,
                        computed_at=late, published_at=late, retained_until=late)
        resp, body, _ = _get(client, monkeypatch, _blob(_envelope(lg)))
        assert (resp.status_code, body["cache_state"], body["reason"]) == (503, "malformed", "invalid_timestamp")

    def test_absurdly_nested_json_is_a_typed_refusal(self, client, poisoned, monkeypatch):
        resp, body, _ = _get(client, monkeypatch, b"[" * 100_000 + b"]" * 100_000)
        assert (resp.status_code, body["cache_state"], body["reason"]) == (503, "malformed", "not_json")

    @pytest.mark.parametrize("base", [
        _envelope(), _retained_error_envelope(),
        _envelope(None, outcome="error", error={"kind": "query_error", "code": "database_error"}),
    ], ids=["success", "error_retaining_evidence", "error_without_evidence"])
    def test_every_field_given_every_json_type_gets_a_typed_answer(self, client, poisoned, monkeypatch, base):
        # Through the real route and JSONResponse: no value of any JSON type in any
        # field may escape as a server error, and a value of the wrong type is
        # never served as evidence.
        redis = PoisonRedis(None)
        _serve(monkeypatch, redis, _aged(60))
        typed = {"hit", "miss", "error", "malformed", "partial", "producer_error", "expired"}
        cases = 0
        for path in _leaf_paths(base):
            if not path:
                continue
            node = base
            for step in path:
                node = node[step]
            original = node
            for probe in _JSON_PROBES:
                redis.value = json.dumps(_substituted(base, path, probe)).encode()
                resp = client.get(PATH, headers=AUTH)
                body = resp.json()
                cases += 1
                assert resp.status_code in (200, 202, 503), (path, probe)
                assert body["cache_state"] in typed, (path, probe)
                if probe is not None and _json_kind(probe) != _json_kind(original):
                    assert resp.status_code == 503 and body["cache_state"] in ("malformed", "partial"), \
                        (path, probe, body["reason"])
        # Every field of the base was probed (not a vacuous sweep).
        assert cases == (len(list(_leaf_paths(base))) - 1) * len(_JSON_PROBES) >= 8 * len(_JSON_PROBES)


# ---------------------------------------------------------------------------
# GET: the read is off the loop and bounded as a whole
# ---------------------------------------------------------------------------


class TestBoundedRead:
    def test_the_reader_reuses_the_existing_request_path_signature(self, client, poisoned, monkeypatch):
        calls = _serve(monkeypatch, PoisonRedis(None))
        client.get(PATH, headers=AUTH)
        assert calls == [{"socket_timeout": 0.5, "fast_fail": True}]

    def test_that_signature_is_fast_fail_with_one_retry_and_a_short_pool_wait(self, monkeypatch):
        # What the client the reader receives is made of (factory patched, so
        # no connection is opened). Its CONNECT timeout is still the 5 s
        # default — which is why the reader carries its own total deadline.
        from app.tasks import redis_state

        built = {}

        def factory(url, **kwargs):
            built.update(kwargs)
            return object()

        redis_state.reset_redis_client_cache()
        monkeypatch.setattr(redis_state.redis, "from_url", factory)
        try:
            cov._coverage_cache_client()
        finally:
            redis_state.reset_redis_client_cache()
        assert built["socket_timeout"] == 0.5
        assert built["socket_connect_timeout"] == 5.0
        assert built["retry"]._retries == 1
        assert built["health_check_interval"] == 25
        assert redis_state._REDIS_POOL_WAIT_FAST_FAIL < 0.5
        assert cov.EVENT_SOURCE_COVERAGE_READ_DEADLINE_S < built["socket_connect_timeout"]

    @pytest.mark.parametrize("stall", ["pool_wait", "connect", "health_check_ping", "get_then_retry"])
    async def test_any_stall_inside_the_client_is_cut_at_the_deadline(self, monkeypatch, stall):
        release = threading.Event()
        entered = []

        class Stalling:
            def get(self, key):
                entered.append(stall)
                release.wait(10)  # stands in for a blocked socket/pool in that stage
                return None

        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda **k: Stalling())
        monkeypatch.setattr(cov, "EVENT_SOURCE_COVERAGE_READ_DEADLINE_S", 0.2)
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        tick_task = asyncio.create_task(ticker())
        started = time.monotonic()
        try:
            status, body = await cov.read_event_source_coverage_cache()
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
        monkeypatch.setattr(cov, "EVENT_SOURCE_COVERAGE_READ_DEADLINE_S", 0.15)
        started = time.monotonic()
        try:
            status, body = await cov.read_event_source_coverage_cache()
        finally:
            release.set()
        assert status == 503 and body["reason"] == "read_deadline_exceeded"
        assert time.monotonic() - started < 0.5

    @pytest.mark.parametrize("exc_name", ["ConnectionError", "TimeoutError", "MaxConnectionsError"])
    async def test_client_errors_are_a_typed_cache_error(self, monkeypatch, exc_name):
        import redis as redis_lib

        exc_cls = getattr(redis_lib.exceptions, exc_name)
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client",
                            lambda **k: PoisonRedis(get_exc=exc_cls("Timeout connecting to server")))
        status, body = await cov.read_event_source_coverage_cache()
        assert (status, body["cache_state"], body["reason"]) == (503, "error", "redis_unavailable")


# ---------------------------------------------------------------------------
# Producer: one transaction, fake session, fake Redis
# ---------------------------------------------------------------------------


def _db_row(r):
    return SimpleNamespace(
        sport_key=r["sport"], total_events=r["total"], live_events=r["live"],
        has_odds_api=r["odds_api"], has_espn=r["espn"], has_statpal=r["statpal"],
        has_espn_wp=r["espn_wp"], has_model=r["model"], has_mlb=r["mlb"],
        has_kalshi=r["kalshi"], has_polymarket=r["polymarket"],
    )


class _Result:
    def __init__(self, rows=None, one=None):
        self._rows, self._one = rows or [], one

    def all(self):
        return self._rows

    def one(self):
        return self._one


class FakeSession:
    def __init__(self, rows, *, meta="default", helper_exc=None):
        self.rows = rows
        self.meta = SimpleNamespace(
            window_anchor=T0, window_start=T0 - timedelta(days=7), window_end=T0 + timedelta(days=2),
            database_timezone="UTC", transaction_isolation="read committed",
        ) if meta == "default" else meta
        self.helper_exc = helper_exc
        self.txn = 0
        self.log: list[tuple[int, str]] = []
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.log.append((self.txn, sql))
        if sql.startswith("SET LOCAL statement_timeout") or sql == "SET TRANSACTION READ ONLY":
            return _Result()
        if sql.startswith("SELECT transaction_timestamp() AS window_anchor"):
            return _Result(one=self.meta)
        if sql.startswith("WITH recent_events AS"):
            if self.helper_exc:
                raise self.helper_exc
            return _Result(rows=[_db_row(r) for r in self.rows])
        raise AssertionError(f"producer ran unexpected SQL: {sql[:80]}")

    async def rollback(self):
        self.rollbacks += 1
        self.txn += 1

    async def commit(self):
        self.txn += 1


def _arm_producer(monkeypatch, session, redis, *, clock=None, env=None):
    @asynccontextmanager
    async def fake_session(**kwargs):
        assert kwargs == {}
        yield session
        await session.commit()

    monkeypatch.setattr("app.tasks.base.get_task_session", fake_session)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: redis)
    monkeypatch.setattr(cov, "_coverage_now", clock or Clock(T0, step=0.5))
    for name, value in (env or {"HEROKU_SLUG_COMMIT": "e" * 40, "HEROKU_RELEASE_VERSION": "v1"}).items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def _forbid_other_panels(monkeypatch):
    for name in ("_query_sport_activity", "_query_coverage_trend", "_query_futures_coverage",
                 "build_database_section", "build_game_state_section", "build_source_coverage_section"):
        def _raise(*a, _n=name, **k):
            raise AssertionError(f"producer ran {_n}")
        monkeypatch.setattr(admin_dashboard, name, _raise)


ROWS = [
    _row("basketball_nba", total=12, kalshi=0, polymarket=12),
    _row("golf_pga", total=3, live=0, odds_api=3, espn=0, statpal=0, espn_wp=0, model=0, mlb=0,
         kalshi=2, polymarket=1),
    _row("boxing_boxing", total=1, live=0, odds_api=1, espn=0, statpal=0, espn_wp=0, model=0, mlb=0,
         kalshi=1, polymarket=0),
]


def _expected(sport):
    return admin_dashboard._expected_sources_for_sport(sport)


class TestProducer:
    async def test_one_read_only_transaction_in_the_contract_order(self, monkeypatch):
        session, redis = FakeSession(ROWS), FakeRedis()
        _forbid_other_panels(monkeypatch)
        _arm_producer(monkeypatch, session, redis)

        result = await cov._precompute_admin_event_source_coverage()

        assert result == {"status": "ok", "error": None, "published": True, "rows": 3}
        order = [sql.split(" AS ")[0][:40] for _, sql in session.log]
        assert order == [
            "SET LOCAL statement_timeout = '10s'",
            "SET TRANSACTION READ ONLY",
            "SELECT transaction_timestamp()",
            "WITH recent_events",
        ]
        assert {txn for txn, _ in session.log} == {0}  # all four in ONE transaction
        assert session.rollbacks == 1
        helper_sql = session.log[3][1]
        assert sum("WITH recent_events" in sql for _, sql in session.log) == 1
        # The accepted helper's SQL, unchanged — not a copy in the producer.
        assert "WITH recent_events" not in inspect.getsource(cov)
        assert "COUNT(*) FILTER (WHERE wp.kalshi OR pm.kalshi)" in helper_sql

    async def test_every_count_flag_and_denominator_is_published_exactly(self, monkeypatch):
        session, redis = FakeSession(ROWS), FakeRedis()
        _arm_producer(monkeypatch, session, redis)
        await cov._precompute_admin_event_source_coverage()

        (key, value, ex), = redis.sets
        env = json.loads(value)
        assert key == KEY
        lg = env["last_good"]
        assert lg["rows"] == [{**r, "expected_sources": _expected(r["sport"])} for r in ROWS]
        assert lg["window"] == {
            "window_anchor": T0.isoformat(),
            "window_start": (T0 - timedelta(days=7)).isoformat(),
            "window_end": (T0 + timedelta(days=2)).isoformat(),
            "database_timezone": "UTC", "transaction_isolation": "read committed",
            "start_inclusive": True, "end_inclusive": True,
        }
        observed = datetime.fromisoformat(lg["observation_started_at"])
        assert datetime.fromisoformat(lg["retained_until"]) == observed + timedelta(seconds=3600)
        assert lg["fresh_for_seconds"] == 1800 and lg["freshness_policy_status"] == "approved"
        attempt_finished = datetime.fromisoformat(env["latest_attempt"]["finished_at"])
        assert ex == int((observed + timedelta(seconds=3600) - attempt_finished).total_seconds())
        assert ex <= 3600
        cov.validate_coverage_envelope(env)

    async def test_the_observation_brackets_only_the_helper_call(self, monkeypatch):
        session, redis = FakeSession(ROWS), FakeRedis()
        stamps = []
        clock = Clock(T0, step=1.0)

        real_helper = admin_dashboard._query_event_source_coverage

        async def watched(db):
            stamps.append(("helper_called_at", clock.now))
            return await real_helper(db)

        monkeypatch.setattr(admin_dashboard, "_query_event_source_coverage", watched)
        _arm_producer(monkeypatch, session, redis, clock=clock)
        await cov._precompute_admin_event_source_coverage()
        lg = json.loads(redis.value)["last_good"]
        started = datetime.fromisoformat(lg["observation_started_at"])
        finished = datetime.fromisoformat(lg["observation_finished_at"])
        assert started < stamps[0][1] <= finished

    async def test_provenance_is_reported_or_unknown_never_the_reference(self, monkeypatch):
        session, redis = FakeSession(ROWS), FakeRedis()
        _arm_producer(monkeypatch, session, redis,
                      env={"HEROKU_SLUG_COMMIT": None, "HEROKU_RELEASE_VERSION": None})
        await cov._precompute_admin_event_source_coverage()
        prov = json.loads(redis.value)["last_good"]["source_provenance"]
        assert prov["executing_source_revision"] is None
        assert prov["provenance_status"] == "unknown"
        assert prov["accepted_semantic_reference"] == cov.EVENT_SOURCE_COVERAGE_ACCEPTED_REFERENCE
        assert prov["reference_is_production_adoption"] is False
        assert prov["source_last_updated_at"] is None
        assert prov["source_last_updated_status"] == "not_supplied_by_helper"
        # The hashes are of the bytes this process imported, by the packet's method.
        source = Path(admin_dashboard.__file__).read_bytes()
        import hashlib

        assert prov["helper_file_sha256"] == hashlib.sha256(source).hexdigest()
        literal = next(
            c.args[0].value for fn in ast.walk(ast.parse(source))
            if isinstance(fn, ast.AsyncFunctionDef) and fn.name == "_query_event_source_coverage"
            for c in ast.walk(fn) if isinstance(c, ast.Call) and getattr(c.func, "id", None) == "text"
        )
        assert prov["sql_literal_sha256"] == hashlib.sha256(literal.encode()).hexdigest()
        assert len(prov["expected_source_mapping_sha256"]) == 64

    async def test_reported_identity_reaches_the_reader_as_fresh(self, monkeypatch, client, request):
        session, redis = FakeSession(ROWS), FakeRedis()
        _arm_producer(monkeypatch, session, redis)
        await cov._precompute_admin_event_source_coverage()
        request.getfixturevalue("poisoned")  # from here on, the GET's rules
        prov = json.loads(redis.value)["last_good"]["source_provenance"]
        assert prov["executing_source_revision"] == "e" * 40
        assert prov["provenance_status"] == "deployment_reported"
        published = redis.value
        resp, body, _ = _get(client, monkeypatch, published, now=T0 + timedelta(seconds=120))
        assert (resp.status_code, body["cache_state"], body["freshness"]) == (200, "hit", "fresh")
        assert body["last_good"] == json.loads(published)["last_good"]

    async def test_complete_empty_population_publishes_as_evidence(self, monkeypatch):
        session, redis = FakeSession([]), FakeRedis()
        _arm_producer(monkeypatch, session, redis)
        result = await cov._precompute_admin_event_source_coverage()
        assert result["published"] is True and result["rows"] == 0
        assert json.loads(redis.value)["last_good"]["rows"] == []

    @pytest.mark.parametrize("exc,kind,code", [
        (type("QueryCanceledError", (Exception,), {})("canceling statement due to statement timeout"),
         "statement_timeout", "query_canceled"),
        (RuntimeError("connection to postgres://u:p@h/db refused"), "query_error", "database_error"),
    ])
    async def test_a_failed_query_rolls_back_and_publishes_only_the_attempt(self, monkeypatch, exc, kind, code):
        session, redis = FakeSession(ROWS, helper_exc=exc), FakeRedis()
        _arm_producer(monkeypatch, session, redis)
        result = await cov._precompute_admin_event_source_coverage()
        assert session.rollbacks == 1
        assert result["status"] == "error" and result["published"] is True
        assert result["error"] == {"kind": kind, "code": code}
        (_, value, ex), = redis.sets
        env = json.loads(value)
        assert env["last_good"] is None
        assert env["latest_attempt"]["error"] == {"kind": kind, "code": code}
        assert ex == 3600
        assert "postgres" not in value and "canceling" not in value

    async def test_a_later_failure_keeps_the_earlier_observation_byte_for_byte(self, monkeypatch):
        clock = Clock(T0, step=0.5)
        good, redis = FakeSession(ROWS), FakeRedis()
        _arm_producer(monkeypatch, good, redis, clock=clock)
        await cov._precompute_admin_event_source_coverage()
        first = json.loads(redis.value)
        first_bytes = json.dumps(first["last_good"], sort_keys=True, separators=(",", ":"))

        clock.now = T0 + timedelta(seconds=1500)
        bad = FakeSession(ROWS, helper_exc=RuntimeError("boom"))
        _arm_producer(monkeypatch, bad, redis, clock=clock)
        result = await cov._precompute_admin_event_source_coverage()

        assert result["status"] == "error" and result["published"] is True
        (_, value, ex) = redis.sets[-1]
        second = json.loads(value)
        assert first_bytes in value  # the retained observation, byte-for-byte
        assert second["last_good"] == first["last_good"]
        assert second["latest_attempt"]["outcome"] == "error"
        # The key lives exactly as long as the ORIGINAL observation; never longer.
        retained = datetime.fromisoformat(first["last_good"]["retained_until"])
        finished = datetime.fromisoformat(second["latest_attempt"]["finished_at"])
        assert ex == int(-(-(retained - finished).total_seconds() // 1))
        assert finished + timedelta(seconds=ex) < retained + timedelta(seconds=1)

    async def test_a_failure_after_retention_drops_the_expired_observation(self, monkeypatch):
        redis = FakeRedis(_blob(_envelope()))
        clock = Clock(T0 + timedelta(seconds=3700), step=0.5)
        _arm_producer(monkeypatch, FakeSession(ROWS, helper_exc=RuntimeError("x")), redis, clock=clock)
        await cov._precompute_admin_event_source_coverage()
        env = json.loads(redis.sets[-1][1])
        assert env["last_good"] is None and redis.sets[-1][2] == 3600

    async def test_a_failure_never_retains_evidence_with_an_incompatible_horizon(self, monkeypatch):
        redis = FakeRedis(_blob(_envelope(_last_good(fresh_for_seconds=3500))))
        clock = Clock(T0 + timedelta(seconds=100), step=0.5)
        _arm_producer(monkeypatch, FakeSession(ROWS, helper_exc=RuntimeError("x")), redis, clock=clock)
        result = await cov._precompute_admin_event_source_coverage()
        assert result["published"] is True
        env = json.loads(redis.sets[-1][1])
        assert env["last_good"] is None and redis.sets[-1][2] == 3600

    async def test_absurdly_nested_prior_bytes_are_not_evidence(self, monkeypatch):
        redis = FakeRedis(b"[" * 100_000 + b"]" * 100_000)
        _arm_producer(monkeypatch, FakeSession(ROWS, helper_exc=RuntimeError("x")), redis)
        result = await cov._precompute_admin_event_source_coverage()
        assert result["published"] is True
        assert json.loads(redis.sets[-1][1])["last_good"] is None

    async def test_an_unreadable_prior_cache_is_never_overwritten(self, monkeypatch):
        import redis as redis_lib

        redis = FakeRedis(get_exc=redis_lib.exceptions.ConnectionError("down"))
        _arm_producer(monkeypatch, FakeSession(ROWS, helper_exc=RuntimeError("x")), redis)
        result = await cov._precompute_admin_event_source_coverage()
        assert redis.sets == []
        assert result["published"] is False
        assert result["publish_error"] == {"kind": "cache_read_error", "code": "prior_envelope_unreadable"}

    async def test_a_failed_publication_does_not_claim_it_published(self, monkeypatch):
        import redis as redis_lib

        redis = FakeRedis(set_exc=redis_lib.exceptions.TimeoutError("slow"))
        _arm_producer(monkeypatch, FakeSession(ROWS), redis)
        result = await cov._precompute_admin_event_source_coverage()
        assert result["published"] is False
        assert result["publish_error"] == {"kind": "cache_publish_error", "code": "redis_set_failed"}

    @pytest.mark.parametrize("rows,code", [
        ([{**_row(), "kalshi": None}], "partial_supplied_unknown"),
        ([_row(), _row()], "malformed_duplicate_sport"),
        ([{**_row(), "total": 0, "live": 0, **{k: 0 for k in SOURCES}}], "malformed_invalid_denominator"),
    ])
    async def test_an_invalid_result_never_replaces_good_evidence(self, monkeypatch, rows, code):
        redis = FakeRedis(_blob(_envelope()))
        clock = Clock(T0 + timedelta(seconds=100), step=0.5)
        session = FakeSession([])
        _arm_producer(monkeypatch, session, redis, clock=clock)

        async def bad_helper(db):
            return rows

        monkeypatch.setattr(admin_dashboard, "_query_event_source_coverage", bad_helper)
        result = await cov._precompute_admin_event_source_coverage()
        assert result["error"] == {"kind": "malformed_result", "code": code}
        env = json.loads(redis.sets[-1][1])
        assert env["last_good"] == _envelope()["last_good"]
        assert env["latest_attempt"]["error"]["kind"] == "malformed_result"

    async def test_unusable_window_metadata_is_a_provenance_error(self, monkeypatch):
        meta = SimpleNamespace(window_anchor=T0.replace(tzinfo=None), window_start=T0, window_end=T0,
                               database_timezone="UTC", transaction_isolation="read committed")
        redis = FakeRedis()
        _arm_producer(monkeypatch, FakeSession(ROWS, meta=meta), redis)
        result = await cov._precompute_admin_event_source_coverage()
        assert result["error"] == {"kind": "provenance_error", "code": "window_metadata_invalid"}
        assert json.loads(redis.value)["last_good"] is None


# ---------------------------------------------------------------------------
# Inertness: nothing registers, schedules or calls the producer
# ---------------------------------------------------------------------------

PRODUCER = "_precompute_admin_event_source_coverage"


class TestInert:
    def test_the_producer_is_a_plain_coroutine_function_with_no_decorator(self):
        tree = ast.parse((BACKEND / "app/tasks/precompute_admin_health.py").read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == PRODUCER)
        assert fn.decorator_list == []
        assert not hasattr(cov._precompute_admin_event_source_coverage, "delay")

    def test_nothing_in_the_app_names_the_producer(self):
        hits = [
            str(p.relative_to(BACKEND)) for p in (BACKEND / "app").rglob("*.py")
            if PRODUCER in p.read_text(encoding="utf-8", errors="replace")
        ]
        assert hits == ["app/tasks/precompute_admin_health.py"]
        own = (BACKEND / "app/tasks/precompute_admin_health.py").read_text()
        # Defined once; referenced only in prose, never called.
        assert own.count(f"async def {PRODUCER}(") == 1
        assert f"{PRODUCER}()" not in own.replace(f"async def {PRODUCER}()", "")

    def test_no_celery_task_or_beat_entry_reaches_the_producer(self):
        from app.tasks import celery_app

        names = set(celery_app.tasks)
        assert not any("event_source_coverage" in n for n in names)
        beat = celery_app.conf.beat_schedule or {}
        assert not any("event_source_coverage" in str(v.get("task", "")) or "event_source_coverage" in k
                       for k, v in beat.items())

    def test_the_module_import_runs_nothing(self):
        # Module top level is imports, definitions and constant-shaped
        # assignments only: importing it can reach no session, cache or task.
        tree = ast.parse((BACKEND / "app/tasks/precompute_admin_health.py").read_text())
        allowed_calls = {"getLogger", "compile", "frozenset"}
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue  # the docstring
            assert isinstance(node, (ast.Assign, ast.AnnAssign)), ast.dump(node)[:80]
            for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
                name = getattr(call.func, "attr", None) or getattr(call.func, "id", None)
                assert name in allowed_calls, name

    def test_existing_producers_keep_their_keys_and_ttl(self):
        src = (BACKEND / "app/tasks/precompute_admin_health.py").read_text()
        for key in ("bainluck:admin:audit_all", "bainluck:admin:link_rate", "bainluck:admin:matured_linkage"):
            assert f'"{key}"' in src
        assert cov._ADMIN_HEALTH_CACHE_TTL == 3600
        assert cov.EVENT_SOURCE_COVERAGE_RETAIN_SECONDS == 3600
