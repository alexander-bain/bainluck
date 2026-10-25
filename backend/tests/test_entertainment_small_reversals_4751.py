"""Original #4751 quantities must not escape through the 2pp trim tolerance.

Historical issue specimens, not current quotes. No price is repaired or invented.
"""

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import entertainment
from tests.test_entertainment_ladder_coherence_4751 import COHERENT, market, rows_in

BLADE_RUNNER = [
    ("Above 45", 0.88),
    ("Above 65", 0.90),
    ("Above 70", 0.37),
    ("Above 75", 0.20),
    ("Above 80", 0.11),
]
PEACOCK = [
    ("Above 98", 0.52),
    ("Above 104", 0.35),
    ("Above 110", 0.36),
    ("Above 113", 0.35),
    ("Above 116", 0.28),
    ("Above 119", 0.22),
    ("Above 122", 0.11),
]


@pytest.mark.parametrize(
    "legs",
    [
        BLADE_RUNNER,
        PEACOCK,
        [("Below 10", 0.36), ("Below 20", 0.35), ("Below 30", 0.52)],
        [("Above 45", 0.88), ("Above 65", 0.90)],
    ],
)
@pytest.mark.parametrize("limit", [1, 3, 8])
def test_residual_numeric_conflict_refuses_before_selection(monkeypatch, legs, limit):
    subject = market(list(reversed(legs)))  # storage/probability order is irrelevant
    subject.hook_description = "More likely than not: Above 65"
    monkeypatch.setattr(entertainment, "is_hook_stale", lambda **kwargs: False)
    before = deepcopy(subject)
    row = entertainment._market_row(subject, max_outcomes=limit)
    assert row.get("ladder_treatment_refused") is True
    assert row["headline"] is None
    assert row["hook"] is None
    assert row["market_id"] == subject.id
    presentation = entertainment._market_row(subject, max_outcomes=8)
    entertainment._mark_ladder(presentation)
    assert presentation["ladder"] is True
    assert subject == before


@pytest.mark.parametrize(
    "legs",
    [
        [("Above 10", 0.9), ("Above 20", 0.9), ("Above 30", 0)],
        [("Below 10", 0), ("Below 20", 0.2), ("Below 30", 0.2)],
        [("Above 10", 0.7), ("Above 20", None), ("Above 30", 0)],
        [("Above 10", 0.2), ("Above 20", 0.9), ("Above 30", 0.8), ("Above 40", 0.7)],
        [("0-10", 0.88), ("10-20", 0.9), ("20-30", 0.37)],
        BLADE_RUNNER + [("Special exception", None)],
        [("By June 2027", 0.50), ("By July 2027", 0.49), ("By August 2027", 0.80)],
    ],
)
def test_equal_zero_absent_trimmed_mixed_and_date_controls(legs):
    row = entertainment._market_row(market(legs), max_outcomes=8)
    assert row.get("ladder_treatment_refused") is not True


def test_withheld_conflict_does_not_refuse_supported_field():
    subject = market(BLADE_RUNNER)
    row = entertainment._market_row(subject, withheld_ids={subject.outcomes[1].id})
    assert row.get("ladder_treatment_refused") is not True
    assert "Above 65" not in [o["name"] for o in row["top_outcomes"]]


@pytest.mark.parametrize("legs", [BLADE_RUNNER, PEACOCK])
async def test_response_keeps_refusal_on_every_copy_and_supported_siblings(
    monkeypatch, legs
):
    subject = market(legs)
    control = market(COHERENT, market_id=4752)
    db, result = AsyncMock(), MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = [
        subject,
        control,
    ]
    db.execute.return_value = result
    monkeypatch.setattr(
        entertainment, "_withheld_price_outcome_ids", AsyncMock(return_value=set())
    )
    monkeypatch.setattr(
        entertainment, "_fleet_newest_observation", AsyncMock(return_value=None)
    )
    rows = list(rows_in(await entertainment.get_entertainment(db)))
    refused = [row for row in rows if row["market_id"] == subject.id]
    assert len(refused) >= 2
    assert all(
        row["ladder_treatment_refused"] and row["headline"] is None for row in refused
    )
    assert any(
        row["market_id"] == control.id and not row.get("ladder_treatment_refused")
        for row in rows
    )
    assert db.execute.await_count == 1
