"""Tests for #13511 / #13642 live save fix: ``ck_ranking_grades_grade`` bijection for ``game_nuggets``."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from httpx import ASGITransport
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.main import app
from app.models.models import RankingGrade
from app.routes import admin_ranking_eval as eval_route
from app.routes import events as events_route
from app.services import get_db, get_db_rw


def _rich_event_payloads(now: datetime) -> tuple[dict, dict, dict]:
    fresh_ts = (now - timedelta(minutes=30)).isoformat()
    gm = {
        "totals": [
            {
                "_market_id": 7001,
                "market_name": "Bengals at Commanders: Total Points O/U 48.5",
                "outcome_name": "Over",
                "over_probability": 0.64,
                "threshold": 48.5,
                "observed_at": fresh_ts,
                "source_mark": {"state": "blended"},
            }
        ],
        "spreads": [
            {
                "_market_id": 7002,
                "market_name": "Commanders vs Bengals: Spread -3.5",
                "outcome_name": "Washington Commanders",
                "probability": 0.58,
                "threshold": -3.5,
                "observed_at": fresh_ts,
                "source_mark": {"state": "blended"},
            }
        ],
        "player_props": [
            {
                "_market_id": 7003,
                "player": {"key": "jayden daniels", "name": "Jayden Daniels"},
                "player_headshot": "https://cdn.example/daniels.png",
                "player_team": "home",
                "stat": {"key": "passing_yards", "label": "Passing Yards"},
                "line": {"kind": "count_at_least", "value": 245, "label": "245+"},
                "over_probability": 0.61,
                "side": "over",
                "source_count": 2,
                "observed_at": fresh_ts,
                "source_mark": {"state": "blend"},
            },
            {
                "_market_id": 7004,
                "player": {"key": "ja marr chase", "name": "Ja'Marr Chase"},
                "player_headshot": "https://cdn.example/chase.png",
                "player_team": "away",
                "stat": {"key": "receiving_yards", "label": "Receiving Yards"},
                "line": {"kind": "count_at_least", "value": 85, "label": "85+"},
                "over_probability": 0.56,
                "side": "over",
                "source_count": 1,
                "observed_at": fresh_ts,
                "source_mark": {"state": "single"},
            },
        ],
        "team_totals": [
            {
                "_market_id": 7005,
                "market_name": "Washington Commanders Team Total Over 24.5",
                "team": "Washington Commanders",
                "over_probability": 0.59,
                "threshold": 24.5,
                "observed_at": fresh_ts,
                "source_mark": {"state": "single"},
            }
        ],
        "other": [
            {
                "_market_id": 7006,
                "market_name": "1st Quarter Total Points O/U 10.5",
                "outcome_name": "Over",
                "over_probability": 0.55,
                "threshold": 10.5,
                "observed_at": fresh_ts,
                "source_mark": {"state": "single"},
            },
            {
                "_market_id": 7007,
                "market_name": "Two-Point Conversion Attempted?",
                "outcome_name": "Yes",
                "probability": 0.38,
                "observed_at": fresh_ts,
                "source_mark": {"state": "single"},
            },
        ],
    }
    rf = {
        "futures": [
            {
                "_market_id": 7100,
                "title": "Washington Commanders to make NFL Playoffs",
                "probability": 0.62,
                "change_24h": 0.04,
            }
        ]
    }
    tp = {
        "teams": [
            {"team_name": "Washington Commanders", "playoff_pct": 62.0},
            {"team_name": "Cincinnati Bengals", "playoff_pct": 44.0},
        ]
    }
    return gm, rf, tp


class _FakeScalarResult:
    def __init__(self, one=None, many=None):
        self._one = one
        self._many = many if many is not None else []

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return self

    def all(self):
        return self._many

    def first(self):
        return self._one


def _build_ranking_grades_sqlite_engine():
    mig_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "ranking_slates_12095.py"
    )
    mig_text = mig_path.read_text(encoding="utf-8")
    for allowed in ("shareable", "interesting", "neither"):
        assert f"'{allowed}'" in mig_text

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE ranking_grades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slate_id VARCHAR(64) NOT NULL,
                    surface VARCHAR(32) NOT NULL,
                    grader VARCHAR(40) NOT NULL,
                    expert BOOLEAN NOT NULL,
                    position INTEGER NOT NULL,
                    item_key VARCHAR(120) NOT NULL,
                    grade VARCHAR(16) NOT NULL,
                    note VARCHAR(300),
                    graded_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    CONSTRAINT ck_ranking_grades_grade CHECK (
                        grade IN ('shareable', 'interesting', 'neither')
                    )
                )
                """
            )
        )
    return engine


