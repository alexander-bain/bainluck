"""Source attribution through the Sports grouped-feed route and its cache."""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import Response
from fastapi.encoders import jsonable_encoder

from app.routes.futures import grouped_feed
from app.utils.grouped_feed_cache import grouped_feed_cache_key
from tests.test_grouped_feed_cache_encoding_2554 import redis  # noqa: F401
from tests.test_grouped_feed_container_fold_route_4153 import (
    _members,
    _parents,
    _pool,
    _StubSession,
)


def _outcome(outcome_id, name, price, *, grade=None, authority=None):
    probability = Decimal(price) if price is not None else None
    return SimpleNamespace(
        id=outcome_id, name=name, probability=probability,
        current_probability=probability, american_odds=None,
        is_winner=grade, resolution_source=authority,
        last_updated="2026-11-17T19:00:00Z",
    )


def _market(market_id, name, source, outcomes, *, group_id=None, status="open"):
    return SimpleNamespace(
        id=market_id, name=name, source=source, category="game_prop",
        llm_sport_category="basketball", status=status, group_id=group_id,
        group_type=None, market_type=None, outcomes=outcomes,
    )


async def _serve(session):
    response = Response()
    payload = await grouped_feed(
        request=SimpleNamespace(scope={}), response=response, category=None,
        sport=None, sports_only=False, limit=20, db=session,
    )
    return jsonable_encoder(payload), response.headers["X-Grouped-Cache"]


def _assert_quote(mark, key, price):
    assert mark["state"] == "single"
    (source,) = mark["sources"]
    assert source["key"] == key
    assert source["probability"] == price
    assert source["observed_at"] is None


@pytest.mark.asyncio
async def test_market_threshold_and_score_keep_each_quote_through_cache(redis):
    markets = [
        _market(1, "Road at Home: Total Games", "kalshi", [
            _outcome(11, "Over 18.5 games", "0.68"),
        ], group_id="total"),
        _market(2, "Road at Home: Total Games", "polymarket", [
            _outcome(12, "Over 20.5 games", "0.53"),
        ], group_id="total"),
        _market(3, "United at City - Exact Score", "polymarket", [
            _outcome(21, "1-1", "0.21"), _outcome(22, "2-1", "0.11"),
        ]),
        _market(4, "Game winner", "odds_api", [
            _outcome(31, "Home", "0.54", grade=False, authority="ungradeable_result"),
            _outcome(32, "Away", "0.00"),
            _outcome(33, "Draw", None),
        ], status="active"),
    ]
    key = grouped_feed_cache_key(category=None, sport=None, sports_only=False, limit=20)
    fingerprint = key.rsplit(":", 1)[-1]
    redis.store[f"bainluck:grouped_feed:v1:{fingerprint}"] = json.dumps({"feed": ["old"]})
    session = _StubSession([markets])
    payload, status = await _serve(session)
    assert status == "miss" and session.calls == 1
    cards = {card.get("kind") or card["type"]: card for card in payload["feed"]}

    points = cards["threshold"]["points"]
    assert [(row["id"], row["probability"]) for row in points] == [(11, 0.68), (12, 0.53)]
    _assert_quote(points[0]["source_mark"], "kalshi", 0.68)
    _assert_quote(points[1]["source_mark"], "polymarket", 0.53)
    score = cards["exact_score"]["points"][0]
    assert (score["id"], score["label"], score["probability"]) == (21, "1–1", 0.21)
    _assert_quote(score["source_mark"], "polymarket", 0.21)
    home, away, draw = cards["market"]["market"]["outcomes"]
    _assert_quote(home["source_mark"], "betting", 0.54)
    _assert_quote(away["source_mark"], "betting", 0.0)
    assert draw["source_mark"]["reason"] == "no_probability"

    cached, status = await _serve(_StubSession([]))
    assert status == "hit" and cached == payload
    del redis.store[key]
    stale, status = await _serve(_StubSession([]))
    assert status == "stale_hit" and stale == payload


@pytest.mark.asyncio
async def test_stat_prop_and_progression_mark_the_first_selected_outcome(redis):
    markets = [
        _market(1, "Jayson Tatum: 25+ Points", "kalshi", [
            _outcome(11, "Yes", "0.48"), _outcome(12, "No", "0.52"),
        ]),
        _market(2, "Jayson Tatum: 30+ Points", "polymarket", []),
        _market(3, "Lakers: Make Playoffs", "kalshi", [
            _outcome(31, "Yes", "0.65"),
        ]),
        _market(4, "Lakers: Make Round 2", "polymarket", [
            _outcome(41, "Yes", "0.32"),
        ]),
    ]
    payload, _ = await _serve(_StubSession([markets]))
    cards = {card["type"]: card for card in payload["feed"]}
    line, empty = cards["stat_prop"]["lines"]
    assert line["probability"] == 0.48
    _assert_quote(line["source_mark"], "kalshi", 0.48)
    assert empty["probability"] is None and empty["source_mark"]["state"] == "none"
    first, second = cards["playoff_progression"]["stages"]
    _assert_quote(first["source_mark"], "kalshi", 0.65)
    _assert_quote(second["source_mark"], "polymarket", 0.32)


@pytest.mark.asyncio
async def test_placement_marks_each_selected_cell_and_leaves_absent_cells_empty(redis):
    markets = [
        _market(1, "Omega European Masters - Winner", "kalshi", [
            _outcome(11, "Angel Ayora", "0.12"),
        ]),
        _market(2, "Omega European Masters - Top 5 Finish", "polymarket", [
            _outcome(21, "Angel Ayora", "0.38"),
        ]),
        _market(3, "Omega European Masters - Top 10 Finish", "kalshi", [
            _outcome(31, "Marco Penge", "0.40"),
        ]),
        _market(4, "Omega European Masters - Top 5 Finish", "odds_api", [
            _outcome(41, "Angel Ayora", "0.42"),
        ]),
    ]
    payload, _ = await _serve(_StubSession([markets]))
    grid = next(card for card in payload["feed"] if card["type"] == "placement_grid")
    ayora, penge = grid["rows"]
    assert ayora["values"] == {"winner": 0.12, "top_5": 0.38, "top_10": None}
    assert set(ayora["source_marks"]) == {"winner", "top_5"}
    _assert_quote(ayora["source_marks"]["winner"], "kalshi", 0.12)
    _assert_quote(ayora["source_marks"]["top_5"], "polymarket", 0.38)
    _assert_quote(penge["source_marks"]["top_10"], "kalshi", 0.4)


@pytest.mark.asyncio
async def test_fold_marks_its_full_membership_yes_legs_and_respects_official_grade(redis):
    members = _members()
    # A settled Yes leg can be graded before its parent field status updates.
    for index, row in enumerate(members):
        if row[1] == 1:
            leg = row[5]
            members[index] = (*row[:6], float(leg == "Yes"), leg == "Yes", "api_settlement")
    session = _StubSession([_pool(), _parents(), members])
    payload, _ = await _serve(session)
    cards = [card["market"] for card in payload["feed"] if card["type"] == "market"]
    final = next(card for card in cards if card["name"].startswith("US Open 2026:"))
    leader, runner_up = final["outcomes"][:2]
    assert leader["name"] == "Belinda Bencic"
    assert leader["source_mark"]["settled"]["result"] == "Won"
    assert runner_up["name"] == "Maria Sakkari"
    _assert_quote(runner_up["source_mark"], "polymarket", 0.48)
    assert session.calls == 3
