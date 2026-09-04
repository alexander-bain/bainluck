"""The ten name shapes that decide whether a tennis row can find its match. #2867.

`app/utils/tennis_name_matching` is the whole of the join between StatPal's
`"B. Van De Zandschulp"` and our `"Botic van de Zandschulp"`. No id connects
them, so if this module is wrong the link is wrong, and a wrong link is an
`event_provider_anchors` row pointing one real match at another.

## why these specimens and not others

Every one is a shape the measurement bus's 2026-09-03 sweep
(`ARTIFACT-M-20260903-I`) hit on real data and banked verbatim as the ten
hardest, plus three more this session found in the live payload. They are not
illustrative: each is a DIFFERENT structural difference between the two
renderings, and a rule that handles nine of them still mis-links the tenth.

## both directions, always

The false-negative arm (a shape that should match and does not) costs coverage.
The false-positive arm (two different players read as one) costs a cross-match
between two real games, which is what ruling 048 exists to prevent. The second
is much worse, so the refusal specimens are paired with their near-miss twin:
`Ka. Pliskova` must accept *Karolina* AND refuse *Kristyna*, and a test that only
asserts the first passes just as well with the initial ignored entirely.
"""

from __future__ import annotations

import pytest

from app.utils.tennis_name_matching import (
    names_match,
    normalize_tokens,
    pair_matches,
    split_initials,
)


class TestTheTenBankedShapes:
    """Verbatim from the sweep's "10 hardest name shapes", plus three found live."""

    SHAPES = [
        # (statpal, ours, what makes it hard)
        ("Y. Bu", "Bu Yunchaokete", "family name written FIRST"),
        ("B. Van De Zandschulp", "Botic van de Zandschulp", "particles, title-cased"),
        ("C. Wong", "Chak Lam Coleman Wong", "three given names"),
        ("D. Merida Aguilar", "Daniel Merida Aguilar", "maternal surname kept"),
        ("T. M. Etcheverry", "Tomas Martin Etcheverry", "two initials"),
        ("A. De Minaur", "Alex de Minaur", "particle, case differs"),
        ("T. Barrios Vera", "Tomas Barrios Vera", "two-token surname"),
        ("L. van Assche", "Luca Van Assche", "particle lowercase upstream"),
        ("Z. Svajda", "Zachary Svajda", "given name abbreviated"),
        ("F. Auger-Aliassime", "Felix Auger Aliassime", "hyphen vs space"),
        # found in the live payload on 2026-09-03, same class:
        ("Ka. Pliskova", "Karolina Pliskova", "MULTI-letter initial"),
        ("Xin. Wang", "Xinyu Wang", "three-letter initial"),
        ("Y. Wu", "Wu Yibing", "family name first, two-letter surname"),
    ]

    @pytest.mark.parametrize(
        "statpal,ours,why", SHAPES, ids=[s[0].replace(" ", "_") for s in SHAPES]
    )
    def test_the_shape_matches(self, statpal, ours, why):
        assert names_match(statpal, ours), why

    @pytest.mark.parametrize(
        "statpal,ours,why", SHAPES, ids=[s[0].replace(" ", "_") for s in SHAPES]
    )
    def test_the_shape_matches_with_diacritics_on_either_side(self, statpal, ours, why):
        """Providers disagree about accents; the fold is applied to both sides."""
        assert names_match(statpal.replace("a", "á"), ours) or "a" not in statpal
        assert names_match(statpal, ours.replace("a", "á")) or "a" not in ours


class TestTheRefusalsThatMakeTheMatchesMeanSomething:
    """Each is the near-miss twin of a specimen above.

    Without these, the rule "everything matches" scores 13/13 on the class above.
    """

    NEAR_MISSES = [
        ("Ka. Pliskova", "Kristyna Pliskova", "the multi-letter initial is the point"),
        ("Xin. Wang", "Xiyu Wang", "Xinyu and Xiyu share the same surname and draw"),
        ("Y. Bu", "Bu Ming", "family-name-first still has to agree on the initial"),
        ("M. Zheng", "Zheng Qinwen", "and it has to agree in the right direction"),
        ("A. Zverev", "Mischa Zverev", "brothers"),
        ("J. De Jong", "Jesper Jong", "the particle is part of the surname"),
        ("A. Rublev", "Andrey Rublev Jr", "the surname must END our name"),
        ("T. M. Etcheverry", "Martin Tomas Etcheverry", "initials are ordered"),
    ]

    @pytest.mark.parametrize(
        "statpal,ours,why", NEAR_MISSES, ids=[s[1].replace(" ", "_") for s in NEAR_MISSES]
    )
    def test_it_is_refused(self, statpal, ours, why):
        assert not names_match(statpal, ours), why

    def test_the_control_ignoring_the_initial_would_pass_the_matches_and_fail_here(self):
        """The arm that shows the initial check is load-bearing, not decoration.

        Surname-only agreement accepts every specimen in the class above AND
        every near-miss in this one. If a future edit drops the initial check,
        the tests above keep passing and only these fail — which is the whole
        reason they are written as pairs.
        """
        surname_only = lambda sp, ours: (  # noqa: E731 — the control, deliberately terse
            split_initials(sp).surname[-1] in normalize_tokens(ours)
        )
        for statpal, ours, _ in TestTheTenBankedShapes.SHAPES:
            assert surname_only(statpal, ours)
        leaks = [
            (sp, ours)
            for sp, ours, _ in self.NEAR_MISSES
            if surname_only(sp, ours)
        ]
        assert len(leaks) >= 5, (
            "the control must actually leak, or it is not showing that the real "
            f"rule is doing work; leaked {leaks}"
        )


