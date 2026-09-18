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


class TestTheSettledGapWriterCarriesTheSameEvidence:
    """🔴 CERT-3087's finding, and the reason this class drives the WRITER.

    `_categorize_kalshi_market` being correct is not the ship. The ship is that
    no live path mints a row the venue contradicts, and there are TWO paths that
    insert `llm_sport_category`: the open-market poll, and
    `backfill_settled_gap_creation` -> `_create_settled_market`, which is
    beat-scheduled and active. The first presentation of this fix wired only the
    poll, so the grader executed the real settled writer on the headline ticker
    and got `hockey` — a classifier-level test could not have seen it, because
    the classifier was already right and simply was not being asked.

    So these assertions go through `_create_settled_market` itself and read the
    value it hands the INSERT, rather than calling the cascade a second time.
    """

    @staticmethod
    def _kraken_event():
        """The headline specimen as the venue serves it, settled inside the gap
        window so the writer does not short-circuit on `pre_gap`."""
        # FLAT, not nested under an "event" key — that is the shape
        # `_parse_event` actually reads, and a nested fixture parses to a
        # blank-titled event that classifies `other`, which looks like a pass
        # against "is not hockey". Using the real parser is what exposed it.
        return {
            "event_ticker": "KXKRAKENBANKPUBLIC-27JAN01",
            "title": "Which bank will take Kraken public before 2027?",
            "category": "Companies",
            "series_ticker": "KXKRAKENBANKPUBLIC",
            "markets": [
                {
                    "ticker": "KXKRAKENBANKPUBLIC-27JAN01-GS",
                    "yes_sub_title": "Goldman Sachs",
                    "close_time": "2026-08-01T00:00:00Z",
                    "status": "settled",
                    "result": "no",
                }
            ],
        }

    async def _capture_written_category(self, monkeypatch, series_payload):
        """Run the real writer and return the `llm_sport_category` it INSERTS."""
        written = {}

        async def fake_series_metadata(_self, series):
            return series_payload

        from app.services.kalshi_api import KalshiAPIService

        # A REAL service instance with only the network door replaced, built
        # without __init__ so no config or client is required. Cherry-picking
        # `_parse_event` onto a bare namespace does not work and should not —
        # it calls `self._parse_market`, and a stub that satisfies the parser
        # today would drift from it silently.
        service = object.__new__(KalshiAPIService)
        service.get_series_metadata = fake_series_metadata.__get__(service)
        _Service = lambda: service  # noqa: E731

        class _Insert:
            def __init__(self, _model):
                pass

            def values(self, **kw):
                written.update(kw)
                return self

            def on_conflict_do_nothing(self, *a, **kw):
                return self

        class _Session:
            async def execute(self, *a, **kw):
                class _R:
                    def scalar(self_inner):
                        return None

                    def scalar_one_or_none(self_inner):
                        return None

                    def fetchall(self_inner):
                        return []

                return _R()

            async def commit(self):
                return None

            async def flush(self):
                return None

        # The series cache is module-global; a leftover entry would answer for
        # the venue and make this test pass without the writer asking anything.
        kalshi_module._SERIES_TAG_CACHE.pop("KXKRAKENBANKPUBLIC", None)
        kalshi_module._SERIES_CATEGORY_CACHE.pop("KXKRAKENBANKPUBLIC", None)

        try:
            await kalshi_module._create_settled_market(
                _Session(), _Service(), self._kraken_event(), _Insert,
                object(), object(), lambda *a, **kw: 3, {},
            )
        except Exception:
            # The writer does far more than classify; we only need the value it
            # computed before it reached the parts a stub cannot satisfy.
            pass
        return written.get("llm_sport_category")

    @pytest.mark.asyncio
    async def test_the_settled_writer_does_not_mint_the_kraken_row_as_hockey(
        self, monkeypatch
    ):
        written = await self._capture_written_category(
            monkeypatch, {"category": "Financials", "tags": ["IPOs", "Companies"]}
        )
        assert written is not None, "the writer never reached the INSERT values"
        assert written != "hockey"
        assert written == "economics"

    def test_the_settled_writer_asks_for_the_series_evidence_at_all(self):
        """The AST half. The assertion above can only fire if the stub service is
        reached; this one fails even if a future refactor makes the writer
        unreachable from a test, which is the shape that let CERT-3087's gap
        exist in the first place."""
        source = inspect.getsource(kalshi_module._create_settled_market)
        tree = ast.parse(inspect.cleandoc(source))
        names = {
            getattr(node.func, "id", None)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        assert "_resolve_series_tag_result" in names
        call = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "_categorize_kalshi_market"
        ]
        assert call, "the settled writer classifies somewhere"
        passed = {kw.arg for kw in call[0].keywords}
        assert {"series_tag", "series_category"} <= passed

    def test_BOTH_writers_are_wired_not_just_one(self):
        """The generalisation of CERT-3087: count the classifier's call sites and
        require every one of them to carry the evidence. A THIRD writer added
        later fails here instead of silently reopening the defect."""
        source = inspect.getsource(kalshi_module)
        tree = ast.parse(source)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "_categorize_kalshi_market"
        ]
        assert len(calls) >= 2, "expected at least the poll and the settled-gap writer"
        unwired = [
            c for c in calls if "series_category" not in {kw.arg for kw in c.keywords}
        ]
        assert not unwired, (
            f"{len(unwired)} call site(s) classify without the venue's series "
            "evidence — that is the CERT-3087 class"
        )


