"""Tests for #12619 (446: B) public /guess board, nickname rules, admin hiding, 60s cache, and parity."""

from __future__ import annotations

import contextlib
import copy
import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models.models import GuessDailyEdition, GuessGroupEntry
from app.routes import guess as guess_routes
from app.services.database import get_db_rw
from app.utils import guess_daily as gd_mod
from app.utils.guess_daily import (
    GuessEditionUnavailableError,
    GuessEditionUnscheduledError,
    build_daily_pack,
    full_guess,
    full_points,
    is_valid_guess,
    points_for,
    score_step_labels,
    today_pt,
    validate_nickname,
)

PARITY_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "guess" / "scoring_parity_cases.json"
)


def _detail(market_id: int, outcomes: list[tuple[str, float]], *, stamp: str = "2026-11-27T15:00:00+00:00") -> dict:
    return {
        "id": market_id,
        "name": f"Market {market_id}",
        "status": "open",
        "representation": "verified_title",
        "resolution_date": None,
        "llm_sport_category": None,
        "outcomes": [
            {
                "id": market_id * 100 + i,
                "name": name,
                "probability": prob,
                "status": "open",
                "is_winner": False,
                "is_out": False,
                "kalshi_no_bid": False,
                "rendered_percent": None,
                "source_mark": {"state": "verified"},
                "last_updated": stamp,
            }
            for i, (name, prob) in enumerate(outcomes)
        ],
    }


