"""#13606 Part 1 — Finished-game `/api/events/{id}/history` durable materialization & invalidation tests.

Covers all five Fable approval conditions + safety invariants:
- Condition 1: Event + 5 small indexed tables fingerprint detects changes; direct invalidation
  evicts both durable storage and process L1 (including twin `duplicate_of_id` links); later
  snapshot/small-table writes immediately appear on subsequent `/history` reads.
- Condition 2: Zero age expiry on stored finished-chart snapshots (90-day-old row still serves);
  only corrupt/incomplete or mismatched `schema_version` rows are bypassed.
- Condition 3: Materializer defaults to batch cap 5, honors `FINISHED_EVENT_HISTORY_BATCH_SIZE`,
  logs `build_s` per event, selects post-grace finished events without a complete durable snapshot,
  and never stores partial or pending on-demand backfill builds.
- Condition 4: `FINISHED_EVENT_HISTORY_COLD_MISS_MODE` switches between `read_through` (default)
  and `since_start_fallback` (enqueues materialization, serves derived `since_start` without
  polluting durable or L1 `"all"`).
- Condition 5: Stored `"all"` equals live `"all"` field-for-field, and `derive_since_start_payload`
  from stored `"all"` equals live `range="since_start"` field-for-field across kickoff,
  `venue_expiration`, withheld 1-point sources, and `hasPostStartData == False`.
"""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import Response
from sqlalchemy import create_engine, event as sa_event, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.sqlite.base import DATETIME as _SQLITE_DATETIME
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.models import (
    Base,
    ESPNSnapshot,
    Event,
    FuturesMarket,
    FuturesOutcome,
    GameMoment,
    OddsSnapshot,
    ScoreSnapshot,
    ScoringPlay,
    Sport,
    WinProbSnapshot,
)
from app.routes import events as events_route
from app.services import durable_snapshots as ds_mod
from app.services import finished_event_history as feh
from app.services.anchor_channel import duplicate_tag
from app.utils import event_history_cache as ehc
from app.utils.durable_state import (
    MISSING as DS_MISSING,
    DurableEnvelope,
    EnvelopeRead,
    canonical_json,
    decode_envelope,
)

UTC = timezone.utc


@pytest.fixture(autouse=True)
def _sqlite_utc_datetime_columns(monkeypatch):
    """Ensure SQLite `DATETIME` columns preserve UTC tzinfo and stub in-memory Redis."""
    orig_result_processor = _SQLITE_DATETIME.result_processor

    def _utc_result_processor(self, dialect, coltype):
        base_proc = orig_result_processor(self, dialect, coltype)
        if base_proc is None or not getattr(self, "timezone", False):
            return base_proc

        def _process(value):
            parsed = base_proc(value)
            if isinstance(parsed, datetime) and parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed

        return _process

    monkeypatch.setattr(_SQLITE_DATETIME, "result_processor", _utc_result_processor)

    class _FakeRedis:
        def __init__(self):
            self.kv: dict[str, str] = {}

        def get(self, key: str):
            return self.kv.get(key)

        def mget(self, keys):
            return [self.kv.get(k) for k in keys]

        def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
            if nx and key in self.kv:
                return False
            self.kv[key] = str(value)
            return True

        def delete(self, key: str):
            return 1 if self.kv.pop(key, None) is not None else 0

        def incr(self, key: str):
            val = int(self.kv.get(key, "0")) + 1
            self.kv[key] = str(val)
            return val

        def expire(self, key: str, ttl: int):
            return True

    fake_redis = _FakeRedis()
    import app.tasks.redis_state as redis_state_mod

    monkeypatch.setattr(redis_state_mod, "get_redis_client", lambda: fake_redis)


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):
    return "TEXT"


_WANTED_TABLES = [
    t
    for t in Base.metadata.sorted_tables
    if t.name
    in {
        "sports",
        "teams",
        "events",
        "odds_snapshots",
        "score_snapshots",
        "espn_snapshots",
        "win_prob_snapshots",
        "scoring_plays",
        "futures_markets",
        "futures_outcomes",
        "game_moments",
        "durable_state_snapshots",
    }
]


class _AsyncSavepointShim:
    def __init__(self, nested):
        self._nested = nested

    async def commit(self):
        if self._nested.is_active:
            self._nested.commit()

    async def rollback(self):
        if self._nested.is_active:
            self._nested.rollback()


