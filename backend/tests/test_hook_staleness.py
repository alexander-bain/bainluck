"""Tests for hook staleness detection (issue #455).

Covers:
- Fresh hooks pass through unchanged
- Leader change → stale
- Probability delta > 15pp → stale
- Hook age > 7 days → stale
- No hook → not stale (nothing to suppress)
- Missing generation metadata → stale (legacy row)
- Probability contradiction scenario from the original bug report
"""

from datetime import datetime, timedelta, timezone

from app.utils.hook_staleness import (
    CURRENT_HOOK_POLICY_VERSION,
    HOOK_POLICY_METADATA_KEY,
    HOOK_PROB_METADATA_KEY,
    STALE_HOOK_MAX_AGE_DAYS,
    STALE_PROBABILITY_DELTA,
    get_hook_probability_at_generation,
    hook_policy_version,
    is_hook_stale,
)


_NOW = datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc)

#: #5461 added a POLICY gate that is checked before every dimension below, so a
#: fixture without it is stale no matter what it was written to test. Every
#: fixture here therefore carries the current stamp and keeps isolating the one
#: dimension it was written for; the policy gate has its own class at the bottom.
_POLICY = {HOOK_POLICY_METADATA_KEY: CURRENT_HOOK_POLICY_VERSION}


class TestIsHookStale:
    """Core staleness detection tests."""

    def test_fresh_hook_not_stale(self):
        """A recently generated hook with same leader and close probability is not stale."""
        assert not is_hook_stale(
            hook_description="Netflix is riding a wave of subscriber growth after its latest earnings beat.",
            hook_generated_at=_NOW - timedelta(hours=6),
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.65,
            market_metadata={HOOK_PROB_METADATA_KEY: 0.63, **_POLICY},
            now=_NOW,
        )

    def test_no_hook_not_stale(self):
        """If there's no hook, there's nothing to suppress."""
        assert not is_hook_stale(
            hook_description=None,
            hook_generated_at=_NOW - timedelta(days=30),
            hook_leader_at_generation="Yes",
            current_leader_name="No",
            current_leader_probability=0.90,
            market_metadata=dict(_POLICY),
            now=_NOW,
        )

    def test_empty_hook_not_stale(self):
        """Empty string hook is treated as no hook."""
        assert not is_hook_stale(
            hook_description="",
            hook_generated_at=_NOW - timedelta(days=30),
            hook_leader_at_generation="Yes",
            current_leader_name="No",
            current_leader_probability=0.90,
            market_metadata=dict(_POLICY),
            now=_NOW,
        )

    def test_leader_change_is_stale(self):
        """When the market leader changes, the hook narrative is wrong."""
        assert is_hook_stale(
            hook_description="The Democrats are consolidating their lead in this critical race.",
            hook_generated_at=_NOW - timedelta(hours=12),
            hook_leader_at_generation="Democratic Party",
            current_leader_name="Republican Party",
            current_leader_probability=0.55,
            market_metadata={HOOK_PROB_METADATA_KEY: 0.60, **_POLICY},
            now=_NOW,
        )

    def test_probability_delta_exceeds_threshold(self):
        """Hook says 'surging to 65%' but probability dropped to 42% — stale."""
        assert is_hook_stale(
            hook_description="Netflix is surging on strong subscriber numbers.",
            hook_generated_at=_NOW - timedelta(hours=12),
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.42,
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65, **_POLICY},
            now=_NOW,
        )

    def test_probability_delta_just_under_threshold(self):
        """Probability moved 14pp — just under the 15pp threshold, not stale."""
        assert not is_hook_stale(
            hook_description="Netflix is riding subscriber growth momentum.",
            hook_generated_at=_NOW - timedelta(hours=12),
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.51,
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65, **_POLICY},
            now=_NOW,
        )

    def test_probability_delta_exactly_at_threshold(self):
        """Probability moved exactly 15pp — stale (>= check)."""
        assert is_hook_stale(
            hook_description="A tight race for the nomination.",
            hook_generated_at=_NOW - timedelta(hours=12),
            hook_leader_at_generation="Candidate A",
            current_leader_name="Candidate A",
            current_leader_probability=0.50,
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65, **_POLICY},
            now=_NOW,
        )

    def test_old_hook_is_stale(self):
        """Hooks older than 7 days are stale regardless of probability."""
        assert is_hook_stale(
            hook_description="The Fed is signaling a rate cut at its next meeting.",
            hook_generated_at=_NOW - timedelta(days=8),
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.65,
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65, **_POLICY},
            now=_NOW,
        )

    def test_hook_exactly_at_max_age_is_not_stale(self):
        """Hook at exactly max age boundary is not stale (< comparison)."""
        assert not is_hook_stale(
            hook_description="The Fed is signaling a rate cut at its next meeting.",
            hook_generated_at=_NOW - timedelta(days=STALE_HOOK_MAX_AGE_DAYS),
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.65,
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65, **_POLICY},
            now=_NOW,
        )

    def test_no_generation_timestamp_is_stale(self):
        """Legacy rows without hook_generated_at are treated as stale."""
        assert is_hook_stale(
            hook_description="Old hook from before we tracked generation time.",
            hook_generated_at=None,
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.65,
            market_metadata=dict(_POLICY),
            now=_NOW,
        )

    def test_no_gen_probability_metadata_not_stale_if_leader_same(self):
        """Without stored probability, we can't detect delta — don't suppress if leader matches."""
        assert not is_hook_stale(
            hook_description="A competitive race for the trophy.",
            hook_generated_at=_NOW - timedelta(hours=6),
            hook_leader_at_generation="Team A",
            current_leader_name="Team A",
            current_leader_probability=0.80,
            market_metadata=dict(_POLICY),
            now=_NOW,
        )

    def test_naive_datetime_comparison_works(self):
        """Timezone-naive hook_generated_at should still be handled."""
        naive_time = _NOW.replace(tzinfo=None) - timedelta(days=10)
        assert is_hook_stale(
            hook_description="Old hook with naive timestamp.",
            hook_generated_at=naive_time,
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.65,
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65, **_POLICY},
            now=_NOW,
        )

    def test_probability_rose_significantly(self):
        """Hook written when probability was 30%, now it's 55% — stale (25pp delta)."""
        assert is_hook_stale(
            hook_description="A long-shot candidate making waves.",
            hook_generated_at=_NOW - timedelta(hours=12),
            hook_leader_at_generation="Candidate X",
            current_leader_name="Candidate X",
            current_leader_probability=0.55,
            market_metadata={HOOK_PROB_METADATA_KEY: 0.30, **_POLICY},
            now=_NOW,
        )

    def test_custom_thresholds(self):
        """Custom max_age_days and probability_delta are respected."""
        # Should be stale with 3-day max age
        assert is_hook_stale(
            hook_description="A recent hook.",
            hook_generated_at=_NOW - timedelta(days=4),
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.65,
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65, **_POLICY},
            now=_NOW,
            max_age_days=3,
        )

        # Should be stale with 10pp delta threshold (12pp move)
        assert is_hook_stale(
            hook_description="A tight race.",
            hook_generated_at=_NOW - timedelta(hours=6),
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.53,
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65, **_POLICY},
            now=_NOW,
            probability_delta=0.10,
        )