def _fixture_schedule_446() -> dict:
    return {
        "version": 1,
        "days": {
            "2026-11-28": {
                "steps": [
                    {"name": "Easy", "how": "Above or below 50%? Which is more likely? One tap each."},
                    {"name": "Medium", "how": "Pick one of four."},
                    {"name": "Hard", "how": "Slide to the number. Closest wins."},
                ],
                "topics": ["Sports", "Money & Tech", "World & Culture"],
                "step_cards": {
                    "easy": [
                        {"id": "e1", "kind": "side", "topic": "Sports", "emoji": "🏆", "extras": ["A", "B"], "prompt": "E1?", "short": "E1", "context": "c", "source": {"market_id": 1001, "outcome_name": "Yes"}},
                        {"id": "e2", "kind": "versus", "topic": "Money & Tech", "emoji": "💡", "prompt": "E2?", "short": "E2", "context": "c", "options": [{"label": "Opt A", "short": "Opt A", "emoji": "💡", "market_id": 1002, "outcome_name": "Yes"}, {"label": "Opt B", "short": "Opt B", "emoji": "⚡", "market_id": 1003, "outcome_name": "Yes"}]},
                        {"id": "e3", "kind": "side", "topic": "World & Culture", "emoji": "🎬", "extras": ["A", "B"], "prompt": "E3?", "short": "E3", "context": "c", "source": {"market_id": 1004, "outcome_name": "Yes"}},
                        {"id": "e4", "kind": "versus", "topic": "Sports", "emoji": "⚽", "prompt": "E4?", "short": "E4", "context": "c", "options": [{"label": "Team X", "short": "Team X", "emoji": "⚽", "market_id": 1005, "outcome_name": "Yes"}, {"label": "Team Y", "short": "Team Y", "emoji": "🥅", "market_id": 1006, "outcome_name": "Yes"}]},
                        {"id": "e5", "kind": "side", "topic": "Money & Tech", "emoji": "🔋", "extras": ["A", "B"], "prompt": "E5?", "short": "E5", "context": "c", "source": {"market_id": 1007, "outcome_name": "Yes"}},
                    ],
                    "medium": [
                        {"id": "m1", "kind": "four", "topic": "Sports", "emoji": "🏀", "extras": ["A", "B"], "prompt": "M1?", "short": "M1", "context": "c", "source": {"market_id": 1008, "outcome_name": "Yes"}, "answer_slot": 0},
                        {"id": "m2", "kind": "leader", "topic": "World & Culture", "emoji": "🎭", "independent": False, "market_id": 1009, "prompt": "M2?", "short": "M2", "context": "c", "options": [{"label": "C1", "short": "C1", "emoji": "🎭", "outcome_name": "C1"}, {"label": "C2", "short": "C2", "emoji": "🎨", "outcome_name": "C2"}, {"label": "C3", "short": "C3", "emoji": "🎬", "outcome_name": "C3"}, {"label": "C4", "short": "C4", "emoji": "🎵", "outcome_name": "C4"}]},
                        {"id": "m3", "kind": "four", "topic": "Money & Tech", "emoji": "🚀", "extras": ["A", "B"], "prompt": "M3?", "short": "M3", "context": "c", "source": {"market_id": 1010, "outcome_name": "Yes"}, "answer_slot": 1},
                        {"id": "m4", "kind": "leader", "topic": "Sports", "emoji": "🏈", "independent": False, "market_id": 1011, "prompt": "M4?", "short": "M4", "context": "c", "options": [{"label": "T1", "short": "T1", "emoji": "🏈", "outcome_name": "T1"}, {"label": "T2", "short": "T2", "emoji": "⚽", "outcome_name": "T2"}, {"label": "T3", "short": "T3", "emoji": "🏀", "outcome_name": "T3"}, {"label": "T4", "short": "T4", "emoji": "⚾", "outcome_name": "T4"}]},
                        {"id": "m5", "kind": "four", "topic": "World & Culture", "emoji": "🌦️", "extras": ["A", "B"], "prompt": "M5?", "short": "M5", "context": "c", "source": {"market_id": 1012, "outcome_name": "Yes"}, "answer_slot": 2},
                    ],
                    "hard": [
                        {"id": "h1", "kind": "chance", "topic": "Sports", "emoji": "🥇", "extras": ["A", "B"], "prompt": "H1?", "short": "H1", "context": "c", "roastHigh": "{n} high {g} vs {w}.", "roastLow": "{n} low {g} vs {w}.", "source": {"market_id": 1013, "outcome_name": "Yes"}},
                        {"id": "h2", "kind": "chance", "topic": "World & Culture", "emoji": "🎵", "extras": ["A", "B"], "prompt": "H2?", "short": "H2", "context": "c", "roastHigh": "{n} high {g} vs {w}.", "roastLow": "{n} low {g} vs {w}.", "source": {"market_id": 1014, "outcome_name": "Yes"}},
                        {"id": "h3", "kind": "chance", "topic": "Money & Tech", "emoji": "🏛️", "extras": ["A", "B"], "prompt": "H3?", "short": "H3", "context": "c", "roastHigh": "{n} high {g} vs {w}.", "roastLow": "{n} low {g} vs {w}.", "source": {"market_id": 1015, "outcome_name": "Yes"}},
                        {"id": "h4", "kind": "chance", "topic": "World & Culture", "emoji": "🌍", "extras": ["A", "B"], "prompt": "H4?", "short": "H4", "context": "c", "roastHigh": "{n} high {g} vs {w}.", "roastLow": "{n} low {g} vs {w}.", "source": {"market_id": 1016, "outcome_name": "Yes"}},
                        {"id": "h5", "kind": "chance", "topic": "Sports", "emoji": "🎾", "extras": ["A", "B"], "prompt": "H5?", "short": "H5", "context": "c", "roastHigh": "{n} high {g} vs {w}.", "roastLow": "{n} low {g} vs {w}.", "source": {"market_id": 1017, "outcome_name": "Yes"}},
                    ],
                },
                "spares": {
                    "easy": [
                        {"id": "se1", "kind": "side", "topic": "Sports", "emoji": "🏟️", "extras": ["A", "B"], "prompt": "SE1?", "short": "SE1", "context": "c", "source": {"market_id": 1020, "outcome_name": "Yes"}},
                        {"id": "se2", "kind": "side", "topic": "World & Culture", "emoji": "📖", "extras": ["A", "B"], "prompt": "SE2?", "short": "SE2", "context": "c", "source": {"market_id": 1021, "outcome_name": "Yes"}},
                    ],
                    "medium": [],
                    "hard": [],
                },
            }
        },
    }


