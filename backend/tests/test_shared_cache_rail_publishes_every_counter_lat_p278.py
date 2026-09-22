"""GATE for LAT-P278 (#2143) — every counter this module keeps reaches the rail.

## The ship

`/api/admin/shared-build-stats`' fleet rail exists so an operator can read a
per-worker counter that an in-memory dict cannot expose. LAT-P277 added
`declined_age` — the L1-tier half of the age decline, the tier that is read
FIRST and therefore the one that fires on a warm worker — and it was unreadable
fleet-wide from the minute it shipped.

## Why it was unreadable, and why that is a class

`failure_rail_snapshot()` selected what to publish with
`k.startswith("cross_worker_")`. The new counter does not carry that prefix, so
it was dropped from every worker's field, from `workers[]` and from
`cross_worker_total`. Nothing raised; the counter was PRESENT in the code and
absent from the instrument, which is the precise failure the module's own
comment cites for `cross_worker_declined_age` one release earlier.

A naming-convention filter fails closed on the counter it has never seen, and
that is always the newly added one. So the assertion here is deliberately NOT
"`declined_age` is published" — that would pass forever while the next counter
repeats the whole incident. It is that the published halves are a PARTITION of
`_stats`: every counter lands in exactly one of them.

## What these tests do NOT assert

Not a value, not an ordering, and not that any particular counter exists — a
test that names today's keys would have to be edited by the very change it is
meant to catch, and an edited guard is not a guard.
"""

from __future__ import annotations

import json

import pytest

from app.utils import principal_independent_cache as pic
from app.utils import request_cache as _rc


class _FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}

    async def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value
        return 1

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def hdel(self, key, *fields):
        bucket = self.hashes.get(key, {})
        return sum(1 for f in fields if bucket.pop(f, None) is not None)

    async def expire(self, key, ttl):
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
def _clean():
    pic.clear_shared_builds()
    yield
    pic.clear_shared_builds()


def test_snapshot_publishes_every_counter_in_stats_exactly_once():
    """The guard. Driven off `_stats` itself, so a new counter is covered the
    moment it is declared — the author does not have to remember this file."""
    snap = pic.failure_rail_snapshot()
    published = dict(snap["cross_worker"])
    published.update(snap["local"])

    missing = sorted(set(pic._stats) - set(published))
    assert not missing, (
        f"{missing} are counted in `_stats` and published nowhere on the rail, "
        "so their VALUE can never be read fleet-wide. Put each in "
        "`cross_worker` or `local` in `failure_rail_snapshot()`."
    )

    overlap = sorted(set(snap["cross_worker"]) & set(snap["local"]))
    assert not overlap, (
        f"{overlap} appear in both halves; a counter summed twice is worse than "
        "one summed never, because it reads as a real number."
    )
    assert set(published) == set(pic._stats)


def test_cross_worker_half_keeps_its_exact_membership():
    """The complement rides BESIDE `cross_worker`, never inside it. The reader
    and its tests are keyed on that dict, and a `builds` count filed under a
    name that says `cross_worker` is a second, quieter lie."""
    snap = pic.failure_rail_snapshot()
    assert set(snap["cross_worker"]) == {
        k for k in pic._stats if k.startswith("cross_worker_")
    }
    assert all(not k.startswith("cross_worker_") for k in snap["local"])


@pytest.mark.asyncio
async def test_local_counters_are_summed_across_fresh_workers(fake_redis):
    """Publishing is half the job: the fleet read has to add them up too."""
    now = 1_000_000.0
    for worker, value in (("web.1:10", 3), ("web.2:11", 4)):
        fake_redis.hashes.setdefault(pic.FAILURE_RAIL_KEY, {})[worker] = json.dumps(
            {
                "at": now,
                "started_at": now - 60,
                "pid": 10,
                "dyno": worker.split(":")[0],
                "cross_worker": {"cross_worker_hits": 1},
                "local": {"declined_age": value},
                "failure_reasons": {},
                "failure_reasons_total": {},
            }
        )

    fleet = await pic.read_failure_rail(now=now)

    assert fleet["available"] is True
    assert fleet["local_total"]["declined_age"] == 7
    assert {w["local"]["declined_age"] for w in fleet["workers"]} == {3, 4}


@pytest.mark.asyncio
async def test_a_generation_the_release_replaced_is_printed_but_never_summed(
    fake_redis,
):
    """Same treatment the cross-worker half already gets. Without this, every
    deploy would read as a regression in the new counters that never heals."""
    now = 1_000_000.0
    bucket = fake_redis.hashes.setdefault(pic.FAILURE_RAIL_KEY, {})
    bucket["web.1:10"] = json.dumps(
        {
            "at": now,
            "started_at": now - 60,
            "pid": 10,
            "dyno": "web.1",
            "cross_worker": {},
            "local": {"declined_age": 5},
            "failure_reasons": {},
            "failure_reasons_total": {},
        }
    )
    bucket["web.1:9"] = json.dumps(
        {
            "at": now - pic.FAILURE_RAIL_FRESH_S - 1,
            "started_at": now - 9_999,
            "pid": 9,
            "dyno": "web.1",
            "cross_worker": {},
            "local": {"declined_age": 900},
            "failure_reasons": {},
            "failure_reasons_total": {},
        }
    )

    fleet = await pic.read_failure_rail(now=now)

    assert fleet["local_total"]["declined_age"] == 5
    stale = [w for w in fleet["workers"] if w["stale"]]
    assert len(stale) == 1 and stale[0]["local"]["declined_age"] == 900


@pytest.mark.asyncio
async def test_a_field_written_before_this_change_still_reads(fake_redis):
    """Forward compatibility in the direction it actually happens: during the
    release, fields written by the OLD slug carry no `local` key. That must
    contribute nothing, not make the whole read unparseable."""
    now = 1_000_000.0
    fake_redis.hashes.setdefault(pic.FAILURE_RAIL_KEY, {})["web.1:10"] = json.dumps(
        {
            "at": now,
            "started_at": now - 60,
            "pid": 10,
            "dyno": "web.1",
            "cross_worker": {"cross_worker_hits": 2},
            "failure_reasons": {},
            "failure_reasons_total": {},
        }
    )

    fleet = await pic.read_failure_rail(now=now)

    assert fleet["available"] is True
    assert fleet["unparseable_field_count"] == 0
    assert fleet["local_total"] == {}
    assert fleet["workers"][0]["local"] == {}
    assert fleet["cross_worker_total"]["cross_worker_hits"] == 2
