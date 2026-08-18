"""Queue 297 Item 1: /api/calibration fails HONEST, never opaque.

The reported public failure was a fresh anonymous load spinning ~18s and then
rendering "Failed to load calibration data". Two ~9s cold-compute attempts, each
individually inside its own per-stage deadline — which is precisely why a
per-stage bound could not catch it.

What must now hold on every path:

  * a fresh ``main`` key serves current data;
  * a main-key miss serves the durable last-good, explicitly DATED and marked
    stale — never dressed up as current;
  * a last-good that is malformed, written by another population version, or
    older than the age bound is REFUSED rather than served;
  * with nothing trustworthy anywhere, the answer is a typed unavailable
    response the page can render honestly with retry;
  * the whole handler is bounded by one absolute budget;
  * recovery is immediate — one good publish and the next request is fresh.

These are route-level tests: they drive ``public_calibration`` directly against
a fake Redis, so they prove the real branch structure rather than a mock of it.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.utils import request_cache as rc
from app.utils.calibration_publish_gate import SERVE_MAX_AGE_S
from tests.conftest import unavailable_body

pytestmark = pytest.mark.asyncio


def _at(*, days_ago: float = 0.0) -> str:
    """A stamp N days back that is ALWAYS in the past and ALWAYS that age.

    Offset FIRST, then truncate — the shape from ``test_calibration_durable_298``
    (gotcha #44, amended by Queue 329). The previous version pinned noon of
    *today* and subtracted from there, so the age it produced swung a full day
    with the wall clock: ``days_ago=2`` was 2.5 days old at 00:00 UTC and 1.5
    days old at 12:00 UTC, and ``days_ago=0`` was twelve hours in the FUTURE all
    morning. ``test_main_miss_serves_dated_last_good`` asserts an age inside
    (1.5d, 2.5d) — a window exactly as wide as the swing, so the suite was red
    at precisely 00:00 UTC, which is when CI most often runs.
    """
    base = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return base.replace(minute=0, second=0, microsecond=0).isoformat()


def _payload(*, outcomes: int = 1_000_000, version: str | None = None, generated_at=None):
    from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

    return {
        "buckets": [{"bucket_idx": 0, "n": outcomes, "winners": outcomes // 2}],
        "by_category": [{"category": "politics", "outcomes": outcomes}],
        "by_source": [{"source": "kalshi", "outcomes": outcomes}],
        "total_outcomes": outcomes,
        "total_markets": outcomes // 4,
        "total_winners": outcomes // 2,
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applies_to": "all"},
        "truth_evidence": {"contract_ok": True},
        "population_version": version or CALIBRATION_POPULATION_VERSION,
        "generated_at": generated_at or _at(days_ago=0.05),
    }


class _FakeRedis:
    """Serves canned values per key; records what was read."""

    def __init__(self, *, main=None, last_good=None):
        self._values = {
            "bainluck:calibration:main": main,
            "bainluck:calibration:main:last_good": last_good,
        }
        self.gets: list[str] = []

    async def get(self, key):
        self.gets.append(key)
        return self._values.get(key)

    def set_main(self, value):
        self._values["bainluck:calibration:main"] = value


def _use(monkeypatch, client):
    async def _getter():
        return client

    monkeypatch.setattr(rc, "get_shared_async_redis", _getter)
    return client


@pytest.fixture(autouse=True)
def _clean_state():
    from app.routes import calibration

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()
    yield
    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()


def _no_compute(monkeypatch):
    """Assert the cold compute never runs on the path under test."""
    from app.tasks import precompute_calibration

    async def _boom(db):
        raise AssertionError("cold compute ran on a path that had a usable snapshot")

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _boom)


# ---------------------------------------------------------------------------
# Fresh main
# ---------------------------------------------------------------------------


async def test_fresh_main_serves_current_data_unmarked(monkeypatch):
    from app.routes import calibration

    fresh = _payload()
    _use(monkeypatch, _FakeRedis(main=json.dumps(fresh)))
    _no_compute(monkeypatch)

    out = await calibration.public_calibration(db=object())

    assert out["total_outcomes"] == 1_000_000
    # A current payload carries no stale marker — honesty runs both ways.
    assert out.get("cache", {}).get("status") != "stale"


# ---------------------------------------------------------------------------
# Dated last-good
# ---------------------------------------------------------------------------


async def test_main_miss_serves_dated_last_good(monkeypatch):
    from app.routes import calibration

    lg = _payload(generated_at=_at(days_ago=2))
    _use(monkeypatch, _FakeRedis(main=None, last_good=json.dumps(lg)))
    _no_compute(monkeypatch)

    out = await calibration.public_calibration(db=object())

    assert out["cache"]["status"] == "stale"
    assert out["cache"]["reason"] == "main_key_absent"
    assert out["cache"]["generated_at"] == lg["generated_at"]
    # ~2 days, with generous slack for clock granularity.
    assert 1.5 * 86400 < out["cache"]["age_s"] < 2.5 * 86400


async def test_an_untrustworthy_main_falls_back_to_the_durable_last_good(monkeypatch):
    """C111 P2: every cache tier is validated, not just last-good.

    A wrong-version ``main`` rendered under current UI labels is uninterpretable,
    so it must lose to a trustworthy last-good rather than be served.
    """
    from app.routes import calibration

    good_lg = _payload(outcomes=1_000_000, generated_at=_at(days_ago=1))
    wrong_version_main = _payload(outcomes=42, version="q001-ancient")
    _use(
        monkeypatch,
        _FakeRedis(main=json.dumps(wrong_version_main), last_good=json.dumps(good_lg)),
    )
    _no_compute(monkeypatch)

    out = await calibration.public_calibration(db=object())

    assert out["total_outcomes"] == 1_000_000
    assert out["cache"]["status"] == "stale"


async def test_the_published_payload_names_its_population_contract():
    """C111 P2: the public artifact must carry its own population version.

    Without it the publish gate cannot tell an intended population change from a
    silent one, and no consumer can tell which contract it is looking at.
    """
    from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION
    from app.utils.calibration_publish_gate import census

    payload = _payload()

    assert payload["population_version"] == CALIBRATION_POPULATION_VERSION
    assert census(payload)["population_version"] == CALIBRATION_POPULATION_VERSION


# ---------------------------------------------------------------------------
# Untrustworthy last-good is REFUSED
# ---------------------------------------------------------------------------


async def test_too_old_last_good_is_refused(monkeypatch):
    """Past the age bound it is not a bridge, it is a misleading old curve."""
    from app.routes import calibration

    ancient = _payload(generated_at=_at(days_ago=SERVE_MAX_AGE_S / 86400 + 3))
    _use(monkeypatch, _FakeRedis(main=None, last_good=json.dumps(ancient)))
    monkeypatch.setattr(rc, "CALIBRATION_COMPUTE_DEADLINE_MS", 100)

    async def _hang(db):
        await asyncio.sleep(30)

    from app.tasks import precompute_calibration

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _hang)

    body = unavailable_body(await calibration.public_calibration(db=object()))

    assert body["status"] == "unavailable"


async def test_wrong_version_last_good_is_refused(monkeypatch):
    """A snapshot from another population version is not this build's curve."""
    from app.routes import calibration
    from app.tasks import precompute_calibration

    stale_version = _payload(version="q001-ancient")
    _use(monkeypatch, _FakeRedis(main=None, last_good=json.dumps(stale_version)))
    monkeypatch.setattr(rc, "CALIBRATION_COMPUTE_DEADLINE_MS", 100)

    async def _hang(db):
        await asyncio.sleep(30)

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _hang)

    unavailable_body(await calibration.public_calibration(db=object()))


