"""UX-P239 — a Discover card's explanation stops printing the No side as the answer.

THE DEFECT, measured on the live feed 2026-08-31 21:5xZ (`GET /api/feed?limit=60`,
60 items). Both of the two-outcome futures cards that were leading on the No side
served a `context_summary` whose grammatical subject was a truncated double
negative, so the percentage read as the answer to the question rather than to its
negation:

    59934328  Will "Onslaught" score at least 80 on the Tomatometer?   (Yes 26%)
              'No: "Onslaught" score at least 80 on ... leads at 74%'
    57792416  Will Neuralink's valuation hit (HIGH) $47.5B by Aug 31?  (Yes 27.5%)
              "Not Neuralink's valuation leads at 72%"

Every label in this file is the VERBATIM served bytes from that capture, including
the ellipsis truncation `humanize_binary_outcome_name` applies at 40 characters —
that truncation is why the restatement comparison has to be prefix-tolerant, so a
tidied-up fixture would stop testing the thing that breaks.

🔴 SCOPE EVERY ASSERTION TO WHAT IT MEANS (UX-P238-5). `"No"` is a substring of
`'No: "Onslaught" ...'`, so `"No" in summary` passes on the DEFECTIVE output too.
The fixed-state assertions therefore name the exact clause (`"No leads at 74%"`)
and separately assert the mangled label is ABSENT.
"""

import pytest

from app.utils.feed_reasons import (
    _answering_side_label,
    _negates_market_question,
    generate_futures_context_summary,
    generate_futures_headline,
    generate_futures_reason,
)

# ── The two live specimens, verbatim ─────────────────────────────────────────

ONSLAUGHT_MARKET = (
    'Will "Onslaught" score at least 80 on the Rotten Tomatoes Tomatometer?'
)
ONSLAUGHT_NO_LABEL = 'No: "Onslaught" score at least 80 on ...'
ONSLAUGHT_YES_LABEL = '"Onslaught" score at least 80 on the ...'

NEURALINK_MARKET = "Will Neuralink's valuation hit (HIGH) $47.5B by August 31?"
NEURALINK_NO_LABEL = "Not Neuralink's valuation"
NEURALINK_YES_LABEL = "Neuralink's valuation"


class TestNegationDetection:
    """The predicate itself, on the specimens and on what must NOT trip it."""

    @pytest.mark.parametrize(
        "label,market",
        [
            (ONSLAUGHT_NO_LABEL, ONSLAUGHT_MARKET),
            (NEURALINK_NO_LABEL, NEURALINK_MARKET),
        ],
    )
    def test_live_negation_labels_are_detected(self, label, market):
        assert _negates_market_question(label, market) is True
        assert _answering_side_label(label, market) == "No"

    @pytest.mark.parametrize(
        "label,market,why",
        [
            (
                ONSLAUGHT_YES_LABEL,
                ONSLAUGHT_MARKET,
                "the affirmative side carries no negation marker",
            ),
            (
                NEURALINK_YES_LABEL,
                NEURALINK_MARKET,
                "the affirmative side carries no negation marker",
            ),
            (
                "No change",
                "Fed decision: what will the September rate move be?",
                "the Fed's real outcome row — 'change' restates no part of the question",
            ),
            (
                "No change",
                "Will the Fed change rates in September?",
                "even when the question contains the word, it is not its PREFIX",
            ),
            (
                "No. 1 seed",
                "Will the No. 1 seed reach the final?",
                "'No.' is an abbreviation, not a negation marker",
            ),
            (
                "Norway",
                "Will Norway win Eurovision 2027?",
                "the marker needs a separator; 'Norway' is one word",
            ),
            (
                "Not a chance",
                "Will the Jets make the playoffs?",
                "a negation marker whose remainder restates nothing",
            ),
            (
                "No recession",
                "Will there be a recession in 2026?",
                "a GOOD standalone No label — not a prefix restatement, so left alone",
            ),
            (
                "Netflix",
                "Which companies will release an AI-generated series before 2027?",
                "a real outcome name that merely starts with the letters 'n','o'",
            ),
            (
                "No",
                NEURALINK_MARKET,
                "the bare side word restates nothing and is already correct",
            ),
        ],
    )
    def test_labels_that_must_not_be_rewritten(self, label, market, why):
        assert _negates_market_question(label, market) is False, why
        assert _answering_side_label(label, market) == label, why

    def test_restatement_shorter_than_the_minimum_is_not_evidence(self):
        # "the" is 3 chars: below the floor, so it cannot buy a rewrite even
        # though it IS a token prefix of the question.
        assert _negates_market_question("Not the", "Will the Fed cut rates?") is False

    def test_prefix_tolerance_runs_in_both_directions(self):
        # The label is truncated (shorter than the question) …
        assert (
            _negates_market_question("No: Neuralink's valuation", NEURALINK_MARKET)
            is True
        )
        # … and the question is the shorter side.
        assert (
            _negates_market_question(
                "Not Neuralink's valuation hit high 47.5B by August",
                "Will Neuralink's valuation?",
            )
            is True
        )

    def test_the_leading_interrogative_is_stripped(self):
        # Load-bearing: with "Will" left in place the question's first token is
        # "will" and NEITHER live specimen matches. This asserts the mechanism,
        # not just the outcome.
        assert (
            _negates_market_question(
                NEURALINK_NO_LABEL, "Neuralink's valuation hit $47.5B?"
            )
            is True
        )
        assert _negates_market_question(NEURALINK_NO_LABEL, NEURALINK_MARKET) is True

    def test_no_market_name_means_no_rewrite(self):
        assert _answering_side_label(NEURALINK_NO_LABEL, None) == NEURALINK_NO_LABEL
        assert _answering_side_label(NEURALINK_NO_LABEL, "") == NEURALINK_NO_LABEL


