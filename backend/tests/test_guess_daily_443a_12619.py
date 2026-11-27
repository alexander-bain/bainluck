"""Tests for daily /guess challenge, PT freeze, verified-title fidelity, privacy, anti-flood, and 30d sweep (#12619, 443: A)."""

from __future__ import annotations

import contextlib
import hashlib
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models.models import GuessDailyEdition, GuessGroupEntry
from app.routes import guess as guess_routes
from app.services.database import get_db_rw
from app.tasks import celery_app
from app.tasks import guess_daily as guess_task
from app.utils.guess_daily import (
    CHANCE_MID_GAP,
    EARNED_MISS,
    LEAD_GAP,
    MAX_DAILY_ENTRIES,
    MAX_GROUP_ENTRIES,
    OPTION_GAP,
    RETENTION_DAYS,
    SIDE_GAP,
    VERSUS_GAP,
    build_daily_pack,
    edition_code_for_day,
    full_guess,
    load_daily_schedule,
    load_site_market_details,
    points_for,
    resolve_card_from_markets,
    today_pt,
)

SCHEDULE_PATH = Path(__file__).resolve().parents[1] / "data" / "guess" / "daily_schedule.json"


def _make_detail(
    market_id: int,
    outcomes: list[tuple[str, float]],
    *,
    name: str = "Fixture board",
    status: str = "open",
    representation: str = "verified_title",
    resolution_date: str | None = None,
    llm_sport_category: str | None = None,
    extra_fields_by_name: dict[str, dict] | None = None,
    last_updated: str | None = None,
) -> dict:
    extra_map = extra_fields_by_name or {}
    stamp = last_updated or "2026-11-27T15:00:00+00:00"
    out_rows = []
    for idx, (oname, prob) in enumerate(outcomes):
        row = {
            "id": market_id * 100 + idx,
            "name": oname,
            "probability": prob,
            "status": "open",
            "is_winner": False,
            "is_out": False,
            "kalshi_no_bid": False,
            "rendered_percent": None,
            "source_mark": {"state": "verified" if representation == "verified_title" else "direct"},
            "last_updated": stamp,
        }
        row.update(extra_map.get(oname, {}))
        out_rows.append(row)
    return {
        "id": market_id,
        "name": name,
        "status": status,
        "representation": representation,
        "resolution_date": resolution_date,
        "llm_sport_category": llm_sport_category,
        "outcomes": out_rows,
    }


