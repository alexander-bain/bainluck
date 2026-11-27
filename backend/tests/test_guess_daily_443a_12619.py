"""Tests for daily /guess challenge, PT freeze, privacy, anti-flood, and 30d sweep (#12619, 443: A)."""

from __future__ import annotations

import contextlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models.models import FuturesMarket, GuessDailyEdition, GuessGroupEntry
from app.routes import guess as guess_routes
from app.services.database import get_db_rw
from app.tasks import celery_app
from app.tasks import guess_daily as guess_task
from app.utils.guess_daily import (
    MAX_GROUP_ENTRIES,
    RETENTION_DAYS,
    build_daily_pack,
    edition_code_for_day,
    load_daily_schedule,
    points_for,
    resolve_card_from_markets,
    sweep_expired_guess_data,
    today_pt,
)

SCHEDULE_PATH = Path(__file__).resolve().parents[1] / "data" / "guess" / "daily_schedule.json"


class _FakeFuturesResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _SyncAsyncSession:
    """Thin async adapter over SQLite ORM session for CI-safe route & task tests."""

    def __init__(self, session, markets_store: dict[int, SimpleNamespace]):
        self._session = session
        self._markets = markets_store

    def get_bind(self):
        return self._session.get_bind()

    def add(self, instance):
        self._session.add(instance)

    async def flush(self):
        self._session.flush()

    async def commit(self):
        self._session.commit()

    async def rollback(self):
        self._session.rollback()

    @contextlib.asynccontextmanager
    async def begin_nested(self):
        nested = self._session.begin_nested()
        try:
            yield nested
            nested.commit()
        except Exception:
            nested.rollback()
            raise

    async def execute(self, statement, params=None):
        return self._session.execute(statement, params or {})

    async def scalar(self, statement):
        return self._session.scalar(statement)

    async def scalars(self, statement):
        descs = getattr(statement, "column_descriptions", None) or ()
        if descs and descs[0].get("entity") is FuturesMarket:
            return _FakeFuturesResult(self._markets.values())
        return self._session.scalars(statement)


