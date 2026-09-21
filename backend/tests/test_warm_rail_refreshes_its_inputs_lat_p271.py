"""LAT-P271 (#2143) — a reader who scrolls past page one stops paying a cold build.

## The ship

Page one of Discover is warm. Page two is a ~2 s rebuild, over and over, and it
has been invisible because every counter the rail reports is about page one.

`GET /api/feed` stores an offset-independent PAGE BASE (LAT-P141): the whole
ranked list, published once, re-rendered into whatever page a reader asks for.
Page two hits it or pays the full build. The warm rail republishes page one
every `FEED_LIVE_REPUBLISH_PERIOD_S` and, in the same request, the route
publishes the base beside it — but the two are given different lifetimes:

* page one, published by `_prewarm_feed_shape`, deliberately does NOT spend the
  age of the shared artifacts the build consumed (#3841: "recorded, never
  spent"), so it gets the full 30 s / 60 s;
* the base, published by `routes/feed.py`, DOES spend it
  (`oldest_artifact_age_s=_consumed_age_s`) — correctly, because the base is the
  whole list and the total-age ceiling is a rule about served content.

Nobody re-derived the cadence arithmetic for that second publication. So the
base lives `CEILING - artifact_age` while the thing that replaces it returns in
`PERIOD` (+ up to `BUDGET`), and whenever the artifacts are older than the
reserve the base dies before its own republish.

## Measured on production, 2026-09-18

`/api/admin/feed-live-prewarm/last` at 03:49:30Z reported every shape `ok`,
`absent_labels: []`, and `discover_native` with **`artifact_age_s: 31.3`** — one
whole republish period. That base was born with 28.7 s of life under a rail that
returns in 30 s. Ten `offset=100` probes at 26 s spacing, a fresh
`x-session-id` each, `limit=50&event_pct=0.15`:

    03:48:15  page_base_hit        0.50 s
    03:48:41  page_base_hit        0.59 s
    03:49:07  MISS                 2.15 s   <-- full cold build
    03:49:34  page_base_hit        0.42 s
    03:50:00  MISS                 1.88 s   <-- full cold build
    03:50:27  page_base_hit        0.46 s
    03:50:53  page_base_hit        0.43 s
    03:51:18  page_base_stale_hit  0.29 s
    03:51:44  page_base_hit        0.29 s
    03:52:09  page_base_hit        0.51 s

Two of ten, and the sampler was itself republishing the base every 26 s — a real
reader, who warms nothing, meets the hole far more often than this.

## The fix, and what it is NOT

The warm rebuild declines shared artifacts older than the reserve, rebuilds
them, and republishes them on the namespace's own TTL. So the bound applies to
the READ and never to the WRITE, and the artifact is never deleted: the shape
later in the same pass consumes the YOUNGER artifact this build just published,
and every request that is not the warmer keeps consuming the older one until it
expires normally.

The shape it is deliberately not is `drop_entries_older_than` — the invalidating
spelling the over-ceiling path (CERT-1864/1885) uses. That one is right for "no
live page may be built from this"; used here it would invalidate the artifact
fleet-wide every 30 s and turn a refresh into a herd on the most expensive
endpoint we have. `test_a_declined_artifact_is_still_there_for_everybody_else`
is that distinction, and it is the load-bearing test in this file.
"""

from __future__ import annotations

import asyncio

import pytest

from app.utils import principal_independent_cache as pic
from app.utils.feed_cache import (
    FEED_LIVE_REPUBLISH_BUDGET_S,
    FEED_LIVE_REPUBLISH_MIN_HEADROOM_S,
    FEED_LIVE_REPUBLISH_PERIOD_S,
    FEED_RESPONSE_STALE_TTL_LIVE_SECONDS,
    live_total_age_headroom_s,
    warm_rail_max_shared_artifact_age_s,
)

NS = "market_load"
KEY = ("lat-p271", 1)

#: The number production actually reported for `discover_native`. Kept as the
#: specimen rather than "some big number" so a reader can tell the arithmetic
#: below is about an observation and not about a worst case someone imagined.
MEASURED_ARTIFACT_AGE_S = 31.3


