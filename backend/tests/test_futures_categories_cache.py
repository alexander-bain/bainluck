"""Guard tests for LAT-P122: the Search tab's category grid stops costing a
~305 MB table scan for every visitor, on every load.

WHAT WAS MEASURED, and it is why every assertion below is about SHAPE, TTL or
CALL COUNT and none is about wall clock.

`/search` renders `CategoryBrowser`, whose first act on mount is
`fetchFuturesCategories()`. Until that answers, the grid — the content of the
page — is not there. Production slug `a68b2a1b`, 2026-08-29, two consecutive
reads ten seconds apart:

    /api/futures/categories   wall=1585.9; db=1577.6; app=8.3; q=1
    /api/futures/categories   wall=1365.1; db=1357.2; app=7.9; q=1

The SECOND read is as slow as the first, because this tier had no cache of any
kind — not a small one, not a per-process one: none. `EXPLAIN (ANALYZE, BUFFERS)`
on the emitted statement reads **39,014 shared blocks** and sorts 21,439 rows to
group into 42, because the two negated `ILIKE`s are unindexable.

So the defect under test is not the query. It is that every visitor ran it. The
tests that matter here are therefore: a second reader does not run it (call
count), the mirror is a SERVE path and not an error handler (state), and the
mirror cannot print a count nobody can reproduce (the age ceiling).
"""

import asyncio
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.routes import futures as futures_route
from app.utils import event_concept_cache as concept_cache
from app.utils import futures_categories_cache as fcc


class _FakeRedis:
    """In-memory Redis: get / setex / set / delete / eval over a dict.

    TTLs are RECORDED rather than enforced — a test that needed a key to expire
    would have to sleep, and a gate that sleeps is a gate that flakes. Expiry is
    simulated by deleting the key, which is what expiry does.
    """

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.store.get(k)

    def setex(self, k, ttl, v):
        self.ttls[k] = ttl
        self.store[k] = v.encode() if isinstance(v, str) else v

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else v
        if ex is not None:
            self.ttls[k] = ex
        return True

    def delete(self, k):
        self.ttls.pop(k, None)
        return int(self.store.pop(k, None) is not None)

    def eval(self, _script, _numkeys, key, arg):
        """The release-if-owner compare-and-delete, faithfully."""
        held = self.store.get(key)
        if held is not None and held.decode() == arg:
            del self.store[key]
            self.ttls.pop(key, None)
            return 1
        return 0


def _census(total: int = 21439) -> dict:
    return {
        "categories": [
            {"key": "politics", "count": 6614},
            {"key": "economics", "count": 2902},
            {"key": "other", "count": 123},
        ],
        "total": total,
    }


def _stamped(*, age_s: float = 0.0, total: int = 21439) -> dict:
    created = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return fcc.stamp(_census(total), created_at=created)


@contextmanager
def _client(rc):
    """Make `rc` the tier's default client.

    BOTH names are patched, and that is not belt-and-braces. `futures_categories_
    cache` does `from ... import get_client`, so it holds its OWN reference:
    patching only `event_concept_cache.get_client` leaves the tier reading the
    real Redis while the test believes it is isolated — which is how a suite
    passes locally, fails in CI, and gets called flaky.
    """
    with patch.object(fcc, "get_client", return_value=rc), patch.object(
        concept_cache, "get_client", return_value=rc
    ):
        yield rc


def _no_client():
    return _client(None)


class _Row:
    def __init__(self, key, count):
        self.llm_sport_category = key
        self.count = count


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _CountingSession:
    """An `AsyncSession` stand-in that counts how many statements it ran.

    The whole ship is "how many people run the 39,014-block statement", so the
    instrument is a counter, not a clock.
    """

    def __init__(self, rows=None):
        self.executions = 0
        self._rows = rows if rows is not None else [
            _Row("politics", 6614),
            _Row("economics", 2902),
            _Row(None, 123),
        ]

    async def execute(self, _query):
        self.executions += 1
        return _Result(self._rows)


