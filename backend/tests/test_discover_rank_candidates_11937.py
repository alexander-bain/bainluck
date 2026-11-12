"""#11937 (127-A stage 1): the two frozen Discover ranking candidates keep the
standing seating rules whatever their worth function says.

* a card failing a truth gate leaves the first page;
* a finished game keeps its served seat;
* two grouped cards are never adjacent when a single card can sit between them;
* no entity appears more than twice in the opening ten;
* nothing the feed did not serve is seated ahead of a served card;
* candidate 1 lifts grouped cards and story-key cards; candidate 2 follows the
  stored score with grouped cards lifted.
"""

from __future__ import annotations

from app.utils import discover_rank as dr


def card(n, kind="futures", **kw):
    base = {"item_key": f"k{n}", "type": kind, "served_position": n, "title": f"Card {n}",
            "category": "other", "entities": [f"e{n}"], "score": 50}
    base.update(kw)
    return base


def keys(order):
    return [c["item_key"] for c in order]


def test_a_gated_card_leaves_the_page():
    cards = [card(1), card(2, stale=True), card(3)]
    order = dr.rank_c2_score(cards)
    assert keys(order)[:2] == ["k1", "k3"] and keys(order)[2] == "k2"


def test_a_finished_game_keeps_its_served_seat():
    cards = [card(1), card(2), card(3, kind="event", settled=True), card(4, kind="bundle")]
    order = dr.rank_c2_score(cards)
    assert keys(order)[2] == "k3"


def test_grouped_cards_are_lifted_but_never_adjacent():
    cards = [card(1), card(2), card(3, kind="bundle"), card(4, kind="bundle")]
    order = keys(dr.rank_c2_score(cards))
    assert order[0] in {"k3", "k4"}
    for a, b in zip(order, order[1:]):
        assert not ({a, b} <= {"k3", "k4"})


def test_no_entity_more_than_twice_in_the_opening_ten():
    cards = [card(n, entities=["Same"]) for n in range(1, 5)] + [card(n) for n in range(5, 16)]
    order = dr.rank_c2_score(cards)
    assert sum("Same" in c["entities"] for c in order[:10]) == 2


def test_unserved_cards_stay_behind_the_served_ones():
    cards = [card(1), card(2), {**card(99, kind="bundle"), "served_position": None}]
    assert keys(dr.rank_c1_story(cards))[-1] == "k99"


def test_candidate_1_lifts_a_story_key_card_over_a_plain_one(monkeypatch):
    monkeypatch.setattr(dr, "has_story_key", lambda c: c["item_key"] == "k3")
    assert keys(dr.rank_c1_story([card(1), card(2), card(3)]))[0] == "k3"


def test_candidate_2_follows_the_stored_score_without_groups():
    cards = [card(1, score=10), card(2, score=90), card(3, score=50)]
    assert keys(dr.rank_c2_score(cards)) == ["k2", "k3", "k1"]


def test_the_frozen_weights():
    assert dr.GROUPED_WEIGHT == 1.0
    assert dr.STORY_KEY_GRID == (0.0, 0.5, 1.0, 2.0)
    assert dr.STORY_KEY_WEIGHT == 0.5
