"""Tests for Discover futures market quality classification."""

from app.utils.feed_market_quality import (
    cap_low_quality_families,
    classify_market_quality,
    quality_score_adjustment,
)
from app.utils.futures_highlights import compute_futures_highlight


class TestMarketQualityClassification:
    def test_narrow_oil_bucket_is_low_quality(self):
        quality = classify_market_quality(
            "Will next month's oil price be between $70.20 and $70.80?",
            sport_category="economics",
        )

        assert quality.quality_class == "low_quality"
        assert quality.is_ladder_or_bucket is True
        assert quality.is_narrow_range is True
        assert "ladder_or_bucket" in quality.reasons
        assert "narrow_range" in quality.reasons
        assert quality_score_adjustment(quality) <= -50

    def test_weather_bucket_is_low_quality(self):
        quality = classify_market_quality(
            "NYC temperature on May 12 above 72 degrees?",
            sport_category="weather",
        )

        assert quality.quality_class == "low_quality"
        assert quality.is_ladder_or_bucket is True

    def test_weather_category_alone_is_not_low_quality(self):
        quality = classify_market_quality(
            "Will a hurricane make landfall in Florida before September?",
            sport_category="weather",
        )

        assert quality.quality_class == "compelling"
        assert quality.is_ladder_or_bucket is False

    def test_broad_crypto_milestone_not_treated_as_price_bucket(self):
        quality = classify_market_quality(
            "Will Bitcoin hit $150k before the end of 2026?",
            sport_category="crypto",
        )

        assert quality.quality_class == "compelling"
        assert quality.is_ladder_or_bucket is False

    def test_dated_oil_price_market_is_low_quality(self):
        quality = classify_market_quality(
            "Oil Price (WTI) on May 1, 2026?",
            sport_category="economics",
        )

        assert quality.quality_class == "low_quality"
        assert quality.is_ladder_or_bucket is True

    def test_social_filler_is_suppressed(self):
        quality = classify_market_quality(
            'Will Trump post "tariffs" this week on Truth?',
            sport_category="politics",
        )

        assert quality.quality_class == "suppress"
        assert "social_filler" in quality.reasons

    def test_sports_personnel_story_is_compelling(self):
        quality = classify_market_quality(
            "Will Mike Vrabel be fired before the Patriots' next game?",
            sport_category="football",
        )

        assert quality.quality_class == "compelling"
        assert "sports_personnel_story" in quality.reasons
        assert quality.has_named_salient_entity is True
        assert quality_score_adjustment(quality) > 0

    def test_health_outbreak_story_is_compelling(self):
        quality = classify_market_quality(
            "Will Hantavirus be declared a public health emergency in 2026?",
            sport_category="health",
        )

        assert quality.quality_class == "compelling"
        assert "health_outbreak" in quality.reasons

    def test_major_geopolitics_not_suppressed(self):
        quality = classify_market_quality(
            "Will Israel and Iran agree to a ceasefire before July?",
            sport_category="geopolitics",
        )

        assert quality.quality_class == "compelling"
        assert "compelling_topic" in quality.reasons

    def test_numeric_outcome_ladder_detected(self):
        quality = classify_market_quality(
            "What will CPI be in June?",
            sport_category="economics",
            outcome_names=["2.0%-2.1%", "2.1%-2.2%", "2.2%-2.3%", "2.3%-2.4%"],
        )

        assert quality.is_ladder_or_bucket is True
        assert "numeric_outcome_ladder" in quality.reasons

    def test_quality_adjustment_demotes_high_volume_narrow_bucket(self):
        oil_highlight = compute_futures_highlight(
            market_tier=5,
            sport_category="economics",
            market_name="Will next month's oil price be between $70.20 and $70.80?",
            volume_24h=100_000,
        )
        oil_quality = classify_market_quality(
            "Will next month's oil price be between $70.20 and $70.80?",
            sport_category="economics",
        )
        hantavirus_highlight = compute_futures_highlight(
            market_tier=5,
            sport_category="health",
            market_name="Will Hantavirus be declared a public health emergency in 2026?",
            volume_24h=1_000,
        )
        hantavirus_quality = classify_market_quality(
            "Will Hantavirus be declared a public health emergency in 2026?",
            sport_category="health",
        )

        oil_score = max(0, oil_highlight.score + quality_score_adjustment(oil_quality))
        hantavirus_score = max(
            0,
            hantavirus_highlight.score + quality_score_adjustment(hantavirus_quality),
        )

        assert oil_highlight.score > hantavirus_highlight.score
        assert oil_score < hantavirus_score


class TestLowQualityFamilyCap:
    def test_cap_keeps_only_best_low_quality_family_member(self):
        items = [
            {"score": 82, "_quality_class": "low_quality", "_quality_family_key": "oil <range>"},
            {"score": 75, "_quality_class": "low_quality", "_quality_family_key": "oil <range>"},
            {"score": 70, "_quality_class": "low_quality", "_quality_family_key": "oil <range>"},
            {"score": 65, "_quality_class": "compelling", "_quality_family_key": "vrabel fired"},
        ]

        capped = cap_low_quality_families(items, cap=1)

        assert len(capped) == 2
        assert any(i["_quality_family_key"] == "vrabel fired" for i in capped)
        oil_items = [i for i in capped if i["_quality_family_key"] == "oil <range>"]
        assert len(oil_items) == 1
        assert oil_items[0]["score"] == 82

    def test_cap_does_not_limit_compelling_same_family(self):
        items = [
            {"score": 90, "_quality_class": "compelling", "_quality_family_key": "ai regulation"},
            {"score": 80, "_quality_class": "compelling", "_quality_family_key": "ai regulation"},
        ]

        capped = cap_low_quality_families(items, cap=1)

        assert len(capped) == 2
