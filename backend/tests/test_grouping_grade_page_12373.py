"""Tests for #12373 (Epic #12288, Plan #12221 row 6): private grading page for proposed grouping cards.

Verifies:
1. ``load_grouping_grade_deck`` loads 20+ proposed grouping cards from
   ``grouping-candidates-2026-11.json``, each carrying both its ``proposed_card``
   preview and its ``best_single`` member.
2. ``select_best_single_member`` selects the priced binary member closest to 50%
   (within ``[0.05, 0.95]``) as the strongest standalone single comparison.
3. ``normalize_grouping_grader`` preserves adult/friend names and enforces
   pseudonyms (`kid1`..`kid4` or `kid-<6hex>`) for kid graders so a kid's real
   name is never stored in ``ranking_grades``.
4. ``GET /api/admin/ranking/grouping-deck``, ``POST /api/admin/ranking/grouping-grades``,
   and ``GET /api/admin/ranking/grouping-grades`` require admin auth, validate
   grades (``amazing`` / ``fine`` / ``no``), store kid grades under pseudonyms
   with ``expert=False``, and compute accurate summary counts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.routes.admin_ranking_eval import (
    DEFAULT_GROUPING_SLATE_ID,
    GROUPING_GRADES,
    GroupingGradeIn,
    get_grouping_deck,
    get_grouping_grades,
    load_grouping_grade_deck,
    normalize_grouping_grader,
    post_grouping_grade,
    select_best_single_member,
    summarize_grouping_grades,
)


def _dummy_request(bearer_token: str | None = None) -> Request:
    headers = []
    if bearer_token:
        headers.append((b"authorization", f"Bearer {bearer_token}".encode("utf-8")))
    return Request({"type": "http", "headers": headers, "query_string": b""})


def test_grouping_grade_deck_loads_twenty_plus_proposed_cards_beside_best_single() -> None:
    deck = load_grouping_grade_deck()
    assert deck["slate_id"] == DEFAULT_GROUPING_SLATE_ID
    assert deck["surface"] == "grouping"
    assert len(deck["items"]) >= 20

    for idx, item in enumerate(deck["items"], start=1):
        assert item["position"] == idx
        assert isinstance(item["item_key"], str) and item["item_key"]
        assert item["kind_verdict"] in ("serve", "refuse")

        card = item["proposed_card"]
        assert isinstance(card["title"], str) and card["title"]
        assert isinstance(card["rows"], list) and len(card["rows"]) >= 1
        assert isinstance(card["footer"], str) and card["footer"]

        single = item["best_single"]
        assert isinstance(single["id"], int) and single["id"] > 0
        assert isinstance(single["name"], str) and single["name"]


def test_select_best_single_member_picks_member_closest_to_fifty_percent() -> None:
    family = {
        "name": "Will which city record snow?",
        "source": "kalshi",
        "category": "weather",
        "members": [
            {"id": 101, "name": "Will Denver record snow?", "subject": "Denver", "yes_probability": 0.91},
            {"id": 102, "name": "Will Chicago record snow?", "subject": "Chicago", "yes_probability": 0.52},
            {"id": 103, "name": "Will Miami record snow?", "subject": "Miami", "yes_probability": 0.02},
        ],
        "quotes": {
            "market_a_id": 102,
            "market_a_quote": "Resolves Yes if Chicago O'Hare records measurable snowfall.",
        },
    }
    single = select_best_single_member(family)
    assert single["id"] == 102
    assert single["subject"] == "Chicago"
    assert single["rendered_percent"] == 52
    assert "Chicago O'Hare" in single["rule_quote"]


def test_kid_graders_are_always_pseudonyms_never_names() -> None:
    # Adult/friend grader keeps normalized name
    assert normalize_grouping_grader("  Alex  ", kid=False) == "Alex"
    assert normalize_grouping_grader("Sam B.", kid=False) == "Sam B."

    # Explicit kid1..kid4 pseudonyms are preserved in lowercase
    assert normalize_grouping_grader("kid1", kid=True) == "kid1"
    assert normalize_grouping_grader("KID3", kid=True) == "kid3"
    assert normalize_grouping_grader("kid4", kid=True) == "kid4"

    # Any real name or non-kid1..kid4 string with kid=True is refused (returns "")
    assert normalize_grouping_grader("Leo", kid=True) == ""
    assert normalize_grouping_grader("kid9", kid=True) == ""
    assert normalize_grouping_grader("kid-a1b2c3", kid=True) == ""


@pytest.mark.asyncio
async def test_grouping_grade_routes_require_admin_and_enforce_kid_pseudonyms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADMIN_SECRET", "test-secret-12373")
    unauth_req = _dummy_request("wrong")
    auth_req = _dummy_request("test-secret-12373")

    # Unauthorized without valid bearer token
    with pytest.raises(HTTPException) as exc:
        await get_grouping_deck(unauth_req)
    assert exc.value.status_code in (401, 403)

    deck = await get_grouping_deck(auth_req)
    assert len(deck["items"]) >= 20
    first_item = deck["items"][0]

    stored_rows: list[Any] = []

    class _FakeScalars:
        def all(self) -> list[Any]:
            return list(stored_rows)

    class _FakeResult:
        def scalars(self) -> _FakeScalars:
            return _FakeScalars()

    class _FakeSession:
        def add(self, obj: Any) -> None:
            obj.id = len(stored_rows) + 1
            obj.graded_at = datetime.now(timezone.utc)
            stored_rows.append(obj)

        async def commit(self) -> None:
            pass

        async def execute(self, _stmt: Any) -> _FakeResult:
            return _FakeResult()

    fake_db = _FakeSession()

    # Invalid grade value rejected with 422
    with pytest.raises(HTTPException) as bad_grade:
        await post_grouping_grade(
            GroupingGradeIn(
                slate_id=DEFAULT_GROUPING_SLATE_ID,
                grader="Alex",
                kid=False,
                position=1,
                item_key=first_item["item_key"],
                grade="shareable",
            ),
            auth_req,
            db=fake_db,  # type: ignore[arg-type]
        )
    assert bad_grade.value.status_code == 422

    # Adult grade saved with expert=True
    res_adult = await post_grouping_grade(
        GroupingGradeIn(
            slate_id=DEFAULT_GROUPING_SLATE_ID,
            grader="Alex",
            kid=False,
            position=1,
            item_key=first_item["item_key"],
            grade="amazing",
            note="Card shows the whole NHL 100-point race at a glance",
        ),
        auth_req,
        db=fake_db,  # type: ignore[arg-type]
    )
    assert res_adult["status"] == "ok"
    assert res_adult["grader"] == "Alex"
    assert stored_rows[0].expert is True

    # Kid grade with a typed name is refused (422) — only kid1..kid4 are accepted
    with pytest.raises(HTTPException) as bad_kid_name:
        await post_grouping_grade(
            GroupingGradeIn(
                slate_id=DEFAULT_GROUPING_SLATE_ID,
                grader="Maya",
                kid=True,
                position=1,
                item_key=first_item["item_key"],
                grade="fine",
            ),
            auth_req,
            db=fake_db,  # type: ignore[arg-type]
        )
    assert bad_kid_name.value.status_code == 422

    # Kid grade with kid2 pseudonym is accepted with expert=False
    res_kid = await post_grouping_grade(
        GroupingGradeIn(
            slate_id=DEFAULT_GROUPING_SLATE_ID,
            grader="KID2",
            kid=True,
            position=1,
            item_key=first_item["item_key"],
            grade="fine",
        ),
        auth_req,
        db=fake_db,  # type: ignore[arg-type]
    )
    assert res_kid["status"] == "ok"
    assert res_kid["grader"] == "kid2"
    assert stored_rows[1].grader == "kid2"
    assert stored_rows[1].expert is False

    # Read back grades and summary
    out = await get_grouping_grades(
        auth_req,
        slate_id=DEFAULT_GROUPING_SLATE_ID,
        days=30,
        db=fake_db,  # type: ignore[arg-type]
    )
    assert out["summary"]["total_grades"] == 2
    assert out["summary"]["distinct_graders"] == 2
    assert out["summary"]["distinct_cards_graded"] == 1
    assert out["summary"]["by_grade"] == {"amazing": 1, "fine": 1, "no": 0}
    assert out["tally"] == [
        {"grader": "Alex", "kid": False, "today": 1},
        {"grader": "kid2", "kid": True, "today": 1},
    ]
    assert set(GROUPING_GRADES) == {"amazing", "fine", "no"}


@pytest.mark.asyncio
async def test_grouping_grades_satisfy_postgres_ck_ranking_grades_grade_and_roundtrip_losslessly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every stored RankingGrade.grade satisfies ck_ranking_grades_grade and round-trips losslessly on surface='grouping'."""
    import sqlite3
    from pathlib import Path
    from app.routes.admin_ranking_eval import GRADES, latest_grades

    mig_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "ranking_slates_12095.py"
    )
    mig_text = mig_path.read_text(encoding="utf-8")
    for allowed in GRADES:
        assert f"'{allowed}'" in mig_text

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ranking_grades ("
        " id INTEGER PRIMARY KEY,"
        " surface TEXT NOT NULL,"
        " grade TEXT NOT NULL,"
        " CONSTRAINT ck_ranking_grades_grade CHECK (grade IN ('shareable', 'interesting', 'neither'))"
        ")"
    )

    monkeypatch.setenv("ADMIN_SECRET", "test-secret-12373")
    auth_req = _dummy_request("test-secret-12373")
    deck = await get_grouping_deck(auth_req)

    stored_rows: list[Any] = []

    class _FakeSession:
        def add(self, obj: Any) -> None:
            obj.id = len(stored_rows) + 1
            obj.graded_at = datetime.now(timezone.utc)
            # Enforce the exact Postgres check constraint from ranking_slates_12095.py
            conn.execute(
                "INSERT INTO ranking_grades (id, surface, grade) VALUES (?, ?, ?)",
                (obj.id, obj.surface, obj.grade),
            )
            stored_rows.append(obj)

        async def commit(self) -> None:
            conn.commit()

    fake_db = _FakeSession()

    for idx, g_val in enumerate(GROUPING_GRADES, start=1):
        item = deck["items"][idx - 1]
        await post_grouping_grade(
            GroupingGradeIn(
                slate_id=DEFAULT_GROUPING_SLATE_ID,
                grader="Alex",
                kid=False,
                position=idx,
                item_key=item["item_key"],
                grade=g_val,
            ),
            auth_req,
            db=fake_db,  # type: ignore[arg-type]
        )

    assert [r.grade for r in stored_rows] == ["shareable", "interesting", "neither"]
    decoded = latest_grades(stored_rows)
    assert [d["grade"] for d in decoded] == ["amazing", "fine", "no"]
    summary = summarize_grouping_grades(decoded)
    assert summary["by_grade"] == {"amazing": 1, "fine": 1, "no": 1}
    conn.close()
