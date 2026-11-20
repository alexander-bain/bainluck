"""An agreed grade survives duplicate NBA prop rows from the same venue."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.routes.events import _build_game_markets
from app.utils.source_mark import (
    fold_prop_source_marks,
    no_source_mark,
    quote_source_mark,
    settled_source_mark,
)
from tests.test_event_props_matrix_10236 import _db, _event, _market, _outcome


@pytest.mark.parametrize("won", [False, True])
def test_duplicate_graded_threes_keep_the_settled_mark(won):
    now = datetime.now(timezone.utc)
    commence = now - timedelta(hours=6)
    event = _event(status="completed", commence=commence)
    event.sport.key = "basketball_nba"
    event.home_team_name = "Golden State Warriors"
    event.away_team_name = "Los Angeles Lakers"
    event.home_score, event.away_score = 112, 95
    event.completed_at = now - timedelta(hours=3)
    event.period = None
    event.score_source = "espn"
    markets = []
    outcomes = []
    for ident in (70400285, 70400287):
        market = _market(
            id=ident,
            name="Los Angeles Lakers vs Golden State: Threes",
            source="kalshi",
            commence=commence,
        )
        market.status = "resolved"
        market.llm_sport_category = "basketball"
        outcome = _outcome(
            id=ident * 10,
            market_id=ident,
            name="Austin Reaves: 2+",
            prob=float(won),
        )
        outcome.is_winner = won
        outcome.resolution_source = "api_settlement"
        control = _outcome(
            id=ident * 10 + 1,
            market_id=ident,
            name="Austin Reaves: 1+",
            prob=1.0,
        )
        control.is_winner = True
        control.resolution_source = "api_settlement"
        markets.append(market)
        outcomes.extend((outcome, control))
    page, _, _ = asyncio.run(
        _build_game_markets(
            event.id,
            _db(event, markets, outcomes, {o.id: now for o in outcomes}),
        )
    )
    assert len(page["player_props"]) == 2
    (row,) = [
        r for r in page["player_props"] if r["outcome_name"] == "Austin Reaves: 2+"
    ]
    assert row["typing_refusal"] == "untyped_stat"
    assert row["over_probability"] == float(won)
    assert row["is_winner"] is won
    assert set(row["contributor_outcome_ids"]) == {
        o.id for o in outcomes if o.name == "Austin Reaves: 2+"
    }
    assert row["source_mark"]["state"] == "settled"
    assert row["source_mark"]["sources"] == []
    assert row["source_mark"]["settled"]["result"] == ("Won" if won else "Lost")


def test_agreed_settlement_does_not_acquire_a_price_or_observation():
    mark = settled_source_mark("espn", "Lost")
    combined = fold_prop_source_marks([mark, dict(mark)])
    assert combined == mark
    combined["settled"]["result"] = "Won"
    assert mark["settled"]["result"] == "Lost"


@pytest.mark.parametrize(
    "other",
    [
        None,
        no_source_mark("source_evidence_incomplete"),
        settled_source_mark("espn", "Lost"),
        settled_source_mark("api_settlement", "Won"),
        settled_source_mark("espn", "Won", "2020-01-01T00:00:00Z"),
        quote_source_mark([{"key": "kalshi", "probability": 0.6}]),
    ],
)
def test_disagreement_or_partial_evidence_does_not_claim_an_agreed_grade(other):
    assert fold_prop_source_marks([settled_source_mark("espn", "Won"), other]) == (
        no_source_mark("source_evidence_incomplete")
    )


def test_open_quotes_keep_the_existing_mean_and_oldest_observation():
    inputs = [
        {"key": "kalshi", "probability": 0.6, "observed_at": "2020-01-01T00:00:00Z"},
        {"key": "kalshi", "probability": 0.4, "observed_at": "2020-01-01T00:01:00Z"},
    ]
    assert fold_prop_source_marks(quote_source_mark([item]) for item in inputs) == (
        quote_source_mark(inputs)
    )
