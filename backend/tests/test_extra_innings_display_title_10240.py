"""A SEARCH CARD STOPS ASKING "…EXTRA INNINGS?: YANKEES VS. RAYS". #10240.

═══ WHAT A READER SAW ═══

`bainluck.com/search?q=yankees`, phone width, 2026-10-02 22:10Z: a card titled

    Will the game go to extra innings?: New York Yankees vs. Tampa Bay Rays

— a question mark followed directly by a colon. Polymarket's own text, stored
as-is: Gamma `markets?condition_ids=0x0f7eac3c…4b62` returns exactly that
`question` (`groupItemTitle = "Extra Innings"`, event `"New York Yankees vs.
Tampa Bay Rays"`); our row is `futures_markets.id = 63854825`, `group_id
polymarket:1113712`. 8 open markets carried `?:` that minute, every one a
polymarket extra-innings game prop.

═══ THE TWO HALVES, AND WHY BOTH ARE HERE ═══

1. `clean_market_display_name` (the shared display cleaner the market page and
   Discover already serve) gains a fifth rule, the public callable
   `rewrite_question_colon_display`: `?: A vs. B` -> `? — A vs. B`.
2. `_format_futures_for_search` served `rewrite_venue_league_vocabulary(name)`
   and never called that cleaner at all, so a helper-only fix would have left
   the search card raw. Its final `name` now runs through that ONE callable —
   not the whole cleaner. The cleaner's four blank-template rules have never
   reached the search card, and this slice does not change that: a blank
   template reads on the card exactly as it did before (the controls below).

The stored name is never rewritten: every assertion below also checks the row's
`name` is byte-identical after formatting.
"""

import pytest

from app.routes.events import _format_futures_for_search
from app.utils.market_display_name import (
    clean_market_display_name,
    rewrite_question_colon_display,
)
from app.utils.market_label_normalization import rewrite_venue_league_vocabulary

SPECIMEN = "Will the game go to extra innings?: New York Yankees vs. Tampa Bay Rays"
SPECIMEN_DISPLAY = (
    "Will the game go to extra innings? — New York Yankees vs. Tampa Bay Rays"
)


class _Market:
    """The attributes `_format_futures_for_search` reads off an ORM row."""

    def __init__(self, name, **kw):
        self.id = kw.get("id", 63854825)
        self.name = name
        self.market_tier = kw.get("market_tier", 5)
        self.llm_sport_category = kw.get("llm_sport_category", "baseball")
        self.category = kw.get("category", "sports")
        self.outcomes = []
        self.sport = None
        self.market_type = None
        self.status = "open"
        self.source = kw.get("source", "polymarket")
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = False


def _served_name(name: str, **kw) -> str:
    market = _Market(name, **kw)
    served = _format_futures_for_search(market)["name"]
    assert market.name == name, "the stored venue text must never be rewritten"
    return served


# ---------------------------------------------------------------------------
# The shared helper: the specimen and its siblings.
# ---------------------------------------------------------------------------


class TestTheSharedHelper:
    def test_the_production_specimen(self):
        assert clean_market_display_name(SPECIMEN) == SPECIMEN_DISPLAY

    @pytest.mark.parametrize(
        "raw, home, away",
        [
            (SPECIMEN, "New York Yankees", "Tampa Bay Rays"),
            (
                "Will the game go to extra innings?: Atlanta Braves vs. Los Angeles Dodgers",
                "Atlanta Braves",
                "Los Angeles Dodgers",
            ),
            (
                "Will the game go to extra innings?: Chicago Cubs vs Milwaukee Brewers",
                "Chicago Cubs",
                "Milwaukee Brewers",
            ),
        ],
    )
    def test_question_and_both_clubs_survive_with_one_separator(self, raw, home, away):
        shown = clean_market_display_name(raw)
        assert "?:" not in shown
        assert shown.count(" — ") == 1
        question, matchup = shown.split(" — ")
        assert question == "Will the game go to extra innings?"
        assert home in matchup and away in matchup
        # Nothing but the colon moved: removing the separator gives back the
        # venue's words in the venue's order.
        assert shown.replace("? — ", "?: ") == raw

    def test_idempotent(self):
        once = clean_market_display_name(SPECIMEN)
        assert clean_market_display_name(once) == once

    def test_surrounding_whitespace_does_not_defeat_the_rule(self):
        assert clean_market_display_name(f"  {SPECIMEN} ") == SPECIMEN_DISPLAY

    def test_the_cleaner_and_search_share_one_callable(self):
        # One grammar, not two copies: the cleaner's fifth rule IS the public
        # callable search applies, so the two surfaces cannot drift apart.
        assert rewrite_question_colon_display(SPECIMEN) == SPECIMEN_DISPLAY
        assert rewrite_question_colon_display(SPECIMEN) == clean_market_display_name(SPECIMEN)
        assert rewrite_question_colon_display(None) is None
        assert rewrite_question_colon_display("") == ""


