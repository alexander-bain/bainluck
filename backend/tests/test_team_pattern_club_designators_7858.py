"""#7858 — a club-type designator is never a bare ILIKE token.

`_team_name_patterns("Leeds United")` emitted a bare `'United'`, so the
related-futures seam (`any_pattern_matches_token`, #6806) assigned every
"… United" outcome in the table to Leeds. Production 2026-09-21 20:40Z,
`/api/events/15311082/related-futures`: **19 of the 23 futures served as Leeds
United's own were another club**, including the United Arab Emirates twice.

The payload in `_WRONG_CLUBS_ON_THE_LEEDS_CARD` is that response, verbatim —
the fixture IS the specimen, so a rule that fixes an invented label and not the
served one cannot pass here.

Sibling classes this file also pins, because they share the one gate:
  * #5798 — bare place qualifiers (`State`, `South`) must stay refused.
  * #6806 — the whole-token rule must stay the boundary test, not a substring.
  * #7676 — `City`, the same defect on Hull City / Coventry City.
"""

import pytest

from app.routes.events import (
    _CLUB_TYPE_DESIGNATORS,
    _GENERIC_PLACE_QUALIFIERS,
    _NON_DISTINCTIVE_BARE_TOKENS,
    _team_name_patterns,
)
from app.utils.team_pattern_match import any_pattern_matches_token

# ── The specimen, verbatim from the banked production payload ───────────────

#: The 19 outcome names served on Leeds United's side that are another club.
_WRONG_CLUBS_ON_THE_LEEDS_CARD = [
    "Loudoun United FC",
    "Scunthorpe United FC",
    "New Mexico United",
    "Boston United FC",
    "Incheon United",
    "Sheffield United",
    "United Arab Emirates",
    "Manchester United",
    "Atlanta United FC",
    "D.C. United",
    "Minnesota United FC",
    "Newcastle United",
    "Sisaket United FC",
    "Pathum United",
    "Rasisalai United",
]

#: The four that ARE Leeds, from the same payload. A fix that drops these is a
#: recall regression wearing the right answer's clothes.
_LEEDS_OWN_ROWS = ["Leeds United", "Leeds"]


class TestTheSpecimen:
    def test_leeds_no_longer_searches_on_a_bare_designator(self):
        assert _team_name_patterns("Leeds United") == ["Leeds United", "Leeds"]

    @pytest.mark.parametrize("label", _WRONG_CLUBS_ON_THE_LEEDS_CARD)
    def test_another_club_is_refused_for_leeds(self, label):
        assert not any_pattern_matches_token(label, _team_name_patterns("Leeds United"))

    @pytest.mark.parametrize("label", _LEEDS_OWN_ROWS)
    def test_leeds_own_rows_are_kept(self, label):
        assert any_pattern_matches_token(label, _team_name_patterns("Leeds United"))

    def test_the_control_side_of_the_same_payload_is_untouched(self):
        """Arsenal is one token, so `len(parts) > 1` never runs — one pattern,
        and it still matches its own label."""
        assert _team_name_patterns("Arsenal") == ["Arsenal"]
        assert any_pattern_matches_token("Arsenal", _team_name_patterns("Arsenal"))


# ── Recall: every club the bare token used to be doing work for ─────────────


class TestRecallIsPreserved:
    """The census (comment above `_CLUB_TYPE_DESIGNATORS`) measured 0 rows that
    name a club by the designator alone. These pin the mechanisms that make it 0."""

    @pytest.mark.parametrize(
        "team,own_label",
        [
            ("Manchester United", "Manchester United"),
            ("Manchester United", "Man Utd is not this row, Manchester United is"),
            ("Newcastle United", "Newcastle United FC vs. Arsenal FC"),
            ("Sheffield United", "EFL Championship: Promotion — Sheffield United"),
            ("D.C. United", "CF Montréal 0 - 0 D.C. United SC"),
            ("Minnesota United", "Austin FC vs. Minnesota United FC"),
            ("Hull City", "Caykur Rizespor 0 - 0 Hull City"),
            ("Coventry City", "Arsenal FC 0 - 0 Coventry City FC"),
            ("Manchester City", "Aston Villa WFC 0 - 0 Manchester City WFC"),
            ("Ipswich Town", "Crystal Palace FC 0 - 3 Ipswich Town FC"),
            ("Grimsby Town", "Draw (Accrington Stanley FC vs. Grimsby Town FC)"),
        ],
    )
    def test_a_club_still_matches_its_own_row(self, team, own_label):
        assert any_pattern_matches_token(own_label, _team_name_patterns(team))

    @pytest.mark.parametrize(
        "team,own_label",
        [
            # Place word under 4 chars, so no city pattern is emitted and the
            # full name is the ONLY pattern left. Measured: every row these two
            # appear on carries the full name.
            ("876 United", "876 United vs Glitch FC"),
            ("Ayr United", "Ayr United FC vs. Alloa Athletic FC"),
        ],
    )
    def test_a_short_place_word_club_survives_on_its_full_name(self, team, own_label):
        assert _team_name_patterns(team) == [team]
        assert any_pattern_matches_token(own_label, _team_name_patterns(team))

    @pytest.mark.parametrize(
        "team,other_clubs_row",
        [
            ("Hull City", "1: Denver / 2: Kansas City / 3: Las Vegas"),
            ("Hull City", "Aston Villa WFC 0 - 0 Manchester City WFC"),
            ("Coventry City", "Atlanta vs Oklahoma City"),
            ("Ipswich Town", "Draw (Accrington Stanley FC vs. Grimsby Town FC)"),
            ("Ipswich Town", "Boreham Wood FC 0 - 0 Harrogate Town AFC"),
        ],
    )
    def test_the_city_and_town_halves_of_the_same_defect(self, team, other_clubs_row):
        assert not any_pattern_matches_token(other_clubs_row, _team_name_patterns(team))


