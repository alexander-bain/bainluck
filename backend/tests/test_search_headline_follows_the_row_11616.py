"""#11616 L1/L2: search's headline on an open multi-winner board is the row both
detail pages lead with.

lane1b's Native delta review (NATIVE-DELTA-REVIEW-0d239c9d.md §2.1-2.2), ruled by
Root (ROOT-NATIVE-DELTA-DISPOSITION.md item 2). Web `pickLiveLeader` and iOS
`futuresDetailHeroOutcome` take the best row that is not a raw `is_winner` true
and is priced above 0; with none, the supported winner. Search's
`_headline_tier` disagreed twice:

* L1 — a live row at exactly 0.0 sat in the live tier, so the dropdown and the
  card led with "A 0%" over "B Won" while both detail heroes showed B.
* L2 — a graded loser (`False` + `api_settlement`) on an open board prints its
  live number on every surface (#6082), yet `leg_is_graded` demoted it, so
  search led with B 30% while both detail heroes led with A 40%.

A real zero is still served as 0.0 (#6195), never null.
"""

from types import SimpleNamespace

import pytest

from app.routes.events import _build_search_top_outcomes


def _leg(oid, name, prob, is_winner=False, source=None):
    return SimpleNamespace(
        id=oid, name=name, external_id=f"0x{oid}", current_probability=prob,
        current_american_odds=None, rank=None, probability_change_24h=None,
        is_winner=is_winner, resolution_source=source,
        current_yes_bid=None if prob is None else max(0.0, prob - 0.01),
        current_yes_ask=None if prob is None else min(1.0, prob + 0.01),
        price_changed_at=None, last_updated=None,
    )


def _board(*legs, mutually_exclusive=False, status="open"):
    return SimpleNamespace(
        id=116160, name="Which rungs hit in 2026", source="polymarket",
        status=status, mutually_exclusive=mutually_exclusive, outcomes=list(legs),
    )


def _card(market):
    return _build_search_top_outcomes(market)


def _typeahead(market):
    return _build_search_top_outcomes(market, limit=3, lean=True)


SURFACES = {"card": _card, "typeahead": _typeahead}

# Rung names, because the builder drops single-letter placeholder legs.
A, B, C = "↑ 4.25%", "↑ 4.5%", "↑ 4.75%"


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_l1_a_live_zero_does_not_headline_over_a_supported_result(surface):
    # Input §2.1: both detail heroes are B (no live row priced above 0).
    out = SURFACES[surface](_board(
        _leg(1, A, 0.0), _leg(2, B, 0.95, True, "api_settlement"),
    ))
    assert out[0]["name"] == B, [o["name"] for o in out]
    zero = next(o for o in out if o["name"] == A)
    assert zero["probability"] == 0.0  # a real zero stays a price (#6195)


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_l1_control_a_live_three_percent_still_leads(surface):
    # web #7439: "a row at 3% still promotes".
    out = SURFACES[surface](_board(
        _leg(1, A, 0.03), _leg(2, B, 0.95, True, "api_settlement"),
    ))
    assert out[0]["name"] == A, [o["name"] for o in out]


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_l1_control_a_null_row_stays_below_the_result(surface):
    out = SURFACES[surface](_board(
        _leg(1, A, None), _leg(2, B, 0.95, True, "api_settlement"),
    ))
    assert out[0]["name"] == B, [o["name"] for o in out]


def test_l1_control_an_ungraded_board_with_zeros_keeps_its_order():
    out = _card(_board(_leg(1, A, 0.2), _leg(2, B, 0.0), _leg(3, C, 0.0)))
    assert [o["name"] for o in out] == [A, B, C]
    assert [o["probability"] for o in out] == [0.2, 0.0, 0.0]


def test_l1_control_an_all_zero_board_keeps_served_order():
    out = _card(_board(_leg(1, A, 0.0), _leg(2, B, 0.0), _leg(3, C, 0.0)))
    assert [o["name"] for o in out] == [A, B, C]


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_l2_a_graded_loser_printing_live_leads_like_any_live_row(surface):
    # Input §2.2: both detail heroes are A 40%; every surface prints A as 40%.
    out = SURFACES[surface](_board(
        _leg(1, A, 0.40, False, "api_settlement"), _leg(2, B, 0.30),
    ))
    assert [o["name"] for o in out] == [A, B]
    assert (out[0]["is_winner"], out[0]["resolution_source"], out[0]["probability"]) == (
        False, "api_settlement", 0.40,
    )  # it keeps its grade on the wire


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_l2_control_a_graded_loser_at_zero_drops_below_live(surface):
    out = SURFACES[surface](_board(
        _leg(1, A, 0.0, False, "api_settlement"), _leg(2, B, 0.30),
    ))
    assert out[0]["name"] == B, [o["name"] for o in out]


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_control_a_raw_winner_flag_is_still_not_a_live_lead(surface):
    # web `pickLiveLeader` / iOS `:105` exclude a raw `is_winner` true from the
    # live lead whatever its source; search keeps it in the result tier.
    out = SURFACES[surface](_board(
        _leg(1, A, 0.90, True, None), _leg(2, B, 0.30),
    ))
    assert out[0]["name"] == B, [o["name"] for o in out]


def test_control_an_open_exclusive_board_still_leads_with_its_supported_winner():
    out = _card(_board(
        _leg(1, "Shai", 0.97), _leg(2, "Victor", 0.95, True, "api_settlement"),
        mutually_exclusive=True,
    ))
    assert out[0]["name"] == "Victor", [o["name"] for o in out]
