"""GATE for LAT-P272 (#2143 residual) — the failure split needs a DYNO-INDEPENDENT
read, and the instrument must not appear in its own numbers.

## The ship

A reader opens Discover on a web worker whose cross-worker read just failed and
pays the rebuild the shared tier exists to avoid — 692-775 ms for `market_load`.
LAT-P225 made that failure name which of ten causes it was. It did not make the
name readable: `shared_build_stats()` is an in-memory dict, so
`/api/admin/shared-build-stats` answers from whichever of
(dynos x WEB_CONCURRENCY) processes served the request.

## Why that is a defect and not a caveat

Measured on production 2026-09-18 02:50-03:01Z:

    pid 11 (busy)   cross_worker_hits 25->31  misses 16->20  FAILURES 0 -> 0
    pid 10 (quiet)  cross_worker_hits 12->14  misses  8->10  FAILURES 4 -> 5

The defect IS the asymmetry. An instrument that samples one unidentified worker
at random cannot measure a per-worker asymmetry — N samples are N draws from an
unknown mixture — and Heroku pids repeat across dynos, so `worker_pid` cannot
even tell two workers apart. The same window paid for this twice:
`cross_worker_declined_age` was PRESENT after its release and its VALUE was
never readable.

## What these tests deliberately do NOT assert

Not a duration, not a failure rate, and not a flush CADENCE in wall-clock terms
(all three are flake generators — LAT-P084). They assert: the merge arithmetic,
that a generation a release replaced is printed but never summed, that a failed
read is never reported as a clean zero, that the instrument books nothing into
the counters it carries, and that the fast path never touches it.
"""

from __future__ import annotations

import json

import pytest

from app.utils import principal_independent_cache as pic
from app.utils import request_cache as _rc

NS = "market_load"
KEY = ("lat-p272",)


class _FakeRedis:
    """Stage tier + the rail hash. Per-op failure injection on the rail."""

    def __init__(self) -> None:
        self.store: dict[str, object] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.expires: dict[str, int] = {}
        self.get_error: BaseException | None = None
        self.hset_error: BaseException | None = None
        self.hgetall_error: BaseException | None = None
        self.hset_calls = 0
        self.hgetall_calls = 0
        self.hdel_calls: list[tuple[str, ...]] = []

    async def get(self, key):
        if self.get_error is not None:
            raise self.get_error
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value
        return True

    async def hset(self, key, field, value):
        self.hset_calls += 1
        if self.hset_error is not None:
            raise self.hset_error
        self.hashes.setdefault(key, {})[field] = value
        return 1

    async def hgetall(self, key):
        self.hgetall_calls += 1
        if self.hgetall_error is not None:
            raise self.hgetall_error
        return dict(self.hashes.get(key, {}))

    async def hdel(self, key, *fields):
        self.hdel_calls.append(tuple(fields))
        bucket = self.hashes.get(key, {})
        return sum(1 for f in fields if bucket.pop(f, None) is not None)

    async def expire(self, key, ttl):
        self.expires[key] = ttl
        return True


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()

    async def _get_client():
        return fake

    monkeypatch.setattr(_rc, "get_shared_async_redis", _get_client)
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "1")
    return fake


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    # `clear_shared_builds` also resets the rail's rate limit and its
    # once-per-process reap; without that a flush in one test suppresses the
    # next one's and the whole file passes vacuously.
    pic.clear_shared_builds()
    yield
    pic.clear_shared_builds()


def _rail(fake: _FakeRedis) -> dict[str, dict]:
    return {
        field: json.loads(blob)
        for field, blob in fake.hashes.get(pic.FAILURE_RAIL_KEY, {}).items()
    }


def _seed_field(fake: _FakeRedis, worker: str, snapshot: dict) -> None:
    fake.hashes.setdefault(pic.FAILURE_RAIL_KEY, {})[worker] = json.dumps(snapshot)


