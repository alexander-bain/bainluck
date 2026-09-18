"""#7012 — a Kalshi market stops wearing a sport badge its own venue contradicts.

PILLAR: DISCOVER on TRUTH · SHIP: a reader browsing hockey stops being handed
"Which bank will take Kraken public before 2027?", and a reader browsing golf
stops being handed Williams-Sonoma's quarterly comparable-brand growth.

THE DEFECT. ``_categorize_kalshi_market`` is first-match-wins, and step 2 —
``categorize_by_rules`` on the market's NAME — answers before the venue's own
category is ever consulted. The name tokens collide with the ordinary world:

    "Which bank will take Kraken public before 2027?"   -> hockey   (the Seattle club)
    "Williams-Sonoma total comparable brand growth"     -> motorsports (the F1 team)
    "Which bills will become law in 2026?"              -> football (the Buffalo club)
    "Will Anthropic sign the Open Weights ... letter"   -> golf     ("Open")
    "NBA YoungBoy: Highest daily view count"            -> basketball (a rapper)
    "Will Donald Trump attend UFC 331?"                 -> mma      (a politics market)

THE RULE, and why it is NOT "the venue's category beats the name rules". That
wider form was the first draft and the LIVE POPULATION REFUSED IT. Measured
2026-09-18 20:55Z against Kalshi's own ``/series`` (notice 26 — the venue, not
our mirror) over ALL 29 open rows in the disagreement:

    KXMLBCBA            category Entertainment   tags ['Baseball']
    KXPERFORMSUPERBOWL  category Entertainment   tags ['Live Music', 'Football']

Both of our sport verdicts agree with the venue's own TAG and disagree only with
its CATEGORY, so the wider rule would have overruled the venue using the venue.
What ships instead is notice 40's doctrine ("the venue's own structure first; a
title match alone is a CANDIDATE, and enters only when a second independent
signal agrees") applied one step lower than step 1b applies it: a sport verdict
that rests on a name token alone yields to the venue's topic, and a sport
verdict with ANY venue signal behind it does not.

Scored on those 29 rows: **20 corrected, 2 protected, 7 out of reach.** The 7
are the Producers-Guild-Awards family, which is a DIFFERENT defect — the ticker
map holds a bare ``kxpga`` prefix and ``startswith`` hands ``KXPGAAWARDS-26-PIC``
to golf at step 1, before anything here runs. It has its own issue; this suite
pins the boundary rather than pretending the number is 27.

THE PREREQUISITE IS LOAD-BEARING, WHICH IS WHY IT IS TESTED AS SUCH.
``_resolve_series_tag_result`` used to end ``tag = tags[0]``. Under that, the
Super Bowl performers row resolves ``Live Music``, step 1b declines, and the new
step 2 rule DEMOTES IT TO ENTERTAINMENT — the fix would have shipped its own
regression. ``test_the_all_tags_scan_is_what_prevents...`` executes both
spellings and asserts the old one regresses, so nobody can delete the scan and
still read green.
"""

import ast
import inspect

import pytest

import app.tasks.kalshi as kalshi_module

from app.tasks.kalshi import (
    _categorize_kalshi_market,
    _kalshi_category_to_llm_category,
    _pick_series_tag,
    _VENUE_TOPIC_DEMOTION_TARGETS,
)
from app.utils.sport_keys import NON_SPORT_LLM_CATEGORIES


def categorize(name, venue_category, ticker, tags=()):
    """The cascade, fed the way the poller feeds it after #7012."""
    return _categorize_kalshi_market(
        name,
        venue_category,
        ticker,
        series_tag=_pick_series_tag(list(tags)),
        series_category=venue_category,
    )


