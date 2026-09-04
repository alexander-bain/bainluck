"""GATE for LAT-P221b — the shared artifact must be allowed to outlive the page.

## The ship

A reader who opens bainluck.com cold stops waiting a second and a half for the
first card. Same ship as LAT-P141 through LAT-P221; this file gates the last
mechanism it needed.

## The defect this file exists because of

`principal_independent_cache.DEFAULT_TTL_S` was 60s. The anonymous feed
response entry is `FEED_RESPONSE_TTL_ANON_SECONDS = 60` fresh. **The two clocks
were the same length**, so at the instant a request became a `miss` — which is
what "the response entry just expired" MEANS — the shared artifact it wanted
had expired at the same second. A reader arriving alone could never benefit
from sharing, no matter how well the sharing worked.

That the sharing itself works was already measured (LAT-P221, CERT-892): two
misses 15s apart took `futures.market_load` from 301ms to 99ms across a worker
boundary, `tier=cross_worker`. What had never been measured was that the
benefit was gated by an unrelated number. Production, 2026-09-04, same code,
same hour, `/tmp/lat145-bars/`:

    readers 20s apart   `market_load` shared on 80.0% of misses   miss p50 1,502ms
    readers 65s apart   `market_load` shared on 41.2% of misses   miss p50 1,767ms

## What is gated here, and what deliberately is NOT

Gated: that a namespace's TTL is independent of every other namespace's, that
it can be moved at runtime with no deploy, that the pre-existing process-wide
kill switch still outranks it, and that raising one cannot resurrect LAT-P104's
"a key that rotates faster than its TTL throws fresh entries away" defect.

NOT gated: any particular value for `market_load`. Raising it is an attended
decision (Alex, DECIDE E1) that lands as a config var first and is promoted
into `TTL_BY_NAMESPACE` only after a post-state measurement has read it in
production. A test that pinned a value would be asserting the decision, not the
mechanism.
"""

from __future__ import annotations

import asyncio
import math

import pytest

from app.utils import principal_independent_cache as pic


@pytest.fixture(autouse=True)
def _clean_env_and_cache(monkeypatch):
    """No inherited TTL env, no inherited artifacts.

    A process-global cache that leaks between tests passes for the wrong
    reason, and an inherited `FEED_SHARED_BUILD_TTL_S` from a sibling suite
    would silently make every precedence assertion below vacuous.
    """
    monkeypatch.delenv("FEED_SHARED_BUILD_TTL_S", raising=False)
    for namespace in sorted(pic.SHARED_ARTIFACT_NAMES):
        monkeypatch.delenv(pic.namespace_ttl_env_var(namespace), raising=False)
    pic.clear_shared_builds()
    yield
    pic.clear_shared_builds()


# --------------------------------------------------------------------------
# the lever
# --------------------------------------------------------------------------


def test_a_namespace_with_no_opinion_still_gets_the_default():
    """The mechanism must be invisible until someone uses it."""
    for namespace in sorted(pic.SHARED_ARTIFACT_NAMES):
        if namespace in pic.TTL_BY_NAMESPACE:
            continue
        assert pic.shared_build_ttl_for(namespace) == pic.DEFAULT_TTL_S


def test_the_shipped_market_load_default_is_staleness_NEUTRAL():
    """The one value this change ships must not make any reader staler.

    Before the promotion fix, an L2 read was promoted into L1 stamped `now`, so
    a 60s artifact COULD be served for up to ~120s — 60 in the worker that built
    it, up to 60 more in a worker that promoted it late. `market_load` at 2x
    `DEFAULT_TTL_S` therefore DECLARES the bound production has been serving
    since LAT-P103 instead of raising it, which is what makes it safe to land
    unattended alongside a fix that would otherwise be a pure latency
    regression (it removes an accidental 2x lifetime).

    Written as an arithmetic relation, not as the literal `120.0`: if someone
    changes `DEFAULT_TTL_S`, the neutrality argument has to move with it or be
    re-made. A bare literal would silently stop meaning what this docstring
    says.
    """
    assert pic.TTL_BY_NAMESPACE["market_load"] == 2 * pic.DEFAULT_TTL_S