def _snapshot(
    *, at: float, hits: int, misses: int, failures: int, reasons: dict
) -> dict:
    return {
        "at": at,
        "started_at": at - 600,
        "pid": 11,
        "dyno": "web.9",
        "cross_worker": {
            "cross_worker_hits": hits,
            "cross_worker_misses": misses,
            "cross_worker_failures": failures,
            "cross_worker_publishes": 0,
            "cross_worker_publish_refused": 0,
            "cross_worker_declined_age": 0,
        },
        "failure_reasons": {NS: dict(reasons)},
        "failure_reasons_total": dict(reasons),
    }


# --------------------------------------------------------------------------
# THE HEADLINE GATE — the asymmetry survives the merge
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_quiet_worker_and_a_busy_one_stay_two_rows(fake_redis):
    """THE gate. The production finding was 4-in-12 on one worker and 0-in-51 on
    another; a fleet reading that reports only the sum says 4 failures in 63
    reads — 6%, which looks like background noise and points at nothing.

    Both rows must survive with their own denominators, or this rail is a
    slower way of getting the number we already had.
    """
    import time as _t

    now = _t.time()
    _seed_field(
        fake_redis,
        "web.1:10",
        _snapshot(
            at=now, hits=8, misses=0, failures=4, reasons={pic.FAIL_READ_TIMEOUT: 4}
        ),
    )
    _seed_field(
        fake_redis,
        "web.2:11",
        _snapshot(at=now, hits=31, misses=20, failures=0, reasons={}),
    )

    fleet = await pic.read_failure_rail(now=now)

    assert fleet["available"] is True
    assert fleet["worker_count"] == 2
    by_worker = {w["worker"]: w for w in fleet["workers"]}
    assert by_worker["web.1:10"]["cross_worker_reads"] == 12
    assert by_worker["web.1:10"]["failure_rate"] == pytest.approx(4 / 12, abs=1e-4)
    assert by_worker["web.2:11"]["cross_worker_reads"] == 51
    assert by_worker["web.2:11"]["failure_rate"] == 0.0
    # Worst first: the operator's eye lands on the worker to fix.
    assert fleet["workers"][0]["worker"] == "web.1:10"
    # And the merged totals still agree with the parts.
    assert fleet["failure_reasons_total"] == {pic.FAIL_READ_TIMEOUT: 4}
    assert fleet["cross_worker_total"]["cross_worker_hits"] == 39
    assert fleet["cross_worker_total"]["cross_worker_failures"] == 4


@pytest.mark.asyncio
async def test_two_workers_on_one_dyno_are_two_fields(fake_redis, monkeypatch):
    """Heroku pids repeat ACROSS dynos, which is why the identity carries `DYNO`.

    If the identity were the pid alone, two workers on different dynos would
    share one field and each flush would overwrite the other's counters — the
    rail would report a fleet smaller than it is and lose exactly the asymmetry
    it exists to show.
    """
    monkeypatch.setenv("DYNO", "web.1")
    first = pic.worker_identity()
    monkeypatch.setenv("DYNO", "web.2")
    second = pic.worker_identity()

    assert first != second
    assert first.startswith("web.1:") and second.startswith("web.2:")


# --------------------------------------------------------------------------
# THE INSTRUMENT MUST NOT APPEAR IN ITS OWN NUMBERS
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_flush_books_nothing_into_the_counters_it_carries(fake_redis):
    """The rail's own Redis failure must never land in `failure_reasons`.

    `publish_timeout` means "the cache could not share an artifact a reader
    wanted". If the instrument's write booked itself there, the rail would
    inflate the very number it reports — and it would do it hardest on the
    workers whose Redis is worst, i.e. on the exact population being measured.
    """
    fake_redis.hset_error = ConnectionError("rail down")

    published = await pic.flush_failure_rail(force=True)

    assert published is False
    stats = pic.shared_build_stats()
    assert stats["failure_reasons"] == {}
    assert stats["cross_worker_failures"] == 0
    assert stats["cross_worker_publishes"] == 0


