"""#3491 — a Discover Yes/No card stops printing its own question back at itself.

THE DEFECT, photographed on the iPhone 17 simulator against production
2026-09-06 05:01 EDT (`artifacts-native-034/discover-depth1.png`, card 1). The
card hero, the headline and the context line all carried the same eight words,
one of them cut mid-word:

    HOCKEY
    40%
    Canadian Team to Win the Stanley Cup®...      <- top_outcomes[0].name
    ──────────────────────────────────────
    Canadian Team to Win the Stanley Cup®
    Before the 2030-31 Season                     <- data.name
    Canadian Team to Win the Stanley Cup®...
    down 24.5 points from opening                 <- context_summary

Kalshi binary outcomes are literally named `Yes`/`No`, so
`humanize_binary_outcome_name` manufactures a readable label. Strategy 1 pulls a
subject out of `Will <subject> <verb> …?` and is good when it hits. Strategy 2 is
the fallback, and it used to force a fit by cutting the market name at 40
characters — but the card prints the market name DIRECTLY BELOW the label, so
the cut string was never a summary of the question, it was the question again.

MEASURED on production 2026-09-06, every 11th open `container_member` market
(n=977 of 10,742): the Yes label was a chopped echo for **41.1%** of them and the
No label for **48.2%**.

THE FIX extends UX-P239's ruling to its affirmative mirror — once a label merely
restates the question, the bare side word is the only honest label — and applies
it where the label is MANUFACTURED, so it reaches `top_outcomes[].name` (what the
card hero renders) and not just the copy templates.

🔴 THE SPECIMENS HERE ARE VERBATIM PRODUCTION MARKET NAMES, captured in the
measurement above. Their length is the whole point of the test, so a tidied-up
or shortened fixture would stop testing the thing that breaks.

── #3517, 2026-09-08: THE GATE IS NO LONGER LENGTH ──────────────────────────
Two cards on feed page one carried the same echo at 33 and 34 characters, so
#3491's gate never saw them. Length was only ever a proxy for redundancy, and
Strategy 2 builds its label by DELETING A SUFFIX from the question — so its
output is always a prefix of the title printed directly below it, at every
length. The gate is now the redundancy itself; the length gate stays as the
second half the issue asked for, and `TestTheEchoIsRefused` above still pins it.

What moved: `LABEL_UNDER_35` used to assert its labels still shipped. They now
collapse, and `TestAFittingEchoIsStillAnEcho` is where they are asserted.
`TestStrategy1Survives` is the control that keeps this from being a blanket
refusal — a Strategy 1 extraction is a prefix of its question too, and must not
collapse, because it leaves the question's PREDICATE out of the label.
"""

import re

import pytest

from app.utils.feed_reasons import (
    _MAX_LABEL_CHARS,
    _TRAILING_NOISE_RE,
    _TRAILING_QM_RE,
    generate_futures_context_summary,
    generate_futures_reason,
    humanize_binary_outcome_name,
    humanize_outcome_names_for_feed,
)

# ── The served specimens the LOOK found, verbatim ────────────────────────────

PHOTOGRAPHED = "Canadian Team to Win the Stanley Cup® Before the 2030-31 Season"

# Served by `GET /api/feed` on 2026-09-06, every one of them a chopped echo.
SERVED_ECHOES = [
    PHOTOGRAPHED,
    "Will Trump create a $250 bill featuring himself?",
    "Will Palantir (PLTR) finish week of September 7 above $169?",
    "Will SpaceX (SPCX) finish week of September 7 above $155?",
    "Will Microsoft (MSFT) finish week of September 7 above $480?",
]

# Real `container_member` rows from the census, one band each. The lengths are
# of the Strategy 2 label, not of the market name.
LABEL_OVER_40 = [
    "Will the Arizona Diamondbacks win 100 or more games during the 2026 MLB Regular Season?",
    "Will the Boston Red Sox win 100 or more games during the 2026 MLB Regular Season?",
    "Ukraine recognizes Russian sovereignty over its territory by June 30, 2026?",
]