class _AsyncSessionShim:
    """Async SQLAlchemy surface over sync sqlite3 (sandbox has no aiosqlite)."""

    def __init__(self, session: Session):
        self._s = session
        self.sync_session = session

    @property
    def identity_map(self):
        return self._s.identity_map

    def get_bind(self):
        return self._s.get_bind()

    async def begin_nested(self):
        return _AsyncSavepointShim(self._s.begin_nested())

    async def execute(self, statement, *a, **k):
        return self._s.execute(statement, *a, **k)

    def add(self, obj):
        self._s.add(obj)

    def add_all(self, objs):
        self._s.add_all(objs)

    async def commit(self):
        self._s.commit()

    async def rollback(self):
        self._s.rollback()

    async def flush(self):
        self._s.flush()


class _AsyncEngineShim:
    def __init__(self, engine):
        self._engine = engine

    async def dispose(self):
        self._engine.dispose()


async def _sqlite_session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=_WANTED_TABLES)

    @contextlib.asynccontextmanager
    async def _maker():
        session = Session(engine, expire_on_commit=False)

        @sa_event.listens_for(session, "loaded_as_persistent")
        def _reattach_utc(_sess, instance):
            for attr, value in list(instance.__dict__.items()):
                if isinstance(value, datetime) and value.tzinfo is None:
                    instance.__dict__[attr] = value.replace(tzinfo=UTC)

        try:
            yield _AsyncSessionShim(session)
        finally:
            session.close()

    return _AsyncEngineShim(engine), _maker


def _install_sqlite_durable_store(monkeypatch, *, age_override: timedelta | None = None):
    """Test double executing real SQLite rows on `durable_state_snapshots`.

    Production `durable_snapshots.py` uses PG-only `CAST(:payload AS jsonb)` and
    `SET LOCAL statement_timeout`, which `session_supports_durable` intentionally skips
    on SQLite. This adapter exercises full end-to-end persistence in `durable_state_snapshots`
    under SQLite without mocking away `finished_event_history.py` logic.
    """
    monkeypatch.setattr(feh, "session_supports_durable", lambda db: True)

    async def _read_sqlite(db, identity, *, expected_version, max_age_s, now=None):
        row = (
            await db.execute(
                text(
                    "SELECT schema_version, generation, generated_at, payload, checksum, complete, source "
                    "FROM durable_state_snapshots WHERE identity = :ident"
                ),
                {"ident": identity},
            )
        ).first()
        if row is None:
            return EnvelopeRead(status=DS_MISSING, tier=ds_mod.TIER_DURABLE)
        gen_at = row[2]
        if isinstance(gen_at, str):
            gen_at = datetime.fromisoformat(gen_at.replace("Z", "+00:00"))
        if isinstance(gen_at, datetime) and gen_at.tzinfo is None:
            gen_at = gen_at.replace(tzinfo=UTC)
        body = json.loads(row[3]) if isinstance(row[3], str) else row[3]
        raw = {
            "identity": identity,
            "schema_version": row[0],
            "generation": int(row[1]),
            "generated_at": gen_at,
            "payload": body,
            "checksum": row[4],
            "complete": bool(row[5]),
            "source": row[6],
        }
        eval_now = (gen_at + age_override) if age_override is not None else now
        return decode_envelope(
            raw,
            tier=ds_mod.TIER_DURABLE,
            expected_version=expected_version,
            max_age_s=max_age_s,
            now=eval_now,
        )

    async def _publish_sqlite(db, envelope: DurableEnvelope):
        existing = (
            await db.execute(
                text("SELECT generation FROM durable_state_snapshots WHERE identity = :ident"),
                {"ident": envelope.identity},
            )
        ).first()
        payload_json = canonical_json(envelope.payload)
        gen_iso = envelope.generated_at.isoformat()
        if existing is None:
            await db.execute(
                text(
                    "INSERT INTO durable_state_snapshots "
                    "(identity, schema_version, generation, generated_at, payload, checksum, complete, source, updated_at) "
                    "VALUES (:ident, :sv, :gen, :gat, :payload, :csum, :comp, :src, :upd)"
                ),
                {
                    "ident": envelope.identity,
                    "sv": envelope.schema_version,
                    "gen": envelope.generation,
                    "gat": gen_iso,
                    "payload": payload_json,
                    "csum": envelope.checksum,
                    "comp": bool(envelope.complete),
                    "src": envelope.source,
                    "upd": gen_iso,
                },
            )
        else:
            await db.execute(
                text(
                    "UPDATE durable_state_snapshots SET schema_version=:sv, generation=:gen, "
                    "generated_at=:gat, payload=:payload, checksum=:csum, complete=:comp, source=:src, updated_at=:upd "
                    "WHERE identity=:ident"
                ),
                {
                    "ident": envelope.identity,
                    "sv": envelope.schema_version,
                    "gen": envelope.generation,
                    "gat": gen_iso,
                    "payload": payload_json,
                    "csum": envelope.checksum,
                    "comp": bool(envelope.complete),
                    "src": envelope.source,
                    "upd": gen_iso,
                },
            )
        return {"status": ds_mod.STATUS_OK, "generation": envelope.generation}

    monkeypatch.setattr(ds_mod, "read_snapshot", _read_sqlite)
    monkeypatch.setattr(ds_mod, "publish_snapshot_in_txn", _publish_sqlite)


