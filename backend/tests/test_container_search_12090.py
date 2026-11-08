"""DISCOVER: published containers remain findable after leaving Browse."""

import asyncio
import copy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import container_discovery as discovery
from app.utils import roundup_containers as roundups
from app.utils import search_collections as search
from app.utils.container_presentation import nfl_week_title


def summary(slug="nfl-2026-week-10"):
    return {
        "type": "collection",
        "id": 10,
        "slug": slug,
        "name": "NFL 2026 · Week 10 · Nov 12–16",
        "state": "published",
        "revision": 3,
        "game_count": 14,
        "question_count": 96,
        "destination": {
            "kind": "container",
            "slug": slug,
            "web": f"/collections/{slug}",
        },
    }


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")


@pytest.mark.parametrize(
    "times,suffix",
    [
        (["2026-11-13T01:15:00+00:00", "2026-11-17T01:15:00+00:00"], "Nov 12–16"),
        (["2026-10-30T01:15:00+00:00", "2026-11-03T01:15:00+00:00"], "Oct 29–Nov 2"),
        (["2027-01-02T01:15:00+00:00"], "Jan 1, 2027"),
        (
            ["2026-12-31T01:15:00+00:00", "2027-01-02T01:15:00+00:00"],
            "Dec 30, 2026–Jan 1, 2027",
        ),
    ],
)
def test_week_dates_come_from_kickoffs_in_the_nfl_calendar(times, suffix):
    title = nfl_week_title("NFL 2026 · Week 10", "nfl-2026-week-10", times)
    assert title == "NFL 2026 · Week 10 · " + suffix
    assert nfl_week_title(title, "nfl-2026-week-10", times) == title


@pytest.mark.parametrize(
    "times",
    [[], [None], ["bad"], [datetime(2026, 11, 12)], ["2026-11-12T17:00:00Z", None]],
)
def test_incomplete_or_undated_schedules_do_not_invent_dates(times):
    assert (
        nfl_week_title("NFL 2026 · Week 10", "nfl-2026-week-10", times)
        == "NFL 2026 · Week 10"
    )


def test_other_collection_titles_keep_their_producers_name():
    assert (
        nfl_week_title("AI", "ai", [datetime(2026, 11, 7, tzinfo=timezone.utc)]) == "AI"
    )


async def test_a_title_query_finds_a_collection_without_returned_games(
    enabled, monkeypatch
):
    read = AsyncMock(return_value=discovery.DiscoveryRead(collections=[summary()]))
    monkeypatch.setattr(discovery, "discover_collections", read)
    monkeypatch.setattr(roundups, "ROUNDUP_PRODUCERS", {})
    body = {"query": "Week 10", "results": [], "futures": []}
    before = copy.deepcopy(body)
    result = await search.attach_search_collections(SimpleNamespace(), body)
    assert result["collections"] == [summary()]
    assert body == before
    assert read.await_args.kwargs["query"] == "Week 10"


async def test_timeout_keeps_the_stored_match_and_declares_the_unfinished_read(
    enabled, monkeypatch
):
    monkeypatch.setattr(
        discovery,
        "discover_collections",
        AsyncMock(return_value=discovery.DiscoveryRead(collections=[summary()])),
    )

    async def unfinished(*_args, **_kwargs):
        await asyncio.sleep(5)

    monkeypatch.setattr(search, "_append_roundup_matches", unfinished)
    db = SimpleNamespace(rollback=AsyncMock())
    result = await search.attach_search_collections(
        db, {"query": "Chiefs"}, budget_seconds=0.02
    )
    assert result["collections"] == [summary()]
    assert result["degraded"] == ["collections"]
    db.rollback.assert_awaited_once()


def cfp_producer():
    def produce(_db):
        return roundups.RoundupMembers(
            [
                {
                    "id": 227,
                    "name": "Make the College Football Playoff",
                    "outcomes": [{"name": "Ohio State", "probability": 0.6}],
                },
            ]
        )

    return roundups.RoundupProducer(
        slug="roundup-cfp-picture",
        name="College Football Playoff picture",
        produce=produce,
    )


@pytest.mark.parametrize("query", ["CFP", "College Football", "Ohio State"])
async def test_computed_sets_match_their_title_slug_and_member_outcomes(
    query, monkeypatch
):
    producer = cfp_producer()
    monkeypatch.setattr(roundups, "ROUNDUP_PRODUCERS", {producer.slug: producer})
    cards = []
    failed = await search._append_roundup_matches(
        [], cards, discovery.collection_query_tokens(query)
    )
    assert not failed
    assert len(cards) == 1
    assert cards[0]["destination"]["web"] == "/collections/roundup-cfp-picture"
    page = await roundups.serve_roundup(producer.slug, [])
    assert cards[0]["revision"] == page["revision"]
    assert cards[0]["question_count"] == page["member_count"]


async def test_one_failed_roundup_does_not_hide_a_healthy_sibling(monkeypatch):
    def broken(_db):
        raise ValueError("source unavailable")

    good = cfp_producer()
    bad = roundups.RoundupProducer(
        slug="roundup-cfp-broken", name="CFP unavailable", produce=broken
    )
    monkeypatch.setattr(roundups, "ROUNDUP_PRODUCERS", {bad.slug: bad, good.slug: good})
    cards = []
    db = SimpleNamespace(rollback=AsyncMock())
    assert await search._append_roundup_matches(db, cards, ("cfp",))
    assert [card["slug"] for card in cards] == [good.slug]
    db.rollback.assert_awaited_once()


