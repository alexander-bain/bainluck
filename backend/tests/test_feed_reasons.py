from app.utils.feed_reasons import (
    generate_event_reason,
    generate_futures_context_summary,
    generate_futures_headline,
    generate_futures_reason,
    humanize_binary_outcome_name,
    humanize_outcome_names_for_feed,
)


def test_futures_headline_names_major_mover():
    headline = generate_futures_headline(
        highlight_reasons=["major_movement_24h"],
        top_mover_name="OpenAI",
        top_mover_change=0.123,
    )

    assert headline == "OpenAI up 12.3 points today"


def test_futures_headline_names_opening_surprise():
    headline = generate_futures_headline(
        highlight_reasons=["major_surprise"],
        top_surprise_name="Fed cut",
        top_surprise_change=-0.187,
    )

    assert headline == "Fed cut down 18.7 points from opening"


def test_futures_headline_uses_market_context_for_numeric_outcome_labels():
    headline = generate_futures_headline(
        highlight_reasons=["major_surprise"],
        top_surprise_name="9",
        top_surprise_change=0.65,
        market_name="How many spots will Drake have in the Billboard top 10?",
    )

    assert (
        headline
        == "How many spots will Drake have in the Billboard top 10 shifted 65.0 points"
    )


def test_futures_headline_uses_market_context_for_date_outcome_labels():
    headline = generate_futures_headline(
        highlight_reasons=["major_surprise"],
        top_surprise_name="May 18",
        top_surprise_change=-0.505,
        market_name="Iran closes its airspace by...?",
    )

    assert headline == "Iran closes its airspace by... shifted 50.5 points"


def test_futures_reason_explains_opening_surprise_with_market_context():
    reason = generate_futures_reason(
        market_name="Fed Decision in July?",
        highlight_reasons=["major_surprise"],
        top_surprise_name="No change",
        top_surprise_change=0.21,
    )

    assert (
        reason == "No change moved up 21.0 points from opening in Fed Decision in July?"
    )


def test_futures_reason_uses_market_context_for_weak_outcome_labels():
    reason = generate_futures_reason(
        market_name="How many Fed rate cuts in 2026?",
        highlight_reasons=["major_surprise"],
        top_surprise_name="0 (0 bps)",
        top_surprise_change=0.593,
    )

    assert reason == "Big shift from opening in How many Fed rate cuts in 2026?"


def test_futures_reason_describes_movement_as_points_not_percent():
    reason = generate_futures_reason(
        market_name="NFL MVP",
        highlight_reasons=["major_movement_24h"],
        top_mover_name="Patrick Mahomes",
        top_mover_change=0.08,
    )

    assert reason == "Patrick Mahomes moved up 8.0 points today in NFL MVP"


def test_futures_reason_names_leader_when_sources_disagree():
    reason = generate_futures_reason(
        market_name="Best Picture",
        highlight_reasons=["source_divergence"],
        leader_name="Sentimental Favorite",
        leader_probability=0.37,
        source_count=3,
    )

    assert (
        reason
        == "3 sources disagree, but Sentimental Favorite leads Best Picture at 37%"
    )


def test_futures_reason_names_leader_for_monthly_resolution():
    reason = generate_futures_reason(
        market_name="Fed Decision in June?",
        highlight_reasons=["resolving_soon_30d"],
        leader_name="No change",
        leader_probability=0.64,
    )

    assert reason == "Fed Decision in June? resolves this month, No change leads at 64%"


def test_futures_reason_names_new_favorite_without_llm_hook():
    reason = generate_futures_reason(
        market_name="2028 Democratic nominee",
        highlight_reasons=["leader_change"],
        leader_name="Gretchen Whitmer",
        leader_probability=0.28,
    )

    assert (
        reason
        == "New favorite: Gretchen Whitmer (28%) now leads 2028 Democratic nominee"
    )


def test_futures_headline_names_new_favorite_without_llm_hook():
    headline = generate_futures_headline(
        highlight_reasons=["leader_change"],
        leader_name="Gretchen Whitmer",
        leader_probability=0.28,
    )

    assert headline == "New favorite: Gretchen Whitmer (28%)"