# ---------------------------------------------------------------------------
# The tier's own constants — asserted against what they claim to be
# ---------------------------------------------------------------------------


def test_the_ceiling_is_the_same_number_the_other_two_tiers_use():
    """Two serve-stale ceilings that disagree are a coin flip about which one a
    reader gets. `game_markets_cache` and `routes/events.py` both use 5x."""
    from app.utils import game_markets_cache as gmc

    assert fcc.STALE_SERVE_CEILING == gmc.STALE_SERVE_CEILING


def test_the_mirror_ttl_is_the_shared_one_not_a_second_copy():
    """`write_payload` does not parameterize the stale TTL, so a literal here
    would be a constant the writer never reads.

    Identity against the tier's OWN import alias, not against
    `concept_cache.STALE_TTL`: the mutation harness re-execs that module from
    source, which mints a fresh `int` object and would fail an `is` for a reason
    that has nothing to do with the property. `_SHARED_STALE_TTL` is the name the
    module imported it under, so this is the same claim with no such hole.
    """
    assert fcc.STALE_TTL is fcc._SHARED_STALE_TTL
    assert fcc.STALE_TTL == concept_cache.STALE_TTL


def test_the_ceiling_binds_well_inside_the_ingest_cadence():
    """25 minutes, against counts that move on a 1-2h ingest.

    Asserted as a derivation rather than a literal: if someone raises FRESH_TTL
    the ceiling must move with it, which is the property, not the number.
    """
    assert fcc.stale_serve_ceiling_seconds() == fcc.STALE_SERVE_CEILING * fcc.FRESH_TTL
    assert fcc.stale_serve_ceiling_seconds() < 3600


def test_the_tier_owns_exactly_one_entry_and_all_four_slots_share_its_base():
    """The census takes no arguments, so a second key would be a second answer to
    a question with one answer. All four slots must hang off one base."""
    slots = fcc.keys()
    assert slots.primary == f"{fcc.CACHE_PREFIX}{fcc.CACHE_KEY}"
    for other in (slots.stale, slots.negative, slots.refresh_lock):
        assert other.startswith(slots.primary)
        assert other != slots.primary


def test_the_prefix_does_not_collide_with_the_tiers_that_share_the_module():
    from app.utils import game_markets_cache as gmc

    prefixes = {fcc.CACHE_PREFIX, gmc.CACHE_PREFIX, concept_cache.CACHE_PREFIX}
    assert len(prefixes) == 3


def test_a_SECOND_PROCESS_computes_the_same_key():
    """THE SHIP'S LOAD-BEARING PROPERTY, and the one an equality assertion inside
    a single process cannot see.

    A key derived from anything process-local — `id(...)`, a pid, a uuid minted
    at import, a hostname — is stable within one worker and therefore passes
    every same-process check, while making the "shared" slot shared with nobody:
    every write succeeds, every metric is healthy, and the second visitor on the
    other Uvicorn worker still pays the 39,014-block scan.

    So the module is RE-EXEC'd into a fresh namespace, which is what a second
    process does, and the two keys must agree.
    """
    import importlib.util
    from pathlib import Path

    source = Path(fcc.__file__).read_text()
    spec = importlib.util.spec_from_loader("_fcc_second_process", loader=None)
    other = importlib.util.module_from_spec(spec)
    other.__file__ = fcc.__file__
    exec(compile(source, fcc.__file__, "exec"), other.__dict__)

    assert other.CACHE_KEY == fcc.CACHE_KEY
    assert other.CACHE_PREFIX == fcc.CACHE_PREFIX
    assert other.keys().primary == fcc.keys().primary


# ---------------------------------------------------------------------------
# The serve ladder
# ---------------------------------------------------------------------------