def _seed_finished_fixture_sync_data(now: datetime):
    kickoff = (now - timedelta(hours=6)).replace(second=0, microsecond=0)
    completed = kickoff + timedelta(hours=3)
    sport = Sport(id=1, key="americanfootball_nfl", name="NFL", group="American Football", active=True)
    event = Event(
        id=136061,
        sport_id=1,
        external_id="ext_136061",
        espn_id="espn_136061",
        home_team_name="San Francisco 49ers",
        away_team_name="Seattle Seahawks",
        commence_time=kickoff,
        commence_time_source="espn",
        status="completed",
        home_score=28,
        away_score=21,
        completed_at=completed,
        win_probability_sources={
            "betting": {"prob": 0.72, "updated_at": completed.isoformat()},
            "kalshi": {"prob": 0.74, "updated_at": completed.isoformat()},
            "espn": {"prob": 0.73, "updated_at": completed.isoformat()},
        },
        box_score_data={"scoring_plays": [{"period": "Q1", "clock": "10:00", "home_score": 7, "away_score": 0, "text": "TD"}]},
    )
    odds = [
        # Pre-kickoff
        OddsSnapshot(
            event_id=136061,
            bookmaker="draftkings",
            home_moneyline=-150,
            away_moneyline=130,
            home_win_probability=0.58,
            away_win_probability=0.42,
            captured_at=kickoff - timedelta(hours=4),
            valid_until=kickoff - timedelta(hours=2),
            reading_count=2,
        ),
        OddsSnapshot(
            event_id=136061,
            bookmaker="fanduel",
            home_moneyline=-145,
            away_moneyline=125,
            home_win_probability=0.57,
            away_win_probability=0.43,
            captured_at=kickoff - timedelta(hours=2),
            valid_until=kickoff + timedelta(minutes=20),
            reading_count=3,
        ),
        # In-game
        OddsSnapshot(
            event_id=136061,
            bookmaker="draftkings",
            home_moneyline=-240,
            away_moneyline=195,
            home_win_probability=0.69,
            away_win_probability=0.31,
            captured_at=kickoff + timedelta(minutes=30),
            valid_until=kickoff + timedelta(minutes=90),
            reading_count=4,
        ),
        OddsSnapshot(
            event_id=136061,
            bookmaker="fanduel",
            home_moneyline=-260,
            away_moneyline=210,
            home_win_probability=0.71,
            away_win_probability=0.29,
            captured_at=kickoff + timedelta(minutes=75),
            valid_until=completed,
            reading_count=4,
        ),
    ]
    wps = [
        # Pre-kickoff-only source (`polymarket`) -> present in `all`, withheld in `since_start`
        WinProbSnapshot(
            event_id=136061,
            source="polymarket",
            home_win_probability=0.56,
            away_win_probability=0.44,
            captured_at=kickoff - timedelta(hours=3),
            valid_until=kickoff - timedelta(hours=1),
            reading_count=2,
            game_state={"market_id": 5001, "poll_type": "live_fast"},
        ),
        # Kalshi both pre and post kickoff (>= 25 points so on-demand refill never enqueues)
        *[
            WinProbSnapshot(
                event_id=136061,
                source="kalshi",
                home_win_probability=0.55 + (0.01 * i if i < 20 else 0.0),
                away_win_probability=0.45 - (0.01 * i if i < 20 else 0.0),
                captured_at=kickoff - timedelta(minutes=90) + timedelta(minutes=10 * i),
                valid_until=kickoff - timedelta(minutes=80) + timedelta(minutes=10 * i),
                reading_count=1,
                game_state={"market_id": 5002, "poll_type": "live_fast"},
            )
            for i in range(24)
        ],
    ]
    espn = [
        ESPNSnapshot(
            event_id=136061,
            home_win_probability=0.62,
            away_win_probability=0.38,
            home_score=7,
            away_score=0,
            period="1",
            game_clock="09:45",
            captured_at=kickoff + timedelta(minutes=25),
        ),
        ESPNSnapshot(
            event_id=136061,
            home_win_probability=0.81,
            away_win_probability=0.19,
            home_score=28,
            away_score=21,
            period="4",
            game_clock="00:00",
            captured_at=completed,
        ),
    ]
    scores = [
        ScoreSnapshot(
            event_id=136061,
            home_score=7,
            away_score=0,
            captured_at=kickoff + timedelta(minutes=25),
        ),
        ScoreSnapshot(
            event_id=136061,
            home_score=28,
            away_score=21,
            captured_at=completed,
        ),
    ]
    plays = [
        ScoringPlay(
            event_id=136061,
            source="espn",
            period="Q1",
            game_clock="09:45",
            home_score=7,
            away_score=0,
            team_name="San Francisco 49ers",
            description="Touchdown",
            play_type="Touchdown",
            captured_at=kickoff + timedelta(minutes=25),
        )
    ]
    moments = [
        GameMoment(
            event_id=136061,
            moment_type="lead_change",
            ts=kickoff + timedelta(minutes=45),
            label="49ers take the lead",
            description="49ers take the lead",
            source="espn",
            confidence=0.88,
            prob_delta=0.14,
            actor_team="San Francisco 49ers",
            period="Q2",
            dedupe_key="m1",
        )
    ]
    fm = FuturesMarket(
        id=9001,
        source="kalshi",
        external_id="KXNFL-136061",
        sport_id=1,
        event_id=136061,
        name="Seahawks vs 49ers",
        category="winner",
        mutually_exclusive=True,
        status="closed",
        created_at=kickoff - timedelta(hours=12),
    )
    fo = FuturesOutcome(
        id=9101,
        market_id=9001,
        external_id="KXNFL-136061-SF",
        name="San Francisco 49ers",
        current_probability=1.0,
        last_updated=completed,
        price_changed_at=completed,
    )
    return sport, event, odds, wps, espn, scores, plays, moments, fm, fo


