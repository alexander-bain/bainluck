"""#4847 — a team nickname must reach the DROPDOWN's game suggestions too.

#4809 fixed the results page. The dropdown has the same hole for the same reason:
`/api/events/typeahead` matches the denormalised `Event.home_team_name` /
`away_team_name` and never joins `teams`, so an alias living on
`teams.alternate_names` is invisible to it. Measured on production 2026-09-10
20:35Z, master `70c777a4`, counting `/api/events/typeahead` suggestions by type:

    q         team   futures   EVENT
    pats      1      5         0
    niners    1      5         0
    9ers      1      5         1   <- already works: see below
    patriots  3      3         1   <- and it is the CRICKET side (the control)

`9ers` is the instructive one and it is NOT a counter-example. This rail's name
test is `or_(fts, ilike)`, so a substring alias reaches the row on the ILIKE arm
alone — the exact opposite of `/search`, whose matcher AND-s the FTS word test
onto the ILIKE and therefore needed `9ers` given an arm of its own (CERT-2527).
Here it is the NON-substring aliases (`pats`, `niners`, `revs`, `bucs`,
`sixers`) that reach nothing, and `9ers` is a live additive control.

Unlike `/search`, this is not one change but two halves that must agree, which is
why the issue was split off rather than ridden along:

  1. the recall arms, added to BOTH `event_team_filter` (the upcoming pool) and
     `event_name_filter` (the or-last query of #4411);
  2. the Python admission test `_ta_names_participant`, which decides whether a
     fetched row NAMES the query. An arm added only to the SQL fetches the
     Patriots row and then discards it — inert code that still costs the query,
     on a per-keystroke path.

Production says both halves are load-bearing, and says it with two different
rows (`BEFORE-patriots-49ers-rows.json`, same session):

  * `niners` is answered by the upcoming pool — `San Francisco 49ers @ Los
    Angeles Rams`, 2026-09-11 00:35Z, inside now+7d.
  * `pats` is answered ONLY through the or-last arm. The Patriots' next game is
    2026-09-20 17:00Z, nine days out and outside that window, so half (1) alone
    leaves the reported symptom exactly as it is. What answers the query is last
    night's completed `New England Patriots @ Seattle Seahawks`
    (2026-09-10 00:20Z), which the or-last query can only keep if half (2)
    admits it.

Behaviour on real rows needs a real Postgres and lives in
`tests/integration/`; these are the pure and structural guards.
"""

from __future__ import annotations

import inspect

import pytest

from app.routes.events import (
    _last_match_query,
    _nickname_names_participant,
    _team_nickname_event_admissions,
    _team_nickname_event_arms,
    _team_nickname_event_rewrites,
    typeahead_search,
)
from app.utils.search_match_class import query_names_participant

# The production rows the acceptance turns on, verbatim from the db-query above.
NFL_PATRIOTS = ("Seattle Seahawks", "New England Patriots")
NFL_NINERS = ("Los Angeles Rams", "San Francisco 49ers")
CRICKET_PATRIOTS = ("Barbados Tridents", "St Kitts & Nevis Patriots")

NFL = "americanfootball_nfl"
CPL = "cricket_caribbean_premier_league"


# --------------------------------------------------------------------------
# One rewrite, two forms — the extraction is the ship, not a tidy-up
# --------------------------------------------------------------------------
def test_the_sql_arms_are_built_from_the_shared_rewrites(monkeypatch) -> None:
    """🔴 The drift guard, asserted by REMOVING the shared source.

    `/search`'s arms and `/typeahead`'s admission test must not be able to
    disagree about which query names which team in which sport — a Python test
    looser than the arm promotes a row the arm never meant to fetch, and a
    stricter one makes the arm inert. Both call sites therefore read
    `_team_nickname_event_rewrites`, and this proves it behaviourally rather
    than by reading the source: empty the shared rewrites and BOTH forms go
    empty. A second copy of the rule anywhere would survive this.
    """

    monkeypatch.setattr(
        "app.routes.events._team_nickname_event_rewrites", lambda terms: []
    )
    assert _team_nickname_event_arms(["pats"]) == []
    assert _team_nickname_event_admissions(["pats"]) == []


def test_the_two_forms_agree_arm_for_arm() -> None:
    """Same count, same sports, same order — they are one list read two ways."""

    terms = ["pats"]
    rewrites = _team_nickname_event_rewrites(terms)
    arms = _team_nickname_event_arms(terms)
    admissions = _team_nickname_event_admissions(terms)

    assert len(rewrites) == len(arms) == len(admissions) == 1
    assert admissions == [("Patriots", NFL)]
    assert [sport for _r, _e, sport in rewrites] == [
        sport for _query, sport in admissions
    ]