class TestDoublesAreRefusedBeforeTheQuestionIsAsked:
    """We hold no doubles rows, so a doubles name can only match by accident.

    The sweep's token fallback caught 30+ false doubles-to-singles hits before
    doubles were excluded, which is why this is a hard refusal at the front of
    the parser rather than a filter somewhere downstream.
    """

    @pytest.mark.parametrize(
        "pair_name",
        [
            "Galloway/ Goransson",
            "Rojer/ Winegar",
            "Guarachi/ Sherif",
            "Bonzi/Rinderknech",
        ],
    )
    def test_a_doubles_name_parses_to_nothing(self, pair_name):
        assert split_initials(pair_name) is None

    @pytest.mark.parametrize(
        "pair_name,singles_name",
        [
            ("Galloway/ Goransson", "Robert Galloway"),
            ("Bonzi/Rinderknech", "Benjamin Bonzi"),
            ("Guarachi/ Sherif", "Mayar Sherif"),
        ],
    )
    def test_a_doubles_name_never_matches_one_of_its_own_players(
        self, pair_name, singles_name
    ):
        assert not names_match(pair_name, singles_name)


class TestTheParser:
    def test_leading_tokens_only_are_read_as_initials(self):
        parsed = split_initials("D. Merida Aguilar")
        assert parsed.initials == ("d",)
        assert parsed.surname == ("merida", "aguilar")

    def test_a_multi_letter_initial_keeps_all_its_letters(self):
        assert split_initials("Ka. Pliskova").initials == ("ka",)
        assert split_initials("Xin. Wang").initials == ("xin",)

    def test_a_lowercase_particle_is_surname_not_initial(self):
        parsed = split_initials("L. van Assche")
        assert parsed.initials == ("l",)
        assert parsed.surname == ("van", "assche")

    def test_a_name_with_no_surname_is_unusable_rather_than_matching_everything(self):
        assert split_initials("A.") is None
        assert split_initials("") is None
        assert split_initials(None) is None

    def test_hyphen_and_apostrophe_are_separators_on_both_sides(self):
        assert normalize_tokens("Auger-Aliassime") == ["auger", "aliassime"]
        assert normalize_tokens("O'Connell") == ["o", "connell"]
        assert names_match("C. O'Connell", "Christopher O Connell")

    def test_a_surname_only_statpal_name_never_uses_the_prefix_arm(self):
        """Without an initial there is nothing bounding the family-name-first arm.

        The suffix arm still works — a surname that ENDS our name is ordinary
        western order and needs no initial to be believable. The prefix arm does
        not: `Bu` begins any number of names, and the initial is the only thing
        that refuses the wrong ones. So dropping the initial drops that arm, and
        `"Bu"` alone no longer reaches `"Bu Yunchaokete"`.

        The cost of that refusal is bounded and the cost of the alternative is
        not: an unbounded prefix arm mis-links two real matches, where this
        merely fails to link one — and the sweep's own `Wu` specimen is exactly
        the case, left to the forward matcher's initial-bearing renderings.
        """
        assert names_match("Zandschulp", "Botic van de Zandschulp") is True
        assert names_match("Svajda", "Zachary Svajda") is True
        assert names_match("Bu", "Bu Yunchaokete") is False
        assert names_match("Y. Bu", "Bu Yunchaokete") is True

    def test_a_ghost_row_with_only_a_surname_does_not_link(self):
        """Measured: our placeholder rows carry `"Sonmez"`, not `"Zeynep Sonmez"`.

        Refusing them is deliberate. There is no given name for the initial to
        corroborate, and those rows are midnight-UTC placeholders that duplicate
        a real row — linking one would stamp the duplicate.
        """
        assert not names_match("Z. Sonmez", "Sonmez")
        assert not names_match("C. Gauff", "Gauff")


class TestAPairIsTwoDistinctPeople:
    def test_either_orientation_matches(self):
        assert pair_matches(
            ("B. Van De Zandschulp", "A. De Minaur"),
            ("Botic van de Zandschulp", "Alex de Minaur"),
        )
        assert pair_matches(
            ("B. Van De Zandschulp", "A. De Minaur"),
            ("Alex de Minaur", "Botic van de Zandschulp"),
        )

    def test_one_player_matching_both_slots_is_refused(self):
        """`A. Zverev` v `A. Zverev` must not satisfy a real match's two slots."""
        assert not pair_matches(
            ("A. Zverev", "A. Zverev"),
            ("Alexander Zverev", "Alexander Zverev"),
        )

    def test_one_matching_player_is_not_a_match(self):
        assert not pair_matches(
            ("B. Van De Zandschulp", "A. De Minaur"),
            ("Botic van de Zandschulp", "Carlos Alcaraz"),
        )

    def test_the_real_live_specimen_that_broke_a_naive_matcher(self):
        """`Y. Bu` v `M. Zheng` against a row that writes BOTH names either way.

        Our own database held this match as `"Bu Yunchaokete"` on one row and
        `"Yunchaokete Bu"` on another (measured 2026-09-03). Both are the same
        player and both must match, which is why the surname is allowed at either
        end.
        """
        assert pair_matches(("Y. Bu", "M. Zheng"), ("Bu Yunchaokete", "Michael Zheng"))
        assert pair_matches(("Y. Bu", "M. Zheng"), ("Yunchaokete Bu", "Michael Zheng"))
