"""#5736 — a search group header hands the reader back their own words, cased.

WHAT A READER SEES. `futures_families[].label` for an `entity:` family is built
from the query the person typed. It was `query_label.title()`, and `str.title()`
lower-cases every letter after the first of every token, so on production
(2026-09-19 00:5xZ, measured before this change):

    typed `nfl`      -> served `Nfl`
    typed `mlb`      -> served `Mlb`
    typed `ncaa`     -> served `Ncaa`
    typed `NFL`      -> served `Nfl`        <- the reader capitalised it CORRECTLY
    typed `US Open`  -> served `Us Open`    <- and we lower-cased it back
    typed `atp`      -> served ['Grand Slam Tennis', 'Atp']

The last row is the whole argument in one response: two families, two arms, one
correctly cased by the house resolver (#6941) and one garbled beside it.

The interesting half is not the failed guess, it is the ACTIVE UN-DOING. `NFL`
-> `Nfl` and `US Open` -> `Us Open` are us overwriting capitalisation the reader
supplied. That is Alex's bug report 145 — "awkward to see 'Mma' with the 2nd and
3rd letter in lowercase" (#1938) — reappearing on the reader's own text.

THE FIX IS NOT A NEW RULE. `_derive_story_title` (`discover_bundles.py`) has had
the right one since long before this: acronym -> upper, digits -> unchanged,
otherwise up-case the FIRST letter and leave the rest alone. That last clause is
what makes it safe on free text — it never lower-cases, so `NFL`, `McIlroy` and
`US` all survive. It was factored out as `title_word` and called from both
arms, exactly as #6941 replaced search's fourth story-key resolver with the
shared one. A fifth casing rule in the search layer is the thing to avoid.

WHICH CLIENT SEES IT. Web uppercases the whole header
(`SearchFamilyCard.tsx:158`, `... uppercase tracking-wide`), so this is INVISIBLE
there; iOS sets `.textCase(nil)` (`SearchView.swift`) and prints the served
string verbatim, which is why native/135 photographed it from the phone. A web
LOOK is blind to this defect and is not its after-check — the same split #6941
recorded.

THE REMAINDER, NOW CLOSED. The first half above left the reader who types LOWER
case still garbled — `atp` -> `Atp`, `pga` -> `Pga`, `mma` -> `Mma` — because
the shared `_TITLE_ACRONYMS` set held no league codes. Its after-check said so
rather than closing the issue, and named the reason not to widen the set as a
rider: the set is also read by `_derive_story_title`, which titles Discover's
bundles, so the reach had to be measured first.

MEASURED, and the reach is nil (`artifacts-lane1b-411/`). All 27 literal story
keys `_story_key` can mint are named in `AUTHORED_STORY_TITLES` or
`NEUTRAL_STORY_TITLES`, so none of them is titled by the derived path at all;
none contains one of the added tokens; every served title is byte-identical
across the change. The golf key the after-check called out by name —
`bmw_pga_championship` — is the interesting one, and it is pinned below: its
DERIVED string genuinely moves, and a reader never sees that string, because
`story_family_label` cuts the tournament verbatim out of the venue's own name.
That pair (derived moves, served does not) is the reach measurement wired into
CI, and it is why widening the set is safe rather than merely untested.

STILL NOT IN SCOPE, said plainly so it is not read as an oversight: tokens that
are English WORDS in the same league vocabulary (`awards`, `boxing`, `rugby`)
and short ambiguous ones (`liv`, `lol`, `dota`, `europa`) are deliberately
excluded — shouting them at a reader who typed an ordinary word would be the
same defect pointing the other way.
"""

import pytest

from app.utils import feed_market_quality
from app.utils.discover_bundles import (
    _TITLE_ACRONYMS,
    _derive_story_title,
    _resolve_story_title,
    story_family_label,
    title_word,
)

from .test_search_family_header_vocabulary_6941 import _headers, _mkt


def _entity_header(query: str) -> str:
    """The label `/api/events/search?q=<query>` ships for the entity family.

    Two markets both NAMING the query, which is what `_compose_futures_families`
    requires of an entity family (>=2 members, >=1 name-match) and what the
    production specimens were.
    """
    expanded = [(t, None) for t in query.split()]
    markets = [
        _mkt(101, f"Who wins the {query} opener?"),
        _mkt(102, f"{query} — total points scored"),
    ]
    headers = _headers(markets, expanded)
    assert headers, f"no family formed for {query!r} — this guard asserts nothing"
    assert len(headers) == 1, headers
    return headers[0]


