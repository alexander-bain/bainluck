"""#6977 — the diacritic search fold, as a pure contract that runs on every push.

The ROUTE-level proof lives in
`tests/integration/test_search_diacritic_fold_pg_6977.py`, which needs real
Postgres and runs in the `search-recall` job. This file is the half that runs
everywhere: the map's own invariants, and the expansion behaviour the route
rides.

WHY BOTH. #5821's bridge gate was green for a year because its only real cases
were `skipif`-gated on a variable CI never set, and pytest exits 0 on a skip.
The durable guard has to be the one that cannot skip — so the properties that do
not need a database are asserted here, on every push, and the database file
proves the reader actually reaches the rows.
"""

from __future__ import annotations

import pytest

from app.config.diacritic_search_folds import DIACRITIC_SEARCH_FOLDS
from app.utils import name_normalization
from app.utils.name_normalization import (
    _CITY_ABBREVIATIONS,
    _GENERAL_ABBREVIATIONS,
    diacritic_fold_query,
    expand_search_terms,
    strip_diacritics,
)


def _expansion(term: str) -> str | None:
    """The expansion the route would spend for `term` — via the real chokepoint."""
    (_, expansion), = expand_search_terms([term])
    return expansion


# ── The ship ────────────────────────────────────────────────────────────────


def test_the_unaccented_spelling_expands_to_the_stored_one():
    """`Atletico` must reach `Atlético` — the query in the issue.

    Asserted through `expand_search_terms`, not by reading the dict: the dict
    being right and the route never consulting it is exactly the inert-fix shape
    this ship had to avoid.
    """
    assert _expansion("Atletico") == "atlético"
    assert _expansion("ATLETICO") == "atlético", "the fold is case-insensitive"


def test_an_already_accented_term_gets_no_expansion():
    """`Atlético` already matches the stored row, so a second arm would be waste.

    This is the same skip `team_nickname_search_expansions` applies to an alias
    that is already a substring of its token.
    """
    assert _expansion("Atlético") is None


def test_an_ordinary_unaccented_term_is_untouched():
    """The overwhelming majority of queries must compile to exactly today's SQL."""
    for term in ("boston", "celtics", "yankees", "election", "winner"):
        assert _expansion(term) is None, f"{term} gained an arm it does not need"


def test_the_abbreviations_still_win_their_own_terms():
    """`la` keeps `los angeles` — no abbreviation lost its expansion."""
    for key, value in _CITY_ABBREVIATIONS.items():
        assert _expansion(key) == value
    for key, value in _GENERAL_ABBREVIATIONS.items():
        assert _expansion(key) == value


def test_a_fold_can_never_displace_an_abbreviation(monkeypatch):
    """The ORDER of the `or` chain, made falsifiable on purpose.

    ⚠️ The test above cannot fail this property, and that is measured rather than
    suspected: moving the fold to the FRONT of the chain leaves all of real data
    passing, because the three dictionaries do not overlap on a single key. An
    unobservable decision is an unguarded one, so the collision that does not
    exist in production is constructed here.

    It matters because the map is REGENERATED. The day a club token lands on
    `la` or `sec`, fold-first would silently take a working abbreviation away
    from every reader, and nothing else in this file would notice.
    """
    colliding = dict(DIACRITIC_SEARCH_FOLDS) | {"la": "lá", "sec": "séc"}
    monkeypatch.setattr(name_normalization, "DIACRITIC_SEARCH_FOLDS", colliding)

    assert _expansion("la") == _CITY_ABBREVIATIONS["la"]
    assert _expansion("sec") == _GENERAL_ABBREVIATIONS["sec"]


def test_the_okina_folds_even_though_it_is_not_a_combining_mark():
    """`hawaii` -> `hawaiʻi`. U+02BB is a MODIFIER LETTER, so NFD leaves it.

    `strip_diacritics` alone returns the token unchanged here, which would have
    produced an expansion equal to its own key — a duplicate arm for zero recall.
    The generator drops the non-ASCII residue instead, which is both what a
    reader types and a real gain.
    """
    assert strip_diacritics("hawaiʻi") == "hawaiʻi", (
        "if this ever folds on its own, the generator's extra strip is redundant"
    )
    assert _expansion("hawaii") == "hawaiʻi"


# ── The map's own invariants ────────────────────────────────────────────────


def test_every_key_is_typeable_on_a_plain_keyboard():
    """A key that cannot be typed can never be looked up — a dead row."""
    for key in DIACRITIC_SEARCH_FOLDS:
        assert key.isascii(), f"{key!r} is not ASCII"
        assert key.isalnum(), f"{key!r} is not alphanumeric"
        assert key == key.lower(), f"{key!r} is not lowercased"


def test_no_entry_expands_to_itself():
    """key == value is an ILIKE arm identical to the one already built."""
    for key, value in DIACRITIC_SEARCH_FOLDS.items():
        assert key != value, f"{key!r} expands to itself"


def test_every_value_actually_carries_an_accent():
    """A pure-ASCII value would be a fold that folds nothing."""
    for key, value in DIACRITIC_SEARCH_FOLDS.items():
        assert not value.isascii(), f"{key!r} -> {value!r} has nothing to fold"


def test_every_value_folds_back_to_its_own_key():
    """The round-trip that makes the map a FOLD rather than a synonym list.

    This is the invariant that keeps a regenerated file honest: whatever the
    generator emitted, the reader's typed spelling of the stored value must be
    the key it is filed under.
    """
    for key, value in DIACRITIC_SEARCH_FOLDS.items():
        typed = "".join(c for c in strip_diacritics(value) if c.isascii())
        assert typed == key, f"{value!r} folds to {typed!r}, filed under {key!r}"


def test_the_fold_keys_do_not_collide_with_the_other_dictionaries():
    """Measured at generation time as zero overlap; pinned so it stays zero.

    An overlap would not break anything today — the fold is last, so it loses —
    but it would mean a club name silently unreachable because a city
    abbreviation owns the token, and nobody would see it happen.
    """
    keys = set(DIACRITIC_SEARCH_FOLDS)
    assert not keys & set(_CITY_ABBREVIATIONS)
    assert not keys & set(_GENERAL_ABBREVIATIONS)


def test_the_map_is_not_empty():
    """A generator that writes an empty dict makes every test above vacuous."""
    assert len(DIACRITIC_SEARCH_FOLDS) > 400


# ── The query-string rewrite (the Teams surface) ────────────────────────────


@pytest.mark.parametrize(
    "query,expected",
    [
        ("Atletico Madrid", "atlético Madrid"),
        ("atletico", "atlético"),
        ("Bayern Munchen", "Bayern münchen"),
    ],
)
def test_the_query_rewrite_replaces_only_the_folded_token(query, expected):
    assert diacritic_fold_query(query) == expected


@pytest.mark.parametrize("query", ["Atlético Madrid", "boston celtics", "", "   "])
def test_the_query_rewrite_returns_none_when_nothing_folds(query):
    """None is the signal the Teams filter uses to build today's exact SQL."""
    assert diacritic_fold_query(query) is None