@pytest.fixture(autouse=True)
def _cold_worker():
    pic.clear_shared_builds()
    pic.bind_max_shared_age(None)
    yield
    pic.clear_shared_builds()
    pic.bind_max_shared_age(None)


# --------------------------------------------------------------------------
# 1. The arithmetic: what the defect IS
# --------------------------------------------------------------------------


def test_the_bound_is_derived_from_the_cadence_and_not_written_down():
    """`CEILING - PERIOD - BUDGET`, computed — so moving any of the three moves it.

    It equals `FEED_LIVE_REPUBLISH_MIN_HEADROOM_S` today because the reserve is
    exactly spent (that constant's own comment says so). Asserting BOTH the
    derivation and the equality is the point: if a later change moves a constant
    and leaves the reserve behind, this fails and names which of the two drifted
    instead of silently re-opening the hole.
    """
    assert warm_rail_max_shared_artifact_age_s() == (
        FEED_RESPONSE_STALE_TTL_LIVE_SECONDS
        - FEED_LIVE_REPUBLISH_PERIOD_S
        - FEED_LIVE_REPUBLISH_BUDGET_S
    )
    assert warm_rail_max_shared_artifact_age_s() == FEED_LIVE_REPUBLISH_MIN_HEADROOM_S


def test_an_artifact_at_the_bound_leaves_the_base_alive_until_its_own_republish():
    """A base built at the bound outlives `PERIOD + BUDGET`. That is the invariant."""
    headroom = live_total_age_headroom_s(warm_rail_max_shared_artifact_age_s())
    assert headroom >= FEED_LIVE_REPUBLISH_PERIOD_S + FEED_LIVE_REPUBLISH_BUDGET_S


def test_the_age_production_reported_does_not(
):
    """The same arithmetic on the measured 31.3 s — the hole, as a number.

    This is the assertion that would have failed on 2026-09-18 and did not exist
    to. It does not assert a duration (LAT-P084's gate: timing assertions on a
    cache are flake generators); it asserts that the published base could not
    reach its own replacement.
    """
    headroom = live_total_age_headroom_s(MEASURED_ARTIFACT_AGE_S)
    assert headroom < FEED_LIVE_REPUBLISH_PERIOD_S + FEED_LIVE_REPUBLISH_BUDGET_S
    # And by a wide margin, not a rounding: the gap was most of a period.
    assert (FEED_LIVE_REPUBLISH_PERIOD_S + FEED_LIVE_REPUBLISH_BUDGET_S) - headroom > 15


# --------------------------------------------------------------------------
# 2. The read bound itself
# --------------------------------------------------------------------------


def test_a_bound_may_only_narrow_never_widen():
    """A caller can decline what the TTL allows; it can never admit what it forbids."""
    assert pic._shared_read_bound(60.0, None) == 60.0
    assert pic._shared_read_bound(60.0, 10.0) == 10.0
    assert pic._shared_read_bound(60.0, 600.0) == 60.0
    assert pic._shared_read_bound(60.0, -5.0) == 0.0


def test_an_unbound_context_is_byte_for_byte_what_shipped():
    """No bound bound => the namespace TTL, i.e. the only bound there has ever been."""
    assert pic.max_shared_age_s() is None

    builds = []

    async def builder():
        builds.append(1)
        return {"v": len(builds)}

    async def run():
        first = await pic.get_or_build(NS, KEY, builder, ttl_s=60.0)
        second = await pic.get_or_build(NS, KEY, builder, ttl_s=60.0)
        return first, second

    first, second = asyncio.run(run())
    assert first == second == {"v": 1}
    assert len(builds) == 1, "an unbound reader must reuse, exactly as before"


