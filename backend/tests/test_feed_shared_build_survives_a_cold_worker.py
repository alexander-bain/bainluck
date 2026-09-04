"""RED-FIRST GATE for LAT-P103 — #2143's residual: the shared stage artifacts
must survive a COLD WORKER.

## The ship

A user WITH personalization state — Alex is user 364, 139 rows in the 30-day
affinity window and 13 in the 14-day dismiss window — opens Discover and it
loads inside the client's hard 6s budget.

#2203 shipped the inert-principal short-circuit: a principal whose
`PersonalizationContext` is structurally equal to a default one reads the
anonymous entry instead of building. Alex's context is NOT equal to a default
one, so that fix does not reach him, and #2203 says so in its own closing
section:

    A principal with live personalization state still pays its own cold build.
    [...] That residual needs the principal-independent stage artifacts to
    survive a cold worker — #2143's module is process-local by design.

This file is that gate. It does not assert a duration (a timing assertion on a
cache is a flake generator, and LAT-P084's own gate says so). It asserts a
BUILD COUNT across a simulated worker boundary: the artifact is built once by
one worker and READ, not rebuilt, by a worker whose process-local tier is
empty.

## Why "cold worker" is not a hypothetical

Production runs several web dynos at `WEB_CONCURRENCY=2`, so the process that
built an artifact is one of many, and every deploy, every dyno cycle and every
worker restart empties the local tier. With a 60s TTL, most requests from a
personalized principal land on a worker that has to rebuild — the artifact was
shareable across processes all along, the module simply had nowhere to put it.

## What "simulating a cold worker" means here, precisely

`clear_shared_builds()` empties the process-local tier and DOES NOT touch
Redis. That is exactly the state of a freshly-booted worker sitting next to a
warm one: no local artifacts, full view of the shared tier. Anything the second
call gets after that clear, it got across the worker boundary.

## The fake

`ColdWorkerRedis` serves ONLY the stage tier's own key prefix and raises a
connection error for every other key. That is deliberate. The feed's RESPONSE
cache, the candidate base and the singleflight registry all share the same
client, and handing them a working Redis would let #2203's inert-principal
share answer request B from the anonymous entry — which would make this file
pass while proving nothing about the stage tier. Keeping every other key on the
error path preserves the exact conditions LAT-P084's gate already runs under
(`X-Feed-Cache: error`, a real cold build per principal) and changes one thing:
the stage tier can now reach across workers.
"""

from __future__ import annotations

import asyncio
import json
import math
import zlib
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils import principal_independent_cache as pic

# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------