@pytest.mark.asyncio
async def test_a_hit_never_touches_the_rail(fake_redis):
    """The latency argument, asserted rather than claimed.

    The flush sits behind `not hit` so it can only appear on a request already
    paying a rebuild. A hit must do no rail I/O at all — if this ever fails, the
    instrument has moved onto the fast path the cache exists to protect.
    """
    import time as _t

    envelope = json.dumps(
        {
            # This build's wire, not a literal — the reader declines any other
            # codec version, and a planted envelope it declines is not a hit.
            "v": pic.WIRE_ENVELOPE_VERSION,
            "ns": NS,
            "k": repr(KEY),
            "stored_wall": _t.time(),
            "payload": pic.encode_shared_payload({"ok": 1}),
        }
    )
    fake_redis.store[pic.redis_key_for(NS, KEY)] = pic.wire_encode(envelope)

    hit, value, _age = await pic._read_cross_worker(NS, KEY, 60.0)

    assert hit is True and value == {"ok": 1}
    assert fake_redis.hset_calls == 0, "a hit paid for the instrument"


@pytest.mark.asyncio
async def test_a_non_hit_publishes_this_worker_to_the_rail(fake_redis):
    """The other half: a read that did NOT hit must reach the rail, and must
    carry the failure it just recorded — not an empty heartbeat.
    """
    fake_redis.get_error = ConnectionError("no route")

    hit, _value, _age = await pic._read_cross_worker(NS, KEY, 60.0)

    assert hit is False
    published = _rail(fake_redis)
    assert list(published) == [pic.worker_identity()]
    mine = published[pic.worker_identity()]
    assert mine["failure_reasons_total"] == {pic.FAIL_READ_ERROR: 1}
    assert mine["cross_worker"]["cross_worker_failures"] == 1
    assert fake_redis.expires[pic.FAILURE_RAIL_KEY] == pic.FAILURE_RAIL_TTL_S


@pytest.mark.asyncio
async def test_the_rate_limit_holds_across_repeated_non_hits(fake_redis):
    """One attempt per period per process, however many non-hits arrive.

    Asserted on the CALL COUNT rather than on elapsed time: a wall-clock
    assertion here would be the flake LAT-P084 warns about, and the property
    that matters is "the rail cannot become per-request", which the count says
    exactly.
    """
    fake_redis.get_error = ConnectionError("no route")

    for _ in range(5):
        await pic._read_cross_worker(NS, KEY, 60.0)

    assert fake_redis.hset_calls == 1
    # And all five failures are on the ONE snapshot that got out — the rail
    # carries lifetime counters, so a suppressed flush loses nothing.
    assert _rail(fake_redis)[pic.worker_identity()]["failure_reasons_total"] == {
        pic.FAIL_READ_ERROR: 1
    }
    assert pic.shared_build_stats()["cross_worker_failures"] == 5


@pytest.mark.asyncio
async def test_a_later_snapshot_carries_what_a_lost_flush_would_have(fake_redis):
    """A SNAPSHOT, NEVER A DELTA — stated as a test because the difference is
    invisible until the day Redis is broken.

    A delta rail would drop the failures accrued while it could not write, which
    is precisely the worker population it exists to find. The snapshot's later
    write must contain them all.
    """
    fake_redis.hset_error = ConnectionError("rail down")
    for _ in range(3):
        pic._bump_failure(NS, pic.FAIL_READ_TIMEOUT)
        await pic.flush_failure_rail(force=True)
    assert _rail(fake_redis) == {}

    fake_redis.hset_error = None
    pic._bump_failure(NS, pic.FAIL_READ_TIMEOUT)
    assert await pic.flush_failure_rail(force=True) is True

    mine = _rail(fake_redis)[pic.worker_identity()]
    assert mine["failure_reasons_total"] == {pic.FAIL_READ_TIMEOUT: 4}