@pytest.mark.parametrize(
    "bad",
    [
        "{not json at all",
        json.dumps({"buckets": [], "total_outcomes": 0}),
        json.dumps({"buckets": [{"n": 1}]}),  # missing every other section
        json.dumps(["a", "list", "not", "an", "object"]),
        json.dumps({"buckets": [{"n": 1}], "total_outcomes": 5}),  # no generated_at
    ],
)
async def test_malformed_last_good_is_refused(monkeypatch, bad):
    from app.routes import calibration
    from app.tasks import precompute_calibration

    _use(monkeypatch, _FakeRedis(main=None, last_good=bad))
    monkeypatch.setattr(rc, "CALIBRATION_COMPUTE_DEADLINE_MS", 100)

    async def _hang(db):
        await asyncio.sleep(30)

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _hang)

    body = unavailable_body(await calibration.public_calibration(db=object()))

    assert body["status"] == "unavailable"


async def test_one_bad_field_cannot_poison_a_complete_snapshot(monkeypatch):
    """Item 1: an unexpected extra/odd field is not a reason to blank the page."""
    from app.routes import calibration

    lg = _payload(generated_at=_at(days_ago=1))
    lg["some_future_section"] = {"unknown": object.__name__}
    lg["by_category"] = [{"category": "politics", "outcomes": None}]  # odd but present
    _use(monkeypatch, _FakeRedis(main=None, last_good=json.dumps(lg)))
    _no_compute(monkeypatch)

    out = await calibration.public_calibration(db=object())

    assert out["cache"]["status"] == "stale"
    assert out["total_outcomes"] == 1_000_000


