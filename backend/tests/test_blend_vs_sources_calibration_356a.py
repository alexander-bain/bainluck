"""Tests for #356a Blend vs Contributing Sources calibration pipeline, route, and PG query."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.tasks import HEAVY_TASKS, celery_app
from app.tasks.precompute_blend_vs_sources import (
    _precompute_blend_vs_sources_calibration,
    collect_blend_vs_sources_observations,
)
from app.utils.blend_vs_sources_calibration import (
    LAST_GOOD_KEY,
    RECORDING_START_ISO,
    REDIS_KEY,
    SCHEMA,
    build_blend_vs_sources_payload,
    extract_forecast_sources,
)

DB_URL = os.environ.get("CALIBRATION_TEST_DATABASE_URL")


class TestBlendVsSourcesScoring:
    def test_excludes_final_result_and_extracts_both_source_shapes(self):
        extracted = extract_forecast_sources(
            {
                "final_result": {"value": 1.0},
                "betting": {"value": 0.64, "updated_at": "2026-11-10T12:00:00Z"},
                "espn": 0.58,
                "kalshi": {"value": 0.61},
            }
        )
        assert extracted == {"betting": 0.64, "espn": 0.58, "kalshi": 0.61}

    def test_pairwise_and_common_sets_compare_exact_same_games_with_raw_buckets(self):
        observations = [
            {
                "event_id": 1,
                "horizon": "start",
                "blend_probability": 0.72,
                "sources": {"betting": 0.75, "kalshi": 0.65, "final_result": 1.0},
                "outcome": 1,
            },
            {
                "event_id": 2,
                "horizon": "start",
                "blend_probability": 0.25,
                "sources": {"betting": 0.20, "kalshi": 0.35},
                "outcome": 0,
            },
            {
                # Betting-only game must NOT enter kalshi matched set or (betting, kalshi) common set.
                "event_id": 3,
                "horizon": "start",
                "blend_probability": 0.85,
                "sources": {"betting": 0.88},
                "outcome": 1,
            },
            {
                "event_id": 1,
                "horizon": "t_minus_1h",
                "blend_probability": 0.62,
                "sources": {"betting": 0.60, "kalshi": 0.65},
                "outcome": 1,
            },
        ]

        payload = build_blend_vs_sources_payload(
            observations,
            generated_at="2026-11-23T12:00:00+00:00",
            events_scanned=3,
        )
        assert payload["schema"] == SCHEMA
        assert payload["status"] == "ready"
        assert payload["smoothing"] == "none"
        assert payload["events_scanned"] == 3

        start = payload["horizons"]["start"]
        assert start["n_events"] == 3

        by_src = {row["source"]: row for row in start["per_source_matched"]}
        assert by_src["betting"]["n_games"] == 3
        assert by_src["kalshi"]["n_games"] == 2
        # Kalshi matched set contains ONLY games 1 and 2 (bin 2 and bin 7 for blend; bins 3 and 6 for kalshi).
        kalshi_blend_bins = by_src["kalshi"]["blend"]["buckets"]
        assert sum(b["n"] for b in kalshi_blend_bins) == 2
        assert [(b["bucket"], b["n"], b["actual"]) for b in kalshi_blend_bins] == [
            ("20-30%", 1, 0.0),
            ("70-80%", 1, 1.0),
        ]

        assert len(start["common_source_sets"]) == 1
        common = start["common_source_sets"][0]
        assert common["sources"] == ["betting", "kalshi"]
        assert common["n_games"] == 2
        assert common["blend"]["n_games"] == 2
        assert common["by_source"]["betting"]["n_games"] == 2
        assert common["by_source"]["kalshi"]["n_games"] == 2


class _FakeRedis:
    def __init__(self, data=None):
        self.store: dict[str, str | bytes] = dict(data or {})
        self.ttl: dict[str, int] = {}

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None):
        self.store[key] = value
        if ex is not None:
            self.ttl[key] = ex
        return True


class TestBlendVsSourcesRoute:
    @pytest.mark.asyncio
    async def test_route_serves_fresh_last_good_and_computing_without_db(self, monkeypatch):
        fake_redis = _FakeRedis()
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: fake_redis)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r_empty = await client.get("/api/calibration/blend-vs-sources")
            assert r_empty.status_code == 200
            assert r_empty.json()["status"] == "computing"
            assert r_empty.json()["schema"] == SCHEMA

            sample = build_blend_vs_sources_payload(
                [],
                generated_at="2026-11-23T12:00:00+00:00",
                events_scanned=12,
            )
            fake_redis.set(LAST_GOOD_KEY, json.dumps(sample))
            r_last = await client.get("/api/calibration/blend-vs-sources")
            assert r_last.status_code == 200
            assert r_last.json()["cache_status"] == "last_good"
            assert r_last.json()["events_scanned"] == 12

            fake_redis.set(REDIS_KEY, json.dumps(sample))
            r_fresh = await client.get("/api/calibration/blend-vs-sources")
            assert r_fresh.status_code == 200
            assert r_fresh.json()["cache_status"] == "fresh"
            assert r_fresh.headers["cache-control"] == "public, max-age=300"


class TestBlendVsSourcesTask:
    def test_heavy_routing_and_beat_registered(self):
        task_name = "app.tasks.precompute_blend_vs_sources_calibration"
        assert task_name in HEAVY_TASKS
        assert task_name in celery_app.tasks
        assert celery_app.conf.task_routes[task_name] == {"queue": "heavy"}
        entry = celery_app.conf.beat_schedule["precompute-blend-vs-sources-calibration"]
        assert entry["task"] == task_name
        assert entry["options"]["queue"] == "heavy"
        assert entry["options"]["expires"] == 86400

    @pytest.mark.asyncio
    async def test_precompute_publishes_to_redis_and_respects_deadline(self, monkeypatch):
        from app.tasks import precompute_blend_vs_sources as pvs

        _FROZEN_NOW = datetime(2026, 11, 20, 0, 0, tzinfo=timezone.utc)

        class _FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return _FROZEN_NOW if tz is None else _FROZEN_NOW.astimezone(tz)

        monkeypatch.setattr(pvs, "datetime", _FrozenDateTime)
        fake_redis = _FakeRedis()
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: fake_redis)

        class _FakeEngine:
            async def dispose(self):
                return None

        monkeypatch.setattr(
            "app.tasks.base._get_task_engine", lambda **kwargs: _FakeEngine()
        )

        async def _fake_collect_complete(*args, **kwargs):
            return {
                "complete": True,
                "events_scanned": 2,
                "events_total": 2,
                "observations": [
                    {
                        "event_id": 10,
                        "horizon": "start",
                        "blend_probability": 0.65,
                        "sources": {"betting": 0.64, "espn": 0.68},
                        "outcome": 1,
                    }
                ],
            }

        monkeypatch.setattr(
            "app.tasks.precompute_blend_vs_sources.collect_blend_vs_sources_observations",
            _fake_collect_complete,
        )
        res = await _precompute_blend_vs_sources_calibration()
        assert res["status"] == "complete"
        assert res["published"] is True
        assert REDIS_KEY in fake_redis.store
        assert LAST_GOOD_KEY in fake_redis.store
        stored = json.loads(fake_redis.store[REDIS_KEY])
        assert stored["smoothing"] == "none"
        assert stored["horizons"]["start"]["n_events"] == 1

        async def _fake_collect_partial(*args, **kwargs):
            return {
                "complete": False,
                "events_scanned": 1,
                "events_total": 2,
                "observations": [],
            }

        monkeypatch.setattr(
            "app.tasks.precompute_blend_vs_sources.collect_blend_vs_sources_observations",
            _fake_collect_partial,
        )
        partial = await _precompute_blend_vs_sources_calibration()
        assert partial["status"] == "partial"
        assert partial["published"] is False
        # Existing last_good stays untouched on deadline truncation.
        assert LAST_GOOD_KEY in fake_redis.store

    @pytest.mark.asyncio
    async def test_collect_sets_read_only_and_statement_timeout(self):
        executed_sql: list[str] = []

        class _FakeResult:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        class _FakeSession:
            def in_transaction(self):
                return True

            async def begin(self):
                return None

            async def execute(self, sql, params=None):
                s = str(sql)
                executed_sql.append(s)
                if "FROM events e" in s:
                    return _FakeResult(
                        [
                            SimpleNamespace(
                                event_id=101,
                                commence_time=datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc),
                                home_score=3,
                                away_score=1,
                                sport_key="soccer_epl",
                            )
                        ]
                    )
                if "CROSS JOIN LATERAL" in s:
                    return _FakeResult(
                        [
                            SimpleNamespace(
                                event_id=101,
                                horizon="start",
                                rev=4,
                                recorded_at=datetime(2026, 11, 10, 19, 55, tzinfo=timezone.utc),
                                sources={"betting": 0.62, "polymarket": 0.59},
                                blend_probability=0.61,
                            )
                        ]
                    )
                return _FakeResult([])

            async def rollback(self):
                return None

        class _FactoryCtx:
            async def __aenter__(self):
                return _FakeSession()

            async def __aexit__(self, *args):
                return None

        collection = await collect_blend_vs_sources_observations(
            lambda: _FactoryCtx(),
            recording_start=datetime.fromisoformat(RECORDING_START_ISO),
            now_utc=datetime(2026, 11, 20, 0, 0, tzinfo=timezone.utc),
            batch_size=50,
            statement_timeout_ms=9000,
        )
        assert collection["complete"] is True
        assert collection["events_scanned"] == 1
        assert len(collection["observations"]) == 1
        assert any("transaction_read_only = on" in s for s in executed_sql)
        assert any("statement_timeout = 9000" in s for s in executed_sql)


@pytest.mark.skipif(
    not DB_URL,
    reason="set CALIBRATION_TEST_DATABASE_URL to run the real-Postgres LATERAL publication test",
)
class TestBlendVsSourcesPostgres:
    @pytest.mark.asyncio
    async def test_lateral_horizon_lookup_selects_latest_rev_at_or_before_cutoff(self):
        from app.models.models import Base

        engine = create_async_engine(DB_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        start_dt = datetime(2026, 11, 12, 20, 0, tzinfo=timezone.utc)
        pre_rec_dt = datetime(2026, 11, 5, 20, 0, tzinfo=timezone.utc)

        try:
            async with Session() as s:
                await s.execute(
                    text(
                        'INSERT INTO sports (id, key, name, "group", active) '
                        "VALUES (1, 'basketball_nba', 'NBA', 'Basketball', true)"
                    )
                )
                await s.execute(
                    text(
                        "INSERT INTO events (id, sport_id, external_id, home_team_name, away_team_name, "
                        "commence_time, status, home_score, away_score) VALUES "
                        "(5001, 1, 'ext-5001', 'Home A', 'Away B', :start_dt, 'completed', 110, 102), "
                        "(5002, 1, 'ext-5002', 'Home C', 'Away D', :pre_dt, 'completed', 98, 105)"
                    ),
                    {"start_dt": start_dt, "pre_dt": pre_rec_dt},
                )
                common_cols = (
                    "(event_id, rev, schema_version, recorded_at, txn_started_at, sources, "
                    "event_status, blend_inputs, source_clocks, blend_probability, blend_tier, "
                    "blend_method, observations, coverage, removed_sources, uncovered_keys, "
                    "unobserved_bumps, queued_frame_matches, payload_sha256) "
                )
                # rev 1 at T-7h (active at T-6h), rev 2 at T-30m (active at Start, NOT at T-1h/T-6h),
                # rev 3 at T+5m (after Start - must NEVER be used for pre-game horizon).
                rows = [
                    (5001, 1, start_dt - timedelta(hours=7), {"betting": 0.55, "espn": 0.60}, 0.57, "h1"),
                    (5001, 2, start_dt - timedelta(minutes=30), {"betting": 0.66, "espn": 0.70}, 0.68, "h2"),
                    (5001, 3, start_dt + timedelta(minutes=5), {"betting": 0.99, "espn": 0.99}, 0.99, "h3"),
                ]
                for eid, rev, rec_at, sources, blend_p, sha in rows:
                    await s.execute(
                        text(
                            f"INSERT INTO probability_publications {common_cols} VALUES "
                            "(:eid, :rev, 1, :rec_at, :rec_at, CAST(:sources AS jsonb), 'scheduled', "
                            "CAST('{}' AS jsonb), CAST('{}' AS jsonb), :bp, 'tiered', 'test', "
                            "CAST('[]' AS jsonb), 'nonvenue_complete', CAST('[]' AS jsonb), "
                            "CAST('[]' AS jsonb), 0, true, :sha)"
                        ),
                        {
                            "eid": eid,
                            "rev": rev,
                            "rec_at": rec_at,
                            "sources": json.dumps(sources),
                            "bp": blend_p,
                            "sha": sha,
                        },
                    )
                await s.commit()

            collection = await collect_blend_vs_sources_observations(
                Session,
                recording_start=datetime.fromisoformat(RECORDING_START_ISO),
                now_utc=datetime(2026, 11, 20, 0, 0, tzinfo=timezone.utc),
                batch_size=10,
            )
            assert collection["complete"] is True
            # Event 5002 precedes RECORDING_START_ISO so only event 5001 is scanned.
            assert collection["events_scanned"] == 1
            by_h = {o["horizon"]: o for o in collection["observations"]}
            assert set(by_h) == {"t_minus_6h", "t_minus_1h", "start"}
            assert by_h["t_minus_6h"]["blend_probability"] == pytest.approx(0.57)
            assert by_h["t_minus_1h"]["blend_probability"] == pytest.approx(0.57)
            assert by_h["start"]["blend_probability"] == pytest.approx(0.68)
            assert by_h["start"]["outcome"] == 1

            payload = build_blend_vs_sources_payload(
                collection["observations"],
                generated_at="2026-11-23T12:00:00+00:00",
                events_scanned=collection["events_scanned"],
            )
            start_matched = {
                r["source"]: r for r in payload["horizons"]["start"]["per_source_matched"]
            }
            assert set(start_matched) == {"betting", "espn"}
            assert start_matched["betting"]["n_games"] == 1
            assert start_matched["espn"]["n_games"] == 1
        finally:
            await engine.dispose()
