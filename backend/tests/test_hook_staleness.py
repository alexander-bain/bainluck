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
    HOOK_PROB_METADATA_KEY,
    STALE_HOOK_MAX_AGE_DAYS,
    STALE_PROBABILITY_DELTA,
    get_hook_probability_at_generation,
    is_hook_stale,
)


_NOW = datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc)


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
            market_metadata={HOOK_PROB_METADATA_KEY: 0.63},
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
            market_metadata={},
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
            market_metadata={},
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
            market_metadata={HOOK_PROB_METADATA_KEY: 0.60},
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
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65},
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
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65},
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
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65},
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
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65},
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
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65},
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
            market_metadata={},
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
            market_metadata={},
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
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65},
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
            market_metadata={HOOK_PROB_METADATA_KEY: 0.30},
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
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65},
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
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65},
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
            market_metadata={HOOK_PROB_METADATA_KEY: 0.65},
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
        market.market_metadata = {HOOK_PROB_METADATA_KEY: 0.65}

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
        market.market_metadata = {HOOK_PROB_METADATA_KEY: 0.65}

        assert not _needs_regeneration(market, "Yes", 0.60, _NOW)