def test_concepts_gets_TIGHTER_not_looser(monkeypatch):
    """The namespace whose staleness is real keeps the smaller number.

    `concepts` embeds `now`-derived text and marquee pin state; `market_load`
    is market rows whose own writers run on a 10-minute-to-6-hour grid. A
    single global TTL could only move both. This asserts the direction: after
    this change `concepts` is bounded at `DEFAULT_TTL_S` for real (the
    promotion no longer stretches it), and is not carried up by `market_load`.
    """
    assert pic.shared_build_ttl_for("concepts") == pic.DEFAULT_TTL_S
    assert pic.shared_build_ttl_for("canonical_counts") == pic.DEFAULT_TTL_S
    assert pic.shared_build_ttl_for("market_load") > pic.DEFAULT_TTL_S


def test_the_table_moves_one_namespace_and_leaves_the_others(monkeypatch):
    """`TTL_BY_NAMESPACE` is the code-default lane, and it is per-namespace.

    This is the property the whole change is for: `market_load` is market rows
    on a 10-minute-to-6-hour writer grid, `concepts` embeds `now`-derived copy
    and pin state. One number cannot bound both honestly.
    """
    monkeypatch.setitem(pic.TTL_BY_NAMESPACE, "market_load", 600.0)

    assert pic.shared_build_ttl_for("market_load") == 600.0
    assert pic.shared_build_ttl_for("concepts") == pic.DEFAULT_TTL_S
    assert pic.shared_build_ttl_for("canonical_counts") == pic.DEFAULT_TTL_S


def test_the_per_namespace_env_var_moves_it_with_no_deploy(monkeypatch):
    """The raise lands as ONE `config:set`, not as a release.

    LAT-P221b asks Alex for a command, not a deploy, precisely so the revert is
    also a command. If this stops working the ask stops being cheap.
    """
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_MARKET_LOAD", "600")

    assert pic.shared_build_ttl_for("market_load") == 600.0
    assert pic.shared_build_ttl_for("concepts") == pic.DEFAULT_TTL_S


def test_the_env_var_name_is_derived_from_the_namespace():
    assert pic.namespace_ttl_env_var("market_load") == (
        "FEED_SHARED_BUILD_TTL_S_MARKET_LOAD"
    )
    assert pic.namespace_ttl_env_var("concepts") == "FEED_SHARED_BUILD_TTL_S_CONCEPTS"


# --------------------------------------------------------------------------
# precedence — and the one rule that is not a precedence rule
# --------------------------------------------------------------------------


def test_the_kill_switch_outranks_the_per_namespace_lever(monkeypatch):
    """`FEED_SHARED_BUILD_TTL_S=0` is ABSOLUTE.

    It is the documented "turn all sharing off without a deploy" lever and it
    predates this table. Adding a second, more specific lever must not create a
    state where someone pulls the kill switch during an incident and one
    namespace keeps serving shared artifacts anyway.
    """
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "0")
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_MARKET_LOAD", "600")
    monkeypatch.setitem(pic.TTL_BY_NAMESPACE, "market_load", 600.0)

    assert pic.shared_build_ttl_for("market_load") == 0.0
    assert pic.shared_build_ttl_for("concepts") == 0.0


def test_the_specific_env_var_beats_the_global_one(monkeypatch):
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "120")
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_MARKET_LOAD", "600")

    assert pic.shared_build_ttl_for("market_load") == 600.0
    assert pic.shared_build_ttl_for("concepts") == 120.0


def test_an_explicit_global_still_moves_namespaces_that_named_no_value(monkeypatch):
    """The process-wide lever keeps working for everyone who has not opted out."""
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "300")

    for namespace in sorted(pic.SHARED_ARTIFACT_NAMES):
        assert pic.shared_build_ttl_for(namespace) == 300.0


def test_an_explicit_global_beats_the_code_default_table(monkeypatch):
    """An operator who sets the global has said something more recent than the
    table did, and gets what they asked for."""
    monkeypatch.setitem(pic.TTL_BY_NAMESPACE, "market_load", 600.0)
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "120")

    assert pic.shared_build_ttl_for("market_load") == 120.0


