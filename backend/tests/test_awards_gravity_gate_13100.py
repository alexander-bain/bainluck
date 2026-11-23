"""Tests for #13100 (Ruling 277: A): awards cultural gravity gate and no double-count."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.futures_highlights import (
    AWARDS_GRAVITY_HORIZON_DAYS,
    COMPELLING_BOOST,
    CULTURAL_GRAVITY_T1_BOOST,
    DISCOVER_AWARDS_GRAVITY_GATE_ENV,
    compute_futures_highlight,
    is_awards_gravity_gate_enabled,
)

FROZEN_NOW = datetime(2025, 2, 15, 18, 0, tzinfo=timezone.utc)


def _quiet_outcomes():
    return [
        {
            "name": "Favorite",
            "probability": 0.45,
            "probability_change_24h": 0.0,
            "opening_probability": 0.45,
            "rank": 1,
            "rank_change_24h": 0,
        },
        {
            "name": "Runner-up",
            "probability": 0.30,
            "probability_change_24h": 0.0,
            "opening_probability": 0.30,
            "rank": 2,
            "rank_change_24h": 0,
        },
    ]


class TestAwardsGravityGateSwitch:
    def test_switch_defaults_on_and_turns_off_in_one_step(self, monkeypatch):
        monkeypatch.delenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, raising=False)
        assert is_awards_gravity_gate_enabled() is True

        for off_val in ("0", "false", "False", "no", "off", "OFF"):
            monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, off_val)
            assert is_awards_gravity_gate_enabled() is False

        monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "1")
        assert is_awards_gravity_gate_enabled() is True


class TestAwardsGravityAndDoubleCount:
    @pytest.mark.parametrize(
        "market_name",
        [
            "Oscar Winner: Best Picture",
            "Oscars 2026: Best Makeup and Hairstyling Winner",
            "Grammys 2026: Best Country Song Winner",
            "Golden Globes 2026: Best Motion Picture Drama",
            "Emmy Awards: Outstanding Drama Series",
            "Tony Awards: Best Musical",
        ],
    )
    def test_far_quiet_awards_lose_gravity_and_duplicate_compelling(
        self, monkeypatch, market_name: str
    ):
        far_res = FROZEN_NOW + timedelta(days=120)

        monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "0")
        legacy = compute_futures_highlight(
            market_tier=1,
            sport_category="entertainment",
            resolution_date=far_res,
            outcomes=_quiet_outcomes(),
            now=FROZEN_NOW,
            market_name=market_name,
        )
        assert "cultural_gravity_t1" in legacy.reasons
        assert any(r.startswith("compelling_x") for r in legacy.reasons)

        monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "1")
        gated = compute_futures_highlight(
            market_tier=1,
            sport_category="entertainment",
            resolution_date=far_res,
            outcomes=_quiet_outcomes(),
            now=FROZEN_NOW,
            market_name=market_name,
        )
        assert "cultural_gravity_t1" not in gated.reasons
        assert "awards_gravity_deferred" in gated.reasons
        assert legacy.raw_score - gated.raw_score == (
            CULTURAL_GRAVITY_T1_BOOST + COMPELLING_BOOST
        )

    def test_near_awards_within_45_days_keep_gravity_without_compelling_double_count(
        self, monkeypatch
    ):
        near_res = FROZEN_NOW + timedelta(days=AWARDS_GRAVITY_HORIZON_DAYS)
        name = "Oscar Winner: Best Picture"

        monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "0")
        legacy = compute_futures_highlight(
            market_tier=1,
            sport_category="entertainment",
            resolution_date=near_res,
            outcomes=_quiet_outcomes(),
            now=FROZEN_NOW,
            market_name=name,
        )

        monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "1")
        gated = compute_futures_highlight(
            market_tier=1,
            sport_category="entertainment",
            resolution_date=near_res,
            outcomes=_quiet_outcomes(),
            now=FROZEN_NOW,
            market_name=name,
        )
        assert "cultural_gravity_t1" in gated.reasons
        assert "awards_gravity_deferred" not in gated.reasons
        assert not any(r.startswith("compelling_") for r in gated.reasons)
        assert legacy.raw_score - gated.raw_score == COMPELLING_BOOST

    def test_far_awards_market_earns_gravity_when_it_moves(self, monkeypatch):
        far_res = FROZEN_NOW + timedelta(days=120)
        moving_outcomes = [
            {
                "name": "Favorite",
                "probability": 0.48,
                "probability_change_24h": 0.04,
                "opening_probability": 0.44,
                "rank": 1,
                "rank_change_24h": 0,
            },
            {
                "name": "Runner-up",
                "probability": 0.28,
                "probability_change_24h": -0.04,
                "opening_probability": 0.32,
                "rank": 2,
                "rank_change_24h": 0,
            },
        ]

        monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "1")
        moved = compute_futures_highlight(
            market_tier=1,
            sport_category="entertainment",
            resolution_date=far_res,
            outcomes=moving_outcomes,
            now=FROZEN_NOW,
            market_name="Grammys 2026: Song of the Year Winner",
        )
        assert "cultural_gravity_t1" in moved.reasons
        assert "awards_gravity_deferred" not in moved.reasons
        assert not any(r.startswith("compelling_") for r in moved.reasons)

        # Tiny 0.5% tick or near-0% nominee move does NOT unlock gravity.
        tiny_outcomes = [
            {
                "name": "Favorite",
                "probability": 0.48,
                "probability_change_24h": 0.005,
                "opening_probability": 0.475,
                "rank": 1,
                "rank_change_24h": 0,
            },
            {
                "name": "Longshot",
                "probability": 0.01,
                "probability_change_24h": 0.05,
                "opening_probability": 0.01,
                "rank": 8,
                "rank_change_24h": 0,
            },
        ]
        tiny = compute_futures_highlight(
            market_tier=1,
            sport_category="entertainment",
            resolution_date=far_res,
            outcomes=tiny_outcomes,
            now=FROZEN_NOW,
            market_name="Grammys 2026: Song of the Year Winner",
        )
        assert "cultural_gravity_t1" not in tiny.reasons
        assert "awards_gravity_deferred" in tiny.reasons

    def test_distinct_non_awards_compelling_keyword_still_counts(self, monkeypatch):
        near_res = FROZEN_NOW + timedelta(days=20)
        monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "1")
        result = compute_futures_highlight(
            market_tier=3,
            sport_category="entertainment",
            resolution_date=near_res,
            outcomes=_quiet_outcomes(),
            now=FROZEN_NOW,
            market_name="Will Taylor Swift win a Grammy?",
        )
        # Grammy gravity (+18) + Taylor Swift compelling (+8), not Grammy compelling twice.
        assert "cultural_gravity_t1" in result.reasons
        assert "compelling_x1" in result.reasons

    @pytest.mark.parametrize(
        ("market_name", "category"),
        [
            ("Will the U.S. confirm that aliens exist?", "tech"),
            ("Will Elon Musk visit Mars in his lifetime?", "tech"),
            ("Major meteor strike before 2030?", "culture"),
            ("TIME Person of the Year 2026", "entertainment"),
            ("2028 U.S. Presidential Election winner?", "politics"),
            ("Super Bowl Halftime Show: Performers", "entertainment"),
        ],
    )
    def test_non_awards_and_far_fun_markets_are_completely_unchanged(
        self, monkeypatch, market_name: str, category: str
    ):
        far_res = FROZEN_NOW + timedelta(days=400)
        monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "0")
        before = compute_futures_highlight(
            market_tier=1,
            sport_category=category,
            resolution_date=far_res,
            outcomes=_quiet_outcomes(),
            now=FROZEN_NOW,
            market_name=market_name,
        )
        monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "1")
        after = compute_futures_highlight(
            market_tier=1,
            sport_category=category,
            resolution_date=far_res,
            outcomes=_quiet_outcomes(),
            now=FROZEN_NOW,
            market_name=market_name,
        )
        assert after.raw_score == before.raw_score
        assert after.score == before.score
        assert after.reasons == before.reasons