def test_a_primary_hit_serves_live():
    rc = _FakeRedis()
    fcc.write(_stamped(), rc=rc)
    body, state = fcc.read(rc=rc)
    assert state == "live"
    assert body["cache"]["availability"] == fcc.AVAILABILITY_LIVE
    assert body["total"] == 21439


def test_a_primary_miss_serves_the_mirror_rather_than_nothing():
    """The defect class this ship closes: a mirror consulted only when the build
    FAILS does nothing at all for a build that was simply not cached."""
    rc = _FakeRedis()
    fcc.write(_stamped(age_s=fcc.FRESH_TTL + 5), rc=rc)
    rc.delete(fcc.keys().primary)  # the primary TTL expired; the mirror did not

    body, state = fcc.read(rc=rc)
    assert state == "stale_ok"
    assert body["cache"]["availability"] == fcc.AVAILABILITY_STALE_OK
    assert body["total"] == 21439


def test_a_mirror_past_the_ceiling_is_REFUSED_so_the_grid_cannot_print_a_lie():
    """These counts are printed to the user — "6,614" beside Politics, "21,439
    markets" at the top. A day-old mirror would print a number nobody can
    reproduce by tapping the tile. Past the ceiling the reader rebuilds."""
    rc = _FakeRedis()
    fcc.write(_stamped(age_s=fcc.stale_serve_ceiling_seconds() + 1), rc=rc)
    rc.delete(fcc.keys().primary)

    body, state = fcc.read(rc=rc)
    assert state == "stale_too_old"
    assert body is None


def test_a_mirror_exactly_at_the_ceiling_is_still_served():
    """The bound is `>`, not `>=`. Asserted so a later edit cannot silently make
    the ceiling one second tighter and call it the same rule.

    `now` is passed EXPLICITLY. Reading the wall clock inside the assertion puts
    a few microseconds between the stamp and the comparison, which is enough to
    push an exactly-at-the-ceiling payload over it — a gate that fails on how
    fast the machine is, which is gotcha #44's shape.
    """
    now = datetime.now(timezone.utc)
    created = now - timedelta(seconds=fcc.stale_serve_ceiling_seconds())
    payload = fcc.stamp(_census(), created_at=created)

    servable, reason = fcc.mirror_is_servable(payload, now=now)
    assert servable is True
    assert reason == "fresh_enough"

    one_second_older = fcc.stamp(_census(), created_at=created - timedelta(seconds=1))
    assert fcc.mirror_is_servable(one_second_older, now=now) == (False, "too_old")


def test_a_payload_that_cannot_say_when_it_was_computed_is_refused():
    """It would be served under an age bound we are unable to evaluate."""
    payload = _stamped()
    payload["cache"]["created_at"] = None
    servable, reason = fcc.mirror_is_servable(payload)
    assert servable is False
    assert reason == "no_created_at"


def test_an_absent_payload_is_refused_and_says_so_distinctly():
    """`absent`, `no_created_at` and `too_old` are different facts about the tier
    and a bool would collapse them."""
    assert fcc.mirror_is_servable(None) == (False, "absent")


def test_no_redis_client_reads_as_a_miss_and_never_raises():
    """A cache that cannot be read must cost a rebuild, not a 500."""
    with _no_client():
        assert fcc.read() == (None, "miss")


def test_a_read_failure_reads_as_a_miss_rather_than_propagating():
    class _Exploding(_FakeRedis):
        def get(self, k):
            raise RuntimeError("redis is down")

    assert fcc.read(rc=_Exploding())[1] == "miss"


def test_a_write_failure_is_swallowed_and_reported_as_ATTEMPTED_only():
    """`write` reports "there was a client and we handed it the bytes", never
    durability — the next read is the only thing that can establish that."""

    class _Exploding(_FakeRedis):
        def setex(self, k, ttl, v):
            raise RuntimeError("redis is down")

    assert fcc.write(_stamped(), rc=_Exploding()) is True
    with _no_client():
        assert fcc.write(_stamped()) is False