@pytest.mark.parametrize("garbage", ["", "abc", "60s", "NaN-ish"])
def test_an_unreadable_value_falls_back_and_never_kills_sharing(monkeypatch, garbage):
    """A typo in a config var is not a kill switch.

    `_parse_ttl` collapses "absent" and "unreadable" deliberately. The failure
    this forecloses is a fat-fingered `config:set` reading as 0 and silently
    turning the flagship route's sharing off — which looks exactly like a
    latency regression with no deploy to blame it on.
    """
    monkeypatch.setitem(pic.TTL_BY_NAMESPACE, "market_load", 600.0)
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_MARKET_LOAD", garbage)
    assert pic.shared_build_ttl_for("market_load") == 600.0

    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", garbage)
    assert pic.shared_build_ttl_for("market_load") == 600.0
    assert pic.shared_build_ttl_for("concepts") == pic.DEFAULT_TTL_S


def test_a_negative_value_clamps_to_the_kill_switch_not_to_the_past(monkeypatch):
    """A negative TTL would make every entry instantly expired; say so as 0."""
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_MARKET_LOAD", "-5")
    assert pic.shared_build_ttl_for("market_load") == 0.0


# --------------------------------------------------------------------------
# LAT-P104 must not come back one env var later
# --------------------------------------------------------------------------


def test_the_clock_bucket_never_rotates_faster_than_a_RAISED_namespace_ttl(
    monkeypatch,
):
    """The clamp used to read the GLOBAL TTL. Per-namespace TTLs break that.

    LAT-P104's defect was a key that rotated (30s) faster than the TTL (60s),
    so the fleet rebuilt a still-fresh 865-1249ms stage twice per TTL. The
    clamp in `clock_bucket_s` is what makes that unrepeatable BY CONSTRUCTION —
    but a clamp that reads only `FEED_SHARED_BUILD_TTL_S` stops bounding a
    namespace that has its own, larger TTL. This is that regression.
    """
    huge = float(pic.CLOCK_BUCKET_S) * 3

    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_CONCEPTS", str(int(huge)))
    assert pic.clock_bucket_s() >= huge

    monkeypatch.delenv("FEED_SHARED_BUILD_TTL_S_CONCEPTS")
    monkeypatch.setitem(pic.TTL_BY_NAMESPACE, "concepts", huge)
    assert pic.clock_bucket_s() >= huge


def test_the_clock_bucket_is_unchanged_when_nothing_is_raised():
    assert pic.clock_bucket_s() == float(pic.CLOCK_BUCKET_S)


def test_the_kill_switch_does_not_collapse_the_clock_bucket(monkeypatch):
    """`max_shared_build_ttl_s()` goes to 0 under the kill switch; the bucket
    must stay at its chosen width rather than following it down."""
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "0")
    assert pic.max_shared_build_ttl_s() == 0.0
    assert pic.clock_bucket_s() == float(pic.CLOCK_BUCKET_S)


# --------------------------------------------------------------------------
# the lever has to reach `get_or_build`, not just the accessor
# --------------------------------------------------------------------------


def _build_counter():
    calls = {"n": 0}

    async def builder():
        calls["n"] += 1
        return {"n": calls["n"]}

    return calls, builder


def test_a_raised_namespace_survives_a_gap_that_kills_the_default_one(monkeypatch):
    """The whole ship, at the unit level.

    Two namespaces, one raised, one not; two reads 90 SECONDS apart — the
    spacing LAT-P221b's registered bar samples at, chosen to be past the 60s
    response cache so every sample is a genuine `miss`. The raised namespace
    reuses; the default one rebuilds. If this inverts, the config var Alex is
    asked to set does nothing.
    """
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "0")
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_MARKET_LOAD", "600")

    now = {"t": 1_000.0}
    raised_calls, raised_builder = _build_counter()
    default_calls, default_builder = _build_counter()

    async def _run():
        for namespace, builder in (
            ("market_load", raised_builder),
            ("concepts", default_builder),
        ):
            await pic.get_or_build(namespace, ("k",), builder, clock=lambda: now["t"])
        now["t"] += 90.0
        for namespace, builder in (
            ("market_load", raised_builder),
            ("concepts", default_builder),
        ):
            await pic.get_or_build(namespace, ("k",), builder, clock=lambda: now["t"])

    asyncio.run(_run())

    assert raised_calls["n"] == 1, "the raised namespace rebuilt inside its TTL"
    assert default_calls["n"] == 2, "the default namespace did NOT expire at 60s"


