"""Guards for `app/utils/prop_template_family.py` (UX-P154, Alex's item 1).

Alex, 2026-08-28, on UX-P151's combined second-major card: *"Was this a bespoke
solution? I thought we'd built tools to identify groups and surface them as
groups. Why didn't any of them trigger?"*

The module's docstring answers the *why not*. This file guards the *instead*:
a template family is found from the markets themselves, so the next one does
not need a person to notice it.

The specimens are the REAL production titles and outcome names, read
2026-08-28, because a detector tested only against titles written to suit it
proves nothing about the shape it will meet.
"""

from __future__ import annotations

import pytest

from app.utils.prop_template_family import (
    MIN_SHARED_TOKENS,
    detect_template_families,
    outcome_signature,
    subject_display,
)

# ── Real specimens, production 2026-08-28 ────────────────────────────────────
#
# ⚠️ THE TWO LADDERS DO NOT CARRY THE SAME RUNGS, and that is measured, not
# invented for the test: Alcaraz's market lists `2+ / 3+ / All 4` and Sinner's
# lists `1+ / 2+ / 3+`. The first version of this detector required an identical
# outcome SET and would have failed to find the one family we already know
# exists. The intersection rule is what the data forced.
ALCARAZ = {
    "market_ext": "KXGRANDSLAM-CALC26",
    "market_name": "Carlos Alcaraz: Grand Slam wins in 2026",
    "source": "kalshi",
    "outcomes": ["2+ Grand Slam wins", "All 4 Grand Slam wins", "3+ Grand Slam wins"],
}
SINNER = {
    "market_ext": "KXGRANDSLAM-JSIN26",
    "market_name": "Jannik Sinner: Grand Slam wins in 2026",
    "source": "kalshi",
    "outcomes": ["1+ Grand Slam wins", "2+ Grand Slam wins", "3+ Grand Slam wins"],
}
SINNER_PLAYS = {
    "market_ext": "KXATPCOMPETE-26USOSIN",
    "market_name": "Jannik Sinner to play in the US Open",
    "source": "kalshi",
    "outcomes": ["Yes"],
}
ALCARAZ_PLAYS = {
    "market_ext": "KXATPCOMPETE-26USOALC",
    "market_name": "Carlos Alcaraz to play in the US Open",
    "source": "kalshi",
    "outcomes": ["Yes"],
}
ATP_FIELD = {
    "market_ext": "KXATPGRANDSLAM-26",
    "market_name": "Who will win a ATP Grand Slam in 2026?",
    "source": "kalshi",
    "outcomes": ["Jannik Sinner", "Carlos Alcaraz", "Alexander Zverev"],
}
WTA_FIELD = {
    "market_ext": "KXWTAGRANDSLAM-26",
    "market_name": "Who will win a WTA Grand Slam in 2026?",
    "source": "kalshi",
    "outcomes": ["Aryna Sabalenka", "Iga Swiatek"],
}


class TestTheFamilyAlexAskedAbout:
    def test_the_two_ladders_are_one_family(self):
        families = detect_template_families([ALCARAZ, SINNER])
        assert len(families) == 1
        family = families[0]
        assert family.skeleton == "{} grand slam wins in 2026"
        assert family.market_exts == ("KXGRANDSLAM-CALC26", "KXGRANDSLAM-JSIN26")

    def test_the_rows_are_named_in_the_sources_own_words(self):
        """Alex's item 4: *"the market's own words are USED when they are the
        market's words."* UX-P151 hand-wrote "Alcaraz" and "Sinner"."""
        family = detect_template_families([ALCARAZ, SINNER])[0]
        assert [m.display_name for m in family.members] == [
            "Carlos Alcaraz",
            "Jannik Sinner",
        ]

    def test_shared_outcomes_is_the_intersection_not_either_side(self):
        """The rule the real rungs forced. `1+` is Sinner's alone and `All 4` is
        Alcaraz's alone; neither may be offered as something the card can
        compare, because one member has no number for it."""
        family = detect_template_families([ALCARAZ, SINNER])[0]
        assert family.signature == ("2 grand slam wins", "3 grand slam wins")

    def test_a_third_subject_joins_with_no_change_to_anything(self):
        """The actual test of "by the system"."""
        djokovic = {
            "market_ext": "KXGRANDSLAM-NDJO26",
            "market_name": "Novak Djokovic: Grand Slam wins in 2026",
            "source": "kalshi",
            "outcomes": ["1+ Grand Slam wins", "2+ Grand Slam wins"],
        }
        families = detect_template_families([ALCARAZ, SINNER, djokovic])
        assert len(families) == 1
        # Ordered by ticker, which is the one ordering that does not move when a
        # source re-sorts its own response.
        assert [m.display_name for m in families[0].members] == [
            "Carlos Alcaraz",
            "Jannik Sinner",
            "Novak Djokovic",
        ]
        # The intersection narrows as it must: Djokovic has no `3+` rung.
        assert families[0].signature == ("2 grand slam wins",)