def _fixture_schedule() -> dict:
    """In-memory synthetic schedule for tests (never leaks into checked-in data)."""
    day_27 = {
        "steps": [
            {"name": "Easy", "how": "Above or below 50%? Which is more likely? One tap each."},
            {"name": "Medium", "how": "Pick one of four."},
            {"name": "Hard", "how": "Slide to the number. Closest wins."},
        ],
        "topics": ["Sports", "Money & Tech", "World & Culture"],
        "step_cards": {
            "easy": [
                {
                    "id": "e1",
                    "kind": "side",
                    "topic": "Money & Tech",
                    "emoji": "📉",
                    "extras": ["💵", "🏛️"],
                    "prompt": "A U.S. recession is called before 2027",
                    "short": "U.S. recession call",
                    "context": "Synthetic fixture context for side low.",
                    "source": {"market_id": 1001, "outcome_name": "Yes"},
                },
                {
                    "id": "e2",
                    "kind": "versus",
                    "topic": "Sports",
                    "emoji": "🏆",
                    "prompt": "Which is more likely?",
                    "short": "Team A vs Team B",
                    "context": "Synthetic fixture context for versus.",
                    "options": [
                        {"market_id": 1002, "outcome_name": "Alpha", "label": "Alpha wins title", "short": "Alpha", "emoji": "🏀"},
                        {"market_id": 1003, "outcome_name": "Beta", "label": "Beta wins bowl", "short": "Beta", "emoji": "🏈"},
                    ],
                },
                {
                    "id": "e3",
                    "kind": "side",
                    "topic": "Sports",
                    "emoji": "🏈",
                    "extras": ["🏆", "🗽"],
                    "prompt": "East club wins the division crown",
                    "short": "East club division",
                    "context": "Synthetic fixture context for side high.",
                    "source": {"market_id": 1004, "outcome_name": "East"},
                },
                {
                    "id": "e4",
                    "kind": "versus",
                    "topic": "World & Culture",
                    "emoji": "🎬",
                    "prompt": "Which is more likely?",
                    "short": "Film vs Album",
                    "context": "Synthetic fixture context for second versus.",
                    "options": [
                        {"market_id": 1005, "outcome_name": "Album", "label": "Album hits number one", "short": "Album", "emoji": "🎸"},
                        {"market_id": 1006, "outcome_name": "Film", "label": "Film wins top prize", "short": "Film", "emoji": "🎬"},
                    ],
                },
                {
                    "id": "e5",
                    "kind": "side",
                    "topic": "Money & Tech",
                    "emoji": "🤖",
                    "extras": ["📈", "💻"],
                    "prompt": "Chip index tops 9000 before December",
                    "short": "Chip index milestone",
                    "context": "Synthetic fixture context for third side.",
                    "source": {"market_id": 1007, "outcome_name": "Yes"},
                },
            ],
            "medium": [
                {
                    "id": "m1",
                    "kind": "leader",
                    "topic": "Sports",
                    "emoji": "🏈",
                    "independent": False,
                    "market_id": 1008,
                    "prompt": "Which club is favored for the trophy?",
                    "short": "Trophy favorite",
                    "context": "Synthetic leader fixture.",
                    "options": [
                        {"outcome_name": "North", "label": "North", "short": "North", "emoji": "☘️"},
                        {"outcome_name": "South", "label": "South", "short": "South", "emoji": "🐶"},
                        {"outcome_name": "West", "label": "West", "short": "West", "emoji": "🤘"},
                        {"outcome_name": "Coastal", "label": "Coastal", "short": "Coastal", "emoji": "🌊"},
                    ],
                },
                {
                    "id": "m2",
                    "kind": "four",
                    "topic": "Sports",
                    "emoji": "⚾",
                    "extras": ["🏆", "🌞"],
                    "answer_slot": 1,
                    "prompt": "What chance do the Pioneers have this season?",
                    "short": "Pioneers chance",
                    "context": "Synthetic four fixture at slot 1.",
                    "source": {"market_id": 1009, "outcome_name": "Pioneers"},
                },
                {
                    "id": "m3",
                    "kind": "leader",
                    "topic": "World & Culture",
                    "emoji": "🎬",
                    "independent": False,
                    "market_id": 1010,
                    "prompt": "Which nominee leads the awards race?",
                    "short": "Awards race favorite",
                    "context": "Synthetic second leader fixture.",
                    "options": [
                        {"outcome_name": "Runner", "label": "Runner", "short": "Runner", "emoji": "🎞️"},
                        {"outcome_name": "Sequel", "label": "Sequel", "short": "Sequel", "emoji": "🏜️"},
                        {"outcome_name": "Drama", "label": "Drama", "short": "Drama", "emoji": "🎱"},
                        {"outcome_name": "Horizon", "label": "Horizon", "short": "Horizon", "emoji": "⚔️"},
                    ],
                },
                {
                    "id": "m4",
                    "kind": "four",
                    "topic": "Money & Tech",
                    "emoji": "🤖",
                    "extras": ["📈", "🏦"],
                    "answer_slot": 2,
                    "prompt": "What chance does CloudCo have to top $1T?",
                    "short": "CloudCo milestone",
                    "context": "Synthetic four fixture at slot 2.",
                    "source": {"market_id": 1011, "outcome_name": "Above"},
                },
                {
                    "id": "m5",
                    "kind": "leader",
                    "topic": "Money & Tech",
                    "emoji": "🧠",
                    "independent": False,
                    "market_id": 1012,
                    "prompt": "Which lab leads end-of-year benchmarks?",
                    "short": "Lab leader",
                    "context": "Synthetic third leader fixture.",
                    "options": [
                        {"outcome_name": "LabA", "label": "LabA", "short": "LabA", "emoji": "🧠"},
                        {"outcome_name": "LabB", "label": "LabB", "short": "LabB", "emoji": "🚀"},
                        {"outcome_name": "LabC", "label": "LabC", "short": "LabC", "emoji": "🌐"},
                        {"outcome_name": "LabD", "label": "LabD", "short": "LabD", "emoji": "🔍"},
                    ],
                },
            ],
            "hard": [
                {
                    "id": "h1",
                    "kind": "chance",
                    "topic": "Sports",
                    "emoji": "🏒",
                    "extras": ["🏒", "❄️"],
                    "prompt": "Harbor Skaters reach Round 2 of the playoffs",
                    "short": "Harbor Skaters",
                    "context": "Synthetic hard card 1.",
                    "roastHigh": "{n} overshot {g}% on {w}%.",
                    "roastLow": "{n} undershot {g}% on {w}%.",
                    "source": {"market_id": 1013, "outcome_name": "Yes"},
                },
                {
                    "id": "h2",
                    "kind": "chance",
                    "topic": "World & Culture",
                    "emoji": "🎵",
                    "extras": ["🎤", "💿"],
                    "prompt": "Festival headliner sells out both nights",
                    "short": "Festival sellout",
                    "context": "Synthetic hard card 2 (low answer drops roastLow).",
                    "roastHigh": "{n} went high at {g}% vs {w}%.",
                    "roastLow": "{n} went too low on a tiny percent.",
                    "source": {"market_id": 1014, "outcome_name": "Yes"},
                },
                {
                    "id": "h3",
                    "kind": "chance",
                    "topic": "Money & Tech",
                    "emoji": "🏛️",
                    "extras": ["💵", "🏦"],
                    "prompt": "Central bank holds rates steady in March",
                    "short": "Rate hold",
                    "context": "Synthetic hard card 3 (high answer drops roastHigh).",
                    "roastHigh": "{n} cannot earn this high roast on {w}%.",
                    "roastLow": "{n} played {g}% when it sat at {w}%.",
                    "source": {"market_id": 1015, "outcome_name": "Yes"},
                },
                {
                    "id": "h4",
                    "kind": "chance",
                    "topic": "World & Culture",
                    "emoji": "🌍",
                    "extras": ["🛰️", "🔭"],
                    "prompt": "Moon relay launches before July",
                    "short": "Moon relay launch",
                    "context": "Synthetic hard card 4.",
                    "roastHigh": "{n} guessed {g}% above {w}%.",
                    "roastLow": "{n} guessed {g}% below {w}%.",
                    "source": {"market_id": 1016, "outcome_name": "Yes"},
                },
                {
                    "id": "h5",
                    "kind": "chance",
                    "topic": "Sports",
                    "emoji": "🎾",
                    "extras": ["🏆", "🏟️"],
                    "prompt": "Top seed holds grass trophy",
                    "short": "Grass trophy",
                    "context": "Synthetic hard card 5.",
                    "roastHigh": "{n} aimed at {g}% on {w}%.",
                    "roastLow": "{n} slipped to {g}% on {w}%.",
                    "source": {"market_id": 1017, "outcome_name": "Yes"},
                },
            ],
        },
        "spares": {
            "easy": [
                {
                    "id": "se1",
                    "kind": "side",
                    "topic": "Money & Tech",
                    "emoji": "💡",
                    "extras": ["🔋", "📊"],
                    "prompt": "Grid storage capacity doubles this year",
                    "short": "Grid storage",
                    "context": "Spare side low.",
                    "source": {"market_id": 1020, "outcome_name": "Yes"},
                },
                {
                    "id": "se2",
                    "kind": "side",
                    "topic": "Money & Tech",
                    "emoji": "🚢",
                    "extras": ["⚓", "📦"],
                    "prompt": "Pacific port clears record cargo",
                    "short": "Port record",
                    "context": "Spare side high.",
                    "source": {"market_id": 1021, "outcome_name": "Yes"},
                },
            ],
            "medium": [
                {
                    "id": "sm1",
                    "kind": "four",
                    "topic": "Sports",
                    "emoji": "⚽",
                    "extras": ["🏆", "🏟️"],
                    "prompt": "What chance does United FC have to finish top four?",
                    "short": "United top four",
                    "context": "Spare four card.",
                    "source": {"market_id": 1022, "outcome_name": "United"},
                },
                {
                    "id": "sm2",
                    "kind": "leader",
                    "topic": "World & Culture",
                    "emoji": "📚",
                    "independent": True,
                    "market_id": 1023,
                    "prompt": "Which author wins a major honor this fall?",
                    "short": "Fall book honor",
                    "context": "Spare independent leader.",
                    "options": [
                        {"outcome_name": "WriterA", "label": "WriterA", "short": "A", "emoji": "✍️"},
                        {"outcome_name": "WriterB", "label": "WriterB", "short": "B", "emoji": "📖"},
                        {"outcome_name": "WriterC", "label": "WriterC", "short": "C", "emoji": "🖋️"},
                        {"outcome_name": "WriterD", "label": "WriterD", "short": "D", "emoji": "📜"},
                    ],
                },
            ],
            "hard": [
                {
                    "id": "sh1",
                    "kind": "chance",
                    "topic": "World & Culture",
                    "emoji": "🌦️",
                    "extras": ["☀️", "🌊"],
                    "prompt": "Warm summer reading breaks monthly mark",
                    "short": "Warm summer",
                    "context": "Spare hard card.",
                    "roastHigh": "{n} reached {g}% on {w}%.",
                    "roastLow": "{n} dropped to {g}% on {w}%.",
                    "source": {"market_id": 1024, "outcome_name": "Yes"},
                }
            ],
        },
    }
    return {"version": 1, "days": {"2026-11-26": day_27, "2026-11-27": day_27, "2026-11-28": day_27}}


