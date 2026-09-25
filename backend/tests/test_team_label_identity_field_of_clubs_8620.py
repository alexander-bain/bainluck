"""#8620 — `label_is_another_club`: an answer that IS another known club.

The route-level proof is
`tests/integration/test_route_related_futures_field_of_clubs_8620.py`; this pins
the predicate. Production ids where the read-only db-query gave them (FC Porto
2175, Sporting Lisbon 2172, Portugal 17792, Wales 17793), constructed otherwise.
"""

from __future__ import annotations

from app.utils.team_label_identity import build_label_identity, label_is_another_club

NATIONS, PRIMEIRA, NCAAF, NFL = 1, 2, 3, 4

ROWS = [
    {"id": 17792, "sport_id": NATIONS, "name": "Portugal", "abbreviation": "POR", "location": "Portugal", "alternate_names": None},
    {"id": 17793, "sport_id": NATIONS, "name": "Wales", "abbreviation": "WAL", "location": "Wales", "alternate_names": None},
    {"id": 2175, "sport_id": PRIMEIRA, "name": "FC Porto", "abbreviation": "POR", "location": None, "alternate_names": None},
    {"id": 2172, "sport_id": PRIMEIRA, "name": "Sporting Lisbon", "abbreviation": "SCP", "location": None, "alternate_names": ["Sporting CP"]},
    {"id": 900, "sport_id": NCAAF, "name": "Jackson State Tigers", "abbreviation": "JKST", "location": "Jackson", "alternate_names": None},
    {"id": 901, "sport_id": NCAAF, "name": "Lamar Cardinals", "abbreviation": "LAM", "location": "Lamar", "alternate_names": None},
]


def _sides(home=17792, away=17793):
    return (
        build_label_identity(ROWS, own_team_ids=[home], own_team_names=["Portugal"]),
        build_label_identity(ROWS, own_team_ids=[away] if away else [], own_team_names=["Wales"]),
    )


def test_a_foreign_club_by_name_or_alias_is_another_club():
    ids = _sides()
    assert label_is_another_club("FC Porto", ids)
    assert label_is_another_club("  sporting lisbon ", ids)
    assert label_is_another_club("Sporting CP", ids)


def test_either_side_of_this_game_is_never_another_club():
    ids = _sides()
    assert not label_is_another_club("Portugal", ids)
    assert not label_is_another_club("Wales", ids)


def test_an_unknown_answer_is_not_evidence():
    ids = _sides()
    for label in ("Estrela Amadora", "Draw", "Yes", "Round of 16", "Over 2.5", ""):
        assert not label_is_another_club(label, ids), label


def test_a_token_inside_the_label_never_counts_only_the_whole_label():
    ids = _sides()
    assert not label_is_another_club("FC Porto B", ids)
    assert not label_is_another_club("Lamar Jackson: 50+", ids)


def test_disarmed_without_a_resolved_side():
    none_resolved = (
        build_label_identity(ROWS, own_team_ids=[], own_team_names=["Portugal"]),
        build_label_identity(ROWS, own_team_ids=[], own_team_names=["Wales"]),
    )
    assert not label_is_another_club("FC Porto", none_resolved)
    assert not label_is_another_club("FC Porto", (None, None))


def test_one_resolved_side_is_enough_to_arm():
    home_only = _sides(away=None)
    assert label_is_another_club("FC Porto", home_only)
