"""#7331 — a bundle row whose ANSWER is a quantity must say which % is the chance.

Production 2026-09-20, 390px, the FED & RATES bundle on page one:

    September Inflation US - Annual
    New favorite: 3.6% (42%)                                  42%

Three percentages on one row — an inflation RATE, its PROBABILITY, and that same
probability again in the row's own right-hand column — and nothing saying which
is which. The row above it reads correctly for the only reason that matters: its
answer is the WORD `Hike 25bps`, so the parenthesis has something to disambiguate.

Both halves are asserted here and both are load-bearing. The repair half proves
the collapsed row now carries the unit; the CONTROL half proves the repair was
spent only where the ambiguity is real, because a fix that reworded every card
would pass the first half alone.

Every label below is a LITERAL. The predicate lives in `leader_percent_parenthetical`
and a test that re-derived it — looping a shared table, or calling the helper to
decide what to expect — could not see that predicate narrow or widen, which is the
whole thing this file exists to catch.
"""

from app.utils.feed_reasons import (
    generate_futures_headline,
    generate_futures_reason,
    leader_percent_parenthetical,
)

# The two served labels that collapse, verbatim from `GET /api/feed?limit=100`
# on 2026-09-20, plus the two shapes the same class produces on a quantity board.
BARE_QUANTITY_LABELS = ["3.6%", "2.4%", "-0.4%", "3"]

# Served labels on the SAME feed that already state their own unit. Named as
# literals so the control cannot drift with the predicate it is guarding.
LABELS_THAT_ALREADY_READ = [
    "Hike 25bps",
    "Above 20 million short tons",
    "Above -0.4%",
    "Above 425,000 TEUs",
    "Marine Le Pen",
    "Yes",
]


class TestTheParentheticalItself:
    def test_a_bare_quantity_answer_names_the_unit(self):
        assert leader_percent_parenthetical("3.6%", 42) == "(42% chance)"
        assert leader_percent_parenthetical("2.4%", 41) == "(41% chance)"
        assert leader_percent_parenthetical("-0.4%", 91) == "(91% chance)"
        assert leader_percent_parenthetical("3", 25) == "(25% chance)"

    def test_an_answer_that_carries_a_word_is_untouched(self):
        assert leader_percent_parenthetical("Hike 25bps", 55) == "(55%)"
        assert leader_percent_parenthetical("Above 20 million short tons", 87) == "(87%)"
        assert leader_percent_parenthetical("Above -0.4%", 91) == "(91%)"
        assert leader_percent_parenthetical("Marine Le Pen", 37) == "(37%)"
        assert leader_percent_parenthetical("Yes", 64) == "(64%)"

    def test_a_label_with_no_digit_at_all_is_untouched(self):
        # The predicate needs BOTH arms. A label that is neither numeric nor a
        # word — an empty string, a stray separator — must not acquire prose.
        assert leader_percent_parenthetical("", 42) == "(42%)"
        assert leader_percent_parenthetical("   ", 42) == "(42%)"
        assert leader_percent_parenthetical("—", 42) == "(42%)"


class TestTheServedHeadline:
    """`generate_futures_headline`, the string the bundle row printed."""

    def test_the_september_inflation_row_says_which_percent_is_the_chance(self):
        headline = generate_futures_headline(
            highlight_reasons=["leader_change"],
            leader_name="3.6%",
            leader_probability=0.42,
            rendered_leader_percent=42,
            market_name="September Inflation US - Annual",
        )
        assert headline == "New favorite: 3.6% (42% chance)"

    def test_the_string_production_served_is_gone(self):
        # The BEFORE, named as a literal. Without this the test above would
        # still pass if the branch stopped speaking altogether.
        headline = generate_futures_headline(
            highlight_reasons=["leader_change"],
            leader_name="3.6%",
            leader_probability=0.42,
            rendered_leader_percent=42,
            market_name="September Inflation US - Annual",
        )
        assert headline != "New favorite: 3.6% (42%)"
        assert headline.startswith("New favorite: 3.6% ")

    def test_a_worded_answer_keeps_todays_headline_byte_for_byte(self):
        headline = generate_futures_headline(
            highlight_reasons=["leader_change"],
            leader_name="Hike 25bps",
            leader_probability=0.55,
            rendered_leader_percent=55,
            market_name="Fed decision in Oct 2026?",
        )
        assert headline == "New favorite: Hike 25bps (55%)"


class TestTheServedReason:
    """`generate_futures_reason` — the other door onto the same row."""

    def test_the_leader_change_reason_names_the_unit(self):
        reason = generate_futures_reason(
            market_name="September Inflation US - Annual",
            highlight_reasons=["leader_change"],
            leader_name="3.6%",
            leader_probability=0.42,
            rendered_leader_percent=42,
        )
        assert reason == (
            "New favorite: 3.6% (42% chance) now leads September Inflation US - Annual"
        )

    def test_a_worded_answer_keeps_todays_reason_byte_for_byte(self):
        reason = generate_futures_reason(
            market_name="Fed decision in Oct 2026?",
            highlight_reasons=["leader_change"],
            leader_name="Hike 25bps",
            leader_probability=0.55,
            rendered_leader_percent=55,
        )
        assert reason == (
            "New favorite: Hike 25bps (55%) now leads Fed decision in Oct 2026?"
        )


class TestNoServedCopyLeavesTwoBarePercentsAdjacent:
    """The class assertion — a blanket sweep, not a per-site one.

    A later site that composes `{bare quantity} ({pct}%)` by hand reintroduces
    the defect without touching any string named above. This walks the two
    generators over every collapsed label and refuses the shape itself.
    """

    def test_neither_generator_prints_a_bare_quantity_beside_a_bare_percent(self):
        offenders = []
        for label in BARE_QUANTITY_LABELS:
            for text in (
                generate_futures_headline(
                    highlight_reasons=["leader_change"],
                    leader_name=label,
                    leader_probability=0.42,
                    rendered_leader_percent=42,
                    market_name="September Inflation US - Annual",
                ),
                generate_futures_reason(
                    market_name="September Inflation US - Annual",
                    highlight_reasons=["leader_change"],
                    leader_name=label,
                    leader_probability=0.42,
                    rendered_leader_percent=42,
                ),
            ):
                if f"{label} (42%)" in text:
                    offenders.append(text)
        assert offenders == [], f"bare quantity beside a bare percent: {offenders}"

    def test_the_worded_controls_are_all_still_bare(self):
        # The other direction, and it is the half that catches an over-wide
        # predicate: if `leader_percent_parenthetical` ever starts saying
        # "chance" for everything, this list is what notices.
        for label in LABELS_THAT_ALREADY_READ:
            headline = generate_futures_headline(
                highlight_reasons=["leader_change"],
                leader_name=label,
                leader_probability=0.42,
                rendered_leader_percent=42,
                market_name="September Inflation US - Annual",
            )
            assert headline == f"New favorite: {label} (42%)", headline