# The 36-40 band: the label alone would fit, `"Not: " + label` would not. 11.0%
# of Strategy 2 markets land here and they are why the gate is pair-wide.
LABEL_36_TO_40 = [
    "Mike Johnson out as Speaker by June 30?",
    "Will Russia capture Lyman by April 30, 2026?",
    "Will Saudi Arabia join the Abraham Accords before 2027?",
    "Will Pam Bondi leave the Trump administration before 2027?",
    "Federal Reserve interest rate above 5%?",
]

# Once the band where #3491 kept the label and #3517 takes it away. The names
# are unchanged; only what is asserted about them below has moved. See
# `TestAFittingEchoIsStillAnEcho`.
LABEL_UNDER_35 = [
    "Jeffrey Epstein foul play confirmed in 2025?",
    "Will AppLovin acquire TikTok?",
    "Will Hezbollah disarm by April 30?",
    "Does Alcaraz reach the semifinals?",
    "Is Earth flat?",
]


class TestTheEchoIsRefused:
    """A label that would have to be chopped is not served at all."""

    @pytest.mark.parametrize("market", SERVED_ECHOES + LABEL_OVER_40)
    def test_an_over_long_label_becomes_the_bare_side(self, market):
        assert humanize_binary_outcome_name("Yes", market) == "Yes"
        assert humanize_binary_outcome_name("No", market) == "No"

    @pytest.mark.parametrize("market", SERVED_ECHOES + LABEL_OVER_40)
    def test_no_fragment_of_the_question_survives_into_the_label(self, market):
        """Scoped per UX-P238-5 — `== "Yes"` alone would pass on a mangled
        label that merely happened to differ, so assert the ABSENCE of the
        question's own words too."""
        for side in ("Yes", "No"):
            label = humanize_binary_outcome_name(side, market)
            assert not label.endswith("...")
            assert "…" not in label
            # The first real word of the question must not be in the label.
            first_word = market.replace("Will ", "", 1).split()[0].strip("\"'")
            assert first_word.lower() not in label.lower()

    def test_the_photographed_card_no_longer_repeats_its_own_headline(self):
        # The exact bytes off the phone: hero label vs the headline beneath it.
        hero = humanize_binary_outcome_name("Yes", PHOTOGRAPHED)
        assert hero == "Yes"
        assert hero not in PHOTOGRAPHED.split()  # not a word lifted from it
        assert "Stanley Cup" not in hero


class TestTheGateIsPairWide:
    """Both sides of a binary are labelled, or neither is.

    🔴 WHY THIS IS NOT A STYLE PREFERENCE. `frontend/lib/discover/heroOutcome.ts`
    (UX-P238) stops a card printing the negation of its own question as its
    headline, and it only flips when it can see the pair as a negation: either
    the canonical `("No", "Yes")`, or a `NEGATION_PREFIX` match whose trailing
    `\\s+` is load-bearing and which a BARE "No" cannot satisfy. A per-side gate
    would strand `("No", "<38-char affirmative>")` — neither canonical nor
    prefix-matchable — and the web hero would silently stop flipping. The
    36-40 band below is exactly that stranding case.
    """

    @pytest.mark.parametrize(
        "market", SERVED_ECHOES + LABEL_OVER_40 + LABEL_36_TO_40 + LABEL_UNDER_35
    )
    def test_the_two_sides_agree_on_whether_they_are_labelled(self, market):
        yes = humanize_binary_outcome_name("Yes", market)
        no = humanize_binary_outcome_name("No", market)
        assert (yes == "Yes") == (no == "No"), (
            f"mixed pair for {market!r}: {yes!r} beside {no!r} — the web hero "
            "cannot read this as a negation pair"
        )

    @pytest.mark.parametrize("market", LABEL_36_TO_40)
    def test_the_36_to_40_band_collapses_rather_than_stranding_a_mixed_pair(
        self, market
    ):
        # Before #3491 these served a full Yes label beside a chopped No one.
        assert humanize_binary_outcome_name("Yes", market) == "Yes"
        assert humanize_binary_outcome_name("No", market) == "No"

    def test_a_collapsed_pair_is_the_canonical_pair_the_web_hero_recognises(self):
        """`heroOutcome.ts` special-cases `neg === "no" && aff === "yes"`. The
        collapsed pair must be exactly that, in the batch shape the feed
        actually serves."""
        outcomes = humanize_outcome_names_for_feed(
            [
                {"name": "No", "probability": 0.6},
                {"name": "Yes", "probability": 0.4},
            ],
            PHOTOGRAPHED,
        )
        assert [o["name"] for o in outcomes] == ["No", "Yes"]
        assert [o["probability"] for o in outcomes] == [0.6, 0.4]