# --------------------------------------------------------------------------
# A ZERO MUST NOT BE READABLE AS "CLEAN"
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unreadable_rail_is_not_an_empty_fleet(fake_redis):
    """The failure this whole rail exists to stop, re-entered one level up.

    An unreachable Redis and a genuinely clean fleet both produce zeros. If
    `available` did not separate them, the wider surface would license exactly
    the "reads zero, therefore nothing is failing" inference that made
    `cross_worker_declined_age` unreadable.
    """
    fake_redis.hgetall_error = ConnectionError("rail unreadable")

    fleet = await pic.read_failure_rail()

    assert fleet["available"] is False
    assert fleet["reason"]
    assert fleet["failure_reasons_total"] == {}
    assert fleet["worker_count"] == 0


@pytest.mark.asyncio
async def test_an_empty_rail_is_available_and_empty(fake_redis):
    """The other side of the same line: a read that SUCCEEDED against an empty
    hash is a real answer, and must not be reported as an instrument failure.
    """
    fleet = await pic.read_failure_rail()

    assert fleet["available"] is True
    assert fleet["reason"] is None
    assert fleet["worker_count"] == 0


@pytest.mark.asyncio
async def test_a_disabled_tier_says_so_rather_than_reporting_zeros(
    fake_redis, monkeypatch
):
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "0")

    fleet = await pic.read_failure_rail()

    assert fleet["available"] is False
    assert "disabled" in fleet["reason"]


# --------------------------------------------------------------------------
# THE RAIL REAPS ITS OWN DEAD, AND NEVER SUMS THEM
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_rail_reads_a_bytes_returning_client(fake_redis, monkeypatch):
    """PRODUCTION RETURNS BYTES AND THIS FAKE DOES NOT.

    `get_async_redis_client()` sets no `decode_responses`, so redis-py hands
    back `bytes` for both the field NAME and the field VALUE — while every other
    test in this file feeds `str`, because that is what a dict-backed fake
    naturally holds. A rail that parsed only `str` would pass this whole file
    and then report an empty fleet on every real dyno: `available: true`,
    `worker_count: 0`, indistinguishable from a healthy quiet fleet, which is
    the exact reading this rail exists to make impossible.

    So one test drives the bytes shape end to end, through both the reader and
    the reaper — the reaper decodes field NAMES to decide what to delete, and an
    undecoded name is an `HDEL` of the wrong thing.
    """
    import time as _t

    now = _t.time()
    mine = pic.worker_identity()
    fresh = json.dumps(
        _snapshot(
            at=now, hits=9, misses=3, failures=2, reasons={pic.FAIL_READ_TIMEOUT: 2}
        )
    ).encode("utf-8")
    dead = json.dumps(
        _snapshot(
            at=now - pic.FAILURE_RAIL_STALE_S - 1,
            hits=1,
            misses=1,
            failures=50,
            reasons={pic.FAIL_READ_ERROR: 50},
        )
    ).encode("utf-8")
    fake_redis.hashes[pic.FAILURE_RAIL_KEY] = {
        b"web.3:41": fresh,
        b"web.3:42": dead,
        mine.encode("utf-8"): fresh,
    }

    fleet = await pic.read_failure_rail(now=now)

    assert fleet["available"] is True
    assert fleet["worker_count"] == 3, "a bytes field name was not decoded"
    assert fleet["fresh_worker_count"] == 2
    assert fleet["stale_worker_count"] == 1
    assert fleet["failure_reasons_total"] == {pic.FAIL_READ_TIMEOUT: 4}
    assert {w["worker"] for w in fleet["workers"]} == {"web.3:41", "web.3:42", mine}

    # ...and the reap must drop exactly the dead field, naming it as decoded
    # text, even though it arrived as bytes. An undecoded name here is an HDEL
    # of a field that does not exist while the real dead one accumulates.
    await pic.flush_failure_rail(force=True)
    assert fake_redis.hdel_calls == [("web.3:42",)]
    assert mine in _rail(fake_redis), "this process's own fresh field was lost"


