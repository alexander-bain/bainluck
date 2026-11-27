"""Real-DB enforcement & round-trip tests for ``RankingGrade`` and every grading POST endpoint (#N6)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
from httpx import ASGITransport
import pytest
from sqlalchemy import BigInteger, CheckConstraint, JSON, create_engine, event, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.main import app
from app.models.models import (
    Base,
    Event,
    FuturesMarket,
    RankingGrade,
    RankingJudgment,
    RankingSlateSnapshot,
    Sport,
)
from app.routes import admin_judgments as judgments_route
from app.routes import admin_ranking_eval as eval_route
from app.services import get_db, get_db_rw


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - SQLite DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - SQLite DDL shim
    return "JSON"


@compiles(BigInteger, "sqlite")
def _bigint_on_sqlite(type_, compiler, **kw):  # pragma: no cover - SQLite DDL shim
    return "INTEGER"


_GRADING_TABLES = [
    Sport.__table__,
    Event.__table__,
    FuturesMarket.__table__,
    RankingSlateSnapshot.__table__,
    RankingGrade.__table__,
    RankingJudgment.__table__,
]

_ALLOWED_DB_GRADES = ("shareable", "interesting", "neither")


class _SyncBackedAsyncSession:
    """AsyncSession facade executing all ORM/SQL operations against a real sync SQLite DB."""

    def __init__(self, sync_session: Session, now: datetime) -> None:
        self._sync = sync_session
        self._now = now

    def add(self, instance) -> None:
        if hasattr(instance, "graded_at") and getattr(instance, "graded_at", None) is None:
            instance.graded_at = self._now
        if hasattr(instance, "created_at") and getattr(instance, "created_at", None) is None:
            instance.created_at = self._now
        self._sync.add(instance)

    async def execute(self, stmt, *args, **kwargs):
        return self._sync.execute(stmt, *args, **kwargs)

    async def scalar(self, stmt, *args, **kwargs):
        return self._sync.scalar(stmt, *args, **kwargs)

    async def commit(self) -> None:
        self._sync.commit()

    async def rollback(self) -> None:
        self._sync.rollback()

    async def flush(self) -> None:
        self._sync.flush()

    async def refresh(self, instance) -> None:
        self._sync.refresh(instance)


@contextmanager
def _real_sqlite_db():
    """Spin up an in-memory SQLite database from ``Base.metadata.create_all`` with CheckConstraints active."""
    engine = create_engine("sqlite:///:memory:")

    def _enable_sqlite_pragmas(dbapi_conn, _conn_record) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA ignore_check_constraints = OFF")
        cur.close()

    def _restore_naive_utc(target, _context) -> None:
        for attr in ("graded_at", "captured_at", "created_at"):
            val = getattr(target, attr, None)
            if isinstance(val, datetime) and val.tzinfo is None:
                setattr(target, attr, val.replace(tzinfo=timezone.utc))

    event.listen(engine, "connect", _enable_sqlite_pragmas)
    for model_cls in (RankingGrade, RankingSlateSnapshot, RankingJudgment):
        event.listen(model_cls, "load", _restore_naive_utc)

    reason_tags_col = RankingJudgment.__table__.c.reason_tags
    orig_reason_tags_type = reason_tags_col.type
    reason_tags_col.type = JSON()

    Base.metadata.create_all(engine, tables=_GRADING_TABLES)
    sync_session = Session(engine)
    try:
        yield engine, sync_session
    finally:
        sync_session.close()
        reason_tags_col.type = orig_reason_tags_type
        for model_cls in (RankingGrade, RankingSlateSnapshot, RankingJudgment):
            event.remove(model_cls, "load", _restore_naive_utc)
        engine.dispose()


def test_ranking_grade_model_carries_and_enforces_allowed_values_constraint() -> None:
    """``RankingGrade`` declares ``ck_ranking_grades_grade`` matching the migration and rejects invalid grades."""
    mig_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "ranking_slates_12095.py"
    )
    mig_text = mig_path.read_text(encoding="utf-8")
    for allowed in _ALLOWED_DB_GRADES:
        assert f"'{allowed}'" in mig_text

    check_constraints = [
        c
        for c in RankingGrade.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_ranking_grades_grade"
    ]
    assert len(check_constraints) == 1
    sql_text = str(check_constraints[0].sqltext)
    for allowed in _ALLOWED_DB_GRADES:
        assert f"'{allowed}'" in sql_text

    with _real_sqlite_db() as (_engine, sync_session):
        for bad_grade in ("yes", "no", "keep", "fix", "drop", "fun", "left", "bogus", ""):
            sync_session.add(
                RankingGrade(
                    slate_id="constraint-check-slate",
                    surface="discover",
                    grader="Builder E test",
                    expert=True,
                    position=1,
                    item_key="futures:1",
                    grade=bad_grade,
                    note=None,
                )
            )
            with pytest.raises(IntegrityError):
                sync_session.commit()
            sync_session.rollback()


async def test_every_grading_post_endpoint_persists_to_real_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every grading POST route writes valid rows through FastAPI into a real enforcing database."""
    monkeypatch.setenv("RANKING_SNAPSHOTS", "1")
    monkeypatch.setattr(eval_route, "_check_admin_secret", lambda *_a, **_kw: None)
    monkeypatch.setattr(judgments_route, "_check_admin_secret", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        judgments_route, "_authorize_admin", AsyncMock(return_value=True)
    )

    now = datetime.now(timezone.utc)
    with _real_sqlite_db() as (_engine, sync_session):
        # Seed a real discover slate snapshot in SQLite for /grades and /pair-picks.
        slate_id = "slate-real-db-test-20261125"
        drawn_candidates = [
            {
                "position": pos,
                "item_key": f"futures:{1000 + pos}",
                "title": f"Real DB Test Market {pos}",
                "probability": 0.55,
                "score": 90 - pos,
                "card": {
                    "type": "futures",
                    "headline": f"Market {pos} moves",
                    "data": {"id": 1000 + pos, "name": f"Real DB Test Market {pos}"},
                },
            }
            for pos in range(1, 5)
        ]
        sync_session.add(
            RankingSlateSnapshot(
                id="11111111-1111-1111-1111-111111111111",
                surface="discover",
                slate_id=slate_id,
                captured_at=now - timedelta(hours=1),
                ranker_version="test-v1",
                served_order=[c["item_key"] for c in drawn_candidates],
                candidates=drawn_candidates,
                summary={"served_count": len(drawn_candidates)},
            )
        )
        sync_session.commit()

        # Register a deterministic 2-card pair matching the seeded slate for /pair-picks.
        monkeypatch.setattr(
            eval_route,
            "load_pairs",
            lambda *_a, **_kw: {
                slate_id: {
                    "testpair": ["futures:1001", "futures:1002"],
                }
            },
        )
        # Provide one minimal valid screen week on top of the shipped screen samples format.
        monkeypatch.setattr(
            eval_route,
            "load_screen_samples",
            lambda *_a, **_kw: {
                "2026-w99": [
                    {"id": "scr-1", "image": "https://cdn.example/s1.png"},
                    {"id": "scr-2", "image": "https://cdn.example/s2.png"},
                    {"id": "scr-3", "image": "https://cdn.example/s3.png"},
                ]
            },
        )

        async_session = _SyncBackedAsyncSession(sync_session, now)

        async def _db_override():
            yield async_session

        prior = dict(app.dependency_overrides)
        app.dependency_overrides[get_db] = _db_override
        app.dependency_overrides[get_db_rw] = _db_override
        try:
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                # 1. /grade -> POST /api/admin/ranking/grades
                for pos, grade in enumerate(("shareable", "interesting", "neither"), start=1):
                    r = await client.post(
                        "/api/admin/ranking/grades",
                        json={
                            "slate_id": slate_id,
                            "surface": "discover",
                            "grader": "Builder E realdb",
                            "kid": False,
                            "position": pos,
                            "item_key": f"futures:{1000 + pos}",
                            "grade": grade,
                            "note": f"discover-{grade}",
                        },
                    )
                    assert r.status_code == 200, r.text
                r_get = await client.get(
                    "/api/admin/ranking/grades",
                    params={"slate_id": slate_id, "days": 2},
                )
                assert r_get.status_code == 200, r_get.text
                assert len(r_get.json()["grades"]) == 3

                # 2. /grade/groupings -> POST /api/admin/ranking/grouping-grades
                grouping_deck = eval_route.load_grouping_grade_deck()
                g_items = grouping_deck["items"]
                assert len(g_items) >= 3
                g_slate_id = grouping_deck["slate_id"]
                for idx, grade in enumerate(eval_route.GROUPING_GRADES):
                    it = g_items[idx]
                    r = await client.post(
                        "/api/admin/ranking/grouping-grades",
                        json={
                            "slate_id": g_slate_id,
                            "grader": "Builder E realdb",
                            "kid": False,
                            "position": it["position"],
                            "item_key": it["item_key"],
                            "grade": grade,
                            "note": f"grouping-{grade}",
                        },
                    )
                    assert r.status_code == 200, r.text
                r_grp = await client.get(
                    "/api/admin/ranking/grouping-grades",
                    params={"slate_id": g_slate_id, "days": 30},
                )
                assert r_grp.status_code == 200, r_grp.text
                assert len(r_grp.json()["grades"]) == 3

                # 3. /grade/pair -> POST /api/admin/ranking/pair-picks
                for idx, choice in enumerate(("left", "right", "none"), start=1):
                    r = await client.post(
                        "/api/admin/ranking/pair-picks",
                        json={
                            "slate_id": slate_id,
                            "pair": "testpair",
                            "choice": choice,
                            "grader": f"Builder E pair-{idx}",
                            "opened_discover_today": False,
                        },
                    )
                    assert r.status_code == 200, r.text
                r_pair = await client.get(
                    "/api/admin/ranking/pair-picks",
                    params={"slate_id": slate_id, "days": 30},
                )
                assert r_pair.status_code == 200, r_pair.text
                assert len(r_pair.json()["picks"]) == 3

                # 4. /grade/screens -> POST /api/admin/ranking/screen-grades & /undo
                for n, s_grade in enumerate(eval_route.SCREEN_GRADES, start=1):
                    r = await client.post(
                        "/api/admin/ranking/screen-grades",
                        json={
                            "week": "2026-w99",
                            "n": n,
                            "grade": s_grade,
                            "grader": "Builder E realdb",
                        },
                    )
                    assert r.status_code == 200, r.text
                r_undo = await client.post(
                    "/api/admin/ranking/screen-grades/undo",
                    json={"week": "2026-w99", "n": 3, "grader": "Builder E realdb"},
                )
                assert r_undo.status_code == 200, r_undo.text
                r_scr = await client.get(
                    "/api/admin/ranking/screen-grades", params={"week": "2026-w99"}
                )
                assert r_scr.status_code == 200, r_scr.text
                assert [
                    s["grades"].get("Builder E realdb")
                    for s in r_scr.json()["screens"]
                ] == ["fun", "fine", None]

                # 5. /grade/game-nuggets -> POST /api/admin/ranking/game-nuggets/grades
                nugget_slate = eval_route._game_nugget_slate_id(None, now)
                for pos, n_grade in enumerate(("yes", "no"), start=1):
                    r = await client.post(
                        "/api/admin/ranking/game-nuggets/grades",
                        json={
                            "slate_id": nugget_slate,
                            "event_id": 15353569,
                            "nugget_id": f"nug-{pos}",
                            "position": pos,
                            "grade": n_grade,
                            "grader": "Builder E realdb",
                            "note": f"nugget-{n_grade}",
                        },
                    )
                    assert r.status_code == 200, r.text
                r_nug = await client.get(
                    "/api/admin/ranking/game-nuggets/grades",
                    params={"slate_id": nugget_slate},
                )
                assert r_nug.status_code == 200, r_nug.text
                assert r_nug.json()["yes_count"] == 1
                assert r_nug.json()["no_count"] == 1

                # 6. /grade/forms, /grade/containers, /grade/sets-v2 -> POST /api/admin/ranking-judgments
                for idx, (surf, label) in enumerate(
                    (
                        ("grade_forms_deck", "love"),
                        ("grade_containers_deck", "fine"),
                        ("grade_sets_v2_deck", "kill"),
                    ),
                    start=1,
                ):
                    r = await client.post(
                        "/api/admin/ranking-judgments",
                        json={
                            "surface": surf,
                            "rank_seen": idx,
                            "item_type": "futures",
                            "market_name": f"Deck card {idx} ({surf})",
                            "label": label,
                            "notes": f"note-{surf}",
                            "reviewer": "Builder E realdb",
                        },
                    )
                    assert r.status_code == 200, r.text
                r_jud = await client.get("/api/admin/ranking-judgments", params={"limit": 20})
                assert r_jud.status_code == 200, r_jud.text
                assert r_jud.json()["total"] == 3
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(prior)

        # Verify every RankingGrade row stored directly in SQLite respects ck_ranking_grades_grade.
        rows = sync_session.execute(select(RankingGrade)).scalars().all()
        assert len(rows) == 3 + 3 + 3 + 3 + 2  # includes 1 soft-retracted screen row
        for r in rows:
            assert r.grade in _ALLOWED_DB_GRADES, (r.surface, r.grade)
        raw_surfaces = {r.surface for r in rows}
        assert {
            "discover",
            eval_route.SURFACE_GROUPING,
            eval_route.SURFACE_PAIR,
            eval_route.SURFACE_SCREENS,
            eval_route.SURFACE_SCREENS_UNDONE,
            eval_route.SURFACE_GAME_NUGGETS,
        } <= raw_surfaces

        judgments = sync_session.execute(select(RankingJudgment)).scalars().all()
        assert {j.surface for j in judgments} == {
            "grade_forms_deck",
            "grade_containers_deck",
            "grade_sets_v2_deck",
        }
