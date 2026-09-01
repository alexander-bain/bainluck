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
    humanize_binary_outcome_name,
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


# ── CERT-624 round 2 ─────────────────────────────────────────────────────────


class TestNonWillInterrogatives:
    """CERT-624: the fix worked only for questions opening with "Will".

    The cert's finding, verbatim: *"The new comparison strips `Does`/`Can`/other
    interrogatives from only the question, while the fallback producer retains
    them in `Not: Does...`; a checked-in real title still renders `Not: Does
    Alcaraz reach the semifinals leads at 72%`."*

    Cause: `humanize_binary_outcome_name`'s Strategy 2 strips a leading "Will "
    and nothing else, so any other auxiliary survives into the label — while
    `_negates_market_question` stripped it from the QUESTION only. Removing a
    token from one side of an equality guarantees a mismatch, so the predicate
    said False and the mangled label reached the reader.

    Round 1 stayed green because every positive specimen in this file opens with
    "Will". These cases exist so that can never be true again.

    🔴 THE LABELS HERE ARE NOT HAND-WRITTEN. Each is produced by calling the real
    `humanize_binary_outcome_name`, which is what manufactured the defect; a
    hand-typed label could quietly stop matching what the producer emits and the
    guard would go vacuous.
    """

    # The cert's own specimen, checked in at `scripts/populate_tournament_props.py:468`.
    ALCARAZ_MARKET = "Does Alcaraz reach the semifinals?"

    NON_WILL_MARKETS = [
        ALCARAZ_MARKET,
        "Can Djokovic win another major?",
        "Is the Fed cutting rates in September?",
        "Are the Jets making the playoffs?",
        "Did the album go platinum?",
        "Should the bill pass before October?",
        "Has the treaty been ratified?",
        "Would a recession start before July?",
    ]

    @pytest.mark.parametrize("market", NON_WILL_MARKETS)
    def test_the_producers_own_no_label_never_reaches_the_reader(self, market):
        # Exactly the path that served the defect: the producer makes the label,
        # the generator renders it.
        label = humanize_binary_outcome_name("No", market)
        assert label != "No", "precondition: the producer must manufacture a label"

        summary = generate_futures_context_summary(
            highlight_reasons=[],
            market_name=market,
            leader_name=label,
            leader_probability=0.72,
            headline="",
        )
        assert summary == "No leads at 72%"
        # Scoped per UX-P238-5: "No" alone is a substring of the defect.
        assert label not in summary

    def test_the_exact_cert_624_sentence_is_gone(self):
        label = humanize_binary_outcome_name("No", self.ALCARAZ_MARKET)
        assert label == "Not: Does Alcaraz reach the semifinals"

        summary = generate_futures_context_summary(
            highlight_reasons=[],
            market_name=self.ALCARAZ_MARKET,
            leader_name=label,
            leader_probability=0.72,
            headline="",
        )
        assert summary == "No leads at 72%"
        assert "Not: Does Alcaraz reach the semifinals leads at 72%" != summary
        assert "Does Alcaraz" not in summary

    def test_the_interrogative_comes_off_both_sides_or_neither(self):
        # The mechanism, asserted directly. Question keeps its auxiliary and the
        # label does not, and vice versa — both must still align.
        assert (
            _negates_market_question(
                "Not: Does Alcaraz reach the semifinals",
                "Does Alcaraz reach the semifinals?",
            )
            is True
        )
        assert (
            _negates_market_question(
                "Not: Alcaraz reach the semifinals",
                "Does Alcaraz reach the semifinals?",
            )
            is True
        )
        assert (
            _negates_market_question(
                "Not: Does Alcaraz reach the semifinals",
                "Alcaraz reach the semifinals?",
            )
            is True
        )

    # Only an ASYMMETRIC pair can test the contents of the auxiliary list. When
    # both sides carry the word, alignment succeeds whether or not it is listed
    # — which is why the first version of this class left the list untested and
    # a mutant reverting it to the round-1 set SURVIVED the battery. These are
    # the words the round-1 set did not have.
    @pytest.mark.parametrize(
        "auxiliary",
        ["Did", "Was", "Were", "Could", "Should", "Has", "Have", "Had"],
    )
    def test_an_auxiliary_present_on_only_one_side_still_aligns(self, auxiliary):
        rest = "the album go platinum"
        assert (
            _negates_market_question(f"Not: {rest}", f"{auxiliary} {rest}?") is True
        ), f"{auxiliary!r} must be strippable from the question side alone"


class TestMidWordTruncation:
    """The 40-char cut lands mid-WORD, so the final token is a fragment.

    Surfaced while reproducing CERT-624: `"Is the Fed cutting rates in
    September?"` becomes `'No: Is the Fed cutting rates in Septe...'`. Token
    equality can never match `septe` against `september`, so even with the
    interrogative fixed this case would still have leaked.
    """

    def test_a_fragment_final_token_still_counts_as_restating(self):
        market = "Is the Fed cutting rates in September?"
        label = humanize_binary_outcome_name("No", market)
        assert label.endswith("..."), "precondition: this label must be truncated"
        assert "Septe" in label and "September" not in label

        assert _negates_market_question(label, market) is True

    def test_a_fragment_that_opens_a_DIFFERENT_word_does_not_count(self):
        # Tolerance is a prefix test, not a wildcard: the fragment must actually
        # open the word it was cut from.
        assert (
            _negates_market_question(
                "Not: the Fed cutting rates in Octo...",
                "Is the Fed cutting rates in September?",
            )
            is False
        )

    def test_everything_before_the_fragment_must_still_match_exactly(self):
        assert (
            _negates_market_question(
                "Not: the Fed RAISING rates in Septe...",
                "Is the Fed cutting rates in September?",
            )
            is False
        )