def test_an_explicit_ttl_argument_still_wins_over_the_table(monkeypatch):
    """`ttl_s=` is the caller's override and stays the most specific thing."""
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "0")
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_MARKET_LOAD", "600")

    now = {"t": 1_000.0}
    calls, builder = _build_counter()

    async def _run():
        await pic.get_or_build(
            "market_load", ("k",), builder, ttl_s=10.0, clock=lambda: now["t"]
        )
        now["t"] += 30.0
        await pic.get_or_build(
            "market_load", ("k",), builder, ttl_s=10.0, clock=lambda: now["t"]
        )

    asyncio.run(_run())
    assert calls["n"] == 2


def test_the_kill_switch_still_bypasses_the_module_entirely(monkeypatch):
    """Two calls, no cache, under the kill switch — even with the lever set."""
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "0")
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_MARKET_LOAD", "600")

    calls, builder = _build_counter()

    async def _run():
        await pic.get_or_build("market_load", ("k",), builder)
        await pic.get_or_build("market_load", ("k",), builder)

    asyncio.run(_run())
    assert calls["n"] == 2
    assert pic.shared_build_stats()["entries"] == 0


# --------------------------------------------------------------------------
# the Redis tier has to expire on the SAME clock as the local one
# --------------------------------------------------------------------------


class _RecordingRedis:
    """Serves only the stage tier's prefix and records the `ex` it is given."""

    def __init__(self) -> None:
        self.store: dict[str, object] = {}
        self.expires: list[int] = []

    def _stage_key(self, key) -> bool:
        return str(key).startswith(pic.REDIS_KEY_PREFIX)

    async def get(self, key):
        if not self._stage_key(key):
            raise ConnectionError("only the stage tier is served by this fake")
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        if not self._stage_key(key):
            raise ConnectionError("only the stage tier is served by this fake")
        self.expires.append(ex)
        self.store[key] = value
        return True


def test_the_cross_worker_entry_expires_on_the_namespace_ttl(monkeypatch):
    """A raised local TTL with an unraised Redis `EX` would be a cache that
    lies to exactly the reader this ship is for.

    The cold worker — a fresh dyno, a restarted process, or simply the other of
    `WEB_CONCURRENCY=2` — reaches the artifact through L2 or not at all. If `EX`
    still tracked the old 60s the raise would help only the worker that built
    it, which is the one reader who never needed it.
    """
    from app.utils import request_cache as _rc

    fake = _RecordingRedis()

    async def _get_client():
        return fake

    monkeypatch.setattr(_rc, "get_shared_async_redis", _get_client)
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_MARKET_LOAD", "600")

    _, builder = _build_counter()

    async def _run():
        await pic.get_or_build("market_load", ("k",), builder)

    asyncio.run(_run())

    assert fake.expires, "nothing was published to the shared tier"
    assert fake.expires[-1] >= 600, fake.expires


def test_a_cold_worker_reads_a_raised_artifact_past_the_old_ttl(monkeypatch):
    """L1 cleared (a cold worker), 90s elapsed, and the artifact is still there.

    Same 90s spacing as the registered bar. Under the old single TTL this read
    was a rebuild by construction; that is the entire finding.
    """
    from app.utils import request_cache as _rc

    fake = _RecordingRedis()

    async def _get_client():
        return fake

    monkeypatch.setattr(_rc, "get_shared_async_redis", _get_client)
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_MARKET_LOAD", "600")

    calls, builder = _build_counter()
    tier_sink: list = []

    async def _run():
        await pic.get_or_build("market_load", ("k",), builder)
        # A worker whose process-local tier is empty, 90s later. `_read_cross_worker`
        # ages on the envelope's WALL clock, so the gap has to be a wall-clock gap.
        pic.clear_shared_builds()
        real_time = pic.time.time
        monkeypatch.setattr(pic.time, "time", lambda: real_time() + 90.0)
        with pic.reuse_scope([], tier_sink):
            await pic.get_or_build("market_load", ("k",), builder)

    asyncio.run(_run())

    assert calls["n"] == 1, "the cold worker rebuilt an artifact that was still live"
    assert pic.SHARED_TIER_CROSS_WORKER in tier_sink, tier_sink


