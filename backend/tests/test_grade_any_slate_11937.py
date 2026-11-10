"""#11937 (127-A): /grade can open a saved slate and deal the cards the scorer needs.

Fable, 12:06 PM PT Nov 10: Alex grades about 50 cards this week (Nov 10: 30;
Nov 9: 20 more below the ten he did), and today's page can't collect them. It
loads only the latest slate's opening ten, and ``POST /grades`` caps the
position at those ten. So Nov 9's ten grades can't judge a ranker change: any
replay that reorders deeper cards reads UNKNOWN.

What must hold:
* ``GET /grade-deck?slate=<date or id>`` opens that saved slate;
* its deck is about 30 cards spread down the candidate list, the SAME cards
  each time for a slate, minus the ones this grader already graded there;
* ``POST /grades`` accepts any card on that list at its list position, so
  grades land where they do now and ``grades.py export`` picks them up;
* with no ``slate``, the deck is the latest opening ten, exactly as before.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.routes.admin_ranking_eval as admin
from app.models.models import RankingGrade
from app.utils.ranking_eval import RANKING_SNAPSHOTS_ENV

# 12 served cards, then 60 candidates that were not served, scored 60..1.
SERVED = [f"futures:{i}" for i in range(1, 13)]
UNSERVED = [f"futures:{i}" for i in range(13, 73)]
SLATE = {
    "id": "row-9",
    "surface": "discover",
    "slate_id": "327293405b250480",
    "captured_at": "2026-11-09T15:15:00+00:00",
    "ranker_version": "c7ce859d5402",
    "served_order": list(SERVED),
    "candidates": (
        [{"item_key": k, "title": k, "probability": 0.5, "served_position": n,
          "score": 100 - n, "card": {"type": "futures", "data": {"key": k}}}
         for n, k in enumerate(SERVED, start=1)]
        # Listed in a shuffled order on purpose: the deck must not depend on it.
        + [{"item_key": k, "title": k, "probability": 0.4, "served_position": None,
            "score": 73 - int(k.split(":")[1]), "card": {"type": "futures", "data": {"key": k}}}
           for k in reversed(UNSERVED)]
    ),
    "summary": {},
}


def _request(grader: str | None = None):
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
    """Answers the graded-keys read with ``graded`` rows; records adds."""

    def __init__(self, graded=()):
        self.graded = list(graded)
        self.added, self.commits = [], 0

    async def execute(self, stmt):
        return _Rows(self.graded)

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.commits += 1


@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setattr(admin, "_check_admin_secret", lambda *a, **k: True)
    seen = {}

    async def slate_row(db, ref, surface):
        seen["ref"] = ref
        return SimpleNamespace(**SLATE)

    monkeypatch.setattr(admin, "_slate_row", slate_row)
    monkeypatch.setattr(admin, "slate_row_dict", lambda row: dict(SLATE))
    monkeypatch.setenv(RANKING_SNAPSHOTS_ENV, "1")
    return seen


class TestTheCandidateList:
    def test_served_cards_first_then_the_rest_by_score(self):
        order = admin.candidate_order(SLATE)
        assert [c["item_key"] for c in order[:12]] == SERVED
        assert [c["item_key"] for c in order[12:]] == UNSERVED  # score 60..1
        assert [c["position"] for c in order] == list(range(1, 73))

    def test_a_served_card_keeps_its_served_position(self):
        # So the opening ten graded before this change keep their positions.
        order = {c["item_key"]: c["position"] for c in admin.candidate_order(SLATE)}
        assert all(order[k] == n for n, k in enumerate(SERVED, start=1))


class TestTheSpreadDeck:
    def test_the_top_twenty_whole_then_ten_spread_to_the_bottom_the_same_each_time(self):
        deck = admin.spread_deck(admin.candidate_order(SLATE), size=30)
        again = admin.spread_deck(admin.candidate_order(SLATE), size=30)
        assert [c["item_key"] for c in deck] == [c["item_key"] for c in again]
        assert len(deck) == 30
        # The served top is graded whole, so the order readers saw can be scored.
        assert [c["position"] for c in deck[:20]] == list(range(1, 21))
        tail = [c["position"] for c in deck[20:]]
        assert tail[0] == 21 and tail[-1] == 72
        gaps = [b - a for a, b in zip(tail, tail[1:])]
        assert min(gaps) >= 5 and max(gaps) <= 6  # spread, not bunched

    def test_a_short_list_is_dealt_whole(self):
        order = admin.candidate_order(SLATE)[:20]
        assert len(admin.spread_deck(order, size=30)) == 20

    def test_already_graded_cards_are_skipped_and_the_rest_unchanged(self):
        order = admin.candidate_order(SLATE)
        full = admin.spread_deck(order, size=30)
        graded = {full[0]["item_key"], full[5]["item_key"]}
        rest = admin.spread_deck(order, size=30, skip=graded)
        assert [c["item_key"] for c in rest] == [c["item_key"] for c in full if c["item_key"] not in graded]


class TestTheDeckEndpoint:
    async def test_a_named_slate_deals_the_spread_with_cards(self, wired):
        deck = await admin.get_grade_deck(_request(), surface="discover", slate="2026-11-09",
                                          size=30, secret=None, db=FakeDB())
        assert wired["ref"] == "2026-11-09"
        assert deck["slate_id"] == "327293405b250480" and deck["mode"] == "spread"
        assert len(deck["items"]) == 30 and deck["candidates"] == 72
        assert deck["items"][-1]["card"] == {"type": "futures", "data": {"key": "futures:72"}}

    async def test_it_skips_what_this_grader_already_graded(self, wired):
        graded = [SimpleNamespace(item_key="futures:1"), SimpleNamespace(item_key="futures:3")]
        deck = await admin.get_grade_deck(_request(" Alex%20%20Bain "), surface="discover",
                                          slate="327293405b250480", size=30, secret=None, db=FakeDB(graded))
        keys = [i["item_key"] for i in deck["items"]]
        assert "futures:1" not in keys and "futures:3" not in keys
        assert deck["already_graded"] == 2

    async def test_nov_9s_ten_done_leave_twenty(self, wired):
        # Alex graded Nov 9's opening ten; the deck is the other 20.
        graded = [SimpleNamespace(item_key=k) for k in SERVED[:10]]
        deck = await admin.get_grade_deck(_request("Alex Bain"), surface="discover",
                                          slate="327293405b250480", size=30, secret=None, db=FakeDB(graded))
        assert len(deck["items"]) == 20 and deck["items"][0]["position"] == 11

    def test_the_grader_name_is_never_a_query_parameter(self):
        import inspect

        assert "grader" not in inspect.signature(admin.get_grade_deck).parameters

    async def test_no_slate_is_still_the_latest_opening_ten(self, wired):
        deck = await admin.get_grade_deck(_request(), surface="discover", slate=None,
                                          size=30, secret=None, db=FakeDB())
        assert wired["ref"] == "latest"
        assert [i["position"] for i in deck["items"]] == list(range(1, 11))


def _grade(**kw):
    body = {"slate_id": "327293405b250480", "grader": "Alex Bain", "kid": False,
            "position": 12, "item_key": "futures:12", "grade": "interesting"}
    body.update(kw)
    return admin.GradeIn(**body)


class TestGradingDeeperCards:
    async def test_a_served_card_below_the_ten_is_accepted(self, wired):
        db = FakeDB()
        assert await admin.post_grade(_grade(), _request(), secret=None, db=db) == {"status": "ok"}
        (row,) = db.added
        assert isinstance(row, RankingGrade) and (row.position, row.item_key) == (12, "futures:12")

    async def test_an_unserved_candidate_is_accepted_at_its_list_position(self, wired):
        db = FakeDB()
        await admin.post_grade(_grade(position=60, item_key="futures:60"), _request(), secret=None, db=db)
        assert db.added[0].position == 60

    @pytest.mark.parametrize("kw", [{"position": 61, "item_key": "futures:60"},
                                    {"position": 73, "item_key": "futures:73"}])
    async def test_a_card_not_at_that_list_position_is_refused(self, wired, kw):
        db = FakeDB()
        with pytest.raises(HTTPException) as exc:
            await admin.post_grade(_grade(**kw), _request(), secret=None, db=db)
        assert exc.value.status_code == 422 and db.added == []


class TestADateNamesAPacificDay:
    def test_the_bounds_are_that_day_in_pacific_time(self):
        start, end = admin.slate_date_bounds("2026-11-09")
        assert start == datetime(2026, 11, 9, 8, 0, tzinfo=timezone.utc)
        assert end == datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc)

    @pytest.mark.parametrize("ref", ["latest", "327293405b250480", "row-9", "2026-13-40"])
    def test_anything_else_is_not_a_date(self, ref):
        assert admin.slate_date_bounds(ref) is None
