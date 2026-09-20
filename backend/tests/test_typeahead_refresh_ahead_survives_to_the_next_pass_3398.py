"""#3398 / LAT-P270 — the `fresh` skip may not drop an entry that then expires.

THE SHIP: the search box stops going cold on the terms people type most.

THE DEFECT, measured from the warmer's own ring (production `2629172a`, 32
passes / 1,233.7 s, `GET /api/admin/typeahead-warmer/last`):

    intervals between passes that actually REBUILT, against a 65 s TTL

        clean   30.0 30.0 30.0 30.0 30.0 30.1 30.2 30.4 31.0 31.0 33.7
                35.3 37.3 39.8 40.0 40.0 40.0 40.0 40.0 47.4 48.0 62.0
        loss    70.0 70.1 70.2 70.3 71.0 89.0 139.7

    max clean 62.0  <  TTL 65  <  min loss 70.0.  No overlap, n=31.

Five of those seven losses are `30 + 40`: a pass fired ~30 s after its
predecessor, called all 40 head entries `fresh`, rebuilt NOTHING, and so did
not restart the TTL clock. The next pass arrived 40 s later — 70 s after the
last real write — and found the entire head expired (`expired: 40`).

THE CLASS, and it is the reason this file is not just a constant assertion:
**a threshold argued in one module against a TTL owned by another goes stale
silently, and the test that pinned it went stale with it.** `REFRESH_AHEAD_
SECONDS = 35` was correct and provably inert against the 45 s TTL it was
argued against. The TTL became 65 (Fable GO ruling 4, 2026-08-19). The
constant did not move, its docstring still reasons from 45, and
`test_refresh_ahead_is_inert_at_every_reachable_period_and_that_is_stated`
hard-coded `ttl_s = 45` — so the guard that existed to catch exactly this
stayed green for a month while the skip it was guarding went live.

Every test below is therefore written to fail if a future edit re-introduces a
LITERAL anywhere in the chain, not merely if the number 35 comes back.
"""

import inspect
from unittest.mock import patch

import pytest

from app.tasks import typeahead_warmer as warmer
from app.utils import typeahead_beat_budget as budget

# The two production facts this file is allowed to quote, both from the ring
# read banked on #3398. The wall is carried as the RING wall, which is far
# smaller than the module's published `MEASURED_WALL_MAX_S` — used here to prove
# the verdict does not depend on which of the two is believed.
RING_WALL_MAX_S = 19.156
RING_PERIOD_MAX_S = 48.0
RING_MAX_CLEAN_REBUILD_INTERVAL_S = 62.0
RING_MIN_LOSING_REBUILD_INTERVAL_S = 70.0


class TestTheSkipCannotDropAnEntryThatExpires:
    """The behavioural half. Driven through `_warm_one`, not through arithmetic."""

    @pytest.mark.parametrize("ttl_before", [1, 17, 30, 35, 36, 48, 60, 64, 65])
    async def test_no_reachable_remaining_life_is_called_fresh(self, ttl_before):
        """At the shipped constants, NOTHING is `fresh`. Every reachable TTL.

        The parametrisation sweeps the whole reachable domain rather than
        picking a specimen, because the defect lived at 48 — a value no
        hand-chosen case would have thought to try, since the reasoning that
        set the threshold said an entry is observed with `ttl - period` = 35 s
        left and can never be above it.

        48 is in the list because it is what production actually showed: an
        entry written LATE in a 13 s pass and read EARLY in the next one is
        `65 - (30 - 13) = 48` s from death, comfortably "fresh" at 35.
        """
        from tests.test_typeahead_warmer import (
            _FakeRedis,
            _FakeSession,
            _ok_route,
            _patch_redis,
        )

        rc = _FakeRedis(ttls={warmer._CACHE_KEY_PREFIX + "red sox": ttl_before})

        with patch("app.routes.events.typeahead_search", _ok_route(rc)), _patch_redis(rc):
            result = await warmer._warm_one(_FakeSession(), "red sox")

        assert result["reason"] != "fresh", (
            f"an entry with {ttl_before}s of life was skipped as `fresh`. A skip "
            f"writes nothing, so the next write is a whole pass later — up to "
            f"{RING_PERIOD_MAX_S + RING_WALL_MAX_S:g}s — and the entry dies first. "
            f"This is #3398: it is how 5 of 7 total-head losses happened."
        )
        assert result["rebuilt"] is True

    async def test_the_production_specimen_that_broke_it_rebuilds_now_and_skipped_before(
        self,
    ):
        """The regression, pinned in BOTH directions on one specimen.

        Asserting only "48 rebuilds today" would pass against a warmer that had
        no skip at all and always rebuilt for some unrelated reason. The second
        half re-runs the SAME specimen at the old threshold and requires it to
        skip — so the test is provably measuring the threshold, and it fails if
        someone restores 35 or any other value below the survival floor.
        """
        from tests.test_typeahead_warmer import (
            _FakeRedis,
            _FakeSession,
            _ok_route,
            _patch_redis,
        )

        async def _run(refresh_ahead):
            rc = _FakeRedis(ttls={warmer._CACHE_KEY_PREFIX + "lakers": 48})
            with patch("app.routes.events.typeahead_search", _ok_route(rc)), _patch_redis(rc):
                return await warmer._warm_one(
                    _FakeSession(), "lakers", refresh_ahead=refresh_ahead
                )

        assert (await _run(warmer.REFRESH_AHEAD_SECONDS))["reason"] != "fresh"

        old = await _run(35)
        assert old["reason"] == "fresh", (
            "the old threshold no longer skips this specimen, so this test has "
            "stopped measuring the threshold and would pass on a warmer with no "
            "skip at all. Re-derive the specimen before trusting the arm above."
        )


