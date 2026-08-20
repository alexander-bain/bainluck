"""#1680 — /api/calibration declares whether its PRODUCER is still running.

The failure these tests exist for, measured in production on 2026-08-17:

* ``precompute_calibration_main`` last published ``2026-08-14T00:16:08Z``.
* ``consecutive_failures = 88`` — every hourly beat since died on a statement
  timeout in the ``futures`` phase.
* ``GET /api/calibration`` answered **HTTP 200**, 0.68s, for the whole outage.

The payload was not silent about its AGE — ``generated_at`` and ``cache.age_s``
were both there, and Queue 324 had already put ``availability`` on every tier.
What it was silent about is that **age and producer-health are different facts**:
``availability = "stale"`` is the same word for a memo that lapsed forty minutes
ago and for an artifact nothing has rebuilt in four days. A reader who wanted the
second had to know the beat cadence, do the division, and pick a threshold —
three things a consumer must never have to supply.

What is deliberately NOT here: a 503. Ruling CAL-P017 (Alex, 2026-08-08) is
standing — every serving tier was once bounded by ``SERVE_MAX_AGE_S``, they all
refused in the same instant, and /calibration went dark. **Stale-with-declaration
beats dark.** So ``test_a_stalled_producer_is_served_200_never_refused`` asserts
the status code, not merely "no exception": a 503 on this path is the
regression, and the 1-4 min post-release 503 (``_unavailable``, availability
``empty``) is a different path that these tests leave untouched.

The fails-first test is
``TestTheSignalFires::test_a_four_day_old_snapshot_declares_its_producer_stalled``
— it reproduces the exact production reading (a 3.7-day-old durable snapshot)
and fails on the pre-#1680 route, which declared that copy ``stale`` with no
statement about the producer at all.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils import durable_state as ds
from app.utils import request_cache as rc
from app.utils.availability_envelope import (
    AVAILABILITY_DEGRADED,
    AVAILABILITY_FRESH,
    AVAILABILITY_STALE,
)
from app.utils.calibration_publish_gate import (
    PRODUCER_STALL_AGE_S,
    PRODUCER_STALL_BEATS,
    PUBLISH_INTERVAL_S,
    SERVE_MAX_AGE_S,
    producer_stall,
)

# pytest.ini runs asyncio in AUTO mode; no module-level mark, so the synchronous
# unit tests below are not decorated with one they do not want.


def _ago(*, hours: float) -> str:
    """A stamp ``hours`` back that is ALWAYS in the past, at any wall clock.

    Gotcha #44: offset FIRST, then truncate. A ``replace(hour=...)`` idiom pins
    an hour rather than an age, so the age swings a full day with the clock and
    the suite goes red every afternoon. Nothing here branches on the clock.
    """
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _payload(*, hours_old: float, outcomes: int = 1_000_000) -> dict:
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
        "population_version": CALIBRATION_POPULATION_VERSION,
        "generated_at": _ago(hours=hours_old),
    }


class _FakeRedis:
    def __init__(self, *, main=None, last_good=None):
        self._values = {
            "bainluck:calibration:main": main,
            "bainluck:calibration:main:last_good": last_good,
        }

    async def get(self, key):
        return self._values.get(key)


def _use(monkeypatch, client):
    async def _getter():
        return client

    monkeypatch.setattr(rc, "get_shared_async_redis", _getter)
    return client


def _durable_db(payload: dict):
    """A DB whose only durable row is this payload, dated from its own stamp."""
    from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

    stamp = datetime.fromisoformat(payload["generated_at"])
    row = {
        "identity": "calibration:main",
        "schema_version": CALIBRATION_POPULATION_VERSION,
        "generation": ds.generation_for(stamp),
        "generated_at": stamp,
        "payload": payload,
        "checksum": ds.checksum_payload(payload),
        "complete": True,
        "source": "precompute_calibration",
    }
    db = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = row
    db.execute.return_value = result
    return db


@pytest.fixture(autouse=True)
def _fresh_process():
    from app.routes import calibration

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()
    yield
    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()


def _no_compute(monkeypatch):
    from app.tasks import precompute_calibration

    async def _boom(db):
        raise AssertionError("the request path must never build")

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _boom)


# ---------------------------------------------------------------------------
# The threshold itself
# ---------------------------------------------------------------------------


class TestTheThreshold:
    def test_the_threshold_is_a_named_constant_derived_from_the_beat(self):
        """Not a magic number in a branch. ``PRODUCER_STALL_AGE_S`` is the beat
        cadence times a beat count, so changing the cadence cannot silently
        leave the threshold behind."""
        assert PUBLISH_INTERVAL_S == 3600
        assert PRODUCER_STALL_AGE_S == PUBLISH_INTERVAL_S * PRODUCER_STALL_BEATS

    def test_the_threshold_is_looser_than_the_watchdog_alarm(self):
        """The watchdog's ``calibration_publish_age`` pages an operator at 2
        beats on suspicion; this states a fact to every anonymous reader. The
        response must never be the one crying wolf, so it may not be tighter."""
        assert PRODUCER_STALL_BEATS >= 2

    def test_the_threshold_is_far_tighter_than_the_serving_bound(self):
        """``SERVE_MAX_AGE_S`` is 7 DAYS — a sensible bound for whether a copy is
        still worth serving, and a nonsense one for an HOURLY task. Collapsing
        the two is what let a four-day outage read as ``fresh``."""
        assert PRODUCER_STALL_AGE_S < SERVE_MAX_AGE_S / 24


class TestProducerStallUnit:
    def test_a_recent_publish_is_not_stalled(self):
        out = producer_stall({"generated_at": _ago(hours=1)})
        assert out["stalled"] is False
        assert out["beats_missed"] == 1
        assert out["stall_after_s"] == PRODUCER_STALL_AGE_S

    def test_exactly_at_the_threshold_is_not_yet_stalled(self):
        """A boundary stated once, so a later refactor cannot drift it."""
        now = datetime.now(timezone.utc)
        payload = {
            "generated_at": (now - timedelta(seconds=PRODUCER_STALL_AGE_S)).isoformat()
        }
        assert producer_stall(payload, now=now)["stalled"] is False

    def test_one_second_past_the_threshold_is_stalled(self):
        now = datetime.now(timezone.utc)
        payload = {
            "generated_at": (
                now - timedelta(seconds=PRODUCER_STALL_AGE_S + 1)
            ).isoformat()
        }
        assert producer_stall(payload, now=now)["stalled"] is True

    def test_an_undateable_payload_is_stalled_not_healthy(self):
        """Gotcha #53: an absent timestamp and a healthy one are not the same
        reading, and the reassuring one must not be the default. The memo tier
        already applies this rule to freshness; the producer verdict agrees."""
        out = producer_stall({"buckets": []})
        assert out["stalled"] is True
        assert out["age_s"] is None
        assert out["beats_missed"] is None

    def test_it_counts_missed_beats_not_just_seconds(self):
        """The number an operator actually wants: "nothing has been built for 90
        beats" is legible in a way that "324,000 seconds" is not."""
        out = producer_stall({"generated_at": _ago(hours=90)})
        assert out["beats_missed"] == 90