class TestAFittingEchoIsStillAnEcho:
    """#3517 — the same rule, tested on the property instead of on length.

    THE DEFECT, on the live feed 2026-09-08 20:25Z, `GET /api/feed?limit=30`,
    two cards on page one and neither of them chopped:

        reason: 'China x Philippines military clash moved up 37.5 points from
                 opening in China x Philippines military clash before 2027?'
        reason: 'China invade Taiwan by end of 2026 (4%) leads
                 Will China invade Taiwan by end of 2026?'

    33 and 34 characters, so #3491's gate never fired. The labels are echoes all
    the same: Strategy 2 builds them by DELETING A SUFFIX from the question, so
    what it returns is a prefix of the title printed directly below it.

    🔴 THE SPLIT IS AT THE STRATEGY BOUNDARY, NOT AT A LENGTH. That is the whole
    content of the change and `TestStrategy1Survives` is its other half — a rule
    that collapsed Strategy 1 too would pass everything here and fail there.
    """

    SPECIMENS = [
        # The two production cards above, verbatim.
        "China x Philippines military clash before 2027?",
        "Will China invade Taiwan by end of 2026?",
    ] + LABEL_UNDER_35

    @pytest.mark.parametrize("market", SPECIMENS)
    def test_a_fitting_restatement_becomes_the_bare_side(self, market):
        assert humanize_binary_outcome_name("Yes", market) == "Yes"
        assert humanize_binary_outcome_name("No", market) == "No"

    @pytest.mark.parametrize("market", SPECIMENS)
    def test_the_label_was_short_enough_that_length_would_not_have_caught_it(
        self, market
    ):
        """Precondition, so the class cannot pass for #3491's reason instead.

        Every specimen here must be one #3491's gate would have LET THROUGH;
        otherwise this test is re-asserting the old rule under a new name.
        """
        label = _TRAILING_QM_RE.sub("", market)
        label = _TRAILING_NOISE_RE.sub("", label)
        label = re.sub(r"^Will\s+", "", label, flags=re.IGNORECASE).strip()
        assert len(f"Not: {label}") <= _MAX_LABEL_CHARS, (
            f"{market!r} is caught by the LENGTH gate, so it proves nothing "
            "about the redundancy gate"
        )

    def test_the_taiwan_card_stops_saying_the_question_twice_in_one_sentence(self):
        """The reader-facing sentence, end to end down the real path."""
        market = "Will China invade Taiwan by end of 2026?"
        summary = generate_futures_context_summary(
            highlight_reasons=[],
            market_name=market,
            leader_name=humanize_binary_outcome_name("Yes", market),
            leader_probability=0.04,
            headline="",
        )
        assert summary == "Yes leads at 4%"
        # The served defect, verbatim, must not be reachable.
        assert "China invade Taiwan by end of 2026 leads at 4%" != summary
        assert summary.lower().count("taiwan") == 0

    def test_the_philippines_card_stops_saying_the_question_twice(self):
        """The other served card, down its own template.

        Reproduced byte-for-byte against the served `reason` before the change,
        so this pins the real sentence and not a plausible one. `major_surprise`
        is the highlight the card carried; `_side_label` is what turns the
        collapsed `Yes` into `Yes side` in movement copy.
        """
        market = "China x Philippines military clash before 2027?"
        label = humanize_binary_outcome_name("Yes", market)
        reason = generate_futures_reason(
            market_name=market,
            highlight_reasons=["major_surprise"],
            top_surprise_name=label,
            top_surprise_change=0.375,
        )
        assert reason == (
            "Yes side moved up 37.5 points from opening in "
            "China x Philippines military clash before 2027?"
        )
        # The served defect, verbatim.
        assert reason != (
            "China x Philippines military clash moved up 37.5 points from "
            "opening in China x Philippines military clash before 2027?"
        )
        assert reason.lower().count("philippines") == 1

    def test_the_pair_stays_canonical_so_the_web_hero_still_flips(self):
        """Same contract #3491 pins, over the band #3517 newly collapses."""
        for market in self.SPECIMENS:
            outcomes = humanize_outcome_names_for_feed(
                [
                    {"name": "No", "probability": 0.96},
                    {"name": "Yes", "probability": 0.04},
                ],
                market,
            )
            assert [o["name"] for o in outcomes] == ["No", "Yes"], market