# Every specimen below is a real open row, with the venue category and tags as
# Kalshi's own /series API returned them on 2026-09-18 20:55Z.
CORRECTED = [
    # (ticker, name, venue category, tags, was, becomes)
    (
        "KXKRAKENBANKPUBLIC-27JAN01",
        "Which bank will take Kraken public before 2027?",
        "Financials",
        ["IPOs", "Companies"],
        "hockey",
        "economics",
    ),
    (
        "KXMOVIECAST-PIR29",
        "Next Pirates of the Caribbean Movie: Cast",
        "Entertainment",
        ["Movies", "Television"],
        "baseball",
        "entertainment",
    ),
    (
        "KXJOHNNYDEPP-35",
        "Next Pirates of the Caribbean film: Will Johnny Depp be cast?",
        "Entertainment",
        ["Movies"],
        "baseball",
        "entertainment",
    ),
    (
        "KXWSM-26NOVCOMP",
        "Williams-Sonoma brand growth in Q3",
        "Financials",
        ["Companies", "KPIs"],
        "motorsports",
        "economics",
    ),
    (
        "KXBILLS",
        "Which bills will become law in 2026?",
        "Politics",
        ["Congress"],
        "football",
        "politics",
    ),
    (
        "KXTRUMPUFC-26SEP",
        "Will Donald Trump attend UFC 331?",
        "Politics",
        ["Trump"],
        "mma",
        "politics",
    ),
    (
        "KXYTVIEWSHIGH-YOU26OCT",
        "NBA YoungBoy: Highest daily view count in September 2026",
        "Entertainment",
        ["Views", "Music", "Monthly Views"],
        "basketball",
        "entertainment",
    ),
    (
        "KXCOMPANYACTIONANTH-27",
        "Will Anthropic sign the Open Weights and American AI Leadership letter",
        "Science and Technology",
        ["AI"],
        "golf",
        "tech",
    ),
    (
        "KXCHIEFSKANSAS-26AUG",
        "Will the Chiefs' Kansas stadium deal become binding in 2026?",
        "Politics",
        ["Local"],
        "football",
        "politics",
    ),
]


class TestTheVenueTopicBeatsABareNameGuess:
    @pytest.mark.parametrize(
        "ticker,name,venue,tags,was,becomes",
        CORRECTED,
        ids=[c[0] for c in CORRECTED],
    )
    def test_the_production_specimen_takes_the_venues_topic(
        self, ticker, name, venue, tags, was, becomes
    ):
        assert categorize(name, venue, ticker, tags) == becomes

    @pytest.mark.parametrize(
        "ticker,name,venue,tags,was,becomes",
        CORRECTED,
        ids=[c[0] for c in CORRECTED],
    )
    def test_the_sport_the_row_used_to_wear_is_gone(
        self, ticker, name, venue, tags, was, becomes
    ):
        """Paired with the assertion above on purpose. "It equals the topic"
        and "it is no longer the sport" are the same claim only while the
        topic and the sport differ, and a future edit that collapses both to
        `other` would satisfy the first reading of the first test."""
        assert categorize(name, venue, ticker, tags) != was

    def test_the_headline_specimen_is_rescued_by_the_SERIES_category(self):
        """`109341` is the reason `series_category` exists. Its EVENT category
        is `Companies`, which neither mapper in this module models, so the event
        signal alone leaves the name rule standing."""
        assert _kalshi_category_to_llm_category("Companies") is None
        name = "Which bank will take Kraken public before 2027?"
        ticker = "KXKRAKENBANKPUBLIC-27JAN01"

        event_only = _categorize_kalshi_market(name, "Companies", ticker)
        assert event_only == "hockey", "the event category cannot carry this row"

        with_series = _categorize_kalshi_market(
            name, "Companies", ticker, series_category="Financials"
        )
        assert with_series == "economics"