def test_the_warm_rail_declines_an_artifact_older_than_the_bound_and_rebuilds():
    """The fix: too-old inputs are refreshed, not inherited."""
    builds = []

    async def builder():
        builds.append(1)
        return {"v": len(builds)}

    async def run():
        # Built now, then read by a context that will only take something much
        # younger than it is. `clock` makes the age explicit instead of sleeping.
        t = [1000.0]
        await pic.get_or_build(NS, KEY, builder, ttl_s=60.0, clock=lambda: t[0])
        t[0] += MEASURED_ARTIFACT_AGE_S
        return await pic.get_or_build(
            NS,
            KEY,
            builder,
            ttl_s=60.0,
            max_age_s=warm_rail_max_shared_artifact_age_s(),
            clock=lambda: t[0],
        )

    out = asyncio.run(run())
    assert len(builds) == 2, "a 31.3s artifact must be refreshed, not consumed"
    assert out == {"v": 2}


def test_an_artifact_inside_the_bound_is_still_consumed():
    """The bound refuses the old, not the shared. Otherwise it is a kill switch."""
    builds = []

    async def builder():
        builds.append(1)
        return {"v": len(builds)}

    async def run():
        t = [1000.0]
        await pic.get_or_build(NS, KEY, builder, ttl_s=60.0, clock=lambda: t[0])
        t[0] += warm_rail_max_shared_artifact_age_s() / 2.0
        return await pic.get_or_build(
            NS,
            KEY,
            builder,
            ttl_s=60.0,
            max_age_s=warm_rail_max_shared_artifact_age_s(),
            clock=lambda: t[0],
        )

    out = asyncio.run(run())
    assert len(builds) == 1
    assert out == {"v": 1}


# --------------------------------------------------------------------------
# 3. The load-bearing one: a decline is not a deletion
# --------------------------------------------------------------------------


def test_a_declined_artifact_is_still_there_for_everybody_else():
    """The herd guard.

    The warmer declines a 31.3 s artifact. Every OTHER request in the process —
    readers for whom that artifact is entirely valid — must still find it in the
    local tier. If this ever fails, the fix has become `drop_entries_older_than`
    in disguise and is now invalidating the shared tier on the flagship route
    every republish period.

    🔴 THIS ASSERTS ON THE TIER, NOT ON A BUILD COUNT, AND THE FIRST DRAFT DID
    THE LATTER AND WAS VACUOUS. A declining `get_or_build` REBUILDS and stores
    the fresh artifact, so the next reader hits either way and the build count
    cannot see an eviction at all: the guard passed with eviction wired in.
    `_read_fresh` is the only place the two outcomes differ.
    """
    now = 1000.0
    pic._store.setdefault(NS, {})[KEY] = (now, {"v": 1})

    # The warmer's read: declined, and the entry stays.
    hit, _value, _age = pic._read_fresh(
        NS,
        KEY,
        60.0,
        now + MEASURED_ARTIFACT_AGE_S,
        warm_rail_max_shared_artifact_age_s(),
    )
    assert hit is False, "31.3s is past the rail's bound"
    assert KEY in pic._store[NS], "declining an artifact must never evict it"

    # Any other reader in the same process, same instant: a plain hit.
    hit, value, age = pic._read_fresh(NS, KEY, 60.0, now + MEASURED_ARTIFACT_AGE_S)
    assert hit is True and value == {"v": 1}
    assert age == pytest.approx(MEASURED_ARTIFACT_AGE_S)

    # And the namespace TTL still does evict, because that bound is everybody's.
    hit, _value, _age = pic._read_fresh(NS, KEY, 60.0, now + 61.0)
    assert hit is False
    assert KEY not in pic._store[NS], "the TTL must still reap"


def test_the_scope_is_a_scope():
    """`max_shared_age_scope` restores the previous bound, including `None`."""
    assert pic.max_shared_age_s() is None
    with pic.max_shared_age_scope(10.0):
        assert pic.max_shared_age_s() == 10.0
        with pic.max_shared_age_scope(2.0):
            assert pic.max_shared_age_s() == 2.0
        assert pic.max_shared_age_s() == 10.0
    assert pic.max_shared_age_s() is None


