"""#8309 — a Polymarket container leg that names no team stops reaching Additional Markets.

THE DEFECT, SEEN ON PRODUCTION (2026-09-23 23:50Z, 390px, /events/15317596,
Cardinals @ Pirates, live). The Polymarket card under "Additional Markets" read

    St. Louis Cardinals 74% / Spread -2.5 49%

and `GET /api/events/15317596/game-markets` served, from market 61294013
(`group_id = polymarket:1038122`, market_type `field`):

    St. Louis Cardinals 0.735 · Spread -1.5 0.63 · Spread -1.5 0.125 · Spread -2.5 0.49

Two different rows under one label, and no team on any of them. The stored row
(read 2026-09-25 06:1xZ) also carries `O/U 6.5`, `O/U 7.5`, `O/U 8.5`,
`1st 5 Innings O/U 4.5`, `1st 5 Innings O/U 5.5` and `NRFI`. The legs are the
container's copies of sub-markets that were never written as their own rows, so
#4189 / #5273 (which drop the parent when a child serves the named leg) keep
the parent as the group's only representation — correctly — and the bare legs
came with it.

🔴 THE CONTROLS ARE THE POINT. "No Spread row" is satisfied by a serializer
that returns nothing, so: the parent's own team leg stays with its price; a
real spread market still fills the spreads section; a Polymarket O/U market
still fills totals; every leg that names something is left alone; and the
container's bare totals stay served — #6799's cert-graded guard (event
14780547) holds those as real rungs, and their missing word is a side, not a
team, so they are not this ship's call.
"""

import asyncio

import pytest

from app.routes.events import (
    _game_markets_cache,
    _leg_is_a_line_with_no_subject,
    get_game_markets,
)
from tests.test_leg_copy_parent_leaves_game_markets_5273 import (
    _db_for,
    _make_event,
    _make_market,
    _make_outcome,
    _rows,
)

PARENT_ID = 61294013
MATCHUP = "St. Louis Cardinals vs. Pittsburgh Pirates"

# The production specimen's legs, in stored order, with the live prices the
# issue quoted (the stored row is settled now; the O/U / NRFI prices are
# illustrative — only their names matter to the rule).
SPECIMEN_LEGS = [
    ("O/U 6.5", 0.81),
    ("O/U 7.5", 0.66),
    ("St. Louis Cardinals", 0.735),
    ("1st 5 Innings O/U 4.5", 0.40),
    ("1st 5 Innings O/U 5.5", 0.28),
    ("Spread -1.5", 0.63),
    ("O/U 8.5", 0.52),
    ("Spread -1.5", 0.125),
    ("NRFI", 0.45),
    ("Spread -2.5", 0.49),
]
BARE_LEGS = {"Spread -1.5", "Spread -2.5", "NRFI"}
#: #6799's cert-graded guard holds bare totals as real rungs; this ship leaves them.
TOTAL_LEGS = {"O/U 6.5", "O/U 7.5", "O/U 8.5", "1st 5 Innings O/U 4.5", "1st 5 Innings O/U 5.5"}


def _event(status):
    event = _make_event()
    event.id = 15317596
    event.status = status
    event.home_team_name = "Pittsburgh Pirates"
    event.away_team_name = "St. Louis Cardinals"
    return event


def _specimen():
    parent = _make_market(
        id=PARENT_ID,
        name=MATCHUP,
        external_id="1038122",
        market_type="field",
        group_id="polymarket:1038122",
    )
    legs = [
        _make_outcome(
            id=i + 1,
            market_id=PARENT_ID,
            name=name,
            probability=prob,
            external_id=f"0x{i + 1:064x}",
        )
        for i, (name, prob) in enumerate(SPECIMEN_LEGS)
    ]
    return [parent], legs


