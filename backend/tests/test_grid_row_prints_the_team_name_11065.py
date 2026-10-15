"""#11065 — a playoff-grid row prints the team's name, not the venue's city label.

WHAT A READER SAW, production, 390px, 2026-10-15 (shopper pass 0433,
`/playoffs/wnba`): eleven rows read "Golden State Valkyries", "Las Vegas Aces",
"Seattle Storm"… and rows 5-6 read **"Dallas"** and **"Indiana"**.

`GET /api/playoffs/wnba` served `name: "Dallas"` beside `team_id: 13389`,
`short_name: "DAL"` and the Wings' crest. The row label came from the first
outcome the builder met — Kalshi's `Playoff Qualifiers` market 12232390 spells
those two clubs by city — and was never replaced by the resolved team's name,
although the metadata beside it had already resolved `teams` 13389
"Dallas Wings" / 13388 "Indiana Fever".
"""

import inspect

from app.routes import playoffs
from app.routes.playoffs import _grid_row_display_name


def _meta(team_id, name):
    return {"team_id": team_id, "name": name, "short_name": None}


def test_the_production_specimens_print_the_team_name():
    assert _grid_row_display_name("Dallas", _meta(13389, "Dallas Wings")) == "Dallas Wings"
    assert _grid_row_display_name("Indiana", _meta(13388, "Indiana Fever")) == "Indiana Fever"


def test_a_row_already_printing_the_team_name_is_unchanged():
    """The eleven rows the reader had no complaint about."""
    assert _grid_row_display_name(
        "Golden State Valkyries", _meta(13416, "Golden State Valkyries")
    ) == "Golden State Valkyries"


def test_a_label_spelled_differently_keeps_the_venue_spelling():
    """Ours is `St.Louis Cardinals`; the venue writes `St. Louis Cardinals`.

    The label is already the full name, so swapping it would print OUR typo in
    place of the correct spelling. Only a whole-word prefix — a city label — is
    replaced.
    """
    assert _grid_row_display_name(
        "St. Louis Cardinals", _meta(10739, "St.Louis Cardinals")
    ) == "St. Louis Cardinals"


def test_a_partial_word_is_not_a_prefix():
    """`Indiana` must not become `Indianapolis Colts`."""
    assert _grid_row_display_name("Indiana", _meta(1, "Indianapolis Colts")) == "Indiana"


def test_no_resolved_team_keeps_the_label():
    """A bare row (no metadata) is the far smaller harm than a guessed name."""
    assert _grid_row_display_name("Dallas", {}) == "Dallas"
    assert _grid_row_display_name("Dallas", {"name": None}) == "Dallas"
    assert _grid_row_display_name("", _meta(13389, "Dallas Wings")) == ""


def test_both_row_builders_route_the_label_through_the_rule():
    """Wiring guard: the live-cell rows and the register terminal rows both
    print the resolved name, and readers keyed on the venue's spelling (admin
    excludes, the NCAA bracket fallback) still read the label.
    """
    src = inspect.getsource(playoffs.get_playoff_grid)
    assert src.count("_grid_row_display_name(") == 2
    assert "_lookup_ncaa_bracket(venue_label)" in src
    assert "_lookup_wncaa_bracket(venue_label)" in src
    assert "venue_label_by_row.get(id(t)" in src
