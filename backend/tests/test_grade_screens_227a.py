"""227-A point 6: Alex's eye on ten sampled phone screens a week (/grade/screens).

Ruling 227-A (Alex, Nov 17) adopts a visual-diversity standard, report-only;
point 6 says a count stays in the standard only if it agrees with his grades on
ten sampled screens a week, graded fun, fine or wall of numbers.

What must hold:
* ``GET /screens`` serves only numbered pictures: no page names, no counts, no
  ids, so nothing on the page can steer the eye;
* the newest week is served when none is named; an unknown week is a 404;
* ``POST /screen-grades`` stores the grade as what it means through the
  existing grade check (no migration), keyed to the screen, first grade stands;
* a bad grade is a 422, an unknown screen a 404, a repeat a 409;
* ``GET /screen-grades`` joins every grade to its screen's counts;
* the card-grade read (``GET /grades``) never returns screen grades.
"""

from __future__ import annotations

import inspect
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.routes.admin_ranking_eval as admin
from app.models.models import RankingGrade
from app.utils.ranking_eval import RANKING_SNAPSHOTS_ENV

WEEK = "2026-w47"
OLDER = "2026-w46"


def _screens(prefix, n=10):
    return [
        {"id": f"{prefix}{i}", "image": f"https://raw.example.com/{prefix}{i}.png",
         "page": f"/page-{i}", "counts": {"pictures": i % 3, "longest_run": 1 + i % 4}}
        for i in range(1, n + 1)
    ]


SAMPLES = {WEEK: {"screens": _screens("a")}, OLDER: {"screens": _screens("b")}}


def _request():
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""})


class FakeDB:
    def __init__(self, rows=()):
        self.rows, self.added, self.statements = list(rows), [], []

    async def execute(self, stmt):
        self.statements.append(stmt)
        rows = self.rows
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        pass


@pytest.fixture
def wired(monkeypatch, tmp_path):
    monkeypatch.setattr(admin, "_check_admin_secret", lambda *a, **k: True)
    path = tmp_path / "screen_samples.json"
    path.write_text(json.dumps(SAMPLES))
    monkeypatch.setattr(admin, "SCREENS_PATH", path)
    monkeypatch.setenv(RANKING_SNAPSHOTS_ENV, "1")
    return path


async def test_the_page_gets_only_numbered_pictures(wired):
    out = await admin.get_screens(_request(), week=WEEK, secret=None)
    assert out["week"] == WEEK
    assert [s["n"] for s in out["screens"]] == list(range(1, 11))
    body = json.dumps(out)
    for leak in ("counts", "page", "/page-", '"id"', "a1\""):
        assert leak not in body, f"the page response must not carry {leak!r}"


async def test_the_newest_week_is_served_by_default_and_an_unknown_week_is_404(wired):
    assert (await admin.get_screens(_request(), week=None, secret=None))["week"] == WEEK
    with pytest.raises(HTTPException) as e:
        await admin.get_screens(_request(), week="2026-w01", secret=None)
    assert e.value.status_code == 404


async def test_a_grade_is_stored_as_its_meaning_against_the_screen(wired):
    db = FakeDB()
    body = admin.ScreenGradeIn(week=WEEK, n=3, grader="  Alex ", grade="wall")
    assert await admin.post_screen_grade(body, _request(), secret=None, db=db) == {"status": "ok"}
    (row,) = db.added
    assert isinstance(row, RankingGrade)
    assert row.surface == "screens" and row.slate_id == f"screens-{WEEK}"
    assert row.item_key == "screen:a3" and row.position == 3 and row.grader == "Alex"
    assert row.grade == "neither"  # inside ck_ranking_grades_grade: no migration
    assert set(admin._SCREEN_TO_DB_GRADE.values()) == {"shareable", "interesting", "neither"}


@pytest.mark.parametrize("week,n,grade,code", [
    (WEEK, 1, "great", 422),
    (WEEK, 11, "fun", 404),
    ("2026-w01", 1, "fun", 404),
])
async def test_bad_grades_and_unknown_screens_are_refused(wired, week, n, grade, code):
    with pytest.raises(HTTPException) as e:
        await admin.post_screen_grade(
            admin.ScreenGradeIn(week=week, n=n, grader="Alex", grade=grade), _request(), secret=None, db=FakeDB())
    assert e.value.status_code == code


async def test_the_first_grade_stands(wired):
    earlier = RankingGrade(slate_id=f"screens-{WEEK}", surface="screens", grader="Alex", expert=True,
                           position=2, item_key="screen:a2", grade="shareable")
    with pytest.raises(HTTPException) as e:
        await admin.post_screen_grade(
            admin.ScreenGradeIn(week=WEEK, n=2, grader="Alex", grade="fine"), _request(), secret=None,
            db=FakeDB([earlier]))
    assert e.value.status_code == 409


async def test_grades_come_back_beside_each_screens_counts(wired):
    rows = [RankingGrade(slate_id=f"screens-{WEEK}", surface="screens", grader="Alex", expert=True,
                         position=1, item_key="screen:a1", grade="shareable")]
    rows[0].graded_at, rows[0].id = datetime(2026, 1, 1), 1
    out = await admin.get_screen_grades(_request(), week=WEEK, secret=None, db=FakeDB(rows))
    first = out["screens"][0]
    assert first["counts"] == {"pictures": 1, "longest_run": 2}
    assert first["grades"] == {"Alex": "fun"}
    assert out["screens"][1]["grades"] == {}


def test_the_card_grade_read_leaves_out_screen_grades():
    src = inspect.getsource(admin.get_grades)
    assert "RankingGrade.surface != SURFACE_SCREENS" in src


def test_a_malformed_week_is_left_out(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({WEEK: {"screens": [{"id": "x"}]}, "not-a-week": {"screens": _screens("c")},
                                OLDER: {"screens": _screens("b")}}))
    assert set(admin.load_screen_samples(path)) == {OLDER}
