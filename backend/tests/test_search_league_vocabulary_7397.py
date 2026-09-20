"""SEARCH STOPS CALLING THE NFL "PRO FOOTBALL". #7397.

═══ WHAT WAS MEASURED ═══

`bainluck.com/search?q=chiefs`, production, 2026-09-20 06:5xZ, LOOK at 390px.
One page, one league, two names:

    filter chip                     NFL (18)
    all eighteen game cards         NFL
    FUTURES & MARKETS  FOOTBALL     Pro Football: 2027 Champion
    FUTURES & MARKETS  FOOTBALL     Pro Football: Chiefs vs. Raiders Season Series Winner
    ANSWERS            CHIEFS       Pro Football: Broncos vs. Chiefs Season Series Winner
    ANSWERS            CHIEFS       Pro Football: Chiefs vs. Chargers Season Series Winner

The dropdown one tap above it printed the same thing:
`GET /api/events/typeahead?q=chiefs` → `"text": "Pro Football: 2027 Champion"`.

"Pro Football" is the venue's word. Population over `status='open'`:

    Pro Football      402 polymarket + 74 kalshi
    Pro Basketball     32 kalshi
    Pro Baseball       26 kalshi
    Pro Football Playoffs  12 kalshi
                      ─────
                      ~550 open markets, BOTH venues

═══ THE MECHANISM: WE ALREADY OWN THE TRANSLATION, ON ONE SURFACE ═══

`_PRO_SPORT_REWRITES` has mapped `Pro Football` → `NFL` for as long as the module
has existed. Its only consumer is `normalize_market_label`, whose only call site
in the entire app is `_build_related_futures` — the event page's Related Futures
rail. The module docstring says it outright: "Market label normalization for
Related Futures." Every other surface serializes `FuturesMarket.name` raw.

Not #6630. That repaired the family KEY in `prop_families.py` so two Sixth Man
cards would collapse into one. This is the displayed TITLE — #6630 is live and
the title still read `Pro Football`.

═══ WHY SEARCH DOES NOT CALL `normalize_market_label` ═══

Because that function is built for a page that already says which league it is,
so it goes on to delete the league. On the production specimen:

    normalize_market_label('Pro Football: 2027 Champion')  ->  'Champion'

Correct on a Chiefs event page; useless in a list of search results. Search takes
the vocabulary step ONLY. `TestSearchIsNotTheRail` is that distinction.

═══ THE TRAP: `All-Pro` → `All-NBA` IS NOT SAFE OFF A BASKETBALL PAGE ═══

The fifth rewrite renames All-Pro to All-NBA. "All-Pro" is an NFL term, and
production carries four open FOOTBALL markets it would rename into the wrong
sport:

    60473175  kalshi  football  open  Pro Football: All-Pro Second-Team Offense
    60473176  kalshi  football  open  Pro Football: All-Pro Second-Team Defense
    60473177  kalshi  football  open  Pro Football: All-Pro First-Team Offense
    60473178  kalshi  football  open  Pro Football: All-Pro First-Team Defense

`normalize_market_label` returns `'All-NBA Second-Team Offense'` for the first of
those TODAY. That survives on the rail because the rail is scoped to one event's
sport; it cannot survive on a search page, which is every sport at once. So the
rule stays out of `_VENUE_LEAGUE_REWRITES`, and `TestTheAllProTrap` is the
assertion that fails if anyone folds the two lists back together.

Order inside the list is load-bearing and unchanged: `\\bPro Basketball\\b` fires
first, so the genuinely-NBA `All-Pro Basketball Third Team Selections` still
becomes `All-NBA Third Team Selections` without the All-Pro rule existing.

═══ WHAT MUST NOT CHANGE ═══

The rail. Proven over the REAL population rather than by inspection: all 3,530
production `futures_markets` rows whose name contains "pro " or "all-pro", run
through `normalize_market_label` before and after this diff — **0 rows change**.
`TestTheRailIsUntouched` freezes that on the specimens that would have moved
first if it were not true.

Display only. The stored `name` is untouched, so family keys, matching and
calibration all keep reading what they read before.

═══ WHAT THIS FILE CAN AND CANNOT SEE ═══

`/search`'s arm runs through the REAL serializer, `_format_futures_for_search`,
so its assertions are on the served payload. The typeahead's arm is an inline
dict literal in an async route body with no seam, so it is guarded by source
inspection — the house pattern for this exact block
(`test_typeahead_futures_pool_ordering_4723`, and #7369 before this). That guard
proves the CALL; the output is proven once on the helper, and both call sites are
asserted to pass the same single argument so the two surfaces cannot drift.
"""