def _baseline_details() -> dict[int, dict]:
    return {
        1001: _make_detail(1001, [("Yes", Decimal("0.140"))]),
        1002: _make_detail(1002, [("Alpha", 0.21)]),
        1003: _make_detail(1003, [("Beta", 0.36)]),
        1004: _make_detail(1004, [("East", 0.67)]),
        1005: _make_detail(1005, [("Album", 0.62)]),
        1006: _make_detail(1006, [("Film", 0.38)]),
        1007: _make_detail(1007, [("Yes", 0.78)]),
        1008: _make_detail(1008, [("North", 0.17), ("South", 0.44), ("West", 0.13), ("Coastal", 0.12)]),
        1009: _make_detail(1009, [("Pioneers", 0.31)]),
        1010: _make_detail(1010, [("Runner", 0.19), ("Sequel", 0.08), ("Drama", 0.05), ("Horizon", 0.41)]),
        1011: _make_detail(1011, [("Above", 0.64)]),
        1012: _make_detail(1012, [("LabA", 0.18), ("LabB", 0.06), ("LabC", 0.69), ("LabD", 0.04)]),
        1013: _make_detail(1013, [("Yes", 0.42)]),
        1014: _make_detail(1014, [("Yes", 0.04)]),
        1015: _make_detail(1015, [("Yes", 0.85)]),
        1016: _make_detail(1016, [("Yes", 0.33)]),
        1017: _make_detail(1017, [("Yes", 0.59)]),
        1020: _make_detail(1020, [("Yes", 0.22)]),
        1021: _make_detail(1021, [("Yes", 0.71)]),
        1022: _make_detail(1022, [("United", 0.44)]),
        1023: _make_detail(1023, [("WriterA", 0.52), ("WriterB", 0.45), ("WriterC", 0.39), ("WriterD", 0.28)]),
        1024: _make_detail(1024, [("Yes", 0.37)]),
    }


class _SyncAsyncSession:
    def __init__(self, session):
        self._session = session

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
        return self._session.scalars(statement)


@pytest.fixture
async def guess_test_env(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    GuessDailyEdition.__table__.create(engine)
    GuessGroupEntry.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()
    details_store = _baseline_details()
    sched_store = _fixture_schedule()
    guess_routes._reset_rate_limits_for_tests()

    clock = {"now": datetime(2026, 11, 27, 16, 30, tzinfo=timezone.utc)}

    from app.utils import guess_daily as gd_mod

    orig_freeze = gd_mod.get_or_freeze_daily_edition

    async def _frozen_now_get(db, requested_day=None, *, now_utc=None, schedule=None, market_details=None):
        return await orig_freeze(
            db,
            requested_day,
            now_utc=now_utc or clock["now"],
            schedule=schedule or sched_store,
            market_details=market_details if market_details is not None else details_store,
        )

    monkeypatch.setattr(guess_routes, "get_or_freeze_daily_edition", _frozen_now_get)
    monkeypatch.setattr(guess_routes, "today_pt", lambda now=None: today_pt(now or clock["now"]))
    monkeypatch.setattr(guess_routes, "_get_async_rl_redis", lambda: None)

    async def _override_rw():
        yield _SyncAsyncSession(db_session)

    app.dependency_overrides[get_db_rw] = _override_rw

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, db_session, details_store, sched_store, clock

    app.dependency_overrides.clear()
    guess_routes._reset_rate_limits_for_tests()
    db_session.close()
    engine.dispose()


def _winning_answers_for_pack(pack: dict) -> list[int]:
    return [full_guess(card) for card in pack["cards"]]


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
        "hidden_at",
    }
    hidden_col = GuessGroupEntry.__table__.columns["hidden_at"]
    assert hidden_col.nullable is True
    assert getattr(hidden_col.type, "timezone", False) is True
    forbidden = {"user_id", "account_id", "email", "device_id", "ip", "ip_address", "score", "points"}
    assert cols.isdisjoint(forbidden)


