from app.utils.feed_reasons import (
    generate_futures_context_summary,
    generate_futures_headline,
    generate_futures_reason,
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


def test_futures_reason_explains_opening_surprise_with_market_context():
    reason = generate_futures_reason(
        market_name="Fed Decision in July?",
        highlight_reasons=["major_surprise"],
        top_surprise_name="No change",
        top_surprise_change=0.21,
    )

    assert reason == "No change moved up 21.0 points from opening in Fed Decision in July?"


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


def test_futures_context_summary_combines_signal_and_leader():
    summary = generate_futures_context_summary(
        headline="Yes side up 10.2 points today",
        highlight_reasons=["moderate_movement_24h"],
        leader_name="No",
        leader_probability=0.88,
    )

    assert summary == "Yes side up 10.2 points today; No leads at 88%"
