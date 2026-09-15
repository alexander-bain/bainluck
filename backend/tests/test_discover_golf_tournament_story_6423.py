"""#6423 — one golf tournament is one story, not seven cards.

Discover dealt Biltmore Championship Asheville as SEVEN cards (three of them
inside five slots) because every one of its 24 open markets carried
``story_key = None``: the only golf arm in the ``_story_key`` cascade named
``truist championship``, a tournament with 243 markets and ZERO open.

The corpus in this file is the real one — all 81 open ``llm_sport_category =
'golf'`` markets as production served them on 2026-09-15, names verbatim
including the three different separators, the two tour prefixes, the
apostrophe, and the seven Producers Guild rows misclassified as golf. It is the
control for both halves of the ship: what MUST fold, and what must not.
"""

from __future__ import annotations

import pytest

from app.utils.discover_bundles import (
    _golf_tournament_bundle_copy,
    assemble_story_theme_bundles,
)
from app.utils.feed_market_quality import (
    GOLF_TOURNAMENT_STORY_PREFIX,
    _story_key,
    diversify_quality_families,
    golf_tournament_display_name,
)

BILTMORE = [
    "Biltmore Championship Asheville End of Round 1 Leader",
    "Biltmore Championship Asheville End of Round 2 Leader",
    "Biltmore Championship Asheville End of Round 3 Leader",
    "Biltmore Championship Asheville: Hole-in-One",
    "Biltmore Championship Asheville - Make the Cut",
    "Biltmore Championship Asheville: Playoff",
    "Biltmore Championship Asheville: To Make the Cut",
    "Biltmore Championship Asheville - Top 10 Finish",
    "Biltmore Championship Asheville: Top 10 Finishers",
    "Biltmore Championship Asheville - Top 20 Finish",
    "Biltmore Championship Asheville: Top 20 Finishers",
    "Biltmore Championship Asheville - Top 5 Finish",
    "Biltmore Championship Asheville: Top 5 Finishers",
    "Biltmore Championship Asheville - Winner",
    "Biltmore Championship Asheville Winner",
    "PGA Tour: Biltmore Championship Asheville Albatross?",
    "PGA Tour: Biltmore Championship Asheville First Round Leader",
    "PGA Tour: Biltmore Championship Asheville Hole in One?",
    "PGA Tour: Biltmore Championship Asheville Second Round Leader",
    "PGA Tour: Biltmore Championship Asheville Third Round Leader",
    "PGA Tour: Biltmore Championship Asheville Top 10",
    "PGA Tour: Biltmore Championship Asheville Top 20",
    "PGA Tour: Biltmore Championship Asheville Top 5",
    "PGA Tour: Biltmore Championship Asheville Winner",
]

BMW_PGA = [
    "BMW PGA Championship - Make the Cut",
    "BMW PGA Championship - Top 10 Finish",
    "BMW PGA Championship - Top 20 Finish",
    "BMW PGA Championship - Top 5 Finish",
    "BMW PGA Championship - Winner",
    "BMW PGA Championship Winner",
    "DP World Tour: BMW PGA Championship Albatross?",
    "DP World Tour: BMW PGA Championship First Round Leader",
    "DP World Tour: BMW PGA Championship Hole in One?",
    "DP World Tour: BMW PGA Championship Second Round Leader",
    "DP World Tour: BMW PGA Championship Third Round Leader",
    "DP World Tour: BMW PGA Championship Top 10",
    "DP World Tour: BMW PGA Championship Top 20",
    "DP World Tour: BMW PGA Championship Top 5",
    "DP World Tour: BMW PGA Championship Winner",
]

NATIONWIDE = [
    "Nationwide Children's Hospital Championship - Make the Cut",
    "Nationwide Children's Hospital Championship - Top 10 Finish",
    "Nationwide Children's Hospital Championship - Top 20 Finish",
    "Nationwide Children's Hospital Championship - Top 5 Finish",
    "Nationwide Children's Hospital Championship - Winner",
]

