"""#11937 (171-A): the blind side-by-side on /grade.

Alex, 8:41 AM PT Nov 12: on each graded morning he also sees two first tens for
the same slate, the served one and a candidate's, side by side and unlabelled,
and picks left, right or no difference. He must not be able to tell which is
which from the page, the URL or the order.

What must hold:
* ``GET /pair`` returns two sides of ten drawn cards each, carrying nothing but
  the drawing (no item keys, positions or scores);
* which side is the candidate is fixed per slate and pair, differs across pairs,
  and is not in the response;
* ``POST /pair-picks`` stores what the pick means (candidate, served or none);
  left on one pair and left on another can mean different things;
* an unknown pair is a 404, a pair naming cards the slate doesn't hold is a 422,
  an undrawn card in either ten is a 409;
* ``GET /pair-picks`` reads the picks back as meanings.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.routes.admin_ranking_eval as admin
from app.models.models import RankingGrade
from app.utils.ranking_eval import RANKING_SNAPSHOTS_ENV

SLATE_ID = "59da9307253a78dc"
SERVED = [f"futures:{i}" for i in range(1, 21)]
CANDIDATE = [SERVED[i] for i in (4, 0, 11, 2, 13, 1, 6, 15, 3, 9)]


def _cand(k, n):
    return {"item_key": k, "title": k, "served_position": n, "score": 100 - n,
            "card": {"type": "futures", "data": {"key": k}}}


SLATE = {"id": "row-12", "surface": "discover", "slate_id": SLATE_ID,
         "captured_at": "2026-11-12T15:15:00+00:00", "ranker_version": "x",
         "served_order": list(SERVED), "candidates": [_cand(k, n) for n, k in enumerate(SERVED, 1)],
         "summary": {}}


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

    async def slate_row(db, ref, surface):
        return SimpleNamespace(**SLATE)

    monkeypatch.setattr(admin, "_slate_row", slate_row)
    monkeypatch.setattr(admin, "slate_row_dict", lambda row: json.loads(json.dumps(SLATE)))
    monkeypatch.setenv(RANKING_SNAPSHOTS_ENV, "1")
    monkeypatch.setenv("ADMIN_TOKEN", "test-only")
    pairs = {SLATE_ID: {f"p{i}": CANDIDATE for i in range(1, 9)} | {"bad": ["futures:999"] * 10}}
    monkeypatch.setattr(admin, "load_pairs", lambda path=None: pairs)


async def _pair(name="p1"):
    return await admin.get_pair(_request(), slate=SLATE_ID, pair=name, surface="discover", secret=None, db=FakeDB())


async def test_two_unlabelled_sides_of_ten_drawings(wired):
    out = await _pair()
    assert set(out) == {"slate_id", "pair", "captured_at", "left", "right"}
    assert out["captured_at"] == SLATE["captured_at"]
    assert len(out["left"]) == len(out["right"]) == 10
    assert all(set(c) == {"card"} for c in out["left"] + out["right"])
    sides = {tuple(c["card"]["data"]["key"] for c in out[s]) for s in ("left", "right")}
    assert sides == {tuple(SERVED[:10]), tuple(CANDIDATE)}


async def test_the_side_is_fixed_per_pair_and_varies_across_pairs(wired):
    a, b = await _pair("p1"), await _pair("p1")
    assert a == b
    lefts = {admin.candidate_on_left(SLATE_ID, f"p{i}") for i in range(1, 9)}
    assert lefts == {True, False}  # random across pairs, not always one side


async def test_a_pick_is_stored_as_what_it_means(wired):
    picks = {}
    for name in ("p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"):
        db = FakeDB()
        body = admin.PairPickIn(slate_id=SLATE_ID, pair=name, grader="Alex Bain", choice="left", opened_discover_today=False)
        assert await admin.post_pair_pick(body, _request(), secret=None, db=db) == {"status": "ok"}
        (row,) = db.added
        assert isinstance(row, RankingGrade) and row.surface == "pair" and row.item_key == f"pair:{name}"
        expected = "candidate" if admin.candidate_on_left(SLATE_ID, name) else "served"
        assert admin._DB_TO_PAIR_PICK[row.grade] == expected
        picks[name] = expected
    assert set(picks.values()) == {"candidate", "served"}  # "left" means different things


async def test_no_difference_is_stored_as_none(wired):
    db = FakeDB()
    body = admin.PairPickIn(slate_id=SLATE_ID, pair="p1", grader="Alex Bain", choice="none", opened_discover_today=True)
    await admin.post_pair_pick(body, _request(), secret=None, db=db)
    assert admin._DB_TO_PAIR_PICK[db.added[0].grade] == "none"


async def test_refusals(wired, monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await _pair("nope")
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        await _pair("bad")
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        await admin.post_pair_pick(admin.PairPickIn(slate_id=SLATE_ID, pair="p1", grader="A", choice="up", opened_discover_today=False),
                                   _request(), secret=None, db=FakeDB())
    assert exc.value.status_code == 422
    undrawn = json.loads(json.dumps(SLATE))
    undrawn["candidates"][0]["card"] = None
    monkeypatch.setattr(admin, "slate_row_dict", lambda row: undrawn)
    with pytest.raises(HTTPException) as exc:
        await _pair("p1")
    assert exc.value.status_code == 409


def _pick_row(grade, minute, note, rid):
    return SimpleNamespace(slate_id=SLATE_ID, surface="pair", grader="Alex Bain", expert=True, position=1,
                           item_key="pair:p1", grade=grade, note=note,
                           graded_at=datetime(2026, 11, 13, 16, minute, tzinfo=timezone.utc), id=rid)


async def test_picks_read_back_as_meanings_and_the_first_one_stands(wired):
    rows = [_pick_row("neither", 5, "opened_discover_today=yes", 2),
            _pick_row("shareable", 0, "opened_discover_today=no", 1)]
    out = await admin.get_pair_picks(_request(), slate_id=SLATE_ID, days=30, secret=None, db=FakeDB(rows))
    (pick,) = out["picks"]
    assert pick["pick"] == "candidate" and pick["pair"] == "p1"
    assert pick["opened_discover_today"] is False


async def test_a_second_pick_for_the_same_pair_is_refused(wired):
    earlier = [_pick_row("shareable", 0, "opened_discover_today=no", 1)]
    db = FakeDB(earlier)
    body = admin.PairPickIn(slate_id=SLATE_ID, pair="p1", grader="Alex Bain", choice="right",
                            opened_discover_today=False)
    with pytest.raises(HTTPException) as exc:
        await admin.post_pair_pick(body, _request(), secret=None, db=db)
    assert exc.value.status_code == 409 and db.added == []


async def test_the_opened_discover_answer_is_stored_with_the_pick(wired):
    db = FakeDB()
    body = admin.PairPickIn(slate_id=SLATE_ID, pair="p2", grader="Alex Bain", choice="none",
                            opened_discover_today=True)
    await admin.post_pair_pick(body, _request(), secret=None, db=db)
    assert db.added[0].note == "opened_discover_today=yes"


@pytest.mark.parametrize("slate_id", [None, SLATE_ID])
async def test_picks_never_come_back_as_card_grades(wired, slate_id):
    db = FakeDB()
    await admin.get_grades(_request(), slate_id=slate_id, days=14, secret=None, db=db)
    compiled = db.statements[0].compile()
    assert "ranking_grades.surface !=" in str(compiled)
    assert "pair" in compiled.params.values()


def test_the_shipped_pairs_file_is_valid():
    data = json.loads(admin.PAIRS_PATH.read_text())
    for slate_id, pairs in data.items():
        for name, keys in pairs.items():
            assert isinstance(keys, list) and len(keys) == 10, (slate_id, name)


async def test_default_morning_pair_computes_frozen_candidate_without_pairs_file(wired, monkeypatch):
    """#11937: one link (/grade/pair with no query params) computes today's blind pair
    from the frozen candidate on the server when ranking_pairs.json has no entry."""
    monkeypatch.setattr(admin, "load_pairs", lambda path=None: {})
    # Pretend SLATE was captured today (PT).
    monkeypatch.setattr(admin, "_captured_today_pt", lambda captured_at, now=None: True)
    out = await admin.get_pair(_request(), slate="latest", pair="p1", surface="discover", secret=None, db=FakeDB())
    assert set(out) == {"slate_id", "pair", "captured_at", "left", "right"}
    assert out["slate_id"] == SLATE_ID and out["pair"] == "p1"
    assert len(out["left"]) == len(out["right"]) == 10
    assert all(set(c) == {"card"} for c in out["left"] + out["right"])
    # Pick against the server-computed pair is accepted and stored by meaning.
    db = FakeDB()
    body = admin.PairPickIn(
        slate_id=SLATE_ID, pair="p1", grader="Alex Bain", choice="left", opened_discover_today=False
    )
    assert await admin.post_pair_pick(body, _request(), secret=None, db=db) == {"status": "ok"}
    assert len(db.added) == 1 and db.added[0].item_key == "pair:p1"
    # Unknown pair names still 404.
    with pytest.raises(HTTPException) as exc:
        await admin.get_pair(_request(), slate="latest", pair="unknown", surface="discover", secret=None, db=FakeDB())
    assert exc.value.status_code == 404


async def test_morning_pair_and_deck_refuse_yesterdays_slate_before_715am(wired, monkeypatch):
    """Fable look on #13022: before today's 7:15 AM PT capture, default morning
    Step 1 (/pair) and Step 2 (/grade-deck?slate=today) must refuse yesterday's slate."""
    monkeypatch.setattr(admin, "load_pairs", lambda path=None: {})
    # 6:50 AM PT on 2026-11-13 vs SLATE captured 2026-11-12 7:15 AM PT -> yesterday!
    early_morning = datetime(2026, 11, 13, 14, 50, tzinfo=timezone.utc)
    orig = admin._captured_today_pt
    monkeypatch.setattr(admin, "_captured_today_pt", lambda ts, now=None: orig(ts, now=early_morning))

    with pytest.raises(HTTPException) as exc_pair:
        await admin.get_pair(_request(), slate="latest", pair="p1", surface="discover", secret=None, db=FakeDB())
    assert exc_pair.value.status_code == 409
    assert exc_pair.value.detail == admin.MORNING_NOT_READY_DETAIL

    with pytest.raises(HTTPException) as exc_deck:
        await admin.get_grade_deck(_request(), surface="discover", slate="today", secret=None, db=FakeDB())
    assert exc_deck.value.status_code == 409
    assert exc_deck.value.detail == admin.MORNING_NOT_READY_DETAIL

    # Same day at 7:20 AM PT on 2026-11-12 -> allowed!
    after_capture = datetime(2026, 11, 12, 15, 20, tzinfo=timezone.utc)
    monkeypatch.setattr(admin, "_captured_today_pt", lambda ts, now=None: orig(ts, now=after_capture))
    out = await admin.get_pair(_request(), slate="latest", pair="p1", surface="discover", secret=None, db=FakeDB())
    assert out["slate_id"] == SLATE_ID and out["captured_at"] == SLATE["captured_at"]
    deck = await admin.get_grade_deck(_request(), surface="discover", slate="today", secret=None, db=FakeDB())
    assert deck["slate_id"] == SLATE_ID and deck["mode"] == "spread"


def test_frozen_discover_rank_sha256_matches_recorded_freeze():
    import hashlib
    from pathlib import Path
    rank_path = Path(admin.__file__).resolve().parents[1] / "utils" / "discover_rank.py"
    digest = hashlib.sha256(rank_path.read_bytes()).hexdigest()
    assert digest == "1c5b8e3685e53a4dc519ec5c188cdc3a76e109bb94edfaf0a698ea6cf30bdb71"