def _baseline_markets_for_schedule() -> dict[int, SimpleNamespace]:
    """Build open market fixtures from the real verified outcome list for offline tests."""
    specs = {
        2: [("San Antonio Spurs", 0.221), ("Oklahoma City Thunder", 0.104), ("Boston Celtics", 0.092), ("Philadelphia 76ers", 0.090)],
        4: [("Scottie Scheffler", 0.133), ("Rory McIlroy", 0.082), ("Jon Rahm", 0.045), ("Ludvig Aberg", 0.033)],
        5: [("Scottie Scheffler", 0.132), ("Rory McIlroy", 0.075), ("Jon Rahm", 0.051)],
        8: [("Carolina Hurricanes", 0.125), ("Edmonton Oilers", 0.088), ("Colorado Avalanche", 0.086)],
        53672: [("Carolina", 0.545), ("Tampa Bay", 0.285), ("Atlanta", 0.095), ("New Orleans", 0.075)],
        53673: [("Chicago", 0.495), ("Minnesota", 0.295), ("Detroit", 0.180), ("Green Bay", 0.010)],
        53674: [("New York Giants", 0.668), ("Washington", 0.223), ("Dallas", 0.074), ("Philadelphia", 0.035)],
        86832: [("San Francisco 49ers", 0.165), ("Buffalo Bills", 0.146), ("Chicago Bears", 0.090)],
        108237: [("Raye", 0.340), ("Olivia Dean", 0.205), ("Lana Del Rey", 0.130), ("Dua Lipa", 0.110)],
        108306: [("Rock", 0.650), ("R&B/Hip-Hop", 0.465), ("Americana/Folk", 0.215), ("Gospel", 0.210)],
        108339: [("Yes", 0.155)],
        109287: [("Bernie Sanders", 0.175), ("Sam Altman", 0.105), ("Tulsi Gabbard", 0.100), ("Vivek Ramaswamy", 0.080)],
        109435: [("Before Jan 20, 2029", 0.205), ("Before Jan 1, 2028", 0.125)],
        112818: [("Before Jan 1, 2028", 0.605), ("Before May 1, 2027", 0.245)],
        113012: [("Yes", 0.034)],
        113355: [("Spider-Man: Brand New Day", 0.885), ("Avengers: Doomsday", 0.118)],
        113364: [("Marine Le Pen", 0.441), ("David Lisnard", 0.239), ("Jean-Luc Mélenchon", 0.145), ("François Hollande", 0.047)],
        115379: [("$800B", 0.685), ("$1T", 0.595), ("$1.2T", 0.425), ("$1.4T", 0.295)],
        5165726: [("The Odyssey", 0.980), ("The Debut", 0.755)],
        6173044: [("The Odyssey", 0.396), ("You Can See Everything", 0.192), ("Dune: Part Three", 0.087), ("The Black Ball", 0.049)],
        6601311: [("Georgia Bulldogs", 0.300), ("Notre Dame Fighting Irish", 0.171), ("Texas Longhorns", 0.124), ("Alabama Crimson Tide", 0.121)],
        7578123: [("Yes", 0.435)],
        13793198: [("Yes", 0.380), ("No", 0.620)],
        13794309: [("Yes", 0.362), ("No", 0.637)],
        27467306: [("James Talarico", 0.299), ("Abdul El-Sayed", 0.225)],
        30587891: [("Yes", 0.325)],
        32127334: [("Google", 0.749), ("Anthropic", 0.188), ("OpenAI", 0.034), ("Meta", 0.013)],
        56916361: [("Yes", 0.092), ("No", 0.908)],
        56995847: [("Yes", 0.090), ("No", 0.910)],
        57574250: [("Quarter-point increase", 0.939), ("No change", 0.036)],
        60607595: [("December 31, 2027", 0.625), ("December 31, 2026", 0.178)],
        60607786: [("Real Madrid", 0.537), ("Paris Saint-Germain", 0.248), ("Barcelona", 0.107), ("Arsenal", 0.031)],
        60626093: [("June 30, 2027", 0.470), ("March 31, 2027", 0.230)],
        61380674: [("Yes", 0.480), ("No", 0.520)],
        67717832: [("After March 2027", 0.567), ("January 2027", 0.162), ("March 2027", 0.122), ("February 2027", 0.106)],
        67903133: [("Yes", 0.045), ("No", 0.955)],
        68198529: [("Los Angeles Dodgers", 0.165)],
        70400892: [("Finland", 0.913)],
        70733200: [("End of Beginning – Djo", 0.870)],
        70883374: [("Yes", 0.145), ("No", 0.855)],
        71380656: [("December 31, 2026", 0.775)],
        72081893: [("Aryna Sabalenka", 0.217)],
        72081895: [("Carlos Alcaraz", 0.541), ("Alexander Zverev", 0.168), ("Ben Shelton", 0.048), ("Novak Djokovic", 0.038)],
    }
    return {
        mid: SimpleNamespace(
            id=mid,
            status="open",
            end_date=None,
            outcomes=[
                SimpleNamespace(id=mid * 100 + i, name=name, probability=prob, status="open")
                for i, (name, prob) in enumerate(outs)
            ],
        )
        for mid, outs in specs.items()
    }