class TestBugReportScenario:
    """BR47: Hook says 'Netflix surging to 65%' but probability is 42%."""

    def test_contradictory_hook_suppressed(self):
        """The exact scenario from the bug report."""
        stale = is_hook_stale(
            hook_description="Netflix is surging amid a wave of new original content and subscriber growth",
            hook_generated_at=_NOW - timedelta(hours=36),
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.42,
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65, **_POLICY},
            now=_NOW,
        )
        assert stale, "Hook should be suppressed when probability dropped 23pp"


class TestGetHookProbabilityAtGeneration:
    """Tests for reading stored generation probability from market_metadata."""

    def test_reads_probability(self):
        assert get_hook_probability_at_generation(
            {HOOK_PROB_METADATA_KEY: 0.65}
        ) == 0.65

    def test_returns_none_for_missing_key(self):
        assert get_hook_probability_at_generation({"other": "data"}) is None

    def test_returns_none_for_none_metadata(self):
        assert get_hook_probability_at_generation(None) is None

    def test_returns_none_for_non_dict(self):
        assert get_hook_probability_at_generation("not a dict") is None

    def test_handles_string_value(self):
        result = get_hook_probability_at_generation(
            {HOOK_PROB_METADATA_KEY: "0.75"}
        )
        assert result == 0.75


class TestNeedsRegeneration:
    """Tests for the enrichment task's regeneration logic."""

    def test_probability_delta_triggers_regen(self):
        """Enrichment task should re-enrich when probability moved 15+pp."""
        from app.tasks.enrich_markets import _needs_regeneration
        from unittest.mock import MagicMock

        market = MagicMock()
        market.hook_description = "An old hook."
        market.hook_generated_at = _NOW - timedelta(hours=6)
        market.hook_leader_at_generation = "Yes"
        market.market_metadata = {HOOK_PROB_METADATA_KEY: 0.65, **_POLICY}

        # Probability dropped 23pp — should trigger regen
        assert _needs_regeneration(market, "Yes", 0.42, _NOW)

    def test_small_probability_change_no_regen(self):
        """No regen when probability moved only 5pp within 24h."""
        from app.tasks.enrich_markets import _needs_regeneration
        from unittest.mock import MagicMock

        market = MagicMock()
        market.hook_description = "A recent hook."
        market.hook_generated_at = _NOW - timedelta(hours=6)
        market.hook_leader_at_generation = "Yes"
        market.market_metadata = {HOOK_PROB_METADATA_KEY: 0.65, **_POLICY}

        assert not _needs_regeneration(market, "Yes", 0.60, _NOW)


