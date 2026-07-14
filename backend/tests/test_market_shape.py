"""Guard tests for the market-shape classifier (Queue #194 Item 1).

One assertion cluster per shape, plus the census mis-bucket fixes:
  * 2-outcome MX with named sides → duel (not claim)
  * sub-2-outcome → unshaped (not claim)
  * quantity keyed off numeric outcome structure, not question text
"""

from app.utils.market_shape import (
    SHAPE_CLAIM,
    SHAPE_CONTAINER_MEMBER,
    SHAPE_DUEL,
    SHAPE_FIELD,
    SHAPE_QUANTITY,
    SHAPE_UNSHAPED,
    SHAPE_TO_KERNEL,
    SIDE_COMPETITORS,
    SIDE_THRESHOLD,
    SIDE_YES_NO,
    classify_market_shape,
)


def shape(names, **kw):
    return classify_market_shape(outcome_names=names, **kw)[0]


def side(names, **kw):
    return classify_market_shape(outcome_names=names, **kw)[1]


# --- claim -----------------------------------------------------------------

def test_claim_yes_no_binary():
    assert classify_market_shape(outcome_names=["Yes", "No"]) == (
        SHAPE_CLAIM,
        SIDE_YES_NO,
    )


def test_claim_case_and_order_insensitive():
    assert shape(["no", "YES"]) == SHAPE_CLAIM


def test_lone_yes_no_in_singleton_group_is_claim_not_container():
    # group_size 1 ⇒ not a container member.
    assert shape(["Yes", "No"], group_id="g1", group_size=1) == SHAPE_CLAIM


# --- duel ------------------------------------------------------------------

def test_duel_named_competitors():
    assert classify_market_shape(
        outcome_names=["Lakers", "Celtics"]
    ) == (SHAPE_DUEL, SIDE_COMPETITORS)


def test_duel_via_event_link_even_if_names_odd():
    # A game-linked 2-outcome market is a duel regardless of naming.
    assert shape(["Home", "Away"], event_id=42) == SHAPE_DUEL


def test_two_outcome_mx_named_sides_is_duel_not_claim():
    # Census mis-bucket fix: "which party wins" 2-outcome MX → duel.
    assert shape(["Democratic", "Republican"]) == SHAPE_DUEL


# --- field -----------------------------------------------------------------

def test_field_multi_named_competitors():
    assert classify_market_shape(
        outcome_names=["Alice", "Bob", "Carol", "Dave"]
    ) == (SHAPE_FIELD, SIDE_COMPETITORS)


def test_field_three_outcomes():
    assert shape(["A", "B", "C"]) == SHAPE_FIELD


# --- quantity --------------------------------------------------------------

def test_quantity_by_ticker_prefix():
    assert classify_market_shape(
        outcome_names=["Yes", "No"], external_id="KXROTTENTOMATOES-XYZ"
    ) == (SHAPE_QUANTITY, SIDE_THRESHOLD)


def test_quantity_by_numeric_bins():
    assert shape(["100-150", "150-200", "200-250"]) == SHAPE_QUANTITY


def test_quantity_threshold_phrases():
    assert shape(["at least 3", "2 or fewer", "4 or more"]) == SHAPE_QUANTITY


def test_quantity_temperature_bands():
    assert shape(["Below 40", "40 to 50", "Above 50"]) == SHAPE_QUANTITY


def test_quantity_before_date_ladder():
    # "when will X happen" date ladders render as a threshold heatmap.
    assert shape(["Before 2027", "Before 2028", "Before Jan 20, 2029"]) == (
        SHAPE_QUANTITY
    )


def test_single_threshold_yes_no_is_claim_not_quantity():
    # One yes/no question about a number is a *claim*, not a ladder.
    assert shape(["Yes", "No"]) == SHAPE_CLAIM


# --- container_member ------------------------------------------------------

def test_container_member_yes_no_in_multi_group():
    assert classify_market_shape(
        outcome_names=["Yes", "No"], group_id="polymarket:123", group_size=72
    ) == (SHAPE_CONTAINER_MEMBER, SIDE_YES_NO)


def test_container_requires_multi_member_group():
    assert shape(["Yes", "No"], group_id="g", group_size=1) == SHAPE_CLAIM


def test_named_pair_in_group_is_still_duel_not_container():
    # container_member is yes/no-only; a named pair in a group is a duel.
    assert shape(["Lakers", "Celtics"], group_id="g", group_size=5) == SHAPE_DUEL


# --- unshaped --------------------------------------------------------------

def test_unshaped_zero_outcomes():
    assert classify_market_shape(outcome_names=[]) == (SHAPE_UNSHAPED, None)


def test_unshaped_one_outcome():
    assert classify_market_shape(outcome_names=["Yes"]) == (SHAPE_UNSHAPED, None)


def test_unshaped_ignores_blank_outcome_names():
    assert shape(["Yes", "   ", ""]) == SHAPE_UNSHAPED


def test_none_outcome_names_is_unshaped():
    assert classify_market_shape(outcome_names=None) == (SHAPE_UNSHAPED, None)


# --- kernel map ------------------------------------------------------------

def test_every_shape_has_a_kernel_entry():
    from app.utils.market_shape import ALL_SHAPES

    assert set(SHAPE_TO_KERNEL) == set(ALL_SHAPES)


def test_unshaped_has_no_kernel():
    assert SHAPE_TO_KERNEL[SHAPE_UNSHAPED] is None