# ── Multi-word patterns that CONTAIN a designator are untouched ─────────────


class TestOnlyTheBareTokenGoes:
    @pytest.mark.parametrize(
        "team,expected",
        [
            ("Kansas City Chiefs",
             ["Kansas City Chiefs", "Chiefs", "Kansas City", "Kansas"]),
            ("Oklahoma City Thunder",
             ["Oklahoma City Thunder", "Thunder", "Oklahoma City", "Oklahoma"]),
            ("North East United", ["North East United", "North East"]),
            ("West Ham United", ["West Ham United", "West Ham"]),
        ],
    )
    def test_the_multi_word_place_pattern_survives(self, team, expected):
        assert _team_name_patterns(team) == expected

    def test_kansas_city_still_matches_its_own_row(self):
        assert any_pattern_matches_token(
            "Kansas City Chiefs", _team_name_patterns("Kansas City Chiefs")
        )

    def test_kansas_city_no_longer_claims_manchester_city(self):
        assert not any_pattern_matches_token(
            "Manchester City", _team_name_patterns("Kansas City Chiefs")
        )


# ── The sibling rulings this change must not regress ────────────────────────


class TestSiblingClasses:
    def test_5798_place_qualifiers_still_refused(self):
        patterns = _team_name_patterns("Arkansas State Red Wolves")
        assert patterns == [
            "Arkansas State Red Wolves", "Wolves", "Arkansas State Red", "Arkansas",
        ]
        assert not any_pattern_matches_token("Ohio State Buckeyes", patterns)

    def test_6806_whole_token_rule_still_applies(self):
        patterns = _team_name_patterns("Lech Poznań")
        assert patterns == ["Lech Poznań", "Poznań", "Lech"]
        assert not any_pattern_matches_token("Anderlecht", patterns)

    def test_a_real_place_word_is_still_a_token(self):
        """The membership test is "could an outcome be labelled this ALONE?".
        Kalshi does label outcomes "Texas" — dropping it would cost recall."""
        assert "Texas" in _team_name_patterns("Texas Rangers")


# ── The class assertion: both gate sites read the same set ──────────────────


class TestTheGateIsOneSet:
    def test_the_two_families_are_disjoint_and_unioned(self):
        assert _GENERIC_PLACE_QUALIFIERS & _CLUB_TYPE_DESIGNATORS == frozenset()
        assert (
            _NON_DISTINCTIVE_BARE_TOKENS
            == _GENERIC_PLACE_QUALIFIERS | _CLUB_TYPE_DESIGNATORS
        )

    @pytest.mark.parametrize(
        "team",
        [
            # mascot slot (parts[-1])
            "Leeds United", "Hull City", "Ipswich Town", "Penn State",
            # the >=3-word loop (parts[:-1]) — the OTHER gate site, which a
            # change that edits only one of the two would leave open
            "Kansas City Chiefs", "Oklahoma City Thunder",
            "Arkansas State Red Wolves", "North East United",
            "Sporting Kansas City", "New York City FC",
        ],
    )
    def test_no_gated_token_is_ever_emitted_bare(self, team):
        emitted_bare = {
            p.lower() for p in _team_name_patterns(team) if " " not in p
        }
        assert emitted_bare & _NON_DISTINCTIVE_BARE_TOKENS == set(), (
            f"{team} emits a gated token as a standalone pattern: "
            f"{sorted(emitted_bare & _NON_DISTINCTIVE_BARE_TOKENS)}"
        )
