"""Guard tests for the market-shape classifier (Queue #194 Item 1).

One assertion cluster per shape, plus the census mis-bucket fixes:
  * 2-outcome MX with named sides → duel (not claim)
  * sub-2-outcome → unshaped (not claim)
  * quantity keyed off numeric outcome structure, not question text
"""

from app.utils.market_shape import (
    CLASSIFIER_VERSION,
    REL_COMPETITORS,
    REL_COMPLEMENTS,
    REL_CONDITIONAL,
    REL_CUMULATIVE,
    REL_PARTICIPATION,
    REL_RANGES,
    REL_UNKNOWN,
    SHAPE_CLAIM,
    SHAPE_CONTAINER_MEMBER,
    SHAPE_DUEL,
    SHAPE_FIELD,
    SHAPE_PARTICIPATION,
    SHAPE_QUANTITY,
    SHAPE_UNSHAPED,
    SHAPE_TO_KERNEL,
    SIDE_COMPETITORS,
    SIDE_THRESHOLD,
    SIDE_YES_NO,
    classify_market_semantics,
    classify_market_shape,
    input_fingerprint,
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


# ===========================================================================
# Queue #260 — semantics v2: C16 P1 trio + versioned recompute
# ===========================================================================

def sem(names, **kw):
    return classify_market_semantics(outcome_names=names, **kw)


# --- C16 P1(3): event-linked Yes/No is a claim, not a duel -----------------

def test_event_linked_yes_no_is_claim_not_duel():
    # The old step-4 order forced every game-linked binary to a duel before
    # checking the Yes/No names.
    assert classify_market_shape(outcome_names=["Yes", "No"], event_id=99) == (
        SHAPE_CLAIM,
        SIDE_YES_NO,
    )


def test_event_linked_named_pair_is_still_duel():
    assert shape(["Home", "Away"], event_id=99) == SHAPE_DUEL


# --- C16 P1(2): field / participation split --------------------------------

def test_top_n_source_kind_is_participation_not_field():
    assert shape(
        ["A", "B", "C", "D", "E", "F"], source_kind="top_5"
    ) == SHAPE_PARTICIPATION


def test_expected_winners_gt_one_is_participation():
    assert shape(["A", "B", "C"], expected_winners=3) == SHAPE_PARTICIPATION


def test_make_cut_is_participation():
    assert shape(["A", "B", "C"], source_kind="make_cut") == SHAPE_PARTICIPATION


def test_plain_multi_named_field_stays_field():
    # No Top-N / multi-winner signal → a one-winner field, not participation.
    assert shape(["A", "B", "C", "D"]) == SHAPE_FIELD


def test_win_source_kind_is_not_participation():
    assert shape(["A", "B", "C"], source_kind="win") == SHAPE_FIELD


def test_participation_has_a_kernel_and_is_in_all_shapes():
    from app.utils.market_shape import ALL_SHAPES

    assert SHAPE_PARTICIPATION in ALL_SHAPES
    assert SHAPE_TO_KERNEL[SHAPE_PARTICIPATION] is not None


# --- semantics v2 contract fixtures (the queue's fixture list) -------------

def test_semantics_linked_yes_no_prop():
    r = sem(["Yes", "No"], event_id=42)
    assert r["display_shape"] == SHAPE_CLAIM
    assert r["outcome_relation"] == REL_COMPLEMENTS
    assert r["exhaustive"] is True
    assert r["expected_winners"] == 1
    assert "linked_yes_no" in r["evidence"]
    assert r["classifier_version"] == CLASSIFIER_VERSION


def test_semantics_moneyline():
    r = sem(["Home", "Away"], event_id=1, mutually_exclusive=True)
    assert r["display_shape"] == SHAPE_DUEL
    assert r["outcome_relation"] == REL_COMPETITORS
    assert r["expected_winners"] == 1
    assert r["exhaustive"] is True


def test_semantics_over_under_is_push_capable_complement():
    r = sem(["Over", "Under"], source_kind="game_total", push_possible=True)
    assert r["outcome_relation"] == REL_COMPLEMENTS
    assert r["push_void_capable"] is True


def test_semantics_draw_capable_match():
    r = sem(["Team A", "Draw", "Team B"], mutually_exclusive=True)
    assert r["outcome_relation"] == REL_COMPETITORS
    assert "draw_capable" in r["evidence"]


def test_semantics_named_h2h():
    r = sem(["Alice", "Bob"], mutually_exclusive=True)
    assert r["display_shape"] == SHAPE_DUEL
    assert r["outcome_relation"] == REL_COMPETITORS


def test_semantics_proven_field_is_exhaustive_one_winner():
    r = sem(["Alice", "Bob", "Carol"], mutually_exclusive=True, expected_winners=1)
    assert r["display_shape"] == SHAPE_FIELD
    assert r["outcome_relation"] == REL_COMPETITORS
    assert r["exhaustive"] is True
    assert r["expected_winners"] == 1


def test_semantics_truncated_field_unproven_is_not_exhaustive():
    # Item 3 guard: a field is only a normalizable one-winner partition when the
    # source PROVES it. >2 named outcomes alone must NOT set exhaustive.
    r = sem(["Alice", "Bob", "Carol"])  # mutually_exclusive unknown
    assert r["display_shape"] == SHAPE_FIELD
    assert r["exhaustive"] is None
    assert r["outcome_relation"] == REL_UNKNOWN


def test_semantics_cumulative_ladder():
    r = sem(["At least 10", "At least 20", "At least 30"])
    assert r["outcome_relation"] == REL_CUMULATIVE
    assert r["exhaustive"] is False


def test_semantics_exclusive_ranges():
    r = sem(["0-10", "11-20", "21-30"], mutually_exclusive=True)
    assert r["outcome_relation"] == REL_RANGES
    assert r["exhaustive"] is True


def test_semantics_correctly_graded_top_n():
    r = sem(["A", "B", "C", "D", "E", "F"], source_kind="top_5", mutually_exclusive=False)
    assert r["display_shape"] == SHAPE_PARTICIPATION
    assert r["outcome_relation"] == REL_PARTICIPATION
    assert r["expected_winners"] == 5
    assert r["exhaustive"] is False


def test_semantics_top_n_classification_is_grading_independent():
    # Grading completeness (how many is_winner are set) is a resolution property,
    # not a classification input — correctly- and incompletely-graded Top-N
    # markets classify identically. The incomplete-grading risk flag lives in the
    # census layer (scripts/evals/shape_semantics_v2.py).
    r = sem(["A", "B", "C"], source_kind="top_3")
    assert r["display_shape"] == SHAPE_PARTICIPATION
    assert r["outcome_relation"] == REL_PARTICIPATION


def test_semantics_conditional_sub_market():
    r = sem(["Yes", "No"], conditional=True, parent_condition_id="parent-1")
    assert r["outcome_relation"] == REL_CONDITIONAL
    assert r["confidence"] == "high"


def test_semantics_container_member():
    r = sem(["Yes", "No"], group_id="poly:1", group_size=72)
    assert r["display_shape"] == SHAPE_CONTAINER_MEMBER
    assert r["outcome_relation"] == REL_COMPLEMENTS


# --- Item 2: versioned, input-sensitive recompute (fingerprint) ------------

def test_fingerprint_stable_and_order_insensitive():
    a = input_fingerprint(outcome_names=["Yes", "No"], source="kalshi")
    b = input_fingerprint(outcome_names=["No", "Yes"], source="kalshi")
    assert a == b


def test_fingerprint_changes_on_late_sibling_and_late_link():
    base = dict(
        outcome_names=["Yes", "No"], source="polymarket", group_id="p:x", group_size=1
    )
    fp0 = input_fingerprint(**base)
    fp_sibling = input_fingerprint(**{**base, "group_size": 4})
    fp_link = input_fingerprint(**{**base, "event_id": 88})
    assert fp0 != fp_sibling
    assert fp0 != fp_link


def test_fingerprint_changes_on_repaired_outcomes_and_source_metadata():
    base = dict(outcome_names=["A", "B", "C"], source="datagolf")
    fp0 = input_fingerprint(**base)
    fp_outcomes = input_fingerprint(**{**base, "outcome_names": ["A", "B", "C", "D"]})
    fp_kind = input_fingerprint(**{**base, "source_kind": "top_3"})
    fp_mx = input_fingerprint(**{**base, "mutually_exclusive": True})
    assert len({fp0, fp_outcomes, fp_kind, fp_mx}) == 4


def test_late_event_link_does_not_flip_yes_no_to_duel_but_triggers_recompute():
    # The frozen-classification + event-link bugs together: a Yes/No market stays
    # a claim whether or not it later gains an event link, and its fingerprint
    # changes so the versioned recompute fires.
    before = classify_market_semantics(outcome_names=["Yes", "No"])
    after = classify_market_semantics(outcome_names=["Yes", "No"], event_id=7)
    assert before["display_shape"] == after["display_shape"] == SHAPE_CLAIM
    assert before["input_fingerprint"] != after["input_fingerprint"]


def test_semantics_is_deterministic():
    kw = dict(
        outcome_names=["A", "B", "C"],
        source="datagolf",
        source_kind="top_5",
        event_id=5,
        group_id="g",
        group_size=3,
        mutually_exclusive=False,
    )
    assert classify_market_semantics(**kw) == classify_market_semantics(**kw)
