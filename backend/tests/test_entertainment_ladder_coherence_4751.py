"""#4751: the category builder applies the existing ladder policy before selection.

VisionQuest prices are the historical issue-comment specimen, not a fresh
production reproduction. Other fixtures are synthetic controls after admission.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import entertainment

VISION_QUEST = [
    ("Above 55", 0.975),
    ("Above 90", 0.96),
    ("Above 75", 0.89),
    ("Above 45", 0.88),
    ("Above 65", 0.875),
    ("Above 50", 0.875),
    ("Above 60", 0.86),
    ("Above 70", 0.85),
]
COHERENT = [("Above 45", 0.9), ("Above 65", 0.7), ("Above 75", 0.4)]


def market(legs, *, market_id=4751):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name="VisionQuest · Rotten Tomatoes score",
        source="kalshi",
        external_id=f"KXRTTV-TEST{market_id}",
        status="open",
        category="entertainment",
        llm_sport_category="entertainment",
        group_id=None,
        market_metadata=None,
        volume_24h=1000,
        resolution_date=now + timedelta(days=30),
        updated_at=now,
        image_url=None,
        hook_description=None,
        outcomes=[
            SimpleNamespace(
                id=market_id * 100 + i,
                name=name,
                current_probability=prob,
                probability_change_24h=0,
                external_id=None,
                rank=i,
                is_winner=None,
                resolution_source=None,
                last_updated=now,
            )
            for i, (name, prob) in enumerate(legs)
        ],
    )


def names(row):
    return [o["name"] for o in row["top_outcomes"]]


@pytest.mark.parametrize("limit", [1, 3, 6, 8])
def test_issue_specimen_filters_before_headline_and_top_n(limit):
    m = market(VISION_QUEST)
    original = deepcopy(m)
    row = entertainment._market_row(m, max_outcomes=limit)
    # Longest coherent run retains 45, 50, 60, 65, 70. The disputed
    # 55, 75 and 90 prices cannot lead or be the median/headline.
    assert (
        names(row)
        == ["Above 45", "Above 65", "Above 50", "Above 60", "Above 70"][:limit]
    )
    assert row["prob"] == 88
    # The retained 60/65 pair still reverses .86/.875 within the trim tolerance.
    # Preserve the trim, but do not turn that residual field into a headline.
    assert row["headline"] is None
    assert row["ladder_treatment_refused"] is True
    assert row["outcome_count"] == 8
    assert m == original  # no column writes or mutation of shared ORM rows


def test_withheld_rung_cannot_condemn_supported_siblings():
    m = market(
        [("Above 10", 0.2), ("Above 20", 0.8), ("Above 30", 0.7), ("Above 40", 0.6)]
    )
    row = entertainment._market_row(m, max_outcomes=8, withheld_ids={m.outcomes[0].id})
    assert names(row) == ["Above 20", "Above 30", "Above 40"]
    assert row["headline"] == {"name": "Above 40", "prob": 60}


@pytest.mark.parametrize("prob,withheld", [(None, False), (0.99, True)])
def test_missing_unparseable_leg_cannot_manufacture_ladder_semantics(prob, withheld):
    m = market(COHERENT + [("Special exception", prob)])
    row = entertainment._market_row(
        m,
        withheld_ids={m.outcomes[-1].id} if withheld else set(),
    )
    assert names(row) == ["Above 45", "Above 65", "Above 75"]
    assert row["headline"] is None


@pytest.mark.parametrize(
    "legs",
    [
        [("Above 10", 0.2), ("Above 20", 0.9), ("Above 30", 0.95)],
        [("Above 10", 0.2), ("Above 20", 0.9)],
    ],
)
def test_unattributable_reversal_preserves_field_without_a_ladder_headline(legs):
    m = market(legs)
    row = entertainment._market_row(m, max_outcomes=8)
    assert set(names(row)) == {name for name, _ in legs}
    assert row["headline"] is None


@pytest.mark.parametrize(
    "legs,is_ladder",
    [
        ([("Above 10", 0.2), ("Above 20", 0.9), ("Above 30", 0.95)], True),
        (COHERENT + [("Special exception", None)], False),
    ],
)
def test_music_preserves_full_board_identity_without_a_false_headline(legs, is_ladder):
    m = market(legs)
    m.external_id = "kxspotify-test"
    m.name = "Spotify streams in October"
    section = entertainment._build_music({"music": [m]})
    row = section["spotify_race"][0]
    assert row["ladder"] is is_ladder
    assert row["headline"] is None
    assert set(names(row)) == {name for name, prob in legs if prob is not None}
    if is_ladder:
        assert names(row) == [name for name, _ in legs]


@pytest.mark.parametrize(
    "legs,headline",
    [
        (COHERENT, {"name": "Above 65", "prob": 70}),
        ([("Above 45", 0.88), ("Above 65", 0.90), ("Above 70", 0.37)], None),
        ([("One", 0.3), ("Two", 0.7), ("Three", 0.5)], None),
        ([("0-10", 0.3), ("10-20", 0.7), ("20-30", 0.5)], None),
        ([("Above 10", 0.7), ("Above 20", None), ("Above 30", 0)], None),
    ],
)
def test_coherent_tolerance_nonladder_and_real_zero_controls(legs, headline):
    m = market(legs)
    row = entertainment._market_row(m, max_outcomes=8)
    expected = sorted(
        (x for x in legs if x[1] is not None), key=lambda x: x[1], reverse=True
    )
    assert [(o["name"], o["prob"]) for o in row["top_outcomes"]] == [
        (n, round(p * 100, 1)) for n, p in expected
    ]
    assert row["headline"] == headline
    assert row["outcome_count"] == len(legs)


def test_all_withheld_or_unpriced_still_refuses_card():
    m = market(COHERENT)
    assert entertainment._market_row(m, withheld_ids={o.id for o in m.outcomes}) is None
    assert (
        entertainment._market_row(market([("Above 10", None), ("Above 20", None)]))
        is None
    )


def rows_in(value):
    if isinstance(value, dict):
        if "market_id" in value and "top_outcomes" in value:
            yield value
        for child in value.values():
            yield from rows_in(child)
    elif isinstance(value, list):
        for child in value:
            yield from rows_in(child)


async def test_real_response_builder_filters_all_card_occurrences_and_preserves_settled_gate(
    monkeypatch,
):
    bad = market(VISION_QUEST)
    control = market(COHERENT, market_id=4752)
    settled = market(COHERENT, market_id=4753)
    for outcome in settled.outcomes:
        outcome.is_winner = outcome is settled.outcomes[0]
        outcome.resolution_source = "api_settlement"
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = [
        bad,
        control,
        settled,
    ]
    db.execute.return_value = result
    # Fixture already represents admitted prices; acquisition is not this repair.
    refusal = AsyncMock(return_value=set())
    monkeypatch.setattr(entertainment, "_withheld_price_outcome_ids", refusal)
    monkeypatch.setattr(
        entertainment, "_fleet_newest_observation", AsyncMock(return_value=None)
    )
    payload = await entertainment.get_entertainment(db)
    rows = list(rows_in(payload))
    bad_rows = [r for r in rows if r["market_id"] == bad.id]
    assert bad_rows
    for row in bad_rows:
        assert not {"Above 55", "Above 75", "Above 90"}.intersection(names(row))
        assert row["prob"] == 88
        assert row["headline"] is None
        assert row["ladder_treatment_refused"] is True
        if "lead_outcomes" in row:
            assert not {"Above 55", "Above 75", "Above 90"}.intersection(
                o["name"] for o in row["lead_outcomes"]
            )
    assert any(r["market_id"] == control.id for r in rows)
    assert all(r["market_id"] != settled.id for r in rows)
    assert {call.args[1].id for call in refusal.await_args_list} == {bad.id, control.id}
    assert db.execute.await_count == 1