import inspect
import re

import pytest

from app.routes import events
from app.routes.events import _format_futures_for_search
from app.utils.market_label_normalization import (
    _PRO_SPORT_REWRITES,
    _QUALIFIED_VENUE_LEAGUE_REWRITES,
    _VENUE_LEAGUE_REWRITES,
    _VOWEL_SOUND_INITIALISMS,
    _apply_venue_league_rewrites,
    normalize_market_label,
    rewrite_venue_league_vocabulary,
)


class _Market:
    """The attributes `_format_futures_for_search` reads off an ORM row."""

    def __init__(self, name, **kw):
        self.name = name
        self.market_tier = kw.get("tier", 1)
        self.llm_sport_category = kw.get("llm_sport_category", "football")
        self.category = kw.get("category", "championship")
        self.outcomes = []
        self.id = kw.get("id", 1)
        self.sport = None
        self.market_type = None
        self.status = "open"
        self.source = "kalshi"
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = True


def _served_name(name, **kw) -> str:
    """The title `/search` actually serves for this row."""
    return _format_futures_for_search(_Market(name, **kw))["name"]


# Real production names, copied from the rows behind the census above.
_PRODUCTION_SPECIMENS = [
    ("Pro Football: 2027 Champion", "NFL: 2027 Champion"),
    (
        "Pro Football: Chiefs vs. Raiders Season Series Winner",
        "NFL: Chiefs vs. Raiders Season Series Winner",
    ),
    (
        "Pro Football: Broncos vs. Chiefs Season Series Winner",
        "NFL: Broncos vs. Chiefs Season Series Winner",
    ),
    (
        "Pro Football: Chiefs vs. Chargers Season Series Winner",
        "NFL: Chiefs vs. Chargers Season Series Winner",
    ),
    ("Pro Basketball Sixth Man Of The Year", "NBA Sixth Man Of The Year"),
    ("Pro Baseball Cy Young", "MLB Cy Young"),
    ("Pro Hockey Rookie Of The Year", "NHL Rookie Of The Year"),
    ("2026 Pro Basketball Cup Champion", "2026 NBA Cup Champion"),
]


class TestTheMeasuredSpecimens:
    """The rows Alex would have seen on `/search?q=chiefs`."""

    @pytest.mark.parametrize("raw,expected", _PRODUCTION_SPECIMENS)
    def test_the_served_title_names_the_league_we_name(self, raw, expected):
        assert _served_name(raw) == expected

    @pytest.mark.parametrize("raw,_expected", _PRODUCTION_SPECIMENS)
    def test_no_served_title_still_says_pro_anything(self, raw, _expected):
        """Asserted as the negative the reader complained about."""
        served = _served_name(raw)
        assert not re.search(
            r"\bPro (Football|Basketball|Hockey|Baseball)\b", served, re.I
        ), served

    def test_the_chip_and_the_card_now_agree(self):
        """The whole defect in one line: chip said NFL, card said Pro Football."""
        assert _served_name("Pro Football: 2027 Champion").startswith("NFL")


