"""#3513 — a Discover card stops asking the reader a question with a hole in it.

WHAT A READER SAW, photographed on production at 390px on 2026-09-15 (released
v4550 `880bb91d`), on the DEFAULT LANDING PAGE:

    Netanyahu out by...?
    Will Samuel Alito announce his retirement by...?
    Netflix (NFLX) closes week of Sep 14 at ___?

Eight such cards in one read of `/api/feed` (offsets 0 and 100, 119 items).
Across production, `status='open'`: **362 markets, 100% polymarket** — 294 with
`...`, 68 with `___`. Polymarket publishes a group TEMPLATE as the event title
plus a written question per member; we ingest the template into
`futures_markets.name` and print it.

WHAT THIS SHIP DOES: removes a placeholder sitting at the END of the question
together with the preposition that governed it, at DISPLAY boundaries only.
311 of the 362 change; 51 are deliberately left byte-identical.

🔴 THE TESTS THAT MATTER MOST HERE ARE THE CONTROLS. This is a string-rewriting
ship over a 362-row population, so the risk is not "does it fire" but "what
else does it touch". Three populations are asserted UNCHANGED:

  * DIRECTIONAL "above" (15) — dropping the comparison word turns a cumulative
    ladder into a set of exact prices, i.e. a clean-looking lie. See
    `TestTheDirectionalLadderIsLeftAlone`.
  * EMBEDDED blanks (36) — real text follows the blank, so removing it produces
    "close above end of September". See `TestTheEmbeddedBlankIsLeftAlone`.
  * Every name with no placeholder at all — 60 real open markets, byte-identity.

Corpora below are REAL PRODUCTION NAMES read from `futures_markets` on
2026-09-15, not invented fixtures.
"""

import ast
import re
from pathlib import Path

import pytest

from app.utils.market_display_name import clean_market_display_name


# ---------------------------------------------------------------------------
# Corpora — real production rows, 2026-09-15
# ---------------------------------------------------------------------------

# (stored name, what a reader should see). Covers all five strippable
# prepositions, the four-dot variant, a trailing-space name, and both the
# spaced `___ ?` and unspaced `by...?` blanks.
CLEANED = [
    ("Netanyahu out by...?", "Netanyahu out?"),
    ("Kraken IPO by ___ ?", "Kraken IPO?"),
    ("NATO/EU troops fighting in Ukraine by...?", "NATO/EU troops fighting in Ukraine?"),
    (
        "Trump eliminates capital gains tax on crypto by ___?",
        "Trump eliminates capital gains tax on crypto?",
    ),
    (
        "SCOTUS accepts sports event contract case by...?     ",
        "SCOTUS accepts sports event contract case?",
    ),
    (
        "European country agrees to give Ukraine security guarantee by...? ",
        "European country agrees to give Ukraine security guarantee?",
    ),
    (
        "Will Samuel Alito announce his retirement by...?",
        "Will Samuel Alito announce his retirement?",
    ),
    ("GPT-5.5 released on...?", "GPT-5.5 released?"),
    ("US-Iran ceasefire continues through...?", "US-Iran ceasefire continues?"),
    (
        "Micron (MU) closes week of Sep 14 at ___?",
        "Micron (MU) closes week of Sep 14?",
    ),
    (
        '"I beat Bush" Epstein Email Sender confirmed as ___ ?',
        '"I beat Bush" Epstein Email Sender confirmed?',
    ),
    # Four dots, not three — two production rows carry this.
    ("ChatGPT Outage by....?", "ChatGPT Outage?"),
    (
        "Ukraine recognizes Russian sovereignty over its territory by....?",
        "Ukraine recognizes Russian sovereignty over its territory?",
    ),
    ("Crude Oil all time high by...?", "Crude Oil all time high?"),
]

# "above" is the comparison the ladder is BUILT FROM. These must never change
# until the ingest-side join lands.
DIRECTIONAL_UNTOUCHED = [
    "Amazon 2026 capex above ___?",
    "OpenAI IPO closing market cap above ___ ?",
    "Will Apple (AAPL) finish week of September 7 above___?",
]

# The blank is mid-sentence with real words after it.
EMBEDDED_UNTOUCHED = [
    "Will Apple (AAPL) close above ___ end of September?",
    "Will any AI model reach ___ Overall Arena Score by December 31?",
    "Nasdaq 100 (NDX) above ___ end of 2026?",
    "Claude Code Commits hit ___ by May 31?",
    "Will a Chinese company have a top ___ AI model by December 31?",
    "North Korea x South Korea diplomatic meeting by...? (direct or indirect)",
]

