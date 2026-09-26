"""#8920 — a side the route resolved no id for still refuses another club's name.

`/events/15317759` (Harvard 14 @ Brown 10, FCS, final, production 2026-09-26):
no `teams` row named `Brown Bears` exists in any `americanfootball%` sport, so
`build_label_identity(own_team_ids=∅)` returned an unarmed identity and Brown's
Bigger Picture drew the Chicago Bears' Super Bowl and NFC legs (outcomes
1309498, 1709113, 1709765) plus Baylor / California Golden / Missouri State
Bears. The rows below are production's (read-only db-query 2026-09-26) except
the 9xxxxx ids, which are constructed.
"""

from __future__ import annotations

import pytest

from app.routes.events import _team_name_patterns
from app.utils.team_label_identity import (
    build_label_identity,
    label_is_another_club,
    label_names_another_club,
    label_qualifies_a_shared_mascot,
)

NCAAF, FCS, NFL = 100, 101, 102

# (id, sport_id, name, abbreviation, location, alternate_names)
FOOTBALL = [
    (8, NCAAF, "Baylor Bears", "BAY", "Baylor", ["Baylor", "Bears"]),
    (81, NCAAF, "California Golden Bears", "CAL", "California", ["California", "Golden Bears"]),
    (561, NFL, "Chicago Bears", "CHI", "Chicago", ["Bears"]),
    (562, NFL, "Cleveland Browns", "CLE", "Cleveland", ["Browns"]),
    (15350, NCAAF, "Missouri State Bears", "MOST", "Missouri State", ["Missouri St", "Bears"]),
    (18635, FCS, "Northern Colorado Bears", "UNCO", "Northern Colorado", ["N Colorado", "Bears"]),
    (19284, FCS, "Harvard Crimson", None, None, None),
    (900001, NCAAF, "Miami (FL) Hurricanes", "MIA", "Miami", ["Hurricanes"]),
    (900002, NCAAF, "Miami (OH) RedHawks", "M-OH", "Miami (OH)", ["RedHawks"]),
]


def _rows(table=FOOTBALL):
    return [
        {"id": i, "sport_id": s, "name": n, "abbreviation": a,
         "location": loc, "alternate_names": alts}
        for i, s, n, a, loc, alts in table
    ]


def _unresolved(team, table=FOOTBALL):
    """The route's call for a side with no resolved id: patterns from the
    event name only, `own_team_ids` empty."""
    ident = build_label_identity(_rows(table), own_team_ids=[], own_team_names=(team,))
    return _team_name_patterns(team), ident


def _refused(label, team, table=FOOTBALL):
    pats, ident = _unresolved(team, table)
    return label_names_another_club(label, pats, ident)


class TestTheSpecimen:

    @pytest.mark.parametrize("label", [
        "Chicago Bears",             # 1309498 / 1709113 / 1709765 — NFL title, NFC
        "Baylor Bears",              # 34312763 — NCAAF title
        "California Golden Bears",   # 34312778
        "Missouri State Bears",      # 34312861
        "Northern Colorado Bears",   # an FCS rival in the same league
    ])
    def test_brown_does_not_claim_another_bears_club(self, label):
        assert _refused(label, "Brown Bears") is True

    def test_before_the_fix_nothing_could_refuse(self):
        # The unresolved identity is not ARMED — the resolved-side rules
        # (#7867 armed path, #8620, #8896) stay exactly as disarmed as before.
        pats, ident = _unresolved("Brown Bears")
        assert ident.is_armed() is False
        assert ident.is_name_armed() is True
        assert label_qualifies_a_shared_mascot("Chicago Bears", pats, ident) is False
        assert label_is_another_club("Chicago Bears", (ident,)) is False


class TestRefusalsToRefuse:

    @pytest.mark.parametrize("label", [
        "Brown",                     # 225952161 — Kalshi FCS title, Brown's own
        "Brown Bears",
        "Bears",                     # bare mascot: unknown, not contradictory
        "Brown vs Harvard",
        "Chicago Bears vs Brown",    # an occurrence of ours is uncovered
        "Chris Brown",               # a person is not in `teams` — unknown
    ])
    def test_brown_keeps_labels_that_are_not_a_known_foreign_club(self, label):
        assert _refused(label, "Brown Bears") is False

    def test_a_longer_row_extending_our_name_counts_as_ours(self):
        # Event `Brown`, family row `Brown Bears`: that row may be this very
        # club, so it never covers our token as a foreign name.
        table = FOOTBALL + [(900003, NCAAF, "Brown Bears", "BRWN", "Brown", ["Brown"])]
        assert _refused("Brown Bears", "Brown", table) is False

    def test_a_covering_name_that_shares_a_word_of_ours_is_not_foreign(self):
        # Our Hurricanes under a longer family name: `Miami` is ours.
        assert _refused("Miami (FL) Hurricanes", "Miami Hurricanes") is False

    def test_a_covering_name_adding_only_foreign_words_still_refuses(self):
        # `Miami` sits inside `Miami (OH)`, which adds only `OH` — the
        # RedHawks, refused exactly as #7867 refuses them for a resolved side.
        assert _refused("Miami (OH) RedHawks", "Miami Hurricanes") is True
        assert _refused("Ball St. vs Miami (OH)", "Miami Hurricanes") is True

    def test_initials_of_our_name_are_ours(self):
        table = FOOTBALL + [(900004, NFL, "BB Bears", None, None, None)]
        assert _refused("BB Bears", "Brown Bears", table) is False

    def test_no_event_name_stays_disarmed(self):
        ident = build_label_identity(_rows(), own_team_ids=[], own_team_names=[])
        assert ident.is_name_armed() is False
        assert label_names_another_club("Chicago Bears", ["Bears"], ident) is False


class TestTheResolvedSideIsUnchanged:

    def test_resolved_identity_is_not_name_mode(self):
        ident = build_label_identity(_rows(), own_team_ids=[19284], own_team_names=("Harvard Crimson",))
        assert ident.is_armed() is True
        assert ident.is_name_armed() is False