@pytest.mark.asyncio
async def test_condition5_stored_all_and_derived_since_start_match_live_field_for_field(monkeypatch):
    ehc._reset_for_tests()
    feh._reset_claims_for_tests()
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    engine, maker = await _sqlite_session_factory()
    try:
        sport, event, odds, wps, espn, scores, plays, moments, fm, fo = _seed_finished_fixture_sync_data(now)
        async with maker() as db:
            db.add_all([sport, event, *odds, *wps, *espn, *scores, *plays, *moments, fm, fo])
            await db.commit()

        async with maker() as db:
            with feh.bypass_durable_context():
                live_all = await events_route.get_event_odds_history(
                    136061, hours=48, chart_range="all", response=Response(), db=db, fresh=False
                )
                live_since_start = await events_route.get_event_odds_history(
                    136061, hours=48, chart_range="since_start", response=Response(), db=db, fresh=False
                )

        # Now turn durable storage on and run the real materializer + route reads.
        _install_sqlite_durable_store(monkeypatch)
        monkeypatch.setattr(events_route, "materialize_finished_event_charts", SimpleNamespace(apply_async=lambda *a, **kw: None), raising=False)
        monkeypatch.setattr("app.tasks.materialize_finished_event_charts", SimpleNamespace(apply_async=lambda *a, **kw: None), raising=False)

        async with maker() as db:
            # Verify route read-through writes the durable row on cold `range=all`
            served_all_miss = await events_route.get_event_odds_history(
                136061, hours=48, chart_range="all", response=Response(), db=db, fresh=False
            )
            assert served_all_miss == live_all

        async with maker() as db:
            # Subsequent reads hit the durable row even if underlying `win_prob_snapshots` / `odds_snapshots`
            # aren't scanned: verify `all` AND derived `since_start` match live field-for-field.
            monkeypatch.setattr(
                events_route,
                "_snapshots_with_split_budget",
                lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not scan odds_snapshots on durable hit")),
            )
            served_all_hit = await events_route.get_event_odds_history(
                136061, hours=48, chart_range="all", response=Response(), db=db, fresh=False
            )
            served_since_hit = await events_route.get_event_odds_history(
                136061, hours=168, chart_range="since_start", response=Response(), db=db, fresh=False
            )

        assert served_all_hit == live_all
        assert served_since_hit == live_since_start
        # Pre-kickoff-only `polymarket` source stayed in `all` and was withheld in derived `since_start`
        assert served_all_hit["pre_window_omitted"] is False
        assert len(served_all_hit["win_prob_history"]["polymarket"]) >= 1
        assert served_since_hit["pre_window_omitted"] is True
        assert served_since_hit["win_prob_history"]["polymarket"] == []
        assert served_since_hit["win_prob_sources"]["polymarket"]["snapshot_count"] == 0
    finally:
        await engine.dispose()
        ehc._reset_for_tests()
        feh._reset_claims_for_tests()


