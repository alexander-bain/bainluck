"""The feed's game headline carries the same admitted source evidence as detail."""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import Response

from tests.test_feed_candidate_unread_columns_1480 import (
    NOW, _CapturingDb, _event, _score,
)


@pytest.fixture(autouse=True)
def frozen_source_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr("app.utils.aggregation.datetime", Clock)


def _quote(value, minutes=2, *, read=True):
    at = NOW - timedelta(minutes=minutes)
    entry = {"value": value, "updated_at": NOW.isoformat()}
    if read:
        entry["price_read"] = {
            "value": value, "observed_at": at.isoformat(), "basis": None,
        }
    return entry


async def _card(sources, *, event_status="live", sport="americanfootball_nfl"):
    row = _event(1, event_status, start=NOW - timedelta(hours=1), box_reads=[])
    row.sport.key = sport
    row.win_probability_sources = sources
    row.espn_win_prob_home = None
    if event_status == "completed":
        row.completed_at = NOW - timedelta(minutes=5)
    items = await _score(_CapturingDb([row]), share_inputs=True)
    assert len(items) == 1
    return items[0]["data"]


@pytest.mark.asyncio
async def test_feed_carries_both_sides_of_the_actual_blend_and_keeps_read_times():
    data = await _card({"kalshi": _quote(.62), "polymarket": _quote(.60, 3)})
    home, away = data["source_mark"], data["away_source_mark"]
    assert home["state"] == away["state"] == "blend"
    assert [s["key"] for s in home["sources"]] == ["kalshi", "polymarket"]
    assert [s["probability"] for s in home["sources"]] == [.62, .60]
    assert [s["probability"] for s in away["sources"]] == [.38, .40]
    assert home["sources"][0]["observed_at"] == (NOW - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    assert away["sources"][0]["observed_at"] == home["sources"][0]["observed_at"]
    assert "weighted average" in home["method"]
    # A feed cache's JSON round trip may not replace the quote clock.
    assert json.loads(json.dumps(data))["source_mark"] == home


@pytest.mark.asyncio
async def test_divergence_mark_credits_only_the_admitted_source():
    data = await _card({"betting": _quote(.90), "kalshi": _quote(.10), "betting_book_count": 5})
    assert data["hero_probability"] == .90
    mark = data["source_mark"]
    assert mark["state"] == "single"
    assert [(s["key"], s["probability"], s.get("count")) for s in mark["sources"]] == [("betting", .90, 5)]


@pytest.mark.asyncio
async def test_a_poll_touch_alone_cannot_give_the_card_an_age():
    data = await _card({"kalshi": _quote(.62, read=False)})
    source = data["source_mark"]["sources"][0]
    assert source["observed_at"] is None
    assert source["reason"] == "observation_unknown"


@pytest.mark.asyncio
async def test_price_change_without_matching_evidence_drops_only_the_age():
    quote = _quote(.62)
    quote["value"] = .63
    data = await _card({"kalshi": quote})
    assert data["source_mark"]["sources"][0]["probability"] == .63
    assert data["source_mark"]["sources"][0]["observed_at"] is None


@pytest.mark.asyncio
async def test_verified_final_marks_both_results_without_listing_old_quotes():
    data = await _card({"betting": _quote(.6)}, event_status="completed")
    assert data["source_mark"]["state"] == "settled"
    assert data["source_mark"]["sources"] == []
    assert data["source_mark"]["settled"]["result"] == "Won"
    assert data["away_source_mark"]["settled"]["result"] == "Lost"


@pytest.mark.asyncio
async def test_a_draw_priced_game_does_not_claim_a_complemented_away_quote():
    data = await _card({"kalshi": _quote(.62)}, sport="soccer_epl")
    assert data["source_mark"]["state"] == "single"
    assert data["away_source_mark"] == {
        "state": "none", "sources": [], "reason": "away_unavailable",
    }


@pytest.mark.asyncio
async def test_price_card_refresh_advances_evidence_even_when_the_price_is_unchanged(monkeypatch):
    from app.routes import feed, feed_prices
    from tests.test_feed_price_cards_9515 import result

    row = _event(1, "live", start=NOW - timedelta(hours=1), box_reads=[])
    row.espn_win_prob_home = None
    db = AsyncMock()
    db.execute.return_value = result([row])
    monkeypatch.setattr(feed, "enrich_event_team_data", AsyncMock())
    monkeypatch.setattr(feed_prices, "folded_probability_sources_with_revision", AsyncMock(
        side_effect=[
            ({"kalshi": _quote(.62, 3)}, {"1": 8}),
            ({"kalshi": _quote(.62, 1)}, {"1": 9}),
        ],
    ))
    first_response, second_response = Response(), Response()
    first = await feed_prices.get_price_cards(first_response, "1", "", db)
    second = await feed_prices.get_price_cards(second_response, "1", "", db)
    before, after = first["items"][0]["data"], second["items"][0]["data"]
    assert before["hero_probability"] == after["hero_probability"] == .62
    assert second["dispositions"] == {"event-1": "updated"}
    assert after["blend_fold_revision"] == {"1": 9}
    assert second_response.headers["cache-control"] == "no-store"
    # The fresh row's bound price-read evidence replaces the old one on both axes.
    for key in ("source_mark", "away_source_mark"):
        assert before[key]["sources"][0]["observed_at"] == (NOW - timedelta(minutes=3)).isoformat().replace("+00:00", "Z")
        assert after[key]["sources"][0]["observed_at"] == (NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    assert db.execute.await_count == 2  # One existing event read per request.