# ---------------------------------------------------------------------------
# The signal on the wire
# ---------------------------------------------------------------------------


class TestTheSignalFires:
    async def test_a_four_day_old_snapshot_declares_its_producer_stalled(
        self, monkeypatch
    ):
        """FAILS-FIRST. The exact production reading on 2026-08-17: the durable
        tier serves a snapshot generated 2026-08-14T00:16Z while 88 consecutive
        beats have died. Before #1680 this came back ``availability: stale``
        with no statement about the producer at all — indistinguishable, to any
        consumer, from a memo that lapsed an hour ago."""
        from app.routes import calibration

        aged = _payload(hours_old=88)
        _use(monkeypatch, _FakeRedis(main=None, last_good=None))
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=_durable_db(aged))

        assert out["producer"]["stalled"] is True
        assert out["producer"]["beats_missed"] == 88
        assert out["producer"]["task"] == "precompute_calibration_main"
        assert out["producer"]["stall_after_s"] == PRODUCER_STALL_AGE_S
        assert out["availability"] == AVAILABILITY_STALE

    async def test_a_stalled_producer_is_served_200_never_refused(self, monkeypatch):
        """Ruling CAL-P017, pinned as behaviour rather than as a comment: the
        page must not go dark for age. A raised HTTPException here is the
        regression this asserts against."""
        from fastapi import HTTPException
        from fastapi.responses import JSONResponse

        from app.routes import calibration

        aged = _payload(hours_old=88)
        _use(monkeypatch, _FakeRedis(main=None, last_good=None))
        _no_compute(monkeypatch)

        try:
            out = await calibration.public_calibration(db=_durable_db(aged))
        except HTTPException as exc:  # pragma: no cover - the regression
            pytest.fail(f"a stalled producer must not refuse: {exc.status_code}")

        assert not isinstance(out, JSONResponse), "a stalled producer must not 503"
        assert out["total_outcomes"] == 1_000_000, "the curve is still served"

    async def test_a_stalled_main_key_cannot_be_declared_fresh(self, monkeypatch):
        """The hole that made the outage invisible at tier 1.

        ``main`` is admitted on ``snapshot_verdict(..., max_age_s=SERVE_MAX_AGE_S)``
        — SEVEN DAYS — so a copy days past its 2h TTL scored ``ok`` and was
        stamped ``fresh``. The inline justification was "its 2h TTL bounds its
        age": an assumption the consumer held about the producer, which fails
        exactly when the producer is the thing that broke.
        """
        from app.routes import calibration

        aged = _payload(hours_old=30)
        _use(monkeypatch, _FakeRedis(main=json.dumps(aged)))
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=object())

        assert out["producer"]["stalled"] is True
        assert out["availability"] == AVAILABILITY_STALE

    async def test_the_memo_cannot_launder_a_stalled_copy_back_to_fresh(
        self, monkeypatch
    ):
        """The in-process memo re-derives its declaration from content, and the
        producer verdict must be re-derived with it — otherwise the second
        request heals what the first correctly marked."""
        from app.routes import calibration

        aged = _payload(hours_old=30)
        _use(monkeypatch, _FakeRedis(main=json.dumps(aged)))
        _no_compute(monkeypatch)

        first = await calibration.public_calibration(db=object())
        assert first["producer"]["stalled"] is True

        class _DeadRedis:
            async def get(self, key):
                raise ConnectionError("redis down")

        _use(monkeypatch, _DeadRedis())
        second = await calibration.public_calibration(db=object())
        assert second["producer"]["stalled"] is True
        assert second["availability"] != AVAILABILITY_FRESH


