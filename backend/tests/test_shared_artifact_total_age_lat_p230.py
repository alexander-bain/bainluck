"""LAT-P230 (#3144) — the artifact outlives the minute, and the payload still tells the truth.

TWO HALVES, AND THEY MUST HOLD TOGETHER.

**Half A — the artifact stopped dying halfway through its own key's life.**
Three layers all expired on the same 60-second boundary: the anonymous response
TTL, ``CANDIDATE_BASE_FRESH_SECONDS``, and the shared-artifact TTL. A reader who
crossed it found all three cold at once. But the artifact's KEY lives longer than
that — ``market_load``'s key is a membership digest of the candidate base, which
is republished every 120s — so the second half of every key generation was thrown
away.

Measured in production 2026-09-05 by the LAT-P229 gap sweep, reading
``x-feed-shared`` as a LIST rather than a boolean::

    concepts         : shared 5/5   cross_worker every time
    canonical_counts : shared 0/5
    market_load      : shared 0/5

    gap  10s: market_load shared 1/1    B elapsed p50 2,632 ms
    gap  45s: market_load shared 4/4    (0 pairs dropped)
    gap  75s: market_load shared 0/2    B elapsed p50 5,140 ms

Sharing works to 45s and fails by 75s with the 60s TTL between them — the TTL
signature. It also refutes key rotation: a churning digest could not have gone
4/4 at a 45s gap. The stop is BRACKETED, not located; nothing here should quote
an effective life more precise than "between 45 and 75 seconds".

**Half B — the payload's age stopped being uncountable.**
``feed_response_cache_ttls()`` could see how long a RESPONSE would be cached and
not how old the shared artifacts it was built from already were. Those two ages
ADD. That is #2236's shape exactly — two individually-correct numbers whose
PRODUCT nobody computed — and raising Half A without Half B walks straight
through the #2216 live ceiling.

WHY BOTH ARE IN ONE FILE: shipping Half A alone is a latency win that quietly
loosens a correctness bound. The bar this file enforces is that it CANNOT be
done, because the test that proves the ceiling holds lives beside the test that
proves the TTL rose.

**A stale price on a live card outranks any latency win.** If the two ever
conflict, Half B wins and Half A gets smaller.
"""

from __future__ import annotations

import time

import pytest

from app.utils import feed_cache as fc
from app.utils import principal_independent_cache as pic

# ==========================================================================
# Half A — the TTL is DERIVED, and its derivation is pinned to the real beat
# ==========================================================================


class TestTheTtlIsDerivedNotChosen:
    def test_market_load_ttl_respects_its_ceiling(self):
        """The LAT-P230 invariant. Negative headroom means it is violated."""
        assert pic.market_load_ttl_headroom_s() >= 0, (
            "market_load's TTL exceeds the tighter of the candidate-base "
            "republish period and the live-market poll period. Past that, a "
            "longer TTL holds entries whose key has rotated — and against a "
            f"{pic.max_entries_for('market_load')}-entry cap it EVICTS live "
            "ones. Lower the TTL or re-derive the ceiling; do not raise the cap."
        )

    def test_the_ceiling_is_the_tighter_of_the_two_cadences(self):
        assert pic.market_load_ttl_ceiling_s() == min(
            pic.CANDIDATE_BASE_REPUBLISH_PERIOD_S, pic.LIVE_MARKET_POLL_PERIOD_S
        )

    def test_the_declared_candidate_base_cadence_matches_the_real_beat(self):
        """#2236 was a 120 in one file and a 60 in another with nothing comparing
        them. A comment would rebuild that arrangement; this reads the schedule.
        """
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["precompute-discover-candidate-base"]
        schedule = entry["schedule"]
        # A crontab, so the period is derived from the minute field rather than
        # read off a float. `*/2` -> fires on 30 of the 60 minutes in an hour.
        fired_minutes = sorted(schedule.minute)
        assert len(fired_minutes) == 30, (
            "precompute-discover-candidate-base no longer fires every 2 minutes; "
            f"it fires on {len(fired_minutes)} minutes per hour. "
            "CANDIDATE_BASE_REPUBLISH_PERIOD_S must move with it."
        )
        implied_period_s = 3600.0 / len(fired_minutes)
        assert implied_period_s == pic.CANDIDATE_BASE_REPUBLISH_PERIOD_S, (
            f"the beat fires every {implied_period_s}s but "
            f"CANDIDATE_BASE_REPUBLISH_PERIOD_S says "
            f"{pic.CANDIDATE_BASE_REPUBLISH_PERIOD_S}s"
        )

    def test_the_declared_market_poll_cadence_matches_the_real_beat(self):
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["poll-live-prediction-markets"]
        assert float(entry["schedule"]) == pic.LIVE_MARKET_POLL_PERIOD_S, (
            "poll_live_prediction_markets' cadence moved; "
            "LIVE_MARKET_POLL_PERIOD_S must move with it, and "
            "market_load's TTL may have to come down."
        )

    def test_the_base_is_never_fresh_longer_than_the_beat_that_refreshes_it(self):
        """ITEM 2b: the cadence the TTL leans on gets the same treatment.

        A base labelled `fresh` for longer than its own republish period would
        mean the beat can never be what keeps it fresh — #2236's shape again.
        """
        from app.utils.candidate_base import candidate_base_refresh_headroom_s

        assert candidate_base_refresh_headroom_s() >= 0

    def test_the_ttl_actually_rose_above_the_process_default(self):
        """The ship itself: `market_load` outlives the 60s boundary that killed it."""
        assert pic.shared_build_ttl_s("market_load") > pic.DEFAULT_TTL_S
        assert pic.shared_build_ttl_s("market_load") == 120.0

    def test_the_75_second_gap_that_failed_in_production_now_fits(self):
        """The pre-registered treated prediction, as an arithmetic fact.

        Production measured `market_load` sharing at a 45s gap and not at 75s.
        Sharing at gap G requires G < TTL, so this is the half of the prediction
        that does not need a dyno. The other half — that the KEY also survives 75s
        — is only measurable in production and is owed as the treated gap curve.
        """
        assert pic.shared_build_ttl_s("market_load") > 75.0