# 🔴 THE TRAP. Seven of the 81 "golf" markets are Producers Guild of America
# awards (the #4515 misclassification class) and the rest are novelties,
# captaincies and 3-Ball matchups. Any key reaching for "PGA", or deriving a
# tournament by stripping whatever trailing phrase it is handed, folds four
# ENTERTAINMENT cards out of the feed for the wrong reason AND hides the
# misclassification. None of these may ever be keyed.
NEVER_KEYED = [
    "PGA Award for Best Animated Theatrical Motion Picture?",
    "PGA Award for Best Documentary Motion Picture?",
    "PGA Award for Best Limited or Anthology Series Television?",
    "PGA Award for Best Televised or Streamed Motion Picture?",
    "PGA Award for Best Television - Comedy?",
    "PGA Award for Best Television - Drama?",
    "PGA Award for Best Theatrical Motion Picture?",
    "Will Anthropic sign the Open Weights and American AI Leadership letter?",
    "1st Round 3-Ball: Penge/Hojgaard/Hall",
    "3rd Round 3-Ball: Kobori/Ferguson/Nørgaard Møller",
    "3rd Round 3-Ball: Waring/Kimsey/Paratore",
    "Europe Team Captain at 2027 Ryder Cup",
    "U.S. Team Captain at 2027 Ryder Cup",
    "Golfers to Compete in a LIV Golf Tournament in Q1 2027",
    "Golfers to compete in the Presidents Cup this year",
    "Golfers to rejoin the PGA Tour before Jan 21, 2027",
    "Golfers to win a PGA Tour Major before 2030 ",
    "Golfers to win a PGA Tour Major in 2027 ",
    "Jackson Koivun: Golf Majors before 2036",
    "Miles Russell: Golf Majors before 2036",
    "Steph Curry to compete in a PGA Tour event before 2028",
    "Tiger Woods to compete in any PGA event in 2026",
    "Will LIV Golf announce shutdown in 2026? ",
    "Will there be a LIV Golf Tournament in Q1 2027?",
    "Will Tiger Woods play in the 2026 Masters Tournament?",
    "Will Trump pardon Tiger Woods by June 30?",
    "2027 The Masters Champion",
]

# Under the cap already, or singletons: keyed, but this ship must not move them.
SMALL_FAMILIES = [
    "2027 Ryder Cup Winner",
    "Amgen Irish Open: To Make the Cut",
    "Amgen Irish Open: Top 10 Finishers",
    "Masters Tournament Winner",
    "PGA Championship Winner",
    "Presidents Cup Winner",
    "The Open Winner",
    "US Open Winner",
]

FLOODS = BILTMORE + BMW_PGA + NATIONWIDE


def _key(name: str) -> str | None:
    return _story_key(name, "golf")


def _item(name: str, rank: float) -> dict:
    return {
        "name": name,
        "_quality_story_key": _key(name),
        # Distinct per market, as the real family key is: this isolates the
        # story cap from the exact-duplicate cap, so a pass here cannot be the
        # `exact_family_cap` doing the work.
        "_quality_family_key": name,
        "_rank_score": rank,
        "_sort_time": 0,
    }


class TestTheFloodsFold:
    @pytest.mark.parametrize(
        "names,slug",
        [
            (BILTMORE, "biltmore_championship_asheville"),
            (BMW_PGA, "bmw_pga_championship"),
            (NATIONWIDE, "nationwide_children_s_hospital_championship"),
        ],
    )
    def test_every_name_form_lands_on_one_key(self, names, slug):
        """Three separators and two tour prefixes, one family."""
        assert {_key(n) for n in names} == {f"{GOLF_TOURNAMENT_STORY_PREFIX}{slug}"}

    def test_the_filed_symptom_is_gone(self):
        """24 Biltmore cards became 3 — the cap, not a drain."""
        items = [_item(n, 100 - i) for i, n in enumerate(BILTMORE)]
        kept = diversify_quality_families(items)
        assert len(items) == 24
        assert len(kept) == 3

    def test_the_cap_is_three_and_the_prefix_rule_is_what_makes_it_three(self):
        """🔴 The mutation this pins: a DERIVED key can never be in the literal
        `per_story_caps` dict, so without the prefix rule the family falls
        through to `story_family_cap` (5). Five Biltmore cards is not a fix, it
        is the same wall one card shorter — so this asserts 3 exactly, never
        "fewer than before"."""
        for names in (BILTMORE, BMW_PGA, NATIONWIDE):
            kept = diversify_quality_families(
                [_item(n, 100 - i) for i, n in enumerate(names)]
            )
            assert len(kept) == 3, names[0]

    def test_the_topic_keeps_its_best_card(self):
        """A cap that dropped the strongest representative would cost the
        reader the card they wanted; the survivors are the top-ranked three."""
        items = [_item(n, float(i)) for i, n in enumerate(BILTMORE)]
        kept = diversify_quality_families(items)
        assert [i["name"] for i in kept] == BILTMORE[-1:-4:-1]


