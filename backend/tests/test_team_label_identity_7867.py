"""#7867 — the pure rule: a token that is part of another known club's name.

Every row below is either a production specimen from issue #7867 (ids as
production carries them, read 2026-09-23 through `/api/events/search` and the
served `/related-futures` payloads) or a CONSTRUCTED control, and each is
labelled which. The route-level proof is
`tests/integration/test_route_related_futures_team_paths_7867.py`; this file
pins the predicate so a later edit to the route cannot move the line without
a test naming it.
"""

from __future__ import annotations

import pytest

from app.routes.events import _team_name_patterns
from app.utils.team_label_identity import (
    LabelIdentity,
    build_label_identity,
    label_names_another_club,
)
from app.utils.team_pattern_match import pattern_token_spans

# ── the family rosters ──────────────────────────────────────────────────────
# (id, sport_id, name, abbreviation, location, alternate_names)
NCAAF, NFL, FCS = 100, 101, 102
MLB, NPB, KBO = 200, 201, 202
NHL, AHL = 300, 301
WNBA, NBA = 400, 401

FOOTBALL = [
    (15311, NCAAF, "Duke Blue Devils", "DUKE", "Duke", ["Duke", "Blue Devils"]),  # production id
    (900001, NCAAF, "Stanford Cardinal", "STAN", "Stanford", ["Stanford"]),      # constructed id
    (900002, NCAAF, "Miami Hurricanes", "MIA", "Miami (FL)", ["Miami (FL)", "Hurricanes"]),
    (15332, NCAAF, "Miami (OH) RedHawks", "M-OH", "Miami (OH)", ["Miami (OH)"]),  # production
    (900003, NCAAF, "Arizona State Sun Devils", "ASU", "Arizona State", ["Sun Devils"]),
    (900004, NCAAF, "Middle Tennessee Blue Raiders", "MTSU", "Middle Tennessee", []),
    (900005, NCAAF, "Delaware Blue Hens", "DEL", "Delaware", []),
    (900006, NCAAF, "Coastal Carolina Chanticleers", "CCU", "Coastal Carolina", ["Coastal Carolina"]),
    (15295, NCAAF, "South Carolina Gamecocks", "SC", "South Carolina", ["South Carolina"]),  # production
    (900007, NCAAF, "North Carolina Tar Heels", "UNC", "North Carolina", ["North Carolina"]),
    (900008, NCAAF, "North Carolina State Wolfpack", "NCSU", "North Carolina St.", ["North Carolina St."]),
    (900009, NCAAF, "East Carolina Pirates", "ECU", "East Carolina", ["East Carolina"]),
    (900010, NCAAF, "Penn State Nittany Lions", "PSU", "Penn State", ["Penn State"]),
    (15299, NCAAF, "Ball State Cardinals", "BALL", "Ball St.", ["Ball St."]),  # production
    (900011, FCS, "Columbia Lions", "COLU", "Columbia", ["Columbia"]),
    (565, NFL, "Miami Dolphins", "MIA", "Miami", ["Miami", "Dolphins"]),        # production
    (11, NFL, "New England Patriots", "NE", "New England", ["New England", "Patriots"]),
    (540, NFL, "Pittsburgh Steelers", "PIT", "Pittsburgh", ["Pittsburgh", "Steelers"]),
    (567, NFL, "Detroit Lions", "DET", "Detroit", ["Detroit", "Lions"]),         # production
]

BASEBALL = [
    (6609, MLB, "San Francisco Giants", "SF", "San Francisco", ["Giants", "San Francisco"]),
    (10739, MLB, "Minnesota Twins", "MIN", "Minnesota", ["Twins", "Minnesota"]),
    (10747, MLB, "Detroit Tigers", "DET", "Detroit", ["Tigers", "Detroit"]),
    (12494, NPB, "Yomiuri Giants", None, None, None),      # production, bare row
    (12483, NPB, "Hanshin Tigers", None, None, None),
    (12796, KBO, "Lotte Giants", None, None, None),
    (12794, KBO, "LG Twins", None, None, None),
]

HOCKEY = [
    (54, NHL, "New York Islanders", "NYI", "New York", ["Islanders", "New York"]),
    (6181, NHL, "New York I", "NYI", None, None),          # production twin
    (12716, NHL, "New Jersey", "NYI", None, None),         # production twin (sic)
    (57, NHL, "New York Rangers", "NYR", "New York", ["Rangers", "New York"]),
    (8293, NHL, "New York R", "NYR", None, None),          # production twin
    (1347, AHL, "Bridgeport Islanders", None, None, None), # production
]