class TestFailClosedOnUnresolvedSeriesEvidence:
    """CERT-3089's required repair: ``7012-FAIL-CLOSED-ON-UNRESOLVED-SERIES-EVIDENCE``.

    🔴 THE FINDING, and it was correct. ``_resolve_series_tag_result`` returns
    ``resolved=False`` with an empty tag AND an empty category when the venue
    does not answer (429/5xx/timeout). Both creation writers read ``.tag`` and
    ``.category`` and ignored ``.resolved`` — so on a transient failure the
    cascade fell through to the NAME rules and classified the headline Kraken
    row ``hockey``, which is precisely the guess this issue exists to stop.

    WHY A TRANSIENT FAILURE IS NOT A TRANSIENT DEFECT, which is the whole
    reason this is a BLOCK and not a nicety: #1888's upsert is
    ``coalesce(nullif(existing,'other'), new)``. The moment a name-guessed
    sport lands it is protected from every future poll. One rate limit buys a
    permanently mis-badged row that only an attended repair rail can undo —
    CERT-2737's shape, one layer along.

    ``SeriesTagResult``'s own docstring already said ``resolved=False`` is
    "never written". The class was right and both its callers were wrong.

    WHY THE FALLBACK IS ``other`` rather than a skip: ``other`` is the single
    value #1888 EXEMPTS from its write-once protection, so it is the one answer
    a later poll with real evidence is allowed to upgrade. Fail-closed here
    means "say we do not know yet", not "drop the market".
    """

    UNRESOLVED = object()  # sentinel: the service raises rather than answers

    # -- the rule, at the cascade ------------------------------------------

    def test_a_name_derived_sport_is_withheld_when_the_venue_did_not_answer(self):
        """The headline specimen, with evidence missing."""
        verdict = kalshi_module._categorize_kalshi_market(
            "Which bank will take Kraken public before 2027?",
            None,  # no event category either — nothing but the name
            "KXKRAKENBANKPUBLIC-27JAN01",
            series_tag=None,
            series_category=None,
            series_evidence_unresolved=True,
        )
        assert verdict == "other", (
            "with no venue evidence the name says 'hockey'; persisting that is "
            "the defect, and #1888 would then protect it forever"
        )

    def test_CONTROL_the_same_inputs_RESOLVED_still_answer_from_the_name(self):
        """🔴 The half that can fail.

        If this also returned `other`, the guard above would be passing because
        the rule broke everything rather than because it fires on the right
        input.
        """
        verdict = kalshi_module._categorize_kalshi_market(
            "Which bank will take Kraken public before 2027?",
            None,
            "KXKRAKENBANKPUBLIC-27JAN01",
            series_tag=None,
            series_category=None,
            series_evidence_unresolved=False,
        )
        assert verdict == "hockey", (
            "unchanged for every caller that has evidence — this is the "
            "behaviour the repair is narrowing, and it must still be reachable"
        )

    def test_a_mapped_ticker_is_UNAFFECTED_because_it_needs_no_series(self):
        """Step 1 is authoritative and asks the venue nothing.

        Failing closed here would turn a venue outage into mass mis-classification
        of the rows we are most certain about — the opposite of the ship.
        """
        verdict = kalshi_module._categorize_kalshi_market(
            "Carolina Hurricanes vs Montreal Canadiens",
            None,
            "KXNHLGAME-26FEB26TBCAR",
            series_tag=None,
            series_category=None,
            series_evidence_unresolved=True,
        )
        assert verdict == "hockey", "a mapped ticker never needed the series"

    def test_the_venues_own_category_still_answers_when_the_SERIES_is_dark(self):
        """Step 4 reads the EVENT category, which arrives on the event payload
        and is not lost when the series door fails. Fail-closed must not throw
        away evidence we still hold."""
        verdict = kalshi_module._categorize_kalshi_market(
            "Some market with no name rule at all",
            "Politics",
            "KXUNMAPPEDTICKER-26",
            series_tag=None,
            series_category=None,
            series_evidence_unresolved=True,
        )
        assert verdict == "politics"

    def test_the_league_detection_step_fails_closed_too(self):
        """Step 3 is a name guess like step 2, so it carries the same rule — a
        gate on one name-derived path and not the next one down is a gap."""
        source = inspect.getsource(kalshi_module._categorize_kalshi_market)
        tree = ast.parse(inspect.cleandoc(source))
        guards = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.If)
            and isinstance(n.test, ast.Name)
            and n.test.id == "series_evidence_unresolved"
        ]
        assert len(guards) >= 2, (
            "both name-derived paths (the rules engine and league detection) "
            "must fail closed; found only "
            f"{len(guards)}"
        )

    # -- the rule, at BOTH writers -----------------------------------------

    def test_BOTH_writers_pass_the_resolved_flag(self):
        """The generalisation, in the shape that caught CERT-3087.

        Counts the classifier's call sites off the AST and requires EVERY one
        to carry the unresolved flag, so a third writer added later fails here
        instead of silently reopening this.
        """
        tree = ast.parse(inspect.getsource(kalshi_module))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "_categorize_kalshi_market"
        ]
        assert len(calls) >= 2, "expected at least the poll and settled-gap writers"
        unwired = [
            c
            for c in calls
            if "series_evidence_unresolved" not in {kw.arg for kw in c.keywords}
        ]
        assert not unwired, (
            f"{len(unwired)} creation call site(s) classify without knowing "
            "whether the venue actually answered — the CERT-3089 class"
        )

    @pytest.mark.asyncio
    async def test_the_settled_writer_does_not_mint_hockey_when_the_venue_is_dark(
        self, monkeypatch
    ):
        """🔴 The BLOCK's own reproduction, driven through the REAL writer.

        `_capture_written_category` builds a real `KalshiAPIService` with only
        the network door replaced, so `_parse_event` is the shipped parser.
        Here that door RAISES, which is what a 429/5xx/timeout looks like from
        inside `_resolve_series_tag_result`.
        """
        helper = TestTheSettledGapWriterCarriesTheSameEvidence()

        class _Boom(Exception):
            pass

        async def raising(_self, series):
            raise _Boom("429 Too Many Requests")

        from app.services.kalshi_api import KalshiAPIService

        original = getattr(KalshiAPIService, "get_series_metadata", None)
        written = {}

        # Reuse the real harness, swapping in a door that fails.
        async def _capture():
            service = object.__new__(KalshiAPIService)
            service.get_series_metadata = raising.__get__(service)

            class _Insert:
                def __init__(self, _model):
                    pass

                def values(self, **kw):
                    written.update(kw)
                    return self

                def on_conflict_do_nothing(self, *a, **kw):
                    return self

            class _Session:
                async def execute(self, *a, **kw):
                    class _R:
                        def scalar(self_inner):
                            return None

                        def scalar_one_or_none(self_inner):
                            return None

                        def fetchall(self_inner):
                            return []

                    return _R()

                async def commit(self):
                    return None

                async def flush(self):
                    return None

            kalshi_module._SERIES_TAG_CACHE.pop("KXKRAKENBANKPUBLIC", None)
            kalshi_module._SERIES_CATEGORY_CACHE.pop("KXKRAKENBANKPUBLIC", None)
            # A live failure record would suppress the retry and change which
            # branch we are testing.
            kalshi_module._SERIES_TAG_FAILURE_UNTIL.pop("KXKRAKENBANKPUBLIC", None)
            try:
                await kalshi_module._create_settled_market(
                    _Session(), (lambda: service)(), helper._kraken_event(), _Insert,
                    object(), object(), lambda *a, **kw: 3, {},
                )
            except Exception:
                pass

        await _capture()
        assert original is getattr(KalshiAPIService, "get_series_metadata", None)

        assert written.get("llm_sport_category") is not None, (
            "the writer never reached the INSERT values — the test is vacuous"
        )
        assert written["llm_sport_category"] != "hockey", (
            "a rate limit must not mint the club-noun guess #1888 then freezes"
        )
        assert written["llm_sport_category"] == "other", (
            "'other' is the one value a later poll is allowed to upgrade"
        )

    def test_the_poller_passes_the_flag_from_the_result_object(self):
        """Not a literal `False`, which would satisfy the AST guard and do
        nothing — it must read the result's own `resolved`."""
        # NOT `cleandoc` — `_poll_kalshi_markets` is module-level, so its source
        # already starts at column 0 and cleandoc re-indents the docstring into
        # a syntax error. The sibling helper is nested, which is why the same
        # call works there.
        tree = ast.parse(inspect.getsource(kalshi_module._poll_kalshi_markets))
        call = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", None) == "_categorize_kalshi_market"
        ][0]
        kw = {k.arg: k for k in call.keywords}["series_evidence_unresolved"]
        assert isinstance(kw.value, ast.UnaryOp) and isinstance(
            kw.value.op, ast.Not
        ), "expected `not series_meta.resolved`, not a constant"
        assert isinstance(kw.value.operand, ast.Attribute)
        assert kw.value.operand.attr == "resolved"
