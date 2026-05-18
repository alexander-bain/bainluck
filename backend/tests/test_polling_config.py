"""Tests for utils/polling_config.py — odds polling parameter logic."""

import pytest

from app.utils.polling_config import determine_api_params, compute_effective_interval
from app.tasks import redis_state
from app.tasks.config import (
    LATER_POLL_INTERVAL,
    LIVE_POLL_INTERVAL,
    MEDIUM_THRESHOLD,
    SLOW_THRESHOLD,
    SOON_POLL_INTERVAL,
    SPORT_POLLING_DEFAULT_TIER,
    SPORT_POLLING_TIERS,
    SPORT_TIER_MULTIPLIERS,
)
from app.tasks.redis_state import (
    QUOTA_GUARD_ABSOLUTE_STOP,
    QUOTA_GUARD_CONSERVATION_INTERVAL,
    QUOTA_GUARD_FULL_STOP,
    QUOTA_GUARD_LIVE_ONLY,
    QUOTA_GUARD_PRIORITY_SPORTS,
)


class _FakeQuotaRedis:
    def __init__(self, remaining: int):
        self.remaining = remaining

    def hgetall(self, _key):
        return {b"remaining": str(self.remaining).encode()}


class TestDetermineApiParams:

    def test_conservation_always_h2h_us(self):
        markets, regions = determine_api_params("live", 1, "basketball_nba", quota_conservation=True)
        assert markets == "h2h"
        assert regions == "us"

    def test_live_tier1_full_markets_dual_region(self):
        markets, regions = determine_api_params("live", 1, "basketball_nba", quota_conservation=False)
        assert markets == "h2h,spreads,totals"
        assert regions == "us,us2"

    def test_live_tier2_full_markets_single_region(self):
        markets, regions = determine_api_params("live", 2, "soccer_usa_mls", quota_conservation=False)
        assert markets == "h2h,spreads,totals"
        assert regions == "us"

    def test_live_tier3_full_markets_single_region(self):
        markets, regions = determine_api_params("live", 3, "cricket_ipl", quota_conservation=False)
        assert markets == "h2h,spreads,totals"
        assert regions == "us"

    def test_soon_tier1_full_markets_dual_region(self):
        markets, regions = determine_api_params("soon", 1, "icehockey_nhl", quota_conservation=False)
        assert markets == "h2h,spreads,totals"
        assert regions == "us,us2"

    def test_later_h2h_only(self):
        markets, regions = determine_api_params("later", 1, "basketball_nba", quota_conservation=False)
        assert markets == "h2h"
        assert regions == "us"

    def test_region_override_applied(self):
        markets, regions = determine_api_params("live", 1, "baseball_mlb", quota_conservation=False)
        assert regions == "us"  # MLB has a region override to us-only

    def test_region_override_not_applied_in_conservation(self):
        markets, regions = determine_api_params("live", 1, "baseball_mlb", quota_conservation=True)
        assert regions == "us"  # Conservation always us, regardless of override


class TestComputeEffectiveInterval:

    def test_base_interval_returned_normally(self):
        interval = compute_effective_interval(
            base_interval=32.0, sport_key="basketball_nba",
            tier="live", unchanged_count=0, quota_conservation=False,
        )
        assert interval == 32.0

    def test_sport_min_overrides_base(self):
        interval = compute_effective_interval(
            base_interval=32.0, sport_key="aussierules_afl",
            tier="live", unchanged_count=0, quota_conservation=False,
        )
        assert interval >= 600  # AFL has 10-min minimum

    def test_conservation_mode_floor(self):
        interval = compute_effective_interval(
            base_interval=32.0, sport_key="basketball_nba",
            tier="live", unchanged_count=0, quota_conservation=True,
        )
        assert interval >= 600

    def test_adaptive_medium_slowdown(self):
        interval = compute_effective_interval(
            base_interval=60.0, sport_key="basketball_nba",
            tier="soon", unchanged_count=MEDIUM_THRESHOLD, quota_conservation=False,
        )
        assert interval >= 300  # MEDIUM_POLL_INTERVAL

    def test_adaptive_slow_slowdown(self):
        interval = compute_effective_interval(
            base_interval=60.0, sport_key="basketball_nba",
            tier="soon", unchanged_count=SLOW_THRESHOLD, quota_conservation=False,
        )
        assert interval >= 600  # SLOW_POLL_INTERVAL

    def test_adaptive_not_applied_to_live(self):
        interval = compute_effective_interval(
            base_interval=32.0, sport_key="basketball_nba",
            tier="live", unchanged_count=SLOW_THRESHOLD + 10, quota_conservation=False,
        )
        assert interval == 32.0  # Live tier exempt from slowdown

    def test_no_slowdown_below_threshold(self):
        interval = compute_effective_interval(
            base_interval=60.0, sport_key="basketball_nba",
            tier="soon", unchanged_count=1, quota_conservation=False,
        )
        assert interval == 60.0


