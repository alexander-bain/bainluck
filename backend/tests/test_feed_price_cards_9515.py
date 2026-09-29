"""Fresh in-place Discover leaves: price truth without feed cache/ranking."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Response

from app.routes import feed, feed_prices as route
from app.utils.futures_market_snapshot import from_plain, to_plain
from app.utils.personalization import PersonalizationContext
from app.utils.proven_duplicates import FoldedBlendView
from tests.test_feed_phantom_midpoint_suppression import _Market, _Outcome, _nvidia, _spacex
from tests.test_feed_score_events_resilience import _make_event

NOW = datetime(2026, 8, 7, 12, tzinfo=timezone.utc)


def result(rows):
    value = MagicMock()
    value.scalars.return_value.all.return_value = rows
    value.scalars.return_value.unique.return_value.all.return_value = rows
    value.all.return_value = []
    return value


def market(mid=1):
    value = _Market(mid, "Who will win the 2026 award?", "entertainment", [
        _Outcome(mid * 10 + 1, "Alice", .6, bid=.59, ask=.61),
        _Outcome(mid * 10 + 2, "Bob", .4, bid=.39, ask=.41),
    ])
    for outcome in value.outcomes:
        outcome.last_updated = NOW
        outcome.is_winner = None
    return value


def event(eid=1):
    value = _make_event(eid)
    value.commence_time = NOW - timedelta(hours=1)
    value.completed_at = None
    value.espn_win_prob_home = None
    value.win_probability_sources = {"kalshi": {"value": .61, "updated_at": NOW.isoformat()}}
    return value


@pytest.mark.parametrize("raw", ["0", "-1", "1,x", "1,", "١", "2147483648", ",".join(["1"] * 51)])
def test_bad_identity_refused(raw):
    with pytest.raises(HTTPException) as error:
        route._ids(raw)
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_combined_bound_and_empty_refused_before_database():
    db = AsyncMock()
    for events, markets in [("", ""), (",".join(map(str, range(1, 51))), "1")]:
        with pytest.raises(HTTPException):
            await route.get_price_cards(Response(), events, markets, db)
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_endpoint_has_exact_order_dispositions_and_no_cache(monkeypatch):
    monkeypatch.setattr(route, "_event_cards", AsyncMock(return_value=([
        {"type": "event", "data": {"id": 2}, "_rank_score": 20},
        {"type": "event", "data": {"id": 1}},
    ], {"event-1": "updated", "event-2": "withheld"})))
    monkeypatch.setattr(route, "_market_cards", AsyncMock(return_value=([], {"futures-8": "unresolved"})))
    response = Response()
    body = await route.get_price_cards(response, "1,2,1", "8", AsyncMock())
    assert [item["data"]["id"] for item in body["items"]] == [1, 2]
    assert "_rank_score" not in body["items"][1]
    assert body["dispositions"]["futures-8"] == "unresolved"
    assert isinstance(body["built_at"], float)
    assert response.headers["cache-control"] == "no-store"


@pytest.fixture
def projection_dependencies(monkeypatch):
    monkeypatch.setattr(feed, "_query_canonical_source_counts", AsyncMock(return_value=({}, {})))
    monkeypatch.setattr(feed, "_team_names_by_id", AsyncMock(return_value={}))
    monkeypatch.setattr(feed, "withheld_price_outcome_ids_for_markets", AsyncMock(return_value={}))


async def fresh(markets, withheld=None):
    snapshots = from_plain(to_plain(markets, withheld_by_market=withheld or {}))
    db = AsyncMock()
    items = await feed._score_futures(db, NOW, None, PersonalizationContext(),
        preloaded_base={"markets": snapshots}, price_refresh=True)
    db.execute.assert_not_awaited()
    return items


@pytest.mark.asyncio
async def test_fresh_projection_updates_same_ids_without_candidate_or_cached_rows(projection_dependencies, monkeypatch):
    monkeypatch.setattr(feed._pic, "get_or_build", AsyncMock(side_effect=AssertionError("cached quote")))
    old = market()
    first = await fresh([old])
    old.outcomes[0].current_probability = .3
    old.outcomes[1].current_probability = .7
    second = await fresh([old])
    assert first[0]["data"]["top_outcomes"][0]["name"] == "Alice"
    assert second[0]["data"]["top_outcomes"][0]["name"] == "Bob"
    assert second[0]["data"]["top_outcomes"][0]["probability"] == .7


@pytest.mark.asyncio
async def test_requested_sibling_members_do_not_disappear_under_group_caps(projection_dependencies):
    values = [market(1), market(2)]
    for value in values:
        value.group_id = "polymarket:shared"
        value.resolution_date = NOW - timedelta(days=1)
    assert {item["data"]["id"] for item in await fresh(values)} == {1, 2}


@pytest.mark.asyncio
async def test_truth_filters_and_divisor_still_apply(projection_dependencies):
    items = await fresh([_spacex(), _nvidia()], {_nvidia().id: {3002}})
    assert _spacex().id not in {item["data"]["id"] for item in items}
    healthy = next(item for item in items if item["data"]["id"] == _nvidia().id)
    assert healthy["data"]["top_outcomes"][0]["probability"] == .845
    assert 3002 not in {o["id"] for o in healthy["data"]["top_outcomes"]}


@pytest.mark.asyncio
async def test_futures_clock_map_covers_off_top_rows_and_preserves_unknown(projection_dependencies):
    value = market()
    value.outcomes.extend([_Outcome(13, "Carol", .2), _Outcome(14, "Dave", .1)])
    value.outcomes[-1].last_updated = NOW - timedelta(minutes=2)
    value.external_id = "venue-exact"
    db = AsyncMock()
    db.execute.return_value = result([value])
    items, states = await route._market_cards(db, [1, 99], NOW)
    assert states == {"futures-1": "updated", "futures-99": "missing"}
    data = items[0]["data"]
    assert data["external_id"] == "venue-exact"
    assert data["outcome_observed_at"]["14"] == (NOW - timedelta(minutes=2)).isoformat()
    assert data["outcome_observed_at"]["13"] is None
    assert data["top_outcomes"][0]["price_observed_at"] == NOW.isoformat()


@pytest.mark.asyncio
async def test_settled_or_refused_market_is_explicit_unresolved_not_deleted(projection_dependencies):
    settled = market()
    settled.status = "closed"
    db = AsyncMock()
    db.execute.return_value = result([settled])
    items, states = await route._market_cards(db, [1], NOW)
    assert items == []
    assert states == {"futures-1": "unresolved"}
    db.execute.return_value = result([_spacex()])
    items, states = await route._market_cards(db, [_spacex().id], NOW)
    assert items == []
    assert states[f"futures-{_spacex().id}"] == "unresolved"


@pytest.mark.asyncio
async def test_event_fresh_scorer_consumes_folded_hero_without_pool(monkeypatch):
    value = event()
    view = FoldedBlendView(value, {"kalshi": {"value": .73, "updated_at": NOW.isoformat()}})
    db = AsyncMock()
    db.execute.return_value = result([])
    items = await feed._score_events(db, NOW, None, PersonalizationContext(), price_refresh_events=[view])
    db.execute.assert_not_awaited()
    assert len(items) == 1
    data = items[0]["data"]
    assert data["current_odds"]["home_probability"] == data["hero_probability"] == .73
    assert data["current_odds"]["home_rendered_percent"] == 73


@pytest.mark.asyncio
async def test_event_fold_revision_and_complete_clock_travel_with_value(monkeypatch):
    value = event()
    db = AsyncMock()
    db.execute.return_value = result([value])
    monkeypatch.setattr(route, "folded_probability_sources_with_revision", AsyncMock(return_value=(
        {"kalshi": {"value": .73, "updated_at": NOW.isoformat()}}, {"1": 7, "2": 4})))
    monkeypatch.setattr(feed, "enrich_event_team_data", AsyncMock())
    items, states = await route._event_cards(db, [1, 3], NOW)
    assert states == {"event-1": "updated", "event-3": "missing"}
    data = items[0]["data"]
    assert data["blend_fold_revision"] == {"1": 7, "2": 4}
    assert data["hero_probability_observed_at"] == NOW.isoformat()
    assert data["current_odds"]["home_probability"] == .73


@pytest.mark.asyncio
async def test_event_opening_only_is_withheld_not_new_current_quote(monkeypatch):
    value = event()
    db = AsyncMock()
    db.execute.return_value = result([value])
    monkeypatch.setattr(route, "folded_probability_sources_with_revision", AsyncMock(return_value=({}, {"1": 8})))
    monkeypatch.setattr(feed, "enrich_event_team_data", AsyncMock())
    items, states = await route._event_cards(db, [1], NOW)
    assert states == {"event-1": "withheld"}
    assert "current_odds" not in items[0]["data"]
    assert items[0]["data"]["hero_probability_source"] == "opening"
    assert items[0]["data"]["hero_probability_observed_at"] is None


def test_public_route_is_mounted():
    from app.main import app
    assert any(route.path == "/api/feed/price-cards" for route in app.routes)


@pytest.mark.asyncio
async def test_event_soccer_away_is_not_fabricated_and_final_keeps_result(monkeypatch):
    value = event()
    value.sport.key = "soccer_epl"
    view = FoldedBlendView(value, value.win_probability_sources)
    db = AsyncMock()
    db.execute.return_value = result([])
    items = await feed._score_events(db, NOW, None, PersonalizationContext(), price_refresh_events=[view])
    assert items[0]["data"]["current_odds"]["away_probability"] is None
    value.status = "completed"
    value.completed_at = NOW
    value.home_score, value.away_score = 1, 4
    items = await feed._score_events(db, NOW, None, PersonalizationContext(), price_refresh_events=[view])
    assert items[0]["data"]["current_odds"]["home_probability"] == 0
    assert items[0]["data"]["current_odds"]["away_probability"] == 1
    assert items[0]["data"]["home_score"] == 1
    assert items[0]["data"]["away_score"] == 4


@pytest.mark.asyncio
async def test_incomplete_fold_cannot_claim_fresh_coverage(monkeypatch):
    db = AsyncMock()
    db.execute.return_value = result([event()])
    monkeypatch.setattr(route, "folded_probability_sources_with_revision", AsyncMock(return_value=({}, None)))
    items, states = await route._event_cards(db, [1], NOW)
    assert items == []
    assert states == {"event-1": "unresolved"}


@pytest.mark.asyncio
async def test_changed_value_with_unknown_source_clock_keeps_unknown(monkeypatch):
    db = AsyncMock()
    db.execute.return_value = result([event()])
    monkeypatch.setattr(route, "folded_probability_sources_with_revision", AsyncMock(return_value=(
        {"kalshi": {"value": .72}}, {"1": 8})))
    monkeypatch.setattr(feed, "enrich_event_team_data", AsyncMock())
    items, states = await route._event_cards(db, [1], NOW)
    assert states["event-1"] == "updated"
    assert items[0]["data"]["hero_probability_observed_at"] is None


@pytest.mark.asyncio
async def test_fresh_mode_requires_caller_owned_rows():
    with pytest.raises(ValueError):
        await feed._score_futures(AsyncMock(), NOW, None, PersonalizationContext(), price_refresh=True)