# ---------------------------------------------------------------------------
# Typed unavailable — the "Failed to load" replacement
# ---------------------------------------------------------------------------


async def test_nothing_trustworthy_returns_a_typed_unavailable_response(monkeypatch):
    from app.routes import calibration
    from app.tasks import precompute_calibration

    _use(monkeypatch, _FakeRedis(main=None, last_good=None))
    monkeypatch.setattr(rc, "CALIBRATION_COMPUTE_DEADLINE_MS", 100)

    async def _hang(db):
        await asyncio.sleep(30)

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _hang)

    res = await calibration.public_calibration(db=object())
    body = unavailable_body(res)

    assert isinstance(body, dict), "the body must be typed, not a bare string"
    assert body["status"] == "unavailable"
    assert body["retry_after_s"] == 30
    assert body["reason"]
    assert "retry" in body["message"].lower()
    assert res.headers["Retry-After"] == "30"


# ---------------------------------------------------------------------------
# The absolute request budget
# ---------------------------------------------------------------------------


async def test_whole_request_is_bounded_by_the_absolute_budget(monkeypatch):
    """The 18-second shape: bounded end to end, not just per stage."""
    from app.routes import calibration
    from app.tasks import precompute_calibration

    _use(monkeypatch, _FakeRedis(main=None, last_good=None))
    monkeypatch.setattr(rc, "CALIBRATION_ROUTE_BUDGET_MS", 400)
    # A per-stage deadline far LARGER than the remaining budget: without the
    # absolute bound this would run 30s.
    monkeypatch.setattr(rc, "CALIBRATION_COMPUTE_DEADLINE_MS", 30_000)

    async def _hang(db):
        await asyncio.sleep(30)

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _hang)

    loop = asyncio.get_running_loop()
    start = loop.time()
    unavailable_body(await calibration.public_calibration(db=object()))
    elapsed_ms = (loop.time() - start) * 1000

    assert elapsed_ms < 2_000, f"handler ran {elapsed_ms:.0f}ms, budget was 400ms"


async def test_an_exhausted_budget_answers_immediately_instead_of_computing(monkeypatch):
    from app.routes import calibration
    from app.tasks import precompute_calibration

    _use(monkeypatch, _FakeRedis(main=None, last_good=None))
    monkeypatch.setattr(rc, "CALIBRATION_ROUTE_BUDGET_MS", 0)

    async def _boom(db):
        raise AssertionError("a compute was started with no budget left")

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _boom)

    body = unavailable_body(await calibration.public_calibration(db=object()))

    assert body["reason"] == "route_budget_exhausted"


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


async def test_recovery_is_immediate_once_main_is_republished(monkeypatch):
    """A degraded copy must not wedge the dyno — the next good publish wins."""
    from app.routes import calibration

    client = _use(
        monkeypatch,
        _FakeRedis(main=None, last_good=json.dumps(_payload(generated_at=_at(days_ago=2)))),
    )
    _no_compute(monkeypatch)

    degraded = await calibration.public_calibration(db=object())
    assert degraded["cache"]["status"] == "stale"

    # The beat republishes.
    client.set_main(json.dumps(_payload(outcomes=1_050_000)))

    recovered = await calibration.public_calibration(db=object())
    assert recovered["total_outcomes"] == 1_050_000
    assert recovered.get("cache", {}).get("status") != "stale"


async def test_a_stale_copy_is_never_cached_as_though_it_were_fresh(monkeypatch):
    """Every request re-attempts main, so staleness cannot become permanent."""
    from app.routes import calibration

    client = _use(
        monkeypatch,
        _FakeRedis(main=None, last_good=json.dumps(_payload(generated_at=_at(days_ago=1)))),
    )
    _no_compute(monkeypatch)

    await calibration.public_calibration(db=object())
    reads_after_first = client.gets.count("bainluck:calibration:main")
    await calibration.public_calibration(db=object())

    assert client.gets.count("bainluck:calibration:main") > reads_after_first


