"""#4614 / #5059 T2-2 — the headline reservation runs BENEATH the entity block.

WHAT WAS WRONG, MEASURED ON PRODUCTION (lane1/245, 2026-09-11, `?debug_evidence=true`
with the classes recomputed locally through the module's own wire form):

    q=yankees
      0  mc=4  key=(4,4,1,0.0)  futures  MLB World Series Champion 2026
      1  mc=0  key=(0,2,0,0.0)  team     New York Yankees
      2  mc=1  key=(1,3,0,0.0)  event    New York Mets at New York Yankees
      …
    q=red sox   — the same shape, the same MC4 row in slot 0.

`reserve_headline_slot` ended in `return front + rest`, an UNCONDITIONAL hoist, so
the worst-classed row on the page took slot 0 from the team card whose name the
user had typed in full. #5059's decision B: "a later headline promotion can never
override entity/game ordering."

WHY THESE TESTS DRIVE THE REAL SCORER rather than hand-building a ranked page.
The defect is not in either function alone — each behaved as written. It is in the
COMPOSITION the route performs: rank, measure the entity block, reserve beneath it.
A test that hand-orders a list asserts the fixture, and would have stayed green
through the bug (the pre-fix page really was `[futures, team, event]` — correct
output for the input the old call site gave it). So every test here starts from
`Evidence` and runs the three steps in the route's own order.

RED-FIRST, both operative lines, verified by reverting each in place:
  * `reserve_headline_slot`'s `rest[:floor] + front + rest[floor:]` -> `front + rest`
    fails `test_a_fully_typed_team_keeps_slot_zero_over_its_championship_market`
    and the `red sox` case.
  * `entity_prefix_len`'s `> ENTITY_KIND_MAX_RANK` -> `> 99` fails
    `test_the_contender_still_leads_when_no_entity_resolved_cert_718`.
"""

import pytest

from app.utils.search_headline_contender import reserve_headline_slot
from app.utils.search_match_class import (
    ENTITY_EVENT_KIND,
    ENTITY_TEAM_KIND,
    Evidence,
    entity_prefix_len,
    rank_with_keys,
)

WS_MARKET_ID = 90001
PROP_MARKET_ID = 90002


def _team(name, *aliases):
    return Evidence(name=name, aliases=tuple(aliases), kind=ENTITY_TEAM_KIND)


def _game(name):
    return Evidence(name=name, kind=ENTITY_EVENT_KIND)


def _futures(name, market_id, *, outcomes=(), kind="futures"):
    return Evidence(name=name, outcomes=tuple(outcomes), kind=kind)


def _compose(query, candidates, headline_ids):
    """Exactly what `typeahead_search` does, in its order, minus the [:7] slice."""
    keyed = rank_with_keys(query, candidates)
    return reserve_headline_slot(
        [payload for _key, payload in keyed],
        headline_ids,
        floor=entity_prefix_len(keyed),
    )


def _yankees_page():
    """The production shape above, as `(evidence, payload)` pairs."""
    return [
        (
            _futures(
                "MLB World Series Champion 2026",
                WS_MARKET_ID,
                outcomes=("New York Yankees", "Los Angeles Dodgers"),
            ),
            {"type": "futures", "text": "MLB World Series Champion 2026",
             "market_id": WS_MARKET_ID},
        ),
        (
            _team("New York Yankees", "Yankees", "NYY"),
            {"type": "team", "text": "New York Yankees"},
        ),
        (
            _game("New York Mets at New York Yankees"),
            {"type": "event", "text": "New York Mets at New York Yankees"},
        ),
        (
            _futures(
                "New York Mets vs. New York Yankees - Player Props", PROP_MARKET_ID
            ),
            {"type": "futures",
             "text": "New York Mets vs. New York Yankees - Player Props",
             "market_id": PROP_MARKET_ID},
        ),
    ]


class TestTheEntityBlockOutranksTheReservation:
    def test_the_fixture_reproduces_the_measured_classes(self):
        """Fence: if the fixture stops matching production, the tests below are
        asserting something else and must not read as a pass for #4614."""
        keyed = rank_with_keys("yankees", _yankees_page())
        classes = [(k[1], k[2]) for k, _ in keyed]  # (mc, kind_rank)
        assert classes == [(0, 2), (1, 3), (1, 4), (4, 4)], classes

    def test_a_fully_typed_team_keeps_slot_zero_over_its_championship_market(self):
        out = _compose("yankees", _yankees_page(), {WS_MARKET_ID})
        assert [r["type"] for r in out] == ["team", "event", "futures", "futures"]
        assert out[0]["text"] == "New York Yankees"

    def test_the_championship_market_is_still_reserved_above_the_props(self):
        """The reservation is moved, not removed: the contender still outranks
        every prop, which is the whole reason the function exists."""
        out = _compose("yankees", _yankees_page(), {WS_MARKET_ID})
        ids = [r.get("market_id") for r in out]
        assert ids.index(WS_MARKET_ID) < ids.index(PROP_MARKET_ID)

    def test_the_game_keeps_its_slot_behind_its_own_team(self):
        out = _compose("yankees", _yankees_page(), {WS_MARKET_ID})
        assert out[1]["text"] == "New York Mets at New York Yankees"

    def test_red_sox_the_second_measured_specimen(self):
        candidates = [
            (
                _futures("MLB World Series Champion 2026", WS_MARKET_ID,
                         outcomes=("Boston Red Sox",)),
                {"type": "futures", "text": "MLB World Series Champion 2026",
                 "market_id": WS_MARKET_ID},
            ),
            (
                _team("Boston Red Sox", "Red Sox", "BOS"),
                {"type": "team", "text": "Boston Red Sox"},
            ),
            (
                _game("Kansas City Royals at Boston Red Sox"),
                {"type": "event", "text": "Kansas City Royals at Boston Red Sox"},
            ),
        ]
        out = _compose("red sox", candidates, {WS_MARKET_ID})
        assert [r["type"] for r in out] == ["team", "event", "futures"]

    def test_every_row_survives_the_reservation(self):
        """Length and membership are invariants — the reservation reorders."""
        page = _yankees_page()
        out = _compose("yankees", page, {WS_MARKET_ID})
        assert len(out) == len(page)
        assert sorted(r["text"] for r in out) == sorted(p["text"] for _e, p in page)