class TestTheAllProTrap:
    """The four open FOOTBALL markets the fifth rewrite would misfile."""

    _FOOTBALL_ALL_PRO = [
        "Pro Football: All-Pro Second-Team Offense",
        "Pro Football: All-Pro Second-Team Defense",
        "Pro Football: All-Pro First-Team Offense",
        "Pro Football: All-Pro First-Team Defense",
    ]

    @pytest.mark.parametrize("raw", _FOOTBALL_ALL_PRO)
    def test_a_football_all_pro_market_is_never_renamed_all_nba(self, raw):
        served = _served_name(raw, llm_sport_category="football")
        assert "All-NBA" not in served, served
        assert served == raw.replace("Pro Football", "NFL")

    def test_a_real_nba_all_pro_market_still_reads_all_nba(self):
        """The control on the other side: the basketball arm must still fire.

        `\\bPro Basketball\\b` matches inside "All-Pro Basketball", so this is
        correct WITHOUT the All-Pro rule — which is why dropping that rule from
        the search helper costs nothing on the sport it was written for.
        """
        assert (
            _served_name(
                "All-Pro Basketball Third Team Selections",
                llm_sport_category="basketball",
            )
            == "All-NBA Third Team Selections"
        )

    def test_the_all_pro_rule_is_not_in_the_unscoped_list(self):
        """Structural. This is the assertion that fails on a "tidy-up" merge.

        If someone collapses the two lists back into one, every football All-Pro
        market starts printing All-NBA in search and the output assertions above
        are the only thing between that and production.
        """
        unscoped = [p.pattern for p, _ in _VENUE_LEAGUE_REWRITES]
        assert not any("All-Pro" in p for p in unscoped), unscoped
        assert any(
            "All-Pro" in p.pattern for p, _ in _PRO_SPORT_REWRITES
        ), "the rail must keep its own rule"

    def test_the_rail_list_is_the_unscoped_list_plus_exactly_one_rule(self):
        """The two lists stay in sync by construction, not by copy-paste.

        A league added to the venue vocabulary must reach BOTH surfaces; this
        fails if someone appends to one list and forgets the other.
        """
        assert _PRO_SPORT_REWRITES[: len(_VENUE_LEAGUE_REWRITES)] == list(
            _VENUE_LEAGUE_REWRITES
        )
        assert len(_PRO_SPORT_REWRITES) == len(_VENUE_LEAGUE_REWRITES) + 1


class TestSearchIsNotTheRail:
    """Search takes the vocabulary step and NOT the league-strip step."""

    def test_the_rail_strips_the_league_and_search_keeps_it(self):
        raw = "Pro Football: 2027 Champion"
        assert normalize_market_label(raw) == "Champion"
        assert rewrite_venue_league_vocabulary(raw) == "NFL: 2027 Champion"

    def test_search_keeps_the_league_wherever_the_rail_strips_it(self):
        """ "Champion" alone is meaningless in a list of every sport at once.

        Scoped to the titles that carry a `League: …` prefix, because those are
        the only ones the rail's strip step can reach. On a title without one
        (`Pro Baseball Cy Young`) the two paths agree, and that agreement is
        correct rather than a miss — so the count below keeps this from passing
        vacuously if the specimen list ever loses its prefixed rows.
        """
        prefixed = [
            raw
            for raw, _ in _PRODUCTION_SPECIMENS
            if re.match(r"^Pro (Football|Basketball|Hockey|Baseball):", raw)
        ]
        assert len(prefixed) >= 4, prefixed
        for raw in prefixed:
            assert rewrite_venue_league_vocabulary(raw) != normalize_market_label(raw)
            assert normalize_market_label(raw) not in rewrite_venue_league_vocabulary(
                raw
            ) or rewrite_venue_league_vocabulary(raw).startswith(
                ("NFL", "NBA", "NHL", "MLB")
            )


class TestTheRailIsUntouched:
    """The rail's NON-WNBA output is frozen. 3,474 of 3,532 names are identical.

    ⚠️ AMENDED. The original claim here was "0 of 3,530 production names change
    on the rail", and it was true of the diff that made it. It is no longer: the
    WNBA repair below moves 58 rail rows on purpose, because the rail splats the
    same list and had the same defect. Re-measured over the whole population —
    3,532 names containing `pro `/`all-pro`, master's function vs this branch's —
    **58 changed, every one a `Women's NBA …` → `WNBA …` repair, 3,474
    identical**. The number is split rather than deleted so the freeze keeps
    meaning something: these four specimens are the ones that would move FIRST if
    the split ever leaked back into `normalize_market_label`, and
    `TestTheWNBAIsNotTheNBA` owns the 58 that are supposed to move.
    """

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Pro Football: 2027 Champion", "Champion"),
            (
                "Pro Football: All-Pro Second-Team Offense",
                "All-NBA Second-Team Offense",
            ),
            ("All-Pro Basketball Third Team Selections", "All-NBA Third Team"),
            ("Pro Baseball Cy Young", "MLB Cy Young"),
        ],
    )
    def test_the_related_futures_rail_is_byte_identical(self, raw, expected):
        assert normalize_market_label(raw) == expected