class ColdWorkerRedis:
    """A Redis that holds the stage tier and nothing else. See the module docstring."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.gets = 0
        self.sets = 0
        #: None | "error" | "stall" — injected failure for the stage tier only.
        self.fail: str | None = None

    def _stage_key(self, key: str) -> bool:
        return str(key).startswith(pic.REDIS_KEY_PREFIX)

    async def get(self, key):
        if not self._stage_key(key):
            raise ConnectionError("only the stage tier is served by this fake")
        self.gets += 1
        if self.fail == "error":
            raise ConnectionError("injected")
        if self.fail == "stall":
            await asyncio.sleep(5)
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        if not self._stage_key(key):
            raise ConnectionError("only the stage tier is served by this fake")
        self.sets += 1
        if self.fail == "error":
            raise ConnectionError("injected")
        if self.fail == "stall":
            await asyncio.sleep(5)
        self.store[key] = value
        return True


@pytest.fixture
def cold_worker_redis(monkeypatch):
    """Install `ColdWorkerRedis` as the process-shared async client."""
    from app.utils import request_cache as _rc

    fake = ColdWorkerRedis()

    async def _get_client():
        return fake

    monkeypatch.setattr(_rc, "get_shared_async_redis", _get_client)
    return fake


@pytest.fixture(autouse=True)
def _clean_shared_cache():
    """Start and end every test with an empty PROCESS-LOCAL tier.

    A process-global cache that leaks between tests produces the single most
    misleading failure mode available here: a test that passes because a
    previous test warmed the thing it is trying to prove gets warmed.
    """
    pic.clear_shared_builds()
    yield
    pic.clear_shared_builds()


def _concept_card(key: str = "ufc-329") -> dict:
    """A concept card shaped like `_score_event_concepts` emits, plus the
    non-JSON scalars `assert_plain_data` admits — because those are exactly the
    values a naive wire format would silently change on the way across."""
    return {
        "type": "concept",
        "score": 71.5,
        "headline": "UFC 329 — main card tonight",
        "data": {
            "key": key,
            "name": "UFC 329",
            "domain": "mma",
            "start_date": date(2026, 8, 27),
            "commence_time": datetime(2026, 8, 27, 2, 30, tzinfo=timezone.utc),
            "implied_probability": Decimal("0.6125"),
            "is_major": True,
            "entry_count": 0,
            "tags": ["mma", "marquee"],
        },
        "_marquee_pin": True,
        "_sort_time": 1787594136.0,
    }


class _Counter:
    """A builder that records how many times it actually ran."""

    def __init__(self, value):
        self.value = value
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        return self.value


# --------------------------------------------------------------------------
# THE HEADLINE GATE
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_cold_worker_reads_the_artifact_instead_of_rebuilding_it(
    cold_worker_redis,
):
    """THE gate for #2143's residual.

    Worker A builds. Worker B starts with an empty process-local tier — a fresh
    dyno, a restarted worker, or simply the other `WEB_CONCURRENCY` process —
    and must READ the artifact, not rebuild it."""
    key = ("all", (), 55_555)
    builder = _Counter([_concept_card()])

    worker_a = await pic.get_or_build("concepts", key, builder)
    assert builder.calls == 1
    assert cold_worker_redis.sets == 1, "worker A never published the artifact"

    # The worker boundary: local tier empty, shared tier intact.
    pic.clear_shared_builds()

    worker_b = await pic.get_or_build("concepts", key, builder)

    assert builder.calls == 1, (
        "the cold worker rebuilt the principal-INDEPENDENT artifact "
        f"({builder.calls} builds); #2143's residual is that it should not"
    )
    assert worker_b == worker_a, "the cold worker got a DIFFERENT artifact"


@pytest.mark.asyncio
async def test_the_cold_worker_read_is_reported_as_cross_worker_on_the_header(
    cold_worker_redis,
):
    """`X-Feed-Shared` already said "concepts was reused". That was true before
    this change too, from the local tier. Only `cross_worker` says the residual
    is closed, so the tier has to be nameable — and from a closed vocabulary."""
    key = ("all", (), 55_556)
    builder = _Counter([_concept_card()])

    warm_tiers: list[str] = []
    with pic.reuse_scope([], warm_tiers):
        await pic.get_or_build("concepts", key, builder)
        # Same worker, second request: local tier, no Redis hop.
        gets_before = cold_worker_redis.gets
        await pic.get_or_build("concepts", key, builder)
    assert warm_tiers == [pic.SHARED_TIER_LOCAL]
    assert cold_worker_redis.gets == gets_before, (
        "a process-local HIT went to Redis — that is the round trip the module "
        "docstring refuses, and it is not needed to close the residual"
    )

    pic.clear_shared_builds()

    cold_tiers: list[str] = []
    cold_names: list[str] = []
    with pic.reuse_scope(cold_names, cold_tiers):
        await pic.get_or_build("concepts", key, builder)

    assert cold_tiers == [pic.SHARED_TIER_CROSS_WORKER]
    assert cold_names == ["concepts"]
    assert set(cold_tiers) <= pic.SHARED_TIER_NAMES


@pytest.mark.asyncio
async def test_stats_separate_a_cross_worker_hit_from_a_local_one(cold_worker_redis):
    """A share that works and a share that survives a cold worker are
    different claims. An ops panel that cannot tell them apart cannot notice
    the second one regressing back to the first."""
    key = ("all", (), 55_557)
    builder = _Counter([_concept_card()])

    await pic.get_or_build("concepts", key, builder)
    await pic.get_or_build("concepts", key, builder)  # local hit

    warm = pic.shared_build_stats()
    assert warm["builds"] == 1
    assert warm["hits"] == 1
    assert warm["cross_worker_publishes"] == 1
    assert warm["cross_worker_hits"] == 0

    # `clear_shared_builds()` resets the counters too, which is the right
    # reading of a worker boundary: a cold worker starts with cold counters.
    pic.clear_shared_builds()
    await pic.get_or_build("concepts", key, builder)  # cross-worker hit

    cold = pic.shared_build_stats()
    assert cold["cross_worker_hits"] == 1
    assert cold["builds"] == 0, "the cold worker built instead of reading"
    assert cold["cross_worker_enabled"] == 1
    assert builder.calls == 1


# --------------------------------------------------------------------------
# the wire codec — exactly invertible, or nothing is published
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_cold_worker_gets_the_same_TYPES_not_merely_the_same_text(
    cold_worker_redis,
):
    """The failure this exists to stop is invisible: a `datetime` that comes
    back as a `str` on one worker and a `datetime` on another produces two
    different feeds for the same question, and neither one errors."""
    key = ("all", (), 55_558)
    builder = _Counter([_concept_card()])

    warm = await pic.get_or_build("concepts", key, builder)
    pic.clear_shared_builds()
    cold = await pic.get_or_build("concepts", key, builder)

    assert builder.calls == 1
    warm_data, cold_data = warm[0]["data"], cold[0]["data"]
    for field in ("start_date", "commence_time", "implied_probability"):
        assert type(cold_data[field]) is type(warm_data[field]), (
            f"{field} crossed the worker boundary as "
            f"{type(cold_data[field]).__name__}, not "
            f"{type(warm_data[field]).__name__}"
        )
        assert cold_data[field] == warm_data[field]


def test_the_codec_round_trips_every_type_the_plain_data_guard_admits():
    """The codec and `assert_plain_data` must agree on their type space. If the
    guard admits something the codec drops, that value crosses a worker
    boundary lossily — silently."""
    value = {
        "none": None,
        "bool": True,
        "int": -7,
        "float": 71.5,
        "str": "UFC 329 — main card",
        "naive_dt": datetime(2026, 8, 27, 2, 30, 15, 123456),
        "aware_dt": datetime(2026, 8, 27, 2, 30, tzinfo=timezone.utc),
        "date": date(2026, 8, 27),
        "decimal": Decimal("0.61250"),
        "list": [1, "two", None, date(2026, 1, 1)],
        "tuple": (1, "two", Decimal("3")),
        "nested": {"a": {"b": [{"c": datetime(2026, 8, 27, 0, 0)}]}},
        "int_keys": {1: "one", 2: "two"},
        "mixed_keys": {None: "n", True: "t", 3: "three", "s": "str"},
        "empty_dict": {},
        "empty_list": [],
    }
    pic.assert_plain_data(value)

    restored = pic.decode_shared_payload(pic.encode_shared_payload(value))

    assert restored == value
    assert type(restored["naive_dt"]) is datetime
    assert restored["naive_dt"].microsecond == 123456
    assert restored["aware_dt"].tzinfo is not None
    assert type(restored["date"]) is date and not isinstance(restored["date"], datetime)
    assert type(restored["decimal"]) is Decimal
    assert str(restored["decimal"]) == "0.61250"
    assert type(restored["tuple"]) is tuple
    assert list(restored["int_keys"]) == [1, 2]
    assert set(restored["mixed_keys"]) == {None, True, 3, "s"}


def test_a_payload_carrying_the_codec_sentinel_as_a_real_key_still_round_trips():
    """The sentinel is a reserved key in the wire format. A payload that
    happens to use the same string as a real dict key must not be mangled by
    it — the escape hatch exists so the rare case cannot corrupt anything."""
    value = {pic._TAG: "a real value", "other": [{pic._TAG: 1}]}
    assert pic.decode_shared_payload(pic.encode_shared_payload(value)) == value


def test_non_finite_floats_cross_as_themselves_rather_than_becoming_null():
    """`orjson` would turn these into `null`, which is a WRONG score, not a
    missing one. The codec is a mirror, not a filter."""
    restored = pic.decode_shared_payload(
        pic.encode_shared_payload({"nan": float("nan"), "inf": float("inf")})
    )
    assert math.isnan(restored["nan"])
    assert restored["inf"] == float("inf")


# --------------------------------------------------------------------------
# fail-closed on sharing, fail-open on the response
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_orm_shaped_value_never_reaches_redis(cold_worker_redis):
    """`assert_plain_data` already refuses it for the local tier. The gate here
    is that the refusal happens BEFORE publication — #2107 is a cross-request
    cached ORM row, and a Redis tier would widen its blast radius from one
    worker to every worker."""

    class FakeORMRow:
        def __init__(self):
            self._sa_instance_state = object()

    builder = _Counter([{"row": FakeORMRow()}])
    out = await pic.get_or_build("concepts", ("orm", (), 1), builder)

    assert out is builder.value, "the response must still be served"
    assert cold_worker_redis.sets == 0, "an ORM-shaped value was published"
    assert cold_worker_redis.store == {}


@pytest.mark.asyncio
async def test_an_over_cap_payload_is_refused_rather_than_published(
    cold_worker_redis, monkeypatch
):
    """Decoding holds the GIL for the whole C-level parse (gotcha #38). An
    unbounded payload would trade a DB stage for an event-loop stall, which is
    how a latency fix becomes a latency bug."""
    monkeypatch.setattr(pic, "MAX_ENVELOPE_BYTES", 128)
    builder = _Counter([{"blob": "x" * 4096}])

    out = await pic.get_or_build("concepts", ("big", (), 1), builder)

    assert out == builder.value
    assert cold_worker_redis.sets == 0
    assert pic.shared_build_stats()["cross_worker_publish_refused"] == 1

    # The LOCAL tier is unaffected — an over-cap artifact is still shared
    # within the worker that built it.
    assert (await pic.get_or_build("concepts", ("big", (), 1), builder)) == out
    assert builder.calls == 1


@pytest.mark.asyncio
async def test_a_redis_error_degrades_to_building_and_never_raises(cold_worker_redis):
    """Every second-tier failure must land the caller back on "build it the way
    we build it today". A cache that can 500 the endpoint it was added to speed
    up is a net loss at any hit rate."""
    key = ("all", (), 55_559)
    builder = _Counter([_concept_card()])

    cold_worker_redis.fail = "error"
    out = await pic.get_or_build("concepts", key, builder)
    assert out == builder.value
    assert builder.calls == 1

    pic.clear_shared_builds()
    out2 = await pic.get_or_build("concepts", key, builder)
    assert out2 == builder.value
    assert builder.calls == 2, "a failing Redis must not stop the build"
    assert pic.shared_build_stats()["cross_worker_failures"] >= 2


@pytest.mark.asyncio
async def test_a_stalled_redis_is_bounded_and_still_serves(cold_worker_redis):
    """The hop is speculative — it is trying to avoid work, and losing it costs
    only the work we were going to do anyway. So it fails FAST rather than
    adding a visible tax to the miss path."""
    key = ("all", (), 55_560)
    builder = _Counter([_concept_card()])
    cold_worker_redis.fail = "stall"

    started = asyncio.get_running_loop().time()
    out = await pic.get_or_build("concepts", key, builder)
    elapsed_ms = (asyncio.get_running_loop().time() - started) * 1000

    assert out == builder.value
    # One bounded read + one bounded publish, each capped; generous headroom so
    # this is a bound assertion, not a performance assertion.
    assert elapsed_ms < 4 * pic.REDIS_READ_DEADLINE_MS, elapsed_ms


@pytest.mark.parametrize(
    "planted",
    [
        pytest.param("{not json", id="a_predecessors_uncompressed_string"),
        pytest.param(b"\x78\x9c not a zlib stream", id="a_truncated_write"),
        pytest.param(
            zlib.compress(b"{not json", 1), id="a_valid_stream_holding_garbage"
        ),
    ],
)
@pytest.mark.asyncio
async def test_a_malformed_envelope_is_a_miss_not_a_crash(cold_worker_redis, planted):
    """Anything can be in a Redis key: a truncated write, a predecessor's
    format, another lane's typo.

    LAT-P221 gives the value TWO layers — a zlib stream carrying JSON — so the
    cases are parametrized rather than merged: a fix that only guarded the JSON
    would pass the third case and crash on the first two."""
    key = ("all", (), 55_561)
    builder = _Counter([_concept_card()])
    cold_worker_redis.store[pic.redis_key_for("concepts", key)] = planted

    out = await pic.get_or_build("concepts", key, builder)

    assert out == builder.value
    assert builder.calls == 1


@pytest.mark.asyncio
async def test_an_entry_that_inflates_past_the_decode_budget_is_refused_unread(
    cold_worker_redis, monkeypatch
):
    """The decode bound is a bound on the READER, not a promise about the writer.

    A 1 KB Redis value can inflate to a hundred megabytes, and the whole point
    of `MAX_ENVELOPE_BYTES` is that no worker spends its event loop finding that
    out (gotcha #38). So `wire_decode` stops the inflation at the budget rather
    than measuring the result afterwards."""
    monkeypatch.setattr(pic, "MAX_ENVELOPE_BYTES", 1024)
    key = ("all", (), 55_567)
    # Compresses to ~100 bytes; inflates to 64 KB, 64x the budget.
    bomb = zlib.compress(json.dumps({"v": 1, "blob": "x" * 65536}).encode(), 1)
    assert len(bomb) < 1024, "the fixture has to be SMALL to prove anything"
    cold_worker_redis.store[pic.redis_key_for("concepts", key)] = bomb
    builder = _Counter([_concept_card()])

    out = await pic.get_or_build("concepts", key, builder)

    assert out == builder.value
    assert builder.calls == 1, "an over-budget stream was inflated and read"
    assert pic.wire_decode(bomb) is None


@pytest.mark.asyncio
async def test_an_over_storage_cap_artifact_is_refused_rather_than_published(
    cold_worker_redis, monkeypatch
):
    """The second of the two bounds LAT-P221 separated. Redis is a shared 100 MB
    LRU, so an artifact can be well inside the decode budget and still be too
    antisocial to store — and the refusal must be for THAT reason, measured on
    the compressed blob, not on the JSON."""
    monkeypatch.setattr(pic, "MAX_ENVELOPE_BYTES", 64 * 1024 * 1024)
    monkeypatch.setattr(pic, "MAX_STORED_BYTES", 256)
    # Random-ish text so zlib cannot squeeze it under the storage cap.
    incompressible = "".join(f"{i:x}" for i in range(20_000))
    builder = _Counter([{"blob": incompressible}])

    out = await pic.get_or_build("concepts", ("bulky", (), 2), builder)

    assert out == builder.value
    assert cold_worker_redis.sets == 0
    assert pic.shared_build_stats()["cross_worker_publish_refused"] == 1

    # Same contract as the decode-cap refusal: the LOCAL tier is unaffected.
    assert (await pic.get_or_build("concepts", ("bulky", (), 2), builder)) == out
    assert builder.calls == 1


@pytest.mark.asyncio
async def test_what_redis_holds_is_compressed_not_raw_json(cold_worker_redis):
    """The storage bound can stay at the 2 MB that was always right for Redis
    only because the stored form is a zlib stream. If a future edit publishes
    raw JSON again, the artifact this whole cycle is about stops fitting."""
    key = ("all", (), 55_568)
    await pic.get_or_build("concepts", key, _Counter([_concept_card()]))

    stored = cold_worker_redis.store[pic.redis_key_for("concepts", key)]

    assert isinstance(stored, bytes), "the stored value is not the wire form"
    assert b'"stored_wall"' not in stored, "the envelope went to Redis as raw JSON"
    assert json.loads(pic.wire_decode(stored))["ns"] == "concepts"


@pytest.mark.asyncio
async def test_a_digest_collision_costs_a_rebuild_never_a_wrong_artifact(
    cold_worker_redis,
):
    """The Redis key is a digest, and a digest is a hash. The envelope carries
    the original key's repr and the reader re-checks it, so two distinct cache
    keys landing on one Redis key can only ever cost work."""
    real_key = ("all", (), 55_562)
    other_key = ("nfl", (), 99_999)
    other_builder = _Counter([_concept_card("other-card")])

    await pic.get_or_build("concepts", other_key, other_builder)
    forged = cold_worker_redis.store[pic.redis_key_for("concepts", other_key)]
    # Plant the OTHER key's artifact at this key's digest.
    cold_worker_redis.store[pic.redis_key_for("concepts", real_key)] = forged

    pic.clear_shared_builds()
    builder = _Counter([_concept_card("real-card")])
    out = await pic.get_or_build("concepts", real_key, builder)

    assert builder.calls == 1, "a colliding envelope was served"
    assert out[0]["data"]["key"] == "real-card"


@pytest.mark.asyncio
async def test_a_namespace_mismatch_is_refused(cold_worker_redis):
    """The same guard, on the other axis: an envelope written for one namespace
    must never answer for another."""
    key = ("all", (), 55_563)
    await pic.get_or_build("concepts", key, _Counter([_concept_card()]))
    envelope = cold_worker_redis.store[pic.redis_key_for("concepts", key)]
    cold_worker_redis.store[pic.redis_key_for("canonical_counts", key)] = envelope

    pic.clear_shared_builds()
    builder = _Counter([[{"k": 1}, {"k": ["kalshi"]}]])
    out = await pic.get_or_build("canonical_counts", key, builder)

    assert builder.calls == 1
    assert out == builder.value


@pytest.mark.asyncio
async def test_an_entry_older_than_the_ttl_is_refused_by_the_readers_wall_clock(
    cold_worker_redis, monkeypatch
):
    """The local tier ages on `time.monotonic`, which means nothing in the
    process that wrote the entry. Redis `EX` is the backstop; the reader's own
    age check against `stored_wall` is the bound."""
    key = ("all", (), 55_564)
    builder = _Counter([_concept_card()])
    await pic.get_or_build("concepts", key, builder, ttl_s=60.0)

    redis_key = pic.redis_key_for("concepts", key)
    envelope = json.loads(pic.wire_decode(cold_worker_redis.store[redis_key]))
    envelope["stored_wall"] = envelope["stored_wall"] - 3600
    cold_worker_redis.store[redis_key] = pic.wire_encode(json.dumps(envelope))

    pic.clear_shared_builds()
    out = await pic.get_or_build("concepts", key, builder, ttl_s=60.0)

    assert builder.calls == 2, "a one-hour-old artifact was served under a 60s TTL"
    assert out == builder.value


@pytest.mark.asyncio
async def test_a_clock_ahead_writer_is_read_as_fresh_not_as_stale(cold_worker_redis):
    """A negative age means the WRITER's clock runs ahead. The entry is younger
    than it looks, so clamping to zero is the conservative reading — the
    alternative is a fleet that stops sharing whenever NTP drifts."""
    key = ("all", (), 55_565)
    builder = _Counter([_concept_card()])
    await pic.get_or_build("concepts", key, builder)

    redis_key = pic.redis_key_for("concepts", key)
    envelope = json.loads(pic.wire_decode(cold_worker_redis.store[redis_key]))
    envelope["stored_wall"] = envelope["stored_wall"] + 30
    cold_worker_redis.store[redis_key] = pic.wire_encode(json.dumps(envelope))

    pic.clear_shared_builds()
    await pic.get_or_build("concepts", key, builder)

    assert builder.calls == 1


@pytest.mark.asyncio
async def test_the_cold_worker_gets_its_own_copy_it_cannot_poison(cold_worker_redis):
    """The display chain mutates items in place. Two cold workers reading the
    same envelope must not be able to scribble on each other."""
    key = ("all", (), 55_566)
    await pic.get_or_build("concepts", key, _Counter([_concept_card()]))

    pic.clear_shared_builds()
    first = await pic.get_or_build("concepts", key, _Counter([_concept_card()]))
    first[0]["score"] = -999
    first[0]["data"]["name"] = "SCRIBBLED"

    pic.clear_shared_builds()
    second = await pic.get_or_build("concepts", key, _Counter([_concept_card()]))

    assert second[0]["score"] == 71.5
    assert second[0]["data"]["name"] == "UFC 329"


# --------------------------------------------------------------------------
# kill switches
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_cross_worker_switch_reverts_to_exactly_the_local_tier(
    cold_worker_redis, monkeypatch
):
    """A rollback of THIS change must need no deploy, and must not give back
    #2143's original process-local win."""
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "0")
    key = ("all", (), 55_567)
    builder = _Counter([_concept_card()])

    await pic.get_or_build("concepts", key, builder)
    assert cold_worker_redis.sets == 0 and cold_worker_redis.gets == 0

    # Local tier still shares.
    await pic.get_or_build("concepts", key, builder)
    assert builder.calls == 1

    # Cold worker rebuilds — which is precisely the pre-LAT-P103 behaviour.
    pic.clear_shared_builds()
    await pic.get_or_build("concepts", key, builder)
    assert builder.calls == 2
    assert cold_worker_redis.gets == 0
    assert pic.shared_build_stats()["cross_worker_enabled"] == 0


@pytest.mark.asyncio
async def test_the_ttl_kill_switch_still_disables_both_tiers(
    cold_worker_redis, monkeypatch
):
    """`FEED_SHARED_BUILD_TTL_S=0` was the whole-module kill switch before this
    change and must remain the whole-module kill switch after it."""
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "0")
    builder = _Counter([_concept_card()])

    await pic.get_or_build("concepts", ("all", (), 55_568), builder)
    await pic.get_or_build("concepts", ("all", (), 55_568), builder)

    assert builder.calls == 2
    assert cold_worker_redis.sets == 0
    assert cold_worker_redis.gets == 0