@pytest.fixture
async def guess_test_env(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    GuessDailyEdition.__table__.create(engine)
    GuessGroupEntry.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()
    markets_store = _baseline_markets_for_schedule()
    guess_routes._reset_rate_limits_for_tests()

    # Freeze wall-clock "now" in PT to Friday 2026-11-27 08:30 AM PT (16:30 UTC).
    clock = {"now": datetime(2026, 11, 27, 16, 30, tzinfo=timezone.utc)}

    from app.utils import guess_daily as gd_mod

    orig_freeze = gd_mod.get_or_freeze_daily_edition

    async def _frozen_now_get(db, requested_day=None, *, now_utc=None, schedule=None):
        return await orig_freeze(
            db, requested_day, now_utc=now_utc or clock["now"], schedule=schedule
        )

    monkeypatch.setattr(guess_routes, "get_or_freeze_daily_edition", _frozen_now_get)
    monkeypatch.setattr(guess_routes, "_get_async_rl_redis", lambda: None)

    async def _override_rw():
        yield _SyncAsyncSession(db_session, markets_store)

    app.dependency_overrides[get_db_rw] = _override_rw

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, db_session, markets_store, clock

    app.dependency_overrides.clear()
    guess_routes._reset_rate_limits_for_tests()
    db_session.close()
    engine.dispose()


def _winning_answers_for_pack(pack: dict) -> list[int]:
    answers: list[int] = []
    for card in pack["cards"]:
        kind = card["kind"]
        if kind == "side":
            answers.append(1 if card["answer"] > 50 else 0)
        elif kind in ("versus", "leader"):
            opts = card["options"]
            best = max(range(len(opts)), key=lambda idx: opts[idx]["percent"])
            answers.append(best)
        elif kind == "four":
            answers.append(card["options"].index(card["answer"]))
        else:
            answers.append(int(card["answer"]))
    return answers


def test_guess_group_entry_schema_stores_only_privacy_allowed_columns():
    cols = set(GuessGroupEntry.__table__.columns.keys())
    assert cols == {
        "id",
        "day_pt",
        "group_code",
        "nickname",
        "nickname_lower",
        "answers",
        "step_times",
    }
    forbidden = {"user_id", "account_id", "email", "device_id", "ip", "ip_address", "score", "points"}
    assert cols.isdisjoint(forbidden)


def test_schedule_json_resolves_cleanly_for_all_seven_days_and_passes_copy_bans():
    sched = load_daily_schedule(SCHEDULE_PATH)
    days = sched["days"]
    assert len(days) == 7
    markets = _baseline_markets_for_schedule()
    now = datetime(2026, 11, 27, 16, 0, tzinfo=timezone.utc)
    ban_re = re.compile(
        r"\b(questions?|stale|blend|priced?|price|curated|cohort|bids?|odds|bets?|betting|wager|gamble|kalshi|polymarket|markets?)\b",
        re.IGNORECASE,
    )

    for day_str, day_cfg in days.items():
        day_obj = date.fromisoformat(day_str)
        pack, provenance = build_daily_pack(day_obj, day_cfg, markets, now)
        assert len(pack["cards"]) == 15
        assert pack["asOf"].endswith("PT")
        assert [s["name"] for s in pack["steps"]] == ["Easy", "Medium", "Hard"]
        topics = {t: sum(1 for c in pack["cards"] if c["topic"] == t) for t in pack["topics"]}
        assert len(topics) == 3
        assert all(count >= 3 for count in topics.values()), (day_str, topics)
        ours = [c["ours"] for c in pack["cards"]]
        assert not any(a and b for a, b in zip(ours, ours[1:]))
        assert not any(p.get("swapped_from_slot") for p in provenance)

        for bucket in ("step_cards", "spares"):
            for tmpl in [t for items in day_cfg[bucket].values() for t in items]:
                if bucket == "spares":
                    assert resolve_card_from_markets(tmpl, markets, now, day_seed=day_str) is not None
                for txt in [
                    tmpl["prompt"],
                    tmpl["short"],
                    tmpl["context"],
                    tmpl.get("sub", ""),
                    tmpl.get("roastHigh", ""),
                    tmpl.get("roastLow", ""),
                    *[o["label"] for o in tmpl.get("options", [])],
                    *[o["short"] for o in tmpl.get("options", [])],
                ]:
                    assert not ban_re.search(txt), f"Banned word in {day_str} {tmpl['id']}: {txt}"


@pytest.mark.asyncio
async def test_pt_daily_freeze_ignores_subsequent_probability_moves(guess_test_env):
    client, _db, markets, _clock = guess_test_env

    first = await client.get("/api/guess/today")
    assert first.status_code == 200
    data1 = first.json()
    assert data1["day"] == "2026-11-27"
    assert data1["edition_code"] == edition_code_for_day(date(2026, 11, 27))
    first_recession_answer = data1["pack"]["cards"][0]["answer"]
    assert first_recession_answer == 3

    # Verify PostgreSQL Numeric/Decimal outcome values resolve cleanly (not rejected by isinstance).
    decimal_outcome = SimpleNamespace(
        id=1, status="open", end_date=None,
        outcomes=[SimpleNamespace(id=10, name="Yes", probability=Decimal("0.7200"), status="open")],
    )
    dec_card = resolve_card_from_markets(
        {"id": "dchk", "kind": "side", "topic": "Sports", "emoji": "🏆", "prompt": "Test", "short": "Test", "context": "Ctx", "extras": [], "source": {"market_id": 1, "outcome_name": "Yes"}},
        {1: decimal_outcome},
        datetime(2026, 11, 27, 16, 0, tzinfo=timezone.utc),
        day_seed="2026-11-27",
    )
    assert dec_card is not None and dec_card[0]["answer"] == 72

    # Mutate live outcome in DB after the morning freeze — frozen pack stays unchanged.
    markets[113012].outcomes[0].probability = 0.88
    second = await client.get("/api/guess/today")
    assert second.status_code == 200
    assert second.json()["pack"]["cards"][0]["answer"] == 3


@pytest.mark.asyncio
async def test_closed_or_unpriced_primary_swaps_to_spare_and_503_never_fabricates(guess_test_env):
    client, db, markets, clock = guess_test_env
    # Close primary market 113012 (e1) AND remove probability on 71380656 (e5).
    markets[113012].status = "closed"
    markets[71380656].outcomes[0].probability = None

    resp = await client.get("/api/guess/today")
    assert resp.status_code == 200
    pack = resp.json()["pack"]
    assert len(pack["cards"]) == 15
    card_ids = [c["id"] for c in pack["cards"]]
    assert card_ids[0] == "se1"
    assert card_ids[4] == "se2"
    row = db.scalar(select(GuessDailyEdition).where(GuessDailyEdition.day_pt == date(2026, 11, 27)))
    assert any(p.get("swapped_from_slot") == "e1" for p in row.source_snapshot)
    assert any(p.get("swapped_from_slot") == "e5" for p in row.source_snapshot)

    # Next PT day where Easy markets and spares are all closed -> explicit 503, never fabricated numbers.
    clock["now"] = datetime(2026, 11, 28, 16, 30, tzinfo=timezone.utc)
    for m in markets.values():
        m.status = "closed"
    fail = await client.get("/api/guess/today")
    assert fail.status_code == 503


@pytest.mark.asyncio
async def test_server_computes_scores_rejects_client_score_and_isolates_groups(guess_test_env):
    client, _db, _markets, _clock = guess_test_env

    # No public board or group list endpoint exists.
    assert (await client.get("/api/guess/groups")).status_code in (404, 405)
    assert (await client.get("/api/guess/groups/short")).status_code == 422

    today_resp = await client.get("/api/guess/today")
    pack = today_resp.json()["pack"]
    win = _winning_answers_for_pack(pack)

    # Client trying to pass score / points / user_id / device_id is rejected by extra="forbid".
    for bad_key, bad_val in [("score", 9999), ("points", 9999), ("user_id", 42), ("device_id", "dev1")]:
        rejected = await client.post(
            "/api/guess/groups/alpha12345/entries",
            json={
                "day": "2026-11-27",
                "nickname": "Hacker",
                "answers": win,
                "step_times": [10, 12, 15],
                bad_key: bad_val,
            },
        )
        assert rejected.status_code == 422

    # Alex submits winning answers -> server computes exact score from engine rules.
    expected_total = sum(points_for(card, g) for card, g in zip(pack["cards"], win, strict=True))
    res1 = await client.post(
        "/api/guess/groups/alpha12345/entries",
        json={"day": "2026-11-27", "nickname": "  Alex  ", "answers": win, "step_times": [10, 12, 15]},
        headers={"X-Forwarded-For": "10.0.0.1"},
    )
    assert res1.status_code == 201
    board = res1.json()
    assert [e["nickname"] for e in board["entries"]] == ["Alex"]
    assert board["entries"][0]["points"] == expected_total
    assert board["entries"][0]["total_time_seconds"] == 37

    # Identical replay returns 200 idempotently; different answers with same nickname (case-insensitive) return 409.
    replay = await client.post(
        "/api/guess/groups/alpha12345/entries",
        json={"day": "2026-11-27", "nickname": "alex", "answers": win, "step_times": [10, 12, 15]},
        headers={"X-Forwarded-For": "10.0.0.2"},
    )
    assert replay.status_code == 200

    collision = await client.post(
        "/api/guess/groups/alpha12345/entries",
        json={"day": "2026-11-27", "nickname": "ALEX", "answers": [0 if x != 0 else 1 for x in win], "step_times": [9, 9, 9]},
        headers={"X-Forwarded-For": "10.0.0.3"},
    )
    assert collision.status_code == 409

    # Group B stays completely isolated from Group A.
    other_group = await client.get("/api/guess/groups/bravo67890")
    assert other_group.status_code == 200
    assert other_group.json()["entries"] == []


@pytest.mark.asyncio
async def test_anti_flood_client_burst_group_burst_and_30_entry_cap(guess_test_env):
    client, db, _markets, _clock = guess_test_env
    pack = (await client.get("/api/guess/today")).json()["pack"]
    win = _winning_answers_for_pack(pack)

    # 1. Per-client burst cap: > 8 submissions in 5 minutes -> 429.
    for i in range(8):
        resp = await client.post(
            "/api/guess/groups/burstgrp01/entries",
            json={"day": "2026-11-27", "nickname": f"P{i}", "answers": win, "step_times": [5, 5, 5]},
            headers={"X-Forwarded-For": "203.0.113.9"},
        )
        assert resp.status_code == 201
    throttled_client = await client.post(
        "/api/guess/groups/burstgrp01/entries",
        json={"day": "2026-11-27", "nickname": "P99", "answers": win, "step_times": [5, 5, 5]},
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert throttled_client.status_code == 429

    # 2. Per-group burst cap: > 20 submissions in 1 minute from distinct clients -> 429.
    for i in range(12):
        resp = await client.post(
            "/api/guess/groups/burstgrp01/entries",
            json={"day": "2026-11-27", "nickname": f"Q{i}", "answers": win, "step_times": [5, 5, 5]},
            headers={"X-Forwarded-For": f"198.51.100.{i + 10}"},
        )
        assert resp.status_code == 201
    throttled_group = await client.post(
        "/api/guess/groups/burstgrp01/entries",
        json={"day": "2026-11-27", "nickname": "Q99", "answers": win, "step_times": [5, 5, 5]},
        headers={"X-Forwarded-For": "198.51.100.250"},
    )
    assert throttled_group.status_code == 429

    # 3. Hard ceiling of 30 entries per (day, group).
    guess_routes._reset_rate_limits_for_tests()
    for i in range(28):
        db.add(
            GuessGroupEntry(
                day_pt=date(2026, 11, 27),
                group_code="capgrp0001",
                nickname=f"Seed{i}",
                nickname_lower=f"seed{i}",
                answers=win,
                step_times=[10, 10, 10],
            )
        )
    db.commit()

    for idx in (28, 29):
        ok = await client.post(
            "/api/guess/groups/capgrp0001/entries",
            json={"day": "2026-11-27", "nickname": f"Seed{idx}", "answers": win, "step_times": [10, 10, 10]},
            headers={"X-Forwarded-For": f"192.0.2.{idx}"},
        )
        assert ok.status_code == 201
    assert MAX_GROUP_ENTRIES == 30
    over_cap = await client.post(
        "/api/guess/groups/capgrp0001/entries",
        json={"day": "2026-11-27", "nickname": "Seed30", "answers": win, "step_times": [10, 10, 10]},
        headers={"X-Forwarded-For": "192.0.2.30"},
    )
    assert over_cap.status_code == 429


@pytest.mark.asyncio
async def test_30_day_retention_sweep_and_beat_task(guess_test_env, monkeypatch):
    _client, db, markets, _clock = guess_test_env
    today = date(2026, 11, 27)
    expired_day = today - timedelta(days=RETENTION_DAYS + 1)
    boundary_day = today - timedelta(days=RETENTION_DAYS)

    for d, code in [(expired_day, "pold0"), (boundary_day, "pbnd0")]:
        db.add(
            GuessDailyEdition(
                day_pt=d,
                edition_code=code,
                frozen_at=datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc),
                pack_json={"id": d.isoformat(), "code": code, "cards": []},
                source_snapshot=[],
            )
        )
        db.add(
            GuessGroupEntry(
                day_pt=d,
                group_code="sweepgroup1",
                nickname="Alex",
                nickname_lower="alex",
                answers=[1] * 15,
                step_times=[5, 5, 5],
            )
        )
    db.commit()

    @contextlib.asynccontextmanager
    async def _fake_task_session():
        yield _SyncAsyncSession(db, markets)

    monkeypatch.setattr(guess_task, "get_task_session", _fake_task_session)
    result = await guess_task.run_guess_daily_maintenance(
        now_utc=datetime(2026, 11, 27, 16, 5, tzinfo=timezone.utc)
    )
    assert result["deleted_entries"] == 1
    assert result["deleted_editions"] == 1
    assert result["edition_frozen"] is True

    remaining_days = {r.day_pt for r in db.scalars(select(GuessDailyEdition)).all()}
    assert expired_day not in remaining_days
    assert boundary_day in remaining_days
    assert today in remaining_days

    entry_days = {r.day_pt for r in db.scalars(select(GuessGroupEntry)).all()}
    assert entry_days == {boundary_day}
    assert "guess-daily-maintenance" in celery_app.conf.beat_schedule
    assert today_pt(datetime(2026, 11, 27, 7, 59, tzinfo=timezone.utc)) == date(2026, 11, 26)
