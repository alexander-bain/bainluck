"""#6110 — a settled winning leg is not a reserved slot, so a finished race has a champion.

WHAT A READER SAW. The Vuelta a España 2026 finished on 2026-09-14. Our
Polymarket field for it (market ``58675941``, *Vuelta a Espana 2026: Winner*)
stored 30 riders, **every one of them correctly a loser**, and no champion:
``resolution_source='all_losers'`` on all 30, whose own producer comment says
out loud what happened — *"The winning outcome isn't in our DB"*. The
Settled-Concept Sentinel filed it as the Champion-hero contract broken: a Grand
Tour that finished, showing no winner.

WHO ACTUALLY WON, read at BOTH venues rather than inferred from our mirror
(standing notice 26), on 2026-09-15:

* Kalshi ``/markets?event_ticker=KXCYCLING-26VLTA`` — 184 settled markets,
  exactly one ``result='yes'``: ``KXCYCLING-26VLTA-EMAS``, **Enric Mas Nicolau**.
* Polymarket Gamma ``/events/815313`` — 71 markets, exactly one with
  ``outcomePrices[0] == "1"``: ``groupItemTitle='Other'``, *"Will any other
  rider win the 2026 Vuelta a Espana?"*.

The two agree: Enric Mas was not among Polymarket's 30 named riders, so the
venue's ``Other`` bucket is him. We hold the Kalshi champion correctly
(``59700067`` crowns Enric Mas, ``clean_resolution``); the Polymarket field lost
its winner at INGEST.

WHERE IT WENT. ``_is_placeholder_outcome``'s last heuristic — *"no trading
activity AND price is exactly 1.0"* — is a true statement about a market that
is still being made, and a false one about a market the venue has settled.
After settlement ``outcomePrices[0]`` is the RESULT, not a quote, and a winner
that never traded has no last trade to show for itself. The two shapes are
byte-identical at that line::

    reserved slot   closed=False  prices=["1","0"]  bid=0  lastTrade=0
    settled winner  closed=True   prices=["1","0"]  bid=0  lastTrade=0

so the champion was classified as a placeholder, ``_resolve_market_probability``
returned ``None``, and ``_parent_outcome_data`` dropped the leg from the write
set. Nothing downstream can recover it: ``_retire_unpriced_legs`` (#4000)
withdraws prices from rows we HOLD, the dark-market refresh only selects markets
with **no** outcome rows, and ``futures_price_refresh`` states in its own
docstring that it never creates outcomes. A leg dropped here is dropped for good.

THE DISCRIMINATOR is the venue's own ``closed`` flag, already parsed onto the
DTO. These tests pin both directions, because the heuristic is load-bearing for
the population it was built for (#953: ~44 open award/round-leader markets
leaking anonymised slots at 100%) and relaxing it wholesale would put those back
on the page.
"""

import pytest

from app.services.polymarket_api import PolymarketEvent, PolymarketMarket
from app.tasks.polymarket import (
    _is_placeholder_outcome,
    _parent_outcome_data,
    _resolve_market_probability_with_source,
)

#: The production specimen, field for field, as Gamma served it on 2026-09-15.
VUELTA_CHAMPION_LEG = {
    "condition_id": (
        "0x7ea6d1b641377841e13d0a7e5b6fa5fc70692704b212f47ad616fd2a3de0d543"
    ),
    "question": "Will any other rider win the 2026 Vuelta a Espana?",
    "group_item_title": "Other",
    "outcomes": ["Yes", "No"],
    "outcome_prices": [1.0, 0.0],
    "active": False,
    "closed": True,
    "best_bid": 0.0,
    "best_ask": 1.0,
    "last_trade_price": 0.0,
    "volume": 0.0,
    "liquidity": 0.0,
    "neg_risk": True,
}


def _leg(**overrides) -> PolymarketMarket:
    data = dict(VUELTA_CHAMPION_LEG)
    data.update(overrides)
    return PolymarketMarket(**data)


class TestTheSettledChampionIsAdmitted:
    """The defect, stated as the specimen that produced it."""

    def test_the_vuelta_champion_leg_is_not_a_placeholder(self):
        assert _is_placeholder_outcome(_leg()) is False

    def test_the_vuelta_champion_leg_prices_at_certainty(self):
        prob, _source = _resolve_market_probability_with_source(_leg())
        assert prob == pytest.approx(1.0), (
            "the venue settled this leg Yes; a champion priced None is dropped "
            "by _parent_outcome_data and the field ends with no winner"
        )

    def test_a_settled_loser_is_still_worth_nothing(self):
        """The other side of the same settlement must not become a champion."""
        prob, _source = _resolve_market_probability_with_source(
            _leg(group_item_title="Jonas Vingegaard", outcome_prices=[0.0, 1.0])
        )
        assert prob is None or prob <= 0