# Real open markets with no placeholder — the overwhelming majority of the
# table. Nothing here may move by a single byte.
NO_PLACEHOLDER_UNTOUCHED = [
    "Game Spread: Carlo Alberto Caniato (-3.5) vs Giuseppe La Vela (+3.5)",
    "Vela vs. Caniato: Set 1 Games O/U 9.5",
    "Puerto Rico vs. Guyana: O/U 10.5 Total Corners",
    "M25 Zlatibor: Nemanja Malesevic vs Gilberto Ravasio",
    "Set Handicap: Katerina Tsygourova (-1.5) vs Elena Korokozidi (+1.5)",
    "W75 Le Neubourg: Demi Tran vs Sachia Vickery",
    "Which party will win the House in 2026?",
    "Who will win the 2026 World Series?",
    "Brazil Presidential Election",
    "MLB World Series Winner",
]


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


class TestThePhotographedCards:
    """The cards Alex would see on the landing page."""

    @pytest.mark.parametrize("stored,shown", CLEANED)
    def test_the_blank_and_its_preposition_are_gone(self, stored, shown):
        assert clean_market_display_name(stored) == shown

    @pytest.mark.parametrize("stored,shown", CLEANED)
    def test_no_blank_survives_into_a_headline(self, stored, shown):
        result = clean_market_display_name(stored)
        assert "___" not in result
        assert "..." not in result

    @pytest.mark.parametrize("stored,shown", CLEANED)
    def test_the_question_keeps_exactly_one_question_mark(self, stored, shown):
        # The blank swallowed the '?'. Restoring two, or none, is its own defect.
        assert clean_market_display_name(stored).count("?") == 1

    @pytest.mark.parametrize("stored,shown", CLEANED)
    def test_the_headline_never_ends_on_a_dangling_preposition(self, stored, shown):
        # "Netanyahu out by?" would be worse than the blank it replaced.
        result = clean_market_display_name(stored).rstrip("?").rstrip().lower()
        assert not re.search(r"\b(by|on|at|through|as|above)$", result)


# ---------------------------------------------------------------------------
# The controls — green BEFORE this ship and green after
# ---------------------------------------------------------------------------


class TestTheDirectionalLadderIsLeftAlone:
    """🔴 DO NOT "FIX" THIS CLASS BY ADDING `above` TO THE STRIP LIST.

    "Will Apple finish week of September 7 above ___?" has rungs $305 · 92%,
    $310 · 84%. Those numbers are only coherent as "above $305" and "above
    $310" — a cumulative ladder. Drop the word and the same rungs read as the
    chance of finishing AT $305 and AT $310, which is both false and
    impossible-looking (two exact prices cannot be 92% and 84%). The ugly
    headline is the honest one until the ingest join supplies the real question.
    """

    @pytest.mark.parametrize("name", DIRECTIONAL_UNTOUCHED)
    def test_byte_identical(self, name):
        assert clean_market_display_name(name) == name


class TestTheEmbeddedBlankIsLeftAlone:
    """A blank with real text after it is not a trailing blank.

    Removing it yields "Will Apple (AAPL) close above end of September?" —
    a sentence no reader can parse. 36 rows on production.
    """

    @pytest.mark.parametrize("name", EMBEDDED_UNTOUCHED)
    def test_byte_identical(self, name):
        assert clean_market_display_name(name) == name


