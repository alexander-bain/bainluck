"""The row named New favorite must own the rank-change evidence (#5105)."""
from copy import deepcopy

import pytest

from app.utils.feed_reasons import generate_futures_headline
from app.utils.futures_highlights import compute_futures_highlight


def row(name, probability, rank, change, *, prior_priced=True):
    return dict(name=name, probability=probability, rank=rank,
                rank_change_24h=change, prior_priced=prior_priced,
                probability_change_24h=None)


def highlight(rows):
    return compute_futures_highlight(outcomes=rows)


@pytest.mark.parametrize("reverse", [False, True])
def test_unprinted_rank_one_cannot_supply_the_printed_leaders_claim(reverse):
    rows = [row("Printed leader", .60, 2, 0), row("Stored leader", .40, 1, 1)]
    if reverse:
        rows.reverse()
    result = highlight(rows)
    assert "leader_change" not in result.reasons
    assert not result.flags.leader_changed
    assert "New favorite" not in (generate_futures_headline(
        result.reasons, leader_name="Printed leader", leader_probability=.60) or "")


def test_duplicate_names_cannot_transfer_evidence_between_rows():
    rows = [row("Same name", .60, 2, 0), row("Same name", .40, 1, 1)]
    assert "leader_change" not in highlight(rows).reasons


@pytest.mark.parametrize("name", ["Other", "TBD"])
def test_a_demoted_or_dropped_row_cannot_supply_favorite_evidence(name):
    rows = [row(name, .99, 1, 1), row("Printed leader", .55, 2, 0)]
    assert "leader_change" not in highlight(rows).reasons


def test_unpriced_rank_one_cannot_supply_a_claim():
    assert "leader_change" not in highlight([row("No price", None, 1, 1)]).reasons


def test_equal_price_evidence_does_not_transfer_from_second_row():
    rows = [row("First displayed", .50, 1, 0), row("Second displayed", .50, 1, 1)]
    assert "leader_change" not in highlight(rows).reasons


def test_held_price_overtake_keeps_both_terms_and_exact_23_points():
    rows = [row("New leader", .60, 1, 1), row("Previous leader", .40, 2, -1)]
    unchanged = deepcopy(rows)
    for outcome in unchanged:
        outcome["rank_change_24h"] = 0
    result = highlight(rows)
    assert result.flags.leader_changed and result.flags.has_rank_shakeup
    assert result.score - highlight(unchanged).score == 23
    assert "New favorite" in (generate_futures_headline(
        result.reasons, leader_name="New leader", leader_probability=.60) or "")


def test_leader_view_does_not_remove_other_rows_from_shakeup_scoring():
    # Only the evidence-to-leader join changes. Even a placeholder remains in
    # the existing independent shakeup computation; no scoring cleanup here.
    rows = [row("Printed leader", .60, 1, 0),
            row("Other", .99, 2, -1), row("Another team", .30, 3, -1)]
    result = highlight(rows)
    assert "rank_shakeup" in result.reasons
    assert not result.flags.leader_changed


def test_input_rows_are_not_reordered_or_mutated():
    rows = [row("Previous leader", .40, 2, -1), row("New leader", .60, 1, 1)]
    before = deepcopy(rows)
    assert highlight(rows).flags.leader_changed
    assert rows == before