class TestTheTrap:
    @pytest.mark.parametrize("name", NEVER_KEYED)
    def test_a_row_without_a_golf_question_is_never_keyed(self, name):
        key = _key(name)
        assert key is None or not key.startswith(GOLF_TOURNAMENT_STORY_PREFIX), key

    def test_the_misclassified_awards_all_survive_the_cap(self):
        """The four Producers Guild cards a naive pattern would have deleted."""
        items = [_item(n, 100 - i) for i, n in enumerate(NEVER_KEYED)]
        kept = diversify_quality_families(items)
        assert [i["name"] for i in kept] == NEVER_KEYED

    def test_a_flood_folding_does_not_take_its_bystanders_with_it(self):
        """The floods fold while everything else on the same page is untouched."""
        bystanders = NEVER_KEYED + SMALL_FAMILIES
        items = [_item(n, 100 - i) for i, n in enumerate(FLOODS + bystanders)]
        kept = diversify_quality_families(items)
        names = [i["name"] for i in kept]
        for n in bystanders:
            assert n in names, n
        folded = [n for n in names if n in FLOODS]
        assert len(folded) == 9  # three tournaments, three cards each


class TestOrderingInTheCascade:
    def test_the_authored_truist_arm_still_wins(self):
        """🔴 The arm is a `return` in a long cascade, so it is only correct
        where it sits. `truist championship` is authored end to end (title,
        question, cap 3) and is the MORE specific of the two; moving the
        derived arm above it silently replaces a shipped, authored family with
        a derived one. This test goes red if that line moves up."""
        assert _story_key("Truist Championship Winner", "golf") == (
            "story:golf_truist_championship"
        )

    def test_a_non_golf_category_never_mints_a_golf_key(self):
        """The grammar alone is not enough — "<two words> Winner" is a common
        shape. The category gate is the other half."""
        for category in ("tennis", "entertainment", "politics", ""):
            assert _story_key("Biltmore Championship Asheville Winner", category) != (
                f"{GOLF_TOURNAMENT_STORY_PREFIX}biltmore_championship_asheville"
            )

    def test_a_bare_question_with_no_tournament_left_is_not_a_family(self):
        """Nothing survives the suffix, so there is no tournament to group on."""
        for name in ("Winner", "Top 10", "Playoff", "Hole-in-One"):
            assert _key(name) is None, name

    @pytest.mark.parametrize(
        "name",
        [
            "Will there be a playoff?",
            "Will anyone make the cut?",
            "Who finishes in the Top 10",
            "Golfers to make the cut",
            "Will Rory McIlroy be the First Round Leader",
        ],
    )
    def test_a_question_shaped_name_ending_in_a_golf_suffix_is_not_a_tournament(
        self, name
    ):
        """🔴 NO SPECIMEN IN THE CORPUS EXERCISES THIS, SO IT IS MANUFACTURED.

        These are the shapes the venues use for exactly these markets, and the
        grammar alone accepts them: strip "playoff" off "Will there be a
        playoff?" and the remainder is "Will there be a", which slugifies to
        `story:golf_tournament:will_there_be_a` — a family that would collect
        every unrelated "Will there be a ..." market on the tour. Caught before
        it shipped only because the mutation run found the guard had no test."""
        key = _key(name)
        assert key is None or not key.startswith(GOLF_TOURNAMENT_STORY_PREFIX), key

    @pytest.mark.parametrize(
        "name", ["Championship Winner", "Playoff Winner", "Open - Top 5 Finish"]
    )
    def test_one_leftover_word_is_a_noun_not_a_tournament(self, name):
        """🔴 ALSO MANUFACTURED. "Championship Winner" leaves "Championship",
        which is not a tournament — it is the word every tournament ends with,
        so the key would herd unrelated stops into one family and cap them
        against each other. The two-word floor is what refuses it."""
        assert _key(name) is None, name


