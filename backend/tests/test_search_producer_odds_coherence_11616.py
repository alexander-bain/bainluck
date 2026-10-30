"""#11616: the search producer never emits odds beside a null probability.

lane1b's synthetic-seed disposition: the non-lean builder emitted
``american_odds=row["american_odds"]`` unconditionally, so a leg whose stored
price is NULL while ``current_american_odds`` is not reached the wire as
``probability null, american_odds 110`` — attested by the producer and then
refused by the cache validator (``is_current_represented_futures_row``), which
demoted the producer's own fresh card to legacy on a hit and stripped an open
board's ``false/api_settlement`` loser.

No reviewed writer stores that residue (every NULL-price write nulls the odds),
so this is a defensive producer guard, not a live incident: odds follow the
served probability, and the producer's card round-trips through the cache
adapter unchanged — attestation, winner and loser metadata included.
"""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.routes import events
from app.utils.search_cache import (
    SEARCH_FUTURES_REPRESENTATION_POLICY_KEY,
    adapt_cached_futures_row,
    is_current_represented_futures_row,
)

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)
SEEN = datetime(2026, 10, 27, 14, 0, tzinfo=timezone.utc)


def _leg(i, name, p, odds, *, is_winner=False, src=None):
    return SimpleNamespace(
        id=i, name=name, external_id=f"KXODDS-{i}", current_probability=p,
        current_yes_bid=None if p is None else max(0, p - 0.01),
        current_yes_ask=None if p is None else min(1, p + 0.01),
        current_american_odds=odds, rank=i, rank_change_24h=None,
        probability_change_24h=None, opening_probability=None,
        opening_american_odds=None, is_winner=is_winner, resolution_source=src,
        last_updated=SEEN, price_changed_at=None,
    )


def _market(legs, *, status="open"):
    return SimpleNamespace(
        id=116161, name="NBA MVP", description=None, category="award",
        source="kalshi", external_id="KXNBAMVP-27", status=status,
        sport=SimpleNamespace(id=1, key="basketball_nba", name="NBA"), sport_id=1,
        event_id=None, market_type="award", market_tier=3,
        llm_sport_category="basketball", mutually_exclusive=True, commence_time=None,
        resolution_date=datetime(2027, 6, 1, tzinfo=timezone.utc), created_at=None,
        updated_at=SEEN, group_id=None, canonical_market_key=None,
        hook_description=None, image_url=None, category_tags=[],
        market_metadata=None, outcomes=legs,
    )


CASES = {
    # The residue: priceless open Kalshi board (gotcha #33 keeps it `open`) whose
    # stored odds outlived the price; a supported winner and a graded loser.
    "residue_null_price_stored_odds": _market([
        _leg(1, "Victor Wembanyama", None, 110, is_winner=True, src="api_settlement"),
        _leg(2, "Shai Gilgeous-Alexander", None, 110, is_winner=False, src="api_settlement"),
    ]),
    "coherent_null_price_null_odds": _market([
        _leg(1, "Victor Wembanyama", None, None, is_winner=True, src="api_settlement"),
        _leg(2, "Shai Gilgeous-Alexander", None, None, is_winner=False, src="api_settlement"),
    ]),
    "priced": _market([
        _leg(1, "Victor Wembanyama", 0.55, -122),
        _leg(2, "Shai Gilgeous-Alexander", 0.45, 122),
    ]),
    # Kalshi graders write 1.0/0.0 with odds NULL.
    "settled_terminal_odds_null": _market([
        _leg(1, "Victor Wembanyama", 1.0, None, is_winner=True, src="api_settlement"),
        _leg(2, "Shai Gilgeous-Alexander", 0.0, None, is_winner=False, src="api_settlement"),
    ], status="resolved"),
}


def _produce(market):
    with patch.object(events, "_search_now", lambda: NOW):
        return events._format_futures_for_search(market)


@pytest.mark.parametrize("case", sorted(CASES))
def test_odds_follow_the_served_probability(case):
    card = _produce(CASES[case])
    assert card["top_outcomes"], case
    for row in card["top_outcomes"]:
        if row["probability"] is None:
            assert row["american_odds"] is None, (case, row)


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_producers_card_round_trips_through_the_cache_unchanged(case):
    card = _produce(CASES[case])
    assert card.get(SEARCH_FUTURES_REPRESENTATION_POLICY_KEY), case
    assert is_current_represented_futures_row(card), case
    assert adapt_cached_futures_row(deepcopy(card)) == card


def test_the_residue_keeps_its_winner_and_its_graded_loser():
    card = _produce(CASES["residue_null_price_stored_odds"])
    results = {r["name"]: (r["is_winner"], r["resolution_source"]) for r in card["top_outcomes"]}
    assert results == {
        "Victor Wembanyama": (True, "api_settlement"),
        "Shai Gilgeous-Alexander": (False, "api_settlement"),
    }
    adapted = adapt_cached_futures_row(deepcopy(card))
    assert {r["name"]: (r["is_winner"], r["resolution_source"]) for r in adapted["top_outcomes"]} == results


def test_control_a_priced_row_keeps_its_odds():
    card = _produce(CASES["priced"])
    assert {r["name"]: r["american_odds"] for r in card["top_outcomes"]} == {
        "Victor Wembanyama": -122, "Shai Gilgeous-Alexander": 122,
    }