# ---------------------------------------------------------------------------
# The envelope
# ---------------------------------------------------------------------------


def test_the_stored_payload_carries_all_five_contract_fields():
    stamped = fcc.stamp(_census())
    assert concept_cache.envelope_defect(stamped) is None
    for field in concept_cache.ENVELOPE_FIELDS:
        assert field in stamped["cache"]


def test_availability_is_the_SERVE_decision_and_is_not_baked_into_the_bytes():
    """The same stored bytes are `live` from the primary and `stale_ok` from the
    mirror, so stamping it on the way in would make one of the two wrong."""
    stamped = fcc.stamp(_census())
    assert stamped["cache"]["availability"] is None

    rc = _FakeRedis()
    fcc.write(stamped, rc=rc)
    live, _ = fcc.read(rc=rc)
    rc.delete(fcc.keys().primary)
    stale, _ = fcc.read(rc=rc)

    assert live["cache"]["availability"] == fcc.AVAILABILITY_LIVE
    assert stale["cache"]["availability"] == fcc.AVAILABILITY_STALE_OK
    # ...and the CONTENT is byte-identical: only the serve decision moved.
    assert live["categories"] == stale["categories"]
    assert live["cache"]["created_at"] == stale["cache"]["created_at"]


def test_the_watermark_is_published_as_null_rather_than_omitted():
    """The contract's own answer for a watermark that cannot be computed. The
    only honest one here is a second pass over the blocks this ship stops
    reading, which is not a trade worth making — but the FIELD must still be
    present, or a consumer cannot tell "unknown" from "nobody stamped it"."""
    stamped = fcc.stamp(_census())
    assert "lifecycle_watermark" in stamped["cache"]
    assert stamped["cache"]["lifecycle_watermark"] is None


def test_the_primary_ttl_written_is_this_tier_s_fresh_ttl():
    rc = _FakeRedis()
    fcc.write(_stamped(), rc=rc)
    assert rc.ttls[fcc.keys().primary] == fcc.FRESH_TTL
    assert rc.ttls[fcc.keys().stale] == fcc.STALE_TTL


def test_the_codec_is_lossless_for_this_tier_s_payload():
    """LAT-P121b found `json.dumps(..., default=str)` silently reshaping a
    datetime. This tier stores ints, strings and one ISO string, so the codec is
    lossless FOR IT — asserted rather than assumed, because "we don't have any
    datetimes" is exactly the kind of claim that stops being true."""
    stamped = fcc.stamp(_census())
    encoded = concept_cache.encode_payload(stamped)
    assert json.loads(encoded) == stamped


# ---------------------------------------------------------------------------
# The route: the thing the ship is actually about — CALL COUNT
# ---------------------------------------------------------------------------