class TestTheEscapees:
    """🔴 A CAP IS ONLY AS GOOD AS THE KEY THE SERVING PATH ACTUALLY USES.

    `classify_market_quality` resolved `persisted_story_key or _story_key(...)`,
    and `futures_markets.story_key` has a SECOND writer:
    `enrich_cu_v2_profiles` stores `raw["story_key"]` — free text the model
    invented. Measured on production 2026-09-15: of 425 open markets carrying a
    persisted key, ZERO carry one `_story_key` could produce, and 406 of the
    413 distinct keys have exactly one member.

    These four are the real rows, verbatim. Each is a slug of its own title, so
    each is a family of one, so each would have walked through the cap and put
    its card back on the page beside the bundle — 24 Biltmore markets rendering
    as FIVE cards, not three, while the tests above all stayed green.
    """

    ESCAPEES = [
        (
            "Biltmore Championship Asheville Winner",
            "story:biltmore_championship_asheville_winner",
            "biltmore_championship_asheville",
        ),
        (
            "Biltmore Championship Asheville End of Round 1 Leader",
            "story:biltmore_championship_asheville_end_of_round_1_leader",
            "biltmore_championship_asheville",
        ),
        (
            "BMW PGA Championship Winner",
            "story:bmw_pga_championship_winner",
            "bmw_pga_championship",
        ),
        (
            "Amgen Irish Open: To Make the Cut",
            "story:amgen_irish_open_to_make_the_cut",
            "amgen_irish_open",
        ),
    ]

    @pytest.mark.parametrize("name,persisted,slug", ESCAPEES)
    def test_a_per_market_llm_key_does_not_outrank_the_tournament(
        self, name, persisted, slug
    ):
        from app.utils.feed_market_quality import classify_market_quality

        quality = classify_market_quality(
            name, sport_category="golf", persisted_story_key=persisted
        )
        assert quality.story_key == f"{GOLF_TOURNAMENT_STORY_PREFIX}{slug}"

    def test_the_whole_flood_still_folds_to_three_with_the_real_keys_persisted(self):
        """The filed number, re-measured with production's own persisted keys
        in place rather than with the column assumed empty."""
        from app.utils.feed_market_quality import classify_market_quality

        persisted = {name: key for name, key, _ in self.ESCAPEES}
        items = []
        for i, name in enumerate(BILTMORE):
            quality = classify_market_quality(
                name,
                sport_category="golf",
                persisted_story_key=persisted.get(name),
            )
            items.append(
                {
                    "name": name,
                    "_quality_story_key": quality.story_key,
                    "_quality_family_key": name,
                    "_rank_score": 100 - i,
                    "_sort_time": 0,
                }
            )
        assert len(diversify_quality_families(items)) == 3

    def test_a_persisted_key_still_wins_everywhere_else(self):
        """The scoping half. Outside the golf grammar this ship changes
        nothing — the general precedence defect is filed, not fixed here."""
        from app.utils.feed_market_quality import classify_market_quality

        quality = classify_market_quality(
            "Iran leader end of 2026?",
            sport_category="politics",
            persisted_story_key="story:iran_leader_end_of_2026",
        )
        assert quality.story_key == "story:iran_leader_end_of_2026"


class TestTheBundleCopy:
    """The cap runs BEFORE the bundler, so three survivors meet `min_items=2`
    and the family folds into ONE card whose headline a reader reads."""

    @pytest.mark.parametrize(
        "names,label",
        [
            (BILTMORE, "Biltmore Championship Asheville"),
            (BMW_PGA, "BMW PGA Championship"),
            (NATIONWIDE, "Nationwide Children's Hospital Championship"),
        ],
    )
    def test_the_headline_is_the_tournament_as_the_venue_writes_it(self, names, label):
        """🔴 Neither fallback under this key is shippable: un-slugifying gives
        "Golf Tournament:bmw PGA Championship" and the shared-member phrase
        gives "nationwide children s hospital championship". Acronyms and the
        apostrophe survive only because the name is cut verbatim."""
        resolved = _golf_tournament_bundle_copy(_key(names[0]), names)
        assert resolved is not None
        assert resolved[0] == label

    @pytest.mark.parametrize("names", [BILTMORE, BMW_PGA, NATIONWIDE])
    def test_the_question_is_true_of_every_member(self, names):
        """🔴 #4147's rule, applied before it could bite. "Who wins the BMW PGA
        Championship?" — the phrasing the neighbouring authored golf key uses —
        is FALSE of the hole-in-one, albatross, playoff and make-the-cut rows
        that sit directly under it in this very family."""
        _, question = _golf_tournament_bundle_copy(_key(names[0]), names)
        assert question.startswith("What happens at ")
        assert "who wins" not in question.lower()

    def test_a_tournament_named_the_something_does_not_get_two_articles(self):
        names = ["The Open Winner", "The Open - Top 10 Finish"]
        label, question = _golf_tournament_bundle_copy(_key(names[0]), names)
        assert label == "The Open"
        assert question == "What happens at The Open?"

    def test_no_statable_tournament_means_no_bundle(self):
        """Fail closed rather than headline a card with a derived slug."""
        assert (
            _golf_tournament_bundle_copy(
                f"{GOLF_TOURNAMENT_STORY_PREFIX}whatever", ["Winner", "Playoff"]
            )
            is None
        )


