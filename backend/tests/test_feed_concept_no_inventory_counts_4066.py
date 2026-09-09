"""A concept card never counts our own inventory, and never serves one bout twice.

Ship D1 of PROGRAM-DISCOVER, issue #4066. Alex read page one on his phone on
2026-09-08 and named two defects in the fight cards:

  1. "one said '2 fights on this card' — a UFC card never has two fights (that is
     OUR attached-market count, not the fight count: never print an ingest count
     as a fact about the world)"
  2. "the same fight, Pasley vs Berisha, appears TWICE as two cards with two
     numbers (59% and 57%)"

Both reproduced on production the same afternoon at
`GET /api/feed?limit=40&offset=0..80`. The concept payloads below are those rows,
verbatim, and they are the fixtures — a guard against the copy that Alex actually
read, not a paraphrase of it.

The two defects share a cause. `list_card_concepts` split the Sept 8/9 card in
half (root cause #4093, against ux/#1712 — the rollover fold's contiguity
test mixes Kalshi close times into the span, gotcha #14), and `fight_count` then
reported each half's row count as the card's size: 5 and 8. So the count was not
merely unmeasured, it was measurably wrong, and the halves each carried their own
probability for the same bout.

The fix does not chase the splitter. It removes the two claims the feed was never
entitled to make: a count of the world it never measured, and a second card for a
bout it already served.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.routes.feed import (
    _concept_bout_key,
    _concept_main_event,
    _concept_reason,
    _drop_duplicate_bout_concepts,
    _score_event_concepts,
)

# ---------------------------------------------------------------------------
# Production payloads, 2026-09-08 ~22:5xZ, GET /api/feed?limit=40.
# ---------------------------------------------------------------------------

#: The Kalshi-named half of the Sept 8/9 card. Carries the priced main event.
SEP08 = {
    "key": "event:ufc:26sep08",
    "name": "MMA: Pasley vs Berisha",
    "domain": "ufc",
    "status": "live",
    "fight_count": 5,
    "entry_count": 0,
    "leader": {"name": "Arlind Berisha", "probability": 0.585, "field_size": 2},
    "headline_bout": {
        "competitors": [
            {"name": "Arlind Berisha", "probability": 0.575},
            {"name": "Quentin Pasley", "probability": 0.425},
        ],
        "commence_time": "2026-09-09T05:20:00+00:00",
    },
}

#: The events-table half of the SAME card. Surnames only, no priced bout, a
#: different row count and a different number for the same fight.
SEP09 = {
    "key": "event:ufc:26sep09",
    "name": "Pasley vs Berisha",
    "domain": "ufc",
    "status": "live",
    "fight_count": 8,
    "entry_count": 0,
    "leader": {"name": "Berisha", "probability": 0.575, "field_size": 2},
}

#: The card whose subtitle Alex quoted. Two rows held; a real UFC card has ten
#: to thirteen fights.
SEP11 = {
    "key": "event:ufc:26sep11",
    "name": "Neemias Santana vs Shawn Marcos Da Silva",
    "domain": "ufc",
    "status": "upcoming",
    "fight_count": 2,
    "entry_count": 0,
    "leader": {"name": "Neemias Santana", "probability": 0.8737, "field_size": 2},
}

#: Not a fight card, and its subtitle counted markets in the same way.
VUELTA = {
    "key": "event:cycling:vuelta-2026",
    "name": "Vuelta a España 2026",
    "domain": "cycling",
    "status": "live",
    "fight_count": 0,
    "entry_count": 13,
}

MONZA = {
    "key": "event:f1:italian-gp-2026",
    "name": "Italian Grand Prix: Driver Winner",
    "domain": "f1",
    "status": "upcoming",
    "fight_count": 0,
    "entry_count": 14,
}

ALL_LIVE_CONCEPTS = [SEP08, SEP09, SEP11, VUELTA, MONZA]


def _as_item(data: dict, score: int) -> dict:
    return {
        "type": "concept",
        "score": score,
        "reason": _concept_reason(data),
        "data": data,
    }


class TestNoInventoryCountInTheCopy:
    """The subtitle never states a number we did not measure."""

    @pytest.mark.parametrize("data", ALL_LIVE_CONCEPTS, ids=lambda d: d["key"])
    def test_no_served_count_appears_in_the_reason(self, data):
        reason = _concept_reason(data)
        for count in (data.get("fight_count"), data.get("entry_count")):
            if count:
                assert str(count) not in reason, (
                    f"{data['key']} published its own row count {count!r} as a fact "
                    f"about the world: {reason!r}"
                )

    def test_the_exact_line_alex_read_is_gone(self):
        # Not "no digits" — the sentence. A reader saw this string.
        assert _concept_reason(SEP11) != "2 fights on the card"
        assert "fights on the card" not in _concept_reason(SEP11)
        assert "fights on the card" not in _concept_reason(SEP08)

    @pytest.mark.parametrize("data", ALL_LIVE_CONCEPTS, ids=lambda d: d["key"])
    def test_no_inventory_noun_survives_anywhere(self, data):
        # "13 race markets" / "14 weekend markets" are the same defect wearing a
        # different noun — the lane's ship is "page one stops counting its own
        # inventory", and a market count is inventory.
        reason = _concept_reason(data).lower()
        assert "market" not in reason
        assert not any(ch.isdigit() for ch in reason), reason

    def test_a_numbered_card_still_earns_a_subtitle(self):
        # The counts go; the card does not go silent when it has something true
        # and non-duplicative to say. "UFC 329" does not name its main event, so
        # the subtitle does.
        assert (
            _concept_reason(
                {
                    "domain": "ufc",
                    "name": "UFC 329",
                    "fight_count": 11,
                    "headline_bout": {
                        "competitors": [
                            {"name": "Alexandre Pantoja"},
                            {"name": "Joshua Van"},
                        ]
                    },
                }
            )
            == "Main event: Alexandre Pantoja vs Joshua Van"
        )


class TestOneFightNightIsOneCard:
    """The bout Alex saw twice is served once."""

    def test_the_two_halves_share_one_identity(self):
        # The whole dedup rests on this: the two sources spell the fighters
        # differently and only one of them prices the bout.
        assert _concept_main_event(SEP08) == ["Arlind Berisha", "Quentin Pasley"]
        assert _concept_main_event(SEP09) == ["Pasley", "Berisha"]
        assert _concept_bout_key(SEP08) == _concept_bout_key(SEP09)

    def test_only_one_pasley_berisha_card_is_served(self):
        kept = _drop_duplicate_bout_concepts(
            [_as_item(SEP08, 89), _as_item(SEP09, 88), _as_item(SEP11, 45)]
        )
        keys = [i["data"]["key"] for i in kept]
        assert keys == ["event:ufc:26sep08", "event:ufc:26sep11"]

    def test_the_keeper_is_the_half_that_can_render_the_bout(self):
        # Both orderings and both score directions. The richer half wins even
        # when it scores LOWER — which is the case that matters, because
        # `_score_event_concept`'s card-size bonus reads `fight_count`, so the
        # half holding more of our rows (8 vs 5) is the one the score favours.
        for pool in (
            [_as_item(SEP08, 89), _as_item(SEP09, 88)],
            [_as_item(SEP09, 88), _as_item(SEP08, 89)],
            [_as_item(SEP08, 84), _as_item(SEP09, 88)],
            [_as_item(SEP09, 88), _as_item(SEP08, 84)],
        ):
            kept = _drop_duplicate_bout_concepts(pool)
            assert len(kept) == 1
            assert kept[0]["data"]["key"] == "event:ufc:26sep08"
            assert kept[0]["data"].get("headline_bout")

    def test_a_tie_between_equals_keeps_the_first_and_is_deterministic(self):
        # Neither half priced: nothing to prefer, so position decides and the
        # result does not depend on dict or scan order.
        bare_a = {**SEP09, "key": "event:ufc:a"}
        bare_b = {**SEP09, "key": "event:ufc:b"}
        pool = [_as_item(bare_a, 88), _as_item(bare_b, 88)]
        assert [i["data"]["key"] for i in _drop_duplicate_bout_concepts(pool)] == [
            "event:ufc:a"
        ]

    def test_order_is_otherwise_preserved(self):
        # A filter over the candidate pool, never a re-rank — a dedup that also
        # reordered would move cards nobody complained about.
        pool = [_as_item(SEP11, 45), _as_item(VUELTA, 80), _as_item(SEP08, 89)]
        assert [i["data"]["key"] for i in _drop_duplicate_bout_concepts(pool)] == [
            d["key"] for d in (SEP11, VUELTA, SEP08)
        ]


class TestTheFeedActuallyAppliesIt:
    """The serving path, not just the helper.

    The first draft of this file tested `_drop_duplicate_bout_concepts` and
    `_concept_reason` directly and nothing else — so deleting the ONE call site
    in `_score_event_concepts` left all 21 tests green while production served
    both Pasley cards again. A guard on a helper is a guard on nothing until it
    also proves the helper is reached.
    """

    @pytest.mark.asyncio
    async def test_the_served_concept_tier_dedups_and_never_counts(self, monkeypatch):
        now = datetime.now(timezone.utc)
        soon = now + timedelta(hours=6)

        # The two halves as `list_card_concepts` emits them, plus the card whose
        # subtitle Alex quoted.
        listed = []
        for data, key in ((SEP08, "26sep08"), (SEP09, "26sep09"), (SEP11, "26sep11")):
            c = dict(data)
            c["status"] = "upcoming"
            c["is_major"] = False
            c["start_date"] = soon.isoformat()
            c["latest_commence"] = soon
            listed.append(c)

        import app.utils.event_concept_population as pop

        async def _fake_list_all_concepts(db, **_kw):
            return [dict(c) for c in listed]

        monkeypatch.setattr(pop, "list_all_concepts", _fake_list_all_concepts)

        # Both resolvers are cache reads; neither is under test here. A leader
        # keeps every card past `_concept_can_render` so nothing is dropped for
        # a reason this test is not asking about.
        async def _fake_leader(_db, key):
            # (leader, bout) since #3058 — no bout, so these cards keep the exact
            # one-line shape this test was written against.
            return {"name": "Arlind Berisha", "probability": 0.58, "field_size": 2}, None

        async def _fake_champion(_db, _key):
            return None

        monkeypatch.setattr("app.routes.feed._resolve_concept_leader", _fake_leader)
        monkeypatch.setattr("app.routes.feed._resolve_concept_champion", _fake_champion)

        items = await _score_event_concepts(db=None, now=now, sport_filter=None)

        keys = [i["data"]["key"] for i in items]
        assert "event:ufc:26sep08" in keys
        assert (
            "event:ufc:26sep09" not in keys
        ), "the served tier handed a reader both halves of one fight night"
        assert "event:ufc:26sep11" in keys

        for item in items:
            reason = (item.get("reason") or "").lower()
            assert "fights on the card" not in reason
            assert not any(ch.isdigit() for ch in reason), item["data"]["key"]


class TestTheDedupRefusesToGuess:
    """The other direction of the cap (gotcha #43): it must not eat real cards."""

    def test_distinct_bouts_on_adjacent_nights_both_survive(self):
        # 26sep12 and 26sep13 are two DIFFERENT main events. They are halves of
        # one real card too, but the feed cannot know that from a main event, and
        # dropping a card we misread is worse than serving one twice. #4093 is
        # where that half is fixed.
        silva = {
            "key": "event:ufc:26sep12",
            "name": "Fight Night: Silva vs Delgado",
            "domain": "ufc",
            "fight_count": 13,
        }
        ige = {
            "key": "event:ufc:26sep13",
            "name": "Martinez vs Ige",
            "domain": "ufc",
            "fight_count": 2,
        }
        kept = _drop_duplicate_bout_concepts([_as_item(silva, 48), _as_item(ige, 40)])
        assert len(kept) == 2

    def test_a_card_with_no_identifiable_main_event_is_never_dropped(self):
        for name in ("Vuelta a España 2026", "", "UFC 329", "A vs B vs C"):
            data = {"key": f"event:ufc:{name}", "name": name, "domain": "ufc"}
            assert _concept_bout_key(data) is None, name
        pool = [
            _as_item({"key": "a", "name": "UFC 329", "domain": "ufc"}, 50),
            _as_item({"key": "b", "name": "UFC 330", "domain": "ufc"}, 50),
        ]
        assert len(_drop_duplicate_bout_concepts(pool)) == 2

    def test_the_same_surnames_in_different_domains_do_not_collide(self):
        a = {"key": "a", "name": "Silva vs Santos", "domain": "ufc"}
        b = {"key": "b", "name": "Silva vs Santos", "domain": "boxing"}
        assert _concept_bout_key(a) != _concept_bout_key(b)
        assert (
            len(_drop_duplicate_bout_concepts([_as_item(a, 50), _as_item(b, 50)])) == 2
        )

    def test_one_unreadable_item_does_not_wipe_the_pass(self):
        # gotcha #42 — healthy siblings survive.
        class Exploding(dict):
            def get(self, *_a, **_k):
                raise RuntimeError("payload from the future")

        pool = [
            _as_item(SEP08, 89),
            {"type": "concept", "score": 70, "data": Exploding()},
            _as_item(SEP09, 88),
        ]
        kept = _drop_duplicate_bout_concepts(pool)
        assert len(kept) == 2
        assert [i.get("score") for i in kept] == [89, 70]