def _run(coro):
    """Run `coro` on a fresh loop and CLOSE it, so a leaked pending task from one
    test cannot be scheduled inside another's loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _drain_refreshes():
    """Wait for every refresh this test scheduled to finish.

    `await asyncio.sleep(0)` a fixed number of times is a bet on how many
    scheduler turns the rebuild needs, and it is a bet that changes when the
    module under test is re-exec'd by the mutation harness. Awaiting the tasks
    themselves is the same assertion with no bet in it.
    """
    tasks = list(concept_cache._REFRESH_TASKS)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def test_the_second_visitor_does_not_run_the_39014_block_statement():
    """THE SHIP, stated as a test. Two readers, one build."""
    rc = _FakeRedis()
    session = _CountingSession()

    async def _two_readers():
        with _client(rc):
            first = await futures_route.list_futures_categories(db=session)
            second = await futures_route.list_futures_categories(db=session)
        return first, second

    first, second = _run(_two_readers())

    assert session.executions == 1, "the second reader rebuilt the census"
    assert first["categories"] == second["categories"]
    assert second["cache"]["availability"] == fcc.AVAILABILITY_LIVE


def test_a_cold_reader_builds_and_publishes_what_the_next_one_will_read():
    """A build and a hit must be the same bytes plus one `availability`, or the
    first visitor and the second are looking at different pages."""
    rc = _FakeRedis()
    session = _CountingSession()

    async def _build_then_read():
        with _client(rc):
            built = await futures_route.list_futures_categories(db=session)
        return built

    built = _run(_build_then_read())
    stored, state = fcc.read(rc=rc)

    assert state == "live"
    assert stored == built
    assert built["total"] == 6614 + 2902 + 123


def test_a_null_category_renders_as_other_exactly_as_it_did_before():
    """The response shape is unchanged by this ship. `row.llm_sport_category or
    "other"` is the pre-existing rule and it is carried across verbatim."""
    rc = _FakeRedis()
    session = _CountingSession(rows=[_Row(None, 123)])

    async def _go():
        with _client(rc):
            return await futures_route.list_futures_categories(db=session)

    body = _run(_go())
    assert body["categories"] == [{"key": "other", "count": 123}]


def test_no_redis_at_all_still_answers_and_still_builds_every_time():
    """Degrade to today's behaviour, never to a 500. This is the property that
    makes the ship safe to deploy before anyone checks Redis."""
    session = _CountingSession()

    async def _go():
        with _no_client():
            a = await futures_route.list_futures_categories(db=session)
            b = await futures_route.list_futures_categories(db=session)
        return a, b

    a, b = _run(_go())
    assert session.executions == 2
    assert a["categories"] == b["categories"]


# ---------------------------------------------------------------------------
# Serve-stale: ONE rebuild behind the mirror, fleet-wide
# ---------------------------------------------------------------------------


def test_a_stale_serve_starts_exactly_one_rebuild_for_many_readers():
    """The stampede this closes. The route copy in `routes/events.py` guards with
    a process-global set, which admits one rebuild per Uvicorn worker per dyno —
    `WEB_CONCURRENCY=2` makes that 2N for one expiry. The lock is in Redis, so
    N readers across the fleet produce ONE build."""
    rc = _FakeRedis()
    calls = []

    async def _rebuild():
        calls.append(1)

    async def _five_readers():
        served = [
            concept_cache.serve_stale_and_refresh(fcc.keys(), _rebuild, rc=rc)
            for _ in range(5)
        ]
        await _drain_refreshes()
        return served

    served = _run(_five_readers())

    assert all(served), "every reader must still be told it may serve the mirror"
    assert len(calls) == 1, f"expected one rebuild, got {len(calls)}"


def test_the_rebuild_is_STRONGLY_referenced_until_it_finishes():
    """`asyncio` keeps only a WEAK reference to a bare `create_task` result, so a
    rebuild with no other referent can be collected mid-flight. The mirror is
    then never replaced and serve-stale silently becomes serve-stale-forever —
    until the age ceiling starts making every reader rebuild synchronously again,
    which reads as the ship having simply not worked.

    Asserted while the task is still PENDING, because that is the only window in
    which the reference has to exist. A test that only checks the outcome passes
    whenever the collector happens not to run.
    """
    rc = _FakeRedis()
    released = asyncio.Event()
    finished = []

    async def _rebuild():
        await released.wait()
        finished.append(1)

    async def _go():
        assert concept_cache.serve_stale_and_refresh(fcc.keys(), _rebuild, rc=rc)
        # PENDING: the strong ref must be held now, not after the fact.
        assert len(concept_cache._REFRESH_TASKS) == 1, (
            "the rebuild is not strongly referenced while it is in flight"
        )
        released.set()
        await _drain_refreshes()
        # ...and the done-callback must give it back, or the set is a leak.
        assert concept_cache._REFRESH_TASKS == set()

    _run(_go())
    assert finished == [1]


def test_the_lock_is_released_by_owner_token_after_the_rebuild():
    """#1678 finding 1: an unconditional delete in a `finally` let a non-holder
    release somebody else's lock and admitted a third concurrent builder."""
    rc = _FakeRedis()

    async def _rebuild():
        return None

    async def _go():
        concept_cache.serve_stale_and_refresh(fcc.keys(), _rebuild, rc=rc)
        await _drain_refreshes()

    _run(_go())
    assert fcc.keys().refresh_lock not in rc.store