class TestTheControlsTheVenueItselfChooses:
    """The two rows the wider "category beats name" rule would have broken."""

    def test_CONTROL_a_venue_tag_naming_a_sport_keeps_the_sport(self):
        """KXPERFORMSUPERBOWL: the venue files it under Entertainment and tags
        it `['Live Music', 'Football']`. The tag is a venue signal, so the
        demotion must not fire."""
        assert (
            categorize(
                "Pro Football Championship Halftime Show: Performers",
                "Entertainment",
                "KXPERFORMSUPERBOWL-27B",
                ["Live Music", "Football"],
            )
            == "football"
        )

    def test_CONTROL_a_mapped_ticker_outranks_the_venues_category(self):
        """KXMLBCBA is protected one rail earlier than the row above — by the
        TICKER map (`kxmlb`), not by its `Baseball` tag. Recorded explicitly
        because the two controls look alike and are not: deleting the tag scan
        breaks one of them and not the other."""
        from app.utils.sport_keys import get_sport_key_from_ticker

        assert get_sport_key_from_ticker("KXMLBCBA-26DEC02") == "baseball_mlb"
        assert (
            categorize(
                "Pro Baseball new CBA agreement before Dec 2, 2026",
                "Entertainment",
                "KXMLBCBA-26DEC02",
                ["Baseball"],
            )
            == "baseball"
        )

    def test_the_all_tags_scan_is_what_prevents_a_regression_here(self):
        """THE PREREQUISITE, EXECUTED. Old behaviour was `tags[0]`. This drives
        both spellings on the same row and asserts the old one regresses — so
        the scan cannot be reverted as a tidy-up while this suite reads green."""
        tags = ["Live Music", "Football"]
        name = "Pro Football Championship Halftime Show: Performers"
        ticker = "KXPERFORMSUPERBOWL-27B"

        assert _pick_series_tag(tags) == "Football"
        assert tags[0] == "Live Music"

        old = _categorize_kalshi_market(
            name, "Entertainment", ticker,
            series_tag=tags[0], series_category="Entertainment",
        )
        new = _categorize_kalshi_market(
            name, "Entertainment", ticker,
            series_tag=_pick_series_tag(tags), series_category="Entertainment",
        )
        assert old == "entertainment", "the old spelling must show the regression"
        assert new == "football"


class TestPickSeriesTag:
    def test_the_first_tag_that_maps_to_a_sport_wins(self):
        assert _pick_series_tag(["Live Music", "Football"]) == "Football"

    def test_the_venues_own_order_decides_between_two_sports(self):
        assert _pick_series_tag(["Baseball", "Football"]) == "Baseball"

    def test_CONTROL_nothing_maps_so_the_first_tag_is_returned_as_before(self):
        """The overwhelming majority of series, and the shape whose behaviour
        must not move: the caller falls through to the name rules either way,
        and the value is what gets cached."""
        assert _pick_series_tag(["Movies", "Television"]) == "Movies"

    def test_CONTROL_no_tags_is_still_None(self):
        assert _pick_series_tag([]) is None
        assert _pick_series_tag(None) is None

    def test_CONTROL_a_single_sport_tag_is_unchanged(self):
        assert _pick_series_tag(["Baseball"]) == "Baseball"


class TestTheDemotionCannotDeleteAMarket:
    def test_crypto_is_never_a_demotion_target(self):
        """The poller `continue`s on a crypto verdict at BOTH call sites, so a
        demotion into crypto does not reclassify a market — it drops one. The
        exclusion is asserted at the set AND through the cascade, because a set
        that is right while the code reads a different set is no protection."""
        assert "crypto" in NON_SPORT_LLM_CATEGORIES
        assert "crypto" not in _VENUE_TOPIC_DEMOTION_TARGETS

        verdict = categorize(
            "Will the Kraken beat the Oilers?", "Crypto", "KXSOMETHINGUNMAPPED-27"
        )
        assert verdict != "crypto"

    def test_the_drop_branch_this_protects_still_exists(self):
        """If the `continue` ever goes away the exclusion above is dead weight
        and should be revisited — so the test names the branch it depends on
        rather than trusting a comment about it."""
        source = inspect.getsource(kalshi_module)
        assert 'sport_category == "crypto"' in source

    def test_other_is_never_a_demotion_target(self):
        """`other` is the absence of a topic. Demoting a confident wrong sport
        to `other` trades a bad answer for no answer."""
        assert "other" in NON_SPORT_LLM_CATEGORIES
        assert "other" not in _VENUE_TOPIC_DEMOTION_TARGETS