class TestRetiringTheSkipDoesNotMakeTheInstrumentLie:
    """The hole this ship opened, closed in the same ship.

    With the skip retired, an entry at a FULL TTL reaches the write
    verification for the first time. That check is `ttl_after > ttl_before`,
    and the route rewrites to exactly the TTL — so `65 > 65` is false and a
    good write reported `no_write`, taking the whole pass to `partial`.
    """

    async def test_an_entry_already_at_a_full_ttl_reports_warmed_not_no_write(self):
        from tests.test_typeahead_warmer import (
            _FakeRedis,
            _FakeSession,
            _ok_route,
            _patch_redis,
        )

        ttl = budget.RESPONSE_CACHE_TTL_S
        rc = _FakeRedis(ttls={warmer._CACHE_KEY_PREFIX + "chiefs": ttl})

        with patch("app.routes.events.typeahead_search", _ok_route(rc, ttl=ttl)), _patch_redis(rc):
            result = await warmer._warm_one(_FakeSession(), "chiefs")

        assert result["reason"] == "warmed", (
            "a rewrite to a full TTL was read as a missing write. The pass goes "
            "`partial` over a cache that is perfectly warm — a false defect, "
            "which is worse than no instrument."
        )
        assert result["ok"] is True

    async def test_a_route_that_writes_nothing_is_still_caught(self):
        """The arm that keeps the arm above from being a hole.

        Widening the verification is only safe if the case it exists to catch —
        a route that serves from cache and writes nothing — still fails. Driven
        with a route that does not write, against an entry BELOW the ceiling.
        """
        from tests.test_typeahead_warmer import (
            _FakeRedis,
            _FakeSession,
            _ok_route,
            _patch_redis,
        )

        rc = _FakeRedis(ttls={warmer._CACHE_KEY_PREFIX + "bruins": 20})

        with patch("app.routes.events.typeahead_search", _ok_route(None)), _patch_redis(rc):
            result = await warmer._warm_one(_FakeSession(), "bruins")

        assert result["reason"] == "no_write"
        assert result["ok"] is False


