"""A live Grand Slam match is a tier-2 moment, not a minor-league one (#2552).

`LEAGUE_TIERS` has always declared the slams tier 2 ("Grand Slams ARE the moments
casual fans care about"), but it spelled them without the tour segment —
`tennis_us_open` — while every ingested event carries `tennis_atp_us_open` or
`tennis_wta_us_open`. The exact-match lookup therefore never once fired: four of
the six slam entries matched zero rows in production, so every Grand Slam match
scored tier 4 and took the -45 minor-league penalty.

Measured on production 2026-09-01, while five US Open matches were `status='live'`:
`GET /api/feed?mode=sports` returned ten live event cards and no tennis, and
/sports rendered "Live Now · 11" as one cycling card, seven MLB and three MMA.
The two live US Open matches scored 40 and 35 and sat at ranks #55 and #64 —
below the window the page loads — where tier 2 would have put them at 95 and 90.

These tests pin the ship in both directions (gotcha #43): a slam reaches tier 2,
and a regular tour stop still does not. They also pin the two things this fix
deliberately does NOT move: the Odds API discovery cadence, and any sport that
was never a tennis key.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.highlights import (
    WEIGHTS,
    compute_highlight,
    get_league_tier,
)


# Every tennis sport key attached to an event row in production, measured
# 2026-09-01 via `POST /api/admin/db-query` (42 keys, 30,853 events). The point
# of pinning the whole measured population rather than a couple of examples is
# that the defect WAS a spelling nobody had compared against reality.
PRODUCTION_SLAM_KEYS = (
    "tennis_atp_us_open",
    "tennis_wta_us_open",
    "tennis_atp_french_open",
    "tennis_wta_french_open",
    "tennis_atp_wimbledon",
    "tennis_wta_wimbledon",
    "tennis_atp_aus_open_singles",
    "tennis_wta_aus_open_singles",
)

PRODUCTION_REGULAR_TOUR_KEYS = (
    "tennis_atp",
    "tennis_wta",
    "tennis_other",
    "tennis_atp_cincinnati_open",
    "tennis_wta_cincinnati_open",
    "tennis_atp_canadian_open",
    "tennis_wta_canadian_open",
    "tennis_wta_monterrey_open",
    "tennis_atp_dubai",
    "tennis_wta_dubai",
    "tennis_atp_qatar_open",
    "tennis_wta_qatar_open",
    "tennis_atp_munich",
    "tennis_atp_washington_open",
    "tennis_wta_washington_open",
    "tennis_wta_charleston_open",
    "tennis_wta_stuttgart_open",
    "tennis_atp_halle_open",
    "tennis_atp_barcelona_open",
    "tennis_atp_italian_open",
    "tennis_wta_italian_open",
    "tennis_atp_queens_club_champ",
    "tennis_wta_queens_club_champ",
    "tennis_wta_german_open",
    "tennis_wta_indian_wells",
    "tennis_atp_indian_wells",
    "tennis_atp_miami_open",
    "tennis_wta_miami_open",
    "tennis_wta_strasbourg",
    "tennis_atp_madrid_open",
    "tennis_wta_madrid_open",
    "tennis_atp_monte_carlo_masters",
    "tennis_atp_hamburg_open",
    "tennis_wta_bad_homburg_open",
)


class TestSlamTennisTier:
    @pytest.mark.parametrize("sport_key", PRODUCTION_SLAM_KEYS)
    def test_every_production_slam_key_is_tier_2(self, sport_key):
        assert get_league_tier(sport_key) == 2

    @pytest.mark.parametrize("sport_key", PRODUCTION_REGULAR_TOUR_KEYS)
    def test_every_production_regular_tour_key_stays_tier_4(self, sport_key):
        """The control. A widened lookup that also promotes the tour is not a fix."""
        assert get_league_tier(sport_key) == 4

    def test_the_two_populations_do_not_overlap(self):
        assert not set(PRODUCTION_SLAM_KEYS) & set(PRODUCTION_REGULAR_TOUR_KEYS)

    def test_non_tennis_keys_are_untouched(self):
        """Control: the fallback is tennis-shaped and must not reach anything else."""
        assert get_league_tier("baseball_mlb") == 1
        assert get_league_tier("mma_mixed_martial_arts") == 2
        assert get_league_tier("boxing_boxing") == 3
        assert get_league_tier("baseball_mlb_preseason") == 4
        assert get_league_tier("icehockey_ahl") == 4
        assert get_league_tier("unknown_sport") == 4
        assert get_league_tier("soccer_atp_us_open") == 4  # tennis-shaped, not tennis
        assert get_league_tier(None) == 4


class TestLiveUsOpenMatchClearsTheRail:
    """The ship, on the two shapes that were measured wrong on production.

    Both were `status='live'` at 2026-09-02 01:28Z while /sports showed no tennis.
    Each is scored twice — once under its real slam key, once under a regular tour
    key — so that the sport key is the only difference between the arms.
    """

    NOW = datetime(2026, 9, 2, 1, 28, tzinfo=timezone.utc)

    def _blowout(self, sport_key):
        """Event 15293804, Vallejo vs Monfils. Opened 0.5545 home, trading 0.0313."""
        return compute_highlight(
            status="live",
            commence_time=self.NOW - timedelta(minutes=24),
            sport_key=sport_key,
            current_home_prob=0.0313,
            current_away_prob=0.9687,
            opening_home_prob=0.5545,
            opening_away_prob=0.4455,
            opening_favorite="home",
            home_team_name="Adolfo Daniel Vallejo",
            away_team_name="Gael Monfils",
            now=self.NOW,
        )

    def _coin_flip(self, sport_key):
        """Event 15293702, Jović vs Frech. Opened 0.7428 home, trading 0.5397."""
        return compute_highlight(
            status="live",
            commence_time=self.NOW - timedelta(minutes=21),
            sport_key=sport_key,
            current_home_prob=0.5397,
            current_away_prob=0.4603,
            opening_home_prob=0.7428,
            opening_away_prob=0.2572,
            opening_favorite="home",
            home_team_name="Iva Jović",
            away_team_name="Magdalena Frech",
            now=self.NOW,
        )

    def test_the_live_us_open_matches_are_scored_as_tier_2(self):
        for result in (
            self._blowout("tennis_atp_us_open"),
            self._coin_flip("tennis_wta_us_open"),
        ):
            assert "tier_2" in result.reasons
            assert "tier_4" not in result.reasons

    def test_both_clear_the_feed_floor_they_used_to_scrape(self):
        """`_score_events` drops anything under min_score 30.

        Neither card was actually cut by that floor — they scored 40 and 35 — but
        the penalty left them ranked #55 and #64, below the window /sports loads.
        Tier 2 is what moves them up to where a fan sees them.
        """
        assert self._blowout("tennis_atp_us_open").score == 60
        assert self._coin_flip("tennis_wta_us_open").score == 90

    def test_the_identical_matches_on_the_regular_tour_still_do_not(self):
        """The control, and the whole reason the assertions above are results."""
        assert self._blowout("tennis_atp_cincinnati_open").score == 35
        assert self._coin_flip("tennis_atp_cincinnati_open").score == 35
        for result in (
            self._blowout("tennis_atp_cincinnati_open"),
            self._coin_flip("tennis_atp_cincinnati_open"),
        ):
            assert "tier_4" in result.reasons

    def test_the_coin_flip_swing_is_the_full_tier_weight_difference(self):
        """A clean specimen: no clamp intervenes, so the arithmetic is legible."""
        swing = (
            self._coin_flip("tennis_wta_us_open").score
            - self._coin_flip("tennis_atp_cincinnati_open").score
        )
        assert swing == WEIGHTS["tier_2_league"] - WEIGHTS["tier_4_penalty"] == 55

    def test_the_blowout_swing_is_smaller_because_a_mid_computation_floor_clips_it(self):
        """Not a bug in this fix, but it is why the live card scored 40 and not -15.

        The blowout penalty at `highlights.py` is `max(0, score - 15)`, and that
        floor runs AFTER the tier block. A tier-4 blowout is already negative by
        then, so the floor absorbs part of the -45 and the two arms end up 25
        apart rather than 55. Pinned so the interaction stays visible.
        """
        swing = (
            self._blowout("tennis_atp_us_open").score
            - self._blowout("tennis_atp_cincinnati_open").score
        )
        assert swing == 25


class TestTheTagAgreesWithTheRanker:
    """One question, one answer — a card scored tier 2 must not be tagged tier:4.

    The live payload measured on 2026-09-01 carried `"tier:4"` in `event_tags`
    for the same match the ranker was about to score, and
    `_discover_event_has_major_league_context` reads those tags as a fallback.
    """

    @staticmethod
    def _tags(sport_key):
        from app.utils.event_taxonomy import compute_event_tags

        return compute_event_tags(
            sport_key=sport_key,
            status="live",
            commence_time=datetime(2026, 9, 2, 1, 4, tzinfo=timezone.utc),
        )

    def test_a_slam_match_is_tagged_tier_2(self):
        assert "tier:2" in self._tags("tennis_atp_us_open")
        assert "tier:4" not in self._tags("tennis_atp_us_open")

    def test_a_regular_tour_match_is_still_tagged_tier_4(self):
        assert "tier:4" in self._tags("tennis_atp_cincinnati_open")

    @pytest.mark.parametrize(
        "sport_key", PRODUCTION_SLAM_KEYS + PRODUCTION_REGULAR_TOUR_KEYS
    )
    def test_the_tag_never_disagrees_with_the_ranker(self, sport_key):
        expected = get_league_tier(sport_key)
        assert f"tier:{expected}" in self._tags(sport_key)


class TestTheOddsApiBudgetDoesNotMove:
    """A deliberate scope boundary, pinned so it cannot drift in silently.

    `_get_discover_interval` reads `LEAGUE_TIERS` directly rather than through
    `get_league_tier`, so promoting the slams does not re-cadence discovery.
    That is on purpose: The Odds API quota is the constrained resource (5M/mo),
    tier 2 would take US Open discovery from 4h to 30min, and that spend is not
    part of this ship and has not been measured. Changing it is a separate,
    quota-budgeted decision — this test makes taking it by accident a red build.
    """

    @pytest.mark.parametrize("sport_key", PRODUCTION_SLAM_KEYS)
    def test_slam_discovery_still_runs_at_the_tier_4_cadence(self, sport_key):
        from app.tasks.config import DISCOVER_TIER4_INTERVAL
        from app.tasks.sports import _get_discover_interval

        if sport_key in ("tennis_atp_aus_open_singles", "tennis_wta_aus_open_singles"):
            # These two spellings were always in the table verbatim, so they were
            # already on the tier-2 cadence before this change and still are.
            pytest.skip("exact-match entry — its cadence predates this fix")
        assert _get_discover_interval(sport_key) == DISCOVER_TIER4_INTERVAL

    def test_the_untouched_cadences_are_still_tiered(self):
        """Control: the cadence function still works, it just didn't move."""
        from app.tasks.config import (
            DISCOVER_TIER1_INTERVAL,
            DISCOVER_TIER4_INTERVAL,
        )
        from app.tasks.sports import _get_discover_interval

        assert _get_discover_interval("baseball_mlb") == DISCOVER_TIER1_INTERVAL
        assert _get_discover_interval("icehockey_ahl") == DISCOVER_TIER4_INTERVAL