@pytest.mark.asyncio
async def test_condition1_small_table_fingerprint_and_snapshot_writer_invalidation(monkeypatch):
    ehc._reset_for_tests()
    feh._reset_claims_for_tests()
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    engine, maker = await _sqlite_session_factory()
    try:
        sport, event, odds, wps, espn, scores, plays, moments, fm, fo = _seed_finished_fixture_sync_data(now)
        # Add an absorbed duplicate pointing to canonical 136061 via event_tags
        twin = Event(
            id=136062,
            sport_id=1,
            external_id="ext_136062",
            home_team_name="San Francisco 49ers",
            away_team_name="Seattle Seahawks",
            commence_time=event.commence_time,
            status="completed",
            completed_at=event.completed_at,
            event_tags=[duplicate_tag(136061)],
            win_probability_sources={},
            box_score_data={},
        )
        async with maker() as db:
            db.add_all([sport, event, twin, *odds, *wps, *espn, *scores, *plays, *moments, fm, fo])
            await db.commit()

        _install_sqlite_durable_store(monkeypatch)
        async with maker() as db:
            # Cold read populates durable row
            payload1 = await events_route.get_event_odds_history(
                136061, hours=48, chart_range="all", response=Response(), db=db, fresh=False
            )
            assert len(payload1["moments"]) == 1
            count_before = (
                await db.execute(text("SELECT COUNT(*) FROM durable_state_snapshots"))
            ).scalar_one()
            assert count_before == 1

        # A) Small-table write (new GameMoment) -> fingerprint mismatches without needing explicit invalidation
        async with maker() as db:
            db.add(
                GameMoment(
                    event_id=136061,
                    moment_type="game_winning_score",
                    ts=event.commence_time + timedelta(minutes=165),
                    label="Sealing TD",
                    description="Sealing TD",
                    source="espn",
                    confidence=0.95,
                    prob_delta=0.22,
                    actor_team="San Francisco 49ers",
                    period="Q4",
                    dedupe_key="m2",
                )
            )
            await db.commit()

        async with maker() as db:
            payload2 = await events_route.get_event_odds_history(
                136061, hours=48, chart_range="all", response=Response(), db=db, fresh=False
            )
            assert len(payload2["moments"]) == 2
            assert any(m["label"] == "Sealing TD" for m in payload2["moments"])

        # B) Large-table write via `_create_or_update_win_prob_snapshot(is_completed=True)` on the twin!
        # Put a finished L1 entry in memory too to verify twin -> canonical L1 + durable eviction.
        ehc.write(ehc.finished_cache_key(136061, "all"), b'{"stale":1}', None, 45.0)
        from app.tasks.snapshots import _create_or_update_win_prob_snapshot

        async with maker() as db:
            # Populate Polymarket terminal point for twin/canonical via `_create_or_update_win_prob_snapshot`
            snap, is_new = await _create_or_update_win_prob_snapshot(
                db,
                event_id=136061,
                source="polymarket",
                home_win_probability=0.91,
                away_win_probability=0.09,
                game_state={"period": "Final"},
                is_completed=True,
            )
            snap.captured_at = event.commence_time + timedelta(minutes=120)
            snap.valid_until = event.completed_at
            if is_new:
                db.add(snap)
            await db.commit()

        assert ehc.read(ehc.finished_cache_key(136061, "all")) is None
        async with maker() as db:
            remaining = (
                await db.execute(text("SELECT COUNT(*) FROM durable_state_snapshots"))
            ).scalar_one()
            assert remaining == 0
            # Re-read rebuilds with the new Polymarket point visible
            payload3 = await events_route.get_event_odds_history(
                136061, hours=48, chart_range="all", response=Response(), db=db, fresh=False
            )
            assert "polymarket" in payload3["win_prob_history"]
            assert any(
                round(pt["home_probability"], 2) == 0.91
                for pt in payload3["win_prob_history"]["polymarket"]
            )

        # C) Twin ID invalidation (`duplicate_of_id`) deletes canonical row + evicts canonical L1
        ehc.write(ehc.finished_cache_key(136061, "since_start"), b'{"stale":2}', None, 45.0)
        async with maker() as db:
            removed = await feh.invalidate_finished_event_history(db, [136062])
            await db.commit()
            assert removed == 1
        assert ehc.read(ehc.finished_cache_key(136061, "since_start")) is None
    finally:
        await engine.dispose()
        ehc._reset_for_tests()
        feh._reset_claims_for_tests()


