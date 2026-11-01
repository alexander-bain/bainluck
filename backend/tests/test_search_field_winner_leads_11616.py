"""#11616 F2: a settled Field/Other winner leads search exactly as it leads detail.

lane1b's interim review (probe P2): detail's representation orders with its
graded-winner rule, but search called ``_leader_pick_order(out)`` with none, so
``demote_dominant_field`` sent a settled "Other" at 1.0 to the end. The web
dropdown (``answers[0]``) then read "Alice Example Lost" for a board Other won.

Control: an UNSETTLED dominant "Other" at ~100% on an open board is still an
untraded artifact and still goes last (UX-P126/F5) on every surface.

T2 (lane1b EARLY-REPAIR-REVIEW-e3de8f84 §3/§6): both search routes serve only
``status="open"`` boards, so the resolved P2 arm alone cannot prove a card a
reader can reach. The open arm below is the reachable one, and it goes through
the card formatter itself (``_format_futures_for_search``), not just the builder.
"""

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.routes import events, futures

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)
SEEN = NOW - timedelta(hours=1)


def _leg(i, name, p, *, is_winner=None, src=None):
    return SimpleNamespace(
        id=i, name=name, external_id=f"F2-{i}", current_probability=p,
        current_yes_bid=max(0, p - 0.01), current_yes_ask=min(1, p + 0.01),
        current_american_odds=None, rank=i, rank_change_24h=None,
        probability_change_24h=None, opening_probability=None,
        opening_american_odds=None, is_winner=is_winner, resolution_source=src,
        last_updated=SEEN, price_changed_at=None,
    )


def _board(legs, *, status):
    return SimpleNamespace(
        id=990021, name="Probe field board", description=None,
        category="championship", source="kalshi", external_id="F2-probe",
        status=status, sport=None, sport_id=None, event_id=None, market_type=None,
        market_tier=5, llm_sport_category="politics", mutually_exclusive=True,
        commence_time=None, resolution_date=datetime(2099, 1, 1, tzinfo=timezone.utc),
        created_at=None, updated_at=None, group_id=None, canonical_market_key=None,
        hook_description=None, image_url=None, category_tags=[],
        market_metadata=None, outcomes=legs,
    )


def _orders(market):
    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    original = deepcopy(market)
    with ExitStack() as stack:
        for module in (events, futures):
            stack.enter_context(patch.object(module, "datetime", _Fixed))
        detail = futures._format_market_detail(market)["outcomes"]
        card = events._build_search_top_outcomes(market, limit=5, lean=False)
        typeahead = events._build_search_top_outcomes(market, limit=3, lean=True)
    assert market == original
    return [[row["name"] for row in rows] for rows in (detail, card, typeahead)]


def test_a_settled_field_winner_leads_detail_card_and_typeahead():
    # P2 verbatim: Other won (api_settlement), the named legs lost at 0.0.
    legs = [
        _leg(1, "Other", 1.0, is_winner=True, src="api_settlement"),
        _leg(2, "Alice Example", 0.0, is_winner=False, src="api_settlement"),
        _leg(3, "Bob Example", 0.0, is_winner=False, src="api_settlement"),
    ]
    detail, card, typeahead = _orders(_board(legs, status="resolved"))
    assert detail[0] == card[0] == typeahead[0] == "Other"
    assert card == detail[: len(card)]
    assert typeahead == detail[: len(typeahead)]


def test_control_an_unsettled_dominant_field_row_still_goes_last_everywhere():
    legs = [
        _leg(1, "Other", 1.0),
        _leg(2, "Alice Example", 0.40),
        _leg(3, "Bob Example", 0.30),
    ]
    detail, card, typeahead = _orders(_board(legs, status="open"))
    for order in (detail, card, typeahead):
        assert order[0] == "Alice Example", order
        assert "Other" not in order[:2], order


def _card_formatter_names(market):
    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    with ExitStack() as stack:
        for module in (events, futures):
            stack.enter_context(patch.object(module, "datetime", _Fixed))
        card = events._format_futures_for_search(market)
    assert card is not None, "the open settled-Other board must keep its search card"
    return [row["name"] for row in card["top_outcomes"]]


def test_t2_an_open_board_whose_field_won_leads_with_other_everywhere():
    # The route-reachable arm: same P2 legs, board still `open` (settled at the
    # venue, not yet closed in our row — gotcha #33's population).
    legs = [
        _leg(1, "Other", 1.0, is_winner=True, src="api_settlement"),
        _leg(2, "Alice Example", 0.0, is_winner=False, src="api_settlement"),
        _leg(3, "Bob Example", 0.0, is_winner=False, src="api_settlement"),
    ]
    board = _board(legs, status="open")
    detail, card, typeahead = _orders(board)
    assert detail[0] == card[0] == typeahead[0] == "Other", (detail, card, typeahead)
    assert _card_formatter_names(board)[0] == "Other"


def test_t2_an_open_field_winner_beside_still_priced_losers_leads():
    # The named legs still carry a stale live price while their grade says
    # lost; the supported Other winner is the answer on every surface.
    legs = [
        _leg(1, "Other", 1.0, is_winner=True, src="api_settlement"),
        _leg(2, "Alice Example", 0.04, is_winner=False, src="api_settlement"),
        _leg(3, "Bob Example", 0.02, is_winner=False, src="api_settlement"),
    ]
    board = _board(legs, status="open")
    detail, card, typeahead = _orders(board)
    assert detail[0] == card[0] == typeahead[0] == "Other", (detail, card, typeahead)
    assert _card_formatter_names(board)[0] == "Other"