# --------------------------------------------------------------------------
# end to end, through the route
# --------------------------------------------------------------------------


@pytest.fixture
async def cold_worker_client(monkeypatch):
    """The LAT-P084 two-principal harness. See that file for why the DB is
    mocked; the difference here is the worker boundary between the requests."""
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    from app.main import app
    from unittest.mock import MagicMock

    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = None
    result.fetchall.return_value = []
    result.all.return_value = []
    result.first.return_value = None
    session.execute.return_value = result

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def counting_concepts(monkeypatch):
    """Count the principal-INDEPENDENT build and the principal-DEPENDENT one.

    `personalization == 2` is the independent witness that two real cold builds
    happened, so `concepts == 1` can only mean sharing — without it, a second
    request that never built at all would satisfy the same assertion."""
    from app.routes import feed as feed_module

    counts: dict[str, list] = {"concepts": [], "personalization": []}

    async def _stub(db, now, sport_filter, ctx=None):
        counts["concepts"].append({"sport_filter": sport_filter})
        return [_concept_card()]

    _real_ctx = feed_module._load_personalization_context

    async def _counting_ctx(*a, **kw):
        counts["personalization"].append(1)
        return await _real_ctx(*a, **kw)

    monkeypatch.setattr(feed_module, "_score_event_concepts", _stub)
    monkeypatch.setattr(feed_module, "_load_personalization_context", _counting_ctx)
    return counts