def _named_markets():
    """Standalone markets that NAME their line — the sections the rule must not touch."""
    spread = _make_market(
        id=70000001,
        name="Spread: St. Louis Cardinals (-1.5)",
        external_id="0x" + "a" * 64,
        group_id=None,
    )
    total = _make_market(
        id=70000002,
        name=f"{MATCHUP}: O/U 8.5",
        external_id="0x" + "b" * 64,
        group_id=None,
    )
    outcomes = [
        _make_outcome(id=101, market_id=spread.id, name="St. Louis Cardinals",
                      probability=0.63, external_id="0x" + "a" * 64 + "_yes"),
        _make_outcome(id=102, market_id=spread.id, name="Pittsburgh Pirates",
                      probability=0.37, external_id="0x" + "a" * 64 + "_no"),
        _make_outcome(id=103, market_id=total.id, name="Over",
                      probability=0.52, external_id="0x" + "b" * 64 + "_yes"),
        _make_outcome(id=104, market_id=total.id, name="Under",
                      probability=0.48, external_id="0x" + "b" * 64 + "_no"),
    ]
    return [spread, total], outcomes


def _payload(status="in_progress", *, with_named=False):
    _game_markets_cache.clear()
    event = _event(status)
    markets, outcomes = _specimen()
    if with_named:
        named, named_outcomes = _named_markets()
        markets += named
        outcomes += named_outcomes
    return asyncio.run(get_game_markets(event.id, _db_for(event, markets, outcomes)))


@pytest.fixture(autouse=True)
def clear_game_markets_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


class TestTheSpecimen:
    @pytest.mark.parametrize("status", ["scheduled", "in_progress"])
    def test_no_bare_line_leg_is_served(self, status):
        served = [r for r in _rows(_payload(status)) if r.get("outcome_name") in BARE_LEGS]
        assert served == [], f"a leg naming no team reached the page: {served}"

    @pytest.mark.parametrize("status", ["scheduled", "in_progress"])
    def test_the_parents_team_leg_keeps_its_card_and_price(self, status):
        """Control: the parent is still the group's only representation (#4189)."""
        other = _payload(status)["other"]
        legs = {(r.get("outcome_name"), r.get("probability"), r.get("_market_id")) for r in other}
        assert ("St. Louis Cardinals", 0.735, PARENT_ID) in legs, sorted(legs)

    @pytest.mark.parametrize("status", ["scheduled", "in_progress"])
    def test_the_bare_totals_are_left_to_6799(self, status):
        """Control on scope: only the team-less legs leave; every other leg is served."""
        served = {r.get("outcome_name") for r in _payload(status)["other"]}
        assert served == TOTAL_LEGS | {"St. Louis Cardinals"}, sorted(served)


class TestNamedLinesAreUntouched:
    def test_a_real_spread_market_still_fills_spreads(self):
        spreads = _payload(with_named=True)["spreads"]
        assert any(r.get("_market_id") == 70000001 for r in spreads), spreads

    def test_a_real_polymarket_total_still_fills_totals(self):
        totals = _payload(with_named=True)["totals"]
        assert any(r.get("_market_id") == 70000002 for r in totals), totals


class TestThePredicate:
    @pytest.mark.parametrize(
        "name",
        [
            # every team-less shape counted on production 2026-09-25 among
            # Polymarket container legs that name neither team
            "Spread -1.5",
            "Spread +2.5",
            "1H Spread -3.5",
            "1Q Spread -0.5",
            "1st 5 Innings Spread -1.5",
            "1H Moneyline",
            "Map 1 Winner",
            "Match Winner",
            "NRFI",
            "  spread -1.5 ",
        ],
    )
    def test_a_line_with_nothing_it_is_about(self, name):
        assert _leg_is_a_line_with_no_subject(name)

    @pytest.mark.parametrize(
        "name",
        [
            None,
            "",
            "St. Louis Cardinals",
            "St. Louis Cardinals -1.5",
            "Cardinals Spread -1.5",
            "Spread: SMU (-13.5)",
            "Over 8.5",
            "O/U 52.5",
            "1st 5 Innings O/U 4.5",
            "Total Corners: O/U 10.5",
            "Map 2 Total Rounds: Over/Under 21.5",
            "Under 8.5",
            "Draw",
            "Neither",
            "Both Teams to Score",
            "Both Teams to Score in First Half",
            "Extra Innings",
            "Any Other Score",
            "Completed Match",
            "Patrick Mahomes: 250+",
            "Team Liquid Map 1 Winner",
            "CA Platense 0 - 0 Estudiantes de La Plata",
        ],
    )
    def test_a_leg_that_names_something(self, name):
        assert not _leg_is_a_line_with_no_subject(name)
