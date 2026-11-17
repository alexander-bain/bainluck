"""A futures feed number carries its own input through every card treatment."""

import copy
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

import app.routes.feed as feed
from app.utils.discover_card_archetypes import classify_discover_card_archetype
from app.utils.futures_market_snapshot import from_plain, to_plain
from app.utils.personalization import PersonalizationContext
from app.utils.principal_independent_cache import (
    clear_shared_builds,
    decode_shared_payload,
    encode_shared_payload,
)
from app.utils.source_mark import quote_source_mark
from tests.test_feed_broaden_pass_reuse import (
    NOW,
    _CountingDB,
    _Market,
    _Outcome,
    _base_hit,
    _no_redis,
)
from tests.test_futures_verified_title_9387 import _at


def board(shape="field", source="kalshi"):
    market = _Market(1)
    market.source = source
    if shape == "field":
        names = ["Kamala Harris", "Donald Trump", "Gretchen Whitmer", "Gavin Newsom"]
        prices = [0.5, 0.3, 0.2, 0.1]
    elif shape == "ladder":
        market.name = "Indianapolis Colts total wins"
        names, prices = ["6.5+ wins", "8.5+ wins", "10.5+ wins"], [0.6, 0.3, 0.1]
        market.mutually_exclusive = False
    else:
        market.name = "When will the next lunar landing happen?"
        names, prices = ["Before January 2028", "Before January 2029"], [0.3, 0.6]
        market.mutually_exclusive = False
    market.outcomes = [
        _Outcome(100 + n, name, price, opening=max(0.02, price - 0.1), change=0.1)
        for n, (name, price) in enumerate(zip(names, prices))
    ]
    for outcome in market.outcomes:
        outcome.last_updated = NOW - timedelta(minutes=2)
        outcome.is_winner = outcome.resolution_source = None
    return market


@pytest.fixture(autouse=True)
def feed_io(monkeypatch):
    # Keep the real scoring, filtering, normalization and serializers. Only
    # existing IO is pinned, with three canonical venues that are NOT inputs.
    for name in (
        "_team_names_by_id",
        "out_legs_by_market",
        "graded_out_leg_ids_by_market",
    ):
        monkeypatch.setattr(feed, name, AsyncMock(return_value={}))
    monkeypatch.setattr(
        feed, "withheld_price_outcome_ids_for_markets", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        feed, "_get_canonical_source_counts", AsyncMock(return_value={"field": 3})
    )
    monkeypatch.setattr(
        feed,
        "_canonical_source_names_cache",
        {"field": ["kalshi", "polymarket", "odds_api"]},
    )
    monkeypatch.setenv("FEED_SPORTS_METADATA_REUSE", "0")
    yield
    clear_shared_builds()


async def serve(monkeypatch, market, mode, *, cached=False):
    clear_shared_builds()
    with _at(NOW), _no_redis():
        markets = (
            from_plain(decode_shared_payload(encode_shared_payload(to_plain([market]))))
            if cached
            else [market]
        )
        db = _CountingDB(markets)
        if mode == "sports":
            items = await feed._score_sports_mode_futures(
                db, NOW, None, PersonalizationContext()
            )
        else:
            _base_hit(monkeypatch, [market.id], set())
            items = await feed._score_futures(
                db,
                NOW,
                None,
                PersonalizationContext(),
                preloaded_base={"markets": markets} if cached else None,
            )
    assert len(items) == 1, items
    return items[0], [str(query) for query in db.executed]


@pytest.mark.parametrize("mode", ["discover", "sports"])
@pytest.mark.parametrize("shape", ["field", "ladder", "date"])
@pytest.mark.parametrize(
    "source,key",
    [("kalshi", "kalshi"), ("polymarket", "polymarket"), ("odds_api", "betting")],
)
async def test_each_feed_row_names_its_input_after_normalization_and_sorting(
    monkeypatch, mode, shape, source, key
):
    market = board(shape, source)
    market.canonical_market_key = "field"
    item, _ = await serve(monkeypatch, market, mode)
    data = item["data"]
    assert data["source_count"] == 3
    raw = {o.name: o.current_probability for o in market.outcomes}
    lists = [data["top_outcomes"], data["discover_card"]["distribution_outcomes"]]
    if shape != "field":
        assert len(data["discover_card"]["threshold_points"]) >= 2
        lists.append(data["discover_card"]["threshold_points"])
    for rows in lists:
        assert rows
        for row in rows:
            mark = row["source_mark"]
            name = row.get("name", row.get("label"))
            assert mark["state"] == "single"
            assert [(s["key"], s["probability"]) for s in mark["sources"]] == [
                (key, raw[name])
            ]
            assert mark["sources"][0]["observed_at"] is None
            assert mark["sources"][0]["reason"] == "observation_unknown"
            if abs(row["probability"] - raw[name]) > 1e-8:
                assert "scaled with the other outcomes" in mark["method"]