# ── The reproduction ─────────────────────────────────────────────────────────


class TestTheReaderOwnCapitalisationSurvives:
    """The half that is an un-doing rather than a bad guess."""

    @pytest.mark.parametrize("typed", ["NFL", "US Open", "McIlroy", "PSG", "AC Milan"])
    def test_a_query_the_reader_cased_is_served_back_unchanged(self, typed):
        assert _entity_header(typed) == typed

    def test_title_case_is_what_would_break_each_of_them(self):
        """The negative control for the case above.

        Without it, that test would still pass the day someone replaced the
        header with the raw query and deleted the casing entirely — and would
        also have passed on inputs `.title()` happens to leave alone. These are
        the inputs where the two rules genuinely disagree.
        """
        for typed in ("NFL", "US Open", "McIlroy", "PSG", "AC Milan"):
            assert typed.title() != typed, typed


class TestALowercaseAcronymGetsTheHouseCase:
    @pytest.mark.parametrize(
        "typed,expected",
        [("nfl", "NFL"), ("mlb", "MLB"), ("ufc", "UFC"), ("nba", "NBA")],
    )
    def test_the_entity_arm_speaks_the_same_vocabulary_as_the_story_arm(
        self, typed, expected
    ):
        assert _entity_header(typed) == expected

    def test_both_arms_of_one_response_agree_about_one_acronym(self):
        """`q=atp` served `['Grand Slam Tennis', 'Atp']` — the contrast that
        made this filable. Reproduced with an acronym the house set knows, so
        the two families in ONE payload must now spell it the same way."""
        markets = [
            _mkt(1, "UFC 331: Renato Moicano vs. Brian Ortega"),
            _mkt(2, "UFC 331: Will there be a first-round finish?"),
        ]
        story = _headers(markets, [("ufc", None)])

        assert story == ["UFC 331"]
        assert _entity_header("ufc") == "UFC"
        assert "Ufc" not in (story[0] + _entity_header("ufc"))


# ── The arms that must NOT move ──────────────────────────────────────────────


class TestTheOrdinaryQueryIsUnchanged:
    @pytest.mark.parametrize(
        "typed,expected",
        [
            ("red sox", "Red Sox"),
            ("alcaraz", "Alcaraz"),
            ("world series", "World Series"),
            ("super bowl", "Super Bowl"),
        ],
    )
    def test_a_lower_case_query_still_reads_as_a_title(self, typed, expected):
        assert _entity_header(typed) == expected


class TestTheStoryArmIsBitIdentical:
    """The refactor must be inert where it was lifted from.

    `_derive_story_title` is the ONLY other reader of this rule, and it feeds
    every unauthored Discover bundle title as well as search's fallback. So the
    old inline loop is restated here — the one place restating production logic
    is right, because the claim being made is literally "these two agree".
    """

    @staticmethod
    def _old_derive(story_key: str) -> str:
        slug = story_key.split(":", 1)[-1]
        words = [w for w in slug.replace("-", "_").split("_") if w]
        if not words:
            return "Related markets"
        out: list[str] = []
        for word in words:
            if word.lower() in _TITLE_ACRONYMS:
                out.append(word.upper())
            elif word.isdigit():
                out.append(word)
            else:
                out.append(word[:1].upper() + word[1:])
        return " ".join(out)

    @pytest.mark.parametrize(
        "story_key",
        [
            "story:macro_rates",
            "story:us_state_races",
            "story:us_government_stakes",
            "story:niche_low_signal_sports",
            "story:minor_soccer_leagues",
            "story:daily_equity_direction",
            "story:ufc_events",
            "story:ufc_event:331",
            "story:golf_tournament:bmw_pga_championship",
            "story:ai",
            "story:ipo_markets",
            "story:fifa_world_cup",
            "story:single_stock_earnings",
            "story:spacex_launches",
            "story:2028",
            "story:",
            "story:tv-ratings",
        ],
    )
    def test_the_derived_title_is_what_it_was(self, story_key):
        assert _derive_story_title(story_key) == self._old_derive(story_key)

    def test_the_empty_slug_still_has_its_own_answer(self):
        """Not folded into `title_word`: the no-words case returns a SENTENCE,
        and a header that reads "Related markets" is a different promise from a
        header that reads "". Pinned because the refactor moved the loop out
        from under it."""
        assert _derive_story_title("story:") == "Related markets"