class TestEverythingElseIsUntouched:
    @pytest.mark.parametrize("name", NO_PLACEHOLDER_UNTOUCHED)
    def test_a_name_with_no_placeholder_is_byte_identical(self, name):
        assert clean_market_display_name(name) == name

    @pytest.mark.parametrize("value", [None, "", "   ", "?", "by...?", "...?", "___?"])
    def test_degenerate_input_is_returned_unchanged(self, value):
        # "by...?" and "___?" are a preposition/blank with NO question left.
        # Returning "" or "?" would be an empty headline, which is worse.
        assert clean_market_display_name(value) == value

    def test_an_unmeasured_governing_word_is_left_alone(self):
        # The allowlist's default is the status quo, never a guess. If
        # Polymarket ships "Bitcoin under ___?" tomorrow we print it unchanged
        # rather than emit "Bitcoin?" and drop the direction.
        assert clean_market_display_name("Bitcoin under ___?") == "Bitcoin under ___?"

    def test_a_mid_sentence_ellipsis_is_not_a_template_blank(self):
        name = "Trump says he will... what exactly?"
        assert clean_market_display_name(name) == name

    @pytest.mark.parametrize("name", [" by...?", ", by...?", "  by ___ ?", "- by...?"])
    def test_a_name_that_is_only_a_preposition_and_a_blank_survives(self, name):
        """Found by mutation: deleting the empty-head guard left this alive.

        A leading space (or leading punctuation) makes `head` end with " by",
        so the preposition branch DOES fire here — unlike the bare "by...?",
        which falls through the allowlist. Strip the preposition and nothing is
        left, and the card would render a headline of "" or "?". Returning the
        stored text is ugly; an empty headline is a broken card.
        """
        assert clean_market_display_name(name) == name


# ---------------------------------------------------------------------------
# The architectural invariant: PRINTED vs INTERPRETED
# ---------------------------------------------------------------------------

FEED_PY = Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"

# Composes a string a person reads.
DISPLAY_CALLEES = {
    "generate_futures_headline",
    "generate_futures_context_summary",
    "generate_futures_reason",
}
# Reads the name to make a DECISION. Must keep the raw stored value: cleaning
# their input would change behaviour, not presentation.
INTERPRETING_CALLEES = {
    "compute_futures_highlight",
    "classify_market_quality",
}


def _market_name_kwargs():
    """Every `market_name=` keyword argument in feed.py, with its callee."""
    tree = ast.parse(FEED_PY.read_text())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        for kw in node.keywords:
            if kw.arg != "market_name":
                continue
            found.append((callee, ast.unparse(kw.value), node.lineno))
    return found


class TestPrintedVersusInterpreted:
    """#3513's real invariant, and the one a later edit is most likely to break.

    Parsed with `ast`, not grepped: a regex over source cannot tell which call
    a keyword belongs to, and that distinction is the whole rule here.
    """

    def test_every_copy_generator_is_handed_the_cleaned_name(self):
        offenders = [
            (callee, value, line)
            for callee, value, line in _market_name_kwargs()
            if callee in DISPLAY_CALLEES and value != "display_name"
        ]
        assert offenders == [], (
            "a string a reader sees is being composed from the raw stored name; "
            f"these would print Polymarket's template blank: {offenders}"
        )

    def test_every_scoring_call_still_reads_the_raw_stored_name(self):
        """The reverse direction — a cleanup must not quietly widen.

        If someone "tidies" these too, market classification and highlight
        scoring silently change for 311 markets, which is a ranking change
        wearing a formatting change's clothes.
        """
        offenders = [
            (callee, value, line)
            for callee, value, line in _market_name_kwargs()
            if callee in INTERPRETING_CALLEES and value != "market.name"
        ]
        assert offenders == [], (
            f"a scoring input was switched to the display string: {offenders}"
        )

    def test_both_sides_of_the_rule_are_actually_present(self):
        """Guards against the whole assertion going vacuous.

        If feed.py is refactored so no `market_name=` kwargs remain, both tests
        above pass over an empty list and prove nothing. Pin the populations.
        """
        kwargs = _market_name_kwargs()
        display = [c for c, _v, _l in kwargs if c in DISPLAY_CALLEES]
        interpreting = [c for c, _v, _l in kwargs if c in INTERPRETING_CALLEES]
        # 3 copy generators x 3 scoring functions; 2 interpreters x 3.
        assert len(display) == 9, f"expected 9 copy call sites, found {len(display)}"
        assert len(interpreting) == 6, (
            f"expected 6 scoring call sites, found {len(interpreting)}"
        )


class TestTheCardPayloadAndTheAdminTraceDisagreeOnPurpose:
    """The served card shows the cleaned question; the trace shows the row.

    A diagnostic that silently tidies the very field it exists to display would
    make #3513 invisible to the next person who looks for it.
    """

    def test_the_two_card_payloads_serve_the_display_name(self):
        source = FEED_PY.read_text()
        assert source.count('"name": display_name,') == 2

    def test_the_admin_surfaces_still_serve_the_raw_name(self):
        source = FEED_PY.read_text()
        # build_discover_market_trace + build_effective_settlement_followup_item
        assert source.count('"name": market.name,') == 2