@pytest.mark.asyncio
async def test_the_route_serves_a_second_principal_from_a_cold_worker(
    cold_worker_client, cold_worker_redis, counting_concepts
):
    """The ship, end to end: principal A builds on one worker; the local tier
    is emptied (the worker boundary); principal B — a DIFFERENT principal, on a
    cold worker — is served the concept stage without rebuilding it, and says
    so on the wire."""
    r1 = await cold_worker_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "cold-principal-A"}
    )
    assert r1.status_code == 200, r1.text

    pic.clear_shared_builds()

    r2 = await cold_worker_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "cold-principal-B"}
    )
    assert r2.status_code == 200, r2.text

    # Both must be genuine builds, or this proves caching rather than sharing.
    assert r1.headers.get("X-Feed-Cache") in ("miss", "error"), dict(r1.headers)
    assert r2.headers.get("X-Feed-Cache") in ("miss", "error"), dict(r2.headers)
    assert len(counting_concepts["personalization"]) == 2, (
        "both requests must have reached a real cold build for this test to say "
        f"anything; personalization ran {len(counting_concepts['personalization'])}x"
    )

    assert len(counting_concepts["concepts"]) == 1, (
        "the principal-independent concept build ran "
        f"{len(counting_concepts['concepts'])} times across a worker boundary; "
        "#2143's residual is that it should run once"
    )
    assert "concepts" in r2.headers.get("X-Feed-Shared", "").split(",")
    assert pic.SHARED_TIER_CROSS_WORKER in r2.headers.get(
        "X-Feed-Shared-Tier", ""
    ).split(","), dict(r2.headers)


