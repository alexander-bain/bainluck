"""Exercise the scorer -> produced card -> offline seating seam (#5105).

Retained display captures begin after scoring. These fixed, synthetic inputs
check the missing upstream composition; they are not a retained-inventory
rescore or evidence of editorial improvement. Only input I/O is substituted.
"""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.routes.feed import _score_golf_tournaments
from app.utils import golf_base, majors_calendar
from app.utils.discover_opening_seating import APPLIED, COMPLIANT, seat_opening


NOW = datetime(2026, 10, 7, 18, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "overrides,marquee,score,headline,seating_status,position",
    [
        pytest.param({}, False, 58, "This week", COMPLIANT, 0, id="future-moving"),
        pytest.param(
            {"start_date": "2026-10-06", "end_date": "2026-10-09"},
            False, 98, "Live", APPLIED, 10, id="ordinary-live",
        ),
        pytest.param(
            {"start_date": "2026-10-04", "end_date": "2026-10-07"},
            False, 98, "Live", APPLIED, 10, id="whole-final-day",
        ),
        pytest.param(
            {"start_date": "2026-10-06", "end_date": "2026-10-09", "is_major": True},
            False, 100, "Live", COMPLIANT, 0, id="major-live",
        ),
        pytest.param(
            {"start_date": "2026-10-06", "end_date": "2026-10-09"},
            True, 98, "Live", COMPLIANT, 0, id="calendar-marquee-live",
        ),
        pytest.param(
            {"start_date": None, "end_date": None, "schedule_status": None},
            False, 43, None, COMPLIANT, 0, id="unknown-moving",
        ),
    ],
)
def test_produced_tournament_seats_without_rewriting(
    monkeypatch, overrides, marquee, score, headline, seating_status, position
):
    source = {
        "key": "composition-golf",
        "name": "Composition tournament",
        "is_tour_event": True,
        "is_major": False,
        "schedule_status": "upcoming",
        "start_date": "2026-10-09",
        "end_date": "2026-10-12",
        "market_sources": ["kalshi", "polymarket"],
        "golfers": [{
            "name": "Leader", "rank": 1, "probability": 0.2,
            "movement_24h": 0.05, "movement_is_dated": False,
        }],
        **overrides,
    }
    original_source = deepcopy(source)

    async def base(_db, _now, stages=None):
        assert _db is None and _now == NOW
        return [source], "fresh"

    # Keep calendar membership deterministic while exercising the actual
    # calendar-to-card is_marquee propagation and pin calculation.
    calendar = [{
        "slug": "composition-golf", "concept_key": source["key"],
        "marquee": True, "start": "2026-10-06", "end": "2026-10-09",
    }] if marquee else []
    monkeypatch.setattr(golf_base, "get_golf_base", base)
    monkeypatch.setattr(majors_calendar, "load_calendar", lambda path=None: calendar)
    provenance = {}
    produced = asyncio.run(
        _score_golf_tournaments(None, NOW, None, provenance_sink=provenance)
    )
    assert len(produced) == 1
    card = produced[0]
    assert card["score"] == score
    assert card["headline"] == headline
    assert card["data"]["is_marquee"] is marquee
    assert card["data"]["is_major"] is source["is_major"]
    assert card["data"]["golfers"] == source["golfers"]
    assert provenance == {"golf": "fresh"}
    assert source == original_source

    fillers = [
        {"type": "futures", "score": 40 - i, "data": {"id": i, "name": str(i)}}
        for i in range(1, 13)
    ]
    # The finished deck is an explicit fixture: this tests the seating seam,
    # not production final assembly or personalized ranking.
    deck = [card, *fillers]
    before = deepcopy(deck)
    outcome = seat_opening(deck, now=NOW)
    assert outcome.status == seating_status
    assert outcome.items[position] is card
    expected = [*fillers[:10], card, *fillers[10:]] if position == 10 else deck
    assert len(outcome.items) == len(expected)
    assert all(actual is original for actual, original in zip(outcome.items, expected))
    assert deck == before  # every score, price, reason and private field survives
    assert outcome.items[position]["score"] == score
