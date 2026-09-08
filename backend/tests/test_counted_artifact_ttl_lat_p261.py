"""LAT-P261 (#3904) — a counted artifact may not spend the whole live ceiling.

THE DEFECT, IN ONE SENTENCE. LAT-P230 made shared-artifact age COUNT against the
#2216 live ceiling but never bounded how much of that ceiling one artifact may
eat, and the answer was *all of it*: `DEFAULT_TTL_S` is 60.0 and
`FEED_RESPONSE_STALE_TTL_LIVE_SECONDS` is 60. So at the end of every generation
of `concepts` / `canonical_counts` the headroom was zero, `routes/feed.py` took
the CERT-1864 refusal branch, and a fully-built page was thrown away.

WHAT THAT COST, measured on production 2026-09-08 09:12-10:02Z by forcing real
builds on a novel `limit` — a novel response-cache key, the same code path and
the same shared artifacts — and reading `cache.stale_ttl_seconds`, which for a
live payload IS `live_total_age_headroom_s()` of the oldest counted artifact::

    n=182 forced builds, live payload 182/182
    5 (2.7%) ->  X-Feed-Cache: unavailable, cache.reason: input_age_ceiling,
                 items: 0, total: 0, `total_age_ceiling` in X-Feed-Stages,
                 build_quality complete.   A BLANK DISCOVER FRONT PAGE.
                 `concepts` consumed on 5/5.
    51%      ->  artifact age above the bound this file guards.
    artifact age at the ceiling check: min 0s, p50 40s, p90 55s, max 60s.

Five events is small: read 2.7% as roughly 1-6%. The five establish that the
mechanism is real and user-visible, not how much of the rail's empty rate it
accounts for — see "what is NOT settled" below.

⚠️ THE INSTRUMENT HAS A TRAP AND IT CAUGHT ME ONCE. Read
`cache.stale_ttl_seconds`, never `cache.ttl_seconds`: the FRESH ttl carries a
second clamp, `FEED_RESPONSE_TTL_LIVE_SECONDS` (30), so it saturates and every
artifact younger than 30s reads back as exactly 30. A `60 - ttl_seconds` reading
of this same run reported a floor of 30s that does not exist —
`test_only_the_stale_ttl_carries_the_headroom` below pins the difference.

`build_quality` being *complete* is why this wore the wrong name for so long:
`_prewarm_feed_shape` classifies the refusal as `outcome: empty` and keeps
last-good — the same word it uses for a genuinely empty world.

⚠️ WHAT IS **NOT** SETTLED, stated here so nobody inherits it as established.
#3904 tabulated a 13-17% `empty` rate per shape per pass. This ship proves the
refusal mechanism is real, fires on production and produces those exact
symptoms; it does NOT prove the refusal is all of that 13-17%. The two rates are
not directly comparable — an isolated forced build samples one random moment,
while a rail pass builds five shapes concurrently off the SAME artifacts twice
per artifact generation, which is also why #3904's empties clustered across
shapes far above chance (8 passes with 3 simultaneous empties against 1.8
expected). The honest position is a strong circumstantial case with a named,
measured mechanism. The post-deploy read decides it, and the `empty_reason`
field added alongside this ship is what will name any second cause.

WHAT THIS SHIP DOES AND DOES NOT DO. It does not touch the ceiling. #2216 and
CERT-1864 are unchanged and the refusal stays exactly as correct as it was — a
live page built from over-age inputs must still not be served. What changes is
that the system stops MANUFACTURING the condition that trips it. The bound is
derived from constants that already exist and are already guarded, so the next
person to move `FEED_LIVE_REPUBLISH_BUDGET_S` or the ceiling gets a red test
rather than a slow return of blank front pages.

🔴 THE SYMMETRY IS THE INVARIANT, and it is what the next reader should keep: a
namespace either has its age counted against the live ceiling, in which case its
TTL must fit under that ceiling with room for the build that consumes it, or its
age is not counted, in which case its own cadence bounds it. Adding a namespace
to `LIVENESS_INERT_NAMESPACES` and giving it a long TTL is coherent. Adding one
that is counted and giving it a long TTL is the defect above, and
`test_every_counted_namespace_fits_under_the_ceiling` is what catches it.
"""

from __future__ import annotations

import math

import pytest

from app.utils import feed_cache as fc
from app.utils import principal_independent_cache as pic