async def test_game_nuggets_grades_satisfy_ck_ranking_grades_grade_and_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    engine = _build_ranking_grades_sqlite_engine()
    sync_session = Session(engine)

    def _restore_sqlite_utc(target, _context) -> None:
        if target.graded_at is not None and target.graded_at.tzinfo is None:
            target.graded_at = target.graded_at.replace(tzinfo=timezone.utc)

    event.listen(RankingGrade, "load", _restore_sqlite_utc)

    gm, rf, tp = _rich_event_payloads(now)
    fake_ev = SimpleNamespace(
        id=15353569,
        home_team_id=10,
        away_team_id=20,
        home_team_name="Washington Commanders",
        away_team_name="Cincinnati Bengals",
        sport=SimpleNamespace(key="americanfootball_nfl"),
        status="scheduled",
        commence_time=now + timedelta(hours=6),
    )
    linked_counts = [(15353569, 8)]
    market_rows = [
        (15353569, "Bengals at Commanders: Total Points O/U 48.5", "KXNFLTOTAL-1"),
        (15353569, "Commanders vs Bengals: Spread -3.5", "KXNFLSPREAD-1"),
        (15353569, "Jayden Daniels: Passing Yards O/U 245.5", "KXNFLPYDS-1"),
        (15353569, "Ja'Marr Chase: Receiving Yards O/U 84.5", "KXNFLRYDS-1"),
        (15353569, "Washington Commanders Team Total Over 24.5", "KXNFLTT-1"),
        (15353569, "1st Quarter Total Points O/U 10.5", "KXNFL1QTOTAL-1"),
        (15353569, "Two-Point Conversion Attempted?", "KXNFL2PT-1"),
    ]

    class _HybridAsyncSession:
        def add(self, obj: RankingGrade) -> None:
            if getattr(obj, "graded_at", None) is None:
                obj.graded_at = now
            sync_session.add(obj)

        async def commit(self) -> None:
            sync_session.commit()

        async def execute(self, stmt):
            sql = str(stmt)
            if "FROM ranking_grades" in sql:
                return sync_session.execute(stmt)
            if "FROM teams" in sql:
                return _FakeScalarResult(
                    many=[
                        SimpleNamespace(
                            id=10,
                            logo_small="https://cdn.example/was.png",
                            logo_url=None,
                            logo_large=None,
                        ),
                        SimpleNamespace(
                            id=20,
                            logo_small="https://cdn.example/cin.png",
                            logo_url=None,
                            logo_large=None,
                        ),
                    ]
                )
            if "FROM futures_markets" in sql:
                if "count(" in sql.lower() and "group by" in sql.lower():
                    return _FakeScalarResult(many=linked_counts)
                if "distinct" in sql.lower():
                    return _FakeScalarResult(many=["football"])
                return _FakeScalarResult(many=market_rows)
            if "ORDER BY events" in sql:
                return _FakeScalarResult(many=[fake_ev])
            return _FakeScalarResult(one=fake_ev)

    hybrid_db = _HybridAsyncSession()

    async def _db_override():
        yield hybrid_db

    # Seed one Discover row so we verify /api/admin/ranking/grades keeps Discover rows
    # while excluding SURFACE_GAME_NUGGETS rows.
    sync_session.add(
        RankingGrade(
            slate_id="discover-2026-11-24",
            surface="discover",
            grader="Alex",
            expert=True,
            position=1,
            item_key="market:999",
            grade="shareable",
            note="discover baseline",
            graded_at=now,
        )
    )
    sync_session.commit()

    monkeypatch.setattr(
        events_route,
        "resolve_served_event",
        AsyncMock(return_value=SimpleNamespace(event=fake_ev, event_id=15353569)),
    )
    monkeypatch.setattr(events_route, "get_game_markets", AsyncMock(return_value=gm))
    monkeypatch.setattr(events_route, "get_related_futures", AsyncMock(return_value=rf))
    monkeypatch.setattr(events_route, "get_team_progression", AsyncMock(return_value=tp))
    monkeypatch.setattr(eval_route, "_check_admin_secret", lambda *_a, **_kw: None)

    prior = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_db_rw] = _db_override
    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            r_deck = await client.get("/api/admin/ranking/game-nuggets/deck?limit=20")
            assert r_deck.status_code == 200, r_deck.text
            slate_id = r_deck.json()["slate_id"]

            r_game = await client.get(
                f"/api/admin/ranking/game-nuggets/games/15353569?limit=8&slate={slate_id}"
            )
            assert r_game.status_code == 200, r_game.text
            nuggets = r_game.json()["game"]["nuggets"]
            assert len(nuggets) >= 6

            for idx, item in enumerate(nuggets):
                want_grade = "yes" if idx < len(nuggets) - 1 else "no"
                r_post = await client.post(
                    "/api/admin/ranking/game-nuggets/grades",
                    json={
                        "slate_id": slate_id,
                        "event_id": 15353569,
                        "nugget_id": item["id"],
                        "position": item["position"],
                        "grade": want_grade,
                        "grader": "Builder E smoke",
                        "note": f"note-{idx + 1}",
                    },
                )
                assert r_post.status_code == 200, r_post.text
                assert r_post.json()["grade"] == want_grade

            with engine.connect() as conn:
                raw_stored = [
                    r[0]
                    for r in conn.execute(
                        text(
                            "SELECT grade FROM ranking_grades "
                            "WHERE surface = 'game_nuggets' ORDER BY id ASC"
                        )
                    ).fetchall()
                ]
            assert raw_stored == ["shareable"] * (len(nuggets) - 1) + ["neither"]

            r_grades = await client.get(
                "/api/admin/ranking/game-nuggets/grades",
                params={"slate_id": slate_id},
            )
            assert r_grades.status_code == 200, r_grades.text
            g_body = r_grades.json()
            assert g_body["yes_count"] == len(nuggets) - 1
            assert g_body["no_count"] == 1
            assert g_body["graded_count"] == len(nuggets)
            assert g_body["by_grader"]["Builder E smoke"] == {
                "yes": len(nuggets) - 1,
                "no": 1,
                "total": len(nuggets),
            }
            assert [row["grade"] for row in g_body["grades"]] == [
                "yes" if i < len(nuggets) - 1 else "no" for i in range(len(nuggets))
            ]

            r_deck_after = await client.get(
                "/api/admin/ranking/game-nuggets/deck?limit=20",
                headers={"X-Grader-Name": "Builder E smoke"},
            )
            assert r_deck_after.status_code == 200, r_deck_after.text
            assert r_deck_after.json()["games"][0]["graded_count"] == len(nuggets)
            assert r_deck_after.json()["summary"]["yes_count"] == len(nuggets) - 1
            assert r_deck_after.json()["summary"]["no_count"] == 1

            r_game_after = await client.get(
                f"/api/admin/ranking/game-nuggets/games/15353569?limit=8&slate={slate_id}",
                headers={"X-Grader-Name": "Builder E smoke"},
            )
            assert r_game_after.status_code == 200, r_game_after.text
            reloaded_nuggets = r_game_after.json()["game"]["nuggets"]
            assert [n.get("saved_grade") for n in reloaded_nuggets] == [
                "yes" if i < len(nuggets) - 1 else "no" for i in range(len(nuggets))
            ]
            assert [n.get("saved_note") for n in reloaded_nuggets] == [
                f"note-{i + 1}" for i in range(len(nuggets))
            ]

            r_scorecard = await client.get("/api/admin/ranking/grades")
            assert r_scorecard.status_code == 200, r_scorecard.text
            scorecard_grades = r_scorecard.json()["grades"]
            assert len(scorecard_grades) == 1
            assert scorecard_grades[0]["surface"] == "discover"

        stored_nugget_rows = (
            sync_session.query(RankingGrade)
            .filter(RankingGrade.surface == eval_route.SURFACE_GAME_NUGGETS)
            .order_by(RankingGrade.id.asc())
            .all()
        )
        decoded = eval_route.latest_grades(stored_nugget_rows)
        assert [row["grade"] for row in decoded] == [
            "yes" if i < len(nuggets) - 1 else "no" for i in range(len(nuggets))
        ]
    finally:
        event.remove(RankingGrade, "load", _restore_sqlite_utc)
        app.dependency_overrides = prior
        sync_session.close()
        engine.dispose()


def test_summarize_game_nugget_grades_decodes_both_encoded_and_literal_rows() -> None:
    now = datetime.now(timezone.utc)
    rows = [
        SimpleNamespace(
            id=1,
            grader="Alex",
            item_key="event:1:k1",
            position=1,
            grade="shareable",
            note=None,
            graded_at=now,
        ),
        SimpleNamespace(
            id=2,
            grader="Alex",
            item_key="event:1:k2",
            position=2,
            grade="neither",
            note="dup",
            graded_at=now,
        ),
        SimpleNamespace(
            id=3,
            grader="Alex",
            item_key="event:1:k3",
            position=3,
            grade="yes",
            note=None,
            graded_at=now,
        ),
        SimpleNamespace(
            id=4,
            grader="Alex",
            item_key="event:1:k4",
            position=4,
            grade="no",
            note=None,
            graded_at=now,
        ),
    ]
    summary = eval_route._summarize_game_nugget_grades(rows)
    assert summary["yes_count"] == 2
    assert summary["no_count"] == 2
    assert summary["graded_count"] == 4
    assert summary["repeat_rate"] == pytest.approx(0.5)
    assert [g["grade"] for g in summary["grades"]] == ["yes", "no", "yes", "no"]