def test_checked_in_schedule_file_is_valid_shell_for_fable_and_edition_codes_avoid_c1_d1():
    sched = load_daily_schedule(SCHEDULE_PATH)
    assert sched["version"] == 1
    days = sched["days"]
    assert "2026-11-28" in days and "2026-11-29" in days
    ban_re = re.compile(r"\b(questions?|stale|blend|priced?|curated|cohort|bids?)\b", re.I)
    for day_key, day_obj in days.items():
        assert len(day_obj["topics"]) == 3
        for bucket in ("step_cards", "spares"):
            for step_key in ("easy", "medium", "hard"):
                for tmpl in (day_obj.get(bucket) or {}).get(step_key) or ():
                    for fld in ("prompt", "sub", "short", "context", "roastHigh", "roastLow"):
                        val = tmpl.get(fld)
                        if val:
                            assert not ban_re.search(val), f"{day_key} {tmpl['id']}.{fld}: {val}"
                            if fld in ("roastHigh", "roastLow"):
                                assert len(val) <= 110
    for offset in range(-400, 400):
        code = edition_code_for_day(date(2026, 1, 1) + timedelta(days=offset))
        assert len(code) >= 4
        assert code not in {"c1", "d1"}


def test_rendered_percent_uses_site_value_fallback_and_rejects_extremes():
    now = datetime(2026, 11, 27, 16, 0, tzinfo=timezone.utc)
    # Pair at 0.195 and 0.805 where site rendered_percent rounds to 19 and 81 (half-up would give 20 and 81).
    pair_details = {
        9001: {
            **_make_detail(9001, [("Yes", 0.195), ("No", 0.805)], extra_fields_by_name={"Yes": {"rendered_percent": 19}, "No": {"rendered_percent": 81}}),
        },
        9002: {
            **_make_detail(9002, [("Yes", 0.565)], extra_fields_by_name={"Yes": {"rendered_percent": None}}),
        },
        9003: {
            **_make_detail(9003, [("Yes", 0.004)], extra_fields_by_name={"Yes": {"rendered_percent": 0}}),
        },
        9004: {
            **_make_detail(9004, [("Yes", 0.996)], extra_fields_by_name={"Yes": {"rendered_percent": 100}}),
        },
    }
    card_pair, _ = resolve_card_from_markets(
        {
            "id": "vp1",
            "kind": "versus",
            "topic": "World",
            "emoji": "A",
            "prompt": "Compare pair",
            "short": "Pair",
            "context": "C",
            "options": [
                {"market_id": 9001, "outcome_name": "Yes", "label": "Left side", "short": "Left", "emoji": "L"},
                {"market_id": 9001, "outcome_name": "No", "label": "Right side", "short": "Right", "emoji": "R"},
            ],
        },
        pair_details,
        now,
        day_seed="2026-11-27",
    )
    assert card_pair["options"][0]["percent"] == 19
    assert card_pair["options"][1]["percent"] == 81

    # Fallback when rendered_percent is None must match graded_card.rendered_percent(0.565) == 57.
    card_fb, _ = resolve_card_from_markets(
        {
            "id": "fb1",
            "kind": "chance",
            "topic": "World",
            "emoji": "B",
            "extras": ["1", "2"],
            "prompt": "Fallback pct",
            "short": "Fallback",
            "context": "C",
            "roastHigh": "{n} too high",
            "roastLow": "{n} too low",
            "source": {"market_id": 9002, "outcome_name": "Yes"},
        },
        pair_details,
        now,
        day_seed="2026-11-27",
    )
    assert card_fb["answer"] == 57

    for extreme_mid in (9003, 9004):
        assert (
            resolve_card_from_markets(
                {
                    "id": f"ex{extreme_mid}",
                    "kind": "chance",
                    "topic": "World",
                    "emoji": "C",
                    "extras": ["1", "2"],
                    "prompt": "Extreme pct",
                    "short": "Extreme",
                    "context": "C",
                    "roastHigh": "{n} too high",
                    "roastLow": "{n} too low",
                    "source": {"market_id": extreme_mid, "outcome_name": "Yes"},
                },
                pair_details,
                now,
                day_seed="2026-11-27",
            )
            is None
        )


def test_pack_invariants_gaps_coin_roasts_and_slots_match_guess_pack_contract():
    sched = _fixture_schedule()
    details = _baseline_details()
    now = datetime(2026, 11, 27, 16, 0, tzinfo=timezone.utc)
    pack, provenance = build_daily_pack(date(2026, 11, 27), sched["days"]["2026-11-27"], details, now)

    assert len(pack["cards"]) == 15
    assert all(p["representation"] == "verified_title" for p in provenance)
    cards = pack["cards"]

    # Step 0: Easy sides (both <50 and >50, SIDE_GAP) & non-adjacent versus (VERSUS_GAP).
    sides = [c for c in cards[:5] if c["kind"] == "side"]
    assert len(sides) >= 2 and {full_guess(c) for c in sides} == {0, 1}
    for s in sides:
        assert abs(s["answer"] - 50) >= SIDE_GAP
    versus_cards = [c for c in cards[:5] if c["kind"] == "versus"]
    assert len({full_guess(c) for c in versus_cards}) == len(versus_cards)
    for v in versus_cards:
        assert abs(v["options"][0]["percent"] - v["options"][1]["percent"]) >= VERSUS_GAP
    assert not any(a["ours"] and b["ours"] for a, b in zip(cards, cards[1:]))

    # Step 1: Medium four (OPTION_GAP, exact scheduled slot, unique slots) & leader (LEAD_GAP, sum <= 100).
    fours = [c for c in cards[5:10] if c["kind"] == "four"]
    assert [full_guess(c) for c in fours] == [1, 2]
    for fcard in fours:
        opts = fcard["options"]
        assert len(opts) == 4 and opts == sorted(opts)
        assert all(1 <= x <= 99 for x in opts)
        assert all(b - a >= OPTION_GAP for a, b in zip(opts, opts[1:]))
    leaders = [c for c in cards[5:10] if c["kind"] == "leader"]
    assert len({full_guess(c) for c in leaders}) == len(leaders)
    for lcard in leaders:
        pcts = sorted((o["percent"] for o in lcard["options"]), reverse=True)
        assert pcts[0] - pcts[1] >= LEAD_GAP
        assert sum(pcts) <= 100

    # Step 2: Hard chance (off-middle >= 5, low/high roasts pruned when unearnable).
    by_id = {c["id"]: c for c in cards[10:]}
    assert "roastLow" not in by_id["h2"] and "roastHigh" in by_id["h2"]  # 4% drops roastLow
    assert "roastHigh" not in by_id["h3"] and "roastLow" in by_id["h3"]  # 85% drops roastHigh
    for hcard in cards[10:]:
        assert abs(hcard["answer"] - 50) >= CHANCE_MID_GAP
        assert bool(hcard.get("roastHigh")) == (hcard["answer"] + EARNED_MISS <= 100)
        assert bool(hcard.get("roastLow")) == (hcard["answer"] - EARNED_MISS >= 0)

    # Ordinary coin rule: 2-3/5 on step 0, exact 1/5 on step 1, None on step 2.
    taps = pack["coinTaps"]
    assert sum(1 for i in range(5) if taps[i] == full_guess(cards[i])) in (2, 3)
    assert sum(1 for i in range(5, 10) if taps[i] == full_guess(cards[i])) == 1
    assert taps[10:] == [None, None, None, None, None]