# ---------------------------------------------------------------------------
# CAL-P070 (#1955): a version bump is not an outage
# ---------------------------------------------------------------------------
#
# 2026-08-02: the version was bumped, ``snapshot_verdict`` refused every cached
# artifact as ``wrong_version`` the instant the dyno booted, /calibration went
# dark, and the bump was reverted within the hour. The ratified rollover contract
# already said what should happen — ``deploy-before-candidate`` serves the
# predecessor DATED, DEGRADED and READ-ONLY — but no code implemented it, so the
# corpus passed 26/26 while production 503'd. These drive the real handler
# through the real bump.


async def test_a_declared_predecessor_keeps_the_page_lit_after_a_bump(monkeypatch):
    from app.routes import calibration
    from app.tasks import precompute_calibration as pc

    previous = _payload(outcomes=706_290, version="q267")
    monkeypatch.setattr(pc, "CALIBRATION_POPULATION_VERSION", "q268")
    monkeypatch.setattr(pc, "COMPATIBLE_PREVIOUS_POPULATION_VERSIONS", ("q267",))
    _use(monkeypatch, _FakeRedis(main=json.dumps(previous)))
    _no_compute(monkeypatch)

    out = await calibration.public_calibration(db=object())

    assert out["total_outcomes"] == 706_290, "the page must not go dark on a bump"
    # ...but it must never claim to be the current curve.
    assert out["availability"] == "degraded"
    assert out["cache"]["status"] == "stale"
    assert out["cache"]["reason"] == "population_version_superseded"
    assert out["cache"]["population_version"] == "q267"
    assert out["cache"]["expected_population_version"] == "q268"
    assert out["cache"]["version_relation"] == "previous"


async def test_an_undeclared_predecessor_is_still_dark_after_a_bump(monkeypatch):
    """CAL-P017 is intact where nobody declared anything.

    The declaration is the whole difference. Without it a cross-version artifact
    is still refused at every tier — which is the correct outcome for a bump that
    really did move the methodology.
    """
    from app.routes import calibration
    from app.tasks import precompute_calibration as pc

    previous = _payload(outcomes=706_290, version="q267")
    monkeypatch.setattr(pc, "CALIBRATION_POPULATION_VERSION", "q268")
    monkeypatch.setattr(pc, "COMPATIBLE_PREVIOUS_POPULATION_VERSIONS", ())
    _use(monkeypatch, _FakeRedis(main=json.dumps(previous), last_good=json.dumps(previous)))
    monkeypatch.setattr(rc, "CALIBRATION_COMPUTE_DEADLINE_MS", 100)

    body = unavailable_body(await calibration.public_calibration(db=object()))

    assert body["status"] == "unavailable"


async def test_a_predecessor_is_never_promoted_into_the_current_caches(monkeypatch):
    """``read_only`` / ``may_seed_current: false``, and it is load-bearing.

    Every other dated tier ends with ``remember_last_good``. Doing that here
    would re-save the predecessor on every request, so it would outlive its own
    rollover window and the page would keep serving q267 numbers long after a
    q268 build existed to replace them.
    """
    from app.routes import calibration
    from app.tasks import precompute_calibration as pc

    previous = _payload(outcomes=706_290, version="q267")
    monkeypatch.setattr(pc, "CALIBRATION_POPULATION_VERSION", "q268")
    monkeypatch.setattr(pc, "COMPATIBLE_PREVIOUS_POPULATION_VERSIONS", ("q267",))
    _use(monkeypatch, _FakeRedis(main=json.dumps(previous)))
    _no_compute(monkeypatch)

    await calibration.public_calibration(db=object())

    assert calibration._cache["data"] is None, "a predecessor must not seed the process cache"
    assert rc.recall_last_good("calibration:main", max_age_s=SERVE_MAX_AGE_S) is None


async def test_the_first_current_build_immediately_displaces_the_predecessor(monkeypatch):
    """Recovery: the rollover window closes by itself, on the first publish."""
    from app.routes import calibration
    from app.tasks import precompute_calibration as pc

    monkeypatch.setattr(pc, "CALIBRATION_POPULATION_VERSION", "q268")
    monkeypatch.setattr(pc, "COMPATIBLE_PREVIOUS_POPULATION_VERSIONS", ("q267",))
    client = _use(
        monkeypatch, _FakeRedis(main=json.dumps(_payload(outcomes=706_290, version="q267")))
    )
    _no_compute(monkeypatch)

    superseded = await calibration.public_calibration(db=object())
    assert superseded["availability"] == "degraded"

    client.set_main(json.dumps(_payload(outcomes=832_650, version="q268")))

    recovered = await calibration.public_calibration(db=object())
    assert recovered["total_outcomes"] == 832_650
    assert recovered["availability"] == "fresh"
    assert recovered.get("cache", {}).get("status") != "stale"
