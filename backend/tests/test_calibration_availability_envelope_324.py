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

from app.utils import durable_state as ds
from app.utils import request_cache as rc
from app.utils.availability_envelope import (
    AVAILABILITY_DEGRADED,
    AVAILABILITY_EMPTY,
    AVAILABILITY_FIELD,
    AVAILABILITY_FRESH,
    AVAILABILITY_STALE,
    AVAILABILITY_VALUES,
    declare,
    never_stronger,
)
from app.utils.calibration_publish_gate import SERVE_MAX_AGE_S
from tests.conftest import unavailable_body

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

        body = unavailable_body(await calibration.public_calibration(db=_empty_db()))

        # The refusal answers in the SAME vocabulary as every served response, so
        # a client reads one field across all five outcomes. Read off the
        # serialized body — see TestOneWirePath for why the exception attribute
        # this used to assert on was the wrong boundary.
        assert body[AVAILABILITY_FIELD] == AVAILABILITY_EMPTY


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
        # Exactly two refusal sites, both below the last-resort tier. Q330 turned
        # these from ``raise`` into ``return`` (the refusal is a composed response
        # now, so its wire shape matches the served answers) — the count is what
        # this test was ever about, not the keyword.
        assert src.count("return _unavailable(") == 2
        assert "raise _unavailable(" not in src
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


# ---------------------------------------------------------------------------
# Queue 330 / B1 defect 1 — a re-wrap may weaken a declaration, never heal one
# ---------------------------------------------------------------------------


class TestARewrapNeverHeals:
    """C272/B1 found this with an independent attack on the real route while
    this file's 112 tests were green, which is the finding worth keeping: every
    test above drives a tier ONCE, and the defect lives in the SECOND wrap.

    The main tier admits a shape-unvalidated copy and correctly calls it
    ``degraded``. The process-local fallback later picks that same copy up,
    knows only that it is old, and re-declares it ``stale`` — a word this
    vocabulary defines as *complete, merely aged*. Nothing about the content
    changed; the promise about it got better.
    """

    async def test_the_b1_attack_no_longer_reproduces(self, monkeypatch):
        """degraded -> (memo expiry + Redis down + no durable row) -> degraded."""
        from app.routes import calibration

        # 1. The main tier admits an unvalidatable copy and declares it degraded.
        partial = {"buckets": [{"bucket_idx": 0}], "generated_at": _at(days_ago=0.01)}
        _use(monkeypatch, _FakeRedis(main=json.dumps(partial)))
        _no_compute(monkeypatch)

        first = await calibration.public_calibration(db=_empty_db())
        assert first["availability"] == AVAILABILITY_DEGRADED

        # 2. The memo TTL lapses, so tier 1 can no longer answer...
        calibration._cache["timestamp"] = 0
        # ...and Redis fails while no durable row exists, which is the only way
        # to reach the process-local fallback at the bottom of the handler.
        _use(monkeypatch, _DeadRedis())

        second = await calibration.public_calibration(db=_empty_db())

        # 3. Same bytes, same incompleteness — so the same declaration.
        assert second["availability"] == AVAILABILITY_DEGRADED, (
            "the process-local fallback healed a degraded payload into stale: "
            "'stale' promises a whole copy whose only compromise is age"
        )
        assert second["cache"]["reason"] == "redis_unavailable"
        # The cache vocabulary is untouched and still says "stale" — the two
        # vocabularies are deliberately independent (ruling 025 clause 2), and
        # this asserts the fix did NOT collapse one into the other.
        assert second["cache"]["status"] == "stale"

    async def test_a_complete_old_copy_is_still_stale_through_the_same_tier(
        self, monkeypatch
    ):
        """The clamp must not over-fire: B1 confirmed this path was correct, and
        a fix that drags every fallback down to ``degraded`` would be a second
        false statement, not a correction."""
        from app.routes import calibration

        _use(monkeypatch, _FakeRedis(main=json.dumps(_payload(generated_at=_at()))))
        _no_compute(monkeypatch)

        first = await calibration.public_calibration(db=_empty_db())
        assert first["availability"] == AVAILABILITY_FRESH

        calibration._cache["timestamp"] = 0
        _use(monkeypatch, _DeadRedis())

        second = await calibration.public_calibration(db=_empty_db())

        assert second["availability"] == AVAILABILITY_STALE
        assert second["cache"]["reason"] == "redis_unavailable"


