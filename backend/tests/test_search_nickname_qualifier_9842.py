"""TYPING `LEICESTER RIDERS` STOPS CARDING THE SASKATCHEWAN ROUGHRIDERS. #9842.

A side effect of #7386 (PR #9820), not a reason to revert it: `riders` names the
Roughriders and still does. Production 2026-09-30 14:2xZ, web v5318:

    leicester riders   teams Saskatchewan Roughriders (only card), above the
                       one real answer, "Leicester Riders vs London Lions"
    knight riders      teams Kolkata + Trinbago Knight Riders, Roughriders third

`_team_nickname_team_arms` looked up EVERY word, so the tail of another club's
name recalled the nickname's row, OR'd it onto the Teams card's filter and
ordered it first. The word BEFORE a nickname decides: a qualifier (`leicester`,
`knight`) makes it part of another name; scaffolding, a connector, a league,
another nickname or a word of the club itself leaves it the nickname. Both
routes hand the helper the words as typed — `terms` has already dropped the
`vs` of `stamps vs riders`.
"""

from __future__ import annotations

import inspect

import pytest

from app.routes import events as ev
from app.routes.events import _team_nickname_team_arms

ROUGHRIDERS = ("americanfootball_cfl", "Saskatchewan Roughriders")


def _named(q: str) -> list[str]:
    """The rows the arm recalls for `q`, split exactly as both routes split it."""
    return [
        str(arm.compile(compile_kwargs={"literal_binds": True}))
        for arm in _team_nickname_team_arms(q.split())
    ]


def _names_roughriders(q: str) -> bool:
    return any("Saskatchewan Roughriders" in sql for sql in _named(q))


@pytest.mark.parametrize(
    "q",
    [
        "leicester riders",   # the issue's specimen: a basketball club
        "knight riders",      # the IPL / CPL clubs full text already finds
        "kolkata knight riders",
        "the knight riders",
        "Leicester Riders",
        "london riders",
    ],
)
def test_a_qualified_nickname_does_not_card_the_roughriders(q) -> None:
    assert not _names_roughriders(q), q


@pytest.mark.parametrize(
    "q",
    [
        "riders",               # #7386's ship, unchanged
        "Riders",
        "the riders",           # scaffolding
        "will the riders win",
        "cfl riders",           # the club's own league
        "saskatchewan riders",  # a word of the club's own name
        "riders playoffs",      # a word AFTER never renames it
        "stamps vs riders",     # connector, read from the typed words
        "stamps @ riders",
        "stamps at riders",
        "riders v stamps",
    ],
)
def test_the_nickname_still_cards_the_roughriders(q) -> None:
    assert _names_roughriders(q), q


@pytest.mark.parametrize(
    "q, team",
    [
        ("a's", "Athletics"),
        ("mlb a's", "Athletics"),
        ("pats playoffs", "New England Patriots"),
        ("nfl pats", "New England Patriots"),
        ("new england pats", "New England Patriots"),
        ("a's m's", "Seattle Mariners"),  # another nickname before it
    ],
)
def test_the_other_curated_nicknames_keep_their_club(q, team) -> None:
    assert any(team in sql for sql in _named(q)), q


def test_the_mutant_that_ignores_the_qualifier_cards_the_roughriders(monkeypatch) -> None:
    """The guard bites: without the adjacency check the specimen reproduces."""
    monkeypatch.setattr(ev, "_nickname_is_qualified", lambda prev, entry: False)
    assert _names_roughriders("leicester riders")
    assert _names_roughriders("knight riders")


def test_the_mutant_that_refuses_every_preceding_word_loses_the_club(monkeypatch) -> None:
    """…and the other direction: refusing every qualifier would lose `the riders`."""
    monkeypatch.setattr(ev, "_nickname_is_qualified", lambda prev, entry: True)
    assert not _names_roughriders("the riders")
    assert not _names_roughriders("stamps vs riders")


def test_the_terms_path_would_lose_the_matchup() -> None:
    """Why both routes pass `_q_identity.split()`: `terms` strips the connector of a
    3-word query, so `stamps` would sit right before `riders` and qualify it."""
    terms = ev._strip_search_scaffolding("stamps vs riders".split())
    assert terms == ["stamps", "riders"]
    assert _team_nickname_team_arms(terms) == []


def test_both_routes_feed_the_arm_the_words_as_typed() -> None:
    for route, var in ((ev.search_events, "_team_nickname_rows"),
                       (ev.typeahead_search, "_ta_team_nickname_rows")):
        src = inspect.getsource(route)
        assert f"{var} = _team_nickname_team_arms(_q_identity.split())" in src
        assert f"{var} = _team_nickname_team_arms(terms)" not in src


def test_the_roughriders_key_is_still_the_riders_row() -> None:
    assert ev._TEAM_NICKNAME_TEAM_ROWS["riders"] == ROUGHRIDERS