@pytest.mark.parametrize("mode", ["discover", "sports"])
async def test_snapshot_and_response_cache_preserve_prices_marks_and_no_source_clock(
    monkeypatch, mode
):
    market = board()
    live, live_queries = await serve(monkeypatch, market, mode)
    rebuilt, snapshot_queries = await serve(monkeypatch, market, mode, cached=True)
    for field in ("top_outcomes", "discover_card"):
        assert rebuilt["data"][field] == live["data"][field]
    if mode == "discover":
        assert len(live_queries) == 1
        assert snapshot_queries == []
    else:
        assert len(live_queries) == 2
        assert snapshot_queries == live_queries
    assert decode_shared_payload(encode_shared_payload(rebuilt)) == rebuilt
    assert all("source_mark" in row for row in rebuilt["data"]["top_outcomes"])


@pytest.mark.parametrize("mode", ["discover", "sports"])
async def test_database_decimal_ladder_keeps_its_card_and_raw_values(monkeypatch, mode):
    market = board("ladder")
    for outcome in market.outcomes:
        outcome.current_probability = Decimal(str(outcome.current_probability))
    item, _ = await serve(monkeypatch, market, mode)
    rows = item["data"]["top_outcomes"]
    original = {o.id: o.current_probability for o in market.outcomes}
    assert len(rows) == len(original)
    for row in rows:
        assert row["probability"] == original[row["id"]]
        mark = row["source_mark"]
        assert mark["sources"][0]["probability"] == float(original[row["id"]])
        assert "method" not in mark


@pytest.mark.parametrize("mode", ["discover", "sports"])
@pytest.mark.parametrize("cached", [False, True])
async def test_saved_grade_evidence_survives_snapshot_without_inventing_a_result(
    monkeypatch, mode, cached
):
    market = board()
    market.outcomes[1].is_winner = False
    market.outcomes[1].resolution_source = "api_settlement"
    market.outcomes[2].is_winner = False
    market.outcomes[2].resolution_source = "ungradeable_result"
    item, _ = await serve(monkeypatch, market, mode, cached=cached)
    rows = {r["id"]: r for r in item["data"]["top_outcomes"]}
    assert rows[101]["source_mark"]["state"] == "settled"
    assert rows[101]["source_mark"]["settled"] == {
        "source": "api_settlement",
        "result": "Lost",
        "at": None,
    }
    assert rows[102]["source_mark"] == {
        "state": "none",
        "sources": [],
        "reason": "result_unknown",
    }


@pytest.mark.parametrize("mode", ["discover", "sports"])
async def test_withheld_leg_leaves_no_mark_and_supported_zero_stays_a_quote(
    monkeypatch, mode
):
    market = board()
    market.outcomes[0].current_probability = 0.0
    market.withheld_outcome_ids = [101]
    monkeypatch.setattr(
        feed,
        "withheld_price_outcome_ids_for_markets",
        AsyncMock(return_value={market.id: [101]}),
    )
    item, _ = await serve(monkeypatch, market, mode)
    rows = item["data"]["top_outcomes"]
    assert 101 not in {row["id"] for row in rows}
    zero = next(row for row in rows if row["id"] == 100)
    assert zero["probability"] == 0
    assert zero["source_mark"]["sources"][0]["probability"] == 0


@pytest.mark.parametrize("shape", ["ladder", "date"])
def test_archetype_reordering_carries_each_inputs_identity(shape):
    market = board(shape)
    rows = [
        {
            "name": o.name,
            "probability": o.current_probability,
            "source_mark": quote_source_mark(
                [
                    {
                        "key": "kalshi",
                        "probability": o.current_probability,
                        "observed_at": None,
                    }
                ]
            ),
        }
        for o in market.outcomes
    ]
    # The classifier sorts in ladder order, opposite the date board's input.
    rows.reverse()
    result = classify_discover_card_archetype(
        name=market.name, outcomes=rows, outcome_count=len(rows)
    )
    for row in result["threshold_points"] + result["distribution_outcomes"]:
        assert row["source_mark"]["sources"][0]["probability"] == row["probability"]


def test_equal_display_names_do_not_cross_wire_marks():
    rows = [
        {
            "name": "Same name",
            "probability": p,
            "source_mark": quote_source_mark(
                [{"key": "kalshi", "probability": p, "observed_at": None}]
            ),
        }
        for p in (0.2, 0.7)
    ]
    original = copy.deepcopy(rows)
    result = classify_discover_card_archetype(
        name="Who wins?", outcomes=rows, outcome_count=2
    )
    assert [
        r["source_mark"]["sources"][0]["probability"]
        for r in result["distribution_outcomes"]
    ] == [0.2, 0.7]
    assert rows == original