class TestTheSignalStaysQuietWhenItShould:
    async def test_a_healthy_producer_declares_fresh_and_not_stalled(
        self, monkeypatch, healthy_staged_bank
    ):
        """Honesty runs both ways. A one-beat-old copy is exactly what a working
        hourly producer looks like, and calling it stalled would train every
        reader to ignore the field."""
        from app.routes import calibration

        _use(monkeypatch, _FakeRedis(main=json.dumps(_payload(hours_old=1))))
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=object())

        assert out["producer"]["stalled"] is False
        assert out["availability"] == AVAILABILITY_FRESH

    async def test_a_two_hour_old_copy_is_healthy_because_the_ttl_allows_it(
        self, monkeypatch, healthy_staged_bank
    ):
        """``_MAIN_CACHE_TTL`` is 7200s, so a HEALTHY producer can serve a copy
        two beats old. The threshold is derived from that fact rather than
        chosen, and this is the test that keeps it honest."""
        from app.routes import calibration

        _use(monkeypatch, _FakeRedis(main=json.dumps(_payload(hours_old=2))))
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=object())

        assert out["producer"]["stalled"] is False
        assert out["availability"] == AVAILABILITY_FRESH

    async def test_a_degraded_copy_is_never_healed_by_the_producer_stamp(
        self, monkeypatch
    ):
        """Q330/B1's clamp, re-asserted through the new single exit: ``_serve``
        may weaken a declaration, never strengthen one. A shape-unvalidated but
        RECENT payload must stay ``degraded`` — 'the producer is running' is not
        evidence that what it produced is whole."""
        from app.routes import calibration

        stub = {"buckets": [1, 2], "generated_at": _ago(hours=1)}
        _use(monkeypatch, _FakeRedis(main=json.dumps(stub)))
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=object())

        assert out["producer"]["stalled"] is False
        assert out["availability"] == AVAILABILITY_DEGRADED