@pytest.mark.asyncio
async def test_load_site_market_details_uses_verified_title_and_ignores_404(monkeypatch):
    import app.routes.futures as futures_routes

    seen_calls = []

    async def _fake_get_futures_market(*, market_id: int, db, representation: str):
        seen_calls.append((market_id, representation))
        if market_id == 999:
            raise HTTPException(status_code=404, detail="Market not found")
        return _make_detail(market_id, [("Yes", 0.58)], representation=representation)

    monkeypatch.setattr(futures_routes, "get_futures_market", _fake_get_futures_market)
    result = await load_site_market_details(db=None, market_ids=[101, 999, 101])
    assert seen_calls == [(101, "verified_title"), (999, "verified_title")]
    assert list(result.keys()) == [101]
    assert result[101]["representation"] == "verified_title"


@pytest.mark.asyncio
async def test_pt_daily_freeze_historical_day_and_expired_day(guess_test_env):
    client, db, details, sched, clock = guess_test_env

    # Yesterday was frozen; today fetches today cleanly.
    today_res = await client.get("/api/guess/today")
    assert today_res.status_code == 200
    data = today_res.json()
    assert data["day"] == "2026-11-27"
    assert data["today_day"] == "2026-11-27"
    assert data["is_today"] is True
    assert data["edition_code"] == edition_code_for_day(date(2026, 11, 27))
    assert data["pack"]["cards"][0]["answer"] == 14

    # Subsequent site move does NOT alter the frozen morning pack.
    details[1001]["outcomes"][0]["probability"] = 0.89
    assert (await client.get("/api/guess/today")).json()["pack"]["cards"][0]["answer"] == 14

    # Historical day inside 30d returns its stored edition with is_today=False.
    pack_26, _ = build_daily_pack(
        date(2026, 11, 26), sched["days"]["2026-11-26"], _baseline_details(), datetime(2026, 11, 26, 16, 0, tzinfo=timezone.utc)
    )
    db.add(
        GuessDailyEdition(
            day_pt=date(2026, 11, 26),
            edition_code=edition_code_for_day(date(2026, 11, 26)),
            frozen_at=datetime(2026, 11, 26, 16, 0, tzinfo=timezone.utc),
            pack_json=pack_26,
            source_snapshot=[],
        )
    )
    db.commit()

    hist = await client.get("/api/guess/today?day=2026-11-26")
    assert hist.status_code == 200
    assert hist.json()["day"] == "2026-11-26"
    assert hist.json()["today_day"] == "2026-11-27"
    assert hist.json()["is_today"] is False

    # Swept (>30d) or missing past day returns 404.
    assert (await client.get("/api/guess/today?day=2026-10-01")).status_code == 404
    assert (await client.get("/api/guess/today?day=2026-11-20")).status_code == 404


def test_stale_withheld_out_of_slot_and_over100_leader_swap_to_spare_or_fail():
    sched = _fixture_schedule()
    now = datetime(2026, 11, 27, 16, 0, tzinfo=timezone.utc)

    # Rejects site-withheld probability (None), unsupported source_mark, title-stale, past resolution, bad slot, sum > 100 leader.
    details = _baseline_details()
    details[1001]["outcomes"][0]["source_mark"] = {"state": "unsupported"}  # e1 -> se1 (side low 22%)
    details[1007]["outcomes"][0]["probability"] = None  # e5 (withheld by get_futures_market) -> se2
    details[1009]["outcomes"][0]["probability"] = 0.92  # m2 needs slot 1 (impossible with max=99, 92+20>99) -> sm1
    details[1008]["outcomes"] = [  # non-independent sum = 135 > 100 -> rejected -> swaps to sm2 (independent=True)
        {"id": 1, "name": "North", "probability": 0.45, "is_winner": False, "is_out": False, "kalshi_no_bid": False, "source_mark": {"state": "verified"}, "last_updated": "2026-11-27T15:00:00+00:00"},
        {"id": 2, "name": "South", "probability": 0.35, "is_winner": False, "is_out": False, "kalshi_no_bid": False, "source_mark": {"state": "verified"}, "last_updated": "2026-11-27T15:00:00+00:00"},
        {"id": 3, "name": "West", "probability": 0.30, "is_winner": False, "is_out": False, "kalshi_no_bid": False, "source_mark": {"state": "verified"}, "last_updated": "2026-11-27T15:00:00+00:00"},
        {"id": 4, "name": "Coastal", "probability": 0.25, "is_winner": False, "is_out": False, "kalshi_no_bid": False, "source_mark": {"state": "verified"}, "last_updated": "2026-11-27T15:00:00+00:00"},
    ]
    details[1014]["name"] = "Eurovision winner"  # title-stale recurring calendar -> h2 -> sh1

    pack, provenance = build_daily_pack(date(2026, 11, 27), sched["days"]["2026-11-27"], details, now)
    ids = [c["id"] for c in pack["cards"]]
    assert ids[0] == "se1" and ids[4] == "se2"
    assert "sm1" in ids and "sm2" in ids
    assert ids[11] == "sh1"
    swapped_slots = {p.get("swapped_from_slot") for p in provenance if p.get("swapped_from_slot")}
    assert swapped_slots == {"e1", "e5", "m1", "m2", "h2"}

    # Verify kalshi_no_bid, rendered_percent <1%, and >110 char roast reject a card cleanly.
    bad_no_bid = _baseline_details()
    bad_no_bid[1001]["outcomes"][0]["kalshi_no_bid"] = True
    assert resolve_card_from_markets(sched["days"]["2026-11-27"]["step_cards"]["easy"][0], bad_no_bid, now, day_seed="2026-11-27") is None

    bad_lt1 = _baseline_details()
    bad_lt1[1001]["outcomes"][0]["rendered_percent"] = "<1%"
    assert resolve_card_from_markets(sched["days"]["2026-11-27"]["step_cards"]["easy"][0], bad_lt1, now, day_seed="2026-11-27") is None

    long_roast_tmpl = dict(sched["days"]["2026-11-27"]["step_cards"]["hard"][0], roastHigh="x" * 111)
    assert resolve_card_from_markets(long_roast_tmpl, _baseline_details(), now, day_seed="2026-11-27") is None


