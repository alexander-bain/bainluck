"""Regression tests for Ruling 275 (#13100): Oscars card rows & downward-prune exception.

1. The Oscars theme card shows the most important awards first: Best Picture,
   then Best Director, Best Actor, and Best Actress where held, ahead of craft
   categories that tie on static score.
2. Cross-venue listings of the same major Oscars race (e.g. Kalshi
   "Oscar Winner: Best Picture" and Polymarket "Oscars 2027: Best Picture Winner")
   collapse to one row in the Oscars card and do not leak as standalone cards.
3. A card never loses a row to a card seated below it: the Oscars card keeps
   Best Picture even when ``roundup-oscars-best-picture`` or
   ``machinery-oscars-best-picture`` sits lower down in the feed.
4. A card seated below a round-up still drops overlapping rows, and machinery
   dissolution takeover (e.g. Fed & Rates -> Fed & U.S. Macro at Seat 4) is preserved.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.utils.discover_bundles import assemble_story_theme_bundles
from app.utils.feed_market_quality import (
    classify_market_quality,
    diversify_quality_families,
    oscars_award_priority,
    oscars_award_slot,
)
from app.utils.roundup_containers import insert_roundup_feed_items

NOW = datetime(2026, 11, 19, 21, 0, tzinfo=timezone.utc)


def _oscar_item(
    market_id: int,
    name: str,
    *,
    source: str = "polymarket",
    score: float = 88.0,
    leader: str = "The Odyssey",
    prob: float = 0.52,
) -> dict:
    q = classify_market_quality(name, "entertainment")
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "_sort_time": NOW.timestamp(),
        "_quality_class": q.quality_class,
        "_quality_family_key": q.family_key,
        "_quality_story_key": q.story_key,
        "data": {
            "id": market_id,
            "name": name,
            "source": source,
            "status": "open",
            "llm_sport_category": "entertainment",
            "resolution_date": "2027-03-15T00:00:00+00:00",
            "outcomes": [{"name": leader, "probability": prob}],
        },
    }


def _filler_item(idx: int, *, score: float = 70.0) -> dict:
    return {
        "type": "futures",
        "score": score - idx * 0.1,
        "_rank_score": score - idx * 0.1,
        "_sort_time": NOW.timestamp(),
        "data": {
            "id": 900000 + idx,
            "name": f"Filler Market {idx}",
            "source": "kalshi",
            "status": "open",
            "llm_sport_category": "politics",
        },
    }


def _roundup_card(
    slug: str,
    covered_ids: list[int],
    *,
    is_machinery: bool = False,
    is_sibling: bool = True,
) -> dict:
    rid = slug if is_machinery else f"roundup:{slug.removeprefix('roundup-')}"
    return {
        "type": "bundle",
        "score": 60.0,
        "data": {
            "id": rid,
            "kind": "roundup",
            "name": slug,
            "collection_ref": {"slug": slug, "href": f"/collections/{slug}", "name": slug},
            "roundup": {
                "kicker": "GROUPING" if is_machinery else "ROUND-UP",
                "relations": ["same_subject", "sibling"] if is_sibling else ["same_subject"],
                "rows": [],
            },
            "items": [
                {"type": "futures", "data": {"id": mid, "status": "open"}}
                for mid in covered_ids
            ],
            "member_ids": list(covered_ids),
            **({"machinery_slug": slug} if is_machinery else {}),
        },
    }


def test_oscars_award_slot_ranks_major_winners_and_excludes_nominations():
    assert oscars_award_slot("Oscar Winner: Best Picture") == (0, "best_picture")
    assert oscars_award_slot("Oscars 2027: Best Director Winner") == (1, "best_director")
    assert oscars_award_slot("Oscar Winner: Best Actor") == (2, "best_actor")
    assert oscars_award_slot("Oscar winner: Best Actress") == (3, "best_actress")
    assert oscars_award_slot("Oscars 2027: Best Supporting Actor Winner") == (
        4,
        "best_supporting_actor",
    )
    assert oscars_award_slot("Oscar Winner: Best Supporting Actress") == (
        5,
        "best_supporting_actress",
    )
    # Nominations and craft categories must not claim major winner slots
    assert oscars_award_slot("Oscar nominees: Best Director") is None
    assert oscars_award_slot("Oscars 2027: Best Actor Nominations") is None
    assert oscars_award_slot("Oscars 2027: Best Film Editing Winner") is None
    assert oscars_award_priority("Oscar Winner: Best Picture") < oscars_award_priority(
        "Oscars 2027: Best Film Editing Winner"
    )


def test_oscars_bundle_leads_with_big_four_even_behind_craft_categories_and_cross_venue_dupes():
    # Craft categories arrive FIRST on tied score 88 (matching live Discover bug #13100)
    craft_names = [
        "Oscars 2027: Best Film Editing Winner",
        "Oscars 2027: Best Production Design Winner",
        "Oscars 2027: Best Costume Design Winner",
        "Oscars 2027: Best Sound Winner",
        "Oscars 2027: Best International Feature Film Winner",
        "Oscars 2027: Best Makeup and Hairstyling Winner",
        "Oscars 2027: Best Visual Effects Winner",
        "Oscars 2027: Best Original Score Winner",
        "Oscars 2027: Best Cinematography Winner",
    ]
    pool = [_oscar_item(65814220 + i, n, score=88.5) for i, n in enumerate(craft_names)]
    # Add BOTH Kalshi and Polymarket listings for the big four AFTER all 9 craft categories
    pool.extend(
        [
            _oscar_item(6173044, "Oscar Winner: Best Picture", source="kalshi", score=88.0, leader="The Odyssey", prob=0.54),
            _oscar_item(57313556, "Oscars 2027: Best Picture Winner", source="polymarket", score=87.5, leader="The Odyssey", prob=0.52),
            _oscar_item(58519933, "Oscars 2027: Best Director Winner", source="polymarket", score=88.0, leader="Christopher Nolan", prob=0.63),
            _oscar_item(5869747, "Oscar Winner: Best Director", source="kalshi", score=87.0, leader="Christopher Nolan", prob=0.56),
            _oscar_item(57368169, "Oscars 2027: Best Actor Winner", source="polymarket", score=88.0, leader="John Malkovich", prob=0.47),
            _oscar_item(5869749, "Oscar Winner: Best Actor", source="kalshi", score=87.0, leader="John Malkovich", prob=0.46),
            _oscar_item(57366460, "Oscars 2027: Best Actress Winner", source="polymarket", score=88.0, leader="Julianne Moore", prob=0.83),
            _oscar_item(5869748, "Oscar winner: Best Actress", source="kalshi", score=87.0, leader="Julianne Moore", prob=0.84),
            _oscar_item(52755611, "Oscar winner: Best Supporting Actor", source="kalshi", score=88.0, leader="Paul Giamatti", prob=0.43),
            _oscar_item(66118096, "Oscars 2027: Best Director Nominations", source="polymarket", score=89.0),
        ]
    )

    capped = diversify_quality_families(pool, exact_family_cap=1, story_family_cap=5)
    bundled = assemble_story_theme_bundles(capped)

    oscar_bundles = [
        it for it in bundled if it.get("type") == "bundle" and (it.get("data") or {}).get("story_key") == "story:oscars"
    ]
    assert len(oscar_bundles) == 1
    bundle = oscar_bundles[0]
    member_ids = bundle["data"]["member_ids"]
    member_names = [ch["data"]["name"] for ch in bundle["data"]["items"]]

    # Exact Big-4 order first, no duplicate cross-venue rows, no nominations ahead of winners
    assert member_ids[:4] == [6173044, 58519933, 57368169, 57366460]
    assert member_ids[4] == 52755611
    assert len(member_ids) == 6
    assert 57313556 not in member_ids
    assert 5869747 not in member_ids
    assert 5869749 not in member_ids
    assert 5869748 not in member_ids
    assert all("nominat" not in n.lower() for n in member_names[:5])

    # Folded cross-venue duplicates must not escape as standalone Oscars cards
    standalone_ids = {it["data"]["id"] for it in bundled if it.get("type") == "futures"}
    assert standalone_ids.isdisjoint({57313556, 5869747, 5869749, 5869748})


def test_card_never_loses_a_row_to_roundup_or_machinery_seated_below_it():
    # Oscars theme card at Seat 1 (index 0), Best Picture round-up / machinery seated lower down
    oscar_pool = [
        _oscar_item(6173044, "Oscar Winner: Best Picture", source="kalshi", score=88.0),
        _oscar_item(58519933, "Oscars 2027: Best Director Winner", score=88.0),
        _oscar_item(57368169, "Oscars 2027: Best Actor Winner", score=88.0),
        _oscar_item(57366460, "Oscars 2027: Best Actress Winner", score=88.0),
        _oscar_item(65814223, "Oscars 2027: Best Film Editing Winner", score=88.0),
    ]
    oscar_card = assemble_story_theme_bundles(oscar_pool)[0]
    feed = [oscar_card] + [_filler_item(i) for i in range(45)]

    # 1. Standing round-up seated below Oscars (at seat >= 11)
    standing_bp = _roundup_card("roundup-oscars-best-picture", [6173044], is_machinery=False)
    out_standing = insert_roundup_feed_items(feed, [standing_bp], seat_floor=10, page_window=20, now=NOW)
    oscar_idx = next(
        i for i, it in enumerate(out_standing) if (it.get("data") or {}).get("story_key") == "story:oscars"
    )
    bp_idx = next(
        i for i, it in enumerate(out_standing) if (it.get("data") or {}).get("id") == "roundup:oscars-best-picture"
    )
    assert oscar_idx < bp_idx
    assert out_standing[oscar_idx]["data"]["member_ids"][0] == 6173044
    assert [c["data"]["id"] for c in out_standing[oscar_idx]["data"]["items"]][0] == 6173044

    # 2. Machinery grouping seated below Oscars (and replacing standing round-up)
    machinery_bp = _roundup_card("machinery-oscars-best-picture", [6173044], is_machinery=True)
    machinery_bp["data"]["replaces_roundups"] = ["roundup-oscars-best-picture"]
    out_machinery = insert_roundup_feed_items(
        out_standing, [machinery_bp], seat_floor=10, page_window=20, now=NOW
    )
    oscar_idx_m = next(
        i for i, it in enumerate(out_machinery) if (it.get("data") or {}).get("story_key") == "story:oscars"
    )
    bp_idx_m = next(
        i for i, it in enumerate(out_machinery) if (it.get("data") or {}).get("id") == "machinery-oscars-best-picture"
    )
    assert oscar_idx_m < bp_idx_m
    assert out_machinery[oscar_idx_m]["data"]["member_ids"][0] == 6173044
    assert [c["data"]["id"] for c in out_machinery[oscar_idx_m]["data"]["items"]][0] == 6173044

    # 3. Even when Oscars is unpinned to Seat 16 (Ruling 277: A) and Best Picture sits at Seat 21+
    feed_unpinned = [_filler_item(i) for i in range(15)] + [oscar_card] + [_filler_item(15 + i) for i in range(30)]
    sib_a = _roundup_card("roundup-sib-a", [700001], is_sibling=True)
    sib_b = _roundup_card("roundup-sib-b", [700002], is_sibling=True)
    out_unpinned = insert_roundup_feed_items(
        feed_unpinned, [sib_a, sib_b, standing_bp], seat_floor=10, page_window=20, now=NOW
    )
    oscar_idx_u = next(
        i for i, it in enumerate(out_unpinned) if (it.get("data") or {}).get("story_key") == "story:oscars"
    )
    bp_idx_u = next(
        i for i, it in enumerate(out_unpinned) if (it.get("data") or {}).get("id") == "roundup:oscars-best-picture"
    )
    assert oscar_idx_u < bp_idx_u
    assert out_unpinned[oscar_idx_u]["data"]["member_ids"][0] == 6173044


def test_card_seated_below_roundup_still_prunes_overlapping_row():
    # Oscars theme card seated at Seat 25 (index 24), BELOW Best Picture round-up at Seat 11
    oscar_pool = [
        _oscar_item(6173044, "Oscar Winner: Best Picture", source="kalshi", score=60.0),
        _oscar_item(58519933, "Oscars 2027: Best Director Winner", score=60.0),
        _oscar_item(57368169, "Oscars 2027: Best Actor Winner", score=60.0),
    ]
    oscar_card = assemble_story_theme_bundles(oscar_pool)[0]
    feed = [_filler_item(i) for i in range(24)] + [oscar_card] + [_filler_item(24 + i) for i in range(10)]
    standing_bp = _roundup_card("roundup-oscars-best-picture", [6173044], is_machinery=False)

    out = insert_roundup_feed_items(feed, [standing_bp], seat_floor=10, page_window=20, now=NOW)
    oscar_idx = next(
        i for i, it in enumerate(out) if (it.get("data") or {}).get("story_key") == "story:oscars"
    )
    bp_idx = next(
        i for i, it in enumerate(out) if (it.get("data") or {}).get("id") == "roundup:oscars-best-picture"
    )
    assert bp_idx < oscar_idx
    assert 6173044 not in out[oscar_idx]["data"]["member_ids"]
    assert out[oscar_idx]["data"]["member_ids"] == [58519933, 57368169]


def test_best_actor_slot_keeps_priced_5869749_over_unpriced_109566_and_prefers_later_resolution_date():
    """Fable 10:26 PM look on #13115: never fold a priced market for an unpriced one,
    and break ties between two priced markets in favor of the later resolution date."""
    unpriced_109566 = {
        "type": "futures",
        "score": 99.0,  # artificially higher score & first in input order
        "reason": "test",
        "headline": "Oscar for Best Actor?",
        "data": {
            "id": 109566,
            "name": "Oscar for Best Actor?",
            "source": "polymarket",
            "status": "open",
            "resolution_date": "2026-12-31T15:00:00+00:00",
            "llm_sport_category": "entertainment",
            "top_outcomes": [
                {"id": 1598463, "name": "Jesse Plemons", "probability": None},
                {"id": 1598464, "name": "Dwayne Johnson", "probability": None},
            ],
        },
    }
    priced_5869749 = {
        "type": "futures",
        "score": 60.0,
        "reason": "test",
        "headline": "Oscar Winner: Best Actor",
        "data": {
            "id": 5869749,
            "name": "Oscar Winner: Best Actor",
            "source": "kalshi",
            "status": "open",
            "resolution_date": "2027-12-31T15:00:00+00:00",
            "llm_sport_category": "entertainment",
            "top_outcomes": [
                {"id": 29659681, "name": "John Malkovich", "probability": 0.49},
                {"id": 29920022, "name": "Andrew Scott", "probability": 0.23},
            ],
        },
    }
    priced_picture = {
        "type": "futures",
        "score": 60.0,
        "reason": "test",
        "headline": "Oscar Winner: Best Picture",
        "data": {
            "id": 6173044,
            "name": "Oscar Winner: Best Picture",
            "source": "kalshi",
            "status": "open",
            "resolution_date": "2027-12-31T15:00:00+00:00",
            "llm_sport_category": "entertainment",
            "top_outcomes": [{"id": 1, "name": "The Odyssey", "probability": 0.54}],
        },
    }
    priced_director = {
        "type": "futures",
        "score": 60.0,
        "reason": "test",
        "headline": "Oscar Winner: Best Director",
        "data": {
            "id": 58519933,
            "name": "Oscar Winner: Best Director",
            "source": "kalshi",
            "status": "open",
            "resolution_date": "2027-12-31T15:00:00+00:00",
            "llm_sport_category": "entertainment",
            "top_outcomes": [{"id": 2, "name": "Christopher Nolan", "probability": 0.61}],
        },
    }

    bundles = assemble_story_theme_bundles(
        [unpriced_109566, priced_picture, priced_director, priced_5869749]
    )
    assert len(bundles) == 1
    ids = [c["data"]["id"] for c in bundles[0]["data"]["items"]]
    assert ids == [6173044, 58519933, 5869749]
    assert 109566 not in ids

    # Both priced -> later resolution_date wins even when earlier ceremony has higher score.
    earlier_priced_actor = {
        **priced_5869749,
        "score": 95.0,
        "data": {
            **priced_5869749["data"],
            "id": 990001,
            "name": "Oscars 2026: Best Actor Winner",
            "resolution_date": "2026-03-15T23:00:00+00:00",
        },
    }
    bundles2 = assemble_story_theme_bundles(
        [earlier_priced_actor, priced_picture, priced_director, priced_5869749]
    )
    ids2 = [c["data"]["id"] for c in bundles2[0]["data"]["items"]]
    assert ids2 == [6173044, 58519933, 5869749]
    assert 990001 not in ids2


def test_machinery_in_place_splice_preserve_existing_roundups_respects_ruling_275():
    """Both prune passes (`insert_roundup_feed_items` and `_splice_machinery_in_place`)
    keep Best Picture on the Oscars card when the grouping sits below, and prune only
    when it sits strictly above."""
    oscar_pool = [
        _oscar_item(6173044, "Oscar Winner: Best Picture", source="kalshi", score=60.0),
        _oscar_item(58519933, "Oscars 2027: Best Director Winner", score=60.0),
        _oscar_item(5869749, "Oscar Winner: Best Actor", source="kalshi", score=60.0),
    ]
    oscar_card = assemble_story_theme_bundles(oscar_pool)[0]
    standing_bp = _roundup_card("roundup-oscars-best-picture", [6173044], is_machinery=False)
    machinery_bp = _roundup_card("machinery-oscars-best-picture", [6173044], is_machinery=True)
    machinery_bp["data"]["replaces_roundups"] = ["roundup-oscars-best-picture"]

    # Case A: Oscars card ABOVE standing Best Picture -> machinery replaces standing in place below Oscars.
    feed_above = (
        [_filler_item(i) for i in range(4)]
        + [oscar_card]
        + [_filler_item(4 + i) for i in range(10)]
        + [standing_bp]
        + [_filler_item(20 + i) for i in range(10)]
    )
    out_above = insert_roundup_feed_items(
        feed_above,
        [machinery_bp],
        seat_floor=10,
        page_window=20,
        now=NOW,
        preserve_existing_roundups=True,
    )
    o_idx = next(i for i, it in enumerate(out_above) if (it.get("data") or {}).get("story_key") == "story:oscars")
    m_idx = next(i for i, it in enumerate(out_above) if (it.get("data") or {}).get("id") == "machinery-oscars-best-picture")
    assert o_idx < m_idx
    assert [c["data"]["id"] for c in out_above[o_idx]["data"]["items"]] == [6173044, 58519933, 5869749]

    # Case B: standing Best Picture ABOVE Oscars card -> machinery replaces standing in place above Oscars -> prunes Best Picture.
    feed_below = (
        [_filler_item(i) for i in range(12)]
        + [standing_bp]
        + [_filler_item(12 + i) for i in range(10)]
        + [oscar_card]
        + [_filler_item(30 + i) for i in range(5)]
    )
    out_below = insert_roundup_feed_items(
        feed_below,
        [machinery_bp],
        seat_floor=10,
        page_window=20,
        now=NOW,
        preserve_existing_roundups=True,
    )
    o_idx_b = next(i for i, it in enumerate(out_below) if (it.get("data") or {}).get("story_key") == "story:oscars")
    m_idx_b = next(i for i, it in enumerate(out_below) if (it.get("data") or {}).get("id") == "machinery-oscars-best-picture")
    assert m_idx_b < o_idx_b
    assert [c["data"]["id"] for c in out_below[o_idx_b]["data"]["items"]] == [58519933, 5869749]