def _baseline_details_446() -> dict[int, dict]:
    return {
        1001: _detail(1001, [("Yes", 0.31)]),
        1002: _detail(1002, [("Yes", 0.22)]),
        1003: _detail(1003, [("Yes", 0.61)]),
        1004: _detail(1004, [("Yes", 0.72)]),
        1005: _detail(1005, [("Yes", 0.64)]),
        1006: _detail(1006, [("Yes", 0.29)]),
        1007: _detail(1007, [("Yes", 0.33)]),
        1008: _detail(1008, [("Yes", 0.18)]),
        1009: _detail(1009, [("C1", 0.45), ("C2", 0.25), ("C3", 0.18), ("C4", 0.12)]),
        1010: _detail(1010, [("Yes", 0.41)]),
        1011: _detail(1011, [("T1", 0.12), ("T2", 0.20), ("T3", 0.46), ("T4", 0.22)]),
        1012: _detail(1012, [("Yes", 0.67)]),
        1013: _detail(1013, [("Yes", 0.34)]),
        1014: _detail(1014, [("Yes", 0.12)]),
        1015: _detail(1015, [("Yes", 0.88)]),
        1016: _detail(1016, [("Yes", 0.62)]),
        1017: _detail(1017, [("Yes", 0.41)]),
        # Spare 1: low side (Sports)
        1020: _detail(1020, [("Yes", 0.24)]),
        # Spare 2: high side (World & Culture)
        1021: _detail(1021, [("Yes", 0.78)]),
    }


class _CountingSyncAsyncSession:
    def __init__(self, session):
        self._session = session
        self.read_queries = 0

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
        self.read_queries += 1
        return self._session.execute(statement, params or {})

    async def scalar(self, statement):
        self.read_queries += 1
        return self._session.scalar(statement)

    async def scalars(self, statement):
        self.read_queries += 1
        return self._session.scalars(statement)


def _contains_forbidden_group_code(obj, forbidden_codes: set[str]) -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "group_code":
                hits.append("key:group_code")
            if isinstance(v, str) and v in forbidden_codes:
                hits.append(f"val:{v}")
            hits.extend(_contains_forbidden_group_code(v, forbidden_codes))
    elif isinstance(obj, list):
        for item in obj:
            hits.extend(_contains_forbidden_group_code(item, forbidden_codes))
    return hits