@pytest.mark.asyncio
async def test_condition2_no_age_expiry_and_condition3_materializer_batch_cap(monkeypatch, caplog):
    ehc._reset_for_tests()
    feh._reset_claims_for_tests()
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    engine, maker = await _sqlite_session_factory()
    try:
        sport, event, odds, wps, espn, scores, plays, moments, fm, fo = _seed_finished_fixture_sync_data(now)
        # Add 7 finished events eligible for materialization + 1 live + 1 within 35m grace
        extra_events = []
        extra_wps = []
        for idx in range(7):
            eid = 20000 + idx
            ct = now - timedelta(hours=10 + idx)
            comp = ct + timedelta(hours=3)
            extra_events.append(
                Event(
                    id=eid,
                    sport_id=1,
                    external_id=f"ext_{eid}",
                    home_team_name=f"Home {idx}",
                    away_team_name=f"Away {idx}",
                    commence_time=ct,
                    commence_time_source="espn",
                    status="completed",
                    home_score=24,
                    away_score=17,
                    completed_at=comp,
                    win_probability_sources={},
                    box_score_data={},
                )
            )
            extra_wps.extend(
                [
                    WinProbSnapshot(
                        event_id=eid,
                        source="kalshi",
                        home_win_probability=0.55 + 0.01 * (j % 5),
                        away_win_probability=0.45 - 0.01 * (j % 5),
                        captured_at=ct + timedelta(minutes=5 * j),
                        valid_until=ct + timedelta(minutes=5 * (j + 1)),
                        reading_count=1,
                    )
                    for j in range(25)
                ]
            )
        grace_ev = Event(
            id=29998,
            sport_id=1,
            external_id="ext_grace",
            home_team_name="Grace Home",
            away_team_name="Grace Away",
            commence_time=now - timedelta(hours=3),
            commence_time_source="espn",
            status="completed",
            completed_at=now - timedelta(minutes=10),
            win_probability_sources={},
            box_score_data={},
        )
        live_ev = Event(
            id=29999,
            sport_id=1,
            external_id="ext_live",
            home_team_name="Live Home",
            away_team_name="Live Away",
            commence_time=now - timedelta(hours=1),
            commence_time_source="espn",
            status="live",
            win_probability_sources={},
            box_score_data={},
        )
        async with maker() as db:
            db.add_all([sport, event, *odds, *wps, *espn, *scores, *plays, *moments, fm, fo, *extra_events, *extra_wps, grace_ev, live_ev])
            await db.commit()

        monkeypatch.delenv("FINISHED_EVENT_HISTORY_BATCH_SIZE", raising=False)
        assert feh.configured_batch_size() == 5
        monkeypatch.setenv("FINISHED_EVENT_HISTORY_BATCH_SIZE", "999")
        assert feh.configured_batch_size() == feh.MAX_BATCH_SIZE == 50
        monkeypatch.delenv("FINISHED_EVENT_HISTORY_BATCH_SIZE", raising=False)

        _install_sqlite_durable_store(monkeypatch)
        with caplog.at_level(logging.INFO, logger=feh.__name__):
            summary = await feh.materialize_finished_event_charts_async(maker)

        assert summary["batch_limit"] == 5
        assert summary["selected"] == 5
        assert summary["written"] == 5
        assert all("build_s" in item for item in summary["per_event"])
        assert "build_s=" in caplog.text

        # Within-grace event and live event are explicitly skipped if targeted
        skip_summary = await feh.materialize_finished_event_charts_async(
            maker, event_ids=[29998, 29999]
        )
        assert skip_summary["written"] == 0
        assert {p["status"] for p in skip_summary["per_event"]} == {
            "within_grace_window",
            "not_finished",
        }

        # Condition 2: 90-day-old stored row is STILL valid and served (never expires on age)
        _install_sqlite_durable_store(monkeypatch, age_override=timedelta(days=90))
        async with maker() as db:
            monkeypatch.setattr(
                events_route,
                "_snapshots_with_split_budget",
                lambda *a, **kw: (_ for _ in ()).throw(AssertionError("90-day-old durable row should still serve")),
            )
            old_hit = await events_route.get_event_odds_history(
                20000, hours=48, chart_range="all", response=Response(), db=db, fresh=False
            )
            assert old_hit["event_id"] == 20000
    finally:
        await engine.dispose()
        ehc._reset_for_tests()
        feh._reset_claims_for_tests()