def test_futures_reason_describes_moderate_mover_deterministically():
    reason = generate_futures_reason(
        market_name="Best Actor",
        highlight_reasons=["moderate_movement_24h"],
        top_mover_name="Colman Domingo",
        top_mover_change=-0.047,
    )

    assert reason == "Colman Domingo odds shifted down 4.7 points today in Best Actor"


def test_futures_headline_describes_moderate_opening_change_deterministically():
    headline = generate_futures_headline(
        highlight_reasons=["moderate_surprise"],
        top_surprise_name="Yes",
        top_surprise_change=-0.052,
    )

    assert headline == "Yes side down 5.2 points from opening"


def test_futures_context_summary_uses_leader_when_headline_missing():
    summary = generate_futures_context_summary(
        headline="",
        highlight_reasons=[],
        leader_name="Shohei Ohtani",
        leader_probability=0.51,
    )

    assert summary == "Shohei Ohtani leads at 51%"


def test_futures_context_summary_does_not_repeat_leader_already_in_headline():
    summary = generate_futures_context_summary(
        headline="Shohei Ohtani leads at 51%",
        highlight_reasons=[],
        leader_name="Shohei Ohtani",
        leader_probability=0.51,
    )

    assert summary == "Shohei Ohtani leads at 51%"


def test_futures_reason_falls_back_to_market_name_without_signal_detail():
    reason = generate_futures_reason(
        market_name="Will a recession begin in 2026?",
        highlight_reasons=[],
    )

    assert reason == "Will a recession begin in 2026?"


def test_futures_copy_suppresses_stale_past_resolution_markets():
    assert (
        generate_futures_headline(
            highlight_reasons=["stale_past_resolution"],
            leader_name="No",
            leader_probability=0.99,
        )
        == ""
    )
    assert (
        generate_futures_reason(
            market_name="Already resolved?",
            highlight_reasons=["stale_past_resolution"],
            leader_name="No",
            leader_probability=0.99,
        )
        == ""
    )
    assert (
        generate_futures_context_summary(
            headline="No leads at 99%",
            highlight_reasons=["stale_past_resolution"],
            leader_name="No",
            leader_probability=0.99,
        )
        == ""
    )


def test_futures_copy_suppresses_stale_markets_before_other_signals():
    highlight_reasons = [
        "stale_past_resolution",
        "major_movement_24h",
        "source_divergence",
        "major_surprise",
    ]

    assert (
        generate_futures_headline(
            highlight_reasons=highlight_reasons,
            top_mover_name="Yes",
            top_mover_change=0.31,
            top_surprise_name="Yes",
            top_surprise_change=0.44,
            leader_name="Yes",
            leader_probability=0.99,
            source_count=3,
        )
        == ""
    )
    assert (
        generate_futures_reason(
            market_name="Already resolved?",
            highlight_reasons=highlight_reasons,
            top_mover_name="Yes",
            top_mover_change=0.31,
            top_surprise_name="Yes",
            top_surprise_change=0.44,
            leader_name="Yes",
            leader_probability=0.99,
            source_count=3,
        )
        == ""
    )
    assert (
        generate_futures_context_summary(
            headline="Sources disagree (3)",
            highlight_reasons=highlight_reasons,
            leader_name="Yes",
            leader_probability=0.99,
            source_count=3,
        )
        == ""
    )


def test_futures_headline_falls_back_to_leader_when_no_signal_detail():
    headline = generate_futures_headline(
        highlight_reasons=[],
        leader_name="Jane Doe",
        leader_probability=0.42,
    )

    assert headline == "Jane Doe leads at 42%"


def test_futures_headline_formats_binary_side_naturally():
    headline = generate_futures_headline(
        highlight_reasons=["major_surprise"],
        top_surprise_name="No",
        top_surprise_change=0.3,
    )

    assert headline == "No side up 30.0 points from opening"


def test_futures_context_summary_expands_generic_resolving_copy():
    summary = generate_futures_context_summary(
        headline="Resolving this month",
        highlight_reasons=["resolving_soon_30d"],
        leader_name="No",
        leader_probability=0.61,
    )

    assert summary == "No leads at 61%; resolves this month"


