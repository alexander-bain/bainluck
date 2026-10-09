"""#3667 — a strict truncation of our own place is not us.

`_team_name_patterns("Alabama State Hornets")` emits a bare `Alabama`, and
`"Florida A&M Rattlers"` a bare `Florida`, so short venue labels can match. A
label reading exactly `Alabama` — or a title "Will Alabama make …" — is then an
EQUAL span, which #7867's longer-cover rule never refuses, and it is the
Crimson Tide's place, not the Hornets'.

SPECIMEN (production, 2026-10-09 17:55–17:57Z, 390 x 844, issue #3667 comment
6091026276): `/events/15326607`, Florida A&M Rattlers @ Alabama State Hornets
(FCS). Bigger Picture served questions 58420064 ("Will Alabama make the 2027
College Football Playoff National Championship Game?") and 58420073 (the
Florida one), and championship-path cards "College Football Playoff 78%" on
the Hornets and "33%" on the Rattlers.

Rows below are labelled SPECIMEN (titles as served) or CONSTRUCTED. Roster
ids are constructed; the shape (name / location / alias) is ESPN's, which is
what `teams` stores (`espn_api.py` `location=team.get("location")`). The route
proof is `tests/integration/test_route_related_futures_fcs_place_3667.py`.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.routes.events import _team_name_patterns
from app.utils.team_label_identity import build_label_identity, label_names_another_club

NCAAF, NFL, FCS, MLB = 100, 101, 102, 200

FOOTBALL = [
    (10, NCAAF, "Alabama Crimson Tide", "ALA", "Alabama", ["Alabama"]),
    (11, NCAAF, "Florida Gators", "FLA", "Florida", ["Florida"]),
    (12, NCAAF, "Florida State Seminoles", "FSU", "Florida State", ["Florida St."]),
    (13, NCAAF, "South Carolina Gamecocks", "SC", "South Carolina", ["South Carolina"]),
    (14, NCAAF, "Miami Hurricanes", "MIA", "Miami (FL)", ["Miami (FL)"]),
    (15, NCAAF, "Saint Mary's Gaels", "SMC", "Saint Mary's", []),
    (16, NCAAF, "Ohio Bobcats", "OHIO", "Ohio", ["Ohio"]),
    (20, NFL, "Carolina Panthers", "CAR", "Carolina", ["Carolina", "Panthers"]),
    (21, NFL, "Miami Dolphins", "MIA", "Miami", ["Miami", "Dolphins"]),
    (30, FCS, "Alabama State Hornets", "ALST", "Alabama State", ["Alabama St"]),
    (31, FCS, "Florida A&M Rattlers", "FAMU", "Florida A&M", ["Florida A&M"]),
    (32, FCS, "South Carolina State Bulldogs", "SCST", "South Carolina State", []),
    (33, FCS, "Jackson State Tigers", "JKST", "Jackson State", []),
]

BASEBALL = [
    (40, MLB, "Chicago White Sox", "CHW", "Chicago", ["White Sox", "Chicago"]),
    (41, MLB, "Chicago Cubs", "CHC", "Chicago", ["Cubs", "Chicago"]),
    (42, MLB, "Texas Rangers", "TEX", "Texas", ["Rangers", "Texas"]),
    (43, MLB, "Texas Longhorns", "TEX", "Texas", ["Texas"]),  # CONSTRUCTED college row
]

ALABAMA_Q = "Will Alabama make the 2027 College Football Playoff National Championship Game?"
FLORIDA_Q = "Will Florida make the 2027 College Football Playoff National Championship Game?"


def _rows(table):
    return [
        {"id": i, "sport_id": s, "name": n, "abbreviation": a, "location": loc,
         "alternate_names": alts}
        for i, s, n, a, loc, alts in table
    ]


def _identity(table, own_ids, name):
    """The route builds one identity per side, from that side's one name."""
    return build_label_identity(_rows(table), own_team_ids=own_ids, own_team_names=(name,))


def _refused(label, name, own_ids, table=FOOTBALL):
    return label_names_another_club(
        label, _team_name_patterns(name), _identity(table, own_ids, name)
    )


# Both identity modes: the side resolved to its `teams` row, and #8920's
# name-only mode for a side the route resolved nothing for.
MODES = pytest.mark.parametrize("resolved", [True, False], ids=["resolved", "name-only"])