def test_a_query_with_no_nickname_admits_nothing_and_arms_nothing() -> None:
    """The no-cost path and the overwhelming majority of keystrokes.

    `[]` is what keeps `if _ta_nickname_arms:` false, and a false branch is what
    keeps the compiled SQL byte-identical on a per-keystroke endpoint.
    """

    for terms in (["galatasaray"], ["arsenal", "chelsea"], []):
        assert _team_nickname_event_arms(terms) == []
        assert _team_nickname_event_admissions(terms) == []


def test_the_admission_keeps_the_surrounding_terms() -> None:
    """A "pats game" query rewrites to "Patriots game" — the other terms are KEPT.

    The admission is a QUERY, not a predicate, because that is what
    `query_names_participant` reads. Dropping the surrounding terms would hand
    that predicate a query the reader never typed and turn "pats <anything>"
    into a bare franchise query with a franchise's promotion rights.
    """

    assert _team_nickname_event_admissions(["pats", "game"]) == [("Patriots game", NFL)]


def test_the_admission_is_case_insensitive_on_the_typed_nickname() -> None:
    """People type `PATS` and `Pats`; the curated map is keyed lowercase."""

    for typed in ("pats", "Pats", "PATS", "PaTs"):
        assert _team_nickname_event_admissions([typed]) == [("Patriots", NFL)]


def test_the_admission_does_not_fire_on_a_word_containing_a_nickname() -> None:
    """`patsy` is not `pats`. The map is looked up on the WHOLE term."""

    assert _team_nickname_event_admissions(["patsy"]) == []
    assert _team_nickname_event_admissions(["revsport"]) == []


# --------------------------------------------------------------------------
# The admission test itself
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "alias,sport_key,participants",
    [
        ("pats", NFL, NFL_PATRIOTS),
        ("niners", NFL, NFL_NINERS),
        ("9ers", NFL, NFL_NINERS),
    ],
)
def test_a_nickname_names_its_own_franchise(alias, sport_key, participants) -> None:
    """The half without which the or-last arm is inert.

    `pats` fetches `New England Patriots @ Seattle Seahawks` through the new
    recall arm and then has to survive this predicate; returning False here
    would discard the row the query was fetched for and leave production
    exactly as measured.
    """

    admissions = _team_nickname_event_admissions([alias])
    assert _nickname_names_participant(admissions, sport_key, participants)


def test_the_sport_scope_refuses_the_cricket_patriots() -> None:
    """🔴 THE MUTATION-KILLING TEST: the scope is what says no, and only it.

    Drop `expansion_sport == sport_key` from `_nickname_names_participant` and
    every other test in this file still passes, while `pats` starts admitting
    `St Kitts & Nevis Patriots at Barbados Tridents` — a real Caribbean Premier
    League fixture, live on production today, and a genuine whole-word match for
    the rewritten token. The second assertion is the mutation stated as a fact:
    the NAME test alone says yes, so the scope is carrying the whole refusal.

    A row can reach this predicate from the OTHER recall arms too, so "the
    sport-scoped arm would never have fetched it" is not a defence available
    here — which is why the scope is re-applied in Python rather than trusted.
    """

    admissions = _team_nickname_event_admissions(["pats"])

    assert not _nickname_names_participant(admissions, CPL, CRICKET_PATRIOTS), (
        "`pats` admits a Caribbean Premier League cricket fixture — the exact "
        "wrong answer `team_nickname_event_expansions` is sport-keyed to avoid"
    )
    assert query_names_participant("Patriots", CRICKET_PATRIOTS), (
        "the name half no longer matches the cricket side, so this test has "
        "stopped proving that the SPORT SCOPE is what refuses it"
    )


def test_a_nickname_does_not_admit_a_different_game_in_the_same_sport() -> None:
    """🔴 The other half of the pair: the NAME test is load-bearing too.

    Return True on a sport match alone and `pats` promotes every NFL fixture the
    or-last query returns, finished ones first. `49ers @ Rams` is in the same
    sport as the Patriots and is not the Patriots.
    """

    admissions = _team_nickname_event_admissions(["pats"])
    assert not _nickname_names_participant(admissions, NFL, NFL_NINERS)


def test_nothing_is_admitted_without_a_nickname_in_the_query() -> None:
    """No curated nickname ⇒ no admissions ⇒ the predicate cannot promote.

    This is the clause that keeps `us open`, `tennis` and `nba mvp` behaving
    exactly as #4411 left them: they produce no rewrite, so the nickname half
    never fires and only `query_names_participant(q, …)` decides.
    """

    assert not _nickname_names_participant([], NFL, NFL_PATRIOTS)
    assert not _nickname_names_participant(
        _team_nickname_event_admissions(["us", "open"]), NFL, NFL_PATRIOTS
    )


def test_a_row_with_no_sport_admits_nothing_and_does_not_crash() -> None:
    """`sport_key` is None for a sport-less row; every expansion carries a sport.

    The right answer is "no", reached by comparison rather than by an exception
    on a per-keystroke path.
    """

    assert not _nickname_names_participant(
        _team_nickname_event_admissions(["pats"]), None, NFL_PATRIOTS
    )