class TestTheTtlLeverBehavesLikeALever:
    def test_other_namespaces_are_untouched(self):
        assert pic.shared_build_ttl_s("concepts") == pic.DEFAULT_TTL_S
        assert pic.shared_build_ttl_s("canonical_counts") == pic.DEFAULT_TTL_S
        assert pic.shared_build_ttl_s() == pic.DEFAULT_TTL_S

    def test_the_kill_switch_stays_absolute(self, monkeypatch):
        """A per-namespace default that could outlive the kill switch would mean
        the one lever that turns sharing off no longer turns sharing off.
        """
        monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "0")
        assert pic.shared_build_ttl_s("market_load") == 0.0
        assert pic.shared_build_ttl_s("concepts") == 0.0
        assert pic.shared_build_ttl_s() == 0.0

    def test_the_kill_switch_beats_even_a_per_namespace_override(self, monkeypatch):
        monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "0")
        monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_MARKET_LOAD", "300")
        assert pic.shared_build_ttl_s("market_load") == 0.0

    def test_a_per_namespace_override_binds(self, monkeypatch):
        monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_MARKET_LOAD", "45")
        assert pic.shared_build_ttl_s("market_load") == 45.0
        assert pic.shared_build_ttl_s("concepts") == pic.DEFAULT_TTL_S

    def test_an_explicit_global_binds_a_namespace_with_a_builtin_default(
        self, monkeypatch
    ):
        """An operator who sets the global expects it to bind. A built-in that
        quietly outranked it would be a lever that lies.
        """
        monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "90")
        assert pic.shared_build_ttl_s("market_load") == 90.0

    def test_an_unparseable_value_falls_through_rather_than_disabling(
        self, monkeypatch
    ):
        """A typo must not read as zero — that would silently kill the cache."""
        monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S_MARKET_LOAD", "ninety")
        assert pic.shared_build_ttl_s("market_load") == 120.0
        monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "banana")
        assert pic.shared_build_ttl_s("market_load") == 120.0
        assert pic.shared_build_ttl_s() == pic.DEFAULT_TTL_S


# ==========================================================================
# Half B — THE TRUTH BAR. Artifact age and response age ADD.
# ==========================================================================