BASKETBALL = [
    (13923, WNBA, "Minnesota Lynx", "MIN", "Minnesota", ["Lynx", "Minnesota"]),
    (13414, WNBA, "New York Liberty", "NY", "New York", ["Liberty", "New York"]),
    (106, NBA, "Minnesota Timberwolves", "MIN", "Minnesota", ["Timberwolves", "Minnesota"]),
    (108, NBA, "New York Knicks", "NY", "New York", ["Knicks", "New York"]),
]


def _rows(table):
    return [
        {
            "id": i, "sport_id": s, "name": n, "abbreviation": a,
            "location": loc, "alternate_names": alts,
        }
        for i, s, n, a, loc, alts in table
    ]


def _identity(table, own_ids, own_names):
    return build_label_identity(_rows(table), own_team_ids=own_ids, own_team_names=own_names)


def _names_other(label, team_names, identity):
    patterns = []
    for t in team_names:
        patterns += _team_name_patterns(t)
    return label_names_another_club(label, patterns, identity)


# ── spans helper ─────────────────────────────────────────────────────────────

class TestPatternTokenSpans:

    def test_every_whole_token_occurrence_in_order(self):
        assert pattern_token_spans("Duke vs Duke Tobin", "Duke") == [(0, 4), (8, 12)]

    def test_interior_and_prefix_are_refused_as_before(self):
        assert pattern_token_spans("Anderlecht", "Lech") == []
        assert pattern_token_spans("Lechia Gdansk", "Lech") == []

    def test_escaped_pattern_reads_back(self):
        assert pattern_token_spans("100% Club", "100\\% Club") == [(0, 9)]


# ── the named failures, one per line ────────────────────────────────────────

class TestNamedFailuresAreRefused:
    """Each subject row from #7867 and its comments, against the family roster."""

    @pytest.mark.parametrize("label", [
        "Arizona State Sun Devils",        # `Devils`
        "Middle Tennessee Blue Raiders",   # `Blue`
        "Delaware Blue Hens",              # `Blue`
    ])
    def test_duke_does_not_claim_another_schools_title_row(self, label):
        ident = _identity(FOOTBALL, [15311, 900001], ["Duke Blue Devils", "Stanford Cardinal"])
        assert _names_other(label, ["Duke Blue Devils"], ident) is True

    @pytest.mark.parametrize("label", [
        "Ball St. vs Miami (OH)",
        "Miami (OH) vs Toledo",
        "Will Miami (OH) Make the 2027 College Football Playoff National Championship Game?",
    ])
    def test_the_hurricanes_do_not_claim_the_redhawks(self, label):
        ident = _identity(FOOTBALL, [900002], ["Miami Hurricanes", "Wake Forest Demon Deacons"])
        assert _names_other(label, ["Miami Hurricanes"], ident) is True

    @pytest.mark.parametrize("label", [
        "South Carolina",
        "Alabama vs South Carolina",
        "North Carolina St. vs Pittsburgh",
        "East Carolina vs Navy",
        "Boston College vs North Carolina",
    ])
    def test_coastal_carolina_does_not_claim_the_other_carolinas(self, label):
        ident = _identity(FOOTBALL, [900006], ["Coastal Carolina Chanticleers", "Liberty Flames"])
        assert _names_other(label, ["Coastal Carolina Chanticleers"], ident) is True

    def test_columbia_does_not_claim_penn_state_or_the_nfl_lions(self):
        ident = _identity(FOOTBALL, [900011], ["Columbia Lions", "Lafayette Leopards"])
        assert _names_other("Penn State Nittany Lions", ["Columbia Lions"], ident) is True
        assert _names_other("Detroit Lions", ["Columbia Lions"], ident) is True

    @pytest.mark.parametrize("label,team", [
        ("Yomiuri Giants", "San Francisco Giants"),
        ("Lotte Giants", "San Francisco Giants"),
        ("LG Twins", "Minnesota Twins"),
        ("Hanshin Tigers", "Detroit Tigers"),
    ])
    def test_an_mlb_club_does_not_claim_a_foreign_leagues_club(self, label, team):
        ident = _identity(BASEBALL, [6609, 10739, 10747], [team, "Washington Nationals"])
        assert _names_other(label, [team], ident) is True

    @pytest.mark.parametrize("label", [
        "Bridgeport Islanders",       # AHL
        "New York Rangers",           # exact sibling
        "New York R and Colorado",    # the Rangers' truncated twin
    ])
    def test_the_islanders_do_not_claim_the_rangers_or_bridgeport(self, label):
        ident = _identity(HOCKEY, [54], ["New York Islanders", "New Jersey Devils"])
        assert _names_other(label, ["New York Islanders"], ident) is True

    def test_the_lynx_and_liberty_do_not_claim_their_nba_counterparts(self):
        ident = _identity(BASKETBALL, [13923, 13414], ["Minnesota Lynx", "New York Liberty"])
        assert _names_other("Minnesota Timberwolves", ["Minnesota Lynx"], ident) is True
        assert _names_other("New York Knicks", ["New York Liberty"], ident) is True