#: Every namespace `get_or_build` is actually called with, from the three call
#: sites in `routes/feed.py`. Spelled out rather than discovered, so ADDING a
#: shared artifact is a decision someone makes here on purpose.
COUNTED_NAMESPACES = ("concepts", "canonical_counts")
INERT_NAMESPACES = ("market_load",)


class TestTheBoundIsDerivedNotChosen:
    def test_the_bound_is_the_ceiling_minus_the_budget_minus_the_rounding(self):
        assert pic.live_artifact_ttl_ceiling_s() == (
            fc.FEED_RESPONSE_STALE_TTL_LIVE_SECONDS
            - fc.FEED_LIVE_REPUBLISH_BUDGET_S
            - pic._LIVE_CEILING_ROUNDING_RESERVE_S
        )

    def test_it_leaves_room_for_the_longest_build_the_rail_permits(self):
        """The whole point: budget-long build + max-age artifact still publishes.

        `_prewarm_feed_shape` runs the route under
        `wait_for(timeout=FEED_LIVE_REPUBLISH_BUDGET_S)`, so this is the worst
        case that can reach the ceiling check at all.
        """
        worst_case_age = (
            pic.live_artifact_ttl_ceiling_s() + fc.FEED_LIVE_REPUBLISH_BUDGET_S
        )
        assert fc.live_total_age_headroom_s(worst_case_age) > 0

    def test_the_rounding_reserve_is_worth_exactly_the_ceil(self):
        """`live_total_age_headroom_s` rounds the age UP, so the trigger is
        `age > CEILING - 1`, not `age >= CEILING`. One second, and it is real."""
        ceiling = fc.FEED_RESPONSE_STALE_TTL_LIVE_SECONDS
        assert fc.live_total_age_headroom_s(ceiling - 1.0) > 0
        assert fc.live_total_age_headroom_s(ceiling - 0.9) == 0
        assert pic._LIVE_CEILING_ROUNDING_RESERVE_S == math.ceil(0.9)

    def test_it_is_shorter_than_the_default_it_replaces(self):
        assert pic.live_artifact_ttl_ceiling_s() < pic.DEFAULT_TTL_S

    def test_only_the_stale_ttl_carries_the_headroom(self):
        """The instrument trap, pinned so the next reader does not repeat it.

        Whoever measures this from outside reads `cache.*` off a forced build.
        The FRESH ttl is `min(headroom, FEED_RESPONSE_TTL_LIVE_SECONDS)` and so
        saturates at 30 — two artifacts 30 seconds apart in age report the same
        number. The STALE ttl is `min(headroom, CEILING)` and, because the
        ceiling IS the headroom's own maximum, it is the headroom exactly.
        """
        saturating, honest = fc.feed_response_cache_ttls(
            live=True, oldest_artifact_age_s=0.0
        )
        assert saturating == fc.FEED_RESPONSE_TTL_LIVE_SECONDS
        assert honest == fc.FEED_RESPONSE_STALE_TTL_LIVE_SECONDS

        for age in (0.0, 5.0, 25.0, 29.0):
            fresh, stale = fc.feed_response_cache_ttls(
                live=True, oldest_artifact_age_s=age
            )
            assert fresh == fc.FEED_RESPONSE_TTL_LIVE_SECONDS, "fresh saturates"
            assert stale == fc.live_total_age_headroom_s(age), "stale does not"