@pytest.fixture
async def public_board_env(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    GuessDailyEdition.__table__.create(engine)
    GuessGroupEntry.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()
    counter = _CountingSyncAsyncSession(db_session)
    details_store = _baseline_details_446()
    sched_store = _fixture_schedule_446()
    guess_routes._reset_rate_limits_for_tests()

    clock = {"now": datetime(2026, 11, 28, 16, 30, tzinfo=timezone.utc)}
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
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-secret-446b")

    async def _override_rw():
        yield counter

    app.dependency_overrides[get_db_rw] = _override_rw

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, db_session, counter, details_store, sched_store, clock

    app.dependency_overrides.clear()
    guess_routes._reset_rate_limits_for_tests()
    db_session.close()
    engine.dispose()


def test_shared_scoring_parity_fixture():
    data = json.loads(PARITY_PATH.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert len(cases) >= 12
    for case in cases:
        card = case["card"]
        guess = case["guess"]
        assert is_valid_guess(card, guess) is case["valid"], case["name"]
        assert full_guess(card) == case["full_guess"], case["name"]
        assert full_points(card) == case["full_points"], case["name"]
        assert points_for(card, guess) == case["points"], case["name"]


@pytest.mark.parametrize(
    ("raw", "allowed"),
    [
        ("Alex", True),
        ("Ann 2", True),
        ("O'Connor", True),
        ("O’Connor", True),
        ("Mary-Jane", True),
        ("Sam 99", True),
        ("Cassie", True),
        ("Dickinson", True),
        ("Titus", True),
        ("Cummins", True),
        ("Alex!", False),
        ("bad_name", False),
        ("---", False),
        ("🔥Alex", False),
        ("Fuck", False),
        ("f u c k", False),
        ("sh1t", False),
        ("asshole", False),
        ("dick", False),
        ("The Coin", False),
    ],
)
def test_validate_nickname_rules_and_no_scunthorpe(raw, allowed):
    clean, err = validate_nickname(raw)
    if allowed:
        assert clean and err is None
    else:
        assert clean == "" and isinstance(err, str) and err


@pytest.mark.asyncio
async def test_refused_nickname_returns_422_with_reader_reason(public_board_env):
    client, *_ = public_board_env
    today_res = await client.get("/api/guess/today")
    assert today_res.status_code == 200
    pack = today_res.json()["pack"]
    answers = [full_guess(c) for c in pack["cards"]]

    for bad_name in ("Alex!", "bad_name", "f u c k", "sh1t"):
        res = await client.post(
            "/api/guess/groups/famcode0001/entries",
            json={
                "day": "2026-11-28",
                "nickname": bad_name,
                "answers": answers,
                "step_times": [10, 12, 15],
            },
        )
        assert res.status_code == 422
        body = res.json()
        assert body["reason"] == "nickname_refused"
        assert "another" in body["detail"].lower()


@pytest.mark.asyncio
async def test_public_board_paging_order_privacy_cache_and_admin_hide(public_board_env):
    client, db_session, counter, _, _, _ = public_board_env
    today_res = await client.get("/api/guess/today")
    pack = today_res.json()["pack"]
    best = [full_guess(c) for c in pack["cards"]]

    # Seed 14 entries across multiple groups (using distinct IP headers + groups so rate limit allows all)
    group_codes = {"alpha1111", "beta22222", "gamma3333"}
    created_ids: dict[str, int] = {}
    for idx in range(14):
        code = ("alpha1111", "beta22222", "gamma3333")[idx % 3]
        nick = "Rowdy" if idx == 5 else f"Player {idx + 1}"
        # Give distinct scores by slightly perturbing hard slider answers
        answers = list(best)
        for j in range(10, 15):
            answers[j] = max(0, min(100, best[j] + idx))
        res = await client.post(
            f"/api/guess/groups/{code}/entries",
            headers={"x-forwarded-for": f"10.0.0.{idx + 10}"},
            json={
                "day": "2026-11-28",
                "nickname": nick,
                "answers": answers,
                "step_times": [10 + idx, 12 + idx, 15 + idx],
            },
        )
        assert res.status_code == 201, res.text
        group_entries = res.json()["entries"]
        me_in_group = next(e for e in group_entries if e["nickname"] == nick)
        created_ids[nick] = me_in_group["entry_id"]

    # Page 1 (10 rows of 14), no group_code leaked, best-first order, step_labels present
    counter.read_queries = 0
    p1 = await client.get("/api/guess/board?day=2026-11-28&page=1&page_size=10")
    assert p1.status_code == 200
    assert counter.read_queries > 0
    b1 = p1.json()
    assert b1["total_count"] == 14
    assert b1["total_pages"] == 2
    assert b1["page"] == 1
    assert len(b1["entries"]) == 10
    assert b1["entries"][0]["rank"] == 1
    assert b1["entries"][0]["step_labels"] == score_step_labels(pack, best, [50, 75, 100])
    assert _contains_forbidden_group_code(b1, group_codes) == []

    # Repeat read for page 2 WITH entry_id on page 2 -> served from 60s cache with ZERO DB queries!
    counter.read_queries = 0
    p2 = await client.get(
        f"/api/guess/board?day=2026-11-28&page=2&page_size=10&entry_id={created_ids['Player 13']}"
    )
    assert p2.status_code == 200
    assert counter.read_queries == 0
    b2 = p2.json()
    assert len(b2["entries"]) == 4
    assert b2["me"]["entry_id"] == created_ids["Player 13"]
    assert b2["me"]["nickname"] == "Player 13"
    assert _contains_forbidden_group_code(b2, group_codes) == []

    # Admin hide requires header bearer auth (not missing, not ?secret=)
    rowdy_id = created_ids["Rowdy"]
    unauth = await client.post(f"/api/guess/admin/entries/{rowdy_id}/hide?secret=test-admin-secret-446b")
    assert unauth.status_code in (401, 403)

    hide_res = await client.post(
        f"/api/guess/admin/entries/{rowdy_id}/hide",
        headers={"Authorization": "Bearer test-admin-secret-446b"},
    )
    assert hide_res.status_code == 200
    assert hide_res.json()["status"] == "hidden"

    # Row stays in DB with hidden_at set (never deleted)
    db_row = db_session.scalar(select(GuessGroupEntry).where(GuessGroupEntry.id == rowdy_id))
    assert db_row is not None and db_row.hidden_at is not None

    # Hidden entry is gone from BOTH boards (and cache was invalidated!)
    grp_after = await client.get("/api/guess/groups/gamma3333?day=2026-11-28")
    assert grp_after.status_code == 200
    assert all(e["entry_id"] != rowdy_id for e in grp_after.json()["entries"])

    pub_after_1 = await client.get(
        f"/api/guess/board?day=2026-11-28&page=1&page_size=25&entry_id={rowdy_id}"
    )
    assert pub_after_1.status_code == 200
    pub_json = pub_after_1.json()
    assert pub_json["total_count"] == 13
    assert pub_json["me"] is None
    assert all(e["entry_id"] != rowdy_id for e in pub_json["entries"])


@pytest.mark.asyncio
async def test_unscheduled_day_returns_503_with_unscheduled_reason(public_board_env):
    assert issubclass(GuessEditionUnscheduledError, GuessEditionUnavailableError)
    client, _, _, _, _, clock = public_board_env
    clock["now"] = datetime(2026, 12, 15, 16, 0, tzinfo=timezone.utc)
    res = await client.get("/api/guess/today")
    assert res.status_code == 503
    body = res.json()
    assert body["reason"] == "unscheduled"
    assert body["detail"] == "No new cards today. Here is the latest set."


def test_build_daily_pack_tries_next_spare_when_first_spare_breaks_whole_day_invariants():
    sched = copy.deepcopy(_fixture_schedule_446()["days"]["2026-11-28"])
    details = copy.deepcopy(_baseline_details_446())
    # Drop primary e3 (high >50% World & Culture), making all 4 remaining Easy cards have:
    # e1 (<50, Sports), e2 (versus, Money), e4 (versus, Sports), e5 (<50, Money).
    # Topic counts at primaries-minus-e3: Sports=5, Money=5, World & Culture=4 -> wait force World & Culture to 2 if swapped wrong!
    # Also note remaining sides e1 (<50) and e5 (<50) are BOTH <50%!
    # So replacing e3 with se1 (ALSO <50%) breaks the whole-day Easy step invariant (both <50 and >50 sides required),
    # while se2 (>50% side, World & Culture) satisfies _validate_pack_invariants!
    details[1004]["outcomes"][0]["probability"] = 0.0
    details[1004]["outcomes"][0]["status"] = "settled"

    pack, provenance = build_daily_pack(
        date(2026, 11, 28),
        sched,
        details,
        datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc),
    )
    easy_ids = [c["id"] for c in pack["cards"][:5]]
    assert "se2" in easy_ids
    assert "se1" not in easy_ids
    assert len(pack["cards"]) == 15
    assert any(p.get("card_id") == "se2" and p.get("swapped_from_slot") == "e3" for p in provenance)
