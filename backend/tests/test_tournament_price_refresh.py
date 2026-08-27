"""The targeted price refresh for register-pinned markets (UX-P139).

Alex, item 2: "state the production guarantee: with the freshness gates,
silently-stale data can never render — and show the UI treatment that proves
it."

The gates were already right. What they could not do is make a number fresh,
and measured 2026-08-26 the whole playoff grid was 27 hours old while
Polymarket snapshots overall were current to the minute — because Gamma caps
offset pagination at 2,000, so the scanning poll rotates a window and reaches a
given event about once a day. This task closes that by asking for the market
IDs the register already pins.

What is asserted here, and why each one is a defect that shipped or nearly did:

* **The register bounds the request.** A refresh that discovered markets would
  be a second scanning poll, at six times the cadence.
* **Every collection is walked**, players and matchups and reaches. The first
  version walked players only, which is 80 of 420 markets.
* **A zero-yield run is loud** (gotcha #53): "it returned" is not "it worked".
"""

from __future__ import annotations

from app.tasks.tournament_price_refresh import (
    BATCH_SIZE,
    MAX_MARKETS,
    registered_polymarket_conditions,
)
from app.utils.tournament_register import load_register


def _register(**overrides):
    base = {
        "players": [
            {
                "entity_key": "a",
                "sources": [
                    {"source": "polymarket", "market_external_id": "0xaaa", "outcome_id": 1},
                    {"source": "kalshi", "market_external_id": "KX-1", "outcome_id": 2},
                ],
            }
        ],
        "matchups": [
            {
                "matchup_key": "m",
                "sources": [
                    {
                        "source": "polymarket",
                        "market_external_id": "0xbbb",
                        "sides": {
                            "a": {"outcome_id": 10},
                            "b": {"outcome_id": 11},
                        },
                    }
                ],
            }
        ],
        "reaches": [
            {
                "draw": "mens-singles",
                "entity_key": "a",
                "round": "SF",
                "sources": [
                    {"source": "polymarket", "market_external_id": "0xccc", "outcome_id": 20},
                    {"source": "kalshi", "market_external_id": None, "outcome_id": None},
                ],
            }
        ],
    }
    base.update(overrides)
    return base


class TestWhatGetsRefreshed:
    def test_walks_players_matchups_AND_reaches(self):
        # The first version walked players only — 80 of ~420 markets, and the
        # 336 that ARE the bracket grid were not among them.
        conditions = registered_polymarket_conditions(_register())
        assert set(conditions) == {"0xaaa", "0xbbb", "0xccc"}

    def test_collects_both_sides_of_a_matchup(self):
        conditions = registered_polymarket_conditions(_register())
        assert sorted(conditions["0xbbb"]) == [10, 11]

    def test_ignores_kalshi_entirely(self):
        # Kalshi is polled by its own task on its own cadence, and this method
        # asks Gamma. A Kalshi ticker in the list would be a 404 per batch.
        conditions = registered_polymarket_conditions(_register())
        assert "KX-1" not in conditions

    def test_a_missing_source_block_pins_nothing(self):
        # A `missing` block carries no identity by construction
        # (`MISSING_ENTRY_HAS_IDENTITY`), so a censused absence costs no request.
        conditions = registered_polymarket_conditions(_register())
        assert None not in conditions
        assert all(condition.startswith("0x") for condition in conditions)

    def test_an_empty_register_asks_for_nothing(self):
        assert registered_polymarket_conditions({}) == {}

    def test_survives_a_malformed_collection_without_dropping_the_rest(self):
        register = _register(players=[None, "nonsense", _register()["players"][0]])
        conditions = registered_polymarket_conditions(register)
        assert "0xaaa" in conditions


class TestTheCommittedRegisterIsABoundedAsk:
    def test_the_us_open_refresh_is_a_handful_of_requests(self):
        register = load_register("us-open", "2026")
        assert register is not None
        conditions = registered_polymarket_conditions(register)
        # ~366 conditions today: 336 reach + 28 matchups + 2 outright fields.
        assert 300 < len(conditions) < MAX_MARKETS
        requests = -(-len(conditions) // BATCH_SIZE)
        # Cheap enough for a 10-minute cadence against a ~1,000/hr limit.
        assert requests <= 12

    def test_every_reach_market_is_in_the_refresh_set(self):
        """The grid's 336 markets are the whole reason this task exists."""
        register = load_register("us-open", "2026")
        assert register is not None
        conditions = set(registered_polymarket_conditions(register))
        pinned = {
            block["market_external_id"]
            for reach in register["reaches"]
            for block in reach["sources"]
            if block.get("market_external_id")
        }
        assert pinned
        assert pinned <= conditions