class TestTheCardAReaderActuallyGets:
    """🔴 EVERY TEST ABOVE CALLS `_golf_tournament_bundle_copy` DIRECTLY, WHICH
    IS NOT THE THING THAT SHIPS. Deleting the branch that CALLS it in
    `_make_theme_bundle_item` left all of them green in the mutation run while
    the bundle reverted to the un-slugified headline. These drive the public
    folder instead, so the wiring is what is under test."""

    @staticmethod
    def _feed_items(names: list[str]) -> list[dict]:
        return [
            {
                "type": "futures",
                "score": float(100 - i),
                "_sort_time": 0,
                "_quality_story_key": _key(name),
                "data": {
                    "id": 9000 + i,
                    "name": name,
                    "llm_sport_category": "golf",
                    "discover_card": {},
                },
            }
            for i, name in enumerate(names)
        ]

    @pytest.mark.parametrize(
        "names,label,question",
        [
            (
                BILTMORE[:3],
                "Biltmore Championship Asheville",
                "What happens at the Biltmore Championship Asheville?",
            ),
            (
                BMW_PGA[:3],
                "BMW PGA Championship",
                "What happens at the BMW PGA Championship?",
            ),
            (
                NATIONWIDE[:3],
                "Nationwide Children's Hospital Championship",
                "What happens at the Nationwide Children's Hospital Championship?",
            ),
        ],
    )
    def test_the_folded_card_reads_like_a_tournament(self, names, label, question):
        out = assemble_story_theme_bundles(self._feed_items(names))
        bundles = [i for i in out if i.get("type") == "bundle"]
        assert len(bundles) == 1, out
        bundle = bundles[0]
        assert bundle["headline"] == label
        assert bundle["data"]["title"] == label
        assert bundle["reason"] == question
        assert bundle["data"]["shared_question"] == question

    def test_no_slug_or_key_vocabulary_reaches_the_screen(self):
        """Notice 34: a reader never sees our internal words. The derived key
        contains "golf_tournament" and underscores; neither may surface."""
        out = assemble_story_theme_bundles(self._feed_items(BMW_PGA[:3]))
        bundle = next(i for i in out if i.get("type") == "bundle")
        for text in (bundle["headline"], bundle["reason"], bundle["data"]["title"]):
            assert "_" not in text, text
            assert "story:" not in text.lower(), text
            assert "golf_tournament" not in text.lower(), text

    def test_a_tournament_under_the_cap_is_left_alone(self):
        """Amgen has two open markets. It folds (min_items=2) but must read
        just as well — this is the arm that proves the copy is not tuned to the
        three floods."""
        names = ["Amgen Irish Open: To Make the Cut", "Amgen Irish Open: Top 10 Finishers"]
        out = assemble_story_theme_bundles(self._feed_items(names))
        bundle = next(i for i in out if i.get("type") == "bundle")
        assert bundle["headline"] == "Amgen Irish Open"
        assert bundle["reason"] == "What happens at the Amgen Irish Open?"

    def test_the_misclassified_awards_never_fold_into_a_golf_card(self):
        out = assemble_story_theme_bundles(self._feed_items(NEVER_KEYED))
        golf = [
            i
            for i in out
            if i.get("type") == "bundle"
            and str(i.get("data", {}).get("story_key", "")).startswith(
                GOLF_TOURNAMENT_STORY_PREFIX
            )
        ]
        assert golf == []


class TestTheDisplayNameHelper:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("PGA Tour: Biltmore Championship Asheville Top 5", "Biltmore Championship Asheville"),
            ("DP World Tour: BMW PGA Championship Albatross?", "BMW PGA Championship"),
            ("Biltmore Championship Asheville: Hole-in-One", "Biltmore Championship Asheville"),
            ("Biltmore Championship Asheville - Winner", "Biltmore Championship Asheville"),
            ("Amgen Irish Open: Top 10 Finishers", "Amgen Irish Open"),
        ],
    )
    def test_the_prefix_and_the_question_both_come_off(self, name, expected):
        assert golf_tournament_display_name(name) == expected

    def test_a_name_that_is_only_a_question_yields_nothing(self):
        assert golf_tournament_display_name("Will Tiger Woods play in 2026?") is None