class TestWhatItMustNotTouch:
    def test_an_italian_club_is_not_a_league(self):
        """`Pro Patria` — 8 rows in #6630's venue census. Whole-phrase, not `Pro `."""
        for raw in ("Pro Patria vs Novara", "Pro Vercelli vs Pro Patria"):
            assert rewrite_venue_league_vocabulary(raw) == raw

    def test_a_title_that_already_says_nfl_is_unchanged(self):
        for raw in ("NFL: 2027 Champion", "NBA: 2026 NBA Cup Winner"):
            assert rewrite_venue_league_vocabulary(raw) == raw

    def test_the_rewrite_is_idempotent(self):
        """A double application must not compound — the surfaces call it once
        each, but families and the flat list share one dict, so a second pass
        must be a no-op rather than a corruption."""
        for raw, _ in _PRODUCTION_SPECIMENS:
            once = rewrite_venue_league_vocabulary(raw)
            assert rewrite_venue_league_vocabulary(once) == once

    def test_whitespace_is_preserved_exactly(self):
        """Display-only must not silently become a trim — a caller diffing the
        served title against the stored name would see a change it did not make.
        """
        assert (
            rewrite_venue_league_vocabulary("  Pro Football: 2027 Champion  ")
            == "  NFL: 2027 Champion  "
        )

    def test_every_other_key_of_the_card_is_unchanged(self):
        """The diff moves `name` and nothing else on the served payload."""
        raw = "Pro Football: 2027 Champion"
        card = _format_futures_for_search(_Market(raw))
        control = _format_futures_for_search(_Market("NFL: 2027 Champion"))
        assert card == control


#: Real WNBA rows, copied verbatim from `futures_markets` (ids in the comments).
#: Every one of these was rendered `Women's NBA …` by the sha I offered.
_WNBA_SPECIMENS = [
    # 12538514 — the one on the WNBA page's awards section.
    ("Women's Pro Basketball MVP Winner", "WNBA MVP Winner"),
    # 16756506
    ("Women's Pro Basketball Finals MVP Winner", "WNBA Finals MVP Winner"),
    # 12046267
    ("Women's Pro Basketball Champion", "WNBA Champion"),
    # 13787860 — an apostrophe in the REMAINDER as well as the qualifier.
    (
        "Women's Pro Basketball Commissioner's Cup MVP Winner",
        "WNBA Commissioner's Cup MVP Winner",
    ),
    # 16757153 — the phrase carries a colon suffix, like the NFL specimens.
    (
        "Women's Pro Basketball: Any Player to Dunk this Season",
        "WNBA: Any Player to Dunk this Season",
    ),
    # 109231 — mid-sentence, not a prefix. The rule is not anchored.
    (
        "Will at least 1 game be played in the Women's Pro Basketball season?",
        "Will at least 1 game be played in the WNBA season?",
    ),
    # 60473144 — mid-sentence at the END of the string.
    (
        "Who will be the next commissioner of Women's Pro Basketball?",
        "Who will be the next commissioner of WNBA?",
    ),
    # 110413 — a `#` immediately after the phrase.
    ("Women's Pro Basketball #1 Overall Pick", "WNBA #1 Overall Pick"),
]