@pytest.fixture
def no_redis_at_all(monkeypatch):
    """A client where EVERY key fails — the Redis-outage case, stated rather
    than inherited from whatever the test host happens to be running."""
    from app.utils import request_cache as _rc

    class DeadRedis:
        async def get(self, key):
            raise ConnectionError("redis is down")

        async def set(self, key, value, ex=None):
            raise ConnectionError("redis is down")

    async def _get_client():
        return DeadRedis()

    monkeypatch.setattr(_rc, "get_shared_async_redis", _get_client)


@pytest.mark.asyncio
async def test_the_route_still_works_with_no_redis_at_all(
    cold_worker_client, no_redis_at_all, counting_concepts
):
    """Every stage-tier op fails. The feed must be exactly as good as it was
    before this change — which, for two principals on ONE warm worker, is still
    one shared concept build, served from the process-local tier."""
    r1 = await cold_worker_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "noredis-A"}
    )
    r2 = await cold_worker_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "noredis-B"}
    )

    assert r1.status_code == 200 and r2.status_code == 200
    assert len(counting_concepts["concepts"]) == 1
    assert "concepts" in r2.headers.get("X-Feed-Shared", "").split(",")
    assert r2.headers.get("X-Feed-Shared-Tier") == pic.SHARED_TIER_LOCAL


@pytest.mark.asyncio
async def test_the_tier_header_vocabulary_is_closed(
    cold_worker_client, cold_worker_redis, counting_concepts
):
    """A diagnostic header is only safe if its vocabulary is closed. Nothing
    principal-shaped, nothing free-form, can ever reach this byte."""
    await cold_worker_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "vocab-A"}
    )
    r2 = await cold_worker_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "vocab-B"}
    )

    value = r2.headers.get("X-Feed-Shared-Tier", "")
    assert value, dict(r2.headers)
    assert set(value.split(",")) <= pic.SHARED_TIER_NAMES