class TestTheSpecimenIsRefused:

    @MODES
    @pytest.mark.parametrize("label", [ALABAMA_Q, "Alabama"])
    def test_alabama_state_does_not_claim_alabama(self, label, resolved):
        assert _refused(label, "Alabama State Hornets", [30] if resolved else []) is True

    @MODES
    @pytest.mark.parametrize("label", [FLORIDA_Q, "Florida", "Florida St."])
    def test_florida_am_does_not_claim_florida_or_florida_state(self, label, resolved):
        assert _refused(label, "Florida A&M Rattlers", [31] if resolved else []) is True

    @MODES
    @pytest.mark.parametrize("label", ["Carolina", "South Carolina"])
    def test_south_carolina_state_does_not_claim_the_panthers_or_gamecocks(self, label, resolved):
        # #3667 comment 5562616182's earlier FCS specimen, the same cut.
        assert _refused(label, "South Carolina State Bulldogs", [32] if resolved else []) is True


class TestOurOwnPlaceIsKept:
    """Refusals-to-refuse: a wrong arm here empties a real card."""

    @MODES
    @pytest.mark.parametrize("label", [
        "Alabama St.",
        "Alabama State",
        "Alabama St. vs Jackson St.",
        "Jackson State vs Alabama State",
        "Alabama State Hornets",
        "Hornets",
    ])
    def test_alabama_state_keeps_its_own_labels(self, label, resolved):
        assert _refused(label, "Alabama State Hornets", [30] if resolved else []) is False

    @MODES
    @pytest.mark.parametrize("label", ["Florida A&M", "Florida A&M vs Jackson State", "Rattlers"])
    def test_florida_am_keeps_its_own_labels(self, label, resolved):
        assert _refused(label, "Florida A&M Rattlers", [31] if resolved else []) is False

    def test_south_carolina_state_keeps_its_abbreviated_place(self):
        # The Gamecocks' `South Carolina` covers `Carolina`, but the label goes
        # on to `St.` — our whole place. Refused before #3667 (a recall loss).
        assert _refused("South Carolina St.", "South Carolina State Bulldogs", [32]) is False

    @pytest.mark.parametrize("label", [ALABAMA_Q, "Alabama"])
    def test_on_alabamas_own_page_alabama_is_alabama(self, label):
        assert _refused(label, "Alabama Crimson Tide", [10]) is False

    @pytest.mark.parametrize("label", [FLORIDA_Q, "Florida"])
    def test_on_floridas_own_page_florida_is_florida(self, label):
        assert _refused(label, "Florida Gators", [11]) is False

    def test_a_bare_place_that_is_our_whole_place_is_never_cut(self):
        # `Miami` IS the Hurricanes' whole place (the Dolphins list it too).
        assert _refused("Miami", "Miami Hurricanes", [14]) is False

    def test_saint_reads_as_st(self):
        assert _refused("St. Mary's", "Saint Mary's Gaels", [15]) is False

    def test_a_city_shared_with_a_sibling_club_stays_when_it_is_ours_too(self):
        # `Chicago White` is the place half; `Chicago` alone is the Cubs' AND ours.
        assert _refused("Chicago", "Chicago White Sox", [40], BASEBALL) is False

    def test_a_one_word_place_is_unchanged(self):
        # `Texas` is the Rangers' whole place, though a college row lists it too.
        assert _refused("Texas", "Texas Rangers", [42], BASEBALL) is False


class TestTheRuleIsTheOneDoingIt:

    def test_without_own_places_the_specimen_was_admitted(self):
        """The BEFORE, kept so this file cannot pass on an unrelated refusal."""
        name = "Alabama State Hornets"
        ident = dataclasses.replace(_identity(FOOTBALL, [30], name), own_places=())
        assert label_names_another_club(ALABAMA_Q, _team_name_patterns(name), ident) is False

    def test_a_cut_nobody_foreign_claims_is_admitted(self):
        # Remove the Crimson Tide: `Alabama` is then unknown, never refused.
        table = [r for r in FOOTBALL if r[0] != 10]
        assert _refused(ALABAMA_Q, "Alabama State Hornets", [30], table) is False

    def test_a_cut_that_one_of_ours_also_claims_is_admitted(self):
        # If our own row lists `Alabama` too, the word is not foreign-only.
        table = [r if r[0] != 30 else (30, FCS, "Alabama State Hornets", "ALST",
                                       "Alabama State", ["Alabama St", "Alabama"])
                 for r in FOOTBALL]
        assert _refused(ALABAMA_Q, "Alabama State Hornets", [30], table) is False