def test_the_ambient_bound_reaches_a_call_site_three_frames_down():
    """`canonical_counts` is resolved inside `_score_futures`, not at the route.

    The bound is a contextvar for exactly that reason. A version of this fix that
    only passed a keyword argument would close the hole for the one artifact the
    route names and leave it open for the two it does not.
    """
    builds = []

    async def builder():
        builds.append(1)
        return {"v": len(builds)}

    async def three_frames_down(clock):
        async def inner():
            return await pic.get_or_build(NS, KEY, builder, ttl_s=60.0, clock=clock)

        return await inner()

    async def run():
        t = [1000.0]
        await pic.get_or_build(NS, KEY, builder, ttl_s=60.0, clock=lambda: t[0])
        t[0] += MEASURED_ARTIFACT_AGE_S
        with pic.max_shared_age_scope(warm_rail_max_shared_artifact_age_s()):
            await three_frames_down(lambda: t[0])
        return len(builds)

    assert asyncio.run(run()) == 2, "the bound must reach a nested call site"


# --------------------------------------------------------------------------
# 4. The route actually asks for the bound
# --------------------------------------------------------------------------


def test_the_route_binds_the_bound_on_the_prewarm_path_and_only_there():
    """STRUCTURAL, and labelled as such — the house idiom for a call site.

    `get_feed` is a single 9,000-line coroutine behind a DB session and a real
    Redis client; `test_feed_prewarm.py` pins its warm-path arguments the same
    way (`inspect.getsource` + `test_prewarm_passes_every_get_feed_parameter_
    explicitly`). What this can prove is the two things that would silently undo
    the fix: that the bind exists under `_prewarm_rebuild`, and that its
    argument is the DERIVED helper rather than a literal that would rot the
    moment a cadence constant moves.

    What it cannot prove is that the bound reaches the artifacts. That is what
    the production after-check is for, and it has a number: `artifact_age_s` on
    `/api/admin/feed-live-prewarm/last` must fall from 31.3 s to inside the
    bound on the next live evening.
    """
    import inspect
    import textwrap

    from app.routes import feed as feed_route

    source = textwrap.dedent(inspect.getsource(feed_route.get_feed))
    assert "bind_max_shared_age(warm_rail_max_shared_artifact_age_s())" in source, (
        "the warm rebuild must bind the derived bound"
    )
    bind_line = next(
        i
        for i, line in enumerate(source.splitlines())
        if "bind_max_shared_age(" in line
    )
    guard = source.splitlines()[bind_line - 1]
    assert guard.strip() == "if _prewarm_rebuild:", (
        "the bound is the WARM RAIL's, not every reader's — a reader who "
        "declines a shared artifact rebuilds it on the request path, which is "
        "the cost this whole module exists to avoid. Found guard: " + guard
    )


# --------------------------------------------------------------------------
# 5. The counter reads as what happened
# --------------------------------------------------------------------------


def test_a_decline_is_not_reported_as_the_tier_failing():
    """`cross_worker_declined_age`, never `cross_worker_misses` or a failure.

    A miss says sharing did not reach this worker; a decline says it reached it
    and the warm rail chose to refresh. Folding the second into the first would
    make the fix that closes this hole look, on every dashboard, exactly like the
    cross-worker tier degrading — and `cross_worker_failures` has already cost
    this module one round of that (LAT-P223).
    """
    async def run():
        return await pic._read_cross_worker(NS, KEY, 60.0, 10.0)

    # No client / disabled tier is fine here: what this pins is that the counter
    # EXISTS and starts at zero on both views, so a reader of
    # `shared_build_stats()` can tell the two apart at all.
    stats = pic.shared_build_stats()
    assert "cross_worker_declined_age" in stats
    assert stats["cross_worker_declined_age"] == 0
    asyncio.run(run())


