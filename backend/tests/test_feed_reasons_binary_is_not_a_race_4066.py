"""D1 clause b (#4066) — a yes/no card stops announcing a race against itself.

THE DEFECT, read off production 2026-09-08 21:07Z, `GET /api/feed?limit=20&offset=0`,
items 8 and 10 of the twenty served. Both strings are the VERBATIM wire bytes:

    item 8   name    'Will China invade Taiwan by end of 2026?'
             reason  'China invade Taiwan by end of 2026 (4%) leads Will China
                      invade Taiwan by end of 2026?'
             headline / context_summary
                     'China invade Taiwan by end of 2026 leads at 4%'
             outcome_count 1

    item 10  name    'China x Philippines military clash before 2027?'
             reason  'China x Philippines military clash moved up 37.5 points from
                      opening in China x Philippines military clash before 2027?'
             headline / context_summary
                     'China x Philippines military clash up 37.5 points from opening'
             outcome_count 1

Each market serves exactly ONE outcome, named for its own question with the
interrogative stripped, so the field templates announce the only entrant as
leading — and the reader is handed a percentage without being told what it is a
percentage OF. `outcome_count: 1` is the tell, and it is on the wire.

🔴 SCOPE THE ASSERTIONS. "leads" is a substring of nothing else these functions
emit, but "4%" appears in both the broken and the fixed output, so the fixed-state
tests name the whole clause and separately assert the served defect is ABSENT.
The two specimens' own probabilities (0.0395 -> 4%, 0.59 -> 59%) are kept because
the rounding is part of what the reader compares against the hero.
"""

from datetime import datetime, timezone

import pytest

from app.utils.feed_reasons import (
    binary_affirmative_probability,
    compose_binary_card_copy,
    format_baseline_date,
    generate_futures_context_summary,
    generate_futures_headline,
    generate_futures_reason,
)

TAIWAN = "Will China invade Taiwan by end of 2026?"
TAIWAN_OUTCOME = "China invade Taiwan by end of 2026"
TAIWAN_PROB = 0.0395

PHILIPPINES = "China x Philippines military clash before 2027?"
PHILIPPINES_OUTCOME = "China x Philippines military clash"
PHILIPPINES_PROB = 0.59

NOW = datetime(2026, 9, 8, 21, 7, tzinfo=timezone.utc)
OPENED = datetime(2026, 1, 4, 9, 30, tzinfo=timezone.utc)


# ── Recognising the shape ────────────────────────────────────────────────────


def test_a_single_outcome_market_is_a_yes_no_question():
    """Item 8's wire shape: one outcome, and its probability is the answer."""
    outcomes = [{"name": TAIWAN_OUTCOME, "probability": TAIWAN_PROB}]

    assert binary_affirmative_probability(outcomes) == pytest.approx(TAIWAN_PROB)


def test_a_literal_yes_no_pair_reports_the_yes_side_even_when_no_leads():
    """The answer to "Will X?" is the YES probability, whichever side is ahead."""
    outcomes = [
        {"name": "No", "probability": 0.74},
        {"name": "Yes", "probability": 0.26},
    ]

    assert binary_affirmative_probability(outcomes) == pytest.approx(0.26)


def test_a_real_field_is_not_a_yes_no_question():
    """A field keeps the "leads" templates — they are correct for a race."""
    outcomes = [
        {"name": "Los Angeles Dodgers", "probability": 0.305},
        {"name": "Milwaukee Brewers", "probability": 0.103},
        {"name": "New York Yankees", "probability": 0.095},
    ]

    assert binary_affirmative_probability(outcomes) is None


def test_a_two_horse_race_between_named_subjects_is_not_a_yes_no_question():
    outcomes = [
        {"name": "Alcaraz", "probability": 0.55},
        {"name": "Sinner", "probability": 0.45},
    ]

    assert binary_affirmative_probability(outcomes) is None


def test_an_outcome_with_no_probability_cannot_answer_anything():
    assert (
        binary_affirmative_probability([{"name": "Yes", "probability": None}]) is None
    )
    assert binary_affirmative_probability([]) is None


# ── The copy the reader gets ─────────────────────────────────────────────────


def test_the_taiwan_card_answers_its_question_instead_of_leading_a_race():
    copy = compose_binary_card_copy(
        market_name=TAIWAN,
        highlight_reasons=["multi_source"],
        affirmative_probability=TAIWAN_PROB,
        now=NOW,
    )

    assert copy.context_summary == "4% chance"
    assert copy.headline == "4% chance"
    assert copy.reason == "Will China invade Taiwan by end of 2026: 4% chance"

    # The served defect, gone from all three strings. Asserted as the whole
    # construction: the outcome name is a SUBSTRING of the market name here, so
    # "the outcome name is absent" would fail on the correct reason too — what
    # must be absent is the name used as a RUNNER.
    for served in (copy.reason, copy.headline, copy.context_summary):
        assert "leads" not in served
        assert f"{TAIWAN_OUTCOME} (4%)" not in served
        assert f"{TAIWAN_OUTCOME} leads at" not in served