class TestTheHeuristicStillHoldsWhereItWasEarned:
    """#953's population is the reason this filter exists; it must not move."""

    def test_an_open_untraded_leg_at_one_is_still_a_placeholder(self):
        """The ONLY thing that changed is ``closed``. Flip it back, defect back."""
        assert _is_placeholder_outcome(_leg(closed=False, active=True)) is True

    def test_an_open_untraded_leg_at_one_is_still_unpriced(self):
        prob, source = _resolve_market_probability_with_source(
            _leg(closed=False, active=True)
        )
        assert (prob, source) == (None, None)

    @pytest.mark.parametrize("name", ["Player B", "Player AD", "Player XX"])
    def test_a_settled_anonymised_slot_is_still_suppressed(self, name):
        """The name patterns run first and unconditionally — closed or not.

        A reserved slot names no rider, so crowning one would print a champion a
        reader cannot read. This is why the fix is keyed on ``closed`` INSTEAD of
        loosening the name rules, not as well as.
        """
        assert _is_placeholder_outcome(_leg(group_item_title=name)) is True
        assert _is_placeholder_outcome(
            _leg(group_item_title=None, question=f"Will {name} win the race?")
        ) is True

    def test_a_traded_favorite_was_never_affected_either_way(self):
        for closed in (True, False):
            leg = _leg(closed=closed, best_bid=0.97, last_trade_price=0.98)
            assert _is_placeholder_outcome(leg) is False

    def test_an_object_without_a_closed_field_keeps_the_old_behaviour(self):
        """``getattr`` default — a duck-typed caller must not gain the carve-out.

        Fail-safe direction: absent information reads as "not settled", which is
        exactly what this function did before #6110.
        """

        class _NoClosedField:
            group_item_title = "Other"
            question = "Will any other rider win?"
            outcome_prices = [1.0, 0.0]
            best_bid = 0.0
            best_ask = 1.0
            last_trade_price = 0.0

        assert _is_placeholder_outcome(_NoClosedField()) is True


class TestTheFieldTheReaderGets:
    """End to end over the write set, because a leg admitted is not a leg written."""

    @staticmethod
    def _vuelta_event() -> PolymarketEvent:
        """The venue's 71-leg partition: 30 named riders + Other + 40 unused slots."""
        named = [
            "Tadej Pogacar", "Jonas Vingegaard", "Remco Evenepoel",
            "Mathieu van der Poel", "Isaac Del Toro", "Paul Seixas",
            "Lenny Martinez", "Jasper Philipsen", "Tobias Johannessen",
            "Wout van Aert", "Florian Lipowitz", "Brady Gilmore",
            "Mattias Skjelmose", "Christophe Laporte", "Jonathan Milan",
            "Tobias Lund Andresen", "Mads Pedersen", "Richard Carapaz",
            "Laurence Pithie", "Sam Welsford", "Mauro Schmid", "Ben Tulett",
            "Thomas Pidcock", "Jasper Stuyven", "Felix Gall",
            "Florian Vermeersch", "Romain Gregoire", "Pello Bilbao",
            "Christian Scaroni", "Juan Ayuso",
        ]
        markets = [
            # Every named rider lost: the venue settles them to 0.
            _leg(
                condition_id=f"0xnamed{i}",
                group_item_title=rider,
                question=f"Will {rider} win the 2026 Vuelta a Espana?",
                outcome_prices=[0.0, 1.0],
            )
            for i, rider in enumerate(named)
        ] + [
            _leg(),  # "Other" — the champion
        ] + [
            # The 40 unused reserved slots, settled to 0 like any other loser.
            _leg(
                condition_id=f"0xslot{i}",
                group_item_title=f"Rider {i}",
                question=f"Will Rider {i} win the 2026 Vuelta a Espana?",
                outcome_prices=[0.0, 1.0],
            )
            for i in range(1, 41)
        ]
        return PolymarketEvent(
            id="815313",
            title="Vuelta a Espana 2026: Winner",
            slug="cycling-vuelta-a-espana-winner-2026-08-21",
            closed=True,
            active=False,
            neg_risk=True,
            markets=markets,
        )

    def test_the_champion_is_in_the_write_set(self):
        rows = _parent_outcome_data(self._vuelta_event())
        by_name = {r["name"]: r for r in rows}
        assert "Other" in by_name, (
            "the leg the venue resolved Yes must reach the write set, or the "
            "settled field has no champion to crown"
        )
        assert by_name["Other"]["prob"] == pytest.approx(1.0)
        assert by_name["Other"]["external_id"] == VUELTA_CHAMPION_LEG["condition_id"]

    def test_exactly_one_champion_and_no_reserved_slots(self):
        """A single-winner partition writes one certainty, and no junk beside it.

        The 40 unused slots are dropped here by the caller's own ``prob <= 0``
        test rather than by the placeholder filter — which is why relaxing that
        filter for settled legs does not flood a resolved field.
        """
        rows = _parent_outcome_data(self._vuelta_event())
        certain = [r for r in rows if r["prob"] >= 0.995]
        assert len(certain) == 1, [r["name"] for r in certain]
        assert certain[0]["name"] == "Other"
        assert not [r for r in rows if str(r["name"]).startswith("Rider ")]

    def test_the_same_event_while_still_racing_writes_no_champion(self):
        """Mid-race the venue quotes real prices and ``Other`` is untraded at 1.0.

        This is the state the old heuristic was written for, and it must still
        produce no 100% leg — otherwise the fix would put a phantom favourite on
        a live page, which is #953 exactly.
        """
        event = self._vuelta_event()
        live_markets = []
        for m in event.markets:
            if m.group_item_title == "Other":
                live_markets.append(
                    _leg(closed=False, active=True)
                )
            elif m.group_item_title == "Tadej Pogacar":
                live_markets.append(
                    _leg(
                        condition_id=m.condition_id,
                        group_item_title="Tadej Pogacar",
                        closed=False,
                        active=True,
                        outcome_prices=[0.41, 0.59],
                        best_bid=0.40,
                        best_ask=0.42,
                        last_trade_price=0.41,
                    )
                )
        live = PolymarketEvent(
            id="815313",
            title="Vuelta a Espana 2026: Winner",
            closed=False,
            active=True,
            neg_risk=True,
            markets=live_markets,
        )
        rows = _parent_outcome_data(live)
        assert [r["name"] for r in rows] == ["Tadej Pogacar"]
        assert not [r for r in rows if r["prob"] >= 0.995]