# ── the controls: what the rejected rule lost, and what this one must keep ──

class TestLegitimateRowsAreKept:

    def test_miami_fl_is_the_hurricanes(self):
        """The row the rejected all-token rule lost (190/841)."""
        ident = _identity(FOOTBALL, [900002], ["Miami Hurricanes", "Wake Forest Demon Deacons"])
        for label in ("Miami (FL)", "Miami (FL) vs Stanford", "Duke vs Miami (FL)",
                      "Will Miami (FL) Make the 2026-27 CFB Playoffs?", "Miami Hurricanes"):
            assert _names_other(label, ["Miami Hurricanes"], ident) is False, label

    def test_a_bare_venue_label_that_is_only_a_sibling_leagues_alias_is_kept(self):
        """`Miami` alone: the Dolphins list it, the Hurricanes' row does not.

        An equal-span rule would refuse the venue's own bare label for the
        Hurricanes here. Only a STRICTLY longer name refuses.
        """
        ident = _identity(FOOTBALL, [900002], ["Miami Hurricanes", "Wake Forest Demon Deacons"])
        assert _names_other("Miami", ["Miami Hurricanes"], ident) is False

    @pytest.mark.parametrize("label,team", [
        ("NE Patriots D/ST: 1+", "New England Patriots"),
        ("PIT Steelers D/ST: 1+", "Pittsburgh Steelers"),
        ("New England", "New England Patriots"),
        ("Pittsburgh", "Pittsburgh Steelers"),
        ("Pittsburgh vs Carolina", "Pittsburgh Steelers"),
    ])
    def test_abbreviated_defensive_props_and_short_labels_are_kept(self, label, team):
        ident = _identity(FOOTBALL, [11, 540], ["New England Patriots", "Pittsburgh Steelers"])
        assert _names_other(label, [team], ident) is False

    def test_coastal_carolinas_own_rows_are_kept(self):
        ident = _identity(FOOTBALL, [900006], ["Coastal Carolina Chanticleers", "Liberty Flames"])
        for label in ("Coastal Carolina", "Coastal Carolina Chanticleers",
                      "Coastal Carolina vs Troy", "Coastal Carolina O/U 23.5"):
            assert _names_other(label, ["Coastal Carolina Chanticleers"], ident) is False, label

    def test_a_person_is_the_named_limitation_and_is_not_refused(self):
        """`Duke Tobin` is not in `teams`; an identity that cannot be
        established is never refused. Recorded, not fixed."""
        ident = _identity(FOOTBALL, [15311, 900001], ["Duke Blue Devils", "Stanford Cardinal"])
        assert _names_other("Duke Tobin", ["Duke Blue Devils"], ident) is False
        assert _names_other("Vaughn Blue", ["Duke Blue Devils"], ident) is False

    def test_the_mlb_clubs_own_rows_are_kept(self):
        ident = _identity(BASEBALL, [6609, 10739], ["San Francisco Giants", "Minnesota Twins"])
        for label, team in (("San Francisco Giants", "San Francisco Giants"),
                            ("Minnesota", "Minnesota Twins"),
                            ("Minnesota vs San Francisco", "Minnesota Twins"),
                            ("Detroit vs San Francisco", "San Francisco Giants")):
            assert _names_other(label, [team], ident) is False, label

    def test_the_islanders_own_rows_are_kept(self):
        ident = _identity(HOCKEY, [54], ["New York Islanders", "New Jersey Devils"])
        for label in ("New York Islanders", "NYI Islanders vs ANA Ducks", "New York I vs Boston"):
            assert _names_other(label, ["New York Islanders"], ident) is False, label

    def test_the_lynxs_bare_state_label_is_kept(self):
        """`Minnesota` alone: both the Lynx and the Wolves list it, so the
        claim set intersects ours and nothing is refused."""
        ident = _identity(BASKETBALL, [13923, 13414], ["Minnesota Lynx", "New York Liberty"])
        assert _names_other("Minnesota", ["Minnesota Lynx"], ident) is False
        assert _names_other("Minnesota Lynx", ["Minnesota Lynx"], ident) is False


