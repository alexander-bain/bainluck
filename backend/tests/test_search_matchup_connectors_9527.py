"""#9527 — `red sox vs yankees` finds the game: a matchup connector is not a search term.

THE DEFECT, production 2026-09-29 ~02:25Z: `red sox vs yankees`, `phillies vs
braves`, `eagles vs bears` (live) all returned ZERO games on `/api/events/search`
and `/api/events/typeahead`, while `red sox at yankees` returned the Wild Card
game. Both routes build their term filter from `_strip_search_scaffolding`,
which dropped `at` but kept `vs`, so every row had to contain "vs".

The route behaviour is `tests/integration/test_typeahead_individual_sport_v_pg_9522.py`
(real Postgres). This file pins the rule.
"""

from __future__ import annotations

import inspect

import pytest

from app.routes import events as ev_mod

strip = ev_mod._strip_search_scaffolding


@pytest.mark.parametrize(
    "q, want",
    [
        ("red sox vs yankees", ["red", "sox", "yankees"]),
        ("phillies vs. braves", ["phillies", "braves"]),
        ("eagles v bears", ["eagles", "bears"]),
        ("Michelsen v Alcaraz", ["Michelsen", "Alcaraz"]),
        ("red sox @ yankees", ["red", "sox", "yankees"]),
        ("celtics versus knicks", ["celtics", "knicks"]),
        ("Alcaraz VS Michelsen", ["Alcaraz", "Michelsen"]),
    ],
)
def test_a_connector_between_two_words_is_dropped(q, want):
    assert strip(q.split()) == want


def test_at_was_already_dropped_and_still_is():
    """The control: the connector that always worked."""
    assert strip("red sox at yankees".split()) == ["red", "sox", "yankees"]


def test_a_trailing_v_is_a_numeral_not_a_connector():
    """`grand theft auto v` names a game; the "v" is not joining two sides."""
    assert strip("grand theft auto v".split()) == ["grand", "theft", "auto", "v"]


def test_a_leading_connector_is_kept():
    assert strip("vs red sox".split()) == ["vs", "red", "sox"]


def test_two_word_queries_are_untouched():
    """The stripper's own floor: 1-2 word queries keep every word."""
    assert strip("v bears".split()) == ["v", "bears"]
    assert strip("eagles vs".split()) == ["eagles", "vs"]


def test_both_routes_build_their_terms_through_the_stripper():
    """A route that split the raw query itself would keep "vs" as a term."""
    assert "_strip_search_scaffolding(_q_identity.strip().split())" in inspect.getsource(
        ev_mod.typeahead_search
    )
    assert "_strip_search_scaffolding(" in inspect.getsource(ev_mod.search_events)
