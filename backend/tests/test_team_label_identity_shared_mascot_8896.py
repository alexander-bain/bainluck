"""#8896 — a mascot two clubs share, qualified by a word that is not ours.

The pure rule, `label_qualifies_a_shared_mascot`. Production rows (read-only
db-query 2026-09-26): UNLV Rebels 15359 alts ['UNLV', 'Rebels']; Ole Miss
Rebels 83 alts ['Rebels', 'Ole Miss']; outcome 55309441 `Mississippi Rebels`
(market 9962834, `NCAA Football: 2027 National Champion`, Polymarket) with
`team_id NULL`. Ottawa/Dallas/Belleville rows are shaped like production's and
carry constructed ids (9xxxxx). The route-level proof is
`tests/integration/test_route_related_futures_shared_mascot_8896.py`.
"""

from __future__ import annotations

import pytest

from app.routes.events import _escape_like, _team_name_patterns
from app.utils.team_label_identity import (
    build_label_identity,
    label_names_another_club,
    label_qualifies_a_shared_mascot,
)

NCAAF, FCS, NFL = 100, 101, 102
NHL, AHL = 300, 301

# (id, sport_id, name, abbreviation, location, alternate_names)
FOOTBALL = [
    (15359, NCAAF, "UNLV Rebels", "UNLV", "UNLV", ["UNLV", "Rebels"]),               # production
    (83, NCAAF, "Ole Miss Rebels", "MISS", "Ole Miss", ["Rebels", "Ole Miss"]),      # production
    (15360, NCAAF, "Mississippi State Bulldogs", "MSST", "Mississippi State",
     ["Mississippi St", "Bulldogs"]),                                                # production
    (900001, NCAAF, "Akron Zips", "AKR", "Akron", ["Akron", "Zips"]),
    (900002, NCAAF, "Clemson Tigers", "CLEM", "Clemson", ["Clemson", "Tigers"]),
    (9, NCAAF, "LSU Tigers", "LSU", "LSU", ["LSU", "Tigers"]),                        # production id
    (900003, NCAAF, "Pittsburgh Panthers", "PITT", "Pittsburgh", ["Pittsburgh", "Panthers"]),
    (900004, NCAAF, "Georgia State Panthers", "GAST", "Georgia State", ["Georgia State"]),
    (900005, NFL, "Carolina Panthers", "CAR", "Carolina", ["Carolina", "Panthers"]),
]

HOCKEY = [
    (900010, NHL, "Ottawa Senators", "OTT", "Ottawa", ["Senators", "Ottawa"]),
    (900011, NHL, "Dallas Stars", "DAL", "Dallas", ["Stars", "Dallas"]),
    (900012, AHL, "Belleville Senators", None, None, None),
    (900013, AHL, "Texas Stars", None, None, None),
]


def _rows(table):
    return [
        {"id": i, "sport_id": s, "name": n, "abbreviation": a,
         "location": loc, "alternate_names": alts}
        for i, s, n, a, loc, alts in table
    ]


def _claim(team, table):
    """The route's claim patterns: `_team_name_patterns` + escaped alts."""
    row = next(r for r in table if r[2] == team)
    pats = _team_name_patterns(team)
    for alt in row[5] or []:
        if _escape_like(alt).lower() not in [p.lower() for p in pats]:
            pats.append(_escape_like(alt))
    ident = build_label_identity(_rows(table), own_team_ids=[row[0]], own_team_names=(team,))
    return pats, ident


def _refused(label, team, table):
    pats, ident = _claim(team, table)
    return label_qualifies_a_shared_mascot(label, pats, ident)


class TestTheSpecimen:

    def test_unlv_does_not_claim_mississippi_rebels(self):
        assert _refused("Mississippi Rebels", "UNLV Rebels", FOOTBALL) is True

    def test_the_old_rule_admitted_it(self):
        # #7867 cannot see it: no `teams` row carries `Mississippi Rebels`.
        pats, ident = _claim("UNLV Rebels", FOOTBALL)
        assert label_names_another_club("Mississippi Rebels", pats, ident) is False

    def test_ole_miss_keeps_mississippi_rebels(self):
        # `Mississippi` clips to `Miss`, a word of `Ole Miss`.
        assert _refused("Mississippi Rebels", "Ole Miss Rebels", FOOTBALL) is False


class TestRefusalsToRefuse:

    @pytest.mark.parametrize("label", [
        "UNLV Rebels",   # the full name — not shared
        "UNLV",          # a name of ours alone
        "Rebels",        # bare mascot, no qualifier: unknown, not contradictory
        "The Rebels",    # connector word
        "Rebels vs Akron Zips",
        "UNLV vs Rebels",
    ])
    def test_unlv_keeps_its_own_labels(self, label):
        assert _refused(label, "UNLV Rebels", FOOTBALL) is False

    def test_pitt_is_a_clip_of_pittsburgh(self):
        assert _refused("Pitt Panthers", "Pittsburgh Panthers", FOOTBALL) is False

    @pytest.mark.parametrize("team", ["Ottawa Senators", "Dallas Stars"])
    def test_an_abbreviation_qualifier_is_ours(self, team):
        assert _refused("OTT Senators vs DAL Stars", team, HOCKEY) is False

    def test_a_mascot_no_foreign_club_carries_never_refuses(self):
        assert _refused("Blue Zips", "Akron Zips", FOOTBALL) is False

    def test_disarmed_when_nothing_resolved(self):
        pats = _team_name_patterns("UNLV Rebels")
        ident = build_label_identity(_rows(FOOTBALL), own_team_ids=[], own_team_names=("UNLV Rebels",))
        assert label_qualifies_a_shared_mascot("Mississippi Rebels", pats, ident) is False


class TestTheClass:

    @pytest.mark.parametrize("label,team", [
        ("Georgia State Panthers", "Pittsburgh Panthers"),  # also #7867's (known name)
        ("Florida Panthers", "Pittsburgh Panthers"),        # unknown school, shared mascot
        ("Missouri Tigers", "Clemson Tigers"),
        ("Wests Tigers", "Clemson Tigers"),                 # production label (rugby league)
    ])
    def test_another_schools_qualified_mascot_is_refused(self, label, team):
        assert _refused(label, team, FOOTBALL) is True

    def test_an_occurrence_that_is_ours_admits_the_row(self):
        # `Pittsburgh` is a name of ours; the row is admitted as today.
        assert _refused("Pittsburgh vs Florida Panthers", "Pittsburgh Panthers", FOOTBALL) is False