@pytest.mark.asyncio
async def test_a_generation_a_release_replaced_is_printed_but_never_summed(fake_redis):
    """THE DEPLOY GATE, and it was written from a measurement, not a worry.

    Sampling production 05:37-05:42Z on 2026-09-18, release v4713 landed
    mid-run:

        05:40:33  pid 11  hits 34  misses 14  publishes 14
        05:41:10  pid 11  hits  0  misses  0  publishes  0

    Same pid, two process generations, 37 s apart — and v4712 had landed 37
    MINUTES earlier. So dead generations are common, recent and frequent here.
    If the replacement comes up under a different pid, the dead field is a
    separate row holding LIFETIME counters that can never fall, and summing it
    inflates the fleet for the whole window — worst in the minutes after a
    deploy, which is when someone is looking.

    Both halves are asserted, because each alone is a different bug: excluded
    from the TOTALS (or every deploy reads as a regression), and still PRESENT
    in `workers` (or a rail built so a zero cannot read as "clean" acquires an
    invisible row).
    """
    import time as _t

    now = _t.time()
    _seed_field(
        fake_redis,
        "web.1:10",
        _snapshot(
            at=now - pic.FAILURE_RAIL_FRESH_S - 1,
            hits=1,
            misses=1,
            failures=99,
            reasons={pic.FAIL_READ_ERROR: 99},
        ),
    )
    _seed_field(
        fake_redis,
        "web.1:12",
        _snapshot(
            at=now, hits=10, misses=2, failures=1, reasons={pic.FAIL_READ_ERROR: 1}
        ),
    )

    fleet = await pic.read_failure_rail(now=now)

    assert fleet["failure_reasons_total"] == {pic.FAIL_READ_ERROR: 1}
    assert fleet["cross_worker_total"]["cross_worker_failures"] == 1
    assert fleet["fresh_worker_count"] == 1
    assert fleet["stale_worker_count"] == 1
    # ...and the dead generation is still on the page, flagged, sorted last.
    assert fleet["worker_count"] == 2
    rows = {w["worker"]: w for w in fleet["workers"]}
    assert rows["web.1:10"]["stale"] is True
    assert rows["web.1:12"]["stale"] is False
    assert (
        fleet["workers"][-1]["worker"] == "web.1:10"
    ), "a dead row sorted above a live one"


@pytest.mark.asyncio
async def test_the_reaper_waits_far_longer_than_the_arithmetic_does(fake_redis):
    """The two windows are not the same number and must not collapse into one.

    Reaping is destructive — once the field is gone its counters exist nowhere —
    so the reaper waits for `FAILURE_RAIL_STALE_S`, an order of magnitude past
    the `FAILURE_RAIL_FRESH_S` at which a row merely stops being added up. A
    field between the two is exactly the interesting case: not trusted, not
    deleted, still readable.
    """
    import time as _t

    assert pic.FAILURE_RAIL_STALE_S > pic.FAILURE_RAIL_FRESH_S * 5

    now = _t.time()
    between = (pic.FAILURE_RAIL_FRESH_S + pic.FAILURE_RAIL_STALE_S) / 2
    _seed_field(
        fake_redis,
        "web.5:31",
        _snapshot(
            at=now - between,
            hits=4,
            misses=1,
            failures=7,
            reasons={pic.FAIL_BAD_JSON: 7},
        ),
    )

    fleet = await pic.read_failure_rail(now=now)
    assert fleet["failure_reasons_total"] == {}, "an untrusted row was summed"
    assert [w["worker"] for w in fleet["workers"]] == ["web.5:31"]

    await pic.flush_failure_rail(force=True)
    assert fake_redis.hdel_calls == [], "a row that is merely untrusted was deleted"
    assert "web.5:31" in _rail(fake_redis)


