"""Queue 324 — ruling 025's availability envelope on /api/calibration (#1680).

The endpoint has five ways of answering and, before this queue, two vocabularies
for saying which one it used: a ``cache`` block on the dated tiers, provenance on
two of them, and — on the tier that matters most here — nothing at all.

What these tests pin:

* **Every serving tier declares.** ``availability ∈ {fresh, stale, degraded,
  empty}``, on all five answers including the 503. The ruling's acceptance test
  is an absolute ("no code path serves substitute content without a declared
  state"), and an absolute is only checkable by enumeration, so this file
  enumerates the tiers.
* **An over-``SERVE_MAX_AGE_S`` payload is SERVED, 200, declared ``stale``.** Not
  503. That is Alex's explicit instruction and the CAL-P017 reversal:
  stale-with-declaration beats dark. A 503 on this path is a regression, which is
  why it is asserted as a status code and not merely as "not an exception".
* **The tier-1 hole is closed.** ``main`` was accepted whenever its verdict was
  not ``wrong_version`` — so a ``too_old`` or ``malformed`` copy went out
  unmarked, justified by an inline assumption that the producer's 2h TTL bounds
  the age. A stopped producer is the failure in play, so that assumption fails
  exactly when it is load-bearing. Both now declare; neither is refused, because
  refusing on shape at that tier is what Queue 300B deliberately ruled out.

Route-level throughout: these drive ``public_calibration`` against a fake Redis
and a mocked durable row, so they prove the real branch structure.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.utils import durable_state as ds
from app.utils import request_cache as rc
from app.utils.availability_envelope import (
    AVAILABILITY_DEGRADED,
    AVAILABILITY_EMPTY,
    AVAILABILITY_FRESH,
    AVAILABILITY_STALE,
    AVAILABILITY_VALUES,
    declare,
)
from app.utils.calibration_publish_gate import SERVE_MAX_AGE_S

# No module-level ``asyncio`` mark: pytest.ini runs asyncio in AUTO mode, so the
# async tests are collected without one — and a blanket mark would attach to this
# file's synchronous vocabulary tests and warn on every run.


def _at(*, days_ago: float = 0.0) -> str:
    """A stamp N days back that is always in the PAST (gotcha #44).

    Anchored an hour behind now and truncated to the hour: a fixed-hour-of-today
    idiom produces a future timestamp on a pre-noon CI run, and a future stamp is
    ``malformed`` here by design, so the suite would fail for a clock reason
    rather than a code one.
    """
    base = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(
        minute=0, second=0, microsecond=0
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
    def __init__(self, *, main=None, last_good=None):
        self._values = {
            "bainluck:calibration:main": main,
            "bainluck:calibration:main:last_good": last_good,
        }

    async def get(self, key):
        return self._values.get(key)


class _DeadRedis:
    async def get(self, key):
        raise ConnectionError("Error 111 connecting to rediss://host:10819")


def _use(monkeypatch, client):
    async def _getter():
        return client

    monkeypatch.setattr(rc, "get_shared_async_redis", _getter)
    return client


def _durable_db(payload, *, generated_at=None):
    from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

    stamp = generated_at or datetime.now(timezone.utc) - timedelta(hours=5)
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


def _empty_db():
    db = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = None
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
# The vocabulary itself
# ---------------------------------------------------------------------------


class TestVocabulary:
    def test_exactly_four_states(self):
        """Ruling 025 clause 5 pairs each state with exactly ONE client
        rendering, which is only a checkable claim while the set is closed."""
        assert AVAILABILITY_VALUES == {"fresh", "stale", "degraded", "empty"}

    def test_an_invented_state_is_refused_not_stamped(self):
        """A typo'd state reads to a consumer exactly like an undeclared one, so
        it fails loudly here instead of quietly at the client."""
        with pytest.raises(ValueError):
            declare({}, "stale_hit")

    def test_declare_does_not_mutate_its_input(self):
        payload = {"buckets": []}
        out = declare(payload, AVAILABILITY_FRESH)
        assert "availability" not in payload
        assert out["availability"] == "fresh"

    def test_the_cache_metric_buckets_are_not_the_vocabulary(self):
        """Clause 2, pinned. ``miss`` is fresh-but-uncached, not ``empty``; the
        two vocabularies are the same size and two words rhyme, which is why the
        ruling forbids the map by name rather than trusting judgment."""
        for metric_word in ("miss", "hit", "stale_hit", "error"):
            assert metric_word not in AVAILABILITY_VALUES


# ---------------------------------------------------------------------------
# Every tier declares
# ---------------------------------------------------------------------------


class TestEveryTierDeclares:
    async def test_fresh_main_declares_fresh(self, monkeypatch):
        from app.routes import calibration

        _use(monkeypatch, _FakeRedis(main=json.dumps(_payload())))
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=object())

        assert out["availability"] == AVAILABILITY_FRESH
        # Honesty runs both ways: a current copy carries no stale marker.
        assert out.get("cache", {}).get("status") != "stale"

    async def test_in_process_memo_declares_from_the_content_it_serves(self, monkeypatch):
        """Tier 1 re-derives rather than replaying the stamp it stored.

        "It was fresh when I memoized it" is a claim about the past, and the memo
        can hold a copy for a full CACHE_TTL.
        """
        from app.routes import calibration

        _use(monkeypatch, _FakeRedis(main=json.dumps(_payload())))
        _no_compute(monkeypatch)

        first = await calibration.public_calibration(db=object())
        assert first["availability"] == AVAILABILITY_FRESH

        # Second read cannot reach Redis at all — it must come off the memo.
        _use(monkeypatch, _DeadRedis())
        second = await calibration.public_calibration(db=object())
        assert second["availability"] == AVAILABILITY_FRESH
        assert second["total_outcomes"] == 1_000_000

    async def test_a_memo_of_an_unvalidated_copy_never_heals_to_fresh(self, monkeypatch):
        """An incomplete payload with a recent timestamp is recent AND still
        incomplete — age alone must not upgrade the declaration."""
        from app.routes import calibration

        stub = {"buckets": [1, 2], "generated_at": _at(days_ago=0.01)}
        _use(monkeypatch, _FakeRedis(main=json.dumps(stub)))
        _no_compute(monkeypatch)

        first = await calibration.public_calibration(db=object())
        assert first["availability"] == AVAILABILITY_DEGRADED

        _use(monkeypatch, _DeadRedis())
        second = await calibration.public_calibration(db=object())
        assert second["availability"] == AVAILABILITY_DEGRADED

    async def test_dated_last_good_declares_stale(self, monkeypatch):
        from app.routes import calibration

        lg = _payload(generated_at=_at(days_ago=2))
        _use(monkeypatch, _FakeRedis(main=None, last_good=json.dumps(lg)))
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=object())

        assert out["availability"] == AVAILABILITY_STALE
        # The existing vocabulary is untouched — this is an addition, not a rename.
        assert out["cache"]["status"] == "stale"
        assert out["cache"]["reason"] == "main_key_absent"

    async def test_durable_tier_declares_stale(self, monkeypatch):
        from app.routes import calibration

        _use(monkeypatch, _DeadRedis())
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=_durable_db(_payload()))

        assert out["availability"] == AVAILABILITY_STALE
        assert out["provenance"]["source"] == "durable"

    async def test_nothing_anywhere_declares_empty(self, monkeypatch):
        from app.routes import calibration

        _use(monkeypatch, _DeadRedis())
        _no_compute(monkeypatch)

        with pytest.raises(HTTPException) as exc:
            await calibration.public_calibration(db=_empty_db())

        assert exc.value.status_code == 503
        # The refusal answers in the SAME vocabulary as every served response, so
        # a client reads one field across all five outcomes.
        assert exc.value.detail["availability"] == AVAILABILITY_EMPTY


# ---------------------------------------------------------------------------
# Over-age: served and declared, NEVER 503
# ---------------------------------------------------------------------------


class TestOverAgeIsServedNotRefused:
    async def test_over_serve_max_age_is_200_and_declared_stale(self, monkeypatch):
        """#1680's real contract, and the one Alex named explicitly.

        The alert's title claimed this path 503s once the last-good crosses
        ``SERVE_MAX_AGE_S``. It does not, by design (CAL-P017): the newest
        durable snapshot is served at ANY age, dated and declared. A 503 here is
        a FAILED behaviour, not a stricter one.
        """
        from app.routes import calibration

        ancient = datetime.now(timezone.utc) - timedelta(seconds=SERVE_MAX_AGE_S + 2 * 86400)
        payload = _payload(generated_at=ancient.isoformat())
        _use(monkeypatch, _DeadRedis())
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(
            db=_durable_db(payload, generated_at=ancient)
        )

        assert isinstance(out, dict)  # served, not raised
        assert out["availability"] == AVAILABILITY_STALE
        assert out["cache"]["reason"] == "durable_over_age"
        assert out["cache"]["age_s"] > SERVE_MAX_AGE_S
        assert out["cache"]["generated_at"]
        assert out["provenance"]["dated"] is True

    async def test_the_route_never_refuses_purely_for_age(self):
        """Pinned in source: no tier turns "old" into a refusal.

        ``_unavailable`` is reachable only from "nothing anywhere" and "budget
        exhausted" — never from an age comparison. Written as a source-shape
        assertion because the behavioural test above can only prove the paths it
        drives, and this is an absolute.
        """
        import inspect

        from app.routes import calibration as route

        src = inspect.getsource(route.public_calibration)
        assert '_unavailable("no_trustworthy_snapshot")' in src
        assert '_unavailable("route_budget_exhausted")' in src
        # Exactly two raise sites, both below the last-resort tier.
        assert src.count("raise _unavailable(") == 2
        assert src.index("durable_over_age") < src.index(
            '_unavailable("no_trustworthy_snapshot")'
        )


# ---------------------------------------------------------------------------
# The tier-1 hole (queue premise P6)
# ---------------------------------------------------------------------------


class TestMainKeyHole:
    async def test_a_too_old_main_key_is_no_longer_served_unmarked(self, monkeypatch):
        """The hole: ``main`` was accepted on any verdict but ``wrong_version``.

        The inline justification was "its 2h TTL bounds its age" — the consumer
        holding an assumption about the producer. #1680 IS the producer stopping,
        so the assumption fails precisely when it is load-bearing. A key that
        outlives its TTL (a paused eviction policy, a manual write, a restored
        snapshot) went out looking exactly like a current curve.
        """
        from app.routes import calibration

        old = _payload(generated_at=_at(days_ago=SERVE_MAX_AGE_S / 86400 + 1))
        _use(monkeypatch, _FakeRedis(main=json.dumps(old)))
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=_empty_db())

        assert out["availability"] == AVAILABILITY_STALE
        assert out["cache"]["status"] == "stale"
        assert out["cache"]["reason"] == "main_key_over_age"
        assert out["cache"]["age_s"] > SERVE_MAX_AGE_S
        # Still SERVED — declaring is not refusing.
        assert out["total_outcomes"] == 1_000_000

    async def test_a_shape_unvalidated_main_key_is_served_but_declared(self, monkeypatch):
        """Declared ``degraded``, not refused, and not called stale.

        Queue 300B deliberately refused to reject on shape here: a payload-shape
        addition would blank the page for a reason that is not a data problem.
        And it is not old, so stamping ``cache.status = "stale"`` would be a
        second false statement rather than a correction.
        """
        from app.routes import calibration

        partial = {"buckets": [{"bucket_idx": 0}], "generated_at": _at(days_ago=0.01)}
        _use(monkeypatch, _FakeRedis(main=json.dumps(partial)))
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=_empty_db())

        assert out["availability"] == AVAILABILITY_DEGRADED
        assert out.get("cache", {}).get("status") != "stale"
        assert out["buckets"] == [{"bucket_idx": 0}]

    async def test_a_wrong_version_main_still_loses_to_a_trustworthy_last_good(
        self, monkeypatch
    ):
        """The boundary of this change: declaring did not widen what is served.

        A payload built under another population contract means something
        different from what the page's labels say, and no banner fixes that.
        """
        from app.routes import calibration

        good_lg = _payload(generated_at=_at(days_ago=1))
        wrong = _payload(outcomes=42, version="q001-ancient")
        _use(
            monkeypatch,
            _FakeRedis(main=json.dumps(wrong), last_good=json.dumps(good_lg)),
        )
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=object())

        assert out["total_outcomes"] == 1_000_000
        assert out["availability"] == AVAILABILITY_STALE


# ---------------------------------------------------------------------------
# Existing consumers are untouched
# ---------------------------------------------------------------------------


class TestAdditiveNotARename:
    async def test_cache_and_provenance_survive_the_addition(self, monkeypatch):
        """The banner, ``data-cache-status`` and the population-contract gate all
        read the existing fields; ruling 025 adds a declaration, it does not
        rename one."""
        from app.routes import calibration

        _use(monkeypatch, _DeadRedis())
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=_durable_db(_payload()))

        assert set(out["cache"]) >= {"status", "reason", "age_s", "generated_at"}
        assert out["cache"]["status"] == "stale"
        assert out["provenance"]["identity"] == "calibration:main"
        assert out["provenance"]["complete"] is True
        assert out["availability"] in AVAILABILITY_VALUES

    async def test_availability_is_never_derived_from_cache_status(self, monkeypatch):
        """Clause 2 has a behavioural witness, not just a comment.

        ``stale`` and ``degraded`` both exist beside a payload whose ``cache``
        block says nothing distinguishing — the shape-unvalidated main tier
        declares ``degraded`` with NO ``cache`` marker at all, which no mapping
        from ``cache.status`` could ever produce.
        """
        from app.routes import calibration

        partial = {"buckets": [{"bucket_idx": 0}], "generated_at": _at(days_ago=0.01)}
        _use(monkeypatch, _FakeRedis(main=json.dumps(partial)))
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=_empty_db())

        assert out["availability"] == AVAILABILITY_DEGRADED
        assert "cache" not in out or out["cache"].get("status") != "stale"
