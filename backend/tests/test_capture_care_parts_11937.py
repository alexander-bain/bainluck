"""#11937, Fable's call 4 (Nov 11): the nightly capture stores question 1's parts.

The ranking design answers "how many care" with the parts the score is built
from, never with ``score``. Each candidate now stores ``market_tier``,
``league_tier`` (the scorer's own tier functions) and ``stakes`` (the stored
``stakes:*`` tags, read from the row because a served card carries only inline
tags), and a bundle stores ``members`` with the same three fields per member.

Unknown stays unknown: ``stakes`` is ``[]`` only when the row was read and holds
no stakes tag, and ``None`` when nothing was read.
"""

from datetime import datetime, timezone

from app.utils.futures_highlights import FUTURES_LEAGUE_TIERS
from app.utils.highlights import get_league_tier
from app.utils.ranking_eval import RANKING_SNAPSHOTS_ENV, build_slate, card_features
from app.utils.ranking_slate_capture import _ids, snapshot_ranking_slate

NOW = datetime(2026, 11, 12, 6, 0, tzinfo=timezone.utc)
ON = {RANKING_SNAPSHOTS_ENV: "1", "HEROKU_SLUG_COMMIT": "abcdef1234567890"}


def futures(mid, *, tier=1, category="basketball"):
    return {
        "type": "futures",
        "score": 80,
        "data": {
            "id": mid,
            "name": f"Market {mid}",
            "llm_sport_category": category,
            "market_tier": tier,
            "status": "open",
            "top_outcomes": [{"name": "A", "probability": 0.4}],
        },
    }


def event(eid, sport="basketball_nba"):
    return {
        "type": "event",
        "score": 90,
        "data": {"id": eid, "home_team": "H", "away_team": "A", "sport": sport, "status": "scheduled"},
    }


def bundle(key, members):
    return {"type": "bundle", "data": {"key": key, "title": "AI race", "story_key": key, "items": members}}


def test_futures_card_stores_its_tiers_and_stored_stakes():
    facts = {3: {"market_tags": ["tier:1", "stakes:title_defense", "stakes:clinch"], "market_tier": 1}}
    out = card_features(futures(3, tier=1, category="basketball"), now=NOW, market_facts=facts)
    assert out["market_tier"] == 1
    assert out["league_tier"] == FUTURES_LEAGUE_TIERS["basketball"] == 1
    assert out["stakes"] == ["stakes:clinch", "stakes:title_defense"]
    # score is still stored beside the parts, never replaced by them
    assert out["score"] == 80.0


def test_stakes_unknown_is_none_and_read_but_empty_is_an_empty_list():
    no_facts = card_features(futures(3), now=NOW, market_facts={})
    assert no_facts["stakes"] is None
    read_none = card_features(futures(3), now=NOW, market_facts={3: {"market_tags": ["tier:1"]}})
    assert read_none["stakes"] == []


def test_market_tier_falls_back_to_the_row_when_the_card_is_silent():
    card = futures(4)
    del card["data"]["market_tier"]
    out = card_features(card, now=NOW, market_facts={4: {"market_tier": 3, "market_tags": []}})
    assert out["market_tier"] == 3


def test_unlisted_futures_category_gets_the_scorers_default_tier():
    out = card_features(futures(5, category="entertainment-not-a-key"), now=NOW)
    assert out["league_tier"] == 3


def test_event_card_stores_the_event_scorers_league_tier_and_row_stakes():
    out = card_features(
        event(9, sport="icehockey_nhl"),
        now=NOW,
        event_facts={9: {"event_tags": ["stakes:elimination", "narrative:rivalry"]}},
    )
    assert out["league_tier"] == get_league_tier("icehockey_nhl")
    assert out["market_tier"] is None
    assert out["stakes"] == ["stakes:elimination"]
    assert card_features(event(9), now=NOW)["stakes"] is None


