"""#4809 — a team nickname must reach the GAME-CARD rail, not just teams and markets.

#4728 gave `pats` the team row and the futures markets. It could not give it the
games, because the game rail matches the denormalised `Event.home_team_name` /
`away_team_name` text and never joins `teams`, so an alias living on
`teams.alternate_names` is invisible to it. Measured on production 2026-09-10
with #4728 already live:

    query     team row   futures   GAME CARDS
    pats      ✓          10        0
    revs      ✓          10        0
    niners    ✓          10        2   <- both are UTEP MINERS

`niners` is the sharp one, and it is two defects stacked: the empty game rail sent
the query to the trigram "did you mean" fallback, which corrected it to the nearest
team NAME (`UTEP Miners` — similarity over 0.25 on the shared `iners`) and filled
the rail with two college football games, in a response whose 10 markets were all
correctly San Francisco 49ers.

So this ships TWO halves and the suite asserts each with the other mutated away:

  1. `_team_nickname_event_arms` — the recall arm, sport-scoped, UNION-shaped.
  2. the `not _event_nickname_arms` clause on the fuzzy fallback's trigger — a query
     that resolved a curated, franchise-anchored nickname is never "corrected".

Half (1) alone would usually hide the Miners (with 49ers games in the window
`total_count` is no longer 0 and the fallback never runs) — and "usually" is exactly
the problem: a bye week, an off-season or a narrow `days_back` puts the count back to
0 and they return.

Behaviour on real rows is `tests/integration/test_search_recall_contract.py`; that
needs a real Postgres and SKIPS locally. These are the pure and structural guards.
"""

from __future__ import annotations

import inspect

import pytest

from app.config.team_aliases import (
    CURATED_TEAM_ALIASES,
    team_nickname_event_expansions,
    team_nickname_search_expansions,
)
from app.routes.events import (
    _team_nickname_event_arms,
    search_events,
)


def _sql(arm) -> str:
    """The arm's compiled SQL, literals inlined so assertions can read values."""
    return str(arm.compile(compile_kwargs={"literal_binds": True}))


# --------------------------------------------------------------------------
# The derivation
# --------------------------------------------------------------------------
def test_the_derived_event_expansions_are_exactly_these() -> None:
    """Pinned value-by-value, like its #4728 sibling and for the same reason.

    The difference from that sibling is the whole point of this map: the second
    element is a **`sport_key`**, not an `llm_sport_category`. Events carry no
    category column — they reach their sport through `sport_id -> sports.key` —
    and `CURATED_TEAM_ALIASES` is already keyed by the sport key, so this needs no
    inversion of `SPORT_PREFIX_TO_LLM_CATEGORY` and cannot drift from it.
    """

    assert team_nickname_event_expansions() == {
        "pats": ("Patriots", "americanfootball_nfl"),
        "revs": ("Revolution", "soccer_usa_mls"),
        "niners": ("49ers", "americanfootball_nfl"),
        "bucs": ("Buccaneers", "americanfootball_nfl"),
        "sixers": ("76ers", "basketball_nba"),
    }


def test_the_two_rails_cover_exactly_the_same_aliases() -> None:
    """The drift guard between the two consumers of one curated map.

    A nickname that reaches the markets and not the games is the defect this
    issue IS. Both maps derive from `CURATED_TEAM_ALIASES` with the same substring
    skip, so adding a row to that map must light up both rails or neither — never
    one, which is the state production was in between #4728 and #4809.
    """

    event_map = team_nickname_event_expansions()
    futures_map = team_nickname_search_expansions()

    assert set(event_map) == set(futures_map), (
        "the game rail and the markets rail disagree about which nicknames exist: "
        f"only-events={set(event_map) - set(futures_map)!r}, "
        f"only-futures={set(futures_map) - set(event_map)!r}"
    )
    for alias in event_map:
        assert event_map[alias][0] == futures_map[alias][0], (
            f"{alias} expands to a different token per rail: "
            f"{event_map[alias][0]!r} vs {futures_map[alias][0]!r}"
        )


def test_an_alias_already_inside_its_token_gets_no_event_arm() -> None:
    """`9ers` is in `49ers`, so the plain ILIKE arm already reaches those rows.

    Same skip as the futures side, kept deliberately in step with it: an extra arm
    here would be a duplicate probe for zero extra recall.
    """

    assert (
        "9ers" in CURATED_TEAM_ALIASES[("americanfootball_nfl", "San Francisco 49ers")]
    )
    assert "9ers" not in team_nickname_event_expansions()
    assert "niners" in team_nickname_event_expansions()


def test_every_event_expansion_carries_a_sport_key() -> None:
    """The invariant, asserted on the data rather than on one example.

    An expansion with no sport key would build an arm with no sport term — the
    cross-league fan-out the (sport_key, name) key exists to prevent — and on the
    EVENT rail that fan-out is not hypothetical: `Patriots` reaches
    `St Kitts & Nevis Patriots`, a real Caribbean Premier League cricket side.
    """

    for alias, (token, sport_key) in team_nickname_event_expansions().items():
        assert token, f"{alias} derived an empty token"
        assert sport_key, f"{alias} would build an UNSCOPED event arm"


# --------------------------------------------------------------------------
# The arm
# --------------------------------------------------------------------------
def test_a_query_with_no_nickname_produces_no_event_arm() -> None:
    """The no-cost path, and the majority of all queries.

    `[]` means `_event_recall_arms` stays single-armed, which means the UNION is
    skipped entirely and the compiled SQL is byte-identical to before this change.
    """

    assert _team_nickname_event_arms(["galatasaray"]) == []
    assert _team_nickname_event_arms(["arsenal", "chelsea"]) == []
    assert _team_nickname_event_arms([]) == []