@pytest.mark.asyncio
async def test_server_scoring_group_isolation_and_no_ip_hash_logged(guess_test_env, caplog):
    client, _db, _details, _sched, _clock = guess_test_env
    caplog.set_level(logging.DEBUG)

    assert (await client.get("/api/guess/groups")).status_code in (404, 405)
    pack = (await client.get("/api/guess/today")).json()["pack"]
    win = _winning_answers_for_pack(pack)

    for bad_key in ("score", "points", "user_id", "device_id"):
        rejected = await client.post(
            "/api/guess/groups/alpha12345/entries",
            json={"day": "2026-11-27", "nickname": "Bad", "answers": win, "step_times": [10, 12, 15], bad_key: 1},
        )
        assert rejected.status_code == 422

    fake_ip = "203.0.113.77"
    active_salt = await guess_routes._get_daily_rate_limit_salt(int(time.time()))
    expected_hash = hashlib.sha256(f"{active_salt}:{fake_ip}".encode("utf-8")).hexdigest()[:24]
    expected_total = sum(points_for(card, g) for card, g in zip(pack["cards"], win, strict=True))
    res1 = await client.post(
        "/api/guess/groups/alpha12345/entries",
        json={"day": "2026-11-27", "nickname": "  Alex  ", "answers": win, "step_times": [10, 12, 15]},
        headers={"X-Forwarded-For": fake_ip},
    )
    assert res1.status_code == 201
    assert res1.json()["entries"][0]["points"] == expected_total
    assert fake_ip not in caplog.text
    assert active_salt not in caplog.text
    assert expected_hash not in caplog.text

    # Idempotent replay -> 200; colliding answers for same nickname -> 409; Group B isolated.
    replay = await client.post(
        "/api/guess/groups/alpha12345/entries",
        json={"day": "2026-11-27", "nickname": "alex", "answers": win, "step_times": [10, 12, 15]},
    )
    assert replay.status_code == 200
    collision = await client.post(
        "/api/guess/groups/alpha12345/entries",
        json={"day": "2026-11-27", "nickname": "ALEX", "answers": [0 if x != 0 else 1 for x in win], "step_times": [9, 9, 9]},
    )
    assert collision.status_code == 409
    assert (await client.get("/api/guess/groups/bravo67890")).json()["entries"] == []


@pytest.mark.asyncio
async def test_anti_flood_client_burst_group_burst_30_cap_and_503(guess_test_env):
    client, db, details, _sched, clock = guess_test_env
    pack = (await client.get("/api/guess/today")).json()["pack"]
    win = _winning_answers_for_pack(pack)

    # Spoofed first X-Forwarded-For hop still hits the router peer's single bucket (203.0.113.9).
    for i in range(8):
        resp = await client.post(
            "/api/guess/groups/burstgrp01/entries",
            json={"day": "2026-11-27", "nickname": f"P{i}", "answers": win, "step_times": [5, 5, 5]},
            headers={"X-Forwarded-For": f"198.51.100.{i + 50}, 203.0.113.9"},
        )
        assert resp.status_code == 201
    assert (
        await client.post(
            "/api/guess/groups/burstgrp01/entries",
            json={"day": "2026-11-27", "nickname": "P99", "answers": win, "step_times": [5, 5, 5]},
            headers={"X-Forwarded-For": "198.51.100.244, 203.0.113.9"},
        )
    ).status_code == 429

    for i in range(12):
        resp = await client.post(
            "/api/guess/groups/burstgrp01/entries",
            json={"day": "2026-11-27", "nickname": f"Q{i}", "answers": win, "step_times": [5, 5, 5]},
            headers={"X-Forwarded-For": f"203.0.113.9, 198.51.100.{i + 10}"},
        )
        assert resp.status_code == 201
    assert (
        await client.post(
            "/api/guess/groups/burstgrp01/entries",
            json={"day": "2026-11-27", "nickname": "Q99", "answers": win, "step_times": [5, 5, 5]},
            headers={"X-Forwarded-For": "198.51.100.250"},
        )
    ).status_code == 429

    guess_routes._reset_rate_limits_for_tests()
    for i in range(30):
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
    assert MAX_GROUP_ENTRIES == 30
    assert (
        await client.post(
            "/api/guess/groups/capgrp0001/entries",
            json={"day": "2026-11-27", "nickname": "Seed30", "answers": win, "step_times": [10, 10, 10]},
            headers={"X-Forwarded-For": "192.0.2.30"},
        )
    ).status_code == 429

    # Day with all markets closed fails closed with 503 (never fabricated).
    clock["now"] = datetime(2026, 11, 28, 16, 30, tzinfo=timezone.utc)
    for d in details.values():
        d["status"] = "closed"
    assert (await client.get("/api/guess/today")).status_code == 503


