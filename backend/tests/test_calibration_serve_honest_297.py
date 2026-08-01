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
from fastapi import HTTPException

from app.utils import request_cache as rc
from app.utils.calibration_publish_gate import SERVE_MAX_AGE_S

pytestmark = pytest.mark.asyncio


def _at(*, days_ago: float = 0.0) -> str:
    """A fixed-hour timestamp N days back (gotcha #44: never straddle midnight)."""
    base = datetime.now(timezone.utc).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    return (base - timedelta(days=days_ago)).isoformat()


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

    out = await calibration.public_calibration(db=object(), bust=0)

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

    out = await calibration.public_calibration(db=object(), bust=0)

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

    out = await calibration.public_calibration(db=object(), bust=0)

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

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(db=object(), bust=0)

    assert exc.value.status_code == 503
    assert exc.value.detail["status"] == "unavailable"


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

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(db=object(), bust=0)

    assert exc.value.status_code == 503


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

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(db=object(), bust=0)

    assert exc.value.status_code == 503
    assert exc.value.detail["status"] == "unavailable"


async def test_one_bad_field_cannot_poison_a_complete_snapshot(monkeypatch):
    """Item 1: an unexpected extra/odd field is not a reason to blank the page."""
    from app.routes import calibration

    lg = _payload(generated_at=_at(days_ago=1))
    lg["some_future_section"] = {"unknown": object.__name__}
    lg["by_category"] = [{"category": "politics", "outcomes": None}]  # odd but present
    _use(monkeypatch, _FakeRedis(main=None, last_good=json.dumps(lg)))
    _no_compute(monkeypatch)

    out = await calibration.public_calibration(db=object(), bust=0)

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

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(db=object(), bust=0)

    detail = exc.value.detail
    assert isinstance(detail, dict), "the body must be typed, not a bare string"
    assert detail["status"] == "unavailable"
    assert detail["retry_after_s"] == 30
    assert detail["reason"]
    assert "retry" in detail["message"].lower()
    assert exc.value.headers["Retry-After"] == "30"


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
    with pytest.raises(HTTPException):
        await calibration.public_calibration(db=object(), bust=0)
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

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(db=object(), bust=0)

    assert exc.value.detail["reason"] == "route_budget_exhausted"


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

    degraded = await calibration.public_calibration(db=object(), bust=0)
    assert degraded["cache"]["status"] == "stale"

    # The beat republishes.
    client.set_main(json.dumps(_payload(outcomes=1_050_000)))

    recovered = await calibration.public_calibration(db=object(), bust=0)
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

    await calibration.public_calibration(db=object(), bust=0)
    reads_after_first = client.gets.count("bainluck:calibration:main")
    await calibration.public_calibration(db=object(), bust=0)

    assert client.gets.count("bainluck:calibration:main") > reads_after_first
