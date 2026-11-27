"""Tests for deploy-independent game-markets cache versioning (#13573)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routes import events as events_route
from app.utils import event_concept_cache as concept_cache, game_markets_cache as gmc

FROZEN_NOW = datetime(2026, 5, 18, 2, 0, tzinfo=timezone.utc)
FROZEN_EPOCH = FROZEN_NOW.timestamp()
PINNED_SHA256 = "7162a13d09c36d2704925e08cd5468244c18f87ea2c736a33fee5613761354b7"


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return FROZEN_NOW.replace(tzinfo=None)
        return FROZEN_NOW.astimezone(tz)

    @classmethod
    def utcnow(cls):
        return FROZEN_NOW.replace(tzinfo=None)


class _FakeTime:
    def __init__(self, current: float = FROZEN_EPOCH) -> None:
        self.current = current

    def time(self) -> float:
        return self.current


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str):
        return self._store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> bool:
        self._store[key] = value
        return True

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self._store:
                del self._store[key]
                deleted += 1
        return deleted


def _make_result(scalar=None, rows=None, all_rows=None):
    rows = rows if rows is not None else []
    all_rows_val = all_rows if all_rows is not None else []
    return SimpleNamespace(
        scalar_one_or_none=lambda: scalar,
        scalars=lambda: SimpleNamespace(all=lambda: rows),
        all=lambda: all_rows_val,
    )


def _make_event(*, id: int, status: str) -> SimpleNamespace:
    commence = datetime(2026, 5, 17, 23, 0, tzinfo=timezone.utc)
    completed = (
        datetime(2026, 5, 18, 1, 45, tzinfo=timezone.utc)
        if status == "completed"
        else None
    )
    return SimpleNamespace(
        id=id,
        sport_id=1,
        sport=SimpleNamespace(key="basketball_nba"),
        external_id=f"nba-{id}",
        home_team_id=None,
        away_team_id=None,
        home_team_name="Boston Celtics",
        away_team_name="New York Knicks",
        commence_time=commence,
        status=status,
        home_score=104 if status == "completed" else 88,
        away_score=98 if status == "completed" else 82,
        score_source=None,
        score_observed_at=None,
        opening_home_probability=None,
        opening_away_probability=None,
        opening_home_spread=None,
        opening_over_under=None,
        opening_favorite=None,
        closing_home_probability=None,
        closing_away_probability=None,
        closing_home_spread=None,
        closing_home_spread_odds=None,
        closing_away_spread_odds=None,
        closing_over_under=None,
        closing_over_odds=None,
        closing_under_odds=None,
        raw_ei=None,
        ei_metadata=None,
        ei_computed_at=None,
        llm_gender=None,
        llm_level=None,
        llm_league=None,
        llm_importance=None,
        home_team_normalized=None,
        away_team_normalized=None,
        home_team_alt_names=None,
        away_team_alt_names=None,
        espn_id=None,
        venue_id=None,
        broadcast_info=None,
        game_clock=None if status == "completed" else "6:32",
        period="Final" if status == "completed" else "3rd Quarter",
        espn_win_prob_home=None,
        win_probability_sources=None,
        win_probability_sources_rev=0,
        statpal_fixture_id=None,
        statpal_end_time=None,
        commence_time_source="schedule",
        completed_at=completed,
        box_score_data=None,
        event_tags=None,
        tournament_seed_home=None,
        tournament_seed_away=None,
        tournament_region=None,
        tournament_round=None,
        tournament_type=None,
        is_tournament_game=False,
        created_at=commence,
        fold_into_event_id=None,
    )


def _make_market(
    *,
    id: int,
    name: str,
    external_id: str,
    event_id: int,
    status: str = "open",
) -> SimpleNamespace:
    ts = datetime(2026, 5, 17, 23, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=id,
        name=name,
        description=None,
        external_id=external_id,
        event_id=event_id,
        category="game_prop",
        status=status,
        source="kalshi",
        sport_id=1,
        llm_sport_category="basketball",
        llm_gender=None,
        llm_level=None,
        llm_league=None,
        canonical_market_key=None,
        category_tags=None,
        market_tags=None,
        commence_time=ts,
        resolution_date=None,
        expiration_time=None,
        settled_at=ts if status == "settled" else None,
        group_id=None,
        group_type=None,
        group_position=None,
        market_tier=1,
        market_type=None,
        market_metadata=None,
        mutually_exclusive=True,
        image_url=None,
        image_width=None,
        image_height=None,
        hook_description=None,
        hook_generated_at=None,
        hook_leader_at_generation=None,
        is_editorial_recall=False,
        curation_score_adj=None,
        volume=1000.0,
        volume_24h=500.0,
        max_movement_24h=None,
        open_interest=None,
        liquidity=None,
        volume_updated_at=ts,
        created_at=ts,
        updated_at=ts,
    )


def _make_outcome(
    *,
    id: int,
    market_id: int,
    name: str,
    probability: float,
    opening_probability: float | None = None,
    is_winner: bool | None = None,
    resolution_source: str | None = None,
) -> SimpleNamespace:
    ts = datetime(2026, 5, 17, 23, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=id,
        market_id=market_id,
        name=name,
        team_id=None,
        current_probability=probability,
        current_american_odds=None,
        current_yes_bid=None,
        current_yes_ask=None,
        opening_probability=opening_probability,
        opening_american_odds=None,
        opening_captured_at=None,
        calibration_probability=None,
        probability_change_24h=None,
        rank=None,
        rank_change_24h=None,
        opening_source=None,
        is_winner=is_winner,
        resolution_source=resolution_source,
        external_id=f"out-{id}",
        volume=500.0,
        last_updated=ts,
        price_changed_at=ts,
        volume_24h=250.0,
        volume_24h_at=ts,
    )


def _build_fixture_db(*, event_id: int, status: str) -> AsyncMock:
    event = _make_event(id=event_id, status=status)
    mkt_status = "settled" if status == "completed" else "open"
    spread_market = _make_market(
        id=event_id * 10 + 1,
        name="Celtics at Knicks",
        external_id=f"KXNBA2HSPREAD-26MAY17BOSNYK-{event_id}",
        event_id=event_id,
        status=mkt_status,
    )
    total_market = _make_market(
        id=event_id * 10 + 2,
        name="Celtics at Knicks: Total Points",
        external_id=f"KXNBATOTAL-26MAY17BOSNYK-{event_id}",
        event_id=event_id,
        status=mkt_status,
    )
    outcomes = [
        _make_outcome(
            id=event_id * 100 + 1,
            market_id=spread_market.id,
            name="Celtics -3.5",
            probability=1.0 if status == "completed" else 0.54,
            opening_probability=0.51,
            is_winner=True if status == "completed" else None,
            resolution_source="kalshi" if status == "completed" else None,
        ),
        _make_outcome(
            id=event_id * 100 + 2,
            market_id=total_market.id,
            name="Over 214.5",
            probability=0.0 if status == "completed" else 0.47,
            opening_probability=0.49,
            is_winner=False if status == "completed" else None,
            resolution_source="kalshi" if status == "completed" else None,
        ),
    ]
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar=event),
            _make_result(),  # serve-fold lookup
            _make_result(rows=[]),  # folded_event_ids
            _make_result(rows=[spread_market, total_market]),  # linked markets
            _make_result(all_rows=[]),  # unlinked futures query
            _make_result(rows=[]),  # unlinked markets
            _make_result(rows=outcomes),  # outcomes
            _make_result(all_rows=[]),  # latest_observed_at
        ]
    )
    return db


@pytest.fixture(autouse=True)
def _clear_memo():
    events_route._game_markets_cache.clear()
    yield
    events_route._game_markets_cache.clear()


class TestGameMarketsPayloadFingerprint:
    @pytest.mark.asyncio
    async def test_payload_shape_and_scoring_fingerprint(self, monkeypatch):
        fake_time = _FakeTime(FROZEN_EPOCH)
        fake_redis = _FakeRedis()

        monkeypatch.setattr(events_route, "datetime", _FrozenDateTime, raising=False)
        monkeypatch.setattr(gmc, "datetime", _FrozenDateTime, raising=False)
        monkeypatch.setattr(concept_cache, "datetime", _FrozenDateTime, raising=False)
        monkeypatch.setattr("time.time", fake_time.time)
        monkeypatch.setattr(gmc, "get_client", lambda: fake_redis)

        live_payload = await events_route.get_game_markets(
            42, _build_fixture_db(event_id=42, status="live")
        )
        completed_payload = await events_route.get_game_markets(
            43, _build_fixture_db(event_id=43, status="completed")
        )

        for payload in (live_payload, completed_payload):
            assert payload[gmc.ENVELOPE_FIELD][gmc.BUILD_FIELD] == "gm-v1"
            assert payload[gmc.ENVELOPE_FIELD][gmc.BUILD_FIELD] == gmc.current_cache_version()

        canonical = json.dumps(
            {"live": live_payload, "completed": completed_payload},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        assert "MagicMock" not in canonical
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert digest == PINNED_SHA256, (
            f"Game-markets payload shape or scoring changed ({digest}); "
            "bump the version (GAME_MARKETS_CACHE_VERSION) and update PINNED_SHA256."
        )


class TestCacheVersionBehavior:
    @pytest.mark.asyncio
    async def test_deploy_sha_change_keeps_l1_and_l2_warm(self, monkeypatch):
        fake_redis = _FakeRedis()
        builds = 0

        async def _counting_build(event_id: int, db):
            nonlocal builds
            builds += 1
            return (
                {
                    "event_id": event_id,
                    "status": "completed",
                    "totals": [{"market_name": "O/U 214.5", "probability": 0.5}],
                    "spreads": [],
                    "moneylines": [],
                    "alternate_lines": [],
                    "team_totals": [],
                    "period_markets": [],
                    "player_props": [],
                    "yes_no_props": [],
                    "game_props": [],
                    "other_props": [],
                    "summary": {"total_markets": 1},
                },
                "completed",
                [],
            )

        monkeypatch.setattr(gmc, "get_client", lambda: fake_redis)
        monkeypatch.setattr(events_route, "_build_game_markets", _counting_build)
        monkeypatch.setenv("HEROKU_RELEASE_VERSION", "v6636")

        first = await events_route.get_game_markets(7, AsyncMock())
        assert builds == 1
        assert first[gmc.ENVELOPE_FIELD][gmc.BUILD_FIELD] == gmc.current_cache_version()

        # Deploy SHA changes while GAME_MARKETS_CACHE_VERSION stays at 1.
        monkeypatch.setenv("HEROKU_RELEASE_VERSION", "v6637")

        # L1 still hits without hitting Redis or DB.
        second = await events_route.get_game_markets(7, AsyncMock())
        assert builds == 1
        assert second == first

        # Simulate fresh dyno L1 cold start: L2 primary still serves without rebuild.
        events_route._game_markets_cache.clear()
        third = await events_route.get_game_markets(7, AsyncMock())
        assert builds == 1
        assert third["event_id"] == 7
        assert third[gmc.ENVELOPE_FIELD]["availability"] == gmc.AVAILABILITY_LIVE

        # Drop primary to force mirror path: L2 mirror still serves under new deploy SHA.
        events_route._game_markets_cache.clear()
        fake_redis.delete(gmc.keys_for(7).primary)
        served_mirror, state = gmc.read(7, rc=fake_redis)
        assert state == "stale_ok"
        assert served_mirror is not None
        assert served_mirror["event_id"] == 7

    def test_legacy_deploy_sha_payload_refused_once_on_primary_and_mirror(self):
        fake_redis = _FakeRedis()
        keys = gmc.keys_for(7)
        now = datetime.now(timezone.utc)
        legacy = {
            "event_id": 7,
            concept_cache.ENVELOPE_FIELD: {
                "generation": concept_cache.GENERATION,
                "created_at": (now - timedelta(seconds=10)).isoformat(),
                "fresh_until": (now + timedelta(seconds=3600)).isoformat(),
                "availability": None,
                "quality": concept_cache.QUALITY_FULL,
                "quality_reasons": [],
                "lifecycle_watermark": None,
                "source_status": "completed",
                "build_id": "v6636",
            },
        }
        raw = json.dumps(legacy)
        fake_redis.setex(keys.primary, 3600, raw)
        fake_redis.setex(keys.stale, 86400, raw)

        assert gmc.read(7, rc=fake_redis) == (None, "stale_build")
        fake_redis.delete(keys.primary)
        assert gmc.read(7, rc=fake_redis) == (None, "stale_build")

    def test_version_bump_invalidates_l1_and_l2_primary_and_mirror(self, monkeypatch):
        fake_redis = _FakeRedis()
        stamped = gmc.stamp({"event_id": 7}, source_status="completed")
        gmc.write(7, stamped, rc=fake_redis)
        events_route._write_game_markets_memo(7, "completed", stamped)
        assert events_route._read_game_markets_memo(7) is stamped
        assert gmc.read(7, rc=fake_redis)[1] == "live"

        monkeypatch.setattr(gmc, "GAME_MARKETS_CACHE_VERSION", gmc.GAME_MARKETS_CACHE_VERSION + 1)
        assert events_route._read_game_markets_memo(7) is None
        assert gmc.read(7, rc=fake_redis) == (None, "stale_build")
        fake_redis.delete(gmc.keys_for(7).primary)
        assert gmc.read(7, rc=fake_redis) == (None, "stale_build")

    def test_ttls_and_ceilings_unchanged(self):
        assert gmc.FRESH_TTL_LIVE == 30
        assert gmc.FRESH_TTL_FINAL == 3600
        assert gmc.STALE_SERVE_CEILING == 5
        assert events_route._GAME_MARKETS_LIVE_TTL == 30
        assert gmc.fresh_ttl("completed") == 3600
        assert gmc.fresh_ttl("live") == 30