class TestStrategy1Survives:
    """The other half of the split, and the reason it is not a blanket refusal.

    A Strategy 1 extraction is a prefix of its question too — `Anthropic` of
    `Will Anthropic IPO first?` — so a redundancy test applied without regard to
    which strategy built the label would collapse every one of these. What makes
    them different is that Strategy 1 leaves the question's PREDICATE behind, so
    the label says something the title beneath it does not.
    """

    @pytest.mark.parametrize(
        "market,expected_yes",
        [
            ("Will Anthropic IPO first?", "Anthropic"),
            ("Will OpenAI IPO before 2027?", "OpenAI"),
            ("Will Taylor Swift be pregnant in 2026?", "Taylor Swift"),
            ("Will Elon Musk step down as CEO of Tesla?", "Elon Musk"),
            ("Will Bitcoin reach $100k by December 2026?", "Bitcoin"),
            (
                "Will New Jersey Devils advance to the Second Round of the "
                "2027 Stanley Cup Playoffs?",
                "New Jersey Devils",
            ),
            # Served alongside the two defect cards in the same feed read.
            (
                "Will Utah Mammoth advance to the Second Round of the 2027 "
                "Stanley Cup Playoffs?",
                "Utah Mammoth",
            ),
        ],
    )
    def test_a_genuine_extraction_is_not_read_as_a_restatement(
        self, market, expected_yes
    ):
        assert humanize_binary_outcome_name("Yes", market) == expected_yes
        assert humanize_binary_outcome_name("No", market) == f"Not {expected_yes}"


class TestNothingElseMoved:
    """Outside the manufactured labels, nothing is rewritten."""

    def test_a_real_outcome_name_is_never_rewritten(self):
        # Only the manufactured Yes/No labels are in scope.
        assert (
            humanize_binary_outcome_name("Florida Panthers", PHOTOGRAPHED)
            == "Florida Panthers"
        )
        # The Fed's real row, named in UX-P239 as the reason the rule is
        # restatement-based and not a bare `/^no\\b/` prefix.
        assert (
            humanize_binary_outcome_name("No change", "Fed decision in September?")
            == "No change"
        )

    def test_multi_outcome_markets_are_left_alone(self):
        outcomes = [
            {"name": "Florida Panthers", "probability": 0.11},
            {"name": "Colorado Avalanche", "probability": 0.09},
        ]
        assert (
            humanize_outcome_names_for_feed(outcomes, "2026-27 Stanley Cup® Winner")
            == outcomes
        )

    def test_passthrough_edges(self):
        assert humanize_binary_outcome_name("", "Will X happen?") == ""
        assert humanize_binary_outcome_name("Yes", None) == "Yes"
        assert humanize_binary_outcome_name("YES", "Will Anthropic IPO first?") == (
            "Anthropic"
        )
