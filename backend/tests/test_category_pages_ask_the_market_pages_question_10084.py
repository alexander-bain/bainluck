"""#10084 — a category card asks the same question its market page asks.

Production, 2026-10-01 15:58Z: nine rows on /politics, /economics and /weather
served Polymarket's group TEMPLATE as `q` — "Will US withdraw from NATO by...?",
"Trump announces Canada tariff increase by...?", "Will the Climate Clock's 1.5°C
deadline change by...?" — while /futures/{id} (and Discover) served the cleaned
title through `clean_market_display_name` (#3513's render-time half).

The fix runs that one rule over the FINISHED response of each builder, so every
assertion here reads the served payload a reader's page renders, and each has a
control: a name with no blank is served byte-identical.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.economics import get_economics
from app.routes.politics import get_politics
from app.routes.weather import get_climate, get_events, get_featured, get_wildcards
from app.utils.market_display_name import clean_served_questions
from tests.integration.test_route_weather import _market, _outcome, _query_result

# The production specimens, verbatim.
NATO = "Will US withdraw from NATO by...?"
MERZ = "Friedrich Merz out as Chancellor of Germany by...?"
CANADA = "Trump announces Canada tariff increase by...?"
CLIMATE_CLOCK = "Will the Climate Clock's 1.5°C deadline change by...?"


def _served_qs(payload):
    qs = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "q" and isinstance(v, str):
                    qs.append(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(payload)
    return qs


def _assert_no_hole(qs):
    assert qs, "the payload served no question at all — the test would be vacuous"
    holed = [q for q in qs if "..." in q or "___" in q]
    assert holed == []


# --- the helper --------------------------------------------------------------


class TestCleanServedQuestions:
    def test_every_q_at_any_depth_is_cleaned(self):
        payload = {
            "themes": {"geo": {"markets": [{"q": NATO, "top_outcomes": [{"name": "December 31"}]}]}},
            "cross_source": [{"q": MERZ}],
        }
        out = clean_served_questions(payload)
        assert out is payload
        assert payload["themes"]["geo"]["markets"][0]["q"] == "Will US withdraw from NATO?"
        assert payload["cross_source"][0]["q"] == "Friedrich Merz out as Chancellor of Germany?"

    def test_only_the_q_key_is_touched(self):
        payload = {"q": NATO, "name": NATO, "label": MERZ, "top_outcomes": [{"name": "December 31"}]}
        clean_served_questions(payload)
        assert payload["name"] == NATO
        assert payload["label"] == MERZ
        assert payload["top_outcomes"] == [{"name": "December 31"}]

    def test_an_unrecognised_name_and_non_strings_are_left_alone(self):
        payload = [
            {"q": "Will 2026 be the hottest year ever?"},
            {"q": "Amazon 2026 capex above ___?"},  # #3513: deliberately left as is
            {"q": None},
            {"q": 7},
        ]
        clean_served_questions(payload)
        assert [r["q"] for r in payload] == [
            "Will 2026 be the hottest year ever?",
            "Amazon 2026 capex above ___?",
            None,
            7,
        ]


# --- /weather ----------------------------------------------------------------


def _wdb(markets):
    db = MagicMock()
    db.execute = AsyncMock(return_value=_query_result(markets))
    return db


def _yes(market_id, name, yes, **kw):
    return _market(
        market_id=market_id,
        name=name,
        outcomes=[_outcome("Yes", yes, outcome_id=market_id * 10)],
        **kw,
    )


@pytest.mark.asyncio
async def test_the_climate_clock_row_asks_its_market_pages_question():
    now = datetime.now(timezone.utc)
    served = await get_climate(_wdb([
        _yes(59254774, CLIMATE_CLOCK, 0.065, resolution_date=now + timedelta(days=92)),
        _yes(70001, "Will 2026 be the hottest year ever?", 0.65,
             resolution_date=now + timedelta(days=92)),
    ]))
    assert {r["market_id"]: r["q"] for r in served} == {
        59254774: "Will the Climate Clock's 1.5°C deadline change?",
        70001: "Will 2026 be the hottest year ever?",  # control: byte-identical
    }


@pytest.mark.asyncio
async def test_weather_event_and_wildcard_rows_are_cleaned_too():
    events = await get_events(_wdb([
        _yes(1, "Category 5 hurricane landfall by...?", 0.2),
        _yes(2, "Will a magnitude 8.0 earthquake hit in 2026?", 0.3),
    ]))
    wild = await get_wildcards(_wdb([
        _yes(3, "Will a supervolcano erupt by...?", 0.03),
    ]))
    qs = _served_qs(events) + _served_qs(wild)
    _assert_no_hole(qs)
    assert "Category 5 hurricane landfall?" in qs
    assert "Will a magnitude 8.0 earthquake hit in 2026?" in qs
    assert "Will a supervolcano erupt?" in qs


@pytest.mark.asyncio
async def test_the_featured_weather_hero_is_cleaned_too():
    now = datetime.now(timezone.utc)
    served = await get_featured(_wdb([
        _yes(4, "Arctic sea ice extent record low by...?", 0.4,
             resolution_date=now + timedelta(days=10)),
    ]))
    qs = _served_qs(served)
    _assert_no_hole(qs)
    assert "Arctic sea ice extent record low?" in qs


# --- /politics ---------------------------------------------------------------


class _Scalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None

    def unique(self):
        return self


class _Result:
    def __init__(self, items):
        self._scalars = _Scalars(items)

    def scalars(self):
        return self._scalars

    def all(self):
        return self._scalars.all()

    def first(self):
        return self._scalars.first()


_PNOW = datetime.now(timezone.utc)


def _pmarket(mid, name, legs):
    outcomes = [
        SimpleNamespace(
            id=mid * 10 + i, name=n, current_probability=p, probability_change_24h=0,
            rank=i + 1, is_winner=False, resolution_source=None,
            last_updated=_PNOW - timedelta(hours=1),
        )
        for i, (n, p) in enumerate(legs)
    ]
    return SimpleNamespace(
        id=mid, name=name, external_id=f"PM-{mid}", source="polymarket", category="news",
        llm_sport_category="politics", group_id=None, outcomes=outcomes,
        market_metadata=None, resolution_date=_PNOW + timedelta(days=91),
        updated_at=_PNOW, volume_24h=1000, image_url=None, hook_description=None,
        status="open",
    )


@pytest.mark.asyncio
async def test_politics_cards_ask_their_market_pages_question():
    db = AsyncMock()
    db.execute.return_value = _Result([
        _pmarket(113250, NATO, [("December 31", 0.032)]),
        _pmarket(113264, MERZ, [("December 31, 2026", 0.08), ("October 31, 2026", 0.021)]),
        _pmarket(113999, "Will Gavin Newsom run for President?", [("Yes", 0.7), ("No", 0.3)]),
    ])
    qs = _served_qs(await get_politics(db))
    _assert_no_hole(qs)
    assert "Will US withdraw from NATO?" in qs
    assert "Friedrich Merz out as Chancellor of Germany?" in qs
    assert "Will Gavin Newsom run for President?" in qs  # control


# --- /economics --------------------------------------------------------------

_ENOW = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)


def _emarket(mid, name, legs, *, source="polymarket"):
    return SimpleNamespace(
        id=mid, name=name, source=source, external_id=f"EX-{mid}",
        outcomes=[
            SimpleNamespace(id=mid * 10 + i, name=n, current_probability=p, rank=i,
                            last_updated=_ENOW - timedelta(hours=2))
            for i, (n, p) in enumerate(legs)
        ],
        status="open", llm_sport_category="economics", group_id=None,
        volume=100_000, volume_24h=5_000,
        resolution_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_economics_cards_ask_their_market_pages_question():
    result_obj = MagicMock()
    result_obj.scalars.return_value.unique.return_value.all.return_value = [
        _emarket(60698697, CANADA, [("October 31", 0.55), ("December 31", 0.7)]),
        _emarket(900001, "Will the US sign a trade deal with India in 2026?",
                 [("Yes", 0.4), ("No", 0.6)], source="kalshi"),
    ]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result_obj)
    with patch("app.routes.economics.datetime") as dt:
        dt.now.return_value = _ENOW
        payload = await get_economics(db)
    qs = _served_qs(payload)
    _assert_no_hole(qs)
    assert "Trump announces Canada tariff increase?" in qs
    assert "Will the US sign a trade deal with India in 2026?" in qs  # control