def test_futures_headline_names_leader_for_monthly_resolution():
    headline = generate_futures_headline(
        highlight_reasons=["resolving_soon_30d"],
        leader_name="No",
        leader_probability=0.61,
    )

    assert headline == "No leads; resolves this month"


def test_futures_context_summary_combines_signal_and_leader():
    summary = generate_futures_context_summary(
        headline="Yes side up 10.2 points today",
        highlight_reasons=["moderate_movement_24h"],
        leader_name="No",
        leader_probability=0.88,
    )

    assert summary == "Yes side up 10.2 points today; No leads at 88%"


def test_futures_context_summary_adds_leader_to_source_disagreement_headline():
    headline = generate_futures_headline(
        highlight_reasons=["source_divergence"],
        leader_name="Sentimental Favorite",
        leader_probability=0.37,
        source_count=3,
    )

    summary = generate_futures_context_summary(
        headline=headline,
        highlight_reasons=["source_divergence"],
        leader_name="Sentimental Favorite",
        leader_probability=0.37,
        source_count=3,
    )

    assert headline == "Sources disagree (3)"
    assert summary == "Sources disagree (3); Sentimental Favorite leads at 37%"


def test_futures_context_summary_avoids_repeating_market_title_prefix():
    summary = generate_futures_context_summary(
        headline="Trump out as President by May 31 leads; resolves this month",
        highlight_reasons=["resolving_soon_30d"],
        market_name="Trump out as President by May 31?",
        leader_name="Trump out as President by May 31",
        leader_probability=0.82,
    )

    assert summary == "Resolution window is this month"


def test_event_reason_uses_category_tag_context_when_odds_reason_absent():
    reason = generate_event_reason(
        home_team="Liberty",
        away_team="Aces",
        status="scheduled",
        highlight_reasons=[],
        event_tags=["stakes:elimination"],
    )

    assert reason == "Elimination game"


def test_event_reason_prefers_odds_movement_over_category_tag_context():
    reason = generate_event_reason(
        home_team="Liberty",
        away_team="Aces",
        status="scheduled",
        highlight_reasons=["major_prob_swing"],
        home_probability=0.63,
        opening_home_prob=0.48,
        event_tags=["stakes:elimination"],
    )

    assert reason == "Liberty odds shifted 15% since open"


def test_event_reason_falls_back_to_empty_string_when_card_context_is_enough():
    reason = generate_event_reason(
        home_team="Liberty",
        away_team="Aces",
        status="scheduled",
        highlight_reasons=[],
    )

    assert reason == ""


# ── BR49: humanize_binary_outcome_name ─────────────────────────────


