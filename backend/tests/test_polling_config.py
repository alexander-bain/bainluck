"""Tests for utils/polling_config.py — odds polling parameter logic."""

from app.utils.polling_config import determine_api_params, compute_effective_interval
from app.tasks.config import SLOW_THRESHOLD, MEDIUM_THRESHOLD


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
