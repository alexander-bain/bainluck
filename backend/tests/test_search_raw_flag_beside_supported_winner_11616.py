"""#11616 B1: an unsupported raw winner flag never takes the search lead from the
supported winner both detail heroes name.

lane1b's EARLY-REPAIR-REVIEW-e3de8f84 §2 (B1). Open independent board, no served
lead, no live row priced above 0:

* A — `is_winner=True`, `resolution_source=None`, 0.60, stored rank 1;
* B — `is_winner=True`, `api_settlement`, 0.20, stored rank 2.

Web `pickHeroOutcome` (`pickLiveLeader` excludes both, the first `"won"` verdict
is B) and iOS `futuresDetailHeroOutcome` (`winners.first`) both lead with B Won.
Search put A in the result tier beside B, and #9675's kept-winner pass ordered
the two by STORED rank, so the card and the dropdown led with "A 60%". The lead
then hung on a stored column (#2556 calls it unreliable): with B's rank first,
search led with B.

The repair sends a raw true that is not a supported result to tier 0, where it
sorts by price below every supported result — detail's own fallback order.
"""

from types import SimpleNamespace

import pytest

from app.routes.events import _build_search_top_outcomes


def _leg(oid, name, prob, is_winner=False, source=None, rank=None):
    return SimpleNamespace(
        id=oid, name=name, external_id=f"0x{oid}", current_probability=prob,
        current_american_odds=None, rank=rank, probability_change_24h=None,
        is_winner=is_winner, resolution_source=source,
        current_yes_bid=None if prob is None else max(0.0, prob - 0.01),
        current_yes_ask=None if prob is None else min(1.0, prob + 0.01),
        price_changed_at=None, last_updated=None,
    )


def _board(*legs, mutually_exclusive=False, status="open"):
    return SimpleNamespace(
        id=116162, name="Which rungs hit in 2026", source="polymarket",
        status=status, mutually_exclusive=mutually_exclusive, outcomes=list(legs),
    )


def _card(market):
    return _build_search_top_outcomes(market)


def _typeahead(market):
    return _build_search_top_outcomes(market, limit=3, lean=True)


SURFACES = {"card": _card, "typeahead": _typeahead}

# Rung names, because the builder drops single-letter placeholder legs.
A, B, C, D = "↑ 4.25%", "↑ 4.5%", "↑ 4.75%", "↑ 5%"

# Stored ranks (A, B): the review's order, both null, and the order that
# already happened to lead with B before the repair.
RANKS = [(1, 2), (None, None), (2, 1)]


@pytest.mark.parametrize("ranks", RANKS, ids=["rank-1-2", "rank-null", "rank-2-1"])
@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_b1_the_supported_winner_leads_over_an_unsupported_raw_flag(surface, ranks):
    out = SURFACES[surface](_board(
        _leg(1, A, 0.60, True, None, rank=ranks[0]),
        _leg(2, B, 0.20, True, "api_settlement", rank=ranks[1]),
    ))
    assert [o["name"] for o in out] == [B, A]
    # Both rows keep what they carry on the wire; A is not crowned or erased.
    assert (out[0]["is_winner"], out[0]["resolution_source"]) == (True, "api_settlement")
    assert (out[1]["is_winner"], out[1]["resolution_source"], out[1]["probability"]) == (
        True, None, 0.60,
    )
    if surface == "card":
        assert out[0]["id"] == 2


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_b1_a_zero_priced_third_row_changes_nothing(surface):
    out = SURFACES[surface](_board(
        _leg(1, A, 0.60, True, None, rank=1),
        _leg(2, B, 0.20, True, "api_settlement", rank=2),
        _leg(3, C, 0.0, rank=3),
    ))
    assert out[0]["name"] == B, [o["name"] for o in out]


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_control_a_legitimate_live_row_still_leads(surface):
    # web `pickLiveLeader` / iOS ME=false live filter: a live 0.30 is the hero.
    out = SURFACES[surface](_board(
        _leg(1, A, 0.60, True, None, rank=1),
        _leg(2, B, 0.20, True, "api_settlement", rank=2),
        _leg(3, C, 0.30, rank=3),
    ))
    assert [o["name"] for o in out][:2] == [C, B]


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_control_a_raw_flag_with_no_supported_winner_falls_back_to_price(surface):
    # No live row above 0 and no supported winner: web falls to its price
    # `leader` (A), iOS to its price leader (A); search leads A as a price.
    out = SURFACES[surface](_board(
        _leg(1, A, 0.60, True, None, rank=1),
        _leg(3, C, 0.0, rank=2),
    ))
    assert out[0]["name"] == A, [o["name"] for o in out]
    assert out[0]["probability"] == 0.60


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_control_several_supported_winners_are_all_retained_above_the_raw_flag(surface):
    out = SURFACES[surface](_board(
        _leg(1, A, 0.60, True, None, rank=1),
        _leg(2, B, 0.20, True, "api_settlement", rank=2),
        _leg(4, D, 0.10, True, "api_settlement", rank=3),
    ))
    names = [o["name"] for o in out]
    assert set(names[:2]) == {B, D}, names
    assert names[2] == A, names


