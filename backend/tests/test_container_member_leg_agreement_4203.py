"""#4203 — a container member whose two legs contradict each other is refused.

Alex, shopping /sports the night the #4153 fold went live: "US Open 2026: To
Reach the Final (Women's Singles)" ranked **Belinda Bencic 2nd at 83%**. She was
out of the tournament. The sibling card, "To Reach Semifinals", did not list her
in its top five at all — so our own data said she was at most 50% to reach the
semis while printing 83% to reach the final, which no draw can produce.

Measured on production `c7cf9898`: her market held ``No = 1.000`` written at
``08:50:04`` and ``Yes = 0.833`` written ten seconds later at ``08:50:14``, and
the Yes had not moved in 21 hours. Polymarket had the market ``closed`` with
``outcomePrices ["0","1"]``. Either leg alone reads as a normal price. Only the
PAIR shows the lie, and the pair sums to 1.833.

Census the same night: 183 of 10,524 open container members drift past
``CONTAINER_FOLD_MAX_LEG_SUM_DRIFT``, 129 of them with a Yes big enough to rank
onto a card, the worst pair summing to exactly 2.000. All four US Open groups
the fold renders were affected.

These tests pin the refusal, and — just as important — pin what it must NOT do:
it must not invent ``1 - No``, and it must not quietly empty a card whose source
only ever stores one leg.
"""

import pytest

from app.utils.market_grouping import (
    CONTAINER_FOLD_MAX_LEG_SUM_DRIFT,
    detect_container_field_groups,
)

_FINAL = "Will {} advance to the Final in Women's Singles at the 2026 US Open?"
PARENT = {"polymarket:910235": "US Open 2026: To Reach the Final (Women's Singles)"}


def _member(market_id, entity, probability, complement=None):
    return {
        "id": market_id,
        "name": _FINAL.format(entity),
        "source": "polymarket",
        "probability": probability,
        "complement_probability": complement,
    }


def _fold(members):
    return detect_container_field_groups({"polymarket:910235": members}, PARENT)


def _entities(result):
    group = result.get("polymarket:910235")
    return [e["name"] for e in group["entries"]] if group else []


# ── the production case ───────────────────────────────────────────────────


def _the_night_it_shipped():
    """Group ``polymarket:910235`` as production served it, both legs.

    Bencic and Sakkari are the two the venue had closed at 0; the rest are the
    live prices, whose legs sum to 1 because one pass wrote them together.
    """
    return [
        _member(1, "Belinda Bencic", 0.833, 1.000),
        _member(2, "Maria Sakkari", 0.480, 1.000),
        _member(3, "Aryna Sabalenka", 0.930, 0.070),
        _member(4, "Coco Gauff", 0.430, 0.570),
        _member(5, "Jessica Pegula", 0.370, 0.630),
    ]


def test_the_eliminated_player_is_not_on_the_card():
    assert "Belinda Bencic" not in _entities(_fold(_the_night_it_shipped()))


def test_every_contradicting_member_goes_not_just_the_worst_one():
    on_card = _entities(_fold(_the_night_it_shipped()))
    assert "Maria Sakkari" not in on_card
    assert on_card == ["Aryna Sabalenka", "Coco Gauff", "Jessica Pegula"]


def test_the_card_still_folds_and_still_leads_with_the_leader():
    """The refusal must not cost #4153 its ship where a field survives."""
    group = _fold(_the_night_it_shipped())["polymarket:910235"]
    assert group["title"] == "US Open 2026: To Reach the Final (Women's Singles)"
    assert group["entries"][0]["name"] == "Aryna Sabalenka"
    assert group["entries"][0]["probability"] == pytest.approx(0.930)


def test_the_survivors_now_sum_below_the_two_slots_a_final_has():
    """The symptom Alex could see: the top rows summed to 3.04 for 2 places."""
    entries = _fold(_the_night_it_shipped())["polymarket:910235"]["entries"]
    assert sum(e["probability"] for e in entries) <= 2.0


# ── what the refusal must not do ──────────────────────────────────────────


def test_the_no_leg_is_never_used_as_a_price():
    """``1 - No`` would be an invented number — #4163's rule, applied to legs.

    If the fold ever "repaired" Bencic instead of dropping her she would appear
    at 0.0, which is a claim we did not measure. We distrust BOTH legs of a
    contradicting pair, so neither may be rendered.
    """
    on_card = _fold(_the_night_it_shipped())["polymarket:910235"]["entries"]
    assert all(e["name"] != "Belinda Bencic" for e in on_card)
    assert all(e["probability"] not in (0.0, 1.0) for e in on_card)


def test_a_member_with_no_no_leg_is_kept():
    """Unjudgeable is not suspect — a one-legged source must still fold."""
    members = [
        _member(1, "Aryna Sabalenka", 0.930, None),
        _member(2, "Coco Gauff", 0.430, None),
        _member(3, "Jessica Pegula", 0.370, None),
    ]
    assert _entities(_fold(members)) == [
        "Aryna Sabalenka",
        "Coco Gauff",
        "Jessica Pegula",
    ]


def test_an_ordinary_spread_is_not_a_contradiction():
    """Real books do not sum to exactly 1; the tolerance exists for them."""
    drift = CONTAINER_FOLD_MAX_LEG_SUM_DRIFT / 2
    members = [
        _member(1, "Aryna Sabalenka", 0.930, 0.070 + drift),
        _member(2, "Coco Gauff", 0.430, 0.570 + drift),
    ]
    assert len(_entities(_fold(members))) == 2


# ── the other shapes the census found ─────────────────────────────────────


def test_both_legs_at_one_is_refused():
    """The second shape: a settled market written 1.0/1.0 in one fresh pass.

    ``Matt Gaetz confirmed as Attorney General?`` and ``Mets vs. Dodgers -
    Game 4`` were both sitting at 2.000 the night this was written, and a 1.0
    Yes takes the TOP row of a field card, not the second.
    """
    members = [
        _member(1, "Belinda Bencic", 1.000, 1.000),
        _member(2, "Aryna Sabalenka", 0.930, 0.070),
        _member(3, "Coco Gauff", 0.430, 0.570),
    ]
    on_card = _entities(_fold(members))
    assert on_card == ["Aryna Sabalenka", "Coco Gauff"]


def test_legs_that_undersum_are_refused_too():
    """Drift is checked in both directions; a 0.4 pair is as broken as a 1.8."""
    members = [
        _member(1, "Belinda Bencic", 0.200, 0.200),
        _member(2, "Aryna Sabalenka", 0.930, 0.070),
        _member(3, "Coco Gauff", 0.430, 0.570),
    ]
    assert "Belinda Bencic" not in _entities(_fold(members))


def test_a_group_refused_below_the_minimum_unfolds_rather_than_lying():
    """Un-folding is the honest fallback, not a #4153 regression.

    A field we cannot rank truthfully must not be presented as a ranked field;
    the members keep the per-member cards they already have.
    """
    members = [
        _member(1, "Belinda Bencic", 0.833, 1.000),
        _member(2, "Maria Sakkari", 0.480, 1.000),
        _member(3, "Aryna Sabalenka", 0.930, 0.070),
    ]
    assert _fold(members) == {}