def test_the_declined_counter_is_bumped_on_the_decline_and_nothing_else_is():
    """Drive `_read_cross_worker` past its envelope checks with a stored age."""
    import json
    import time as _time

    class _Client:
        def __init__(self, stored_wall):
            self._raw = pic.wire_encode(
                json.dumps(
                    {
                        # This build's wire, not a literal: a planted envelope
                        # is only a test of the READ path if the reader would
                        # accept it (it declines any other codec version).
                        "v": pic.WIRE_ENVELOPE_VERSION,
                        "ns": NS,
                        "k": repr(KEY),
                        "stored_wall": stored_wall,
                        "payload": pic.encode_shared_payload({"v": 1}),
                    },
                    separators=(",", ":"),
                )
            )

        async def get(self, _key):
            return self._raw

    async def run(monkeypatched_client, bound):
        import app.utils.request_cache as _rc

        async def _fake_client():
            return monkeypatched_client

        orig = _rc.get_shared_async_redis
        _rc.get_shared_async_redis = _fake_client
        try:
            return await pic._read_cross_worker(NS, KEY, 60.0, bound)
        finally:
            _rc.get_shared_async_redis = orig

    if not pic.cross_worker_enabled():
        pytest.skip("cross-worker tier disabled in this environment")

    client = _Client(_time.time() - MEASURED_ARTIFACT_AGE_S)

    pic.clear_shared_builds()
    hit, _value, _age = asyncio.run(run(client, warm_rail_max_shared_artifact_age_s()))
    declined = pic.shared_build_stats()
    assert hit is False
    assert declined["cross_worker_declined_age"] == 1
    assert declined["cross_worker_misses"] == 0
    assert declined["cross_worker_failures"] == 0
    assert declined["cross_worker_hits"] == 0

    # The SAME bytes, read without the bound, are a plain hit — so the decline is
    # the caller's choice and not a property of the stored envelope.
    pic.clear_shared_builds()
    hit, value, _age = asyncio.run(run(client, None))
    unbound = pic.shared_build_stats()
    assert hit is True and value == {"v": 1}
    assert unbound["cross_worker_hits"] == 1
    assert unbound["cross_worker_declined_age"] == 0


# --------------------------------------------------------------------------
# 5. LAT-P277 (#2143): the SAME rule, in the tier that is read FIRST
# --------------------------------------------------------------------------
#
# `cross_worker_declined_age` above is the Redis half. The bound is enforced in
# TWO places — `_read_cross_worker` and `_read_fresh` — by a byte-identical
# predicate, and only one of them was instrumented. `_read_fresh` is the tier
# consulted FIRST (`get_or_build`: process-local dict -> Redis -> builder), and
# the warm rail runs every `FEED_LIVE_REPUBLISH_PERIOD_S` in a process that just
# published the artifact, so on a warm worker the decline happens in L1 and the
# Redis hop is never reached. The counter that existed covered the rarer path.
#
# Folded into `builds`, a decline is indistinguishable from a cold miss — and
# those have opposite readings. A cold miss says sharing did not reach this
# worker; a decline says sharing reached it and the warm rail chose to refresh.
# That is the same argument the `cross_worker_declined_age` comment makes, and
# it applies with more force here, because this is the path that actually runs.


def test_the_local_tier_decline_is_counted_and_not_folded_into_builds():
    """The L1 half of the bound reports itself, exactly as the Redis half does.

    Drives the identical scenario as
    `test_the_warm_rail_declines_an_artifact_older_than_the_bound_and_rebuilds`
    — which proves the decline HAPPENS — and asserts the event is now readable
    from `shared_build_stats()`. Without the counter that test passes and an
    operator still cannot tell the rail is refreshing rather than missing.
    """
    builds = []

    async def builder():
        builds.append(1)
        return {"v": len(builds)}

    async def run():
        t = [1000.0]
        await pic.get_or_build(NS, KEY, builder, ttl_s=60.0, clock=lambda: t[0])
        t[0] += MEASURED_ARTIFACT_AGE_S
        return await pic.get_or_build(
            NS,
            KEY,
            builder,
            ttl_s=60.0,
            max_age_s=warm_rail_max_shared_artifact_age_s(),
            clock=lambda: t[0],
        )

    pic.clear_shared_builds()
    out = asyncio.run(run())
    stats = pic.shared_build_stats()

    # The behaviour this file already guarantees, restated so a failure here is
    # never mistaken for the bound itself having stopped working.
    assert len(builds) == 2 and out == {"v": 2}

    assert stats["declined_age"] == 1, (
        "an L1 artifact inside its TTL and past the caller's bound must be "
        "counted as a decline, not silently absorbed into `builds`"
    )
    # Named by artifact, for the same reason as every other counter here: the
    # aggregate cannot say WHICH shared artifact the rail keeps refreshing.
    assert stats["by_namespace"][NS]["declined_age"] == 1