@pytest.mark.parametrize(
    "alias,token,sport_key",
    [
        ("pats", "Patriots", "americanfootball_nfl"),
        ("revs", "Revolution", "soccer_usa_mls"),
        ("niners", "49ers", "americanfootball_nfl"),
        ("bucs", "Buccaneers", "americanfootball_nfl"),
        ("sixers", "76ers", "basketball_nba"),
    ],
)
def test_the_event_arm_matches_the_token_and_pins_the_sport(
    alias: str, token: str, sport_key: str
) -> None:
    """🔴 THE MUTATION-KILLING PAIR, half one: the scope is IN the arm.

    Delete `Sport.key == sport_key` from `_team_nickname_event_arms` and `pats`
    still reaches the New England Patriots — the recall test passes — while a
    Patriots fan is also served Caribbean Premier League cricket. That is the
    regression this line refuses, asserted on the compiled SQL so it cannot be
    satisfied by a scope applied somewhere else and later dropped.
    """

    arms = _team_nickname_event_arms([alias])
    assert len(arms) == 1, f"{alias} produced {len(arms)} arms, expected 1"

    sql = _sql(arms[0])
    assert (
        f"sports.key = '{sport_key}'" in sql
    ), f"the {alias} event arm is NOT scoped to {sport_key}: {sql}"
    assert (
        token.lower() in sql.lower()
    ), f"the {alias} event arm does not match its token {token!r}: {sql}"


def test_the_event_arm_reads_event_columns_and_not_futures() -> None:
    """It is the GAME rail. Reading `futures_markets` here would be the sibling.

    The two arms are separate functions precisely because they match different
    columns; a copy-paste that left the futures column in place would produce an
    arm that is always false inside the event UNION and silently restore the bug.
    """

    sql = _sql(_team_nickname_event_arms(["pats"])[0])
    assert "events.home_team_name" in sql, f"the arm does not read the home name: {sql}"
    assert "events.away_team_name" in sql, f"the arm does not read the away name: {sql}"
    assert "futures_markets" not in sql, f"the event arm reads futures: {sql}"


def test_the_event_arm_is_case_insensitive_on_the_typed_nickname() -> None:
    """People type `PATS` and `Pats`. The map is keyed lowercase."""

    for typed in ("pats", "Pats", "PATS", "PaTs"):
        assert (
            len(_team_nickname_event_arms([typed])) == 1
        ), f"{typed!r} produced no event arm"


def test_the_alias_composes_with_the_rest_of_the_query() -> None:
    """ "pats game" is a nickname query too — the other terms are KEPT.

    The alias substitutes its own term in place and leaves the surrounding terms
    alone, so the arm still requires them. An arm that dropped them would turn
    "pats <anything>" into a bare franchise query.
    """

    sql = _sql(_team_nickname_event_arms(["pats", "kickoff"])[0])
    assert "Patriots" in sql, f"the token is missing: {sql}"
    assert "kickoff" in sql.lower(), f"the surrounding term was dropped: {sql}"


def test_the_arm_does_not_fire_on_a_word_that_merely_contains_a_nickname() -> None:
    """The map is looked up on the WHOLE term, never as a prefix or substring.

    `patsy` is not `pats`. A substring lookup here would be LAT-P033's `fed` ->
    `Federico` defect wearing an alias's clothes, which `_event_name_match`'s own
    docstring refuses "in full".
    """

    assert _team_nickname_event_arms(["patsy"]) == []
    assert _team_nickname_event_arms(["revsport"]) == []


# --------------------------------------------------------------------------
# The call sites — the helper being right is not the route calling it
# --------------------------------------------------------------------------
def test_search_wires_the_event_nickname_arms_into_the_recall_arms() -> None:
    """Every test above exercises the helper directly.

    Deleting the `.extend(...)` line would leave them all green and ship the
    defect straight back — the same failure mode #4728's own suite records, where
    the helper was correct and one of three call sites never got it.
    """

    source = inspect.getsource(search_events)
    assert (
        "_team_nickname_event_arms(terms)" in source
    ), "search_events no longer builds the nickname event arms"
    assert (
        "_event_recall_arms.extend(_event_nickname_arms)" in source
    ), "the nickname event arms are built and then never added to the recall arms"


def test_the_fuzzy_fallback_is_suppressed_when_a_nickname_resolved() -> None:
    """🔴 THE MUTATION-KILLING PAIR, half two: the `niners` -> UTEP Miners half.

    Delete this clause and the recall arm above still passes every test in this
    file, because with 49ers games in the window `total_count` is not 0 and the
    fallback never runs. Then comes a bye week, an off-season or a narrow
    `days_back`, the count returns to 0, and search once again answers `niners`
    with two UTEP Miners games.

    We KNOW what `niners` names — the map is curated, franchise-anchored and
    sport-keyed — so guessing at a spelling neighbour is strictly worse than an
    honest empty rail, and the markets and team rails still answer.

    A source guard rather than a behavioural one because the behaviour needs a
    real Postgres (`tests/integration/`), while the wiring is exactly what got
    lost before.
    """

    source = inspect.getsource(search_events)
    assert "and not _event_nickname_arms" in source, (
        "the fuzzy 'did you mean' fallback no longer refuses to correct a query "
        "that resolved a curated nickname — `niners` can return UTEP Miners again"
    )
