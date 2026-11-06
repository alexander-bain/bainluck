"""#12095 Phase 2: the /grade page's endpoints and the grades export.

Pinned here: a grade is refused while ``RANKING_SNAPSHOTS`` is off, refused
outside the three grades, and refused for a card that is not at that position
in that slate; a kid's grade is stored non-expert; the latest grade per grader
and card wins; the family tally counts since Pacific midnight; the export
writes the same file shape the scorecard reads and never overwrites a
hand-filled sheet.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.routes.admin_ranking_eval as admin
from app.models.models import RankingGrade
from app.utils.ranking_eval import RANKING_SNAPSHOTS_ENV

REPO = Path(__file__).resolve().parents[2]
SLATE = {
    "id": "row-1",
    "surface": "discover",
    "slate_id": "ae0bc760eb204e34",
    "captured_at": "2026-11-06T12:15:00+00:00",
    "ranker_version": "abc",
    "served_order": [f"futures:{i}" for i in range(1, 13)],
    "candidates": [
        {"item_key": f"futures:{i}", "title": f"Card {i}", "probability": 0.5, **({"card": {"type": "futures", "data": {"id": i}}} if i <= 10 else {})}
        for i in range(1, 13)
    ],
    "summary": {},
}


def _request():
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "query_string": b""})


class FakeDB:
    def __init__(self):
        self.added, self.commits = [], 0

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.commits += 1


@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setattr(admin, "_check_admin_secret", lambda *a, **k: True)

    async def slate_row(db, ref, surface):
        return SimpleNamespace(**SLATE, captured_at_dt=None)

    monkeypatch.setattr(admin, "_slate_row", slate_row)
    monkeypatch.setattr(admin, "slate_row_dict", lambda row: dict(SLATE))
    monkeypatch.setenv(RANKING_SNAPSHOTS_ENV, "1")


def grade(**kw):
    body = {
        "slate_id": "ae0bc760eb204e34", "grader": "  Robin  ", "kid": True, "position": 3,
        "item_key": "futures:3", "grade": "interesting", "note": " fun ",
    }
    body.update(kw)
    return admin.GradeIn(**body)


class TestPostGrade:
    async def test_a_kid_grade_is_stored_non_expert_and_trimmed(self, wired):
        db = FakeDB()
        assert await admin.post_grade(grade(), _request(), secret=None, db=db) == {"status": "ok"}
        (row,) = db.added
        assert isinstance(row, RankingGrade)
        assert row.grader == "Robin" and row.expert is False and row.note == "fun"
        assert (row.position, row.item_key, row.grade) == (3, "futures:3", "interesting")
        assert db.commits == 1

    async def test_refused_while_the_switch_is_off(self, wired, monkeypatch):
        monkeypatch.delenv(RANKING_SNAPSHOTS_ENV)
        with pytest.raises(HTTPException) as exc:
            await admin.post_grade(grade(), _request(), secret=None, db=FakeDB())
        assert exc.value.status_code == 409

    @pytest.mark.parametrize(
        "kw",
        [{"grade": "cool"}, {"position": 4}, {"item_key": "futures:11", "position": 10}, {"grader": "   "}],
    )
    async def test_refused_outside_the_grades_or_the_slate(self, wired, kw):
        db = FakeDB()
        with pytest.raises(HTTPException) as exc:
            await admin.post_grade(grade(**kw), _request(), secret=None, db=db)
        assert exc.value.status_code == 422 and db.added == []


async def test_the_grade_deck_is_the_opening_ten_with_cards(wired):
    deck = await admin.get_grade_deck(_request(), surface="discover", secret=None, db=FakeDB())
    assert deck["slate_id"] == "ae0bc760eb204e34" and deck["switch_on"] is True
    assert [i["position"] for i in deck["items"]] == list(range(1, 11))
    assert deck["items"][0]["card"] == {"type": "futures", "data": {"id": 1}}


def _row(i, grader, key, g, at, expert=True):
    return SimpleNamespace(
        id=i, slate_id="s", surface="discover", grader=grader, expert=expert, position=1,
        item_key=key, grade=g, note=None, graded_at=at,
    )


def test_the_latest_grade_per_grader_and_card_wins_and_the_tally_counts_since_pacific_midnight():
    rows = [
        _row(1, "Alex", "futures:1", "neither", datetime(2026, 11, 6, 16, 0, tzinfo=timezone.utc)),
        _row(2, "Alex", "futures:1", "shareable", datetime(2026, 11, 6, 17, 0, tzinfo=timezone.utc)),
        _row(3, "Alex", "futures:2", "interesting", datetime(2026, 11, 6, 17, 1, tzinfo=timezone.utc)),
        _row(4, "Sam", "futures:1", "shareable", datetime(2026, 11, 6, 17, 2, tzinfo=timezone.utc), expert=False),
        # 11:00 PM PT the day before: not today.
        _row(5, "Robin", "futures:1", "neither", datetime(2026, 11, 6, 7, 0, tzinfo=timezone.utc), expert=False),
    ]
    grades = admin.latest_grades(rows)
    alex1 = [g for g in grades if g["grader"] == "Alex" and g["item_key"] == "futures:1"]
    assert len(grades) == 4 and alex1[0]["grade"] == "shareable"
    tally = admin.family_tally(grades, now=datetime(2026, 11, 6, 18, 0, tzinfo=timezone.utc))
    assert tally == [
        {"grader": "Alex", "kid": False, "today": 2},
        {"grader": "Sam", "kid": True, "today": 1},
    ]


def _grades_tool():
    spec = importlib.util.spec_from_file_location("grades", REPO / "tools" / "ranking" / "grades.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_export_writes_the_scorecard_shape_pseudonymizes_kids_and_never_overwrites_a_hand_sheet(tmp_path):
    gr = _grades_tool()
    rows = [
        {"slate_id": "s", "surface": "discover", "grader": "Sam", "expert": False, "position": 2,
         "item_key": "futures:2", "grade": "neither", "note": "", "graded_at": "2026-11-06T17:00:00+00:00"},
        {"slate_id": "s", "surface": "discover", "grader": "Sam", "expert": False, "position": 1,
         "item_key": "futures:1", "grade": "shareable", "note": "wow", "graded_at": "2026-11-06T17:00:00+00:00"},
        {"slate_id": "s", "surface": "discover", "grader": "Alex", "expert": True, "position": 1,
         "item_key": "futures:1", "grade": "interesting", "note": "", "graded_at": "2026-11-07T06:30:00+00:00"},
    ]
    kid, alex = sorted(gr.export_documents(rows), key=lambda d: d["expert"])
    # The kid's typed name never reaches the file: a stable pseudonym does.
    assert kid["grader"] == gr.kid_pseudonym("sam") and gr.KID_ID.match(kid["grader"])
    assert "Sam" not in json.dumps(kid)
    assert kid["expert"] is False and kid["source"] == "grade-page"
    assert [i["position"] for i in kid["items"]] == [1, 2] and kid["items"][0]["grade"] == "shareable"
    assert gr.validate_grades(kid) == [] and gr.validate_grades(alex) == []
    # Dated in Pacific time: 06:30Z Nov 7 is still Nov 6 in PT.
    assert alex["date"] == "2026-11-06" and alex["grader"] == "Alex"
    assert gr.export_path(tmp_path, alex).name == "2026-11-06-discover-s-alex.json"
    (tmp_path / "2026-11-06-discover-s-alex.json").write_text(json.dumps({"slate_id": "s", "grader": "alex"}))
    assert gr.export_path(tmp_path, alex).name == "2026-11-06-discover-s-alex-web.json"