class TestContextSummary:
    """`generate_futures_context_summary` — the field the two live cards served."""

    def test_onslaught_summary_names_the_side_not_the_restatement(self):
        summary = generate_futures_context_summary(
            headline='"Onslaught" score at least 80 on the ... up 14.0 points today',
            highlight_reasons=["fresh", "moving", "resolving_soon"],
            market_name=ONSLAUGHT_MARKET,
            leader_name=ONSLAUGHT_NO_LABEL,
            leader_probability=0.74,
            source_count=1,
        )
        assert "No leads at 74%" in summary
        assert ONSLAUGHT_NO_LABEL not in summary
        assert "No: " not in summary

    def test_neuralink_summary_names_the_side_not_the_restatement(self):
        summary = generate_futures_context_summary(
            headline="Neuralink's valuation down 50.0 points today",
            highlight_reasons=["decisive_but_not_settled", "moving", "resolving_soon"],
            market_name=NEURALINK_MARKET,
            leader_name=NEURALINK_NO_LABEL,
            leader_probability=0.725,
            source_count=1,
        )
        assert "No leads at 72%" in summary
        assert NEURALINK_NO_LABEL not in summary

    def test_an_ordinary_leader_is_untouched(self):
        summary = generate_futures_context_summary(
            headline="Tracked by 2 sources",
            highlight_reasons=["multi_source"],
            market_name="MLB World Series Winner",
            leader_name="Los Angeles Dodgers",
            leader_probability=0.31,
            source_count=2,
        )
        assert "Los Angeles Dodgers leads at 31%" in summary


class TestReasonAndHeadline:
    """The other two generators print the same clause and need the same rule."""

    @pytest.mark.parametrize(
        "reasons",
        [
            ["resolving_soon_7d"],
            ["resolving_soon_30d"],
            ["multi_source"],
            ["leader_change"],
            [],  # the fallback branch
        ],
    )
    def test_reason_never_prints_the_negation_label(self, reasons):
        reason = generate_futures_reason(
            market_name=NEURALINK_MARKET,
            highlight_reasons=reasons,
            leader_name=NEURALINK_NO_LABEL,
            leader_probability=0.725,
            source_count=2,
        )
        assert NEURALINK_NO_LABEL not in reason, reasons

    @pytest.mark.parametrize(
        "reasons",
        [
            ["resolving_soon_7d"],
            ["resolving_soon_30d"],
            ["leader_change"],
            [],  # the fallback branch
        ],
    )
    def test_headline_never_prints_the_negation_label(self, reasons):
        headline = generate_futures_headline(
            highlight_reasons=reasons,
            leader_name=NEURALINK_NO_LABEL,
            leader_probability=0.725,
            source_count=2,
            market_name=NEURALINK_MARKET,
        )
        assert NEURALINK_NO_LABEL not in headline, reasons

    def test_headline_resolving_soon_names_the_side(self):
        headline = generate_futures_headline(
            highlight_reasons=["resolving_soon_7d"],
            leader_name=NEURALINK_NO_LABEL,
            leader_probability=0.725,
            source_count=1,
            market_name=NEURALINK_MARKET,
        )
        assert headline == "Resolving soon: No leads at 72%"

    def test_mover_and_surprise_labels_get_the_same_rule(self):
        # The movement branches take a DIFFERENT name argument. A fix applied
        # only to `leader_name` leaves the identical defect reachable here.
        moved = generate_futures_reason(
            market_name=NEURALINK_MARKET,
            highlight_reasons=["major_movement_24h"],
            top_mover_name=NEURALINK_NO_LABEL,
            top_mover_change=-0.5,
        )
        assert NEURALINK_NO_LABEL not in moved
        # `_side_label` is this file's existing convention for movement copy and
        # still applies: the bare side word becomes "No side" so the sentence
        # reads. That is the pre-existing rule, not part of this fix.
        assert moved.startswith("No side moved down 50.0 points today in")

        surprised = generate_futures_reason(
            market_name=NEURALINK_MARKET,
            highlight_reasons=["major_surprise"],
            top_surprise_name=NEURALINK_NO_LABEL,
            top_surprise_change=-0.5,
        )
        assert NEURALINK_NO_LABEL not in surprised

    def test_an_ordinary_leader_is_untouched(self):
        reason = generate_futures_reason(
            market_name="MLB World Series Winner",
            highlight_reasons=["multi_source"],
            leader_name="Los Angeles Dodgers",
            leader_probability=0.31,
            source_count=2,
        )
        assert reason == (
            "Los Angeles Dodgers (31%) leads MLB World Series Winner across 2 sources"
        )