class TestTheTotalServedAgeCannotExceedTheLiveCeiling:
    """The non-negotiable bar. This is the test Half A is not allowed to break."""

    @pytest.mark.parametrize(
        "artifact_age_s",
        [0.0, 1.0, 15.0, 29.0, 30.0, 31.0, 45.0, 59.0, 59.9, 60.0, 61.0, 120.0, 600.0],
    )
    @pytest.mark.parametrize("identified", [False, True])
    @pytest.mark.parametrize("my_teams_only", [False, True])
    def test_artifact_age_plus_response_age_stays_under_the_ceiling(
        self, artifact_age_s, identified, my_teams_only
    ):
        fresh, stale = fc.feed_response_cache_ttls(
            my_teams_only=my_teams_only,
            identified=identified,
            live=True,
            oldest_artifact_age_s=artifact_age_s,
        )
        ceiling = fc.FEED_RESPONSE_STALE_TTL_LIVE_SECONDS
        # THE BAR, stated exactly. `stale` is the longest a reader can still be
        # served this payload FROM CACHE, so it is the term the clamp controls.
        #
        # `min(age, ceiling)` and not `age`, because once the inputs alone have
        # spent the whole ceiling there is no cache extension left to shorten —
        # the clamp drives `stale` to 0 and the payload is never cached, so no
        # SECOND reader is ever served it. Writing the bar as
        # `age + stale <= ceiling` would be unsatisfiable in that regime and
        # would be a guard that can only be passed by deleting it.
        assert min(artifact_age_s, ceiling) + stale <= ceiling + 1e-9, (
            f"a live payload built from a {artifact_age_s}s-old artifact would be "
            f"cached a further {stale}s — {artifact_age_s + stale}s total against "
            f"a {ceiling}s ceiling. #2216: past the ceiling the page is REBUILT, "
            f"not served older."
        )
        assert min(artifact_age_s, ceiling) + fresh <= ceiling + 1e-9
        assert fresh <= stale

        # And the regime boundary itself: inputs at or past the ceiling buy the
        # response exactly zero cache life.
        if artifact_age_s >= ceiling:
            assert (fresh, stale) == (0, 0)

    def test_inputs_that_have_spent_the_whole_ceiling_are_not_cached_at_all(self):
        """Headroom 0 means the next reader REBUILDS rather than being served older."""
        fresh, stale = fc.feed_response_cache_ttls(
            live=True, oldest_artifact_age_s=fc.FEED_RESPONSE_STALE_TTL_LIVE_SECONDS
        )
        assert (fresh, stale) == (0, 0)

    def test_the_headroom_function_never_goes_negative(self):
        assert fc.live_total_age_headroom_s(10_000.0) == 0
        assert fc.live_total_age_headroom_s(-5.0) == (
            fc.FEED_RESPONSE_STALE_TTL_LIVE_SECONDS
        )

    def test_the_term_can_only_ever_shorten(self):
        """The #2216 discipline: a ceiling that LENGTHENED a cache would be a
        latency fix wearing a correctness fix's clothes.
        """
        for age in (0.0, 5.0, 30.0, 90.0):
            with_age = fc.feed_response_cache_ttls(live=True, oldest_artifact_age_s=age)
            without = fc.feed_response_cache_ttls(live=True)
            assert with_age[0] <= without[0]
            assert with_age[1] <= without[1]

    def test_a_non_live_payload_is_untouched(self):
        """The ceiling is a bound on live cards. A futures-only page keeps its TTL."""
        assert fc.feed_response_cache_ttls(
            live=False, oldest_artifact_age_s=119.0
        ) == fc.feed_response_cache_ttls(live=False)

    def test_the_default_keeps_every_existing_caller_byte_identical(self):
        """An un-updated call site must be conservative, never wrong."""
        for live in (False, True):
            for identified in (False, True):
                for mto in (False, True):
                    assert fc.feed_response_cache_ttls(
                        my_teams_only=mto, identified=identified, live=live
                    ) == fc.feed_response_cache_ttls(
                        my_teams_only=mto,
                        identified=identified,
                        live=live,
                        oldest_artifact_age_s=0.0,
                    )


class TestTheOldBehaviourFailsThisBar:
    """Red-first: the pre-LAT-P230 arithmetic violates the bar it now passes."""

    def test_ignoring_artifact_age_breaks_the_ceiling(self):
        ceiling = fc.FEED_RESPONSE_STALE_TTL_LIVE_SECONDS
        artifact_age = 59.0

        # What the code did before: the live ceiling applied to the response age
        # alone, with the artifact's age uncounted.
        old_stale = min(fc.FEED_RESPONSE_STALE_TTL_SECONDS, ceiling)
        assert artifact_age + old_stale > ceiling, (
            "this test no longer reproduces the defect it guards — the old "
            "arithmetic must exceed the ceiling for the new one to be a fix"
        )

        # What it does now.
        _, new_stale = fc.feed_response_cache_ttls(
            live=True, oldest_artifact_age_s=artifact_age
        )
        assert artifact_age + new_stale <= ceiling