class TestTheWNBAIsNotTheNBA:
    """The regression that nearly shipped. #7397's second defect.

    `\\bPro Basketball\\b` matches inside `Women's Pro Basketball` — Kalshi's
    name for the WNBA, 58 markets, 23 of them on `/sport/basketball/wnba`. The
    first version of this fix turned "Women's Pro Basketball: Las Vegas Aces
    Total Wins" into "Women's NBA: …" and told a reader the Aces play in the
    NBA. Renaming a league wrongly is worse than printing the venue's jargon,
    which is the entire premise of this issue.

    It was invisible to the census that cleared the first sha because that census
    counted CHANGED ROWS: all 58 sat inside the 1,261 "repairs". A count cannot
    tell a repair from a new lie. What found it was asking, per league page,
    whether the league token that came out is the league that page is about.
    """

    @pytest.mark.parametrize("raw,expected", _WNBA_SPECIMENS)
    def test_the_served_title_says_wnba(self, raw, expected):
        assert _served_name(raw, llm_sport_category="basketball") == expected

    @pytest.mark.parametrize("raw,_expected", _WNBA_SPECIMENS)
    def test_no_wnba_row_is_ever_served_as_the_nba(self, raw, _expected):
        """The negative, stated as the reader's complaint would be.

        `WNBA` contains `NBA` as a substring, so this cannot be a substring test
        — `\\bNBA\\b` is the whole point. `WNBA MVP Winner` must pass and
        `Women's NBA MVP Winner` must fail, and only a word-boundary test
        separates them.
        """
        served = _served_name(raw, llm_sport_category="basketball")
        assert not re.search(r"\bNBA\b", served), served
        assert "WNBA" in served, served

    @pytest.mark.parametrize("raw,_expected", _WNBA_SPECIMENS)
    def test_the_rail_repairs_them_too(self, raw, _expected):
        """58 rail rows move, deliberately — the rail splats the same list.

        Paired with `TestTheRailIsUntouched`, which freezes the other 3,474.
        """
        out = normalize_market_label(raw)
        assert not re.search(r"\bNBA\b", out), out

    def test_the_aces_row_that_search_serves_today(self):
        """`GET /api/events/search?q=aces` returns this row on production."""
        raw = "Women's Pro Basketball: Las Vegas Aces Total Wins"
        assert (
            _served_name(raw, llm_sport_category="basketball")
            == "WNBA: Las Vegas Aces Total Wins"
        )

    def test_a_real_nba_row_is_still_the_nba(self):
        """The control. The repair must not make every basketball row a WNBA
        row — a rule that answered `WNBA` to everything would satisfy every
        assertion above."""
        assert _served_name("Pro Basketball Finals MVP Winner") == (
            "NBA Finals MVP Winner"
        )
        assert _served_name("2026 Pro Basketball Cup Champion") == (
            "2026 NBA Cup Champion"
        )

    def test_the_possessive_is_not_required(self):
        """Venue spelling is not ours to rely on; `Womens` occurs in the wild."""
        assert rewrite_venue_league_vocabulary("Womens Pro Basketball MVP") == (
            "WNBA MVP"
        )

    def test_a_typographic_apostrophe_is_handled(self):
        """Production stores U+0027 today (measured, all 58 rows). This is the
        arm that means a venue switching to U+2019 is a no-op, not a relapse."""
        assert rewrite_venue_league_vocabulary("Women’s Pro Basketball MVP") == (
            "WNBA MVP"
        )

    def test_the_repair_is_idempotent(self):
        for raw, expected in _WNBA_SPECIMENS:
            assert rewrite_venue_league_vocabulary(expected) == expected


class TestTheQualifierGuardFailsSafe:
    """What happens to the qualifier nobody has mapped yet.

    A rule can only rescue a phrase somebody has already seen. This is about the
    NEXT one: if a league-changing qualifier sits in front of the phrase and no
    qualified rule claimed it, the venue's words are left alone. Printing
    "Girls Pro Basketball" is the bug we are fixing; printing "Girls NBA" is a
    lie, and between the two the jargon is the safe failure.
    """

    @pytest.mark.parametrize(
        "raw",
        [
            "Girls Pro Basketball Champion",
            "College Pro Football Champion",
            "NCAA Pro Basketball Thing",
            "Youth Pro Hockey Thing",
            "Semi-Pro Football Thing",
        ],
    )
    def test_an_unmapped_qualifier_leaves_the_venue_words_alone(self, raw):
        assert rewrite_venue_league_vocabulary(raw) == raw

    @pytest.mark.parametrize(
        "raw,expected",
        [
            # 181 production rows are prefixed `2026`, 10 by `2027`.
            ("2026 Pro Football Champion", "2026 NFL Champion"),
            ("2027 Pro Football Champion", "2027 NFL Champion"),
            # Cities are the other common prefix — 3 Milwaukee, 3 Chicago, …
            ("Milwaukee Pro Basketball Total Wins", "Milwaukee NBA Total Wins"),
            ("New York Pro Basketball Total Wins", "New York NBA Total Wins"),
            # Articles and prepositions.
            ("Will the 2026 Pro Football champs visit?", "Will the 2026 NFL champs visit?"),
            ("Winner of Pro Baseball Cy Young", "Winner of MLB Cy Young"),
            # Sentence-initial "A" is a real article, so it moves to "An" with
            # the initialism behind it. The team-abbreviation case that must NOT
            # move is its own test in `TestTheIndefiniteArticleMovesWithTheLeague`.
            ("A Pro Football game this season", "An NFL game this season"),
        ],
    )
    def test_an_ordinary_prefix_still_gets_rewritten(self, raw, expected):
        """THE OVER-FIRE CONTROL, and the reason the guard is a NAMED list
        rather than "any preceding word".

        Of the 363 production names where the phrase is not at the start, 191
        are preceded by a year and most of the rest by a city. A guard that
        declined on any prefix would refuse all of them — it would pass every
        assertion in the class above while silently un-fixing the majority of
        the ship.
        """
        assert rewrite_venue_league_vocabulary(raw) == expected

    def test_the_guard_reads_the_text_immediately_before_the_match(self):
        """Not "does the word appear anywhere". A name that merely MENTIONS
        women elsewhere must still be rewritten."""
        raw = "Most women in a Pro Football front office"
        assert rewrite_venue_league_vocabulary(raw) == (
            # "an", not "a" — incidental to what this test is for, but it is the
            # reader's sentence either way.
            "Most women in an NFL front office"
        )