@pytest.mark.asyncio
async def test_30_day_retention_sweep_and_beat_task(guess_test_env, monkeypatch):
    _client, db, details, sched, _clock = guess_test_env
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
        yield _SyncAsyncSession(db)

    monkeypatch.setattr(guess_task, "get_task_session", _fake_task_session)
    monkeypatch.setattr(guess_task, "load_daily_schedule", lambda: sched, raising=False)

    from app.utils import guess_daily as gd_mod

    orig_freeze = gd_mod.get_or_freeze_daily_edition
    monkeypatch.setattr(
        guess_task,
        "get_or_freeze_daily_edition",
        lambda s, d_arg=None, *, now_utc=None: orig_freeze(
            s, d_arg, now_utc=now_utc, schedule=sched, market_details=details
        ),
    )

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


class _FakeSharedRedis:
    def __init__(self):
        self.kv: dict[str, str] = {}

    async def get(self, key: str):
        return self.kv.get(key)

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None):
        if nx and key in self.kv:
            return False
        self.kv[key] = str(value)
        return True

    async def incr(self, key: str) -> int:
        val = int(self.kv.get(key, "0")) + 1
        self.kv[key] = str(val)
        return val

    async def expire(self, key: str, ttl: int) -> bool:
        return True


@pytest.mark.asyncio
async def test_shared_redis_salt_across_processes_and_daily_rotation(guess_test_env, monkeypatch, caplog):
    client, _db, _details, _sched, _clock = guess_test_env
    caplog.set_level(logging.INFO)
    shared = _FakeSharedRedis()
    monkeypatch.setattr(guess_routes, "_get_async_rl_redis", lambda: shared)

    pack = (await client.get("/api/guess/today")).json()["pack"]
    win = _winning_answers_for_pack(pack)

    day1_ts = int(datetime(2026, 11, 27, 16, 0, tzinfo=timezone.utc).timestamp())
    day2_ts = int(datetime(2026, 11, 28, 16, 0, tzinfo=timezone.utc).timestamp())
    monkeypatch.setattr(guess_routes.time, "time", lambda: day1_ts)

    salt_p1 = await guess_routes._get_daily_rate_limit_salt(day1_ts)
    # Simulate a second worker process starting with an empty process cache.
    guess_routes._CACHED_SALT = ("", "", False)
    salt_p2 = await guess_routes._get_daily_rate_limit_salt(day1_ts)
    assert salt_p1 == salt_p2

    for i in range(8):
        if i % 2 == 1:
            guess_routes._CACHED_SALT = ("", "", False)
        r = await client.post(
            "/api/guess/groups/sharedsalt1/entries",
            json={"day": "2026-11-27", "nickname": f"S{i}", "answers": win, "step_times": [5, 5, 5]},
            headers={"X-Forwarded-For": f"10.0.0.{i + 1}, 203.0.113.44"},
        )
        assert r.status_code == 201

    guess_routes._CACHED_SALT = ("", "", False)
    blocked = await client.post(
        "/api/guess/groups/sharedsalt1/entries",
        json={"day": "2026-11-27", "nickname": "S99", "answers": win, "step_times": [5, 5, 5]},
        headers={"X-Forwarded-For": "10.0.0.99, 203.0.113.44"},
    )
    assert blocked.status_code == 429

    salt_next_day = await guess_routes._get_daily_rate_limit_salt(day2_ts)
    assert salt_next_day != salt_p1
    assert "203.0.113.44" not in caplog.text
    assert salt_p1 not in caplog.text
    assert salt_next_day not in caplog.text


@pytest.mark.asyncio
async def test_daily_entry_ceiling_returns_429_and_logs_once_per_day(guess_test_env, monkeypatch, caplog):
    client, _db, _details, _sched, _clock = guess_test_env
    caplog.set_level(logging.ERROR)
    assert MAX_DAILY_ENTRIES == 10_000
    monkeypatch.setattr(guess_routes, "MAX_DAILY_ENTRIES", 3)

    pack = (await client.get("/api/guess/today")).json()["pack"]
    win = _winning_answers_for_pack(pack)

    for idx in range(3):
        res = await client.post(
            f"/api/guess/groups/dailygrp0{idx}/entries",
            json={"day": "2026-11-27", "nickname": f"User{idx}", "answers": win, "step_times": [7, 8, 9]},
            headers={"X-Forwarded-For": f"192.0.2.{idx + 1}"},
        )
        assert res.status_code == 201

    # 4th finished game across another group triggers the daily ceiling and logs once.
    capped1 = await client.post(
        "/api/guess/groups/dailygrp99/entries",
        json={"day": "2026-11-27", "nickname": "Fourth", "answers": win, "step_times": [7, 8, 9]},
        headers={"X-Forwarded-For": "192.0.2.99"},
    )
    assert capped1.status_code == 429
    assert "full right now" in capped1.json()["detail"].lower()

    # 5th refusal emits 429 without duplicating the error log; idempotent replay stays 200.
    capped2 = await client.post(
        "/api/guess/groups/dailygrp98/entries",
        json={"day": "2026-11-27", "nickname": "Fifth", "answers": win, "step_times": [7, 8, 9]},
        headers={"X-Forwarded-For": "192.0.2.98"},
    )
    assert capped2.status_code == 429
    err_logs = [rec for rec in caplog.records if "daily entry ceiling" in rec.message.lower()]
    assert len(err_logs) == 1
    assert "192.0.2." not in caplog.text

    replay = await client.post(
        "/api/guess/groups/dailygrp00/entries",
        json={"day": "2026-11-27", "nickname": "User0", "answers": win, "step_times": [7, 8, 9]},
        headers={"X-Forwarded-For": "192.0.2.1"},
    )
    assert replay.status_code == 200


