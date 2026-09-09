"""D1 (#4066) — the metric that grades "why is this card here TODAY".

`explanation-coverage@20` asks whether a card said anything, and every card on
production 2026-09-08 21:07Z passed it. This metric asks the other question, and
on the same payload the answer over the first ten served cards was ZERO.

The fixtures below are the VERBATIM served items from that capture
(`GET /api/feed?limit=20&offset=0`), trimmed to the fields the metric reads. A
tidied fixture would stop testing the strings that failed.

🔴 A METRIC THAT ONLY EVER PASSES IS NOT A METRIC. The baseline test asserts 0/10
on the served defect and the fixed-state tests assert each repaired form scores,
so the two directions are both pinned: a change that made everything pass would
break the first test, and a change that made nothing pass would break the rest.
"""

from app.utils.feed_quality_debug import why_now_coverage

# ── The ten cards production served, verbatim ────────────────────────────────

BASELINE_2026_09_08 = [
    {
        "type": "concept",
        "reason": "13 race markets",
        "headline": "Live",
        "data": {"name": "Vuelta a España 2026"},
    },
    {
        "type": "futures",
        "reason": "Los Angeles Dodgers (31%) leads MLB World Series Winner across 2 sources",
        "headline": "Tracked by 2 sources",
        "context_summary": "Los Angeles Dodgers leads at 31% across 2 sources",
        "data": {"name": "MLB World Series Winner"},
    },
    {
        "type": "bundle",
        "reason": "2 related markets",
        "headline": "2028 Election",
        "data": {"title": "2028 Election", "items": []},
    },
    {
        "type": "futures",
        "reason": "Los Angeles Rams (14%) leads NFL Super Bowl Winner",
        "headline": "Los Angeles Rams leads at 14%",
        "context_summary": "Los Angeles Rams leads at 14%",
        "data": {"name": "NFL Super Bowl Winner"},
    },
    {
        "type": "bundle",
        "reason": "2 related markets",
        "headline": "AI",
        "data": {"title": "AI", "items": []},
    },
    {
        "type": "bundle",
        "reason": "2 related markets",
        "headline": "Awards Season",
        "data": {"title": "Awards Season", "items": []},
    },
    {
        "type": "bundle",
        "reason": "3 related markets",
        "headline": "Fed & Rates",
        "data": {"title": "Fed & Rates", "items": []},
    },
    {
        "type": "futures",
        "reason": "China invade Taiwan by end of 2026 (4%) leads Will China invade Taiwan by end of 2026?",
        "headline": "China invade Taiwan by end of 2026 leads at 4%",
        "context_summary": "China invade Taiwan by end of 2026 leads at 4%",
        "data": {"name": "Will China invade Taiwan by end of 2026?"},
    },
    {
        "type": "bundle",
        "reason": "4 related markets",
        "headline": "Middle East",
        "data": {"title": "Middle East", "items": []},
    },
    {
        "type": "futures",
        "reason": "China x Philippines military clash moved up 37.5 points from opening in China x Philippines military clash before 2027?",
        "headline": "China x Philippines military clash up 37.5 points from opening",
        "context_summary": "China x Philippines military clash up 37.5 points from opening",
        "data": {"name": "China x Philippines military clash before 2027?"},
    },
]


def test_the_served_baseline_scores_zero_of_ten():
    """Page one on 2026-09-08: not one card named something that happened."""
    coverage = why_now_coverage(BASELINE_2026_09_08, top_n=10)

    assert coverage["slots"] == 10
    assert coverage["with_why_now"] == 0


def test_the_baseline_report_names_every_offender_with_its_copy():
    """The audit prints these lines; they have to identify the card."""
    coverage = why_now_coverage(BASELINE_2026_09_08, top_n=10)
    offenders = [row for row in coverage["items"] if not row["why_now"]]

    assert len(offenders) == 10
    assert offenders[1]["name"] == "MLB World Series Winner"
    assert offenders[1]["served_copy"] == (
        "Los Angeles Dodgers leads at 31% across 2 sources"
    )


def test_an_undated_move_from_opening_does_not_count():
    """The exact string that made slot 10 look like news, and is not."""
    coverage = why_now_coverage(
        [
            {
                "type": "futures",
                "headline": "China x Philippines military clash up 37.5 points from opening",
                "data": {"name": "x"},
            }
        ],
        top_n=1,
    )

    assert coverage["with_why_now"] == 0


# ── What the repaired copy scores ────────────────────────────────────────────


def test_a_dated_move_counts():
    coverage = why_now_coverage(
        [
            {
                "type": "futures",
                "headline": "Up 37.5 points since Jan 4",
                "data": {"name": "x"},
            }
        ],
        top_n=1,
    )

    assert coverage["with_why_now"] == 1
    assert coverage["items"][0]["why_now"] == "points since "


def test_a_move_today_counts():
    coverage = why_now_coverage(
        [{"type": "futures", "headline": "Up 12 points today", "data": {"name": "x"}}],
        top_n=1,
    )

    assert coverage["with_why_now"] == 1


def test_a_new_favorite_counts():
    coverage = why_now_coverage(
        [
            {
                "type": "futures",
                "headline": "New favorite: Philadelphia Waterdogs (48%)",
                "data": {"name": "x"},
            }
        ],
        top_n=1,
    )

    assert coverage["with_why_now"] == 1


def test_a_catalyst_inside_the_week_counts():
    coverage = why_now_coverage(
        [
            {
                "type": "futures",
                "context_summary": "59% chance, resolving this week",
                "data": {"name": "x"},
            }
        ],
        top_n=1,
    )

    assert coverage["with_why_now"] == 1


def test_a_bundle_scores_on_its_members_not_on_having_a_question():
    """A shared question says WHAT the group is; it does not say why today."""
    question_only = {
        "type": "bundle",
        "reason": "Who wins in 2028?",
        "headline": "2028 Election",
        "data": {
            "title": "2028 Election",
            "items": [
                {"headline": "J.D. Vance leads at 22%"},
            ],
        },
    }
    with_a_member_signal = {
        "type": "bundle",
        "reason": "Who wins in 2028?",
        "headline": "2028 Election",
        "data": {
            "title": "2028 Election",
            # Was "Multiple ranking changes" until #4160 took that string off
            # the screen and out of WHY_NOW_MARKERS. The point of this test is
            # that a bundle inherits a member's why-now, so it needs a member
            # signal that is still one.
            "items": [
                {"headline": "New favorite: J.D. Vance (24%)"},
            ],
        },
    }

    assert why_now_coverage([question_only], top_n=1)["with_why_now"] == 0
    assert why_now_coverage([with_a_member_signal], top_n=1)["with_why_now"] == 1


def test_a_bare_probability_answer_is_not_a_why_now():
    """Clause b's repaired Taiwan card is honest AND still has no news."""
    coverage = why_now_coverage(
        [
            {
                "type": "futures",
                "headline": "4% chance",
                "context_summary": "4% chance",
                "data": {"name": "Will China invade Taiwan by end of 2026?"},
            }
        ],
        top_n=1,
    )

    assert coverage["with_why_now"] == 0


def test_a_short_page_reports_the_slots_it_actually_had():
    coverage = why_now_coverage(BASELINE_2026_09_08[:3], top_n=10)

    assert coverage["slots"] == 3