# ── twins, same-name-across-leagues, ambiguity, disarmed ────────────────────

class TestOwnIsWiderThanTwoIds:

    def test_a_same_league_abbreviation_twin_is_ours(self):
        """On the RANGERS' page, `New York R and Colorado` is theirs, because the
        `New York R` row shares `NYR` with the Rangers in the same league."""
        ident = _identity(HOCKEY, [57], ["New York Rangers", "Colorado Avalanche"])
        assert 8293 in ident.own
        assert _names_other("New York R and Colorado", ["New York Rangers"], ident) is False

    def test_a_cross_league_abbreviation_sibling_is_not_ours(self):
        """`MIN` is the Lynx in the WNBA and the Timberwolves in the NBA."""
        ident = _identity(BASKETBALL, [13923], ["Minnesota Lynx", "New York Liberty"])
        assert 106 not in ident.own

    def test_the_same_name_in_another_league_is_ours(self):
        """CONSTRUCTED: one school with a men's and a women's row. The women's
        row has the lower id, and the event resolved only the men's."""
        rows = [
            (700, 401, "Connecticut Huskies", "CONN", "Connecticut", ["UConn"]),   # women's, lower id
            (701, 400, "Connecticut Huskies", "CONN", "Connecticut", ["UConn"]),   # men's, resolved
            (702, 401, "Central Connecticut St.", "CCSU", "Central Connecticut", []),
        ]
        ident = _identity(rows, [701], ["Connecticut Huskies", "Duke Blue Devils"])
        assert {700, 701} <= ident.own
        assert _names_other("UConn vs Duke", ["Connecticut Huskies"], ident) is False
        assert _names_other("Central Connecticut St.", ["Connecticut Huskies"], ident) is True

    def test_an_alias_shared_by_two_foreign_clubs_still_refuses(self):
        """CONSTRUCTED: `North Carolina` listed by UNC and NC State. Which of
        them does not matter; neither is ours."""
        rows = list(FOOTBALL) + [
            (900012, NCAAF, "NC State Wolfpack (dup)", "NCST", "North Carolina", ["North Carolina"]),
        ]
        ident = _identity(rows, [900006], ["Coastal Carolina Chanticleers", "Liberty Flames"])
        assert _names_other("North Carolina", ["Coastal Carolina Chanticleers"], ident) is True

    def test_an_alias_any_of_ours_claims_never_refuses(self):
        """CONSTRUCTED: a foreign row listing OUR full name as its alias. The
        claim set intersects ours, so the label is not refused."""
        rows = list(FOOTBALL) + [
            (900013, NCAAF, "Junk Row", "JUNK", None, ["Duke Blue Devils"]),
        ]
        ident = _identity(rows, [15311], ["Duke Blue Devils", "Stanford Cardinal"])
        assert _names_other("Duke Blue Devils", ["Duke Blue Devils"], ident) is False


class TestDisarmed:

    def test_no_identity_no_refusal(self):
        assert label_names_another_club("Yomiuri Giants", ["Giants"], None) is False

    def test_no_own_ids_no_refusal(self):
        """Unknown league metadata: the event's teams did not resolve."""
        ident = build_label_identity(_rows(BASEBALL), own_team_ids=[], own_team_names=[])
        assert ident.is_armed() is False
        assert label_names_another_club("Yomiuri Giants", ["Giants"], ident) is False

    def test_no_occurrence_no_refusal(self):
        ident = _identity(BASEBALL, [6609], ["San Francisco Giants", "Minnesota Twins"])
        assert label_names_another_club("Over 8.5", ["Giants"], ident) is False

    def test_empty_label(self):
        ident = _identity(BASEBALL, [6609], ["San Francisco Giants", "Minnesota Twins"])
        assert label_names_another_club("", ["Giants"], ident) is False
        assert label_names_another_club(None, ["Giants"], ident) is False

    def test_a_bare_frozen_identity_is_honest_about_arming(self):
        assert LabelIdentity(claims={}, own=frozenset({1})).is_armed() is False
