"""#9859 — a leading city abbreviation (`sf giants`), as a pure contract that runs on every push.

The route-level proof (team card + game order served for `sf giants`, `la kings`,
`la angels`) lives in `tests/integration/test_search_city_abbrev_pg_9859.py`,
which needs Postgres and runs in the `search-recall` job. This half cannot skip.
"""

from __future__ import annotations

import pytest

from app.routes import events as ev
from app.utils.name_normalization import city_abbreviated_names, city_abbreviation_query
from app.utils.search_match_class import MC1_ALL_TOKENS, match_class


@pytest.mark.parametrize(
    "typed, rewritten",
    [
        ("sf giants", "san francisco giants"),
        ("SF Giants", "san francisco Giants"),
        ("la kings", "los angeles kings"),
        ("ny rangers", "new york rangers"),
        ("stl cardinals", "st louis cardinals"),
        ("okc thunder", "oklahoma city thunder"),
    ],
)
def test_a_leading_city_abbreviation_is_spelled_out(typed, rewritten) -> None:
    assert city_abbreviation_query(typed) == rewritten


@pytest.mark.parametrize(
    "typed", ["la", "sf", "giants sf", "giants", "san francisco giants", "lakers", "", None]
)
def test_a_bare_or_trailing_abbreviation_is_not_rewritten(typed) -> None:
    """A bare `la` asks for more than one club, and the city comes first in a name."""
    assert city_abbreviation_query(typed) is None


@pytest.mark.parametrize(
    "name, abbreviated",
    [
        ("San Francisco Giants", ("SF giants",)),
        ("Los Angeles Angels", ("LA angels",)),
        ("St. Louis Cardinals", ("SL cardinals", "STL cardinals")),
        ("St.Louis Cardinals", ("SL cardinals", "STL cardinals")),
        ("Oklahoma City Thunder", ("OKC thunder",)),
        ("Oklahoma Sooners", ("OK sooners",)),
    ],
)
def test_a_clubs_name_with_its_city_abbreviated(name, abbreviated) -> None:
    assert city_abbreviated_names(name) == abbreviated


@pytest.mark.parametrize("name", ["LA Galaxy", "Washington", "Ohio State Buckeyes", "", None])
def test_names_without_a_leading_city_or_with_only_the_city_get_nothing(name) -> None:
    assert city_abbreviated_names(name) == ()


def _row(name, aliases=(), abbreviation=None):
    return {"name": name, "_aliases": list(aliases), "abbreviation": abbreviation,
            "sport_key": "baseball_mlb"}


def test_the_named_club_outranks_a_club_that_owns_the_city_twice() -> None:
    """`la angels` carded the Clippers: their aliases own `LA` and the scorer read
    the Angels as a partial match. With the abbreviated name the Angels own every
    word; the Clippers still do not."""
    angels = ev._search_team_evidence(_row("Los Angeles Angels", abbreviation="LAA"), "la angels")
    clippers = ev._search_team_evidence(
        _row("Los Angeles Clippers", ["LA Clippers", "Los Angeles Clippers"], "LAC"), "la angels"
    )
    assert match_class("la angels", angels) <= MC1_ALL_TOKENS
    assert match_class("la angels", clippers) > MC1_ALL_TOKENS


@pytest.mark.parametrize("query", ["angels", "la", "los angeles angels", None])
def test_every_other_query_scores_the_evidence_it_scored_before(query) -> None:
    row = _row("Los Angeles Angels", ["Halos"], "LAA")
    assert ev._search_team_evidence(row, query).aliases == ("Halos", "LAA")