class TestTheIndefiniteArticleMovesWithTheLeague:
    """"a Pro Football game" is English; "a NFL game" is not.

    Found by walking the NFL league page's own served payload AFTER this ship
    was already offered and gated GREEN — no test caught it, because two tests
    in this file had pinned "a NFL game" as the expected string.

    The population is five open markets, counted on production rather than
    guessed, and four of the five are novelty markets:

        30779639  Aaron Donald to play in a Pro Football game this season
        56914123  Jake Paul to Play in a Pro Football Game This Season
        59164756  Ben Simmons to play in a Pro Basketball game this season
        59693519  Will Salt Lake City receive a Pro Baseball expansion team...
        27561356  Will Trump attend a Pro Basketball finals game?   (resolved)
    """

    @pytest.mark.parametrize(
        "raw,expected",
        [
            (
                "Aaron Donald to play in a Pro Football game this season",
                "Aaron Donald to play in an NFL game this season",
            ),
            (
                "Jake Paul to Play in a Pro Football Game This Season",
                "Jake Paul to Play in an NFL Game This Season",
            ),
            (
                "Ben Simmons to play in a Pro Basketball game this season",
                "Ben Simmons to play in an NBA game this season",
            ),
            (
                "Will Salt Lake City receive a Pro Baseball expansion team"
                " before Aug 1, 2027?",
                "Will Salt Lake City receive an MLB expansion team"
                " before Aug 1, 2027?",
            ),
            (
                "Will Trump attend a Pro Basketball finals game?",
                "Will Trump attend an NBA finals game?",
            ),
        ],
    )
    def test_the_five_production_specimens(self, raw, expected):
        assert rewrite_venue_league_vocabulary(raw) == expected

    def test_a_mid_name_capital_a_is_a_team_abbreviation_and_does_not_move(self):
        """THE TRAP, and it is a live row rather than a hypothetical.

        Market 252 is `Los Angeles A pro baseball wins this season?` — the LA
        Angels, written the way Kalshi writes `New York J` and `New York G`,
        both of which the NFL page serves today. A rule that reads any "A" as an
        article prints "Los Angeles An MLB wins this season?", which is worse
        than the jargon this ship exists to remove.

        The phrase is still rewritten; only the article is left alone.
        """
        assert rewrite_venue_league_vocabulary(
            "Los Angeles A pro baseball wins this season?"
        ) == "Los Angeles A MLB wins this season?"

    def test_a_sentence_initial_capital_a_is_a_real_article_and_does_move(self):
        """The other side of the same rule — without this, the guard above
        would pass just as well by never correcting a capital "A" at all.
        """
        assert rewrite_venue_league_vocabulary(
            "A Pro Football game will be played in Dublin"
        ) == "An NFL game will be played in Dublin"

    def test_the_wnba_keeps_its_article_because_it_is_read_double_you(self):
        """Spelling does not decide this, pronunciation does. `WNBA` opens on a
        consonant sound, so the naive `repl[0] not in "AEIOU"` test — which
        would pass every other assertion in this class — is wrong here.
        """
        assert rewrite_venue_league_vocabulary(
            "a Women's Pro Basketball game this season"
        ) == "a WNBA game this season"
        assert "WNBA" not in _VOWEL_SOUND_INITIALISMS

    def test_every_bare_replacement_is_classified(self):
        """A league added to the bare list without an entry here silently keeps
        the wrong article. This fails the moment someone adds one.
        """
        for _pat, repl in _VENUE_LEAGUE_REWRITES:
            assert repl in _VOWEL_SOUND_INITIALISMS, (
                f"{repl!r} is rewritten but not classified for its article"
            )

    def test_a_name_with_no_article_is_untouched_by_the_rule(self):
        """The article group is optional, so the rule must not have narrowed
        what the bare pattern matches."""
        assert (
            rewrite_venue_league_vocabulary("Pro Football: 2027 Champion")
            == "NFL: 2027 Champion"
        )

    def test_an_a_inside_a_word_is_not_an_article(self):
        """`\\ba` must not fire on the trailing "a" of the preceding word."""
        assert (
            rewrite_venue_league_vocabulary("Formula Pro Basketball trophy")
            == "Formula NBA trophy"
        )

    def test_the_qualifier_guard_still_declines_the_whole_match(self):
        """When the guard declines, it has to hand back the article too —
        otherwise the article is dropped and the phrase reappears bare.
        """
        assert (
            rewrite_venue_league_vocabulary("a Semi-Pro Football league")
            == "a Semi-Pro Football league"
        )
        assert (
            rewrite_venue_league_vocabulary("a College Pro Basketball showcase")
            == "a College Pro Basketball showcase"
        )