def test_a_promoted_entry_does_not_restart_its_own_ttl(monkeypatch):
    """An artifact must not outlive its TTL by being handed between workers.

    LAT-P221b found this while asking why 90s-spaced samples were sharing a
    60s artifact at all. `get_or_build` promoted an L2 read into L1 stamped
    `_clock()` — NOW — throwing away the age the L2 read had just measured
    against the envelope's `stored_wall`. So:

        t=0    worker A builds, publishes (EX = TTL+1)
        t=59   worker B promotes it — a legal read, age 59 <= 60
        t=119  worker B is STILL serving it from L1, age 60 by its own clock

    Twice the declared bound, silently, and it scales with the TTL: the whole
    point of `TTL_BY_NAMESPACE` is to size a TTL against its writers' cadence,
    which a 2x overrun makes meaningless. This test walks that exact timeline.
    """
    from app.utils import request_cache as _rc

    fake = _RecordingRedis()

    async def _get_client():
        return fake

    monkeypatch.setattr(_rc, "get_shared_async_redis", _get_client)

    ttl = 60.0
    wall = {"t": 10_000.0}
    mono = {"t": 500.0}
    calls, builder = _build_counter()
    monkeypatch.setattr(pic.time, "time", lambda: wall["t"])

    async def _run():
        # t=0 — worker A builds and publishes.
        await pic.get_or_build("market_load", ("k",), builder, ttl_s=ttl)

        # t=59 — worker B is cold and promotes the artifact out of Redis.
        pic.clear_shared_builds()
        wall["t"] += 59.0
        mono["t"] += 59.0
        await pic.get_or_build(
            "market_load", ("k",), builder, ttl_s=ttl, clock=lambda: mono["t"]
        )
        assert calls["n"] == 1, "the promotion itself did not happen"

        # t=119 — same worker, L1 only (Redis has aged out by `stored_wall`).
        # The artifact is 119s old against a 60s bound and MUST be rebuilt.
        wall["t"] += 60.0
        mono["t"] += 60.0
        await pic.get_or_build(
            "market_load", ("k",), builder, ttl_s=ttl, clock=lambda: mono["t"]
        )

    asyncio.run(_run())

    assert calls["n"] == 2, (
        "a promoted L1 entry served past 2x its TTL — the promotion restarted "
        "the clock instead of backdating to the build"
    )


# --------------------------------------------------------------------------
# the bar has to be REACHABLE, not just failed by the pre-state
# --------------------------------------------------------------------------


def _share_rate(ttl_s: float, spacing_s: float) -> float:
    """Share rate for a LONE reader arriving every `spacing_s`, TTL `ttl_s`.

    One arrival builds and publishes; every later arrival still inside the TTL
    reuses WITHOUT extending it (`get_or_build` republishes only on the build
    path, which is correct — staleness is bounded from the build, not from the
    last read). So the cycle is one build plus `k` reuses, where `k` is the
    number of arrivals strictly inside the TTL.
    """
    k = math.ceil(ttl_s / spacing_s) - 1
    return k / (k + 1)


def test_the_registered_bar_is_satisfiable_by_the_value_being_recommended():
    """The trap that has now voided FOUR bars in this program.

    LAT-P141/142's bar passed before its fix existed. LAT-P143's guardrail was
    narrower than ambient drift. LAT-P221's required ">60s spacing" for sample
    independence, which guaranteed every sample landed after the 60s artifact
    had expired — UNSATISFIABLE by construction, and nobody noticed until it
    had been measured twice. LAT-P221b's own clause (a) then failed the other
    way: its pre-state at 90s spacing measured 90.9% shared against a ">=80%"
    bar, so the clause could not discriminate at all (it was reading the
    promotion overrun this change removes — see the promotion test above).

    So this pins the arithmetic rather than leaving it in a report. At a 90s
    sampling cadence a TTL merely LARGER than 90s is not enough: a lone
    reader's share rate is k/(k+1), so >=80% needs at least four reuses per
    build. The SHIPPED default (120s, staleness-neutral) cannot clear it, and
    is not trying to; 300s cannot either; 600s can. Ambient production traffic
    only helps — it must never be the reason a bar passes.
    """
    spacing = 90.0
    shipped = pic.TTL_BY_NAMESPACE["market_load"]
    assert _share_rate(shipped, spacing) < 0.80, (
        "the shipped default is chosen for staleness-neutrality, not to clear "
        "clause (a) — if it clears it, the bar has stopped discriminating again"
    )

    assert _share_rate(60.0, spacing) == 0.0, "the pre-state must FAIL the bar"
    assert _share_rate(120.0, spacing) < 0.80
    assert _share_rate(300.0, spacing) < 0.80, "a 5-minute TTL cannot reach ≥80%"
    assert _share_rate(600.0, spacing) >= 0.80, "the recommended value must REACH it"
