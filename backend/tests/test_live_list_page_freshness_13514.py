"""Guard tests for live game list-vs-page freshness parity (#13514 / run 46134571629).

Pins both sides of the asymmetry measured in standing scores run 46134571629:
1. Search (`GET /api/events/search`) hitting Redis (up to 180s / 600s head-warm)
   overlays fresh live-game state from the DB before returning, while non-live
   cache hits perform 0 DB reads.
2. Live detail (`GET /api/events/{id}`) checks `win_probability_sources_rev` and
   `status` on live `_event_detail_cache` hits (up to 30s TTL) via a single PK
   query and coalesces a fresh rebuild when moved, matching `GET /api/events?status=live`.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock

from fastapi import Response
import pytest

from app.models.models import Event, Sport
from app.routes import events as events_route
from app.utils.search_cache import SEARCH_CACHE_HEADER
from scripts.nightly_standing_scores import (
    compare_card_against_detail,
    extract_headline_percent,
    extract_source_percents,
)
from tests.test_search_response_cache import FakeRedis, _request
from tests.test_series_fold_3810 import is_blend_fold, is_series_fold


LIVE_EVENT_ID = 15354942
TWIN_EVENT_ID = 15354999
SETTLED_EVENT_ID = 15350001
SPORT_ID = 77


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def unique(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


def _make_sport() -> Sport:
    return Sport(id=SPORT_ID, key="esports", name="Esports")


def _make_live_event(
    *,
    now: datetime,
    polymarket_prob: float,
    rev: int,
    status: str = "live",
    commence_delta: timedelta = timedelta(minutes=-35),
    home_score: int | None = None,
    away_score: int | None = None,
    kalshi_prob: float | None = None,
) -> Event:
    sources: dict = {
        "polymarket": {"value": polymarket_prob, "updated_at": now.isoformat()},
    }
    if kalshi_prob is not None:
        sources["kalshi"] = {"value": kalshi_prob, "updated_at": now.isoformat()}
    event = Event(
        id=LIVE_EVENT_ID,
        sport_id=SPORT_ID,
        home_team_name="Finishers",
        away_team_name="MeatZn",
        commence_time=now + commence_delta,
        status=status,
        home_score=home_score,
        away_score=away_score,
        win_probability_sources=sources,
        win_probability_sources_rev=rev,
        opening_home_probability=0.45,
        opening_away_probability=0.55,
    )
    event.sport = _make_sport()
    return event


class _ParitySession:
    """Async session answering `get_event`, `list_events`, and search live overlay."""

    def __init__(
        self,
        event: Event,
        *,
        twin_rev: int | None = None,
        twin_kalshi: float | None = None,
    ):
        self.event = event
        self.twin_rev = twin_rev
        self.twin_kalshi = twin_kalshi
        self.pk_rev_checks = 0
        self.full_event_loads = 0
        self.queries: list[str] = []

    async def execute(self, statement, *_a, **_kw):
        sql = " ".join(str(statement).split())
        self.queries.append(sql)

        # `_cached_live_detail_is_stale` narrow PK check:
        if sql.startswith(
            "SELECT events.id, events.win_probability_sources_rev, events.status, events.win_probability_sources FROM events"
        ):
            self.pk_rev_checks += 1
            rows = [
                (
                    self.event.id,
                    self.event.win_probability_sources_rev,
                    self.event.status,
                    self.event.win_probability_sources,
                )
            ]
            if self.twin_rev is not None:
                twin_sources = (
                    {"kalshi": {"value": self.twin_kalshi}}
                    if self.twin_kalshi is not None
                    else {}
                )
                rows.append((TWIN_EVENT_ID, self.twin_rev, "live", twin_sources))
            return _Result(rows)

        # `event_state_read_window`:
        if "transaction_timestamp()" in sql and "clock_timestamp()" in sql:
            now = datetime.now(timezone.utc)
            return _Result([(now, now)])

        # `folded_probability_sources_with_revision` / `folded_series_event_ids`:
        if is_blend_fold(sql):
            rows = [
                (
                    self.event.id,
                    self.event.home_team_name,
                    self.event.away_team_name,
                    self.event.win_probability_sources,
                    self.event.win_probability_sources_rev,
                    False,
                )
            ]
            if self.twin_rev is not None and self.twin_kalshi is not None:
                rows.append(
                    (
                        TWIN_EVENT_ID,
                        self.event.home_team_name,
                        self.event.away_team_name,
                        {
                            "kalshi": {
                                "value": self.twin_kalshi,
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }
                        },
                        self.twin_rev,
                        True,
                    )
                )
            return _Result(rows)

        if is_series_fold(sql):
            rows = [
                (
                    self.event.id,
                    self.event.home_team_name,
                    self.event.away_team_name,
                )
            ]
            if self.twin_rev is not None:
                rows.append(
                    (
                        TWIN_EVENT_ID,
                        self.event.home_team_name,
                        self.event.away_team_name,
                    )
                )
            return _Result(rows)

        # Standard ORM Event load (`get_event`, `list_events`, `_refresh_live_search_results`):
        if "FROM events" in sql:
            # Exclude twin-lookup / drainage side queries that select filtered candidates
            if "provenance:duplicate-of" in sql or "events.event_tags" in sql and "events.id !=" in sql:
                return _Result([])
            self.full_event_loads += 1
            if self.event.status == "live" or "events.id = " in sql or "events.id IN" in sql:
                return _Result([self.event])
            return _Result([])

        return _Result([])

    async def begin_nested(self):
        class _Savepoint:
            async def rollback(self):
                pass

            async def commit(self):
                pass

        return _Savepoint()


@pytest.fixture
def clean_env(monkeypatch):
    rc = FakeRedis()
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: rc)
    events_route._event_detail_cache.clear()
    events_route._event_detail_live_signatures.clear()
    events_route._DETAIL_FRESH_BUILDS.clear()

    async def _no_percentiles(_db):
        return {}

    async def _no_teams(_db, _names):
        return {}

    async def _no_collection(db, payload, **_kw):
        return payload

    async def _empty_list(*_a, **_kw):
        return []

    async def _empty_dict(*_a, **_kw):
        return {}

    monkeypatch.setattr(events_route, "_load_gei_percentiles", _no_percentiles)
    monkeypatch.setattr(events_route, "_build_team_lookup", _no_teams)
    monkeypatch.setattr(events_route, "attach_search_collections", _no_collection)
    monkeypatch.setattr(events_route, "resolve_market_born_duplicate", AsyncMock(return_value=None))
    monkeypatch.setattr(events_route, "market_born_duplicates_on_page", AsyncMock(return_value={}))
    monkeypatch.setattr(events_route, "same_instant_refuted_on_page", AsyncMock(return_value={}))
    monkeypatch.setattr(events_route, "attach_venue_settlement", AsyncMock(return_value=None))
    monkeypatch.setattr(events_route, "read_pregame_projections", AsyncMock(return_value={}))
    monkeypatch.setattr(events_route, "folded_card_numbers_batch", _empty_dict)
    monkeypatch.setattr("app.utils.price_evidence.load_price_evidence", AsyncMock(return_value=None))
    yield rc
    events_route._event_detail_cache.clear()
    events_route._event_detail_live_signatures.clear()
    events_route._DETAIL_FRESH_BUILDS.clear()


async def _call_search(q: str, db, response: Response | None = None):
    return await events_route.search_events(
        request=_request(),
        response=response if response is not None else Response(),
        q=q,
        sport=None,
        tags=None,
        page=1,
        per_page=25,
        days_back=30,
        include_upcoming=True,
        debug_timing=False,
        db=db,
        current_user=None,
    )


async def _call_live_list(db):
    return await events_route.list_events(
        sport=None,
        status="live",
        days=7,
        past_days=1,
        limit=200,
        offset=0,
        db=db,
        league_page=False,
    )


def _seed_search_cache(rc: FakeRedis, q: str, results: list[dict], ttl: int = 180) -> str:
    from app.utils.search_cache import search_response_cache_key

    key = search_response_cache_key(
        q=q, sport=None, tags=None, page=1, per_page=25, days_back=30, include_upcoming=True
    )
    payload = {
        "query": q,
        "teams": [],
        "event_concepts": [],
        "results": results,
        "futures": [],
        "futures_families": [],
        "pagination": {
            "page": 1,
            "per_page": 25,
            "total_results": len(results),
            "total_pages": 1,
            "has_next": False,
            "has_prev": False,
        },
        "sports": [],
        "filters": {"sport": None, "days_back": 30, "include_upcoming": True},
    }
    rc.strings[key] = json.dumps(payload)
    rc.ttls[key] = ttl
    return key


class TestSearchCacheHitRefreshesLiveGames:
    @pytest.mark.asyncio
    async def test_live_card_in_search_hit_refreshes_to_match_detail_without_mutating_cache(
        self, clean_env
    ):
        rc = clean_env
        now = datetime.now(timezone.utc)
        stale_live_card = {
            "id": LIVE_EVENT_ID,
            "sport": "esports",
            "home_team": "Finishers",
            "away_team": "MeatZn",
            "status": "live",
            "commence_time": (now - timedelta(minutes=35)).isoformat(),
            "hero_probability": 0.46,
            "hero_probability_away": 0.54,
            "home_team_data": {"primary_color": "#112233", "logo_url_small": "https://cdn/f.png"},
            "away_team_data": {"primary_color": "#445566", "logo_url_small": "https://cdn/m.png"},
        }
        settled_card = {
            "id": SETTLED_EVENT_ID,
            "sport": "esports",
            "home_team": "Alpha",
            "away_team": "Beta",
            "status": "completed",
            "commence_time": (now - timedelta(hours=3)).isoformat(),
            "hero_probability": 1.0,
        }
        cache_key = _seed_search_cache(rc, "finishers", [stale_live_card, settled_card])
        raw_before = rc.strings[cache_key]

        fresh_event = _make_live_event(now=now, polymarket_prob=0.57, rev=5)
        session = _ParitySession(fresh_event)
        resp = Response()

        search_out = await _call_search("finishers", session, response=resp)
        detail_out = await events_route.get_event(LIVE_EVENT_ID, db=_ParitySession(fresh_event))

        assert resp.headers.get(SEARCH_CACHE_HEADER) == "hit"
        live_out = next(r for r in search_out["results"] if r["id"] == LIVE_EVENT_ID)
        untouched_settled = next(r for r in search_out["results"] if r["id"] == SETTLED_EVENT_ID)

        assert extract_headline_percent(live_out) == 57
        assert extract_source_percents(live_out)["polymarket"] == 57
        assert compare_card_against_detail(
            surface="GET /api/events/search", card=live_out, detail=detail_out
        ) == []
        # Cached logo/color metadata survives without extra Team lookups.
        assert live_out["home_team_data"] == stale_live_card["home_team_data"]
        assert live_out["away_team_data"] == stale_live_card["away_team_data"]
        # Settled rows stay untouched and Redis bytes are never mutated in place.
        assert untouched_settled == settled_card
        assert rc.strings[cache_key] == raw_before

    @pytest.mark.asyncio
    async def test_non_live_search_cache_hit_costs_zero_db_reads(self, clean_env):
        rc = clean_env
        now = datetime.now(timezone.utc)
        _seed_search_cache(
            rc,
            "future",
            [
                {
                    "id": 2001,
                    "status": "scheduled",
                    "commence_time": (now + timedelta(hours=4)).isoformat(),
                    "hero_probability": 0.62,
                },
                {
                    "id": 2002,
                    "status": "completed",
                    "commence_time": (now - timedelta(hours=5)).isoformat(),
                    "hero_probability": 1.0,
                },
            ],
        )
        resp = Response()
        # `db=None` proves 0 queries are executed when no cached card is live or past kickoff.
        out = await _call_search("future", db=None, response=resp)
        assert resp.headers.get(SEARCH_CACHE_HEADER) == "hit"
        assert [r["id"] for r in out["results"]] == [2001, 2002]

    @pytest.mark.asyncio
    async def test_past_kickoff_scheduled_card_in_search_hit_refreshes_when_live(self, clean_env):
        rc = clean_env
        now = datetime.now(timezone.utc)
        _seed_search_cache(
            rc,
            "finishers",
            [
                {
                    "id": LIVE_EVENT_ID,
                    "status": "scheduled",
                    "commence_time": (now - timedelta(minutes=2)).isoformat(),
                    "hero_probability": 0.45,
                }
            ],
        )
        session = _ParitySession(_make_live_event(now=now, polymarket_prob=0.63, rev=2))
        out = await _call_search("finishers", db=session)
        refreshed = out["results"][0]
        assert refreshed["status"] == "live"
        assert extract_headline_percent(refreshed) == 63


class TestLiveDetailCacheRevisionInvalidation:
    @pytest.mark.asyncio
    async def test_cached_live_detail_reuses_cache_when_rev_matches_and_rebuilds_when_moved(
        self, clean_env
    ):
        now = datetime.now(timezone.utc)
        ev_v4 = _make_live_event(now=now, polymarket_prob=0.48, rev=4)
        first_session = _ParitySession(ev_v4)
        first = await events_route.get_event(LIVE_EVENT_ID, db=first_session)
        assert extract_headline_percent(first) == 48
        assert first["blend_fold_revision"] == {str(LIVE_EVENT_ID): 4}

        # Same revision inside 30s TTL -> 1 PK check, 0 full rebuilds.
        hit_session = _ParitySession(ev_v4)
        second = await events_route.get_event(LIVE_EVENT_ID, db=hit_session)
        assert hit_session.pk_rev_checks == 1
        assert hit_session.full_event_loads == 0
        assert extract_headline_percent(second) == 48

        # Price tick bumps `win_probability_sources_rev` (4 -> 5) BEFORE 30s TTL expires.
        ev_v5 = _make_live_event(now=now, polymarket_prob=0.57, rev=5)
        moved_session = _ParitySession(ev_v5)
        third = await events_route.get_event(LIVE_EVENT_ID, db=moved_session)
        live_list = await _call_live_list(_ParitySession(ev_v5))
        list_card = live_list["events"][0]

        assert moved_session.pk_rev_checks == 1
        assert moved_session.full_event_loads >= 1
        assert third["blend_fold_revision"] == {str(LIVE_EVENT_ID): 5}
        assert extract_headline_percent(third) == 57
        assert extract_source_percents(third)["polymarket"] == 57
        assert compare_card_against_detail(
            surface="GET /api/events?status=live", card=list_card, detail=third
        ) == []

        # Cache now holds rev=5, so the following hit serves 57 without rebuilding.
        post_session = _ParitySession(ev_v5)
        fourth = await events_route.get_event(LIVE_EVENT_ID, db=post_session)
        assert post_session.pk_rev_checks == 1
        assert post_session.full_event_loads == 0
        assert extract_headline_percent(fourth) == 57

    @pytest.mark.asyncio
    async def test_folded_twin_rev_bump_invalidates_cached_live_detail(self, clean_env):
        now = datetime.now(timezone.utc)
        ev_v4 = _make_live_event(now=now, polymarket_prob=0.60, rev=4)
        seed_session = _ParitySession(ev_v4, twin_rev=9, twin_kalshi=0.40)
        first = await events_route.get_event(LIVE_EVENT_ID, db=seed_session)
        assert first["blend_fold_revision"] == {
            str(LIVE_EVENT_ID): 4,
            str(TWIN_EVENT_ID): 9,
        }
        assert extract_headline_percent(first) == 50

        # Canonical rev stays 4, but absorbed twin rev bumps 9 -> 10 (kalshi moves 0.40 -> 0.20).
        twin_moved = _ParitySession(ev_v4, twin_rev=10, twin_kalshi=0.20)
        rebuilt = await events_route.get_event(LIVE_EVENT_ID, db=twin_moved)
        assert twin_moved.pk_rev_checks == 1
        assert twin_moved.full_event_loads >= 1
        assert rebuilt["blend_fold_revision"][str(TWIN_EVENT_ID)] == 10
        assert extract_headline_percent(rebuilt) == 40

    @pytest.mark.asyncio
    async def test_live_to_completed_transition_invalidates_cached_live_detail(self, clean_env):
        now = datetime.now(timezone.utc)
        ev_live = _make_live_event(now=now, polymarket_prob=0.70, rev=4, status="live")
        await events_route.get_event(LIVE_EVENT_ID, db=_ParitySession(ev_live))

        ev_final = _make_live_event(
            now=now, polymarket_prob=0.70, rev=4, status="completed", home_score=2, away_score=0
        )
        transition_session = _ParitySession(ev_final)
        rebuilt = await events_route.get_event(LIVE_EVENT_ID, db=transition_session)
        assert transition_session.pk_rev_checks == 1
        assert transition_session.full_event_loads >= 1
        assert rebuilt["status"] == "completed"

    @pytest.mark.asyncio
    async def test_same_price_rev_bump_keeps_cache_while_price_move_rebuilds(self, clean_env):
        now = datetime.now(timezone.utc)
        ev_v4 = _make_live_event(now=now, polymarket_prob=0.48, rev=4)
        await events_route.get_event(LIVE_EVENT_ID, db=_ParitySession(ev_v4))

        # Timestamp-only same-price heartbeat (#12581) bumps rev 4 -> 5 with identical 0.48 price:
        # cache stays warm (`full_event_loads == 0`), avoiding an unnecessary detail rebuild.
        ev_v5_same_price = _make_live_event(
            now=now + timedelta(seconds=10), polymarket_prob=0.48, rev=5
        )
        same_price_session = _ParitySession(ev_v5_same_price)
        same_out = await events_route.get_event(LIVE_EVENT_ID, db=same_price_session)
        assert same_price_session.pk_rev_checks == 1
        assert same_price_session.full_event_loads == 0
        assert extract_headline_percent(same_out) == 48

        # Actual price movement (0.48 -> 0.57, rev 6) invalidates cache and matches live list.
        ev_v6_moved = _make_live_event(
            now=now + timedelta(seconds=15), polymarket_prob=0.57, rev=6
        )
        moved_session = _ParitySession(ev_v6_moved)
        moved_out = await events_route.get_event(LIVE_EVENT_ID, db=moved_session)
        assert moved_session.pk_rev_checks == 1
        assert moved_session.full_event_loads >= 1
        assert extract_headline_percent(moved_out) == 57

    @pytest.mark.asyncio
    async def test_non_live_detail_cache_hit_skips_pk_revision_query(self, clean_env):
        now = datetime.now(timezone.utc)
        ev_done = _make_live_event(
            now=now, polymarket_prob=0.80, rev=4, status="completed", home_score=3, away_score=1
        )
        await events_route.get_event(LIVE_EVENT_ID, db=_ParitySession(ev_done))

        hit_session = _ParitySession(copy.copy(ev_done))
        served = await events_route.get_event(LIVE_EVENT_ID, db=hit_session)
        assert hit_session.pk_rev_checks == 0
        assert hit_session.full_event_loads == 0
        assert served["status"] == "completed"
