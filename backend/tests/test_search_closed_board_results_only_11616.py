"""#11616 O1: a closed, frozen board is kept for its result and shows ONLY that.

#8852 withdrew a Kalshi board whose ticker date had passed and whose prices had
stopped: its `>99%` rows were April's legs printed as live. This PR keeps such
a board when it carries a supported result (settled means settled), which
lane1b's interim review flagged as a relevance change (O1). Disposition:

* truth — the card draws only the supported result; the board's other legs'
  frozen prices are never drawn as live answers to a closed question;
* relevance — the promoted headline never takes a closed, frozen board, result
  or not (pinned by name in `test_search_withdraws_the_closed_frozen_board_8852`).
"""

from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.routes import events

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)
APRIL = datetime(2026, 4, 17, 20, 0, tzinfo=timezone.utc)


def _leg(i, name, p, *, last, is_winner=None, src=None):
    return SimpleNamespace(
        id=i, name=name, external_id=f"O1-{i}", current_probability=p,
        current_yes_bid=max(0, p - 0.005), current_yes_ask=min(1, p + 0.005),
        current_american_odds=None, rank=i, rank_change_24h=None,
        probability_change_24h=None, opening_probability=None,
        opening_american_odds=None, is_winner=is_winner, resolution_source=src,
        last_updated=last, price_changed_at=None,
    )


def _board(last):
    # #8852's shape: KXEARNINGSMENTION…-26APR17, still stored open (gotcha #33),
    # one leg graded a winner and the rest frozen near-certain.
    return SimpleNamespace(
        id=990061, name="What will Truist Financial say during their next earnings call?",
        description=None, category="economics", source="kalshi",
        external_id="KXEARNINGSMENTIONTFC-26APR17", status="open", sport=None,
        sport_id=None, event_id=None, market_type=None, market_tier=3,
        llm_sport_category="economics", mutually_exclusive=False, commence_time=None,
        resolution_date=datetime(2099, 1, 1, tzinfo=timezone.utc), created_at=None,
        updated_at=None, group_id=None, canonical_market_key=None,
        hook_description=None, image_url=None, category_tags=[], market_metadata=None,
        outcomes=[
            _leg(1, "Recession", 0.995, last=last, is_winner=True, src="api_settlement"),
            _leg(2, "Tariff", 0.99, last=last),
            _leg(3, "Deposits", 0.985, last=last),
        ],
    )


def _read(market):
    # Pin search's one clock (#11616 F1), not `events.datetime`: a datetime
    # subclass swapped into the module makes `_newest_price_stamp`'s isinstance
    # check refuse every real stamp, and the board reads as "cannot say".
    with ExitStack() as stack:
        stack.enter_context(patch.object(events, "_search_now", lambda: NOW))
        kept = not events._futures_card_has_no_answer(market, set())
        card = list(events._build_search_top_outcomes(market, limit=5, lean=False))
        typeahead = list(events._build_search_top_outcomes(market, limit=3, lean=True))
    return kept, card, typeahead


def test_a_closed_frozen_board_with_a_result_shows_only_the_result():
    market = _board(APRIL)
    assert events._search_market_is_closed_and_frozen(market, NOW)
    assert not events._search_market_is_past_and_frozen(market, NOW)
    kept, card, typeahead = _read(market)
    assert kept
    for rows in (card, typeahead):
        assert [(r["name"], r["is_winner"]) for r in rows] == [("Recession", True)]


def test_control_the_same_board_still_trading_keeps_its_live_prices():
    market = _board(NOW.replace(hour=14))
    assert not events._search_market_is_closed_and_frozen(market, NOW)
    _, card, _ = _read(market)
    priced = {r["name"] for r in card if r["probability"] is not None}
    assert {"Tariff", "Deposits"} <= priced