class TestEveryCountedNamespaceFitsUnderTheCeiling:
    """The bar. This is the test the next long TTL is not allowed to break."""

    @pytest.mark.parametrize("namespace", COUNTED_NAMESPACES)
    def test_every_counted_namespace_fits_under_the_ceiling(self, namespace):
        assert pic.live_artifact_ttl_headroom_s(namespace) >= 0

    @pytest.mark.parametrize("namespace", COUNTED_NAMESPACES)
    def test_a_counted_namespace_can_never_reach_zero_headroom(self, namespace):
        """Restated as the thing a user sees: the build is not refused.

        Asserted through the real headroom function rather than by comparing
        two numbers, so it stays true if the ceiling arithmetic is ever changed
        somewhere other than here.
        """
        oldest = pic.shared_build_ttl_s(namespace) + fc.FEED_LIVE_REPUBLISH_BUDGET_S
        assert fc.live_total_age_headroom_s(oldest) > 0

    @pytest.mark.parametrize("namespace", COUNTED_NAMESPACES)
    def test_the_counted_set_is_what_the_clamp_keys_on(self, namespace):
        """A namespace counted by `_note_age` is a namespace clamped here.
        The two must never be decided from different lists."""
        assert namespace not in pic.LIVENESS_INERT_NAMESPACES
        assert pic.shared_build_ttl_s(namespace) <= pic.live_artifact_ttl_ceiling_s()

    @pytest.mark.parametrize("namespace", INERT_NAMESPACES)
    def test_an_inert_namespace_is_deliberately_not_clamped(self, namespace):
        """Clamping an artifact whose age nobody counts would undo LAT-P230's
        ship and buy no correctness at all."""
        assert namespace in pic.LIVENESS_INERT_NAMESPACES
        assert pic.shared_build_ttl_s(namespace) > pic.live_artifact_ttl_ceiling_s()
        assert pic.live_artifact_ttl_headroom_s(namespace) == float("inf")

    def test_market_loads_ship_survived_this_one(self):
        """LAT-P230's ship, asserted from this file too — the two changes pull in
        opposite directions and a future edit could satisfy one by breaking the
        other."""
        assert pic.shared_build_ttl_s("market_load") == 120.0
        assert pic.market_load_ttl_headroom_s() >= 0


class TestTheOldBehaviourFailsThisBar:
    """The negative control. Without it, every assertion above could be passing
    for a reason that has nothing to do with the repair (a positive control can
    pass for the wrong reason)."""

    def test_the_shipped_defect_would_be_caught(self):
        """`concepts` at `DEFAULT_TTL_S` is what production was running, and it
        refuses with a build of ZERO seconds — never mind the budget."""
        assert pic.DEFAULT_TTL_S == 60.0
        assert fc.live_total_age_headroom_s(pic.DEFAULT_TTL_S) == 0
        assert (
            pic.live_artifact_ttl_ceiling_s() - pic.DEFAULT_TTL_S
        ) < 0, "the pre-LAT-P261 TTL must violate the bound this file adds"

    def test_the_refusal_branch_still_triggers_on_an_over_age_input(self):
        """The ceiling is NOT weakened. If this ever goes green the ship has been
        implemented by loosening #2216 instead of by bounding the input."""
        assert fc.live_total_age_headroom_s(9_999.0) == 0
        fresh, stale = fc.feed_response_cache_ttls(
            live=True, oldest_artifact_age_s=9_999.0
        )
        assert (fresh, stale) == (0, 0)


class TestTheClampIsAClampAndNotAPreference:
    def test_the_kill_switch_still_outranks_it(self, monkeypatch):
        monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "0")
        for namespace in COUNTED_NAMESPACES + INERT_NAMESPACES:
            assert pic.shared_build_ttl_s(namespace) == 0.0

    def test_an_operator_may_still_shorten(self, monkeypatch):
        """Every lever that made things SAFER has to keep working."""
        monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_CONCEPTS", "5")
        assert pic.shared_build_ttl_s("concepts") == 5.0

    def test_an_operator_cannot_lengthen_past_the_bound(self, monkeypatch):
        """…and the one that would bring blank front pages back does not.

        This is the whole reason the clamp sits over the precedence table
        instead of inside it as a sixth level.
        """
        monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_CONCEPTS", "300")
        assert pic.shared_build_ttl_s("concepts") == pic.live_artifact_ttl_ceiling_s()
        assert pic.live_artifact_ttl_headroom_s("concepts") >= 0

    def test_an_explicit_global_cannot_lengthen_a_counted_namespace(
        self, monkeypatch
    ):
        monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "300")
        assert pic.shared_build_ttl_s("concepts") == pic.live_artifact_ttl_ceiling_s()
        # …but it still binds where no correctness bound is at stake.
        assert pic.shared_build_ttl_s("market_load") == 300.0

    def test_an_unparseable_value_still_falls_through(self, monkeypatch):
        """A typo must not read as zero, and must not escape the clamp either."""
        monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_CONCEPTS", "ninety")
        assert pic.shared_build_ttl_s("concepts") == pic.live_artifact_ttl_ceiling_s()

    def test_the_process_wide_value_is_not_clamped(self):
        """`clock_bucket_s()` asks this question and is not asking about an
        artifact's life. Clamping it would move a key-rotation width for no
        reason — and `CLOCK_BUCKET_S` dominates it anyway."""
        assert pic.shared_build_ttl_s() == pic.DEFAULT_TTL_S
        assert pic.clock_bucket_s() == float(pic.CLOCK_BUCKET_S)