def test_a_yes_no_card_never_names_its_own_question_as_a_runner():
    """Item 10: the "runner" was the question, so the move read as a clash moving."""
    copy = compose_binary_card_copy(
        market_name=PHILIPPINES,
        highlight_reasons=["major_surprise"],
        affirmative_probability=PHILIPPINES_PROB,
        top_surprise_change=0.375,
        top_surprise_opened_at=OPENED,
        now=NOW,
    )

    assert copy.context_summary == "Up 37.5 points since Jan 4 — now 59% chance"
    assert copy.headline == "Up 37.5 points since Jan 4"
    assert PHILIPPINES_OUTCOME not in copy.context_summary
    assert "from opening" not in copy.context_summary


def test_a_yes_no_card_leads_with_today_over_a_lifetime_move():
    copy = compose_binary_card_copy(
        market_name=PHILIPPINES,
        highlight_reasons=["major_movement_24h", "major_surprise"],
        affirmative_probability=PHILIPPINES_PROB,
        top_mover_change=0.12,
        top_surprise_change=0.375,
        top_surprise_opened_at=OPENED,
        now=NOW,
    )

    assert copy.context_summary == "Up 12 points today — now 59% chance"


def test_a_yes_no_card_leads_with_a_catalyst_over_a_lifetime_move():
    copy = compose_binary_card_copy(
        market_name=PHILIPPINES,
        highlight_reasons=["resolving_soon_7d", "major_surprise"],
        affirmative_probability=PHILIPPINES_PROB,
        top_surprise_change=0.375,
        top_surprise_opened_at=OPENED,
        now=NOW,
    )

    assert copy.context_summary == "59% chance, resolving this week"


def test_an_undated_lifetime_move_is_not_published_on_a_yes_no_card():
    """Same rule as the field templates: no baseline date, no movement sentence."""
    copy = compose_binary_card_copy(
        market_name=PHILIPPINES,
        highlight_reasons=["major_surprise"],
        affirmative_probability=PHILIPPINES_PROB,
        top_surprise_change=0.375,
        top_surprise_opened_at=None,
        now=NOW,
    )

    assert copy.context_summary == "59% chance"
    assert "37.5" not in copy.context_summary


def test_a_settled_yes_no_card_says_nothing():
    copy = compose_binary_card_copy(
        market_name=TAIWAN,
        highlight_reasons=["stale_past_resolution"],
        affirmative_probability=TAIWAN_PROB,
        now=NOW,
    )

    assert copy == ("", "", "")


def test_one_point_is_singular():
    copy = compose_binary_card_copy(
        market_name=PHILIPPINES,
        highlight_reasons=["moderate_movement_24h"],
        affirmative_probability=PHILIPPINES_PROB,
        top_mover_change=0.01,
        now=NOW,
    )

    assert copy.headline == "Up 1 point today"


# ── The three public generators route to it ──────────────────────────────────


def test_all_three_generators_route_a_yes_no_market_away_from_leads():
    common = dict(
        market_name=TAIWAN,
        highlight_reasons=["multi_source"],
        leader_name=TAIWAN_OUTCOME,
        leader_probability=TAIWAN_PROB,
        source_count=2,
        affirmative_probability=TAIWAN_PROB,
        now=NOW,
    )

    reason = generate_futures_reason(**common)
    headline = generate_futures_headline(**common)
    summary = generate_futures_context_summary(headline=headline, **common)

    for served in (reason, headline, summary):
        assert "leads" not in served
        assert "across 2 sources" not in served

    assert headline == "4% chance"
    assert summary == "4% chance"


def test_a_field_market_keeps_its_leads_copy():
    """The change is scoped to yes/no questions and nothing else moves."""
    headline = generate_futures_headline(
        highlight_reasons=["multi_source"],
        leader_name="Los Angeles Dodgers",
        leader_probability=0.305,
        source_count=2,
        market_name="MLB World Series Winner",
        affirmative_probability=None,
        now=NOW,
    )

    # Was `"Tracked by 2 sources"` until #4160/#4133 took the inventory count
    # off the screen. The point of this test is unchanged and still tested: a
    # FIELD market keeps its "leads" copy, and only yes/no questions were
    # rescued from being rendered as a race.
    # 30% -> 31% with #4146: 0.305 is a .5 boundary, and the card's own row
    # prints 31 (`rendered_percent`, half-up like web and native). This fixture
    # had pinned the number Python's banker's `round` gave, which is the number
    # the reader could see the card disagreeing with.
    assert headline == "Los Angeles Dodgers leads at 31%"


# ── The dated baseline itself ────────────────────────────────────────────────


def test_a_baseline_inside_this_year_omits_the_year():
    assert format_baseline_date(OPENED, now=NOW) == "Jan 4"


def test_a_baseline_from_a_previous_year_keeps_it():
    stamped = datetime(2025, 11, 20, 12, 0, tzinfo=timezone.utc)

    assert format_baseline_date(stamped, now=NOW) == "Nov 20, 2025"


def test_a_naive_baseline_is_read_as_utc_which_is_how_the_pollers_store_it():
    assert format_baseline_date(datetime(2026, 1, 4, 9, 30), now=NOW) == "Jan 4"


def test_no_baseline_is_not_a_date():
    assert format_baseline_date(None, now=NOW) is None
