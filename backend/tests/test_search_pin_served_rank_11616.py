"""#11616 O-P1a: the query pin's served ``rank`` is the number detail prints.

lane1b's EARLY-REPAIR-REVIEW-e3de8f84 §6 (O-P1a). Since P1 the search card
badges siblings with their served ``rank`` (detail's own ``assign_display_ranks``
number), but the pin's badge read ``matched_rank``: 1 + the legs priced
STRICTLY above it. On a priced tie that is a neighbour's number — Leader 0.5 /
X 0.2 / pin 0.2 printed 1, 2, 2 beside detail's 1, 2, 3.

The correction is at both ends: the producer serves a priced pin's
``matched_rank`` as its served rank (the #8863 count only where no rank is
served), and ``FuturesCard.boardRank`` prefers the served rank on a ranked card,
so a cached row from the old producer prints detail's number too. Pinned on the
same inputs the web guard renders from the committed fixture; query selection
and the priceless refusal are unchanged.
"""

from datetime import datetime, timezone

import pytest

from app.routes.events import _format_futures_for_search
from app.routes.futures import _format_market_detail
from tests.test_search_cache_compatibility_11616 import _make_market, _make_outcome

NOW = datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc)
FIELD = [(10 + i, f"Field Person {chr(65 + i)}", round(0.3 - 0.01 * i, 2)) for i in range(6)]
DEEP = [(10 + i, f"Field Person {chr(65 + i)}", round(0.4 - 0.01 * i, 2)) for i in range(6)]

SHAPES = {
    # (legs, expected served/detail rank of the pin, the old #8863 count)
    "tied": ([(1, "Leader Person", 0.5), (2, "Xavier Other", 0.2), (3, "Pinned Player", 0.2)], 3, 2),
    "tied-pin-served-first": (
        [(1, "Leader Person", 0.5), (3, "Pinned Player", 0.2), (2, "Xavier Other", 0.2)], 2, 2,
    ),
    "full-field": (
        [(1, "Leader Person", 0.5), (2, "Xavier Other", 0.2), (3, "Pinned Player", 0.2), *FIELD], 9, 8,
    ),
    "truncated": ([(1, "Leader Person", 0.5), *DEEP, (3, "Pinned Player", 0.05)], 8, 8),
}


def _market(legs):
    return _make_market(
        market_id=116168, name="NBA MVP", status="open", source="kalshi",
        outcomes=[_make_outcome(oid, name, p, last_updated=NOW) for oid, name, p in legs],
        updated_at=NOW,
    )


def _card(market):
    return _format_futures_for_search(market, query_terms=[("pinned", None)])


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_the_pin_carries_detail_s_rank(shape):
    legs, expected_rank, _old_count = SHAPES[shape]
    market = _market(legs)
    card = _card(market)
    detail_rank = {o["id"]: o["rank"] for o in _format_market_detail(market)["outcomes"]}
    pin = card["top_outcomes"][0]
    # Query selection unchanged: the named leg is pinned and leads the payload.
    assert (pin["name"], pin.get("query_match")) == ("Pinned Player", True)
    assert pin["rank"] == detail_rank[3] == expected_rank
    # matched_rank is detail's number too, where the old count could differ.
    assert pin["matched_rank"] == expected_rank
    # Every drawn sibling also carries detail's number.
    for row in card["top_outcomes"]:
        assert row["rank"] == detail_rank[row["id"]], row["name"]


def test_control_a_priceless_named_leg_is_never_pinned():
    market = _market([(1, "Leader Person", 0.5), (2, "Xavier Other", 0.2), (3, "Pinned Player", None)])
    card = _card(market)
    assert not any(row.get("query_match") for row in card["top_outcomes"])
    assert all(row.get("matched_rank") is None for row in card["top_outcomes"])