async def test_typeahead_keeps_its_cached_input_unchanged_and_uses_working_destinations(
    monkeypatch,
):
    lookup = AsyncMock(return_value={"collections": [summary()]})
    monkeypatch.setattr(search, "attach_search_collections", lookup)
    body = {
        "query": "Week 10",
        "suggestions": [{"type": "futures", "market_id": 1, "text": "Ordinary market"}],
        "_evidence": [{"entity_key": "kalshi:1"}],
    }
    before = copy.deepcopy(body)
    result = await search.attach_typeahead_collections(SimpleNamespace(), body)
    assert (
        result["collections"][0]["destination"]["web"]
        == "/collections/nfl-2026-week-10"
    )
    assert result["suggestions"] == body["suggestions"]
    assert result["_evidence"] == body["_evidence"]
    assert len(result["suggestions"]) == len(result["_evidence"])
    assert body == before
    assert lookup.await_args.kwargs["titles_only"] is True


async def test_midterms_disabled_cannot_become_a_search_destination(
    enabled, monkeypatch
):
    from app.routes import containers

    monkeypatch.setattr(containers, "midterms_enabled", lambda: False)
    monkeypatch.setattr(
        discovery,
        "correction_schema_present",
        AsyncMock(return_value=SimpleNamespace(columns=True)),
    )
    row = (
        1,
        "Midterms 2026",
        "midterms-2026",
        "live",
        None,
        None,
        None,
        "published",
        1,
        0,
        2,
        [],
        None,
        None,
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(fetchall=lambda: [row]))
    )
    read = await discovery.discover_collections(db, query="Midterms")
    assert not read.collections


async def test_typeahead_cache_hit_rechecks_the_live_collection_destinations(
    monkeypatch,
):
    import json
    from app.routes import events
    from app.tasks import redis_state

    body = {"query": "Week 10", "suggestions": []}
    cache = SimpleNamespace(get=lambda _key: json.dumps(body))
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: cache)
    monkeypatch.setattr(events, "_record_trending", lambda _query: None)
    enriched = {
        **body,
        "collections": [summary()],
    }
    attach = AsyncMock(return_value=enriched)
    monkeypatch.setattr(events, "attach_typeahead_collections", attach)
    db = SimpleNamespace()
    result = await events.typeahead_search(
        q="Week 10", debug_evidence=False, debug_timing=False, db=db
    )
    assert result == enriched
    attach.assert_awaited_once_with(db, body)


async def test_computed_collection_counts_unique_member_destinations(monkeypatch):
    producer = cfp_producer()
    page = roundups.compose_roundup_container(producer, producer.produce([]))
    page["sections"][0]["members"] *= 2
    monkeypatch.setattr(roundups, "ROUNDUP_PRODUCERS", {producer.slug: producer})
    monkeypatch.setattr(
        roundups, "evaluate_roundup_producer", AsyncMock(return_value=(None, page))
    )
    cards = []
    assert not await search._append_roundup_matches([], cards, ("cfp",))
    assert cards[0]["question_count"] == 1


async def test_named_computed_sets_do_not_scan_unrelated_stored_members(
    enabled, monkeypatch
):
    producer = cfp_producer()
    monkeypatch.setattr(roundups, "ROUNDUP_PRODUCERS", {producer.slug: producer})
    read = AsyncMock(side_effect=AssertionError("unrelated stored-set read"))
    monkeypatch.setattr(discovery, "discover_collections", read)
    result = await search.attach_search_collections([], {"query": "CFP"})
    assert result["collections"][0]["slug"] == producer.slug
    read.assert_not_awaited()


async def test_full_search_forwards_the_selected_sport(enabled, monkeypatch):
    read = AsyncMock(return_value=discovery.DiscoveryRead())
    monkeypatch.setattr(discovery, "discover_collections", read)
    monkeypatch.setattr(roundups, "ROUNDUP_PRODUCERS", {})
    await search.attach_search_collections(
        SimpleNamespace(),
        {
            "query": "Week 10",
            "filters": {"sport": "basketball_nba"},
        },
    )
    assert read.await_args.kwargs["sport_key"] == "basketball_nba"


@pytest.mark.parametrize("matches", [False, True])
async def test_computed_sets_use_the_member_rows_sport_identity(matches, monkeypatch):
    producer = cfp_producer()
    monkeypatch.setattr(roundups, "ROUNDUP_PRODUCERS", {producer.slug: producer})
    execute = AsyncMock(return_value=SimpleNamespace(scalar=lambda: matches))
    db = SimpleNamespace(execute=execute)
    cards = []
    failed = await search._append_roundup_matches(
        db, cards, ("cfp",), sport_key="americanfootball_ncaaf"
    )
    assert not failed
    assert bool(cards) == matches
    assert execute.await_args.args[1] == {
        "event_ids": [],
        "market_ids": [227],
        "sport_key": "americanfootball_ncaaf",
    }


async def test_failed_sport_read_keeps_its_reason_and_restores_the_session(monkeypatch):
    producer = cfp_producer()
    monkeypatch.setattr(roundups, "ROUNDUP_PRODUCERS", {producer.slug: producer})
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=ValueError("sport read unavailable")),
        rollback=AsyncMock(),
    )
    cards = []
    assert await search._append_roundup_matches(
        db, cards, ("cfp",), sport_key="americanfootball_ncaaf"
    )
    assert not cards
    db.rollback.assert_awaited_once()
