"""#11937: the grading page never deals a card it can't draw.

Fable, 10:11 PM PT Tue Nov 10: slates captured before every card was kept
store a drawing for the opening ten only, and ``/grade`` dealt the rest as a
title with a bare percent, or nothing at all. Alex graded 50 of those boxes on
the Nov 9 and Nov 10 slates, and none of those grades can count. Keeping every
drawing fixes new slates, but an old slate, a failed capture or a card kind the
capture misses would bring the blank box back.

What must hold:
* a card with no stored drawing is left out of the deck, in both decks;
* the deck says how many it left out, so the page can say so;
* the cards that are dealt keep their list positions;
* ``POST /grades`` refuses a grade on a card with no drawing, so a stale tab
  can't save one either.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.routes.admin_ranking_eval as admin
from app.utils.ranking_eval import RANKING_SNAPSHOTS_ENV

# Nov 10's shape: 12 served cards, 60 more candidates, and only the opening ten
# carry a drawing (the capture kept payloads for those alone).
SERVED = [f"futures:{i}" for i in range(1, 13)]
UNSERVED = [f"futures:{i}" for i in range(13, 73)]


def _cand(key, position, score, drawn):
    c = {"item_key": key, "title": key, "probability": 0.5, "served_position": position, "score": score}
    if drawn:
        c["card"] = {"type": "futures", "data": {"key": key}}
    return c


SLATE = {
    "id": "row-10",
    "surface": "discover",
    "slate_id": "15f9c0798c113275",
    "captured_at": "2026-11-10T15:15:00+00:00",
    "ranker_version": "c7ce859d5402",
    "served_order": list(SERVED),
    "candidates": (
        [_cand(k, n, 100 - n, drawn=n <= 10) for n, k in enumerate(SERVED, start=1)]
        + [_cand(k, None, 73 - int(k.split(":")[1]), drawn=False) for k in UNSERVED]
    ),
    "summary": {},
}


def _request(grader=None):
    headers = [(b"x-grader-name", grader.encode())] if grader else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "query_string": b""})


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class FakeDB:
    def __init__(self, graded=()):
        self.graded = list(graded)
        self.added, self.commits = [], 0

    async def execute(self, stmt):
        return _Rows(self.graded)

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.commits += 1


def _wire(monkeypatch, slate):
    monkeypatch.setattr(admin, "_check_admin_secret", lambda *a, **k: True)

    async def slate_row(db, ref, surface):
        return SimpleNamespace(**slate)

    monkeypatch.setattr(admin, "_slate_row", slate_row)
    monkeypatch.setattr(admin, "slate_row_dict", lambda row: dict(slate))
    monkeypatch.setenv(RANKING_SNAPSHOTS_ENV, "1")


@pytest.fixture
def wired(monkeypatch):
    _wire(monkeypatch, SLATE)


class TestTheSpreadDeck:
    async def test_only_drawn_cards_are_dealt_and_the_rest_are_counted(self, wired):
        deck = await admin.get_grade_deck(_request(), surface="discover", slate="2026-11-10",
                                          size=30, secret=None, db=FakeDB())
        assert [i["position"] for i in deck["items"]] == list(range(1, 11))
        assert all(i["card"] for i in deck["items"])
        assert deck["left_out_no_drawing"] == 20

    async def test_cards_already_graded_are_not_counted_as_left_out(self, wired):
        # Alex graded all 30 of Nov 10's deck: nothing is dealt, nothing is "left out".
        full = admin.spread_deck(admin.candidate_order(SLATE), size=30)
        graded = [SimpleNamespace(item_key=c["item_key"]) for c in full]
        deck = await admin.get_grade_deck(_request("Alex Bain"), surface="discover",
                                          slate="15f9c0798c113275", size=30, secret=None, db=FakeDB(graded))
        assert deck["items"] == [] and deck["left_out_no_drawing"] == 0

    async def test_a_fully_drawn_slate_leaves_nothing_out(self, monkeypatch):
        drawn = dict(SLATE, candidates=[dict(c, card={"type": "futures", "data": {}}) for c in SLATE["candidates"]])
        _wire(monkeypatch, drawn)
        deck = await admin.get_grade_deck(_request(), surface="discover", slate="2026-11-10",
                                          size=30, secret=None, db=FakeDB())
        assert len(deck["items"]) == 30 and deck["left_out_no_drawing"] == 0


class TestTheOpeningDeck:
    async def test_a_served_card_with_no_drawing_is_left_out(self, monkeypatch):
        cands = [dict(c) for c in SLATE["candidates"]]
        cands[2].pop("card")  # position 3 lost its drawing
        cands[6]["card"] = {}  # position 7 stored an empty one
        _wire(monkeypatch, dict(SLATE, candidates=cands))
        deck = await admin.get_grade_deck(_request(), surface="discover", slate=None,
                                          size=30, secret=None, db=FakeDB())
        assert [i["position"] for i in deck["items"]] == [1, 2, 4, 5, 6, 8, 9, 10]
        assert deck["left_out_no_drawing"] == 2


def _grade(**kw):
    body = {"slate_id": "15f9c0798c113275", "grader": "Alex Bain", "kid": False,
            "position": 12, "item_key": "futures:12", "grade": "interesting"}
    body.update(kw)
    return admin.GradeIn(**body)


class TestGrading:
    async def test_a_grade_on_a_card_with_no_drawing_is_refused(self, wired):
        db = FakeDB()
        with pytest.raises(HTTPException) as exc:
            await admin.post_grade(_grade(), _request(), secret=None, db=db)
        assert exc.value.status_code == 422 and db.added == [] and db.commits == 0

    async def test_a_grade_on_a_drawn_card_is_saved(self, wired):
        db = FakeDB()
        assert await admin.post_grade(_grade(position=10, item_key="futures:10"), _request(),
                                      secret=None, db=db) == {"status": "ok"}
        assert db.added[0].position == 10