class TestSportTierQuotaGuardrails:

    def test_tier_intervals_match_quota_budget(self):
        """Live cadence is the quota budget's sharp edge; keep tier multipliers locked."""
        cases = [
            ("basketball_nba", LIVE_POLL_INTERVAL, SOON_POLL_INTERVAL, LATER_POLL_INTERVAL),
            ("soccer_usa_mls", LIVE_POLL_INTERVAL * 2, SOON_POLL_INTERVAL * 2, LATER_POLL_INTERVAL * 2),
            ("cricket_ipl", LIVE_POLL_INTERVAL * 4, SOON_POLL_INTERVAL * 4, LATER_POLL_INTERVAL * 4),
        ]

        for sport_key, live_interval, soon_interval, later_interval in cases:
            sport_tier = SPORT_POLLING_TIERS.get(sport_key, SPORT_POLLING_DEFAULT_TIER)
            tier_mult = SPORT_TIER_MULTIPLIERS[sport_tier]
            assert LIVE_POLL_INTERVAL * tier_mult == live_interval
            assert SOON_POLL_INTERVAL * tier_mult == soon_interval
            assert LATER_POLL_INTERVAL * tier_mult == later_interval

    def test_default_tier_is_long_tail_single_region_h2h_later(self):
        sport_tier = SPORT_POLLING_TIERS.get("cricket_ipl", SPORT_POLLING_DEFAULT_TIER)

        assert sport_tier == 3
        assert SPORT_TIER_MULTIPLIERS[sport_tier] == 4
        assert determine_api_params("later", sport_tier, "cricket_ipl", quota_conservation=False) == (
            "h2h",
            "us",
        )

    def test_priority_sports_are_core_tier_one_only(self):
        assert QUOTA_GUARD_PRIORITY_SPORTS == frozenset({
            "basketball_nba",
            "baseball_mlb",
            "basketball_ncaab",
        })
        assert all(SPORT_POLLING_TIERS[sport_key] == 1 for sport_key in QUOTA_GUARD_PRIORITY_SPORTS)

    @pytest.mark.parametrize("remaining", [QUOTA_GUARD_LIVE_ONLY, QUOTA_GUARD_FULL_STOP + 1])
    def test_live_only_guard_blocks_discovery_and_futures_but_allows_odds_polling(
        self, monkeypatch, remaining
    ):
        monkeypatch.setattr(redis_state, "QUOTA_GUARD_EXPIRY", "2999-01-01T00:00:00+00:00")
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: _FakeQuotaRedis(remaining))

        assert redis_state.check_quota_guard("poll_odds") == (True, f"live_only_{remaining}")
        assert redis_state.check_quota_guard("discover_events") == (False, f"live_only_{remaining}")
        assert redis_state.check_quota_guard("poll_futures") == (False, f"live_only_{remaining}")

    def test_full_stop_guard_only_allows_priority_sports_in_conservation(self, monkeypatch):
        remaining = QUOTA_GUARD_FULL_STOP
        monkeypatch.setattr(redis_state, "QUOTA_GUARD_EXPIRY", "2999-01-01T00:00:00+00:00")
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: _FakeQuotaRedis(remaining))

        assert redis_state.check_quota_guard("poll_odds", sport_key="basketball_nba") == (
            True,
            f"conservation_{remaining}",
        )
        assert redis_state.check_quota_guard("poll_odds", sport_key="icehockey_nhl") == (
            False,
            f"full_stop_{remaining}",
        )
        assert redis_state.check_quota_guard("poll_futures") == (False, f"full_stop_{remaining}")

    def test_absolute_stop_blocks_even_priority_sports(self, monkeypatch):
        remaining = QUOTA_GUARD_ABSOLUTE_STOP
        monkeypatch.setattr(redis_state, "QUOTA_GUARD_EXPIRY", "2999-01-01T00:00:00+00:00")
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: _FakeQuotaRedis(remaining))

        assert redis_state.check_quota_guard("poll_odds", sport_key="basketball_nba") == (
            False,
            f"absolute_stop_{remaining}",
        )

    def test_conservation_interval_floor_matches_guard_constant(self):
        interval = compute_effective_interval(
            base_interval=LIVE_POLL_INTERVAL,
            sport_key="basketball_nba",
            tier="live",
            unchanged_count=0,
            quota_conservation=True,
        )

        assert interval == QUOTA_GUARD_CONSERVATION_INTERVAL