class TestNeverStronger:
    """The clamp itself, over the whole vocabulary rather than the one pair the
    route happens to hit today."""

    @pytest.mark.parametrize(
        "current,proposed,expected",
        [
            # The B1 pair: the weaker existing claim survives.
            (AVAILABILITY_DEGRADED, AVAILABILITY_STALE, AVAILABILITY_DEGRADED),
            (AVAILABILITY_DEGRADED, AVAILABILITY_FRESH, AVAILABILITY_DEGRADED),
            (AVAILABILITY_STALE, AVAILABILITY_FRESH, AVAILABILITY_STALE),
            # Weakening is always allowed — a later tier can know something worse.
            (AVAILABILITY_FRESH, AVAILABILITY_STALE, AVAILABILITY_STALE),
            (AVAILABILITY_FRESH, AVAILABILITY_DEGRADED, AVAILABILITY_DEGRADED),
            (AVAILABILITY_STALE, AVAILABILITY_DEGRADED, AVAILABILITY_DEGRADED),
            # Equal is equal.
            (AVAILABILITY_STALE, AVAILABILITY_STALE, AVAILABILITY_STALE),
            # No prior claim: the serving tier decides, unclamped.
            (None, AVAILABILITY_STALE, AVAILABILITY_STALE),
        ],
    )
    def test_the_ordering(self, current, proposed, expected):
        assert never_stronger(current, proposed) == expected

    def test_an_unreadable_prior_claim_is_no_claim(self):
        """A typo tells a consumer exactly as little as an absent field, and
        ranking it would be a second guess stacked on a first."""
        assert never_stronger("stale_hit", AVAILABILITY_STALE) == AVAILABILITY_STALE

    def test_empty_is_not_a_claim_content_can_make(self):
        """``empty`` means NOTHING was served. A payload on its way to a client
        contradicts it, and honouring it would ship a body full of numbers
        declared absent."""
        assert never_stronger(AVAILABILITY_EMPTY, AVAILABILITY_STALE) == AVAILABILITY_STALE

    def test_an_invalid_proposal_still_raises_where_it_should(self):
        """The clamp must not swallow a bad state — ``declare`` owns that error,
        and its message names the offending value."""
        assert never_stronger(AVAILABILITY_STALE, "stale_hit") == "stale_hit"
        with pytest.raises(ValueError):
            declare({}, never_stronger(AVAILABILITY_STALE, "stale_hit"))


# ---------------------------------------------------------------------------
# Queue 330 / B1 defect 2 — ONE wire-level availability path, 503 included
# ---------------------------------------------------------------------------


def _wire_client(monkeypatch, *, db):
    """A REAL HTTP client over the real app — the only boundary that can certify
    a wire contract.

    Everything above this line calls ``public_calibration`` directly and reads a
    Python dict. That is why Queue 324 shipped believing a client could read one
    field across all five outcomes when it could not: ``HTTPException(detail=
    {...})`` serializes NESTED, so the four served answers carried
    ``availability`` at the top level and the refusal carried it at
    ``detail.availability``. An in-process call never renders that difference —
    the exception object holds the detail dict either way — so 112 green tests
    saw nothing. A test that cannot see the wire cannot certify the wire.
    """
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.database import get_db

    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


class TestOneWirePath:
    """Synchronous on purpose: ``TestClient`` drives the app through its own
    portal, so these read the bytes the route actually puts on the socket."""

    def test_the_503_declares_at_the_same_top_level_path_as_a_200(self, monkeypatch):
        """B1 defect 2, reproduced and closed.

        Read with the SAME expression — ``body["availability"]`` — on both a
        served answer and the refusal. A primitive with one exception is not a
        primitive, so the assertion is deliberately written as one expression
        applied twice rather than two shapes checked separately.
        """
        gen = _wire_client(monkeypatch, db=_empty_db())
        client = next(gen)
        try:
            # The refusal goes FIRST, deliberately: a served answer memoizes
            # itself as this process's last-good, and the bottom tier would then
            # answer 200 from it — correctly, which is the whole CAL-P017 point.
            # "Nothing anywhere" has to mean nothing anywhere.
            _use(monkeypatch, _DeadRedis())
            refused = client.get("/api/calibration")

            assert refused.status_code == 503
            assert refused.json()[AVAILABILITY_FIELD] == AVAILABILITY_EMPTY, (
                "the refusal hid its declaration under `detail` — a client must "
                "not special-case the hardest path to reach"
            )

            _use(monkeypatch, _FakeRedis(main=json.dumps(_payload(generated_at=_at()))))
            served = client.get("/api/calibration")

            assert served.status_code == 200
            # Same expression, both outcomes. That is the whole contract.
            assert served.json()[AVAILABILITY_FIELD] == AVAILABILITY_FRESH
        finally:
            next(gen, None)

    def test_the_503_keeps_retry_after_and_its_legacy_detail_mirror(self, monkeypatch):
        """The shipped web page renders its "temporarily unavailable" state from
        ``error.detail.status`` / ``.reason`` / ``.message``
        (``frontend/app/calibration/page.tsx``). Moving the declaration up must
        not take that surface down — on a queue whose entire point is that the
        page does not go dark."""
        gen = _wire_client(monkeypatch, db=_empty_db())
        client = next(gen)
        try:
            _use(monkeypatch, _DeadRedis())
            refused = client.get("/api/calibration")
            body = refused.json()

            assert refused.status_code == 503
            assert refused.headers["Retry-After"] == "30"
            assert body["status"] == "unavailable"
            assert body["reason"] == "no_trustworthy_snapshot"
            assert body["retry_after_s"] == 30
            assert "retry" in body["message"].lower()

            mirror = body["detail"]
            assert mirror["status"] == "unavailable"
            assert mirror["reason"] == body["reason"]
            assert mirror["message"] == body["message"]
        finally:
            next(gen, None)

    def test_a_dated_answer_declares_on_the_wire_too(self, monkeypatch):
        """The third of the five outcomes, over HTTP: served, 200, dated, and
        declared at the same path as the other four."""
        gen = _wire_client(monkeypatch, db=_empty_db())
        client = next(gen)
        try:
            old = _payload(generated_at=_at(days_ago=SERVE_MAX_AGE_S / 86400 + 1))
            _use(monkeypatch, _FakeRedis(main=json.dumps(old)))

            res = client.get("/api/calibration")
            body = res.json()

            assert res.status_code == 200
            assert body[AVAILABILITY_FIELD] == AVAILABILITY_STALE
            assert body["cache"]["reason"] == "main_key_over_age"
        finally:
            next(gen, None)
