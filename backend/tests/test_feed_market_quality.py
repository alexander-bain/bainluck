"""Tests for Discover futures market quality classification."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routes.feed import _market_base_trace, _market_runtime_filter_trace, _outcomes_overlap, _trace_search_tokens
from app.utils.feed_market_quality import (
    apply_explanation_quality_score,
    apply_quality_score,
    backfill_discover_editorial_tail,
    balance_discover_event_category_mix,
    cap_low_quality_families,
    classify_market_quality,
    diversify_discover_first_page,
    diversify_quality_families,
    editorial_archetype,
    has_specific_explanation,
    has_strong_hook,
    quality_score_adjustment,
)
from app.utils.feed_quality_debug import build_feed_quality_debug
from app.utils.feed_quality_debug import diagnose_stale_card_root_cause
from app.utils.feed_quality_debug import summarize_missing_ground_truth_db_trace
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

    def test_dated_finance_and_commodity_markets_are_low_quality(self):
        examples = [
            "Live cattle price on May 01, 2026 at 1:05 PM EDT?",
            "Treasury 10-year yield on May 8, 2026?",
            "USD/JPY price on May 4, 2026 at 10am EDT?",
            "EUR/USD price range on May 4, 2026 at 10am EDT?",
            "PPI YoY in April",
        ]

        for name in examples:
            quality = classify_market_quality(name, sport_category="economics")
            assert quality.quality_class == "low_quality", name
            assert quality.is_ladder_or_bucket is True, name

    def test_finance_price_threshold_variants_stay_low_quality(self):
        examples = [
            "S&P 500 price between 5,200 and 5,225 on May 17?",
            "Will natural gas close above $3.10 on May 20?",
            "Gold price below $2,350 next week?",
        ]

        for name in examples:
            quality = classify_market_quality(name, sport_category="economics")
            assert quality.quality_class == "low_quality", name
            assert quality.is_ladder_or_bucket is True, name
            assert "ladder_or_bucket" in quality.reasons, name
            assert quality.explanation_required is False, name
            assert apply_quality_score(100, quality) <= 70, name

    def test_daily_equity_direction_markets_are_low_quality(self):
        examples = [
            "SPY (SPY) Up or Down on May 18?",
            "Google (GOOGL) closes above ___ on May 18?",
            "Rocket Lab (RKLB) Up or Down on May 18?",
        ]

        for name in examples:
            quality = classify_market_quality(name, sport_category="economics")
            assert quality.quality_class == "low_quality", name
            assert "daily_equity_direction" in quality.reasons, name
            assert quality.story_key == "story:daily_equity_direction", name
            assert apply_quality_score(100, quality) <= 70, name

    def test_social_filler_is_suppressed(self):
        quality = classify_market_quality(
            'Will Trump post "tariffs" this week on Truth?',
            sport_category="politics",
        )

        assert quality.quality_class == "suppress"
        assert "social_filler" in quality.reasons

    def test_social_engagement_count_filler_is_suppressed_even_with_big_names(self):
        examples = [
            "Trump # likes on Truth this week",
            "Elon Musk # views on X this week",
            "What will Trump say during the debate?",
        ]

        for name in examples:
            quality = classify_market_quality(name, sport_category="politics")
            assert quality.quality_class == "suppress", name
            assert "social_filler" in quality.reasons, name
            assert apply_quality_score(100, quality) == 0, name

    def test_conversation_and_endorsement_filler_is_suppressed(self):
        examples = [
            "Who will Donald Trump talk to in Apr 2026?",
            "How many people will Trump endorse on Truth Social this week? (5/3-5/9)",
        ]

        for name in examples:
            quality = classify_market_quality(name, sport_category="politics")
            assert quality.quality_class == "suppress", name
            assert "social_filler" in quality.reasons

    def test_music_metric_markets_are_low_quality_and_family_capped(self):
        # Raw metric markets remain low_quality/suppressed
        boring_examples = [
            "GREENGREEN: Album Equivalent Units (May 01-May 07, 2026)",
            "Friday Night Lights streams up this week?",
            "Where will 'Ordinary' by Alex Warren rank on the Billboard Hot 100 chart dated May 9?",
        ]

        boring_qualities = [
            classify_market_quality(name, sport_category="entertainment")
            for name in boring_examples
        ]

        assert all(q.quality_class == "low_quality" for q in boring_qualities)
        assert all("entertainment_metric" in q.reasons for q in boring_qualities)

    def test_chart_ranking_markets_are_not_suppressed(self):
        # "Who's #1?" and "Top Artist on Spotify?" are genuinely interesting
        # prediction markets, not raw chart metrics. BR56: user complained
        # about never seeing Spotify content.
        interesting_examples = [
            "Top USA Artist on Spotify on Apr 29, 2026?",
            "#1 on the Billboard Hot 100 chart for the Week of May 9, 2026?",
            "#2 on the Billboard Hot 100 chart for the Week of May 9, 2026?",
        ]

        qualities = [
            classify_market_quality(name, sport_category="entertainment")
            for name in interesting_examples
        ]

        assert all(q.quality_class == "normal" for q in qualities)
        assert all("entertainment_metric" not in q.reasons for q in qualities)

    def test_netflix_rank_one_and_two_get_distinct_family_keys(self):
        # BR56: #1 and #2 Netflix Show markets must not be deduped into the
        # same family, or whichever has less movement gets killed.
        q1 = classify_market_quality("#1 US Netflix Show: May 12-18", "entertainment")
        q2 = classify_market_quality("#2 US Netflix Show: May 12-18", "entertainment")

        assert q1.family_key != q2.family_key
        assert "rankone" in q1.family_key
        assert "ranktwo" in q2.family_key
        assert q1.quality_class == "normal"
        assert q2.quality_class == "normal"

    def test_spotify_song_rank_markets_get_distinct_family_keys(self):
        q1 = classify_market_quality("#1 Global Spotify Song: May 12-18", "entertainment")
        q2 = classify_market_quality("#2 Global Spotify Song: May 12-18", "entertainment")

        assert q1.family_key != q2.family_key
        assert q1.quality_class == "normal"
        assert q2.quality_class == "normal"

    def test_regional_us_elections_are_low_quality_and_story_capped(self):
        examples = [
            "KY-04 Republican nominee?",
            "South Carolina Republican Governor nominee?",
            "NY-11 Democratic nominee?",
        ]

        qualities = [
            classify_market_quality(name, sport_category="politics")
            for name in examples
        ]

        assert all(q.quality_class == "low_quality" for q in qualities)
        assert all("regional_us_election" in q.reasons for q in qualities)
        assert all(q.story_key == "story:regional_us_elections" for q in qualities)

    def test_regional_public_interest_items_are_not_election_noise(self):
        examples = [
            ("Will California declare a wildfire emergency before October?", "weather"),
            ("Will New York City have a subway strike before July?", "politics"),
        ]

        qualities = [
            classify_market_quality(name, sport_category=category)
            for name, category in examples
        ]

        assert all(q.quality_class == "compelling" for q in qualities)
        assert all("regional_us_election" not in q.reasons for q in qualities)
        assert all("social_filler" not in q.reasons for q in qualities)
        assert all(q.explanation_required for q in qualities)

    def test_public_interest_markets_are_preserved_above_noise_filters(self):
        examples = [
            (
                "Will China invade Taiwan before 2027?",
                "geopolitics",
                "world_event",
            ),
            (
                "Will Nvidia earnings beat expectations in Q2?",
                "economics",
                "tech_frontier",
            ),
            (
                "Will a Category 4 hurricane make landfall in Florida before September?",
                "weather",
                "health_weather_risk",
            ),
        ]

        for name, category, expected_archetype in examples:
            quality = classify_market_quality(name, sport_category=category)
            assert quality.quality_class == "compelling", name
            assert "compelling_topic" in quality.reasons, name
            assert "ladder_or_bucket" not in quality.reasons, name
            assert "social_filler" not in quality.reasons, name
            assert quality.explanation_required is True, name
            assert apply_quality_score(100, quality) == 100, name
            assert editorial_archetype(name, category) == expected_archetype, name

    def test_niche_low_signal_sports_are_low_quality(self):
        quality = classify_market_quality(
            "Women's Table Tennis World Championship winner?",
            sport_category="sports",
        )

        assert quality.quality_class == "low_quality"
        assert "low_signal_sport" in quality.reasons
        assert quality.story_key == "story:niche_low_signal_sports"

    def test_more_low_signal_sports_share_single_story_family(self):
        examples = [
            "World Snooker Championship winner?",
            "All England Badminton Championship winner?",
            "Premier League Darts champion?",
        ]

        qualities = [
            classify_market_quality(name, sport_category="sports")
            for name in examples
        ]

        assert all(q.quality_class == "low_quality" for q in qualities)
        assert all("low_signal_sport" in q.reasons for q in qualities)
        assert {q.story_key for q in qualities} == {"story:niche_low_signal_sports"}
        assert all(not q.explanation_required for q in qualities)

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
        assert quality_score_adjustment(quality) >= 24

    def test_compelling_non_sports_stories_get_explanation_path(self):
        examples = [
            ("Will OpenAI release GPT-5 before 2027?", "tech", "story:ai"),
            ("Will SpaceX IPO in 2026?", "tech", None),
            ("Will Taylor Swift be pregnant in 2026?", "entertainment", None),
        ]

        for name, category, expected_story_key in examples:
            quality = classify_market_quality(name, sport_category=category)

            assert quality.quality_class == "compelling", name
            assert "compelling_topic" in quality.reasons, name
            assert quality.explanation_required is True, name
            assert quality_score_adjustment(quality) > 0, name
            if expected_story_key is not None:
                assert quality.story_key == expected_story_key, name

    def test_absurd_public_interest_markets_are_compelling(self):
        quality = classify_market_quality(
            "Will the U.S. confirm that aliens exist before 2027?",
            sport_category="culture",
        )

        assert quality.quality_class == "compelling"
        assert "absurd_but_real" in quality.reasons
        assert quality.story_key == "story:aliens_disclosure"
        assert apply_quality_score(88, quality) == 100

    def test_sports_personnel_story_gets_extra_boost(self):
        quality = classify_market_quality(
            "Will Mike Vrabel be fired before the Patriots' next game?",
            sport_category="football",
        )

        assert quality.quality_class == "compelling"
        assert "sports_personnel_story" in quality.reasons
        assert quality_score_adjustment(quality) >= 22

    def test_trade_deal_is_not_sports_personnel_story(self):
        quality = classify_market_quality(
            "Will Trump announce a new trade deal in Apr 2026?",
            sport_category="politics",
        )

        assert "sports_personnel_story" not in quality.reasons

    def test_non_sports_release_market_is_not_sports_personnel_story(self):
        quality = classify_market_quality(
            "When will The Last of Us Season 3 be released?",
            sport_category="entertainment",
        )

        assert "sports_personnel_story" not in quality.reasons
        assert editorial_archetype(
            "When will The Last of Us Season 3 be released?",
            "entertainment",
        ) == "culture_moment"

    def test_major_geopolitics_not_suppressed(self):
        quality = classify_market_quality(
            "Will Israel and Iran agree to a ceasefire before July?",
            sport_category="geopolitics",
        )

        assert quality.quality_class == "compelling"
        assert "compelling_topic" in quality.reasons
        assert quality.story_key == "story:middle_east_conflict"

    def test_story_key_groups_related_variants(self):
        examples = [
            "Iran closes its airspace by...?",
            "Israel x Iran permanent peace deal by...?",
            "Iran agrees to surrender enriched uranium stockpile by...?",
            "Will the Iranian regime fall by May 31?",
            "US-Iran nuclear deal?",
        ]

        story_keys = {
            classify_market_quality(name, sport_category="geopolitics").story_key
            for name in examples
        }

        assert story_keys == {"story:middle_east_conflict"}

    def test_story_key_groups_russia_war_territory_variants_without_ukraine(self):
        examples = [
            "Will Russia capture Kharkiv before July?",
            "Will Russia advance toward Sumy before July?",
            "Will Russia launch an offensive near Pokrovsk?",
            "Will Russian forces seize more territory before July?",
        ]

        qualities = [
            classify_market_quality(name, sport_category="geopolitics")
            for name in examples
        ]

        assert {quality.story_key for quality in qualities} == {"story:russia_ukraine"}
        assert all(quality.quality_class != "suppress" for quality in qualities)

    def test_story_key_groups_minor_soccer_leagues(self):
        minor = classify_market_quality(
            "Who will win the Chilean Primera Division?",
            sport_category="soccer",
        )
        major = classify_market_quality(
            "Who will win the Premier League?",
            sport_category="soccer",
        )

        assert minor.story_key == "story:minor_soccer_leagues"
        assert major.story_key != "story:minor_soccer_leagues"

    def test_story_key_groups_fifa_world_cup_futures(self):
        germany = classify_market_quality(
            "Will Germany win the 2026 FIFA World Cup?",
            sport_category="soccer",
        )
        france = classify_market_quality(
            "Will France win the 2026 FIFA World Cup?",
            sport_category="soccer",
        )

        assert germany.story_key == "story:fifa_world_cup"
        assert france.story_key == "story:fifa_world_cup"
        assert germany.quality_class == "compelling"

    def test_story_key_groups_repeated_company_stake_and_tournament_props(self):
        stake = classify_market_quality(
            "Will the US federal government take a stake in Lockheed Martin Corporation?",
            sport_category="politics",
        )
        golf = classify_market_quality(
            "Will Harry Hall finish in the Top 5 at the 2026 Truist Championship?",
            sport_category="golf",
        )

        assert stake.story_key == "story:us_government_stakes"
        assert golf.story_key == "story:golf_truist_championship"

    def test_story_key_groups_oil_ladder_variants(self):
        monthly_high = classify_market_quality(
            "What will WTI Crude Oil (WTI) hit in May 2026?",
            sport_category="economics",
        )
        daily_direction = classify_market_quality(
            "WTI Crude Oil (WTI) Up or Down on May 8?",
            sport_category="economics",
        )

        assert monthly_high.story_key == "story:oil"
        assert daily_direction.story_key == "story:oil"

    def test_story_key_groups_basketball_finals_path_variants(self):
        win = classify_market_quality(
            "Will the Boston Celtics win the 2026 NBA Finals?",
            sport_category="basketball",
        )
        advance = classify_market_quality(
            "Will Boston Celtics advance to the 2026 NBA Finals?",
            sport_category="basketball",
        )

        assert win.story_key == "story:basketball_finals_path"
        assert advance.story_key == "story:basketball_finals_path"

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

    def test_quality_score_ceiling_prevents_normal_market_saturation(self):
        normal = classify_market_quality(
            "PGA Tour: Truist Championship Top 20",
            sport_category="golf",
        )
        compelling = classify_market_quality(
            "Will Israel and Iran agree to a ceasefire before July?",
            sport_category="geopolitics",
        )

        assert normal.quality_class == "normal"
        assert apply_quality_score(100, normal) < 100
        assert apply_quality_score(100, compelling) == 100

    def test_low_quality_score_ceiling_prevents_bucket_saturation(self):
        quality = classify_market_quality(
            "Treasury 10-year yield on May 8, 2026?",
            sport_category="economics",
        )

        assert quality.quality_class == "low_quality"
        assert apply_quality_score(100, quality) <= 70

    def test_repetitive_oil_ranges_collapse_to_one_boring_family(self):
        qualities = [
            classify_market_quality(
                "Will next month's oil price be between $70.20 and $70.80?",
                sport_category="economics",
            ),
            classify_market_quality(
                "Will next month's oil price be between $70.80 and $71.40?",
                sport_category="economics",
            ),
        ]

        assert all(q.quality_class == "low_quality" for q in qualities)
        assert all(q.is_ladder_or_bucket for q in qualities)
        assert all(q.is_narrow_range for q in qualities)
        assert {q.family_key for q in qualities} == {
            "will next month s oil price be between <range>"
        }


class TestFeedQualityDebug:
    def test_builds_summary_and_item_diagnostics(self):
        now = datetime(2026, 5, 18, tzinfo=timezone.utc)
        items = [
            {
                "type": "futures",
                "score": 100,
                "headline": "Yes side up 30.0 points from opening",
                "reason": "Yes side moved up 30.0 points from opening in Iran closes its airspace by...?",
                "data": {
                    "id": 1,
                    "name": "Iran closes its airspace by...?",
                    "llm_sport_category": "geopolitics",
                    "source": "kalshi",
                    "status": "open",
                    "top_outcomes": [{"name": "Yes", "probability": 0.8}],
                    "hook_description": None,
                    "image_url": None,
                },
            },
            {
                "type": "futures",
                "score": 70,
                "headline": "Yes side up 5.0 points today",
                "reason": "Oil moved today",
                "data": {
                    "id": 2,
                    "name": "Oil Price (WTI) on May 1, 2026?",
                    "llm_sport_category": "economics",
                    "source": "kalshi",
                    "status": "open",
                    "resolution_date": "2026-05-01T00:00:00+00:00",
                    "top_outcomes": [{"name": "Yes", "probability": 0.55}],
                    "hook_description": None,
                    "image_url": None,
                },
            },
        ]

        debug = build_feed_quality_debug(
            items,
            ground_truth_items=[
                {
                    "source": "kalshi",
                    "category": "geopolitics",
                    "name": "Iran closes its airspace by...?",
                    "probability": "Yes 80%, No 20%",
                },
                {
                    "source": "polymarket",
                    "category": "Technology",
                    "name": "Will OpenAI announce GPT-6 in 2026?",
                    "probability": "Yes 35%, No 65%",
                },
                {
                    "source": "polymarket",
                    "category": "Sports",
                    "name": "Celtics vs. Knicks",
                    "probability": "Celtics 55%, Knicks 45%",
                },
                {
                    "source": "polymarket",
                    "category": "Sports",
                    "name": "Lakers vs. Knicks",
                    "probability": "Lakers 100%, Knicks 0%",
                },
            ],
            top_n=2,
            now=now,
        )

        assert debug["summary"]["items"] == 2
        assert debug["summary"]["boring_count"] == 1
        assert debug["summary"]["ladder_count"] == 1
        assert debug["summary"]["ground_truth_hit_count_50"] == 1
        assert debug["items"][0]["quality_class"] == "compelling"
        assert debug["items"][0]["ground_truth"] is True
        assert debug["items"][1]["quality_class"] == "low_quality"
        assert debug["items"][1]["stale_root_cause"]["code"] == "past_resolution_date"
        assert [item["name"] for item in debug["missing_ground_truth"]] == [
            "Will OpenAI announce GPT-6 in 2026?",
            "Celtics vs. Knicks",
        ]
        buckets = {
            item["name"]: item["triage_bucket"]
            for item in debug["missing_ground_truth"]
        }
        assert buckets["Will OpenAI announce GPT-6 in 2026?"] == "candidate_recall_gap"
        assert buckets["Celtics vs. Knicks"] == "game_market_noise"
        assert debug["missing_ground_truth_summary"]["bucket_counts"] == {
            "candidate_recall_gap": 1,
            "game_market_noise": 1,
        }

    def test_stale_root_cause_labels_obvious_futures_and_event_causes(self):
        now = datetime(2026, 5, 18, 12, tzinfo=timezone.utc)

        closed = diagnose_stale_card_root_cause(
            {"type": "futures", "data": {"status": "resolved"}},
            now=now,
        )
        stale_update = diagnose_stale_card_root_cause(
            {
                "type": "futures",
                "data": {
                    "status": "open",
                    "updated_at": "2026-05-15T00:00:00+00:00",
                },
            },
            now=now,
        )
        completed_event = diagnose_stale_card_root_cause(
            {
                "type": "event",
                "data": {
                    "status": "completed",
                    "commence_time": "2026-05-17T00:00:00+00:00",
                },
            },
            now=now,
        )

        assert closed["label"] == "Market is closed or resolved"
        assert stale_update["code"] == "no_recent_market_update"
        assert completed_event["reason"] == "completed_old"

    def test_ground_truth_matching_normalizes_us_punctuation(self):
        debug = build_feed_quality_debug(
            [
                {
                    "type": "futures",
                    "score": 93,
                    "headline": "Yes side up 2.7 points today",
                    "reason": "Yes side moved today",
                    "data": {
                        "id": 109435,
                        "name": "Will the U.S. confirm that aliens exist before 2027?",
                        "llm_sport_category": "tech",
                        "source": "kalshi",
                        "top_outcomes": [{"name": "Yes", "probability": 0.12}],
                    },
                }
            ],
            ground_truth_items=[
                {
                    "source": "polymarket",
                    "category": "trending",
                    "name": "Will the US confirm that aliens exist before 2027?",
                    "probability": "Yes 12%, No 88%",
                }
            ],
            top_n=1,
        )

        assert debug["summary"]["ground_truth_hit_count_50"] == 1
        assert debug["missing_ground_truth"] == []

    def test_trace_search_tokens_ignore_win_for_advance_markets(self):
        tokens = _trace_search_tokens("Will the Boston Celtics win the 2026 NBA Finals?")

        assert tokens[:3] == ["boston", "celtics", "nba"]
        assert "win" not in tokens

    def test_ground_truth_matching_treats_win_and_advance_as_same_finals_story(self):
        debug = build_feed_quality_debug(
            [
                {
                    "type": "futures",
                    "score": 100,
                    "headline": "No side up 42.5 points from opening",
                    "reason": "No side shifted from opening",
                    "data": {
                        "id": 13805266,
                        "name": "Will Boston Celtics advance to the 2026 NBA Finals?",
                        "llm_sport_category": "basketball",
                        "source": "polymarket",
                        "top_outcomes": [{"name": "No", "probability": 0.58}],
                    },
                }
            ],
            ground_truth_items=[
                {
                    "source": "polymarket",
                    "category": "trending",
                    "name": "Will the Boston Celtics win the 2026 NBA Finals?",
                    "probability": "Yes 42%, No 58%",
                }
            ],
            top_n=1,
        )

        assert debug["summary"]["ground_truth_hit_count_50"] == 1
        assert debug["missing_ground_truth"] == []

    def test_ground_truth_matching_treats_recession_year_phrasings_as_same_story(self):
        debug = build_feed_quality_debug(
            [
                {
                    "type": "futures",
                    "score": 100,
                    "headline": "Tracked by 2 sources",
                    "reason": "Multi-source recession market",
                    "data": {
                        "id": 108622,
                        "name": "US recession by end of 2026?",
                        "llm_sport_category": "economics",
                        "source": "kalshi",
                        "top_outcomes": [{"name": "Yes", "probability": 0.28}],
                    },
                }
            ],
            ground_truth_items=[
                {
                    "source": "kalshi",
                    "category": "Economics",
                    "name": "Recession this year?",
                    "probability": "Yes 28%, No 72%",
                }
            ],
            top_n=1,
        )

        assert debug["summary"]["ground_truth_hit_count_50"] == 1
        assert debug["missing_ground_truth"] == []

    def test_missing_ground_truth_db_trace_explains_no_match(self):
        trace = summarize_missing_ground_truth_db_trace(
            {"name": "Will OpenAI announce GPT-6 in 2026?"},
            [],
        )

        assert trace["trace_status"] == "no_db_match"
        assert "ingestion" in trace["recommended_action"].lower()

    def test_missing_ground_truth_db_trace_explains_eligible_match(self):
        trace = summarize_missing_ground_truth_db_trace(
            {"name": "Will OpenAI announce GPT-6 in 2026?"},
            [
                {
                    "id": 123,
                    "name": "Will OpenAI announce GPT-6 in 2026?",
                    "source": "kalshi",
                    "status": "open",
                    "event_id": None,
                    "llm_sport_category": "tech",
                    "volume_24h": 2000,
                    "resolution_date": None,
                }
            ],
        )

        assert trace["trace_status"] == "eligible_but_not_top_50"
        assert trace["matches"][0]["blocked_reasons"] == []

    def test_missing_ground_truth_db_trace_explains_game_market_block(self):
        trace = summarize_missing_ground_truth_db_trace(
            {"name": "Pistons vs. Magic"},
            [
                {
                    "id": 124,
                    "name": "Pistons vs. Magic",
                    "source": "polymarket",
                    "status": "open",
                    "event_id": 55,
                    "llm_sport_category": "basketball",
                    "volume_24h": 2000,
                    "resolution_date": None,
                }
            ],
        )

        assert trace["trace_status"] == "blocked:event_linked_game_market"
        assert "event_linked_game_market" in trace["matches"][0]["blocked_reasons"]

    def test_discover_market_base_trace_blocks_event_linked_games(self):
        trace = _market_base_trace(
            SimpleNamespace(
                status="open",
                event_id=55,
                resolution_date=datetime.now(timezone.utc) + timedelta(days=1),
                name="Pistons vs. Magic",
            ),
            datetime.now(timezone.utc),
        )

        assert trace["eligible"] is False
        assert "event_linked_game_market" in trace["blockers"]
        assert "game_name_filtered" in trace["blockers"]

    def test_discover_runtime_trace_ignores_past_commence_for_open_futures(self):
        now = datetime.now(timezone.utc)
        trace = _market_runtime_filter_trace(
            SimpleNamespace(
                updated_at=now,
                commence_time=now - timedelta(days=30),
            ),
            [
                {"name": "Yes", "probability": 0.45, "probability_change_24h": 0, "opening_probability": 0.4},
                {"name": "No", "probability": 0.55, "probability_change_24h": 0, "opening_probability": 0.6},
            ],
            "No",
            0.55,
            now,
        )

        assert trace["eligible"] is True
        assert trace["blockers"] == []
        assert trace["checks"]["commence_time_staleness_applied"] is False

    def test_sports_futures_resolve_at_lower_probability_threshold(self):
        now = datetime.now(timezone.utc)
        trace = _market_runtime_filter_trace(
            SimpleNamespace(
                updated_at=now,
                commence_time=None,
            ),
            [
                {
                    "name": "No",
                    "probability": 0.92,
                    "probability_change_24h": 0,
                    "opening_probability": 0.75,
                },
                {
                    "name": "Yes",
                    "probability": 0.08,
                    "probability_change_24h": 0,
                    "opening_probability": 0.25,
                },
            ],
            "No",
            0.92,
            now,
            sport_category="basketball",
        )

        assert trace["eligible"] is False
        assert "effectively_resolved" in trace["blockers"]
        assert trace["checks"]["effective_resolution_threshold"] == 0.90

    def test_non_sports_futures_keep_generic_resolved_threshold(self):
        now = datetime.now(timezone.utc)
        trace = _market_runtime_filter_trace(
            SimpleNamespace(
                updated_at=now,
                commence_time=None,
            ),
            [
                {
                    "name": "No",
                    "probability": 0.92,
                    "probability_change_24h": 0,
                    "opening_probability": 0.75,
                },
                {
                    "name": "Yes",
                    "probability": 0.08,
                    "probability_change_24h": 0,
                    "opening_probability": 0.25,
                },
            ],
            "No",
            0.92,
            now,
            sport_category="politics",
        )

        assert trace["eligible"] is True
        assert "effectively_resolved" not in trace["blockers"]
        assert trace["checks"]["effective_resolution_threshold"] == 0.95

    def test_sports_futures_with_real_surprise_can_still_surface(self):
        now = datetime.now(timezone.utc)
        trace = _market_runtime_filter_trace(
            SimpleNamespace(
                updated_at=now,
                commence_time=None,
            ),
            [
                {
                    "name": "Yes",
                    "probability": 0.91,
                    "probability_change_24h": 0.12,
                    "opening_probability": 0.18,
                },
                {
                    "name": "No",
                    "probability": 0.09,
                    "probability_change_24h": -0.12,
                    "opening_probability": 0.82,
                },
            ],
            "Yes",
            0.91,
            now,
            sport_category="hockey",
        )

        assert trace["eligible"] is True
        assert "effectively_resolved" not in trace["blockers"]

    def test_soft_settled_binary_suppresses_stale_sports_elimination(self):
        """A basketball binary market at 69% No with no movement = soft settled."""
        now = datetime.now(timezone.utc)
        trace = _market_runtime_filter_trace(
            SimpleNamespace(
                updated_at=now,
                commence_time=None,
            ),
            [
                {
                    "name": "No",
                    "probability": 0.69,
                    "probability_change_24h": 0.003,
                    "opening_probability": 0.55,
                },
                {
                    "name": "Yes",
                    "probability": 0.31,
                    "probability_change_24h": -0.003,
                    "opening_probability": 0.45,
                },
            ],
            "No",
            0.69,
            now,
            sport_category="basketball",
        )

        assert trace["eligible"] is False
        assert "soft_settled_binary" in trace["blockers"]
        assert trace["checks"]["soft_settled_binary"] is True

    def test_soft_settled_binary_allows_active_sports_market(self):
        """A basketball binary market at 65% with significant movement = keep it."""
        now = datetime.now(timezone.utc)
        trace = _market_runtime_filter_trace(
            SimpleNamespace(
                updated_at=now,
                commence_time=None,
            ),
            [
                {
                    "name": "Yes",
                    "probability": 0.65,
                    "probability_change_24h": 0.05,
                    "opening_probability": 0.50,
                },
                {
                    "name": "No",
                    "probability": 0.35,
                    "probability_change_24h": -0.05,
                    "opening_probability": 0.50,
                },
            ],
            "Yes",
            0.65,
            now,
            sport_category="basketball",
        )

        assert trace["eligible"] is True
        assert "soft_settled_binary" not in trace["blockers"]

    def test_soft_settled_binary_does_not_apply_to_politics(self):
        """A politics binary market at 69% with no movement should stay eligible."""
        now = datetime.now(timezone.utc)
        trace = _market_runtime_filter_trace(
            SimpleNamespace(
                updated_at=now,
                commence_time=None,
            ),
            [
                {
                    "name": "No",
                    "probability": 0.69,
                    "probability_change_24h": 0.001,
                    "opening_probability": 0.55,
                },
                {
                    "name": "Yes",
                    "probability": 0.31,
                    "probability_change_24h": -0.001,
                    "opening_probability": 0.45,
                },
            ],
            "No",
            0.69,
            now,
            sport_category="politics",
        )

        assert trace["eligible"] is True
        assert "soft_settled_binary" not in trace["blockers"]

    def test_soft_settled_binary_spares_underdog_rise(self):
        """Sports binary at 65% where leader opened at 30% = genuine story, keep it."""
        now = datetime.now(timezone.utc)
        trace = _market_runtime_filter_trace(
            SimpleNamespace(
                updated_at=now,
                commence_time=None,
            ),
            [
                {
                    "name": "Yes",
                    "probability": 0.65,
                    "probability_change_24h": 0.005,
                    "opening_probability": 0.30,
                },
                {
                    "name": "No",
                    "probability": 0.35,
                    "probability_change_24h": -0.005,
                    "opening_probability": 0.70,
                },
            ],
            "Yes",
            0.65,
            now,
            sport_category="hockey",
        )

        assert trace["eligible"] is True
        assert "soft_settled_binary" not in trace["blockers"]

    def test_soft_settled_binary_does_not_apply_to_multi_outcome(self):
        """Multi-outcome sports market at 60% leader should not be soft-settled."""
        now = datetime.now(timezone.utc)
        trace = _market_runtime_filter_trace(
            SimpleNamespace(
                updated_at=now,
                commence_time=None,
            ),
            [
                {
                    "name": "Team A",
                    "probability": 0.60,
                    "probability_change_24h": 0.001,
                    "opening_probability": 0.55,
                },
                {
                    "name": "Team B",
                    "probability": 0.25,
                    "probability_change_24h": 0.001,
                    "opening_probability": 0.25,
                },
                {
                    "name": "Team C",
                    "probability": 0.15,
                    "probability_change_24h": -0.002,
                    "opening_probability": 0.20,
                },
            ],
            "Team A",
            0.60,
            now,
            sport_category="basketball",
        )

        assert trace["eligible"] is True
        assert "soft_settled_binary" not in trace["blockers"]

    def test_canonical_dedupe_does_not_collapse_unrelated_yes_no_markets(self):
        china_invade = {
            "data": {
                "name": "Will China invade Taiwan by end of 2026?",
                "top_outcomes": [{"name": "Yes"}, {"name": "No"}],
            }
        }
        trump_china = {
            "data": {
                "name": "Will Trump visit China on May 13?",
                "top_outcomes": [{"name": "Yes"}, {"name": "No"}],
            }
        }

        assert _outcomes_overlap(china_invade, trump_china) is False

    def test_canonical_dedupe_keeps_similar_yes_no_markets_collapsible(self):
        kalshi = {
            "data": {
                "name": "Will the U.S. confirm that aliens exist before 2027?",
                "top_outcomes": [{"name": "Yes"}, {"name": "No"}],
            }
        }
        polymarket = {
            "data": {
                "name": "Will the US confirm that aliens exist by...?",
                "top_outcomes": [{"name": "Yes"}, {"name": "No"}],
            }
        }

        assert _outcomes_overlap(kalshi, polymarket) is True

    def test_strong_hook_boosts_score(self):
        quality = classify_market_quality(
            "Will GameStop acquire eBay?",
            sport_category="economics",
        )
        hook = "A surprise acquisition would reshape the meme-stock story and signal a much bigger retail strategy."

        assert has_strong_hook(hook)
        assert apply_explanation_quality_score(
            88,
            hook_description=hook,
            headline="Multi-source",
            quality=quality,
        ) == 93

    def test_generic_explanation_caps_normal_market(self):
        quality = classify_market_quality(
            "PGA Tour: Truist Championship Top 20",
            sport_category="golf",
        )

        assert not has_specific_explanation(
            hook_description=None,
            headline="New favorite",
            quality=quality,
        )
        assert apply_explanation_quality_score(
            94,
            hook_description=None,
            headline="New favorite",
            quality=quality,
        ) == 90

    def test_health_outbreak_counts_as_specific_without_hook(self):
        quality = classify_market_quality(
            "Hantavirus pandemic in 2026?",
            sport_category="health",
        )

        assert has_specific_explanation(
            hook_description=None,
            headline="Multi-source",
            quality=quality,
        )
        assert apply_explanation_quality_score(
            100,
            hook_description=None,
            headline="Multi-source",
            quality=quality,
        ) == 100


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

    def test_cap_uses_story_key_for_low_quality_story_families(self):
        items = [
            {
                "score": 100,
                "_quality_class": "low_quality",
                "_quality_family_key": "ky 04 republican nominee",
                "_quality_story_key": "story:regional_us_elections",
            },
            {
                "score": 95,
                "_quality_class": "low_quality",
                "_quality_family_key": "ok 01 republican nominee",
                "_quality_story_key": "story:regional_us_elections",
            },
            {
                "score": 90,
                "_quality_class": "low_quality",
                "_quality_family_key": "women table tennis winner",
                "_quality_story_key": "story:niche_low_signal_sports",
            },
        ]

        capped = cap_low_quality_families(items, cap=1)

        assert len(capped) == 2
        assert [i["_quality_story_key"] for i in capped] == [
            "story:regional_us_elections",
            "story:niche_low_signal_sports",
        ]


class TestQualityFamilyDiversity:
    def test_diversify_caps_exact_duplicate_families(self):
        items = [
            {
                "score": 100,
                "_quality_class": "compelling",
                "_quality_family_key": "russia x ukraine ceasefire by <month> <num> <num>",
                "_quality_story_key": "story:russia_ukraine",
            },
            {
                "score": 95,
                "_quality_class": "compelling",
                "_quality_family_key": "russia x ukraine ceasefire by <month> <num> <num>",
                "_quality_story_key": "story:russia_ukraine",
            },
            {
                "score": 94,
                "_quality_class": "normal",
                "_quality_family_key": "pga tour top 20",
                "_quality_story_key": None,
            },
        ]

        capped = diversify_quality_families(items, exact_family_cap=1, story_family_cap=5)

        assert len(capped) == 2
        assert capped[0]["score"] == 100
        assert any(i["_quality_family_key"] == "pga tour top 20" for i in capped)

    def test_diversify_caps_hot_story_without_removing_all_cards(self):
        items = [
            {
                "score": 100 - i,
                "_quality_class": "compelling",
                "_quality_family_key": f"middle east variant {i}",
                "_quality_story_key": "story:middle_east_conflict",
            }
            for i in range(6)
        ]
        items.append({
            "score": 80,
            "_quality_class": "compelling",
            "_quality_family_key": "openai valuation",
            "_quality_story_key": "story:ai",
        })

        capped = diversify_quality_families(items, exact_family_cap=1, story_family_cap=3)

        middle_east = [
            i for i in capped
            if i["_quality_story_key"] == "story:middle_east_conflict"
        ]
        assert len(middle_east) == 3
        assert any(i["_quality_story_key"] == "story:ai" for i in capped)

    def test_diversify_uses_tighter_caps_for_some_story_families(self):
        items = [
            {
                "score": 100 - i,
                "_quality_class": "compelling",
                "_quality_family_key": f"2028 election variant {i}",
                "_quality_story_key": "story:us_2028_election",
            }
            for i in range(4)
        ]
        items.extend([
            {
                "score": 90 - i,
                "_quality_class": "normal",
                "_quality_family_key": f"government stake variant {i}",
                "_quality_story_key": "story:us_government_stakes",
            }
            for i in range(4)
        ])

        capped = diversify_quality_families(items, exact_family_cap=1, story_family_cap=5)

        election = [
            i for i in capped
            if i["_quality_story_key"] == "story:us_2028_election"
        ]
        stakes = [
            i for i in capped
            if i["_quality_story_key"] == "story:us_government_stakes"
        ]
        assert len(election) == 2
        assert len(stakes) == 2

    def test_diversify_caps_russia_war_territory_story_to_two(self):
        names = [
            "Will Russia capture Kharkiv before July?",
            "Will Russia capture Sumy before July?",
            "Will Russia advance toward Dnipro before July?",
            "Will Russia launch an offensive near Pokrovsk?",
        ]
        items = []
        for idx, name in enumerate(names):
            quality = classify_market_quality(name, sport_category="geopolitics")
            items.append({
                "score": 100 - idx,
                "_quality_class": quality.quality_class,
                "_quality_family_key": quality.family_key,
                "_quality_story_key": quality.story_key,
            })
        items.append({
            "score": 80,
            "_quality_class": "compelling",
            "_quality_family_key": "openai release gpt 5",
            "_quality_story_key": "story:ai",
        })

        capped = diversify_quality_families(items, exact_family_cap=1, story_family_cap=5)

        russia_war = [
            i for i in capped
            if i["_quality_story_key"] == "story:russia_ukraine"
        ]
        assert len(russia_war) == 2
        assert [i["score"] for i in russia_war] == [100, 99]
        assert any(i["_quality_story_key"] == "story:ai" for i in capped)

    def test_diversify_caps_minor_soccer_story_to_one(self):
        items = [
            {
                "score": 100,
                "_quality_class": "compelling",
                "_quality_family_key": "chilean primera division",
                "_quality_story_key": "story:minor_soccer_leagues",
            },
            {
                "score": 95,
                "_quality_class": "compelling",
                "_quality_family_key": "peruvian liga 1",
                "_quality_story_key": "story:minor_soccer_leagues",
            },
            {
                "score": 90,
                "_quality_class": "compelling",
                "_quality_family_key": "premier league",
                "_quality_story_key": None,
            },
        ]

        capped = diversify_quality_families(items, exact_family_cap=1, story_family_cap=5)

        minor_soccer = [
            item for item in capped
            if item["_quality_story_key"] == "story:minor_soccer_leagues"
        ]
        assert len(minor_soccer) == 1
        assert minor_soccer[0]["score"] == 100
        assert any(item["_quality_family_key"] == "premier league" for item in capped)

    def test_diversify_caps_aliens_disclosure_story_to_two(self):
        names = [
            "Will the US confirm that aliens exist by...?",
            "Will Trump release new UFO files before 2027?",
            "Japan declassifies new UFO files in 2026?",
            "Will the U.S. confirm that aliens exist before 2027?",
        ]
        items = []
        for idx, name in enumerate(names):
            quality = classify_market_quality(name, sport_category="culture")
            items.append({
                "score": 100 - idx,
                "_quality_class": quality.quality_class,
                "_quality_family_key": quality.family_key,
                "_quality_story_key": quality.story_key,
            })
        items.append({
            "score": 80,
            "_quality_class": "compelling",
            "_quality_family_key": "fed rates",
            "_quality_story_key": "story:macro_rates",
        })

        capped = diversify_quality_families(items, exact_family_cap=1, story_family_cap=5)

        aliens = [
            item for item in capped
            if item["_quality_story_key"] == "story:aliens_disclosure"
        ]
        assert len(aliens) == 2
        assert [item["score"] for item in aliens] == [100, 99]
        assert any(item["_quality_story_key"] == "story:macro_rates" for item in capped)

    def test_diversify_hard_caps_regional_and_niche_low_signal_stories(self):
        items = [
            {
                "score": 100 - i,
                "_quality_class": "low_quality",
                "_quality_family_key": f"regional race {i}",
                "_quality_story_key": "story:regional_us_elections",
            }
            for i in range(4)
        ]
        items.extend([
            {
                "score": 90 - i,
                "_quality_class": "low_quality",
                "_quality_family_key": f"table tennis {i}",
                "_quality_story_key": "story:niche_low_signal_sports",
            }
            for i in range(3)
        ])

        capped = diversify_quality_families(items, exact_family_cap=1, story_family_cap=5)

        regional = [
            i for i in capped
            if i["_quality_story_key"] == "story:regional_us_elections"
        ]
        niche = [
            i for i in capped
            if i["_quality_story_key"] == "story:niche_low_signal_sports"
        ]
        assert len(regional) == 1
        assert len(niche) == 1


class TestDiscoverFirstPageMixer:
    def _item(self, idx: int, category: str, score: int = 100, name: str | None = None, story_key: str | None = None):
        return {
            "type": "futures",
            "score": score,
            "_quality_story_key": story_key,
            "data": {
                "id": idx,
                "name": name or f"{category} market {idx}",
                "llm_sport_category": category,
            },
        }

    def test_mixer_caps_politics_in_first_page_without_dropping_items(self):
        items = [
            self._item(i, "politics", 100 - i)
            for i in range(8)
        ] + [
            self._item(100 + i, category, 80 - i)
            for i, category in enumerate([
                "tech",
                "entertainment",
                "weather",
                "economics",
                "geopolitics",
                "golf",
            ])
        ]

        mixed = diversify_discover_first_page(items, first_page_size=8)
        first_page = mixed[:8]

        assert len(mixed) == len(items)
        assert sum(
            1 for item in first_page
            if item["data"]["llm_sport_category"] == "politics"
        ) <= 5
        assert any(item["data"]["llm_sport_category"] == "tech" for item in first_page)
        assert any(item["data"]["llm_sport_category"] == "entertainment" for item in first_page)

    def test_mixer_fills_when_category_caps_are_tighter_than_available_categories(self):
        items = [self._item(i, "politics", 100 - i) for i in range(7)]

        mixed = diversify_discover_first_page(items, first_page_size=7)

        assert [item["data"]["id"] for item in mixed] == list(range(7))

    def test_mixer_caps_world_event_archetype_when_other_stories_are_available(self):
        items = [
            self._item(
                i,
                "geopolitics",
                100 - i,
                name=f"Will Iran conflict variant {i} happen?",
                story_key="story:middle_east_conflict",
            )
            for i in range(8)
        ] + [
            self._item(100, "tech", 80, name="OpenAI $1T+ valuation in 2026?"),
            self._item(101, "entertainment", 79, name='Will "Super Bowl" be said on ICEMAN?'),
            self._item(102, "weather", 78, name="Hantavirus pandemic in 2026?"),
            self._item(103, "economics", 77, name="How many Fed rate cuts in 2026?"),
            self._item(104, "golf", 76, name="PGA Tour: Truist Championship Top 20"),
            self._item(105, "politics", 75, name="2028 U.S. Presidential Election winner?"),
        ]

        mixed = diversify_discover_first_page(items, first_page_size=8)
        first_page = mixed[:8]

        world_events = [
            item for item in first_page
            if editorial_archetype(
                item["data"]["name"],
                item["data"]["llm_sport_category"],
            ) == "world_event"
        ]
        middle_east = [
            item for item in first_page
            if item.get("_quality_story_key") == "story:middle_east_conflict"
        ]

        assert len(world_events) <= 4
        assert len(middle_east) <= 2
        assert any(item["data"]["llm_sport_category"] == "tech" for item in first_page)
        assert any(item["data"]["llm_sport_category"] == "entertainment" for item in first_page)

    def test_mixer_repairs_top_10_non_political_texture(self):
        items = [
            self._item(i, "politics", 100 - i, name=f"2028 election variant {i}")
            for i in range(7)
        ] + [
            self._item(100, "economics", 94, name="How many Fed rate cuts in 2026?"),
            self._item(101, "entertainment", 93, name="Eurovision Winner 2026?"),
            self._item(102, "tech", 92, name="Gemini 3.2 released by...?"),
            self._item(103, "weather", 91, name="Hantavirus pandemic in 2026?"),
        ]

        mixed = diversify_discover_first_page(items, first_page_size=11)
        top10 = mixed[:10]

        assert sum(
            1 for item in top10
            if item["data"]["llm_sport_category"] not in {"politics", "geopolitics"}
        ) >= 4

    def test_mixer_pulls_strong_weird_news_into_first_page(self):
        items = [
            self._item(i, "politics", 100 - i, name=f"2028 election variant {i}")
            for i in range(5)
        ] + [
            self._item(100, "economics", 94, name="Fed Decision in July?"),
            self._item(101, "entertainment", 93, name='Will "Super Bowl" be said on ICEMAN?'),
            self._item(102, "weather", 92, name="Hantavirus pandemic in 2026?"),
            self._item(103, "golf", 91, name="PGA Tour: Truist Championship Top 20"),
            self._item(104, "tech", 90, name="Will the U.S. confirm that aliens exist before 2027?"),
        ]

        mixed = diversify_discover_first_page(items, first_page_size=8)
        first_page = mixed[:8]

        assert any(
            editorial_archetype(
                item["data"]["name"],
                item["data"]["llm_sport_category"],
            ) == "absurd_but_real"
            for item in first_page
        )

    def test_mixer_pulls_real_fun_market_into_top_10(self):
        items = [
            self._item(i, "politics", 100 - i, name=f"2028 election variant {i}")
            for i in range(5)
        ] + [
            self._item(100, "economics", 95, name="How many Fed rate cuts in 2026?"),
            self._item(101, "basketball", 94, name="Will Cleveland Cavaliers advance to the 2026 NBA Finals?"),
            self._item(102, "geopolitics", 93, name="US-Iran nuclear deal by May 31?"),
            self._item(103, "tech", 92, name="GPT-5.6 released by...?"),
            self._item(104, "economics", 91, name="Fed Decision in July?"),
            self._item(105, "entertainment", 90, name="Will Taylor Swift be pregnant in 2026?"),
        ]

        mixed = diversify_discover_first_page(items, first_page_size=11)
        top10 = mixed[:10]

        assert any(
            editorial_archetype(
                item["data"]["name"],
                item["data"]["llm_sport_category"],
            ) in {"culture_moment", "absurd_but_real", "big_name", "sports_drama", "weird_news"}
            for item in top10
        )

    def test_editorial_tail_backfill_preserves_top_20_and_adds_recall_story(self):
        items = [
            self._item(i, "economics", 100, name=f"Company IPO Closing Market Cap {i}")
            for i in range(55)
        ]
        items.extend([
            self._item(1000, "entertainment", 99, name="Who will win Survivor Season 50?"),
            self._item(1001, "geopolitics", 93, name="Xi Jinping out before 2027?"),
        ])

        mixed = backfill_discover_editorial_tail(items, window_size=50, preserve_top=20)

        assert [item["data"]["id"] for item in mixed[:20]] == list(range(20))
        top50_names = [item["data"]["name"] for item in mixed[:50]]
        assert "Who will win Survivor Season 50?" in top50_names
        assert "Xi Jinping out before 2027?" in top50_names

    def test_editorial_tail_backfill_adds_2028_presidential_story(self):
        items = [
            self._item(i, "economics", 100, name=f"Company IPO Closing Market Cap {i}")
            for i in range(55)
        ]
        items.append(
            self._item(1000, "politics", 100, name="2028 U.S. Presidential Election winner?")
        )

        mixed = backfill_discover_editorial_tail(items, window_size=50, preserve_top=20)

        assert "2028 U.S. Presidential Election winner?" in [
            item["data"]["name"] for item in mixed[:50]
        ]

    def test_editorial_tail_backfill_does_not_replace_much_stronger_cards(self):
        items = [
            self._item(i, "economics", 100, name=f"Strong macro story {i}")
            for i in range(50)
        ]
        items.append(
            self._item(1000, "soccer", 70, name="2026 FIFA World Cup: Nation to Reach Final")
        )

        mixed = backfill_discover_editorial_tail(items, window_size=50, preserve_top=20)

        assert "2026 FIFA World Cup: Nation to Reach Final" not in [
            item["data"]["name"] for item in mixed[:50]
        ]

    def test_event_category_mix_defers_over_budget_soccer_events(self):
        items = [
            {
                "type": "event",
                "score": 70,
                "data": {"id": i, "sport": "soccer_france_ligue_two"},
            }
            for i in range(7)
        ] + [
            self._item(100, "entertainment", 69, name="Eurovision Winner 2026?"),
        ]

        mixed = balance_discover_event_category_mix(items)
        entertainment_index = next(
            idx for idx, item in enumerate(mixed)
            if item["type"] == "futures"
        )

        assert entertainment_index == 5
        assert [item["data"]["id"] for item in mixed[-2:]] == [5, 6]

    def test_event_category_mix_defers_low_score_events_behind_futures(self):
        event = {
            "type": "event",
            "score": 35,
            "data": {"id": 1, "sport": "baseball_mlb"},
        }
        future = self._item(2, "tech", 34, name="OpenAI $1T+ valuation in 2026?")

        mixed = balance_discover_event_category_mix([event, future])

        assert mixed == [future, event]

    def test_mixer_gives_entertainment_floor_to_strong_candidate(self):
        items = [
            self._item(i, "geopolitics", 100 - i, name=f"Will Russia conflict variant {i} happen?")
            for i in range(6)
        ] + [
            self._item(100, "politics", 93, name="2028 U.S. Presidential Election winner?"),
            self._item(101, "economics", 92, name="How many Fed rate cuts in 2026?"),
            self._item(102, "tech", 91, name="GPT-5.6 released by...?"),
            self._item(103, "entertainment", 80, name="Eurovision Winner 2026?"),
        ]

        mixed = diversify_discover_first_page(items, first_page_size=8)
        first_page = mixed[:8]

        assert any(
            item["data"]["llm_sport_category"] == "entertainment"
            for item in first_page
        )

    def test_category_hunger_preserves_required_archetype_singletons(self):
        items = [
            self._item(1, "politics", 100, name="2028 U.S. Presidential Election winner?"),
            self._item(2, "politics", 99, name="Will China invade Taiwan by June 30, 2026?"),
            self._item(3, "politics", 98, name="Will Elon Musk announce Presidential run before 2027?"),
            self._item(4, "tech", 97, name="Anthropic IPO Closing Market Cap"),
            self._item(5, "tech", 96, name="SpaceX IPO Closing Market Cap"),
            self._item(6, "economics", 95, name="How many Fed rate cuts in 2026?"),
            self._item(7, "entertainment", 94, name="Taylor Swift pregnant before marriage?"),
            self._item(8, "basketball", 93, name="Will New York Knicks advance to the 2026 NBA Finals?"),
            self._item(9, "tech", 92, name="Gemini 3.5 released by...?"),
            self._item(10, "weather", 91, name="Hantavirus pandemic in 2026?"),
        ]

        mixed = diversify_discover_first_page(items, first_page_size=8)
        first_page = mixed[:8]
        archetypes = {
            editorial_archetype(
                item["data"]["name"],
                item["data"]["llm_sport_category"],
            )
            for item in first_page
        }

        assert "tech_frontier" in archetypes
        assert "health_weather_risk" in archetypes


class TestEditorialArchetypes:
    def test_editorial_archetype_detects_positive_story_roles(self):
        examples = {
            "Will China invade Taiwan by end of 2026?": "world_event",
            "Next US x Iran diplomatic meeting on...?": "breaking_news",
            "OpenAI $1T+ valuation in 2026?": "tech_frontier",
            "How many Fed rate cuts in 2026?": "macro_signal",
            'Will "Super Bowl" be said on ICEMAN?': "culture_moment",
            "Hantavirus pandemic in 2026?": "health_weather_risk",
            "PGA Tour: Truist Championship Top 20": "sports_story",
            "Will Mike Vrabel be fired before the Patriots' next game?": "sports_drama",
            "Will Elon win his case against OpenAI?": "company_drama",
            "Will the U.S. confirm that aliens exist before 2027?": "absurd_but_real",
            "Will Taylor Swift be pregnant in 2026?": "absurd_but_real",
        }

        for name, expected in examples.items():
            assert editorial_archetype(name, None) == expected