class TestTheThresholdIsDerivedFromTheLiveTTL:
    """The arithmetic half — and the stale-input trap that caused #3398."""

    def test_the_shipped_constant_is_its_own_derivation(self):
        """No drift between the value and the rule that produces it.

        `REFRESH_AHEAD_SECONDS` is now an alias, so this cannot fail today
        without an edit — which is the point: it fails the moment someone
        replaces the alias with a literal, which is exactly what the last
        three cycles of this constant did.
        """
        assert warmer.REFRESH_AHEAD_SECONDS == budget.derive_refresh_ahead_s()
        assert budget.REFRESH_AHEAD_S == budget.derive_refresh_ahead_s()

    def test_the_derivation_reads_the_live_ttl_and_moves_when_it_moves(self):
        """🔴 THE ROOT CAUSE OF #3398, pinned directly.

        The old guard hard-coded `ttl_s = 45`. The TTL moved to 65 and the
        guard could not see it, so a threshold that had become unsafe kept
        passing. A derivation that ignores its TTL argument would satisfy every
        other test in this file; only this one catches it.
        """
        tight = budget.derive_refresh_ahead_s(
            ttl_s=65, period_max_s=RING_PERIOD_MAX_S, wall_max_s=RING_WALL_MAX_S
        )
        roomy = budget.derive_refresh_ahead_s(
            ttl_s=600, period_max_s=RING_PERIOD_MAX_S, wall_max_s=RING_WALL_MAX_S
        )
        assert tight != roomy, (
            "the derivation returns the same threshold at a 65s TTL and a 600s "
            "one, so it is not reading the TTL — which is the precise failure "
            "that let 35 survive the 45 -> 65 move"
        )
        assert tight == 65, "no safe threshold exists at 65s; ship the TTL (skip off)"
        assert roomy == 68, "a safe threshold exists at 600s; ship the floor (skip on)"

    def test_the_floor_is_the_period_PLUS_the_wall_and_varies_with_both(self):
        """The term whose absence made 35 look adequate is the pass wall.

        Parameterised and shown to vary, per this module's own lesson at
        `wall_max_exceeds_response_ttl()`: a bare constant comparison cannot
        distinguish a computed answer from a hard-coded one, so a mutation that
        returns a fixed number must be caught by the inputs moving the output.
        """
        assert budget.refresh_ahead_safe_floor_s(10.0, 5.0) == 15.0
        assert budget.refresh_ahead_safe_floor_s(20.0, 5.0) == 25.0, "period is live"
        assert budget.refresh_ahead_safe_floor_s(10.0, 9.0) == 19.0, "wall is live"

    def test_reachability_varies_with_both_of_its_inputs(self):
        assert budget.refresh_ahead_skip_is_reachable(30, ttl_s=65) is True
        assert budget.refresh_ahead_skip_is_reachable(65, ttl_s=65) is False
        assert budget.refresh_ahead_skip_is_reachable(30, ttl_s=30) is False

    def test_the_verdict_does_not_depend_on_which_wall_constant_is_believed(self):
        """Why this ship does not owe a re-derivation of `MEASURED_WALL_MAX_S`.

        The published wall (66.365 s, carrying an argued margin) and the wall
        this ring measured (19.156 s) disagree by a factor of three. Retiring
        the skip would be an unsafe call if the answer turned on that gap. It
        does not: both walls put the survival floor above the TTL.
        """
        for wall in (RING_WALL_MAX_S, budget.MEASURED_WALL_MAX_S):
            floor = budget.refresh_ahead_safe_floor_s(RING_PERIOD_MAX_S, wall)
            assert floor > budget.RESPONSE_CACHE_TTL_S, (
                f"at wall={wall}s the floor is {floor:g}s, which is BELOW the "
                f"{budget.RESPONSE_CACHE_TTL_S}s TTL — a safe threshold exists and "
                f"the skip should be live, not retired. Re-derive before shipping."
            )
        assert budget.REFRESH_AHEAD_SKIP_REACHABLE is False

    def test_the_measured_period_max_is_not_quantised_period_s(self):
        """The helper is right about its model and wrong for this input.

        `quantised_period_s` assumes the beat grid is aligned to pass starts.
        It is not, so the floor expires mid-beat and the pass waits a further
        whole beat. Substituting the helper here would derive a threshold from
        a period production does not have — the LAT-P062 failure one module
        over. Pinned so the substitution is a red test, not a plausible tidy-up.
        """
        predicted = budget.quantised_period_s(
            budget.CURRENT_BEAT_INTERVAL_S, RING_WALL_MAX_S, budget.MIN_PASS_PERIOD_S
        )
        assert predicted < budget.MEASURED_PERIOD_MAX_S, (
            f"quantised_period_s predicts {predicted:g}s and the ring measured "
            f"{budget.MEASURED_PERIOD_MAX_S:g}s. If these have converged the "
            f"measured constant may finally be substitutable — check, don't assume."
        )


class TestTheInstrumentSaysWhichZeroItIs:
    """gotcha #53: `fresh: 0` has two causes and they are different findings.

    "Nothing was due a rebuild" and "the skip cannot fire" print the same zero.
    #3398 is what that ambiguity cost — every reader of `fresh: 0`, including
    this module's own docstring, concluded the skip was inert while it was
    firing on 10 of 32 passes.
    """

    def test_both_summary_shapes_carry_the_reachability_flag(self):
        """The skip path and the real path, same keys — the same-keys contract.

        Read off the source rather than by running a pass, because the skip
        path needs a held lock and the real path needs a database; what is
        under test is that NEITHER shape can omit the field.
        """
        src = inspect.getsource(warmer)
        assert src.count('"refresh_ahead_skip_reachable": REFRESH_AHEAD_SKIP_REACHABLE') == 2, (
            "the flag must appear in BOTH the `_no_work` skip summary and the "
            "completed-pass summary — a field present on one shape and absent on "
            "the other makes a consumer branch on `terminal` to know if it exists"
        )
