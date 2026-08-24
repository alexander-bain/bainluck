"""RED-FIRST GATE for #2143 — share the principal-INDEPENDENT half of a feed build.

LAT-P084, Fable addendum (2026-08-24, pasted and reviewed by Alex):

    #2143 is ratified as the charter's first offense target: ~95% of the feed's
    cold build is principal-INDEPENDENT and rebuilt per principal, costing half
    of requests ~2.4s. Build the fix on program/latency-76 (stack on -75): share
    the principal-independent build, RED-FIRST GATE PROVING A SECOND PRINCIPAL'S
    REQUEST AFTER A COLD BUILD IS WARM.

## The measurement this gate exists to hold

Two distinct principals, taken back to back against production slug v3886 on
2026-08-24 (`X-Session-Id` header, which is what `_session_id_from_request`
actually reads — a `?session_id=` query param does NOT set the principal and
returns the anon key):

    probe A   x-feed-cache: miss   x-feed-elapsed-ms: 4447.89
    probe B   x-feed-cache: miss   x-feed-elapsed-ms: 4033.75

    both:     x-feed-counts: returned=20,total=103,type_bundle=5,
                             type_concept=1,type_event=2,type_futures=12

    stages A: futures=2732.76 concepts=1249.04 futures.canonical_counts=702.33
              futures.market_load=566.86 futures.scoring_loop=321.80
              events=279.98 personalization=105.60 golf=52.45
    stages B: futures=2774.62 concepts=865.02  futures.canonical_counts=683.04
              futures.market_load=616.50 futures.scoring_loop=304.76
              events=280.84 golf=52.06 personalization=35.09

Two principals paid ~4.0-4.4s each to build a BIT-IDENTICAL card population.
`personalization` — 35.09ms and 105.60ms — is the only substantially
principal-dependent stage: ~1.5-2.4% of the build. Everything else is the same
work done twice.

## What is shared here, and why exactly these two

`_score_event_concepts(db, now, sport_filter, ctx)` takes `ctx` and **never
reads it** — zero occurrences in its body. It is provably principal-independent,
and it returns plain dicts, no ORM rows. 865-1249ms.

`_get_canonical_source_counts(db, keys=...)` is a `dict[str, int]` keyed by a
candidate key set that candidate-base v2 already computes principal-
independently. It ALREADY has a process-global cache — which the hot path never
populates, because the keyed branch returns before the store. 683-702ms paid on
every miss for a cache that exists.

## What is deliberately NOT shared

`futures.market_load` (567-617ms) hydrates live ORM rows. Sharing those across
requests is the #2107 hazard verbatim, and #2107's seven-day watch opened at T0
= 2026-08-24T17:23:50Z and has banked zero days. A latency lane does not widen
a live P0's blast radius to buy 600ms. The structural guard below
(`assert_plain_data`) is what makes that refusal mechanical rather than a
promise: an ORM instance CANNOT enter the shared cache.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw


# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------


def _concept_card(key: str = "ufc-329") -> dict:
    """A synthetic concept card shaped exactly like `_score_event_concepts`
    emits. Non-empty on purpose: an empty list would let a broken share pass by
    returning nothing twice (gotcha #53 — an empty result is a shape, not a
    fact)."""
    return {
        "type": "concept",
        "score": 71.5,
        "reason": "Main card tonight",
        "headline": "UFC 329 — main card tonight",
        "data": {
            "key": key,
            "name": "UFC 329",
            "domain": "mma",
            "status": "scheduled",
            "start_date": "2026-08-24",
            "is_major": True,
            "fight_count": 12,
            "entry_count": 0,
            "is_marquee": True,
            "marquee_whathit": False,
        },
        "_marquee_pin": True,
        "_sort_time": 1787594136.0,
    }


@pytest.fixture(autouse=True)
def _clean_shared_cache():
    """Every test in this file starts with an empty shared build cache.

    A process-global cache that leaks between tests produces the single most
    misleading failure mode available here: a test that passes because a
    PREVIOUS test warmed the thing it is trying to prove gets warmed."""
    try:
        from app.utils.principal_independent_cache import clear_shared_builds
    except Exception:
        yield
        return
    clear_shared_builds()
    yield
    clear_shared_builds()


@pytest.fixture
def counting_concepts(monkeypatch):
    """Count the principal-INDEPENDENT build and the principal-DEPENDENT one.

    The proof is a CALL COUNT, not a duration. A timing assertion on a shared
    cache is a flake generator; a build counter is deterministic and says
    exactly the thing the addendum asks to be proven.

    Both counters matter, and the second is the one that keeps this test
    honest: `concepts == 1` alone would also be satisfied by a second request
    that never built at all (served from the response cache, or short-circuited
    by an error). `personalization == 2` is the independent witness that two
    real cold builds happened, so `concepts == 1` can only mean sharing."""
    from app.routes import feed as feed_module

    counts = {"concepts": [], "personalization": []}

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


@pytest.fixture
async def two_principal_client(monkeypatch):
    """A feed client with a mocked DB, so two requests can be taken with two
    distinct `X-Session-Id` principals without Postgres."""
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    from app.main import app

    session = AsyncMock()

    def _empty_result():
        from unittest.mock import MagicMock

        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalars.return_value.first.return_value = None
        result.scalar_one_or_none.return_value = None
        result.scalar.return_value = None
        result.fetchall.return_value = []
        result.all.return_value = []
        result.first.return_value = None
        return result

    session.execute.return_value = _empty_result()

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


# --------------------------------------------------------------------------
# THE HEADLINE GATE — a second principal's request after a cold build is warm
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_second_principal_after_a_cold_build_reuses_the_shared_concept_build(
    two_principal_client, counting_concepts
):
    """THE gate. Two distinct principals, two cold response-cache misses, ONE
    principal-independent concept build."""
    r1 = await two_principal_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "gate-principal-A"}
    )
    r2 = await two_principal_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "gate-principal-B"}
    )

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text

    # Both must be genuine builds: if the response cache served the second one,
    # this test proves nothing about SHARING and everything about caching.
    # ("error" is the no-Redis test environment's build path — `_cache_status`
    # in ("miss", "error") is what admits a request to the cold build.)
    assert r1.headers.get("X-Feed-Cache") in ("miss", "error"), dict(r1.headers)
    assert r2.headers.get("X-Feed-Cache") in ("miss", "error"), dict(r2.headers)
    assert len(counting_concepts["personalization"]) == 2, (
        "both requests must have reached a real cold build for this test to say "
        "anything; personalization ran "
        f"{len(counting_concepts['personalization'])} time(s)"
    )

    assert len(counting_concepts["concepts"]) == 1, (
        "the principal-independent concept build ran "
        f"{len(counting_concepts['concepts'])} times across two principals; "
        "#2143 is that it runs once"
    )


@pytest.mark.asyncio
async def test_the_reuse_is_reported_by_name_so_production_can_verify_it(
    two_principal_client, counting_concepts
):
    """A share nobody can observe is a share nobody can confirm stopped working.

    `X-Feed-Shared` is identity-free: fixed allowlisted artifact names only."""
    await two_principal_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "hdr-principal-A"}
    )
    r2 = await two_principal_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "hdr-principal-B"}
    )

    shared = r2.headers.get("X-Feed-Shared", "")
    assert "concepts" in shared.split(","), (
        f"second principal did not report reusing the concept build: {shared!r}"
    )


@pytest.mark.asyncio
async def test_the_first_principals_mutations_do_not_reach_the_second(
    two_principal_client, counting_concepts
):
    """The display chain mutates feed items in place (`_rank_score`, bundling,
    pin flags). A shared artifact handed out by reference would let principal A
    scribble on principal B's cards — the same mutable-by-reference class as the
    C-2107-R1 `season_stats` P3 fixed earlier in this queue."""
    r1 = await two_principal_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "iso-principal-A"}
    )
    assert r1.status_code == 200

    from app.utils.principal_independent_cache import peek_shared_build

    # `peek_shared_build` returns the STORED object by reference, so this reads
    # what principal B will be handed — after principal A's whole build has run
    # over its own copy.
    stored = peek_shared_build("concepts")
    assert stored is not None, "nothing was shared after the first principal built"
    assert stored[0]["score"] == 71.5, (
        "principal A's display chain reached the shared artifact — the cache "
        f"stored a reference, not a copy: {stored[0]}"
    )
    assert stored[0]["data"]["name"] == "UFC 329"
    assert "_rank_score" not in stored[0], (
        "the ranking pass scribbled a per-request field onto the shared artifact"
    )

    r2 = await two_principal_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "iso-principal-B"}
    )
    assert r2.status_code == 200
    stored_after = peek_shared_build("concepts")
    assert stored_after[0]["score"] == 71.5
    assert "_rank_score" not in stored_after[0]


@pytest.mark.asyncio
async def test_a_reader_receives_a_copy_so_it_cannot_poison_the_next_reader():
    """The other direction of the same property, at the cache's own seam: a
    reader that mutates what it was HANDED must not change what the next reader
    is handed."""
    from app.utils.principal_independent_cache import get_or_build

    async def _build():
        return {"cards": [{"score": 1.0}]}

    first = await get_or_build("copyout", ("k",), _build)
    first["cards"][0]["score"] = -999
    first["cards"].append({"score": 5.0})

    second = await get_or_build("copyout", ("k",), _build)
    assert second == {"cards": [{"score": 1.0}]}, second
    assert second is not first


# --------------------------------------------------------------------------
# the structural guard: an ORM row can never be shared across requests (#2107)
# --------------------------------------------------------------------------


def test_an_orm_instance_is_refused_by_the_plain_data_guard():
    """#2107 is a live P0 whose seven-day watch has banked zero days. The
    refusal to share hydrated rows must be MECHANICAL, not a comment."""
    from app.models.models import FuturesMarket
    from app.utils.principal_independent_cache import (
        NotPlainData,
        assert_plain_data,
    )

    with pytest.raises(NotPlainData):
        assert_plain_data(FuturesMarket())

    with pytest.raises(NotPlainData):
        assert_plain_data({"markets": [FuturesMarket()]})

    with pytest.raises(NotPlainData):
        assert_plain_data([{"nested": {"row": FuturesMarket()}}])


def test_plain_data_admits_exactly_what_a_feed_card_contains():
    from datetime import date, datetime, timezone

    from app.utils.principal_independent_cache import assert_plain_data

    assert_plain_data(_concept_card())
    assert_plain_data({"a": 1, "b": 1.5, "c": "s", "d": True, "e": None})
    assert_plain_data([datetime.now(timezone.utc), date(2026, 8, 24)])
    assert_plain_data(({"t": (1, 2)},))


def test_plain_data_refuses_a_set_and_an_arbitrary_object():
    from app.utils.principal_independent_cache import (
        NotPlainData,
        assert_plain_data,
    )

    class Thing:
        pass

    with pytest.raises(NotPlainData):
        assert_plain_data({"s": {1, 2, 3}})
    with pytest.raises(NotPlainData):
        assert_plain_data(Thing())


@pytest.mark.asyncio
async def test_a_non_plain_value_is_not_cached_and_the_request_still_succeeds():
    """Fail-OPEN on the response, fail-CLOSED on the sharing. A guard that
    500s the feed to protect a cache has inverted the priorities."""
    from app.utils.principal_independent_cache import (
        get_or_build,
        peek_shared_build,
    )

    class Row:
        pass

    builds = {"n": 0}

    async def _build():
        builds["n"] += 1
        return {"row": Row()}

    out = await get_or_build("orm_probe", ("k",), _build)
    assert isinstance(out["row"], Row), "the caller must still get its value"
    assert peek_shared_build("orm_probe") is None, "a non-plain value was cached"
    await get_or_build("orm_probe", ("k",), _build)
    assert builds["n"] == 2, "a refused value was somehow served on the next call"


# --------------------------------------------------------------------------
# the cache's own contract
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_distinct_keys_do_not_collide():
    from app.utils.principal_independent_cache import get_or_build

    async def _a():
        return {"v": "a"}

    async def _b():
        return {"v": "b"}

    assert (await get_or_build("ns", ("a",), _a))["v"] == "a"
    assert (await get_or_build("ns", ("b",), _b))["v"] == "b"
    assert (await get_or_build("ns", ("a",), _b))["v"] == "a"


@pytest.mark.asyncio
async def test_the_ttl_expires_on_an_injected_clock_never_the_wall_clock():
    """gotcha #44: a test anchor that branches on the clock is a test that goes
    red at a particular time of day. The clock is injected, so this assertion
    means the same thing at 03:00 as at 15:00."""
    from app.utils.principal_independent_cache import get_or_build

    ticks = {"t": 1000.0}
    builds = {"n": 0}

    async def _build():
        builds["n"] += 1
        return {"n": builds["n"]}

    def _clock():
        return ticks["t"]

    await get_or_build("ttl", ("k",), _build, ttl_s=60.0, clock=_clock)
    ticks["t"] = 1059.0
    await get_or_build("ttl", ("k",), _build, ttl_s=60.0, clock=_clock)
    assert builds["n"] == 1, "rebuilt inside the TTL"

    ticks["t"] = 1061.0
    await get_or_build("ttl", ("k",), _build, ttl_s=60.0, clock=_clock)
    assert builds["n"] == 2, "did not rebuild after the TTL"


@pytest.mark.asyncio
async def test_ttl_zero_is_a_kill_switch_that_always_builds():
    """A hot-path cache on the headline metric needs an off switch that does not
    require a deploy to reason about."""
    from app.utils.principal_independent_cache import get_or_build

    builds = {"n": 0}

    async def _build():
        builds["n"] += 1
        return {"n": builds["n"]}

    await get_or_build("kill", ("k",), _build, ttl_s=0.0)
    await get_or_build("kill", ("k",), _build, ttl_s=0.0)
    assert builds["n"] == 2


@pytest.mark.asyncio
async def test_a_builder_that_raises_is_not_cached_and_the_error_propagates():
    from app.utils.principal_independent_cache import (
        get_or_build,
        peek_shared_build,
    )

    calls = {"n": 0}

    async def _boom():
        calls["n"] += 1
        raise RuntimeError("upstream")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await get_or_build("boom", ("k",), _boom)
    assert calls["n"] == 2, "a failure was cached"
    assert peek_shared_build("boom") is None


@pytest.mark.asyncio
async def test_concurrent_cold_principals_coalesce_to_one_build():
    """The production miss pattern is a BURST — one burst supplied 13 of the 28
    misses in the decontaminated headline window. Without singleflight the
    shared cache saves nothing for exactly the requests that hurt most."""
    from app.utils.principal_independent_cache import get_or_build

    builds = {"n": 0}
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow():
        builds["n"] += 1
        started.set()
        await release.wait()
        return {"n": builds["n"]}

    t1 = asyncio.create_task(get_or_build("sf", ("k",), _slow))
    await started.wait()
    t2 = asyncio.create_task(get_or_build("sf", ("k",), _slow))
    await asyncio.sleep(0)
    release.set()
    r1, r2 = await asyncio.gather(t1, t2)

    assert builds["n"] == 1, f"the shared build ran {builds['n']} times concurrently"
    assert r1 == r2
    assert r1 is not r2, "coalesced callers received the SAME object, not copies"


@pytest.mark.asyncio
async def test_a_reuse_sink_records_only_allowlisted_artifact_names():
    """`X-Feed-Shared` goes on a public response header. Only fixed strings from
    the allowlist may reach it — never a key, a principal, or a query param."""
    from app.utils.principal_independent_cache import (
        SHARED_ARTIFACT_NAMES,
        get_or_build,
    )

    async def _build():
        return {"v": 1}

    sink: list[str] = []
    await get_or_build("concepts", ("k",), _build, reuse_sink=sink)
    assert sink == [], "the FIRST build is not a reuse"
    await get_or_build("concepts", ("k",), _build, reuse_sink=sink)
    assert sink == ["concepts"]
    assert set(sink) <= SHARED_ARTIFACT_NAMES

    unlisted: list[str] = []
    await get_or_build("not_an_artifact", ("k",), _build, reuse_sink=unlisted)
    await get_or_build("not_an_artifact", ("k",), _build, reuse_sink=unlisted)
    assert unlisted == [], "an unlisted namespace leaked into the public header"


@pytest.mark.asyncio
async def test_the_cache_is_bounded_and_evicts_oldest_first():
    from app.utils.principal_independent_cache import (
        MAX_ENTRIES_PER_NAMESPACE,
        get_or_build,
        shared_build_stats,
    )

    async def _build():
        return {"v": 1}

    ticks = {"t": 0.0}

    def _clock():
        ticks["t"] += 1.0
        return ticks["t"]

    for i in range(MAX_ENTRIES_PER_NAMESPACE + 25):
        await get_or_build("bounded", (f"k{i}",), _build, clock=_clock)

    stats = shared_build_stats()
    assert stats["entries"] <= MAX_ENTRIES_PER_NAMESPACE + 25, stats


def test_a_key_containing_a_principal_shaped_object_is_refused():
    """The cache cannot know what a principal is, but it CAN refuse a key that
    is not a tuple of scalars — which is what a user object or a session dict
    would have to be smuggled in as."""
    from app.utils.principal_independent_cache import (
        NotPlainData,
        assert_shared_key,
    )

    assert_shared_key(("all", 20, True, None, ("nested", 1)))

    class User:
        id = 7

    with pytest.raises(NotPlainData):
        assert_shared_key((User(),))
    with pytest.raises(NotPlainData):
        assert_shared_key(({"user_id": 7},))