class TestWhatItRefusesToGroup:
    def test_a_ladder_and_a_yes_no_are_not_a_family(self):
        """Same subject, same tournament, titles that pair — and nothing the
        card could put in one column. This is the UX-P134 defect in grouping
        form: a `2+ Grand Slam wins` beside a `Yes` under one heading."""
        ladder = {
            "market_ext": "A",
            "market_name": "Carlos Alcaraz in the US Open",
            "source": "kalshi",
            "outcomes": ["2+ Grand Slam wins"],
        }
        binary = {
            "market_ext": "B",
            "market_name": "Jannik Sinner in the US Open",
            "source": "kalshi",
            "outcomes": ["Yes"],
        }
        assert detect_template_families([ladder, binary]) == []

    def test_two_unrelated_questions_are_not_a_family(self):
        assert detect_template_families([SINNER, SINNER_PLAYS]) == []

    def test_the_two_grand_slam_fields_are_not_a_family(self):
        """ "Who will win a ATP Grand Slam in 2026?" and its WTA twin DO differ
        in one token, and they are still not a family: they share no outcome,
        because they hold different players. The outcome half of the rule is
        what catches this — a card putting Sabalenka's row beside Sinner's under
        one question would be two draws in one column."""
        assert detect_template_families([ATP_FIELD, WTA_FIELD]) == []

    def test_two_different_tournaments_are_not_a_template(self):
        """THE specimen `MAX_SUBJECT_RATIO` exists for, and it caught this rule
        the first time it ran.

        These DO differ in one contiguous run and they DO share three trailing
        tokens ("open in 2026"), so a floor-only rule paired them into
        `{} open in 2026` with subjects "alcaraz to win the us" and "sinner to
        win the australian" — two different tournaments on one card. The
        difference had swallowed the question, and the fix is that the subject
        may not be longer than the part the two titles agree on.
        """
        left = {
            "market_ext": "A",
            "market_name": "Alcaraz to win the US Open in 2026",
            "source": "kalshi",
            "outcomes": ["Yes"],
        }
        right = {
            "market_ext": "B",
            "market_name": "Sinner to win the Australian Open in 2026",
            "source": "kalshi",
            "outcomes": ["Yes"],
        }
        assert detect_template_families([left, right]) == []

    def test_the_same_tournament_named_the_same_way_IS_a_template(self):
        """The control for the test above: same rule, same shape, one fewer
        differing token, and now the shared part is the bigger half. Without
        this the guard above could be passing because the rule rejects
        everything."""
        left = {
            "market_ext": "A",
            "market_name": "Alcaraz to win the US Open in 2026",
            "source": "kalshi",
            "outcomes": ["Yes"],
        }
        right = {
            "market_ext": "B",
            "market_name": "Sinner to win the US Open in 2026",
            "source": "kalshi",
            "outcomes": ["Yes"],
        }
        families = detect_template_families([left, right])
        assert len(families) == 1
        assert families[0].skeleton == "{} to win the us open in 2026"

    def test_two_short_titles_sharing_one_word_are_not_a_family(self):
        """One shared word is evidence of English, not of a template."""
        left = {
            "market_ext": "A",
            "market_name": "Alcaraz wins",
            "source": "k",
            "outcomes": ["Yes"],
        }
        right = {
            "market_ext": "B",
            "market_name": "Sinner wins",
            "source": "k",
            "outcomes": ["Yes"],
        }
        assert MIN_SHARED_TOKENS == 2
        assert detect_template_families([left, right]) == []

    def test_identical_titles_are_a_duplicate_not_a_family(self):
        twin = {**ALCARAZ, "market_ext": "KXGRANDSLAM-CALC26-DUPE"}
        assert detect_template_families([ALCARAZ, twin]) == []

    def test_a_lone_market_is_a_card_not_a_family_of_one(self):
        assert detect_template_families([SINNER]) == []

    def test_a_market_with_no_outcomes_cannot_be_grouped(self):
        bare = {**SINNER, "outcomes": []}
        assert detect_template_families([ALCARAZ, bare]) == []


class TestTheGeneralShape:
    """Nothing in the detector knows about tennis. These are the same rule on
    populations it has never seen, which is the claim "systemic" makes."""

    def test_it_groups_a_weather_template(self):
        cities = [
            {
                "market_ext": f"KXRAIN-{code}",
                "market_name": f"Will it rain in {city} on Tuesday?",
                "source": "kalshi",
                "outcomes": ["Yes", "No"],
            }
            for code, city in (
                ("CHI", "Chicago"),
                ("DEN", "Denver"),
                ("NYC", "New York"),
            )
        ]
        families = detect_template_families(cities)
        assert len(families) == 1
        assert families[0].skeleton == "will it rain in {} on tuesday"
        assert [m.display_name for m in families[0].members] == [
            "Chicago",
            "Denver",
            "New York",
        ]

    def test_it_groups_a_next_team_template(self):
        players = [
            {
                "market_ext": "A",
                "market_name": "LeBron James Next Team",
                "source": "kalshi",
                "outcomes": ["Lakers", "Warriors"],
            },
            {
                "market_ext": "B",
                "market_name": "Kevin Durant Next Team",
                "source": "polymarket",
                "outcomes": ["Lakers", "Suns"],
            },
        ]
        families = detect_template_families(players)
        assert len(families) == 1
        assert families[0].skeleton == "{} next team"
        assert families[0].signature == ("lakers",)


class TestHelpers:
    def test_outcome_signature_is_order_independent_and_deduped(self):
        assert outcome_signature(["B", "a", "A"]) == ("a", "b")

    @pytest.mark.parametrize(
        "title,tokens,expected",
        [
            (
                "Carlos Alcaraz: Grand Slam wins in 2026",
                ("carlos", "alcaraz"),
                "Carlos Alcaraz",
            ),
            ("Will it rain in New York on Tuesday?", ("new", "york"), "New York"),
            # Re-scan misses -> title-case fallback, which is still a real name.
            ("nothing here", ("carlos", "alcaraz"), "Carlos Alcaraz"),
        ],
    )
    def test_subject_display_returns_the_sources_own_casing(
        self, title, tokens, expected
    ):
        assert subject_display(title, tokens) == expected

    def test_subject_display_is_empty_for_no_subject(self):
        assert subject_display("anything", ()) == ""