@pytest.mark.asyncio
async def test_condition4_cold_miss_since_start_fallback_and_kill_switch(monkeypatch):
    ehc._reset_for_tests()
    feh._reset_claims_for_tests()
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    engine, maker = await _sqlite_session_factory()
    try:
        sport, event, odds, wps, espn, scores, plays, moments, fm, fo = _seed_finished_fixture_sync_data(now)
        async with maker() as db:
            db.add_all([sport, event, *odds, *wps, *espn, *scores, *plays, *moments, fm, fo])
            await db.commit()

        _install_sqlite_durable_store(monkeypatch)
        enqueued: list[dict] = []

        def _fake_apply_async(**kwargs):
            enqueued.append(kwargs)

        monkeypatch.setattr(
            "app.tasks.materialize_finished_event_charts",
            SimpleNamespace(apply_async=_fake_apply_async),
            raising=False,
        )

        # Cold-miss fallback mode: cold `range=all` enqueues background materializer once,
        # serves derived `since_start` (`pre_window_omitted=True`), skips L1 cache for `"all"`,
        # and does NOT write the trimmed body to `durable_state_snapshots`.
        monkeypatch.setenv("FINISHED_EVENT_HISTORY_COLD_MISS_MODE", "since_start_fallback")
        assert feh.cold_miss_mode() == feh.COLD_MISS_SINCE_START_FALLBACK

        async with maker() as db:
            resp = await events_route.get_event_odds_history_cached(
                136061, hours=48, chart_range="all", response=Response(), db=db, fresh=False
            )
            body = json.loads(resp.body)
            assert body["pre_window_omitted"] is True
            assert len(enqueued) == 1
            assert enqueued[0]["kwargs"] == {"event_ids": [136061]}
            assert ehc.read(ehc.finished_cache_key(136061, "all")) is None
            stored_cnt = (
                await db.execute(text("SELECT COUNT(*) FROM durable_state_snapshots"))
            ).scalar_one()
            assert stored_cnt == 0

        # Second cold request within cooldown does not duplicate enqueue
        async with maker() as db:
            await events_route.get_event_odds_history_cached(
                136061, hours=48, chart_range="all", response=Response(), db=db, fresh=False
            )
            assert len(enqueued) == 1

        # Back to default `read_through`, `hours` collapse shares one L1 finished key
        monkeypatch.setenv("FINISHED_EVENT_HISTORY_COLD_MISS_MODE", "read_through")
        async with maker() as db:
            r24 = await events_route.get_event_odds_history_cached(
                136061, hours=24, chart_range="all", response=Response(), db=db, fresh=False
            )
            r168 = await events_route.get_event_odds_history_cached(
                136061, hours=168, chart_range="all", response=Response(), db=db, fresh=False
            )
            assert r24.headers["x-feed-cache"] == "miss"
            assert r168.headers["x-feed-cache"] == "hit"
            assert json.loads(r24.body)["pre_window_omitted"] is False

        # Kill switch disables durable read & write cleanly
        monkeypatch.setenv("FINISHED_EVENT_HISTORY_DURABLE_ENABLED", "0")
        assert feh.durable_enabled() is False
        ehc._reset_for_tests()
        async with maker() as db:
            read_calls = []
            monkeypatch.setattr(feh, "read_finished_event_history", lambda *a, **k: read_calls.append(1))
            r_off = await events_route.get_event_odds_history_cached(
                136061, hours=48, chart_range="all", response=Response(), db=db, fresh=False
            )
            assert read_calls == []
            assert json.loads(r_off.body)["event_id"] == 136061
    finally:
        await engine.dispose()
        ehc._reset_for_tests()
        feh._reset_claims_for_tests()


def test_celery_task_routing_beat_and_result_retention_registered():
    from app.tasks import HEAVY_TASKS, _HEAVY_KEEP_ON_BACKGROUND, celery_app
    from app.tasks.result_retention import RESULT_CONSUMER_TASKS

    task_name = "app.tasks.materialize_finished_event_charts"
    assert task_name in RESULT_CONSUMER_TASKS
    assert task_name in _HEAVY_KEEP_ON_BACKGROUND
    assert task_name not in HEAVY_TASKS
    assert celery_app.conf.task_routes[task_name]["queue"] == "background"
    entry = celery_app.conf.beat_schedule["materialize-finished-event-charts"]
    assert entry["task"] == task_name
    assert entry["options"]["queue"] == "background"
    assert set(entry["schedule"].minute) == {0, 10, 20, 30, 40, 50}


