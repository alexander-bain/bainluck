"""#10230 — `/api/events/typeahead?q=judge` reaches an Aaron Judge market.

Production 2026-10-02 19:58Z: the dropdown was the impeachment question and four
Texas county-judge races. Every name match trades under $10k (most have no volume
at all); "MLB The Show 27: Cover Athlete" prices Aaron Judge at 8.5% on $21.8k and
never reached the five futures rows. Rows below are the production values.

Driven through the route, not the reranker alone: the dropdown takes the first five
reranked rows and then re-sorts every pool by match class, so a reranker-only test
cannot see whether the row survives to the response.
"""

import pytest

from tests.integration.test_route_typeahead_headline_slot_2579 import (
    _client,
    _market,
    _outcome,
)

_asyncio = pytest.mark.asyncio

SHOW_COVER_ID = 24014885
AL_MVP_ID = 216


def _county(mid, county, volume=None):
    return _market(
        mid=mid, name=f"{county} County Judge winner?", volume=volume, tier=1,
        outcomes=[_outcome("Candidate A", 0.7, mid * 10 + 1),
                  _outcome("Candidate B", 0.3, mid * 10 + 2)],
    )


def _categorised(market, category):
    # The shared `_market` stamps every row "tennis", which makes "Harris County
    # Judge winner?" read as a tennis winner board and mint a tournament concept
    # row that production never serves. These are the rows' real categories.
    market.llm_sport_category = category
    market.category = category
    return market


def _window():
    rows = _rows()
    for m in rows:
        _categorised(m, "baseball" if m.id in (AL_MVP_ID, SHOW_COVER_ID) else "politics")
    return rows


def _rows():
    return [
        _county(60481098, "Harris", 4005.0),
        _county(63135151, "Bexar"),
        _county(63135150, "Collin"),
        _county(63135142, "Tarrant"),
        _county(63135147, "Fort Bend"),
        _county(63135148, "El Paso"),
        _market(mid=AL_MVP_ID, name="AL MVP Winner?", volume=5_055_009.0, tier=3,
                outcomes=[_outcome("Cal Raleigh", 0.95, 2161),
                          _outcome("Aaron Judge", 0.01, 2162)]),
        _market(mid=112810, name="Will the House impeach a federal judge this year?",
                volume=8056.0, tier=5,
                outcomes=[_outcome("Yes", 0.0905, 1128101),
                          _outcome("No", 0.9095, 1128102)]),
        _market(mid=SHOW_COVER_ID, name="MLB The Show 27: Cover Athlete",
                volume=21820.0, tier=5,
                outcomes=[_outcome("Cal Raleigh", 0.40, 240148851),
                          _outcome("Aaron Judge", 0.085, 240148852)]),
    ]


def _futures_ids(body):
    return [s.get("market_id") for s in body["suggestions"] if s.get("type") == "futures"]


@_asyncio
async def test_judge_dropdown_carries_the_aaron_judge_market(monkeypatch):
    async for ac in _client(window=_window(), contenders=[], monkeypatch=monkeypatch):
        body = (await ac.get("/api/events/typeahead?q=judge")).json()
    ids = [str(i) for i in _futures_ids(body)]
    assert str(SHOW_COVER_ID) in ids, ids
    # AL MVP prices him at 1%: the longshot shape the contender rule refuses.
    assert str(AL_MVP_ID) not in ids, ids


@_asyncio
async def test_control_a_partial_word_leaves_the_dropdown_to_the_name_matches(monkeypatch):
    async for ac in _client(window=_window(), contenders=[], monkeypatch=monkeypatch):
        body = (await ac.get("/api/events/typeahead?q=jud")).json()
    ids = [str(i) for i in _futures_ids(body)]
    assert len(ids) == 5, ids
    assert str(SHOW_COVER_ID) not in ids, ids