class TestHumanizeBinaryOutcomeName:
    """Yes/No outcomes should be replaced with meaningful entity names."""

    def test_extracts_subject_from_will_question(self):
        assert (
            humanize_binary_outcome_name("Yes", "Will Anthropic IPO first?")
            == "Anthropic"
        )

    def test_extracts_subject_openai(self):
        assert (
            humanize_binary_outcome_name("Yes", "Will OpenAI IPO before 2027?")
            == "OpenAI"
        )

    def test_extracts_subject_with_the(self):
        # "the Dodgers" — "the" is generic but "the Dodgers" is a valid entity
        result = humanize_binary_outcome_name(
            "Yes", "Will the Dodgers win the World Series?"
        )
        # "the" is first word, so falls back to truncation
        assert result != "Yes"
        assert "Dodgers" in result

    def test_no_outcome_negates_subject(self):
        result = humanize_binary_outcome_name("No", "Will Anthropic IPO first?")
        assert result == "Not Anthropic"

    def test_no_outcome_preserves_side_for_top_five_market(self):
        result = humanize_binary_outcome_name(
            "No",
            "Will Rory McIlroy finish Top 5 at the Truist Championship?",
        )
        assert result.startswith("No: ") or result.startswith("Not")
        assert not result.startswith("Rory McIlroy finish Top 5")

    def test_extracts_person_name(self):
        assert (
            humanize_binary_outcome_name(
                "Yes", "Will Taylor Swift be pregnant in 2026?"
            )
            == "Taylor Swift"
        )

    def test_extracts_elon_musk(self):
        assert (
            humanize_binary_outcome_name(
                "Yes", "Will Elon Musk step down as CEO of Tesla?"
            )
            == "Elon Musk"
        )

    def test_generic_subject_falls_back_to_truncation(self):
        result = humanize_binary_outcome_name(
            "Yes", "Will there be a government shutdown?"
        )
        assert result != "Yes"
        assert result != "there"
        assert "government shutdown" in result.lower()

    def test_non_will_question_truncates(self):
        result = humanize_binary_outcome_name(
            "Yes", "Federal Reserve interest rate above 5%?"
        )
        assert result != "Yes"
        assert "Federal Reserve" in result

    def test_passthrough_for_named_outcomes(self):
        assert (
            humanize_binary_outcome_name(
                "OpenAI", "Will Anthropic or OpenAI IPO first?"
            )
            == "OpenAI"
        )

    def test_passthrough_for_empty_name(self):
        assert humanize_binary_outcome_name("", "Will X happen?") == ""

    def test_passthrough_when_no_market_name(self):
        assert humanize_binary_outcome_name("Yes", None) == "Yes"

    def test_long_market_name_truncated(self):
        long_name = "Will the extremely long and complicated market name that goes on forever resolve positively?"
        result = humanize_binary_outcome_name("Yes", long_name)
        assert len(result) <= 40

    def test_caps_at_40_chars(self):
        # Verifies the 40-char cap on the truncation fallback
        result = humanize_binary_outcome_name(
            "Yes", "GDP growth rate for the United States exceeding expectations?"
        )
        assert len(result) <= 40

    def test_strips_year_suffix(self):
        result = humanize_binary_outcome_name(
            "Yes", "Will Bitcoin reach $100k by December 2026?"
        )
        assert result == "Bitcoin"

    def test_case_insensitive_yes_no(self):
        assert (
            humanize_binary_outcome_name("YES", "Will Anthropic IPO first?")
            == "Anthropic"
        )
        assert (
            humanize_binary_outcome_name("yes", "Will Anthropic IPO first?")
            == "Anthropic"
        )


class TestHumanizeOutcomeNamesForFeed:
    """Batch humanization for the top_outcomes list in feed cards."""

    def test_humanizes_binary_yes_no(self):
        outcomes = [
            {"name": "Yes", "probability": 0.69},
            {"name": "No", "probability": 0.31},
        ]
        result = humanize_outcome_names_for_feed(outcomes, "Will Anthropic IPO first?")
        assert result[0]["name"] == "Anthropic"
        assert result[1]["name"] == "Not Anthropic"
        # Original list not mutated
        assert outcomes[0]["name"] == "Yes"

    def test_skips_named_outcomes(self):
        outcomes = [
            {"name": "OpenAI", "probability": 0.55},
            {"name": "Anthropic", "probability": 0.35},
        ]
        result = humanize_outcome_names_for_feed(outcomes, "Who will IPO first?")
        assert result[0]["name"] == "OpenAI"
        assert result[1]["name"] == "Anthropic"

    def test_skips_mixed_outcomes(self):
        # If not ALL outcomes are Yes/No, don't humanize any
        outcomes = [
            {"name": "Yes", "probability": 0.55},
            {"name": "OpenAI", "probability": 0.35},
        ]
        result = humanize_outcome_names_for_feed(outcomes, "Will OpenAI IPO?")
        assert result[0]["name"] == "Yes"

    def test_empty_list(self):
        assert humanize_outcome_names_for_feed([], "Some market") == []

    def test_preserves_other_fields(self):
        outcomes = [
            {"id": 1, "name": "Yes", "probability": 0.69, "rank": 1, "movement": 0.05},
        ]
        result = humanize_outcome_names_for_feed(outcomes, "Will Anthropic IPO first?")
        assert result[0]["id"] == 1
        assert result[0]["probability"] == 0.69
        assert result[0]["rank"] == 1
        assert result[0]["movement"] == 0.05