def test_a_local_decline_is_not_reported_as_a_cross_worker_event():
    """The two tiers keep their own books. Otherwise one hides the other.

    A decline in L1 must never move the Redis counters: the Redis hop is not
    even reached on this path, so a nonzero `cross_worker_*` here would be an
    instrument reporting traffic that did not occur.
    """

    async def builder():
        return {"v": 1}

    async def run():
        t = [1000.0]
        await pic.get_or_build(NS, KEY, builder, ttl_s=60.0, clock=lambda: t[0])
        t[0] += MEASURED_ARTIFACT_AGE_S
        return await pic.get_or_build(
            NS,
            KEY,
            builder,
            ttl_s=60.0,
            max_age_s=warm_rail_max_shared_artifact_age_s(),
            clock=lambda: t[0],
        )

    pic.clear_shared_builds()
    asyncio.run(run())
    stats = pic.shared_build_stats()

    assert stats["declined_age"] == 1
    assert stats["cross_worker_declined_age"] == 0
    assert stats["hits"] == 0, "a declined read is not a hit"


def test_an_artifact_inside_the_bound_bumps_no_decline_counter():
    """The control. Without it the counter could be bumped on every L1 read."""

    async def builder():
        return {"v": 1}

    async def run():
        t = [1000.0]
        await pic.get_or_build(NS, KEY, builder, ttl_s=60.0, clock=lambda: t[0])
        t[0] += warm_rail_max_shared_artifact_age_s() / 2.0
        return await pic.get_or_build(
            NS,
            KEY,
            builder,
            ttl_s=60.0,
            max_age_s=warm_rail_max_shared_artifact_age_s(),
            clock=lambda: t[0],
        )

    pic.clear_shared_builds()
    asyncio.run(run())
    stats = pic.shared_build_stats()

    assert stats["declined_age"] == 0
    assert stats["hits"] == 1


def test_an_unbounded_read_past_the_bound_bumps_no_decline_counter():
    """The second control, and the one that pins the counter to the BOUND.

    The same artifact at the same age, read by a caller that asked for no
    narrower bound, is a plain hit. So `declined_age` counts the caller's
    choice — not the artifact's age, which every other reader is still happily
    consuming (`test_a_declined_artifact_is_still_there_for_everybody_else`).
    """

    async def builder():
        return {"v": 1}

    async def run():
        t = [1000.0]
        await pic.get_or_build(NS, KEY, builder, ttl_s=60.0, clock=lambda: t[0])
        t[0] += MEASURED_ARTIFACT_AGE_S
        return await pic.get_or_build(NS, KEY, builder, ttl_s=60.0, clock=lambda: t[0])

    pic.clear_shared_builds()
    asyncio.run(run())
    stats = pic.shared_build_stats()

    assert stats["declined_age"] == 0
    assert stats["hits"] == 1


def test_both_enforcement_sites_of_the_bound_are_instrumented():
    """The class guard: one rule with two implementations, both counted.

    This file's defect was not a missing counter — it was a rule implemented
    twice and instrumented once. A third tier, or a refactor that moves the
    predicate, must not re-open that gap silently, so the guard is on the
    SOURCE: every `age_s > read_bound` decline must sit beside a counter bump.
    """
    import inspect

    source = inspect.getsource(pic)
    predicate = "if read_bound is not None and age_s > read_bound:"
    sites = source.count(predicate)
    assert sites == 2, (
        f"expected the bound to be enforced in exactly 2 tiers, found {sites} — "
        "a new enforcement site needs its own decline counter"
    )
    for counter in ("declined_age", "cross_worker_declined_age"):
        assert f'_bump(namespace, "{counter}")' in source, (
            f"{counter} must be bumped by name at its enforcement site"
        )
