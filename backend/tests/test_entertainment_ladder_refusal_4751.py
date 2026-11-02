"""A collapsed board keeps its destination without authorizing a price fallback."""
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import entertainment
from tests.test_entertainment_ladder_coherence_4751 import market, rows_in, COHERENT, VISION_QUEST


@pytest.mark.parametrize("limit", [1, 3, 8])
def test_collapsed_field_is_explicit_and_keeps_legacy_shape_without_a_hook(monkeypatch, limit):
    m = market([("Above 10", .2), ("Above 20", .9), ("Above 30", .95)])
    m.hook_description = "Above 30 is 95% likely"
    monkeypatch.setattr(entertainment, "is_hook_stale", lambda **kwargs: False)
    original = deepcopy(m)
    row = entertainment._market_row(m, max_outcomes=limit)
    assert row["ladder_treatment_refused"] is True
    assert row["headline"] is None
    assert row["hook"] is None
    presentation = entertainment._market_row(m, max_outcomes=8)
    entertainment._mark_ladder(presentation)
    assert presentation["ladder"] is True
    assert row["market_id"] == m.id
    assert row["q"] == m.name
    assert row["top_outcomes"]  # older decoders keep their required numeric shape
    assert row["prob"] == 95
    assert m == original


@pytest.mark.parametrize("legs", [COHERENT, [("A", .2), ("B", .9), ("C", .95)], [("Above 10", .7), ("Above 20", None), ("Above 30", 0)]])
def test_supported_unknown_missing_and_zero_are_not_refused(legs):
    row = entertainment._market_row(market(legs), max_outcomes=8)
    assert row.get("ladder_treatment_refused") is not True


@pytest.mark.parametrize("legs", [VISION_QUEST, [("Above 45", .88), ("Above 65", .9), ("Above 70", .37)]])
def test_previous_tolerance_controls_now_refuse_the_visible_residual(legs):
    # Both previously passed through numeric cards. The original #4751
    # acceptance rules out that behavior, including after a partial trim.
    row = entertainment._market_row(market(legs), max_outcomes=8)
    assert row["ladder_treatment_refused"] is True
    assert row["headline"] is None


def test_grouping_cannot_turn_a_refused_board_back_into_a_heatmap_price():
    bad = entertainment._market_row(market([("Above 10", .2), ("Above 20", .9), ("Above 30", .95)]))
    good = entertainment._market_row(market(COHERENT, market_id=4752))
    other = entertainment._market_row(market(COHERENT, market_id=4753))
    for row, threshold in [(bad, 10), (good, 20), (other, 30)]:
        row["q"] = f'"A movie" score at least {threshold}'
    groups, ungrouped = entertainment._group_threshold_markets([bad, good, other])
    assert len(groups) == 1
    assert {r["market_id"] for r in groups[0]["thresholds"]} == {4752, 4753}
    assert ungrouped == [bad]


async def test_actual_response_preserves_refusal_at_every_occurrence(monkeypatch):
    subject = market([("Above 10", .2), ("Above 20", .9), ("Above 30", .95)])
    subject.hook_description = "Above 30 is 95% likely"
    control = market(COHERENT, market_id=4752)
    db, result = AsyncMock(), MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = [subject, control]
    db.execute.return_value = result
    monkeypatch.setattr(entertainment, "_withheld_price_outcome_ids", AsyncMock(return_value=set()))
    monkeypatch.setattr(entertainment, "_fleet_newest_observation", AsyncMock(return_value=None))
    monkeypatch.setattr(entertainment, "is_hook_stale", lambda **kwargs: False)
    rows = list(rows_in(await entertainment.get_entertainment(db)))
    subject_rows = [row for row in rows if row["market_id"] == subject.id]
    assert len(subject_rows) >= 2  # trending and category copies
    for row in subject_rows:
        assert row["ladder_treatment_refused"] is True
        assert row["hook"] is None
        assert row["headline"] is None
    assert any(row["market_id"] == control.id for row in rows)
    assert db.execute.await_count == 1