# ── The rule itself ──────────────────────────────────────────────────────────


class TestTitleWordNeverLowercases:
    """The property the whole fix rests on, asserted directly rather than only
    through the two call sites: whatever `title_word` does, it may not turn an
    upper-case letter into a lower-case one. That is the difference between a
    casing rule that is safe on a slug WE minted and one that is safe on text a
    PERSON typed, and it is what `.title()` violated."""

    WORDS = [
        "NFL", "nfl", "McIlroy", "US", "us", "PSG", "psg", "O'Brien", "III",
        "iPhone", "331", "2028", "x", "X", "aC", "UFC", "ufc", "Ufc",
        "MacDonald", "van", "d'Or", "e", "", "ATP", "atp", "tv", "TV",
    ]

    @pytest.mark.parametrize("word", WORDS)
    def test_no_character_is_ever_case_folded_downwards(self, word):
        out = title_word(word)

        assert len(out) == len(word), (word, out)
        for before, after in zip(word, out):
            if before.isupper():
                assert after.isupper(), (word, out)

    @pytest.mark.parametrize("word", WORDS)
    def test_the_letters_themselves_are_untouched(self, word):
        """Only case may change — no substitution, no stripping, no reordering."""
        assert title_word(word).lower() == word.lower()

    def test_an_unknown_token_keeps_its_interior(self):
        assert title_word("mcilroy") == "Mcilroy"  # we do not guess
        assert title_word("McIlroy") == "McIlroy"  # but we never un-guess

    def test_a_known_acronym_wins_over_the_first_letter_rule(self):
        for acronym in sorted(_TITLE_ACRONYMS):
            assert title_word(acronym) == acronym.upper()
            assert title_word(acronym.upper()) == acronym.upper()
            assert title_word(acronym.capitalize()) == acronym.upper()

    def test_a_digit_token_is_left_alone(self):
        assert title_word("331") == "331"
        assert title_word("2028") == "2028"

    def test_the_empty_word_does_not_raise(self):
        assert title_word("") == ""


# ── The remainder: the reader who typed LOWER case ───────────────────────────
#
# Named as LITERALS rather than looped over `_TITLE_ACRONYMS`, which is the
# whole point: a test that iterates the set its fix defines cannot see that set
# shrink — deleting `pga` would leave it green with one less case to check.
# `test_a_known_acronym_wins_over_the_first_letter_rule` above is that loop, and
# it is why these are spelled out here.
_ADDED_LEAGUE_ACRONYMS = {
    "afl", "atp", "cfl", "csgo", "epl", "fiba", "icc", "ipl", "lpga", "mls",
    "mma", "nascar", "ncaa", "ncaab", "ncaaf", "nrl", "nwsl", "pdc", "pga",
    "psg", "ucl", "wncaab", "wta", "xfl",
}


class TestTheLowerCaseLeagueIsServedTheHouseSpelling:
    """The half the first fix left open, with production's own queries.

    `pga` (5 logged queries in the 30 days to 2026-09-20), `psg` (2), `atp` (1)
    and `fiba` (1) were all still being handed back garbled after the first
    half merged — a reader typing `pga` got `Pga` over their results.
    """

    @pytest.mark.parametrize(
        "typed,expected",
        [
            # Named as the remainder by this issue's own after-check.
            ("atp", "ATP"), ("wta", "WTA"), ("ncaa", "NCAA"),
            ("pga", "PGA"), ("mma", "MMA"), ("psg", "PSG"),
            # Logged on production and still garbled after the first half.
            ("fiba", "FIBA"),
            # The rest of the league vocabulary, same rule.
            ("epl", "EPL"), ("mls", "MLS"), ("nascar", "NASCAR"),
            ("ncaaf", "NCAAF"), ("lpga", "LPGA"), ("ucl", "UCL"),
        ],
    )
    def test_a_lower_case_league_is_not_handed_back_half_capitalised(
        self, typed, expected
    ):
        assert _entity_header(typed) == expected

    @pytest.mark.parametrize("typed", sorted(_ADDED_LEAGUE_ACRONYMS))
    def test_every_added_token_is_still_in_the_house_set(self, typed):
        """Each spelled out, so removing one from the app set reds here."""
        assert title_word(typed) == typed.upper()

    def test_the_readers_own_capitals_still_survive_the_wider_set(self):
        """The first half's property, re-asserted on the new tokens: a token is
        upper-cased because it is an acronym, never lower-cased back."""
        for typed in ("ATP", "PGA", "NCAA", "PSG"):
            assert _entity_header(typed) == typed

    def test_a_multi_word_query_cases_only_the_league_token(self):
        assert _entity_header("ncaa football") == "NCAA Football"
        assert _entity_header("pga championship") == "PGA Championship"