class TestTheOriginCaseIsUnchanged:
    """CERT-718's shape: a player query, no team row, props first and the winner
    market sunk below them. There is no entity block, so the floor is 0 and the
    hoist is exactly what it was."""

    def _sabalenka_page(self):
        rows = [
            (
                _futures(f"Aryna Sabalenka vs. Iga Swiatek - Total Games {i}",
                         100 + i),
                {"type": "futures",
                 "text": f"Aryna Sabalenka vs. Iga Swiatek - Total Games {i}",
                 "market_id": 100 + i},
            )
            for i in range(4)
        ]
        rows.append(
            (
                _futures("US Open Women's Winner", WS_MARKET_ID,
                         outcomes=("Aryna Sabalenka",)),
                {"type": "futures", "text": "US Open Women's Winner",
                 "market_id": WS_MARKET_ID},
            )
        )
        return rows

    def test_the_contender_still_leads_when_no_entity_resolved_cert_718(self):
        page = self._sabalenka_page()
        assert entity_prefix_len(rank_with_keys("sabalenka", page)) == 0
        out = _compose("sabalenka", page, {WS_MARKET_ID})
        assert out[0]["market_id"] == WS_MARKET_ID

    def test_a_weaker_classed_team_row_does_not_shield_the_props(self):
        """The floor is the SCORER's entity block, not "is there a team row".
        A team the query only fragment-matches ranks BELOW the contender, so it
        is not part of the leading block and must not push the contender down —
        the `fed` -> "Fed..." hazard the reservation's docstring names."""
        page = self._sabalenka_page()
        page.append(
            (
                Evidence(name="Sabal Palms FC", kind="team"),
                {"type": "team", "text": "Sabal Palms FC"},
            )
        )
        out = _compose("sabalenka", page, {WS_MARKET_ID})
        assert out[0]["market_id"] == WS_MARKET_ID


class TestTheFloorIsTotal:
    @pytest.mark.parametrize("floor", [0, 1, 5, 99, -3])
    def test_any_floor_preserves_length_and_membership(self, floor):
        ranked = [
            {"type": "team", "text": "t"},
            {"type": "event", "text": "e"},
            {"type": "futures", "text": "f", "market_id": WS_MARKET_ID},
        ]
        out = reserve_headline_slot(ranked, {WS_MARKET_ID}, floor=floor)
        assert len(out) == len(ranked)
        assert sorted(r["text"] for r in out) == ["e", "f", "t"]

    def test_floor_zero_is_the_previous_behaviour(self):
        ranked = [
            {"type": "team", "text": "t"},
            {"type": "futures", "text": "f", "market_id": WS_MARKET_ID},
        ]
        assert reserve_headline_slot(ranked, {WS_MARKET_ID}, floor=0) == [
            {"type": "futures", "text": "f", "market_id": WS_MARKET_ID},
            {"type": "team", "text": "t"},
        ]

    def test_a_floor_past_the_end_leaves_the_page_alone(self):
        ranked = [
            {"type": "team", "text": "t"},
            {"type": "futures", "text": "f", "market_id": WS_MARKET_ID},
        ]
        assert reserve_headline_slot(ranked, {WS_MARKET_ID}, floor=99) == ranked

    def test_an_empty_entity_prefix_on_an_empty_page(self):
        assert entity_prefix_len([]) == 0

    def test_a_key_too_short_to_carry_a_kind_stops_the_scan(self):
        assert entity_prefix_len([((0,), {"type": "team"})]) == 0


class TestRankStillAgreesWithRankWithKeys:
    """`rank` is now a projection of `rank_with_keys`; a divergence would mean the
    page the user sees and the keys the floor is measured from came from two
    different orderings."""

    def test_the_two_orderings_are_the_same_object_sequence(self):
        from app.utils.search_match_class import rank

        page = _yankees_page()
        assert rank("yankees", page) == [p for _k, p in rank_with_keys("yankees", page)]