class TestSharingItselfSurvivesTheShorterTtl:
    """The cost side. A bound that silently turned the share off would be a
    latency regression wearing a correctness fix's clothes."""

    @pytest.mark.parametrize("namespace", COUNTED_NAMESPACES)
    def test_the_live_rail_reconsumes_well_inside_the_ttl(self, namespace):
        """The rail alone consumes these every `FEED_LIVE_REPUBLISH_PERIOD_S`, so
        every generation is still shared many times before it expires. This is
        the reason the ~1.5x rebuild cost is affordable, stated as arithmetic."""
        assert fc.FEED_LIVE_REPUBLISH_PERIOD_S < pic.shared_build_ttl_s(namespace)

    @pytest.mark.parametrize("namespace", COUNTED_NAMESPACES)
    def test_the_key_never_rotates_faster_than_the_ttl(self, namespace):
        """LAT-P104's property, re-checked against the shorter TTL: a key that
        rotated faster would discard entries that are still fresh."""
        assert pic.clock_bucket_s() >= pic.shared_build_ttl_s(namespace)

    @pytest.mark.parametrize("namespace", COUNTED_NAMESPACES)
    def test_sharing_is_not_switched_off(self, namespace):
        assert pic.shared_build_ttl_s(namespace) > 0


class TestTheRailSaysWhyItWasEmpty:
    """The observability half. `outcome: empty` with no reason is why this took
    three queues to name — the rail could not tell "the world is empty" from "we
    built a good page and declined to serve it"."""

    @staticmethod
    def _empty_branch(payload: dict) -> dict:
        """Run `_prewarm_feed_shape`'s empty branch against a payload.

        Reproduced rather than invoked: the real function needs a DB session, a
        route call and a Redis client, none of which this claim depends on. The
        assertion below pins that the SHAPE of what it returns carries the
        reason, and `test_the_refusal_payload_is_shaped_as_assumed` pins that the
        route really stamps the field being read.
        """
        cache_meta = payload.get("cache")
        reason = cache_meta.get("reason") if isinstance(cache_meta, dict) else None
        status = cache_meta.get("status") if isinstance(cache_meta, dict) else None
        return {"outcome": "empty", "empty_reason": reason, "cache_status": status}

    def test_a_refusal_is_reported_as_a_refusal(self):
        refused = {
            "items": [],
            "cache": fc.build_feed_cache_metadata(
                "unavailable",
                ttl_seconds=0,
                stale_ttl_seconds=0,
                reason="input_age_ceiling",
                live=True,
            ),
        }
        out = self._empty_branch(refused)
        assert out["outcome"] == "empty"
        assert out["empty_reason"] == "input_age_ceiling"
        assert out["cache_status"] == "unavailable"

    def test_a_genuinely_empty_world_is_still_distinguishable(self):
        """The other side of the same coin: no reason means no refusal, and a
        successor must be able to tell that apart rather than assume."""
        out = self._empty_branch({"items": [], "cache": {"status": "miss"}})
        assert out["empty_reason"] is None
        assert out["cache_status"] == "miss"

    def test_a_payload_with_no_cache_block_does_not_raise(self):
        """It runs on a beat and must never raise; a missing block reads as
        unknown, not as a crash."""
        assert self._empty_branch({"items": []})["empty_reason"] is None
        assert self._empty_branch({"items": [], "cache": None})["empty_reason"] is None

    def test_the_refusal_payload_is_shaped_as_assumed(self):
        """The load-bearing coupling: the reader above is only correct if the
        route really stamps `reason` on the refusal it returns. Read from the
        same constructor `routes/feed.py` uses."""
        meta = fc.build_feed_cache_metadata(
            "unavailable",
            ttl_seconds=0,
            stale_ttl_seconds=0,
            reason="input_age_ceiling",
            live=True,
        )
        assert meta["status"] == "unavailable"
        assert meta["reason"] == "input_age_ceiling"

    def test_the_rail_reads_the_reason_it_is_given(self):
        """Anchored to the production source, so deleting the field from
        `_prewarm_feed_shape` fails HERE and not only in a post-deploy read."""
        import inspect

        from app.tasks import precompute_category_pages as pcp

        source = inspect.getsource(pcp._prewarm_feed_shape)
        assert '"empty_reason"' in source, (
            "the rail stopped carrying the empty reason; #3904's instrument is "
            "blind again"
        )
        assert '"cache_status"' in source