class TestControlsStayByteIdentical:
    @pytest.mark.parametrize(
        "raw",
        [
            None,
            "",
            # Ordinary questions and Kalshi titles: a colon with no "?" before it.
            "Will the Yankees win the 2026 World Series?",
            "Pro Football: 2027 Champion",
            "New York Yankees vs. Tampa Bay Rays",
            "Yankees vs Rays: Total Runs",
            "Will the game go to extra innings?",
            # "?:" whose tail is not two sides of a game — unread shape.
            "What happens next?: The sequel",
            "Will it rain?: London",
            # A tail asking its own question.
            "Will the game go to extra innings?: Yankees vs. Rays?",
            # Two "?:" joins.
            "Who wins?: A vs. B?: C vs. D",
            # A template blank in the question half — unread, left alone.
            "Will the game go to ___ innings?: New York Yankees vs. Tampa Bay Rays",
            # No space after the colon: not the venue's shape.
            "Will the game go to extra innings?:New York Yankees vs. Tampa Bay Rays",
        ],
    )
    def test_unrecognised_shapes_are_untouched(self, raw):
        assert clean_market_display_name(raw) == raw

    @pytest.mark.parametrize(
        "raw, expected",
        [
            # The #3513 rules keep doing exactly what they did.
            ("Netanyahu out by...?", "Netanyahu out?"),
            ("Will EUR/USD hit __ in 2026?", "What will EUR/USD hit in 2026?"),
            # Threshold safeguard: the directional carve-out still refuses.
            ("Amazon 2026 capex above ___?", "Amazon 2026 capex above ___?"),
        ],
    )
    def test_existing_placeholder_rules_unchanged(self, raw, expected):
        assert clean_market_display_name(raw) == expected


# ---------------------------------------------------------------------------
# The actual search formatter — the surface the reader photographed.
# ---------------------------------------------------------------------------


class TestTheSearchCard:
    def test_the_specimen_card_reads_cleanly(self):
        assert _served_name(SPECIMEN) == SPECIMEN_DISPLAY

    def test_card_matches_the_market_page_it_opens(self):
        # `routes/futures.py` serves `clean_market_display_name(market.name)`.
        assert _served_name(SPECIMEN) == clean_market_display_name(SPECIMEN)

    def test_strawman_the_old_line_served_the_raw_join(self):
        # What the formatter published before this change, kept so the test
        # above is known to be able to fail.
        assert rewrite_venue_league_vocabulary(SPECIMEN) == SPECIMEN
        assert _served_name(SPECIMEN) != rewrite_venue_league_vocabulary(SPECIMEN)

    def test_league_vocabulary_rewrite_still_applies(self):
        assert _served_name("Pro Football: 2027 Champion", source="kalshi") == (
            "NFL: 2027 Champion"
        )

    @pytest.mark.parametrize(
        "raw",
        [
            # One specimen per blank-template rule of the cleaner (#3513 and
            # after). Each would CHANGE under `clean_market_display_name`; the
            # search card has never applied those rules and still must not.
            "Netanyahu out by...?",  # trailing blank
            "Will EUR/USD hit __ in 2026?",  # object slot
            "Meta (META) closes above ___ on September 25?",  # directional
            "Will any AI model reach ___ Coding Arena Score by December 31?",  # score slot
            # Threshold safeguard: a refusal everywhere.
            "Amazon 2026 capex above ___?",
        ],
    )
    def test_blank_templates_keep_their_prior_search_rendering(self, raw):
        prior = rewrite_venue_league_vocabulary(raw)
        assert _served_name(raw, llm_sport_category="politics", category="politics") == prior

    def test_strawman_the_whole_cleaner_would_have_changed_those_cards(self):
        # Proves the control above can fail: mounting all of
        # `clean_market_display_name` (PR #10258's first head) rewrote these.
        for raw in (
            "Netanyahu out by...?",
            "Will EUR/USD hit __ in 2026?",
            "Meta (META) closes above ___ on September 25?",
            "Will any AI model reach ___ Coding Arena Score by December 31?",
        ):
            assert clean_market_display_name(raw) != rewrite_venue_league_vocabulary(raw), raw

    @pytest.mark.parametrize(
        "raw",
        [
            "Will the Yankees win the 2026 World Series?",
            "Will the game go to extra innings?",
            "Amazon 2026 capex above ___?",
        ],
    )
    def test_ordinary_names_serve_unchanged(self, raw):
        assert _served_name(raw) == raw