def test_a_failing_rebuild_releases_the_lock_and_leaves_the_mirror_alone():
    """A failed rebuild must not poison the cache, and must not park the lock for
    REFRESH_LOCK_TTL — otherwise one bad build costs two minutes of no refresh."""
    rc = _FakeRedis()
    fcc.write(_stamped(), rc=rc)
    before = rc.store[fcc.keys().stale]

    async def _rebuild():
        raise RuntimeError("the build failed")

    async def _go():
        concept_cache.serve_stale_and_refresh(fcc.keys(), _rebuild, rc=rc)
        await _drain_refreshes()

    _run(_go())
    assert fcc.keys().refresh_lock not in rc.store
    assert rc.store[fcc.keys().stale] == before


def test_no_running_loop_refuses_AND_gives_the_lock_back():
    """No loop means nothing can run behind the caller, so serving stale would
    mean serving it forever. Refusing is right — parking the lock on a rebuild
    that was never started is not."""
    rc = _FakeRedis()

    async def _rebuild():
        return None

    assert (
        concept_cache.serve_stale_and_refresh(fcc.keys(), _rebuild, rc=rc) is False
    )
    assert fcc.keys().refresh_lock not in rc.store


def test_no_redis_client_refuses_the_stale_serve_rather_than_serving_forever():
    """With no client there is no lock, so there is no single-flight and no way
    to know a rebuild is coming. Build synchronously."""

    async def _rebuild():
        return None

    async def _go():
        return concept_cache.serve_stale_and_refresh(fcc.keys(), _rebuild, rc=None)

    with _no_client():
        assert _run(_go()) is False


def test_a_reader_that_loses_the_lock_race_still_serves_the_mirror():
    """Somebody else is already rebuilding. The mirror is still the right answer
    and the lock's own TTL bounds the wait — the loser must not block."""
    rc = _FakeRedis()
    rc.set(fcc.keys().refresh_lock, "somebody-else", nx=True, ex=120)

    async def _rebuild():
        raise AssertionError("the loser must not rebuild")

    async def _go():
        return concept_cache.serve_stale_and_refresh(fcc.keys(), _rebuild, rc=rc)

    assert _run(_go()) is True


def test_the_route_serves_the_mirror_without_running_the_statement():
    """End to end: primary gone, mirror present, and the request does NOT pay the
    39,014 blocks. The rebuild that runs behind it is a separate session, which
    is why this session's counter must stay at zero."""
    rc = _FakeRedis()
    fcc.write(_stamped(age_s=fcc.FRESH_TTL + 5), rc=rc)
    rc.delete(fcc.keys().primary)
    session = _CountingSession()

    async def _go():
        with _client(rc), patch.object(
            futures_route, "_rebuild_futures_categories", _noop_rebuild
        ):
            body = await futures_route.list_futures_categories(db=session)
            await _drain_refreshes()
        return body

    body = _run(_go())

    assert session.executions == 0, "the request paid for a build it should not have"
    assert body["cache"]["availability"] == fcc.AVAILABILITY_STALE_OK
    assert _NOOP_CALLS, "the refresh behind the mirror never ran"


_NOOP_CALLS: list[int] = []


async def _noop_rebuild() -> None:
    _NOOP_CALLS.append(1)


@pytest.fixture(autouse=True)
def _clear_noop_calls():
    _NOOP_CALLS.clear()
    concept_cache._REFRESH_TASKS.clear()
    yield
    _NOOP_CALLS.clear()
    concept_cache._REFRESH_TASKS.clear()