class TestQualifiedRulesRunFirst:
    """Order is load-bearing, so it is asserted rather than assumed.

    If the bare rules ran first they would consume `Pro Basketball` out of
    `Women's Pro Basketball` and the qualified rule would have nothing left to
    match — the defect, restored, with every qualified rule still present in the
    file and looking correct.
    """

    def test_the_qualified_list_is_not_empty(self):
        """A mutant that empties it would make the ordering test vacuous."""
        assert _QUALIFIED_VENUE_LEAGUE_REWRITES

    def test_every_qualified_pattern_is_shadowed_by_a_bare_one(self):
        """Proves the ordering MATTERS for each rule, so the test below is not
        passing by accident on a rule no bare pattern could have eaten."""
        for pat, _repl in _QUALIFIED_VENUE_LEAGUE_REWRITES:
            sample = "Women's Pro Basketball"
            assert pat.search(sample)
            assert any(bare.search(sample) for bare, _ in _VENUE_LEAGUE_REWRITES)

    def test_the_applier_consults_the_qualified_list_before_the_bare_list(self):
        src = inspect.getsource(_apply_venue_league_rewrites)
        # The two LOOPS, not the first mention of each name — `bare_rules` is
        # also the signature's parameter, which is line one and would make this
        # read backwards no matter what the body does.
        q = src.index("for pat, repl in _QUALIFIED_VENUE_LEAGUE_REWRITES")
        b = src.index("for pat, repl in bare_rules")
        assert q < b, "bare rules must not run before the qualified ones"

    def test_both_public_entry_points_share_the_applier(self):
        """The rail and search cannot drift apart into two rule sets again."""
        for fn in (rewrite_venue_league_vocabulary, normalize_market_label):
            assert "_apply_venue_league_rewrites" in inspect.getsource(fn)


class TestBothSurfacesCallIt:
    """The typeahead arm has no seam, so its CALL is proven from the source."""

    def test_the_typeahead_futures_row_rewrites_its_text(self):
        src = inspect.getsource(events.typeahead_search)
        assert (
            '"text": rewrite_venue_league_vocabulary(market.name),' in src
        ), "the dropdown serializes the raw venue name again"

    def test_the_typeahead_no_longer_serializes_the_raw_name(self):
        src = inspect.getsource(events.typeahead_search)
        assert '"text": market.name,' not in src

    def test_both_call_sites_pass_the_same_single_argument(self):
        """So the dropdown and the card below it can never drift apart."""
        ta = inspect.getsource(events.typeahead_search)
        card = inspect.getsource(_format_futures_for_search)
        call = "rewrite_venue_league_vocabulary(market.name)"
        assert call in ta and call in card

    def test_the_search_card_arm_is_the_real_serializer_not_a_copy(self):
        """Guards against the output assertions above going vacuous if the
        formatter stops being the thing `/search` serializes."""
        assert "_format_futures_for_search" in inspect.getsource(events.search_events)
