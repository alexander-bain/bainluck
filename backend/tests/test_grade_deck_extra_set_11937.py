"""#11937 (159-A): /grade deals a named extra set of cards, mixed in and unlabeled.

Alex, 2:39 PM PT Wed Nov 11: after ranking candidates are frozen, the cards in
their first tens that he never graded join that slate's grading page, mixed in
and unlabeled, so he cannot tell which order they came from. One round covers
all candidates.

What must hold:
* ``GET /grade-deck?slate=<id>&set=<name>`` deals the slate's usual deck plus the
  set's cards, each card once;
* the deck's order says nothing about where a card came from: it is a fixed
  hash order, and no item carries a flag;
* cards this grader already graded are skipped, as on the usual deck;
* an unknown set is a 404, a set naming a card the slate doesn't hold is a 422,
  and a set without ``slate`` is a 422;
* with no ``set``, the deck is exactly what it was.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.routes.admin_ranking_eval as admin
from app.utils.ranking_eval import RANKING_SNAPSHOTS_ENV

SERVED = [f"futures:{i}" for i in range(1, 13)]
UNSERVED = [f"futures:{i}" for i in range(13, 73)]
SLATE = {
    "id": "row-11",
    "surface": "discover",
    "slate_id": "c5a077361cd9e2dc",
    "captured_at": "2026-11-11T15:15:00+00:00",
    "ranker_version": "c7ce859d5402",
    "served_order": list(SERVED),
    "candidates": (
        [{"item_key": k, "title": k, "probability": 0.5, "served_position": n, "score": 100 - n,
          "card": {"type": "futures", "data": {"key": k}}} for n, k in enumerate(SERVED, start=1)]
        + [{"item_key": k, "title": k, "probability": 0.4, "served_position": None,
            "score": 73 - int(k.split(":")[1]), "card": {"type": "futures", "data": {"key": k}}}
           for k in UNSERVED]
    ),
    "summary": {},
}
# Two cards the usual deck doesn't deal (positions 25, 40) and one it does (5).
EXTRA = ["futures:25", "futures:40", "futures:5"]


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

    async def execute(self, stmt):
        return _Rows(self.graded)


@pytest.fixture
def wired(monkeypatch, tmp_path):
    monkeypatch.setattr(admin, "_check_admin_secret", lambda *a, **k: True)

    async def slate_row(db, ref, surface):
        return SimpleNamespace(**SLATE)

    monkeypatch.setattr(admin, "_slate_row", slate_row)
    monkeypatch.setattr(admin, "slate_row_dict", lambda row: dict(SLATE))
    monkeypatch.setenv(RANKING_SNAPSHOTS_ENV, "1")
    sets = tmp_path / "sets.json"
    sets.write_text(json.dumps({"c5a077361cd9e2dc": {"round-1": EXTRA, "typo": ["futures:999"]}}))
    monkeypatch.setattr(admin, "EXTRA_SETS_PATH", sets)
    monkeypatch.setattr(admin, "load_extra_sets", lambda path=sets: json.loads(sets.read_text()))


async def _deck(**kw):
    args = dict(surface="discover", slate="2026-11-11", size=30, card_set=None, secret=None, db=FakeDB())
    args.update(kw)
    grader = args.pop("grader", None)
    return await admin.get_grade_deck(_request(grader), **args)


class TestTheSet:
    async def test_the_usual_deck_plus_the_set_each_card_once(self, wired):
        usual = await _deck()
        withset = await _deck(card_set="round-1")
        usual_keys = {i["item_key"] for i in usual["items"]}
        keys = [i["item_key"] for i in withset["items"]]
        assert len(keys) == len(set(keys)) == 32
        assert set(keys) == usual_keys | set(EXTRA)

    async def test_the_order_is_a_fixed_hash_order_with_no_flag(self, wired):
        a = await _deck(card_set="round-1")
        b = await _deck(card_set="round-1")
        assert [i["item_key"] for i in a["items"]] == [i["item_key"] for i in b["items"]]
        # Not the usual top-then-spread order, and nothing marks a set card.
        assert [i["position"] for i in a["items"]] != sorted(i["position"] for i in a["items"])
        assert all(set(i) == {"position", "item_key", "title", "probability", "card"} for i in a["items"])
        assert "set" not in a and a["mode"] == "spread"

    async def test_already_graded_cards_are_skipped(self, wired):
        graded = [SimpleNamespace(item_key="futures:25"), SimpleNamespace(item_key="futures:1")]
        deck = await _deck(card_set="round-1", grader="Alex Bain", db=FakeDB(graded))
        keys = {i["item_key"] for i in deck["items"]}
        assert "futures:25" not in keys and "futures:1" not in keys and "futures:40" in keys
        assert deck["already_graded"] == 2


class TestRefusals:
    async def test_an_unknown_set_is_a_404(self, wired):
        with pytest.raises(HTTPException) as exc:
            await _deck(card_set="nope")
        assert exc.value.status_code == 404

    async def test_a_set_naming_a_card_not_on_the_slate_is_a_422(self, wired):
        with pytest.raises(HTTPException) as exc:
            await _deck(card_set="typo")
        assert exc.value.status_code == 422 and "futures:999" in exc.value.detail

    async def test_a_set_needs_a_slate(self, wired):
        with pytest.raises(HTTPException) as exc:
            await _deck(slate=None, card_set="round-1")
        assert exc.value.status_code == 422


async def test_with_no_set_the_deck_is_unchanged(wired):
    deck = await _deck()
    assert deck["items"] == [dict(c) for c in admin.spread_deck(admin.candidate_order(SLATE), size=30)]


def test_the_shipped_sets_file_is_valid():
    data = admin.load_extra_sets()
    assert isinstance(data, dict)
    for slate_id, sets in data.items():
        assert isinstance(sets, dict)
        for name, keys in sets.items():
            assert isinstance(keys, list) and all(isinstance(k, str) for k in keys), (slate_id, name)