@pytest.mark.asyncio
async def test_the_first_flush_of_a_process_reaps_stale_fields_once(fake_redis):
    """Bounded growth. A new field appears exactly when a process starts, so the
    reap belongs there — and must NOT repeat, or every flush for the life of the
    dyno pays an extra HGETALL.
    """
    import time as _t

    now = _t.time()
    _seed_field(
        fake_redis,
        "web.9:99",
        _snapshot(
            at=now - pic.FAILURE_RAIL_STALE_S - 1,
            hits=0,
            misses=0,
            failures=0,
            reasons={},
        ),
    )
    live = _snapshot(at=now, hits=5, misses=1, failures=0, reasons={})
    _seed_field(fake_redis, "web.9:98", live)

    await pic.flush_failure_rail(force=True)

    assert fake_redis.hdel_calls == [("web.9:99",)]
    assert "web.9:99" not in _rail(fake_redis)
    assert "web.9:98" in _rail(fake_redis), "a LIVE sibling was reaped"

    await pic.flush_failure_rail(force=True)
    assert len(fake_redis.hdel_calls) == 1, "the reap repeated"
    assert fake_redis.hgetall_calls == 1


@pytest.mark.asyncio
async def test_an_unparseable_field_is_skipped_not_fatal(fake_redis):
    """One corrupt field must not take the whole fleet reading down with it —
    the reading is needed most when something is wrong.

    And it is counted on its OWN line, not folded into `stale`: a field nothing
    can decode is a writer defect, while a stale one is an ordinary restart.
    Reporting a bug as an expected event is how it stays unfixed.
    """
    import time as _t

    now = _t.time()
    fake_redis.hashes.setdefault(pic.FAILURE_RAIL_KEY, {})["web.1:7"] = "not json"
    _seed_field(
        fake_redis,
        "web.1:8",
        _snapshot(at=now, hits=3, misses=1, failures=2, reasons={pic.FAIL_BAD_JSON: 2}),
    )

    fleet = await pic.read_failure_rail(now=now)

    assert fleet["available"] is True
    assert fleet["worker_count"] == 1
    assert fleet["fresh_worker_count"] == 1
    assert fleet["stale_worker_count"] == 0
    assert fleet["unparseable_field_count"] == 1
    assert fleet["failure_reasons_total"] == {pic.FAIL_BAD_JSON: 2}


# --------------------------------------------------------------------------
# THE ENDPOINT
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_admin_endpoint_serves_the_fleet_beside_the_process(
    fake_redis, monkeypatch
):
    """Both halves in one read, and the per-process half unchanged.

    `stats` is still the answer for THIS worker — every reader of it predates
    this change — and `fleet` is the one that can be reasoned about across
    dynos.
    """
    import time as _t

    from app.routes import admin as admin_routes

    monkeypatch.setattr(admin_routes, "_check_admin_secret", lambda *a, **k: None)
    now = _t.time()
    _seed_field(
        fake_redis,
        "web.4:21",
        _snapshot(
            at=now, hits=2, misses=1, failures=3, reasons={pic.FAIL_READ_TIMEOUT: 3}
        ),
    )
    pic._bump_failure(NS, pic.FAIL_READ_ERROR)

    body = await admin_routes.get_shared_build_stats(request=None, secret="x")

    assert body["failure_reasons_total"] == {pic.FAIL_READ_ERROR: 1}
    assert body["worker_identity"] == pic.worker_identity()
    assert body["fleet"]["available"] is True
    assert body["fleet"]["failure_reasons_total"] == {pic.FAIL_READ_TIMEOUT: 3}
    assert body["fleet"]["workers"][0]["worker"] == "web.4:21"
    assert pic.FAIL_READ_TIMEOUT in body["known_failure_reasons"]