def test_bundle_links_each_member_with_its_parts():
    b = bundle("story:ai", [futures(11, tier=1, category="tech"), futures(12, tier=5, category="tech")])
    facts = {11: {"market_tags": ["stakes:record_chase"]}, 12: {"market_tags": []}}
    out = card_features(b, now=NOW, market_facts=facts)
    assert out["members"] == [
        {"item_key": "futures:11", "market_tier": 1, "league_tier": FUTURES_LEAGUE_TIERS["tech"], "stakes": ["stakes:record_chase"]},
        {"item_key": "futures:12", "market_tier": 5, "league_tier": FUTURES_LEAGUE_TIERS["tech"], "stakes": []},
    ]
    # the bundle itself has no single tier of its own
    assert out["market_tier"] is None and out["league_tier"] is None and out["stakes"] is None
    # a lone card carries no member list
    assert card_features(futures(11), now=NOW)["members"] is None


def test_the_facts_reads_include_bundle_members():
    items = [futures(1), event(7), bundle("story:x", [futures(21), futures(22)])]
    assert _ids(items, "futures") == [1, 21, 22]
    assert _ids(items, "event") == [7]


def test_build_slate_carries_the_parts_on_every_candidate():
    served = [futures(1), event(7)]
    _, cands = build_slate(
        served,
        [futures(50, tier=2)],
        now=NOW,
        market_facts={1: {"market_tags": []}, 50: {"market_tags": ["stakes:seeding"]}},
        event_facts={7: {"event_tags": ["stakes:must_win"]}},
    )
    by_key = {c["item_key"]: c for c in cands}
    assert by_key["futures:1"]["stakes"] == []
    assert by_key["event:7"]["stakes"] == ["stakes:must_win"]
    assert by_key["futures:50"]["market_tier"] == 2 and by_key["futures:50"]["stakes"] == ["stakes:seeding"]


class _DB:
    def __init__(self):
        self.added, self.commits = [], 0

    def add(self, row):
        self.added.append(row)

    async def execute(self, stmt):
        return None

    async def commit(self):
        self.commits += 1


def _deck(items):
    async def read(db):
        return {"items": items, "edition": "ae0bc760eb204e34", "total": len(items)}

    return read


async def _pool(db, now):
    return []


async def _facts(db, ids):
    return {i: {"market_tags": ["stakes:clinch"]} for i in ids}


async def test_capture_reads_member_and_event_ids_and_stores_the_parts():
    seen = {}

    async def events(db, ids):
        seen["events"] = ids
        return {i: {"event_tags": ["stakes:elimination"]} for i in ids}

    async def facts(db, ids):
        seen["futures"] = ids
        return await _facts(db, ids)

    db = _DB()
    out = await snapshot_ranking_slate(
        db,
        now=NOW,
        read_deck=_deck([event(7), bundle("story:x", [futures(21)])]),
        read_pool=_pool,
        read_facts=facts,
        read_events=events,
        environ=ON,
    )
    assert out["status"] == "ok" and out["event_facts_error"] is None
    assert seen == {"events": [7], "futures": [21]}
    (row,) = db.added
    by_key = {c["item_key"]: c for c in row.candidates}
    assert by_key["event:7"]["stakes"] == ["stakes:elimination"]
    assert by_key["bundle:story:x"]["members"][0]["stakes"] == ["stakes:clinch"]


async def test_a_failed_event_read_is_ok_partial_and_stakes_stay_unknown():
    async def bad_events(db, ids):
        raise RuntimeError("events down")

    db = _DB()
    out = await snapshot_ranking_slate(
        db, now=NOW, read_deck=_deck([event(7)]), read_pool=_pool, read_facts=_facts,
        read_events=bad_events, environ=ON,
    )
    assert out["status"] == "ok_partial" and out["event_facts_error"] == "events down"
    (row,) = db.added
    assert row.candidates[0]["stakes"] is None  # unknown, never an empty list
