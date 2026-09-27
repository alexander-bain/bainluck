"""#8950 — the name-only identity (#8920) now also runs on events where NEITHER
side resolved, and two kinds of row count as possibly-ours there.

Measured by replaying the rule over 100 production events with both team ids
NULL (2026-09-27 03:3xZ, `artifacts/8950/replay*.txt`): the first pass refused
the right club on NHL preseason rows stored under the bare mascot (`Blues` v
`Stars`, `icehockey_other`) and `South Korea` on `Korea Republic`. Those are
the rows below; every other refusal of that pass (Aston Villa on Hanworth
Villa, Union Berlin on Fath Union Sport, Orlando Magic on Shimane Susanoo
Magic, Czech Republic on Korea Republic, ...) still refuses. Team rows are
production's (read-only db-query 2026-09-27).
"""

from __future__ import annotations

from app.routes.events import _team_name_patterns
from app.utils.team_label_identity import build_label_identity, label_names_another_club

NHL, AHL, PRE, WC, MLS, CHI = 1, 2, 3, 4, 5, 6

ROWS = [
    (116, NHL, "Dallas Stars", "DAL", "Dallas", ["Stars"]),
    (1337, AHL, "Texas Stars", None, None, None),
    (571, NHL, "St. Louis Blues", "STL", "St. Louis", ["Blues"]),
    (19702, PRE, "St Louis Blues", None, None, None),
    (12901, WC, "South Korea", None, None, None),
    (20, MLS, "New England Revolution", "NE", "New England Revolution",
     ["revs", "New England", "New England Revolution"]),
    (1908, WC, "England", None, None, None),
    (866, WC, "Czech Republic", None, None, None),
    (77, CHI, "Universidad de Chile", None, None, None),
]


def _identity(name):
    rows = [
        {"id": i, "sport_id": s, "name": n, "abbreviation": a, "location": loc,
         "alternate_names": alts}
        for i, s, n, a, loc, alts in ROWS
    ]
    return build_label_identity(rows, own_team_ids=(), own_team_names=(name,))


def _refused(label, name):
    return label_names_another_club(label, _team_name_patterns(name), _identity(name))


def test_a_bare_mascot_keeps_the_clubs_whose_names_end_with_it():
    assert not _refused("Dallas Stars", "Stars")
    assert not _refused("St. Louis Blues", "Blues")
    assert not _refused("Texas Stars", "Stars")      # ambiguous: unknown, never refused


def test_the_same_nation_under_another_spelling_is_ours():
    assert not _refused("South Korea", "Korea Republic")
    assert _refused("Czech Republic", "Korea Republic")


def test_england_still_refuses_new_england():
    assert _refused("New England Revolution", "England")
    assert _refused("New England", "England")
    assert not _refused("England", "England")


def test_a_name_ending_with_ours_is_unknown_not_refused():
    """The named cost of the suffix clause: `Chile` keeps `Universidad de
    Chile`, as it did before #8950 — unknown, not contradictory."""
    assert not _refused("Universidad de Chile", "Chile")