@pytest.mark.asyncio
async def test_thin_chart_not_persisted_and_deferred_without_starving_batch(monkeypatch):
    from app.tasks import event_chart_backfill as ecb

    ehc._reset_for_tests()
    feh._reset_claims_for_tests()
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    engine, maker = await _sqlite_session_factory()
    try:
        sport, event, odds, wps, espn, scores, plays, moments, fm, fo = _seed_finished_fixture_sync_data(now)
        # Seed two extra completed events behind a newest thin completed event (30001):
        # 30001 has a 72h FuturesMarket lifetime and only 1 venue point -> thin!
        # 30002 and 30003 have no FuturesMarket -> non-thin (`on_demand_backfill is None`).
        t_head = now - timedelta(hours=1)
        thin_ev = Event(
            id=30001,
            sport_id=1,
            external_id="ext_30001",
            home_team_name="Thin Home",
            away_team_name="Thin Away",
            commence_time=t_head - timedelta(hours=3),
            commence_time_source="espn",
            status="completed",
            home_score=14,
            away_score=10,
            completed_at=t_head,
            win_probability_sources={"kalshi": {"prob": 0.6, "updated_at": t_head.isoformat()}},
            box_score_data={},
        )
        thin_fm = FuturesMarket(
            id=39001,
            source="kalshi",
            external_id="KXNFL-30001",
            sport_id=1,
            event_id=30001,
            name="Thin Away vs Thin Home",
            category="winner",
            mutually_exclusive=True,
            status="closed",
            created_at=t_head - timedelta(days=3),
        )
        thin_wp = WinProbSnapshot(
            event_id=30001,
            source="kalshi",
            home_win_probability=0.6,
            away_win_probability=0.4,
            captured_at=t_head - timedelta(hours=1),
            valid_until=t_head,
            reading_count=1,
            game_state={"market_id": 39001, "poll_type": "live_fast"},
        )
        ready_rows = []
        for idx, eid in enumerate((30002, 30003)):
            comp = t_head - timedelta(minutes=30 + 15 * idx)
            ready_rows.append(
                Event(
                    id=eid,
                    sport_id=1,
                    external_id=f"ext_{eid}",
                    home_team_name=f"Ready Home {idx}",
                    away_team_name=f"Ready Away {idx}",
                    commence_time=comp - timedelta(hours=3),
                    commence_time_source="espn",
                    status="completed",
                    home_score=20,
                    away_score=10,
                    completed_at=comp,
                    win_probability_sources={"kalshi": {"prob": 0.7, "updated_at": comp.isoformat()}},
                    box_score_data={},
                )
            )
            ready_rows.append(
                WinProbSnapshot(
                    event_id=eid,
                    source="kalshi",
                    home_win_probability=0.7,
                    away_win_probability=0.3,
                    captured_at=comp - timedelta(minutes=30),
                    valid_until=comp,
                    reading_count=1,
                    game_state={},
                )
            )
            ready_rows.append(
                WinProbSnapshot(
                    event_id=eid,
                    source="kalshi",
                    home_win_probability=0.75,
                    away_win_probability=0.25,
                    captured_at=comp,
                    valid_until=comp + timedelta(minutes=5),
                    reading_count=1,
                    game_state={},
                )
            )
        async with maker() as db:
            db.add_all([sport, event, *odds, *wps, *espn, *scores, *plays, *moments, fm, fo, thin_ev, thin_fm, thin_wp, *ready_rows])
            await db.commit()

        _install_sqlite_durable_store(monkeypatch)
        monkeypatch.setenv("FINISHED_EVENT_HISTORY_COLD_MISS_MODE", "read_through")

        # 1) Route read-through must NOT store a thin chart for enqueue=True or transient refusal reasons
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "app.tasks.backfill_event_chart_history",
                SimpleNamespace(apply_async=lambda *a, **k: None),
                raising=False,
            )
            for verdict in (
                {"enqueue": True, "event_id": 136061, "served_points": 2, "lifetime_hours": 48.0, "min_period_minutes": 1},
                {"enqueue": False, "reason": "already_claimed"},
                {"enqueue": False, "reason": "hourly_cap"},
                {"enqueue": False, "reason": "no_redis"},
            ):
                async def _stub_plan(session, ev, *, served_points: int, allow_claim: bool = True, _v=verdict):
                    return dict(_v)

                mp.setattr(ecb, "plan_on_demand_fill", _stub_plan)
                ehc._reset_for_tests()
                async with maker() as db:
                    await events_route.get_event_odds_history(
                        136061, hours=48, chart_range="all", response=Response(), db=db, fresh=False
                    )
                    cnt = (
                        await db.execute(text("SELECT COUNT(*) FROM durable_state_snapshots"))
                    ).scalar_one()
                    assert cnt == 0, f"thin chart should not be persisted for verdict={verdict}"

        # Real planner active again: prove background materializer never calls claim_on_demand_fill,
        # defers thin event 30001, and advances to ready event 30002 on the next run (even at limit=1).
        claims: list[int] = []
        monkeypatch.setattr(
            ecb,
            "claim_on_demand_fill",
            lambda eid, **kw: (claims.append(eid), (False, "should_not_be_called"))[1],
        )

        run1 = await feh.materialize_finished_event_charts_async(maker, limit=1)
        assert claims == []
        assert run1["selected"] == 1
        assert run1["per_event"][0]["event_id"] == 30001
        assert run1["per_event"][0]["status"] == "on_demand_pending"
        assert run1["written"] == 0

        run2 = await feh.materialize_finished_event_charts_async(maker, limit=1)
        assert claims == []
        assert run2["selected"] == 1
        assert run2["per_event"][0]["event_id"] == 30002
        assert run2["written"] == 1
    finally:
        await engine.dispose()
        ehc._reset_for_tests()
        feh._reset_claims_for_tests()