def test_stale_24h_last_updated_guards_primaries_spares_multi_outcome_and_missing():
    """Fable 11:56 AM PT (#12619) staleness guard: >24h or missing/unreadable last_updated is refused."""
    from app.utils.guess_daily import GuessEditionUnavailableError, MAX_OUTCOME_AGE

    assert MAX_OUTCOME_AGE == timedelta(hours=24)
    sched = _fixture_schedule()
    day_sched = sched["days"]["2026-11-27"]
    freeze_at = datetime(2026, 11, 27, 16, 0, tzinfo=timezone.utc)
    fresh_23h = (freeze_at - timedelta(hours=23)).isoformat()
    boundary_24h = (freeze_at - timedelta(hours=24)).isoformat()
    stale_24h1s = (freeze_at - timedelta(hours=24, seconds=1)).isoformat()
    stale_25h = (freeze_at - timedelta(hours=25)).isoformat()

    # 1. Primary 23h and exact 24h00m00s old are kept; 25h and 24h00m01s swap to spare with swapped_reason.
    for kept_ts in (fresh_23h, boundary_24h):
        details_kept = _baseline_details()
        details_kept[1001]["outcomes"][0]["last_updated"] = kept_ts
        pack_kept, prov_kept = build_daily_pack(date(2026, 11, 27), day_sched, details_kept, freeze_at)
        assert pack_kept["cards"][0]["id"] == "e1"
        assert prov_kept[0]["last_updated"] == kept_ts

    for stale_ts in (stale_25h, stale_24h1s):
        details_stale = _baseline_details()
        details_stale[1001]["outcomes"][0]["last_updated"] = stale_ts
        pack_swapped, prov_swapped = build_daily_pack(date(2026, 11, 27), day_sched, details_stale, freeze_at)
        assert pack_swapped["cards"][0]["id"] == "se1"
        se1_prov = [p for p in prov_swapped if p["card_id"] == "se1"]
        assert len(se1_prov) == 1
        assert se1_prov[0]["swapped_from_slot"] == "e1"
        assert se1_prov[0]["swapped_reason"].startswith("stale_last_updated:1001:")

    # 2. Stale spare (25h) is skipped for the next fresh spare; if no fresh spare remains, freeze fails cleanly.
    details_spare_skip = _baseline_details()
    details_spare_skip[1007]["outcomes"][0]["last_updated"] = stale_25h  # e5 (>50) stale -> se1 needed
    details_spare_skip[1020]["outcomes"][0]["last_updated"] = stale_25h  # se1 also stale -> must skip to se2 (>50)
    pack_skip, prov_skip = build_daily_pack(date(2026, 11, 27), day_sched, details_spare_skip, freeze_at)
    assert pack_skip["cards"][4]["id"] == "se2"
    se2_prov = next(p for p in prov_skip if p["card_id"] == "se2")
    assert se2_prov["swapped_from_slot"] == "e5"
    assert se2_prov["swapped_reason"].startswith("stale_last_updated:1007:")

    details_spare_exhausted = _baseline_details()
    details_spare_exhausted[1001]["outcomes"][0]["last_updated"] = stale_25h
    details_spare_exhausted[1020]["outcomes"][0]["last_updated"] = stale_25h
    details_spare_exhausted[1021]["outcomes"][0]["last_updated"] = stale_25h
    with pytest.raises(GuessEditionUnavailableError):
        build_daily_pack(date(2026, 11, 27), day_sched, details_spare_exhausted, freeze_at)

    # 3. Multi-outcome & multi-market cards (versus, four, leader) are refused when ANY printed outcome is >24h old.
    versus_tmpl = day_sched["step_cards"]["easy"][1]  # e2 uses 1002 & 1003
    details_v_bad = _baseline_details()
    details_v_bad[1003]["outcomes"][0]["last_updated"] = stale_25h  # 2nd leg stale, 1st leg fresh
    reasons_v: list[str] = []
    assert resolve_card_from_markets(versus_tmpl, details_v_bad, freeze_at, day_seed="2026-11-27", refusal_reasons_out=reasons_v) is None
    assert any(r.startswith("stale_last_updated:1003:") for r in reasons_v), reasons_v

    four_tmpl = day_sched["step_cards"]["medium"][1]  # m2 uses 1009
    details_f_bad = _baseline_details()
    details_f_bad[1009]["outcomes"][0]["last_updated"] = stale_25h
    reasons_f: list[str] = []
    assert resolve_card_from_markets(four_tmpl, details_f_bad, freeze_at, day_seed="2026-11-27", refusal_reasons_out=reasons_f) is None
    assert any(r.startswith("stale_last_updated:1009:") for r in reasons_f), reasons_f

    leader_tmpl = day_sched["step_cards"]["medium"][0]  # m1 uses 1008 with 4 outcomes
    details_l_bad = _baseline_details()
    details_l_bad[1008]["outcomes"][2]["last_updated"] = stale_25h  # 3rd of 4 outcomes stale
    reasons_l: list[str] = []
    assert resolve_card_from_markets(leader_tmpl, details_l_bad, freeze_at, day_seed="2026-11-27", refusal_reasons_out=reasons_l) is None
    assert any(r.startswith("stale_last_updated:1008:") for r in reasons_l), reasons_l

    # 4. Missing, empty, or unreadable last_updated is refused, never treated as fresh.
    side_tmpl = day_sched["step_cards"]["easy"][0]
    for bad_stamp in (None, "", "not-a-timestamp", "2026/13/45"):
        details_missing = _baseline_details()
        details_missing[1001]["outcomes"][0]["last_updated"] = bad_stamp
        reasons_m: list[str] = []
        assert (
            resolve_card_from_markets(
                side_tmpl, details_missing, freeze_at, day_seed="2026-11-27", refusal_reasons_out=reasons_m
            )
            is None
        ), bad_stamp
        assert any(r.startswith("missing_or_invalid_last_updated:1001:") for r in reasons_m), (bad_stamp, reasons_m)

    # Full pack swap check when missing/unreadable last_updated hits primary h1 (chance card) -> swaps to sh1.
    details_chance_missing = _baseline_details()
    details_chance_missing[1013]["outcomes"][0]["last_updated"] = None
    pack_cm, prov_cm = build_daily_pack(date(2026, 11, 27), day_sched, details_chance_missing, freeze_at)
    sh1_prov = next(p for p in prov_cm if p["card_id"] == "sh1")
    assert pack_cm["cards"][10]["id"] == "sh1"
    assert sh1_prov["swapped_from_slot"] == "h1"
    assert sh1_prov["swapped_reason"].startswith("missing_or_invalid_last_updated:1013:")