class TestRetiredPromptHooksAreSuppressedImmediately5461:
    """#5461 / CERT-2697's required repair: stopping the WRITER is not enough.

    The evidence gate shipped in `hook_prompt.should_generate_hook` stops the
    retired prompt writing any MORE invented lines. It does nothing about the
    1,076 hooks it had already written, every one of which was live on a card.
    Before this repair their only exit was `STALE_HOOK_MAX_AGE_DAYS` — so a fix
    that shipped on a Saturday would have been invisible to readers until the
    following Saturday, and for markets holding no citable evidence the gate
    also blocks the re-enrichment that would otherwise have replaced them.

    A production sample of what was being served while the countdown ran:
    *"Ella Langley's 'Choosin' Texas' has surged to the top of the Billboard
    Hot 100"*, *"Shake Shack is experiencing a notable surge in foot traffic
    this September"*. Nothing in our data says either thing.
    """

    def test_fresh_retired_prompt_hook_is_suppressed_on_first_serve_5461(self):
        """🔴 THE ONE THE BLOCK NAMED. Fresh by every other measure.

        Generated six hours ago, same leader, probability unmoved — checks 1, 2
        and 3 all pass it. Only the policy check can see that the RULES it was
        written under have been retired, which is why check 0 exists and why it
        runs first.
        """
        assert is_hook_stale(
            hook_description=(
                "Ella Langley's 'Choosin' Texas' has surged to the top of the "
                "Billboard Hot 100"
            ),
            hook_generated_at=_NOW - timedelta(hours=6),
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.65,
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65},
            now=_NOW,
        )

    def test_a_hook_written_minutes_ago_under_the_old_policy_is_still_suppressed(self):
        """Age is not the axis. One minute old and still retired."""
        assert is_hook_stale(
            hook_description="Shake Shack is experiencing a notable surge in foot traffic",
            hook_generated_at=_NOW - timedelta(minutes=1),
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.65,
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65},
            now=_NOW,
        )

    def test_a_current_policy_hook_survives(self):
        """The other direction, or the repair is just 'suppress every hook'."""
        assert not is_hook_stale(
            hook_description="The Chiefs play the Eagles on Sunday 14 September.",
            hook_generated_at=_NOW - timedelta(hours=6),
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.65,
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65, **_POLICY},
            now=_NOW,
        )

    def test_absent_metadata_entirely_is_retired_not_exempt(self):
        """`market_metadata=None` is the commonest legacy shape and must not
        slip through the gate by being unreadable rather than old."""
        assert is_hook_stale(
            hook_description="An unlabelled hook.",
            hook_generated_at=_NOW - timedelta(hours=1),
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.65,
            market_metadata=None,
            now=_NOW,
        )

    def test_the_219e_array_shaped_metadata_row_is_retired_not_crashed(self):
        """~369 production rows carry ARRAY metadata from a jsonb-concat gotcha
        (#219E). Those must read as policy 1, not raise inside the hot path of
        `GET /api/feed`."""
        assert is_hook_stale(
            hook_description="A hook on a malformed row.",
            hook_generated_at=_NOW - timedelta(hours=1),
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.65,
            market_metadata=[None, {"shape": {}}],
            now=_NOW,
        )

    def test_a_retired_hook_is_queued_for_rewrite_not_merely_hidden(self):
        """Suppression alone would leave the card wordless indefinitely. The
        regen gate's own `age_hours < 24` early return would actively hold a
        freshly-retired hook out of the queue for a day."""
        from unittest.mock import MagicMock

        from app.tasks.enrich_markets import _needs_regeneration

        market = MagicMock()
        market.hook_description = "A recent hook under the retired policy."
        market.hook_generated_at = _NOW - timedelta(hours=6)
        market.hook_leader_at_generation = "Yes"
        market.market_metadata = {HOOK_PROB_METADATA_KEY: 0.65}

        assert _needs_regeneration(market, "Yes", 0.65, _NOW)

    def test_the_policy_gate_is_read_before_the_age_gate(self):
        """Order, asserted behaviourally rather than by reading the source: a
        retired hook that is ALSO within the age window must still be stale. If
        the checks were reordered this passes anyway — but paired with the
        version reader's own tests it pins that no later check can rescue a
        retired hook."""
        for age in (timedelta(seconds=0), timedelta(days=1), timedelta(days=99)):
            assert is_hook_stale(
                hook_description="A hook.",
                hook_generated_at=_NOW - age,
                hook_leader_at_generation="Yes",
                current_leader_name="Yes",
                current_leader_probability=0.65,
                market_metadata={HOOK_PROB_METADATA_KEY: 0.65},
                now=_NOW,
            )