def test_an_empty_participant_pair_admits_nothing() -> None:
    """A row whose denormalised names are null cannot be named by anything."""

    assert not _nickname_names_participant(
        _team_nickname_event_admissions(["pats"]), NFL, (None, None)
    )


# --------------------------------------------------------------------------
# The call site — the helpers being right is not the route calling them
# --------------------------------------------------------------------------
def test_typeahead_arms_both_filters_and_says_which_answers_what() -> None:
    """🔴 Both filters, because production answers the two queries differently.

    `event_team_filter` alone answers `niners` (a fixture inside now+7d) and
    leaves `pats` broken (next game nine days out). `event_name_filter` alone
    answers `pats` through the or-last query and makes the upcoming pool fire a
    second query it did not need. Deleting either line leaves every unit test
    above green and half the issue on production.
    """

    source = inspect.getsource(typeahead_search)
    assert "_ta_nickname_arms = _team_nickname_event_arms(terms)" in source, (
        "typeahead no longer builds the nickname event arms from the SHARED "
        "builder `/search` uses"
    )
    assert "event_team_filter = or_(event_team_filter, *_ta_nickname_arms)" in source, (
        "the nickname arms never reach the upcoming-events pool — `niners` gets "
        "no game suggestion"
    )
    assert "event_name_filter = or_(event_name_filter, *_ta_nickname_arms)" in source, (
        "the nickname arms never reach the or-last query — `pats` gets no game "
        "suggestion between fixtures, which is the reported symptom"
    )


def test_the_arms_are_added_only_when_a_nickname_resolved() -> None:
    """The latency clause. Every other query must compile the SQL it does today.

    An unconditional `or_(event_team_filter, *[])` would rebuild the predicate on
    every keystroke for the nickname-free majority.
    """

    source = inspect.getsource(typeahead_search)
    assert "if _ta_nickname_arms:" in source, (
        "the nickname arms are wired unconditionally — the no-nickname path no "
        "longer compiles byte-identical SQL on a per-keystroke endpoint"
    )


def test_the_admission_test_reads_the_shared_rewrites_with_the_rows_sport() -> None:
    """The Python half is wired, and the sport travels with it.

    `_nickname_names_participant` cannot apply a scope it is not given, so the
    call site passing the row's own sport is part of the guard rather than a
    detail of it.
    """

    source = inspect.getsource(typeahead_search)
    assert "_ta_nickname_admissions = _team_nickname_event_admissions(terms)" in source
    assert "_nickname_names_participant(" in source, (
        "`_ta_names_participant` no longer consults the nickname rewrites — the "
        "recall arms fetch the Patriots row and then discard it"
    )
    assert "ev.sport.key if ev.sport else None" in source, (
        "the row's sport no longer travels into the admission test, so the "
        "Python test is looser than the SQL arm that fetched the row"
    )


def test_the_fuzzy_corrector_cannot_fire_for_a_curated_nickname() -> None:
    """Why this ship has no analogue of #4809's second half.

    #4809 needed TWO halves: the recall arm, and `and not _event_nickname_arms`
    on the fuzzy "did you mean" fallback — because on `/search` an empty game
    rail sent `niners` to the trigram corrector, which answered `UTEP Miners`.
    This surface cannot reach that state: its corrector is gated on
    `not team_pool`, and for every curated nickname the team row is already
    there (#4728 put it there — it is the `team = 1` column of #4847's own
    before-table).

    So a suppression clause here would guard an unreachable branch. That is only
    true while the trigger keeps its `not team_pool` term, which is what this
    pins — loosen it to "few results" and `niners` can be corrected to a
    spelling neighbour again, on the dropdown this time.
    """

    source = inspect.getsource(typeahead_search)
    assert "if not team_pool and not event_pool and len(futures_pool) < 2:" in source, (
        "the typeahead fuzzy corrector's trigger changed. If it can now fire "
        "while a team row exists, a curated nickname can be 'corrected' to a "
        "spelling neighbour and #4809's suppression clause is owed here too"
    )


def test_both_event_pools_eagerly_load_the_sport_they_are_now_read_for() -> None:
    """🔴 `ev.sport` on a lazily-loaded row is a 500 on a per-keystroke path.

    The admission test now reaches through the relationship for every row in
    BOTH pools (gotcha #6: an async lazy load raises `MissingGreenlet`, it does
    not quietly emit a query). Both queries already `selectinload(Event.sport)`;
    this fails the day one of them stops.
    """

    for name, source in (
        ("the upcoming-events pool", inspect.getsource(typeahead_search)),
        ("the or-last query", inspect.getsource(_last_match_query)),
    ):
        assert "selectinload(Event.sport)" in source, (
            f"{name} no longer eager-loads `Event.sport`, which the nickname "
            "admission test reads on every fetched row"
        )