def test_control_the_card_keeps_both_supported_winners_on_a_full_board():
    # limit 5 with more legs than rows: #9675 still keeps every supported
    # winner; the raw flag is the one that can fall off, never a result.
    out = _card(_board(
        _leg(1, A, 0.60, True, None, rank=1),
        _leg(2, B, 0.20, True, "api_settlement", rank=2),
        _leg(4, D, 0.10, True, "api_settlement", rank=3),
        _leg(5, "↑ 5.25%", 0.05, rank=4),
        _leg(6, "↑ 5.5%", 0.04, rank=5),
        _leg(7, "↑ 5.75%", 0.03, rank=6),
        _leg(8, "↑ 6%", 0.02, rank=7),
    ))
    names = [o["name"] for o in out]
    assert len(names) == 5
    assert {B, D} <= set(names), names


# ── R-multi: several supported winners, no live row ─────────────────────────
# lane1b §6 R-multi: web (`winners[0]` in served detail order) and iOS
# (`winners.first`) lead with the first supported winner detail SERVES, and
# detail serves by price (`represent_futures_outcomes`). Search ordered its
# kept winners by stored rank, so a disagreeing rank led with the other team.


def _detail_first_winner(market):
    from app.routes.futures import _format_market_detail

    return next(
        o["name"] for o in _format_market_detail(market)["outcomes"]
        if o["is_winner"] is True and o["resolution_source"] == "api_settlement"
    )


def _multi(*legs):
    from tests.test_search_cache_compatibility_11616 import _make_market, _make_outcome

    return _make_market(
        market_id=116169, name="Team to advance", mutually_exclusive=False,
        outcomes=[
            _make_outcome(oid, name, p, is_winner=True, resolution_source="api_settlement", rank=rank)
            for oid, name, p, rank in legs
        ],
    )


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_r_multi_a_stored_rank_does_not_override_detail_s_price_order(surface):
    market = _multi((1, "Milwaukee Brewers", 0.99, 2), (2, "Los Angeles Dodgers", 0.95, 1))
    out = SURFACES[surface](market)
    assert out[0]["name"] == _detail_first_winner(market) == "Milwaukee Brewers"


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_r_multi_a_priceless_winner_follows_the_priced_one_as_detail(surface):
    market = _multi((1, "Milwaukee Brewers", None, 1), (2, "Los Angeles Dodgers", 0.95, 2))
    out = SURFACES[surface](market)
    assert out[0]["name"] == _detail_first_winner(market) == "Los Angeles Dodgers"


def test_r_multi_control_an_exact_tie_keeps_9675_s_load_order_independent_order():
    # Equal 1.0 winners: detail's own tie is load order (the relationship has no
    # `order_by`); search keeps #9675's stable rank/name/id so a card cannot flip
    # between reads. Both orders below give the same card.
    a = (1, "Milwaukee Brewers", 1.0, 1)
    b = (2, "Los Angeles Dodgers", 1.0, 1)
    assert [o["name"] for o in _card(_multi(a, b))] == [o["name"] for o in _card(_multi(b, a))] == [
        "Los Angeles Dodgers", "Milwaukee Brewers",
    ]