class TestHookPolicyVersionReader5461:
    """`hook_policy_version` — an unlabelled hook is not unknown, it is old."""

    def test_an_absent_key_is_policy_one(self):
        assert hook_policy_version({}) == 1

    def test_a_non_dict_is_policy_one(self):
        for bad in (None, [], "2", 2, [None, {"shape": {}}]):
            assert hook_policy_version(bad) == 1

    def test_a_non_integer_value_is_policy_one(self):
        for bad in ("2", 2.0, None, [], {}):
            assert hook_policy_version({HOOK_POLICY_METADATA_KEY: bad}) == 1

    def test_true_does_not_read_as_a_version(self):
        """`bool` is an `int` in Python, so `True` would otherwise sneak in as
        version 1 by coincidence rather than by decision."""
        assert hook_policy_version({HOOK_POLICY_METADATA_KEY: True}) == 1

    def test_the_current_stamp_reads_back(self):
        assert (
            hook_policy_version({HOOK_POLICY_METADATA_KEY: CURRENT_HOOK_POLICY_VERSION})
            == CURRENT_HOOK_POLICY_VERSION
        )

    def test_a_future_policy_is_not_retired_by_an_older_server(self):
        """A rolling deploy runs two versions at once. The newer writer's hooks
        must not be suppressed by the older reader, or the fleet would flap
        every card's prose for the length of the rollout."""
        assert not is_hook_stale(
            hook_description="Written by a newer dyno.",
            hook_generated_at=_NOW - timedelta(hours=1),
            hook_leader_at_generation="Yes",
            current_leader_name="Yes",
            current_leader_probability=0.65,
            market_metadata={
                HOOK_PROB_METADATA_KEY: 0.65,
                HOOK_POLICY_METADATA_KEY: CURRENT_HOOK_POLICY_VERSION + 1,
            },
            now=_NOW,
        )


class TestBothFeedPathsCanSeeThePolicy5461:
    """The BLOCK asked for this "across both feed paths", and that is a real
    requirement rather than a formality: `routes/feed.py` calls `is_hook_stale`
    in TWO places (the sports/futures path and the Discover path). Either one
    omitting `market_metadata` would keep serving retired hooks on that surface
    while the other went quiet — a half-fixed feed, which is harder to notice
    than an unfixed one.

    Asserted over the source because the alternative is standing up two full
    feed builds to observe one argument.
    """

    def test_every_is_hook_stale_call_in_the_feed_route_passes_market_metadata(self):
        import inspect

        from app.routes import feed as feed_module

        src = inspect.getsource(feed_module)
        calls = src.split("is_hook_stale(")[1:]
        assert len(calls) >= 2, (
            f"expected both feed paths to gate hooks; found {len(calls)} call(s)"
        )
        for i, call in enumerate(calls):
            body = call[: call.index("\n            )") if "\n            )" in call[:900] else 900]
            assert "market_metadata=" in body, (
                f"is_hook_stale call #{i + 1} cannot see the policy version"
            )


class TestTheWriterStampsThePolicy5461:
    """🔴 THE CATASTROPHIC DIRECTION, AND IT IS THE QUIET ONE.

    Every test above checks that RETIRED hooks are suppressed. If the writer
    fails to stamp, the same code suppresses *every* hook forever: the gate
    reads policy 1 on a sentence the current prompt just wrote, the card goes
    wordless, and the feed's entire prose layer disappears with no error, no
    exception and no failing test — the hooks would simply never appear again.

    The stamp and the sentence must therefore go into the SAME write. Asserted
    over the task's source because the alternative is a live LLM call.
    """

    def test_the_hook_write_stamps_the_current_policy_version(self):
        import inspect

        from app.tasks import enrich_markets

        src = inspect.getsource(enrich_markets)
        start = src.index("next_metadata[HOOK_PROB_METADATA_KEY]")
        block = src[start : src.index("hook_description=hook,", start)]
        assert "HOOK_POLICY_METADATA_KEY" in block, (
            "the hook write must stamp the policy version, or every hook it "
            "writes is suppressed on its own first serve"
        )
        assert "CURRENT_HOOK_POLICY_VERSION" in block

    def test_the_stamp_is_in_the_same_metadata_dict_as_the_sentence(self):
        """Not a separate UPDATE that could fail on its own and leave a
        sentence with no stamp — which is the retired state."""
        import inspect

        from app.tasks import enrich_markets

        src = inspect.getsource(enrich_markets)
        write = src[src.index("hook_description=hook,") :]
        write = write[: write.index(")\n")]
        assert "market_metadata=next_metadata" in write