# ==========================================================================
# The instrument itself — an age that never reaches the reader is not a term
# ==========================================================================


class TestTheAgeSinkActuallyCollects:
    """A guard against the "both ends green, ship dead" class: the arithmetic
    above is worthless if nothing ever feeds it a non-zero age."""

    def test_the_oldest_of_several_artifacts_wins(self):
        """MAX, not mean — a payload is only as fresh as its stalest input.

        The sink holds ORIGINS since CERT-1862, so "oldest" is the EARLIEST
        origin; the ages are reconstructed from `monotonic()` at read time.
        """
        now = time.monotonic()
        origins = [now - 0.0, now - 55.0, now - 3.0]
        assert pic.oldest_consumed_artifact_age_s(origins) == pytest.approx(
            55.0, abs=1.0
        )

    def test_the_recorded_age_keeps_growing_after_consumption(self, monkeypatch):
        """CERT-1862's falsifier: consumption is early, the ceiling is applied late.

        A sink that stored the age observed at consumption froze it there, so a
        20-second build was invisible and the ceiling was applied to a number
        that was already 20 seconds out of date. The exact figures the cert
        reproduced: consumed at 50s, 20s of build, still read 50s, and a live
        payload went out at 79s true age against a 60s ceiling.
        """
        fake = {"t": 1000.0}
        monkeypatch.setattr(pic.time, "monotonic", lambda: fake["t"])

        sink: list[float] = []
        with pic.reuse_scope([], [], sink):
            pic._note_age(50.0)  # consumed a 50s-old artifact, at t=1000

        assert pic.oldest_consumed_artifact_age_s(sink) == pytest.approx(50.0)

        fake["t"] = 1020.0  # ...and the build then took 20 seconds
        assert pic.oldest_consumed_artifact_age_s(sink) == pytest.approx(70.0), (
            "the artifact's age did not grow with the build — the sink froze "
            "the age observed at consumption instead of storing an origin "
            "(CERT-1862)"
        )

        # …and the consequence: at 70s there is no ceiling left to spend.
        assert fc.feed_response_cache_ttls(live=True, oldest_artifact_age_s=70.0) == (
            0,
            0,
        )

    def test_no_artifacts_consumed_reads_as_zero(self):
        assert pic.oldest_consumed_artifact_age_s([]) == 0.0
        assert pic.oldest_consumed_artifact_age_s(None) == 0.0

    @pytest.mark.asyncio
    async def test_a_freshly_built_artifact_records_age_zero(self):
        """Recorded, not skipped — so an EMPTY sink means "consumed nothing" and
        not "the instrument was silent"."""
        pic.clear_shared_builds("lat_p230_probe")
        origins: list[float] = []
        with pic.reuse_scope([], [], origins):
            await pic.get_or_build(
                "lat_p230_probe", ("k",), _builder({"v": 1}), ttl_s=60.0
            )
        # One entry recorded (not silence), and it reads as brand new.
        assert len(origins) == 1
        assert pic.oldest_consumed_artifact_age_s(origins) == pytest.approx(
            0.0, abs=1.0
        )

    @pytest.mark.asyncio
    async def test_a_local_hit_records_the_age_it_had_already_spent(self):
        pic.clear_shared_builds("lat_p230_probe")
        clock = _FakeClock()
        await pic.get_or_build(
            "lat_p230_probe", ("k",), _builder({"v": 1}), ttl_s=120.0, clock=clock
        )
        clock.advance(47.0)

        origins: list[float] = []
        with pic.reuse_scope([], [], origins):
            await pic.get_or_build(
                "lat_p230_probe", ("k",), _builder({"v": 2}), ttl_s=120.0, clock=clock
            )
        assert pic.oldest_consumed_artifact_age_s(origins) == pytest.approx(
            47.0, abs=1.0
        )

    @pytest.mark.asyncio
    async def test_the_collected_age_is_what_shortens_the_ttl(self, monkeypatch):
        """End to end across the seam: a real cache read produces the term, and
        the term reaches the ceiling arithmetic. Testing the two ends separately
        is how a ship dies green at both ends.

        The monotonic clock is frozen because since CERT-1862 the age is
        re-derived at READ time, so the few hundred microseconds between the
        read and the assertion are now part of the answer — and 58.0s and
        58.0003s land on opposite sides of an integer TTL boundary. A guard
        whose result depends on how fast the box ran is a flake, not a bound
        (gotcha #44: a test anchor must not branch on the clock).
        """
        pic.clear_shared_builds("lat_p230_probe")
        frozen = {"t": 5_000.0}
        monkeypatch.setattr(pic.time, "monotonic", lambda: frozen["t"])

        clock = _FakeClock()
        await pic.get_or_build(
            "lat_p230_probe", ("k",), _builder({"v": 1}), ttl_s=120.0, clock=clock
        )
        clock.advance(58.0)

        origins: list[float] = []
        with pic.reuse_scope([], [], origins):
            await pic.get_or_build(
                "lat_p230_probe", ("k",), _builder({"v": 2}), ttl_s=120.0, clock=clock
            )

        fresh, stale = fc.feed_response_cache_ttls(
            live=True,
            oldest_artifact_age_s=pic.oldest_consumed_artifact_age_s(origins),
        )
        assert (fresh, stale) == (2, 2)


