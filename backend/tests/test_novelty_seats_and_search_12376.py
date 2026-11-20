"""#12376 — Novelty seats and search (Decide 32-C, 31-A, 37-B).

Covers:
1. First-time readers get zero novelty seats in the opening ten; all round-up
   cards sit at seat 11+ (index >= 10).
2. Returning readers get up to two novelty seats (seats 9-10, indices 8-9) in
   the opening ten when new unseen generated/round-up cards exist, both before
   and after ``seat_opening``.
3. Already-seen or dismissed round-up cards (by bundle key or covered member IDs)
   and round-up cards that inherit an ordinary-live restriction (#5105) never
   take an opening novelty seat.
4. Searching a generated card's title, kicker, or keywords finds its container
   via ``attach_search_collections``, while member-only queries still do not run
   unnamed computed producers.
5. ``tools/ranking/scorecard.py --replay novelty`` scores the stored slates.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import container_discovery as discovery
from app.utils import roundup_containers as roundups
from app.utils import search_collections as search
from app.utils.discover_opening_seating import seat_opening
from app.utils.personalization import PersonalizationContext, is_returning_reader

REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 8, 18, 0, tzinfo=timezone.utc)


def _load_scorecard():
    spec = importlib.util.spec_from_file_location(
        "scorecard", REPO / "tools" / "ranking" / "scorecard.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _futures_card(mid: int, score: float = 90.0) -> dict:
    return {
        "type": "futures",
        "score": score,
        "reason": f"Market {mid}",
        "headline": f"Market {mid}",
        "data": {
            "id": mid,
            "name": f"Will outcome {mid} happen?",
            "status": "active",
            "top_outcomes": [{"id": mid * 10, "name": "Yes", "probability": 0.5}],
        },
    }


def _live_event_card(eid: int, *, exempt: bool = False, score: float = 95.0) -> dict:
    return {
        "type": "event",
        "score": score,
        "reason": f"Live game {eid}",
        "headline": f"Live game {eid}",
        "data": {
            "id": eid,
            "status": "live",
            "commence_time": (NOW - timedelta(hours=1)).isoformat(),
            "is_major": exempt,
            "is_marquee": False,
            "event_tags": ["tier:1", "importance:playoff"] if exempt else [],
        },
    }


def _roundup_card(
    slug: str,
    member_ids: list[int],
    *,
    live_event_child: bool = False,
) -> dict:
    items = []
    for mid in member_ids:
        if live_event_child:
            items.append(
                {
                    "type": "event",
                    "score": 80.0,
                    "data": {
                        "id": mid,
                        "status": "live",
                        "commence_time": (NOW - timedelta(hours=1)).isoformat(),
                        "is_major": False,
                        "is_marquee": False,
                        "event_tags": [],
                    },
                }
            )
        else:
            items.append(
                {
                    "type": "futures",
                    "score": 80.0,
                    "data": {"id": mid, "name": f"Member {mid}"},
                }
            )
    return {
        "type": "bundle",
        "score": 0.0,
        "reason": f"Roundup {slug}",
        "headline": f"Roundup {slug}",
        "data": {
            "id": f"roundup:{slug}",
            "title": f"Roundup {slug}",
            "kind": "roundup",
            "story_key": f"roundup:{slug}",
            "item_count": len(member_ids),
            "member_ids": list(member_ids),
            "items": items,
            "collection_ref": {
                "slug": slug,
                "href": f"/collections/{slug}",
                "name": f"Roundup {slug}",
                "revision": "rev1",
                "collection_count": len(member_ids),
            },
            "roundup": {
                "kicker": "ROUNDUP",
                "tag": "CULTURE",
                "footer": "Combined probability",
                "rows": [
                    {"market_id": mid, "label": f"Row {mid}", "probability": 0.5}
                    for mid in member_ids
                ],
                "relations": ["sibling_market"],
                "level": "grouped",
            },
        },
    }


def test_first_time_reader_has_zero_novelty_seats_in_opening_ten():
    assert is_returning_reader(None) is False
    assert is_returning_reader(PersonalizationContext()) is False

    deck = [_futures_card(i, score=100.0 - i) for i in range(1, 16)]
    r_cards = [
        _roundup_card("rt-scores-this-week", [201, 202, 203]),
        _roundup_card("snow-first-flakes-2026", [204, 205, 206]),
        _roundup_card("gta-vi-album-features", [207, 208, 209]),
    ]

    out = roundups.insert_roundup_feed_items(
        deck,
        r_cards,
        returning_reader=False,
        now=NOW,
    )
    opening_ten = out[:10]
    assert all(c.get("type") != "bundle" for c in opening_ten)
    roundup_positions = [idx for idx, c in enumerate(out) if c.get("type") == "bundle"]
    assert roundup_positions == [10, 12, 14]


def test_returning_reader_gets_up_to_two_novelty_seats_in_opening_ten():
    ctx = PersonalizationContext(recent_seen_futures_ids={1, 2})
    assert is_returning_reader(ctx) is True

    deck = [_futures_card(i, score=100.0 - i) for i in range(1, 16)]
    r_cards = [
        _roundup_card("rt-scores-this-week", [201, 202, 203]),
        _roundup_card("snow-first-flakes-2026", [204, 205, 206]),
        _roundup_card("gta-vi-album-features", [207, 208, 209]),
        _roundup_card("who-announces-before-2027", [210, 211, 212]),
    ]

    out = roundups.insert_roundup_feed_items(
        deck,
        r_cards,
        returning_reader=True,
        seen_futures_ids=ctx.recent_seen_futures_ids,
        now=NOW,
    )
    opening_ten = out[:10]
    opening_bundles = [
        (idx, c["data"]["id"])
        for idx, c in enumerate(opening_ten)
        if c.get("type") == "bundle"
    ]
    assert opening_bundles == [
        (8, "roundup:rt-scores-this-week"),
        (9, "roundup:snow-first-flakes-2026"),
    ]
    tail_bundles = [
        (idx, c["data"]["id"])
        for idx, c in enumerate(out)
        if c.get("type") == "bundle" and idx >= 10
    ]
    assert [b[1] for b in tail_bundles] == [
        "roundup:gta-vi-album-features",
        "roundup:who-announces-before-2027",
    ]


def test_returning_reader_skips_already_seen_roundups_for_novelty_seats():
    deck = [_futures_card(i, score=100.0 - i) for i in range(1, 16)]
    r_cards = [
        _roundup_card("rt-scores-this-week", [201, 202, 203]),
        _roundup_card("snow-first-flakes-2026", [204, 205, 206]),
        _roundup_card("gta-vi-album-features", [207, 208, 209]),
    ]

    # Case 1: first roundup seen by card key, second seen by all member IDs -> only third takes a novelty seat (seat 10, index 9).
    out = roundups.insert_roundup_feed_items(
        deck,
        r_cards,
        returning_reader=True,
        seen_card_keys={"bundle:roundup:rt-scores-this-week"},
        seen_futures_ids={204, 205, 206},
        now=NOW,
    )
    opening_bundles = [
        (idx, c["data"]["id"])
        for idx, c in enumerate(out[:10])
        if c.get("type") == "bundle"
    ]
    assert opening_bundles == [(9, "roundup:gta-vi-album-features")]

    # Case 2: all three seen -> zero novelty seats in the opening ten.
    out_all_seen = roundups.insert_roundup_feed_items(
        deck,
        r_cards,
        returning_reader=True,
        seen_card_keys={
            "roundup:rt-scores-this-week",
            "roundup:snow-first-flakes-2026",
            "roundup:gta-vi-album-features",
        },
        now=NOW,
    )
    assert all(c.get("type") != "bundle" for c in out_all_seen[:10])


def test_novelty_seats_survive_seat_opening_and_skip_restricted_live_roundups():
    # Two restricted ordinary-live events sit at the top of the raw deck, followed by 14 eligible futures cards.
    deck = [
        _live_event_card(901, exempt=False, score=99.0),
        _live_event_card(902, exempt=False, score=98.0),
        *[_futures_card(i, score=95.0 - i) for i in range(1, 15)],
    ]
    r_cards = [
        _roundup_card(
            "roundup-closest-games-tonight", [901, 902], live_event_child=True
        ),
        _roundup_card("rt-scores-this-week", [201, 202, 203]),
        _roundup_card("snow-first-flakes-2026", [204, 205, 206]),
        _roundup_card("gta-vi-album-features", [207, 208, 209]),
    ]

    inserted = roundups.insert_roundup_feed_items(
        deck,
        r_cards,
        returning_reader=True,
        seen_futures_ids={1},
        now=NOW,
    )
    seated = seat_opening(inserted, now=NOW)
    assert seated.status == "applied"
    opening_ten = seated.items[:10]
    opening_bundles = [
        (idx, c["data"]["id"])
        for idx, c in enumerate(opening_ten)
        if c.get("type") == "bundle"
    ]
    assert opening_bundles == [
        (8, "roundup:rt-scores-this-week"),
        (9, "roundup:snow-first-flakes-2026"),
    ]
    # Restricted live roundup stays out of the opening ten.
    assert all(
        c.get("data", {}).get("id") != "roundup:roundup-closest-games-tonight"
        for c in opening_ten
    )


@pytest.mark.asyncio
async def test_searching_generated_card_title_or_keywords_finds_its_container(
    monkeypatch,
):
    monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")

    def produce(_db):
        return roundups.RoundupMembers(
            [
                {
                    "id": 501,
                    "name": "Will Gladiator II score 80%+ on Rotten Tomatoes?",
                    "outcomes": [{"name": "Yes", "probability": 0.72}],
                },
                {
                    "id": 502,
                    "name": "Will Wicked score 85%+ on Rotten Tomatoes?",
                    "outcomes": [{"name": "Yes", "probability": 0.88}],
                },
            ]
        )

    producer = roundups.RoundupProducer(
        slug="generated-box-office-buzz",
        name="Autumn movie buzz",
        kicker="ROTTEN TOMATOES",
        category="entertainment",
        produce=produce,
        rule={
            "producer": "sibling_family",
            "title_pattern": "Rotten Tomatoes",
            "keywords": ["critic score", "freshness rating", "cinema"],
            "candidates": ["Gladiator II", "Wicked"],
        },
    )
    monkeypatch.setattr(roundups, "ROUNDUP_PRODUCERS", {producer.slug: producer})
    monkeypatch.setattr(
        discovery,
        "discover_collections",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("should not fall through when named roundup matches")
        ),
    )

    for query in (
        "Autumn movie buzz",
        "Rotten Tomatoes",
        "critic score",
        "freshness rating",
    ):
        res = await search.attach_search_collections(
            SimpleNamespace(), {"query": query, "results": [], "futures": []}
        )
        assert "collections" in res, f"query {query!r} should find the container"
        assert res["collections"][0]["slug"] == "generated-box-office-buzz"
        assert (
            res["collections"][0]["destination"]["web"]
            == "/collections/generated-box-office-buzz"
        )


def test_scorecard_novelty_replay_scores_stored_slates():
    sc = _load_scorecard()
    slates_dir = REPO / "evals" / "ranking" / "slates"
    nov8_path = slates_dir / "2026-11-08-discover-1ad0550f8399123a.json"
    assert nov8_path.exists()

    slate = sc.load_json(nov8_path)
    previous = sc.find_previous(slates_dir, slate)
    assert previous is not None

    served_order = list(slate.get("served_order") or [])
    novelty_ranker = sc.resolve_ranker("novelty")
    novelty_order = sc.replay(slate, novelty_ranker)

    # Served opening ten has zero roundup bundles; novelty replay places 2 roundup bundles in seats 9-10.
    assert sum(1 for k in served_order[:10] if k.startswith("bundle:roundup:")) == 0
    assert [k for k in novelty_order[8:10]] == [
        "bundle:roundup:cfp-picture",
        "bundle:roundup:by-november-30",
    ]
    assert novelty_order[:8] == served_order[:8]

    served_score = sc.score_ranking(served_order, slate, [], previous)
    novelty_score = sc.score_ranking(novelty_order, slate, [], previous)
    assert novelty_score["truth_gate"]["failures"] == 0
    assert novelty_score["sameness"] <= served_score["sameness"]
