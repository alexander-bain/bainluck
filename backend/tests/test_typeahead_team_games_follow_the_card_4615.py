"""#4615: once the dropdown resolves a team, its own game comes next, before its props.

Production 2026-09-25 07:30Z (`6e2f96cb`), `?q=dodg&debug_evidence=true`, replayed
through `rank_with_keys`:

    (0, 1.5, 6)  team     Los Angeles Dodgers
    (0, 2,   4)  futures  Los Angeles Dodgers vs. San Francisco Giants
    (0, 2,   4)  futures  ... - 1st Inning Winner      (and 3rd, 4th, 5th)
    (0, 2,   5)  event    Los Angeles Dodgers at San Francisco Giants   <- tonight

The game lost on kind alone: a plain `event` (5) sorts under `futures` (4). The
promotion that fixes that (`entity_event`, #4411) is gated on
`query_names_participant`, which refuses both a prefix (`dodg`) and the plural
fold (`yankee`) on purpose (CERT-2392). `query_resolves_team` is the test the
route now uses to hand the lead team's OWN fixtures the same promotion.

The route wiring is proven against real Postgres in
`tests/integration/test_search_recall_contract.py` (the #4615 block).
"""

import pytest

from app.utils.search_match_class import (
    ENTITY_EVENT_KIND,
    ENTITY_TEAM_KIND,
    Evidence,
    query_is_entity_name,
    query_resolves_team,
    rank_with_keys,
)

_DODGERS_NAMES = ("Los Angeles Dodgers", "Los Angeles", "Dodgers", "LAD")


def _team(q: str) -> Evidence:
    """The Dodgers row as `_typeahead_evidence` hands it to the scorer."""
    name, *aliases = _DODGERS_NAMES
    kind = ENTITY_TEAM_KIND if query_is_entity_name(q, _DODGERS_NAMES) else "team"
    return Evidence(
        name=name, aliases=tuple(aliases), kind=kind, sport_key="baseball_mlb"
    )


@pytest.mark.parametrize(
    "q",
    [
        "dodg",  # the unfinished alias — MC1B, the production specimen
        "dodger",  # the whole alias through the plural fold — the `yankee` shape
        "dodgers",  # the alias itself
        "lad",  # the abbreviation
        "los angeles",  # a whole alternate name
    ],
)
def test_a_team_the_query_names_is_resolved(q):
    assert query_resolves_team(q, _team(q)) is True


@pytest.mark.parametrize(
    "q",
    [
        # A token (or part of one) INSIDE a name is a landing, not the entity
        # (ruling 041). `angel` is the route control's query.
        "angel",
        "angeles",
        "new",
        "york",
        "los",
    ],
)
def test_a_team_the_query_merely_lands_on_is_not(q):
    assert query_resolves_team(q, _team(q)) is False


def test_only_a_team_row_can_be_resolved():
    """A market whose NAME starts with the query is MC1B too — it is not a team."""
    market = Evidence(name="Dodgers vs. Giants - 1st Inning Winner", kind="futures")
    assert query_resolves_team("dodg", market) is False


# --- the ordering the promotion buys, on the production specimen -------------

_GAME = "Los Angeles Dodgers at San Francisco Giants"
_PARENT = "Los Angeles Dodgers vs. San Francisco Giants"


def _dodg_page(game_kind: str) -> list[Evidence]:
    name, *aliases = _DODGERS_NAMES
    sides = ("Los Angeles Dodgers", "San Francisco Giants")
    return [
        Evidence(
            name=name, aliases=tuple(aliases), kind="team", sport_key="baseball_mlb"
        ),
        Evidence(name=_PARENT, outcomes=sides, kind="futures", sport_key="baseball"),
        *(
            Evidence(
                name=f"{_PARENT} - {n} Inning Winner",
                outcomes=sides,
                kind="futures",
                sport_key="baseball",
            )
            for n in ("1st", "3rd", "4th", "5th")
        ),
        Evidence(name=_GAME, kind=game_kind, sport_key="baseball_mlb"),
    ]


def _order(q: str, page: list[Evidence]) -> list[str]:
    return [p.name for _k, p in rank_with_keys(q, [(e, e) for e in page])]


def test_the_strawman_reproduces_production():
    """Unpromoted, the game is LAST — exactly the 07:30Z production order."""
    assert _order("dodg", _dodg_page("event"))[-1] == _GAME


def test_the_promoted_game_sits_directly_under_its_team():
    order = _order("dodg", _dodg_page(ENTITY_EVENT_KIND))
    assert order[:2] == ["Los Angeles Dodgers", _GAME], order


def test_the_promotion_cannot_lift_the_game_over_its_team():
    """The card still leads: MC1B (1.5) beats the game's MC2 whatever the kind."""
    assert _order("dodg", _dodg_page(ENTITY_EVENT_KIND))[0] == "Los Angeles Dodgers"