class TestEverythingElseIsUntouched:
    def test_CONTROL_a_real_sports_row_is_not_demoted(self):
        """The 123,071 game_prop and 96,866 championship rows: the venue files
        them under `Sports`, which maps to no topic, so no demotion is even
        considered."""
        assert _kalshi_category_to_llm_category("Sports") is None
        assert (
            categorize(
                "Will the Kraken beat the Oilers?", "Sports", "KXNHLGAME-26OCT01"
            )
            == "hockey"
        )

    def test_CONTROL_a_non_sport_name_verdict_is_left_alone(self):
        """The rule only ever fires on a SPORT verdict. Here the name rule
        already answers `economics` and the venue says `Entertainment` — a
        genuine disagreement between two non-sport topics, which this ship
        deliberately does NOT arbitrate. Pinned to the exact value because
        "is a non-sport category" would be satisfied by the demotion firing."""
        args = ("Will inflation exceed 3% in 2026?", "Entertainment", "KXSOMETHINGUNMAPPED-27")
        assert _categorize_kalshi_market(*args, series_category="Entertainment") == "economics"
        # …and identically with no venue signal at all, which is the proof that
        # the venue did not influence this row rather than agreeing with it.
        assert _categorize_kalshi_market(args[0], None, args[2]) == "economics"

    def test_CONTROL_no_venue_category_leaves_todays_answer(self):
        """A venue that says nothing is not evidence. The name rule stands, which
        is the safe fall-through #5637 chose for the same reason."""
        assert (
            categorize("Which bills will become law in 2026?", None, "KXBILLS")
            == "football"
        )

    def test_CONTROL_an_unmodelled_venue_word_leaves_todays_answer(self):
        assert _kalshi_category_to_llm_category("Companies") is None
        assert (
            categorize("Which bills will become law in 2026?", "Companies", "KXBILLS")
            == "football"
        )


class TestTheStepFourHoistIsBehaviourPreserving:
    """`_kalshi_category_to_llm_category` was lifted out of step 4 verbatim. The
    only intended difference is that "nothing matched" is now `None` rather than
    falling into `"other"`, and step 4 restores that with `or "other"`."""

    @pytest.mark.parametrize(
        "word,expected",
        [
            ("Golf", "golf"),
            ("Tennis", "tennis"),
            ("Soccer", "soccer"),
            ("Politics", "politics"),
            ("Elections", "politics"),
            ("Entertainment", "entertainment"),
            ("Economics", "economics"),
            ("Financials", "economics"),
            ("Science and Technology", "tech"),
            ("Climate and Weather", "weather"),
            ("Health", "health"),
            ("Olympics", "olympics"),
        ],
    )
    def test_the_vocabulary_maps_as_it_did(self, word, expected):
        assert _kalshi_category_to_llm_category(word) == expected

    def test_step_four_still_answers_other_for_an_unmodelled_word(self):
        """The hoist's `None` must not leak out of the cascade as `None`."""
        assert _kalshi_category_to_llm_category("Companies") is None
        assert (
            _categorize_kalshi_market("A market about nothing in particular", "Companies")
            == "other"
        )

    def test_step_four_still_answers_other_for_no_category(self):
        assert _categorize_kalshi_market("A market about nothing in particular", None) == "other"


class TestThePollerActuallyFeedsIt:
    """A classifier repaired in a module the caller does not feed is a fix that
    passes its own tests and changes nothing a reader sees. Read off the AST so
    it cannot pass on a comment."""

    def test_the_poller_passes_the_series_category(self):
        source = inspect.getsource(kalshi_module)
        tree = ast.parse(source)

        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "_categorize_kalshi_market"
        ]
        assert calls, "the cascade is called somewhere in this module"

        wired = [
            call
            for call in calls
            if any(kw.arg == "series_category" for kw in call.keywords)
        ]
        assert wired, (
            "no call site passes series_category — the Kraken row's only "
            "signal never reaches the classifier"
        )

    def test_the_poller_takes_the_result_form_not_the_bare_tag(self):
        """`_resolve_series_tag` returns only the tag, so a call site using it
        cannot see the category however well the classifier is written."""
        source = inspect.getsource(kalshi_module)
        tree = ast.parse(source)
        awaited = {
            getattr(node.func, "id", None)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        assert "_resolve_series_tag_result" in awaited
