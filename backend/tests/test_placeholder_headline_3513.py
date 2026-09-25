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

────────────────────────────────────────────────────────────────────────────
SECOND SHIP, 2026-09-15 (the residual): THE OBJECT-SLOT BLANK.

The rule above only reaches a blank at the END. Re-measured on production at
23:24Z after v4555, `/api/feed` offsets 0/50/100/150: a blank with real text
after it is untouched, and a reader still meets

    What will Gold (GC) hit__ by end of December?     <- /futures/115349 H1,
    Microsoft (MSFT) closes above ___ on September 16?   photographed 390px

Whole-table census by Postgres regex (2026-09-16 02:2xZ): 2,626 rows carry a
blank (372 open, 2,254 resolved), of which 37 open rows put the blank straight
after a verb. 35 of those are rewritten from a yes/no question into the
wh-question they were always asking ("What will OpenAI's valuation hit by
December 31?"), which is Polymarket's OWN phrasing for the same family — 558 of
our rows (52 open) already arrive that way, blank-free.

Applied to the live open population: **87 rows printed a hole after the trailing
rule alone, 52 after both.** Every one of the 35 rewrites was read back off
production before this shipped, as were the 49 the rule reaches in the resolved
population; none produces a broken sentence.

The remaining 52 are the DIRECTIONAL (37), ADJECTIVE-SLOT (2) and EMBEDDED (13)
controls below. They wait for the ingest join, which stays open on #3513.

────────────────────────────────────────────────────────────────────────────
THIRD SHIP, 2026-09-25 (discover/489): THE DIRECTIONAL LADDER, RE-ASKED.

Still live at 04:1xZ, 1280px Discover shop, card 25 of the landing page and the
H1 of the page it links to:

    Meta (META) closes above ___ on September 25?
        $710 90%   $720 90%   $730 90%   $740 88%   More likely than not: $740

The directional carve-out was right that "above" cannot be DROPPED — the rungs
are floors. It never had to keep the blank: re-asked as "How high will Meta
(META) close on September 25?", every rung reads as a level reached, which is
what each "above" rung is, and the card's own caption (highest rung at ≥50%)
is only true under that reading. Census, open rows, Postgres regex
``above\\s*(_{2,}|\\.{3,})``: 36 — 33 are three stock-ticker frames (eleven
tickers each), all rewritten; the 3 with no price verb ("Amazon 2026 capex
above ___?") stay byte-identical. A 1,000-row read of the resolved population:
956 rewritten, every one to "How high will …" with no blank left.
"""

import ast
import re
from pathlib import Path
from types import SimpleNamespace

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
    "Anthropic IPO closing market cap above ___ ?",
]

# (stored name, what a reader should see) for the DIRECTIONAL rule — the three
# stock-ticker frames, real open rows read 2026-09-25 04:2xZ. The subject keeps
# every character it arrived with: an ampersand and digits (S&P 500), a
# multi-word commodity (WTI Crude Oil), and the unspaced `above___?`.
DIRECTIONAL_REWRITTEN = [
    (
        "Meta (META) closes above ___ on September 25?",
        "How high will Meta (META) close on September 25?",
    ),
    (
        "S&P 500 (SPY) closes above ___ on September 25?",
        "How high will S&P 500 (SPY) close on September 25?",
    ),
    (
        "WTI Crude Oil (WTI) closes above ___ on September 25?",
        "How high will WTI Crude Oil (WTI) close on September 25?",
    ),
    (
        "Will Apple (AAPL) close above ___ end of September?",
        "How high will Apple (AAPL) close at the end of September?",
    ),
    (
        "Will Opendoor (OPEN) close above ___ end of September?",
        "How high will Opendoor (OPEN) close at the end of September?",
    ),
    (
        "Will Apple (AAPL) finish week of September 7 above___?",
        "How high will Apple (AAPL) finish the week of September 7?",
    ),
    (
        "Will Amazon (AMZN) finish week of September 21 above___?",
        "How high will Amazon (AMZN) finish the week of September 21?",
    ),
]

# 🔴 THE DIRECTIONAL CONTROL. Each is ONE feature away from a rewritten row
# above, and that feature is what refuses it: a comparator nobody measured
# ("below" — zero open rows), a subject that is not a `Name (TICKER)`, a
# comparator the frame does not name ("at"), and a trailing clause the frame
# does not end on. `test_each_control_is_one_feature_from_firing` proves the
# rule reaches each shape when that one feature is put back.
DIRECTIONAL_FRAME_REFUSED = [
    ("Meta (META) closes below ___ on September 25?", "below", "above"),
    ("Gold closes above ___ on September 25?", "Gold ", "Gold (GC) "),
    ("Meta (META) closes at ___ on September 25?", " at ", " above "),
    (
        "Will Apple (AAPL) close above ___ end of September or later?",
        " or later?",
        "?",
    ),
]

# The blank is mid-sentence with real words after it, and NO rule here reaches
# it. "Claude Code Commits hit ___ by May 31?" is the interesting member: the
# object-slot rewrite would read fine, but the sentence has no "Will" to turn
# into "What will", and inventing one is composing copy rather than re-voicing
# the venue's. One measured row; it keeps the hole.
EMBEDDED_UNTOUCHED = [
    "Will any AI model reach ___ Overall Arena Score by December 31?",
    "Nasdaq 100 (NDX) above ___ end of 2026?",
    "Claude Code Commits hit ___ by May 31?",
    "Will a Chinese company have a top ___ AI model by December 31?",
    "North Korea x South Korea diplomatic meeting by...? (direct or indirect)",
    "Will Claude go down on __ days in September?",
    "Will US crude oil reserves fall to __ by September 25?",
]

# (stored name, what a reader should see) for the OBJECT-SLOT rule. Real rows,
# covering every shape the census found: 2- and 3-underscore blanks, the blank
# glued to the verb, a name that is ALREADY a wh-question, both apostrophes
# Polymarket writes (U+0027 and U+2019), and both measured tail openers.
OBJECT_SLOT_REWRITTEN = [
    (
        "Will OpenAI's valuation hit __ by December 31?",
        "What will OpenAI's valuation hit by December 31?",
    ),
    (
        "Will Anthropic’s valuation hit __ by September 30?",
        "What will Anthropic’s valuation hit by September 30?",
    ),
    ("Will EUR/USD hit __ in 2026?", "What will EUR/USD hit in 2026?"),
    ("Will SOFR hit __ in February?", "What will SOFR hit in February?"),
    (
        "Will the 30-year Mortgage Rate hit __ in 2026?",
        "What will the 30-year Mortgage Rate hit in 2026?",
    ),
    ("Will gas hit __ by end of September?", "What will gas hit by end of September?"),
    # Already a wh-question upstream; only the glued blank has to go.
    (
        "What will Gold (GC) hit__ by end of December?",
        "What will Gold (GC) hit by end of December?",
    ),
    ("Will gas hit__ by end of March?", "What will gas hit by end of March?"),
    # Three underscores, and a subject with no possessive at all.
    (
        "Will Alien arrests in New York hit ___ by June 30?",
        "What will Alien arrests in New York hit by June 30?",
    ),
    (
        "Will Gold (GC) hit __ by end of March?",
        "What will Gold (GC) hit by end of March?",
    ),
]

# 🔴 THE OBJECT-SLOT CONTROL. Each of these MATCHES the object-slot pattern and
# is refused by its TAIL test, because the blank qualifies the words after it
# instead of standing in for them. 19 distinct production names; the rewrite
# would print "What will MrBeast hit Billion views by June 30?".
#
# The last two are the ones that prove the tail test is doing work rather than
# describing the first two: they were found in the RESOLVED population after
# the rule was written against the open one.
ADJECTIVE_SLOT_UNTOUCHED = [
    "Will MrBeast hit ___ Billion views by September 30?",
    "Will MrBeast hit ___ Million subscribers by September 30?",
    "Will USD hit ___ Iranian rials by March 31?",
    "Will USD hit ___ Indonesian rupiah by June 30?",
    "Will Crude Oil (CL) hit__ Week of March 16?",
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

    2026-09-25: the rows with a price VERB left this list for
    `TestTheDirectionalLadderIsReAskedAsHowHigh`, which keeps the floor
    reading without the word. What remains has no verb to re-ask with.
    """

    @pytest.mark.parametrize("name", DIRECTIONAL_UNTOUCHED)
    def test_byte_identical(self, name):
        assert clean_market_display_name(name) == name


class TestTheDirectionalLadderIsReAskedAsHowHigh:
    """"X closes above ___ on D?" -> "How high will X close on D?".

    "How high" asks for a level REACHED, so each rung under it is a floor —
    the reading "above" gave it — and the word no longer has to be printed.
    """

    @pytest.mark.parametrize("stored,shown", DIRECTIONAL_REWRITTEN)
    def test_the_reader_gets_the_how_high_question(self, stored, shown):
        assert clean_market_display_name(stored) == shown

    @pytest.mark.parametrize("stored,shown", DIRECTIONAL_REWRITTEN)
    def test_no_blank_survives(self, stored, shown):
        assert not re.search(r"_{2,}|\.{3,}", clean_market_display_name(stored))

    @pytest.mark.parametrize("stored,shown", DIRECTIONAL_REWRITTEN)
    def test_the_ticker_subject_survives_verbatim(self, stored, shown):
        subject = re.search(r"\A(?:Will )?(.+?\([A-Z]+\))", stored).group(1)
        assert subject in clean_market_display_name(stored)

    @pytest.mark.parametrize("stored,shown", DIRECTIONAL_REWRITTEN)
    def test_exactly_one_question_mark_and_it_is_last(self, stored, shown):
        result = clean_market_display_name(stored)
        assert result.count("?") == 1 and result.endswith("?")

    @pytest.mark.parametrize("stored,_c,_r", DIRECTIONAL_FRAME_REFUSED)
    def test_the_control_is_byte_identical(self, stored, _c, _r):
        assert clean_market_display_name(stored) == stored

    @pytest.mark.parametrize("stored,refused,restored", DIRECTIONAL_FRAME_REFUSED)
    def test_each_control_is_one_feature_from_firing(self, stored, refused, restored):
        """A control the rule could never reach would pass while testing nothing."""
        assert stored.count(refused) == 1
        fixed = stored.replace(refused, restored)
        assert clean_market_display_name(fixed).startswith("How high will ")


class TestTheEmbeddedBlankIsLeftAlone:
    """A blank with real text after it is not a trailing blank.

    Removing it yields "Will Apple (AAPL) close above end of September?" —
    a sentence no reader can parse. 36 rows on production.
    """

    @pytest.mark.parametrize("name", EMBEDDED_UNTOUCHED)
    def test_byte_identical(self, name):
        assert clean_market_display_name(name) == name


class TestTheObjectSlotQuestionIsRevoiced:
    """A yes/no question becomes the wh-question it was always asking.

    "Will X hit __ by D?" -> "What will X hit by D?".

    The verb is NOT dropped — that is the whole difference from the directional
    class. "hit" is what the question asks; "above" is the comparator the ladder
    is built from. Deleting a verb leaves nonsense, deleting a comparator leaves
    a lie, and only one of those is repairable by re-voicing the sentence.
    """

    @pytest.mark.parametrize("stored,shown", OBJECT_SLOT_REWRITTEN)
    def test_the_reader_gets_the_wh_question(self, stored, shown):
        assert clean_market_display_name(stored) == shown

    @pytest.mark.parametrize("stored,shown", OBJECT_SLOT_REWRITTEN)
    def test_no_blank_survives(self, stored, shown):
        result = clean_market_display_name(stored)
        assert not re.search(r"(_{2,}|\.{3,})", result)

    @pytest.mark.parametrize("stored,shown", OBJECT_SLOT_REWRITTEN)
    def test_exactly_one_question_mark_and_it_is_last(self, stored, shown):
        result = clean_market_display_name(stored)
        assert result.count("?") == 1
        assert result.endswith("?")

    @pytest.mark.parametrize("stored,shown", OBJECT_SLOT_REWRITTEN)
    def test_the_verb_survives_the_rewrite(self, stored, shown):
        """Dropping "hit" would give "What will EUR/USD in 2026?"."""
        assert " hit" in clean_market_display_name(stored)

    @pytest.mark.parametrize("stored,shown", OBJECT_SLOT_REWRITTEN)
    def test_it_is_no_longer_a_yes_no_question(self, stored, shown):
        """A ladder of eight prices under "Will …?" is the original defect.

        "Will OpenAI's valuation hit by December 31?" would be worse than the
        blank: a yes/no sentence over a list of candidate answers.
        """
        assert clean_market_display_name(stored).startswith("What will ")

    def test_the_phrasing_is_the_venue_s_own(self):
        """558 of our rows (53 open) already arrive in exactly this form.

        This is a re-voicing of Polymarket's sibling titles, not copy we wrote:
        "What will Fed Rate hit before 2027?" and "What will S&P 500 (SPX) hit
        by end of December?" are stored, blank-free, from the same ingest.
        Those must pass through untouched, which also pins the rule's shape:
        an already-clean wh-question is not rewritten twice.
        """
        for venue_name in (
            "What will Fed Rate hit before 2027?",
            "What will S&P 500 (SPX) hit by end of December?",
            "What will Apple (AAPL) hit in February 2026?",
        ):
            assert clean_market_display_name(venue_name) == venue_name


class TestTheAdjectiveSlotIsLeftAlone:
    """🔴 DO NOT "FIX" THIS CLASS BY WIDENING THE TAIL LIST.

    "Will MrBeast hit ___ Billion views by June 30?" reaches the object-slot
    pattern, but the blank is a quantity qualifying "Billion views" — it is not
    the object. Re-voicing it gives "What will MrBeast hit Billion views by June
    30?", which is not a sentence, so the tail test refuses it and the reader
    keeps the (honest) hole until the ingest join lands.

    The tail test was written against two open rows and then, re-measured on
    2026-09-16, refused seventeen distinct names in the resolved population it
    had never seen — "Iranian rials", "Indonesian rupiah", "Week of March 16".
    That is the reason it is a rule about the tail and not a list of names.
    """

    @pytest.mark.parametrize("name", ADJECTIVE_SLOT_UNTOUCHED)
    def test_byte_identical(self, name):
        assert clean_market_display_name(name) == name

    @pytest.mark.parametrize("name", ADJECTIVE_SLOT_UNTOUCHED)
    def test_the_control_actually_reaches_the_rule_it_is_refused_by(self, name):
        """Guards the control against going vacuous.

        If the object-slot PATTERN stops matching these — a tightened verb
        list, a changed anchor — `test_byte_identical` still passes while
        proving nothing about the tail test. Assert the refusal happens at the
        tail, i.e. that the pattern really did match first.
        """
        from app.utils.market_display_name import _OBJECT_SLOT

        assert _OBJECT_SLOT.match(name.strip()) is not None


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


# ---------------------------------------------------------------------------
# The card and the page it links to ask the SAME question
# ---------------------------------------------------------------------------


def _holed_market(name: str):
    """A futures market as production stores one, with a template blank."""
    return SimpleNamespace(
        id=115349,
        name=name,
        description=None,
        category="economics",
        source="polymarket",
        external_id="192787",
        status="open",
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=2,
        llm_sport_category="economics",
        mutually_exclusive=False,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id="polymarket:192787",
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=[],
    )


class TestTheDetailPageAsksTheSameQuestionAsTheCard:
    """#6267 cleaned the card and left the page it links to holed.

    Photographed 2026-09-15 at 390px: `/futures/115349`'s H1 read "What will
    Gold (GC) hit__ by end of December?" while the Discover card for the same
    market had already been cleaned. A reader who taps a question should not be
    shown a different, broken one — and the divergence is worse than the
    original defect, because it makes the two surfaces look like different
    markets.
    """

    @pytest.fixture
    def detail(self):
        from app.routes.futures import _format_market_detail

        return lambda market: _format_market_detail(market, None, set())

    @pytest.mark.parametrize(
        "stored,shown",
        [
            OBJECT_SLOT_REWRITTEN[6],  # the photographed H1
            (
                "Netflix (NFLX) closes week of Sep 14 at ___?",
                "Netflix (NFLX) closes week of Sep 14?",
            ),
            DIRECTIONAL_REWRITTEN[0],  # /futures/61311441's family, 9/25 shop
        ],
    )
    def test_the_detail_payload_serves_the_cleaned_question(
        self, detail, stored, shown
    ):
        assert detail(_holed_market(stored))["name"] == shown

    @pytest.mark.parametrize("name", DIRECTIONAL_UNTOUCHED + ADJECTIVE_SLOT_UNTOUCHED)
    def test_the_carve_outs_reach_the_detail_page_unchanged(self, detail, name):
        """The route must not acquire a second, looser opinion of its own."""
        assert detail(_holed_market(name))["name"] == name

    def test_a_name_with_no_blank_is_served_byte_identical(self, detail):
        name = "Who will win the 2026 World Series?"
        assert detail(_holed_market(name))["name"] == name


# ---------------------------------------------------------------------------
# The one thing that makes cleaning a PAYLOAD field safe
# ---------------------------------------------------------------------------

#: Mirrors of the only two client tests that READ `name` to make a decision
#: rather than to print it (`frontend/lib/eventKey.ts`): `isWinnerMarketName`
#: (WINNER_RE minus MATCHUP_RE) and `awardsEventKey`'s name stems. Restated
#: here rather than imported because they live in TypeScript; they are pinned
#: against drift by the companion jest test named in the class docstring.
_WINNER_RE = re.compile(r"\b(winner|champion|champ|to win)\b", re.I)
_MATCHUP_RE = re.compile(r"\b(vs\.?|v\.?|def\.?|beats?)\b", re.I)
_AWARDS_STEMS = ("academy award", "oscar", "emmy", "grammy", "tony award")


def _interpreted_verdicts(name: str) -> tuple[bool, tuple[bool, ...]]:
    """Every decision a client makes FROM this string, as a comparable value."""
    winner = bool(_WINNER_RE.search(name)) and not _MATCHUP_RE.search(name)
    lowered = name.lower()
    return winner, tuple(stem in lowered for stem in _AWARDS_STEMS)


class TestCleaningNeverChangesADecisionAClientMakesFromTheName:
    """🔴 THE CONSTRAINT THIS MODULE'S OWN DOCTRINE IMPOSES ON THE ROUTE.

    `_format_market_detail` serves `name` as a PAYLOAD field, and
    `frontend/app/futures/[id]/page.tsx` passes the whole payload to
    `marketEventKey()` — so this is a string the client interprets, not only
    one it prints. Cleaning it is safe only because every interpreting step is
    invariant under the cleaning:

      * `combatCardKey` reads `external_id` only — name-independent.
      * `awardsEventKey` tests for a ceremony stem; no rule here can add or
        remove one (both rules only delete a blank, a preposition, or promote
        "Will" to "What will").
      * `marketEventKey` reaches the name-derived `cleanSlug` ONLY when
        `llm_sport_category == "tennis"` AND the name is a winner field.
        Measured 2026-09-16: of 133,033 tennis rows, exactly ONE carries a
        blank — "Will Novak Djokovic announce his retirement by...?" — and it
        has no winner word before or after cleaning, so it returns null at the
        winner gate and never reaches the slug.

    This test pins the general property rather than that one row: a rule added
    later that rewrites "champion" or drops "to win" would change a LINK, not
    just a label, and must fail here first.
    """

    @pytest.mark.parametrize(
        "name",
        [stored for stored, _ in CLEANED]
        + DIRECTIONAL_UNTOUCHED
        + EMBEDDED_UNTOUCHED
        + ADJECTIVE_SLOT_UNTOUCHED
        + NO_PLACEHOLDER_UNTOUCHED
        + [stored for stored, _ in OBJECT_SLOT_REWRITTEN]
        + [stored for stored, _ in DIRECTIONAL_REWRITTEN]
        + [stored for stored, _c, _r in DIRECTIONAL_FRAME_REFUSED]
        + [
            # The live specimens, carried so the corpus cannot lose them.
            "Will Novak Djokovic announce his retirement by...?",
            "Republicans favored to win the Senate on Nate Silver's Bulletin by...?",
        ],
    )
    def test_the_verdicts_are_identical_before_and_after(self, name):
        assert _interpreted_verdicts(name) == _interpreted_verdicts(
            clean_market_display_name(name)
        )

    def test_the_mirror_is_not_vacuous(self):
        """A corpus that trips neither test would pass while asserting nothing."""
        winners = [
            n
            for n in NO_PLACEHOLDER_UNTOUCHED
            + ["Republicans favored to win the Senate on Nate Silver's Bulletin by...?"]
            if _interpreted_verdicts(n)[0]
        ]
        assert winners, "no winner-field name in the corpus — the guard is asleep"
        assert _interpreted_verdicts("Oscar winner: Best Picture?")[1][1] is True