# ==========================================================================
# The exemption, GUARDED rather than asserted
# ==========================================================================


class TestMarketLoadCannotItselfAgeALivePrice:
    """Why raising ONLY `market_load`'s TTL is safe today — as a test, not a claim.

    `market_load` carries `FuturesMarket` rows. `FuturesMarket.status` takes
    `open` / `closed` / `resolved` / `active`; every ``status="live"`` write in
    the tree targets `Event.status`. A futures card's ``data["status"]`` is
    ``market.status``, and `_payload_has_live_card` reads exactly that key — so a
    `market_load`-derived card cannot make a payload live, and a 120s TTL cannot
    age a live price.

    That is a true sentence about TODAY'S data, which is exactly the kind of
    sentence that rots. So it is a guard: the day a futures card can render
    ``status == "live"``, this file goes red and whoever did it has to re-derive
    the TTL instead of discovering the problem in production.

    🔴 CERT-1856 — READ THIS BEFORE REUSING THIS ARGUMENT. Everything above is
    still true, and it is still too narrow to have concluded what LAT-P230
    concluded from it. This class answers "can `market_load` carry a live
    price?"; it does NOT answer "can any shared artifact whose age we subtract
    carry a live price?" — and `concepts` can, because `_score_event_concepts`
    copies a concept's ``status`` onto the card, ``live`` included. LAT-P230
    read the narrow answer as the broad one and declared the process-local
    last-good residual unreachable. It was reachable, on a shipping path, at
    118s against a 60s ceiling. The repair is in
    ``routes/feed.py`` (``_age_origin``) and its guard is
    ``test_feed_live_cache_ceiling.py::
    test_a_live_page_built_from_an_aged_artifact_gets_no_fresh_window``.
    The general lesson, which outlives this case: an exemption argued about ONE
    input is not an exemption for the mechanism that input travels through.
    """

    @pytest.mark.parametrize("status", ["open", "closed", "resolved", "active"])
    def test_a_futures_card_does_not_make_a_payload_live(self, status):
        payload = {"items": [{"type": "futures", "data": {"status": status}}]}
        assert fc.payload_contains_live_event(payload) is False

    def test_if_the_exemption_ever_breaks_the_clamp_still_catches_it(self):
        """The backstop, proven rather than assumed. If a futures card DID go
        live, the total-age clamp is what keeps it inside the ceiling — which is
        why Half B is not scoped to `market_load` and does not check a namespace.
        """
        payload = {"items": [{"type": "futures", "data": {"status": "live"}}]}
        assert fc.payload_contains_live_event(payload) is True

        _, stale = fc.feed_response_cache_ttls(
            live=fc.payload_contains_live_event(payload),
            oldest_artifact_age_s=119.0,
        )
        assert stale == 0

    def test_an_event_card_is_still_what_makes_a_payload_live(self):
        """The control: the clamp must not have made liveness undetectable."""
        payload = {"items": [{"type": "event", "data": {"status": "live"}}]}
        assert fc.payload_contains_live_event(payload) is True


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


class _FakeClock:
    """A monotonic clock we can advance. `get_or_build` takes `clock` for exactly
    this reason — a test that sleeps is a test that flakes."""

    def __init__(self, t: float = 1_000.0) -> None:
        self._t = t

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


def _builder(value):
    async def _build():
        return value

    return _build