class TestTheWordsInThatVocabularyAreDeliberatelyExcluded:
    """The judgement call, pinned so a later blanket widening reds.

    `detect_league` also returns `AWARDS`, `BOXING` and `RUGBY` in upper case,
    and they are the one part of that vocabulary this set must NOT copy: they
    are ordinary English words, and shouting one back at the reader who typed it
    is the same defect as `Mma`, pointing the other way. Same for short tokens a
    reader could mean as a name — `liv` is LIV Golf and also Liverpool.
    """

    @pytest.mark.parametrize(
        "typed,expected",
        [
            ("awards", "Awards"), ("boxing", "Boxing"), ("rugby", "Rugby"),
            ("liv", "Liv"), ("lol", "Lol"), ("europa", "Europa"),
        ],
    )
    def test_an_ordinary_word_is_still_title_cased_not_shouted(
        self, typed, expected
    ):
        assert _entity_header(typed) == expected
        assert typed not in _TITLE_ACRONYMS


class TestWideningTheSetMovedNoDiscoverTitle:
    """The reach measurement the first half's after-check said was owed.

    This set is shared with `_derive_story_title`, which titles every unauthored
    Discover bundle, so the question "does adding league codes change what
    Discover says?" had to be answered before the edit rather than after. The
    answer is no, and both arms of the proof are here: no story key the feed can
    mint is titled differently, AND the one key whose derived string genuinely
    does move is a key whose derived string is never served.
    """

    @staticmethod
    def _derive_under_the_old_set(story_key: str) -> str:
        """`_derive_story_title` as it behaved before the league codes landed."""
        old = _TITLE_ACRONYMS - _ADDED_LEAGUE_ACRONYMS
        slug = story_key.split(":", 1)[-1]
        words = [w for w in slug.replace("-", "_").split("_") if w]
        if not words:
            return "Related markets"
        return " ".join(
            w.upper() if w.lower() in old else (w if w.isdigit() else w[:1].upper() + w[1:])
            for w in words
        )

    @staticmethod
    def _minted_story_keys() -> list[str]:
        """Every literal `story:...` key `_story_key` can return.

        Read off the source rather than restated, so a key added tomorrow is
        covered by this guard without anyone remembering to list it here.
        """
        import re
        from pathlib import Path

        src = Path(feed_market_quality.__file__).read_text()
        return sorted(set(re.findall(r'return "(story:[a-z0-9_]+)"', src)))

    def test_the_key_list_is_not_empty(self):
        """Without this the sweep below would pass by finding nothing."""
        keys = self._minted_story_keys()
        assert len(keys) >= 20, keys
        assert "story:macro_rates" in keys

    def test_no_story_key_the_feed_can_mint_is_titled_differently(self):
        for key in self._minted_story_keys():
            assert _derive_story_title(key) == self._derive_under_the_old_set(key), key

    def test_every_minted_key_is_named_so_none_is_derived_for_a_reader(self):
        """Why the sweep above finds nothing: the derived path is a fallback for
        a key nobody has labelled, and today every key is labelled. Recorded as
        an observation — a future unnamed key is not a defect (it would simply
        derive, which is what the fallback is for) — so this asserts the state
        the measurement was taken in, and names the count."""
        sources = {_resolve_story_title(k)[1] for k in self._minted_story_keys()}
        assert sources <= {"authored", "neutral"}, sources

    def test_the_golf_key_whose_derived_string_does_move_never_serves_it(self):
        """🔴 The non-vacuity control for this whole class, and the specific
        worry the after-check named. `bmw_pga_championship` DOES title
        differently now — so the widening is real and the sweep above is not
        passing because nothing changed anywhere. A reader never sees it: the
        golf arm cuts the tournament verbatim out of the venue's own string,
        precisely because un-slugifying the key cannot recover "BMW"."""
        key = "story:golf_tournament:bmw_pga_championship"
        names = ["BMW PGA Championship Winner"]

        assert _derive_story_title(key) != self._derive_under_the_old_set(key)
        assert "Pga" in self._derive_under_the_old_set(key)
        assert "PGA" in _derive_story_title(key)

        assert story_family_label(key, names) == "BMW PGA Championship"
