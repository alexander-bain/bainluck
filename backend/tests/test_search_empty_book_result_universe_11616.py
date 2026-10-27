"""#11616 F5 + O2: card predicates and the builder judge results on ONE leg set.

lane1b's interim review (probe P4): ``_futures_card_has_no_answer`` kept a card
because a supported result existed among the eligible legs, while the builder
had dropped that leg as an empty-book midpoint (#6676) — so ``/search`` served
the card with ``top_outcomes == []``. Base withdrew it; detail shows the result.

The repair keeps the card AND draws the result: a supported result on an empty
book is served result-only, never with the book's manufactured 0.50. An
ungraded empty-book leg is still not a price and still never drawn.

O2: ``_search_market_is_past_and_frozen`` now judges results with the division
labels its caller holds, so a result the grid has put out cannot keep a frozen
board's stale prices on the page.
"""

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.routes import events, futures

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)
SEEN = NOW - timedelta(hours=1)


def _leg(i, name, p, *, bid, ask, is_winner=None, src=None, last=SEEN):
    return SimpleNamespace(
        id=i, name=name, external_id=f"F5-{i}", current_probability=p,
        current_yes_bid=bid, current_yes_ask=ask, current_american_odds=None,
        rank=i, rank_change_24h=None, probability_change_24h=None,
        opening_probability=None, opening_american_odds=None,
        is_winner=is_winner, resolution_source=src, last_updated=last,
        price_changed_at=None,
    )


def _board(legs, *, status, external_id="F5-probe"):
    return SimpleNamespace(
        id=990051, name="Probe empty-book board", description=None,
        category="championship", source="kalshi", external_id=external_id,
        status=status, sport=None, sport_id=None, event_id=None, market_type=None,
        market_tier=5, llm_sport_category="politics", mutually_exclusive=True,
        commence_time=None, resolution_date=datetime(2099, 1, 1, tzinfo=timezone.utc),
        created_at=None, updated_at=None, group_id=None, canonical_market_key=None,
        hook_description=None, image_url=None, category_tags=[],
        market_metadata=None, outcomes=legs,
    )


def _surfaces(market, **kw):
    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    original = deepcopy(market)
    with ExitStack() as stack:
        for module in (events, futures):
            stack.enter_context(patch.object(module, "datetime", _Fixed))
        kept = not events._futures_card_has_no_answer(market, set(), **kw)
        card = list(events._build_search_top_outcomes(market, limit=5, lean=False, **kw))
        typeahead = list(events._build_search_top_outcomes(market, limit=3, lean=True, **kw))
    assert market == original
    return kept, card, typeahead


def _p4(status):
    # P4 verbatim: graded Kalshi legs whose stored price is a 0.01/0.99 midpoint.
    return _board(
        [
            _leg(1, "Alpha Example", 0.50, bid=0.01, ask=0.99, is_winner=True, src="api_settlement"),
            _leg(2, "Beta Example", 0.50, bid=0.01, ask=0.99, is_winner=False, src="api_settlement"),
        ],
        status=status,
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        # open: only `Won` prints (#6082); the graded loser keeps no number to show.
        ("open", [("Alpha Example", True)]),
        ("resolved", [("Alpha Example", True), ("Beta Example", False)]),
    ],
)
def test_a_kept_card_draws_its_empty_book_result_and_never_the_midpoint(status, expected):
    kept, card, typeahead = _surfaces(_p4(status))
    assert kept
    assert card, "a card kept for its result must never be served with no rows"
    for rows in (card, typeahead):
        assert [(r["name"], r["is_winner"]) for r in rows] == expected
        for row in rows:
            assert row["resolution_source"] == "api_settlement"
            assert row["probability"] is None and row["rendered_percent"] is None
            assert row["movement"] is None
    for row in card:
        assert row["american_odds"] is None and row["rank"] is None


def test_predicates_and_builder_name_the_same_results():
    for status in ("open", "resolved"):
        market = _p4(status)
        _, card, _ = _surfaces(market)
        drawn = {r["id"] for r in card if r["is_winner"] is not None}
        assert events._search_card_result_ids(market) == drawn


def test_control_an_ungraded_empty_book_board_is_still_withdrawn_and_drawn_empty():
    market = _board(
        [
            _leg(1, "Alpha Example", 0.50, bid=0.01, ask=0.99),
            _leg(2, "Beta Example", 0.50, bid=0.01, ask=0.99),
        ],
        status="open",
    )
    kept, card, typeahead = _surfaces(market)
    assert not kept
    assert card == [] and typeahead == []


def test_control_a_real_price_beside_an_empty_book_result_keeps_its_number():
    market = _board(
        [
            _leg(1, "Alpha Example", 0.50, bid=0.01, ask=0.99, is_winner=True, src="api_settlement"),
            _leg(2, "Gamma Example", 0.30, bid=0.29, ask=0.31),
        ],
        status="open",
    )
    _, card, _ = _surfaces(market)
    by_name = {r["name"]: r for r in card}
    assert by_name["Alpha Example"]["probability"] is None
    assert by_name["Gamma Example"]["probability"] is not None


def test_o2_a_result_the_grid_put_out_does_not_keep_a_frozen_board():
    april = datetime(2026, 4, 17, 20, 0, tzinfo=timezone.utc)
    market = _board(
        [
            _leg(1, "AL East", 0.995, bid=0.99, ask=1.0, is_winner=True, src="api_settlement", last=april),
            _leg(2, "AL Central", 0.995, bid=0.99, ask=1.0, last=april),
            _leg(3, "AL West", 0.995, bid=0.99, ask=1.0, last=april),
        ],
        status="open",
        external_id="KXEARNINGSMENTIONTFC-26APR17",
    )
    labels = frozenset({"al east"})
    assert not events._search_market_is_past_and_frozen(market, now=NOW)
    assert events._search_market_is_past_and_frozen(market, now=NOW, out_division_labels=labels)
    assert events._futures_card_has_no_answer(market, set(), out_division_labels=labels)


def test_r_o2_a_result_the_grid_put_out_does_not_keep_a_wholly_refused_board():
    # lane1b R-O2: `_futures_card_has_no_answer` judged results with the labels,
    # but its #8661 arm re-asked WITHOUT them, so a board whose only supported
    # result sits on a leg the grid put out kept a ladder of refused prices.
    market = _board(
        [
            _leg(1, "AL East", 0.60, bid=0.59, ask=0.61, is_winner=True, src="api_settlement"),
            _leg(2, "AL Central", 0.25, bid=0.24, ask=0.26),
            _leg(3, "AL West", 0.15, bid=0.14, ask=0.16),
        ],
        status="open",
    )
    labels = frozenset({"al east"})
    withheld = {1, 2, 3}
    assert events._futures_market_prices_all_withheld(market, withheld, out_division_labels=labels)
    assert events._futures_card_has_no_answer(market, withheld, out_division_labels=labels)
    # Control: with no division verdict the supported result keeps the card.
    assert not events._futures_card_has_no_answer(market, withheld)
    # Control: a refusal that leaves one priced leg withdraws nothing.
    assert not events._futures_card_has_no_answer(market, {1, 2}, out_division_labels=labels)
