"""#13097 Batch 1 (Rulings 272: A & 273: B): three fun grouping rule files through the machinery.

Covers:
  1. `machinery-white-christmas` (title "Will it snow in ... on Christmas?", weather pool)
  2. `machinery-next-james-bond` (title "Next James Bond film: ...")
  3. `machinery-who-gets-engaged` ("engaged" in title, both venues, one row per couple,
     excluding Roblox hours / Taylor Swift wedding / taste-guard markets)
  4. 32-C novelty-seat eligibility (can reach opening ten for returning readers, never pinned)
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.utils.container_machinery import (
    _category_llm_pool_for_definition,
    _compute_member_number_parity,
    build_container_machinery_producer,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    apply_novelty_seats,
    compose_roundup_container,
    compose_roundup_feed_item,
    insert_roundup_feed_items,
)

NOW = datetime(2026, 11, 19, 21, 0, tzinfo=timezone.utc)


def _sample_markets() -> list[dict]:
    return [
        # White Christmas
        {"id": 70170344, "name": "Will it snow in Pittsburgh on Christmas?", "status": "open", "source": "kalshi", "category": "weather", "outcomes": [{"id": 1, "name": "Above 0 inches", "probability": 0.44}]},
        {"id": 70170347, "name": "Will it snow in Milwaukee on Christmas?", "status": "open", "source": "kalshi", "category": "weather", "outcomes": [{"id": 2, "name": "Above 0 inches", "probability": 0.41}]},
        {"id": 70170348, "name": "Will it snow in Detroit on Christmas?", "status": "open", "source": "kalshi", "category": "weather", "outcomes": [{"id": 3, "name": "Above 0 inches", "probability": 0.38}]},
        {"id": 70170343, "name": "Will it snow in Seattle on Christmas?", "status": "open", "source": "kalshi", "category": "weather", "outcomes": [{"id": 4, "name": "Above 0 inches", "probability": 0.11}]},
        # Next James Bond film
        {"id": 108237, "name": "Next James Bond film: Artist performing the James Bond Theme", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 11, "name": "Raye", "probability": 0.43}, {"id": 12, "name": "Olivia Dean", "probability": 0.28}, {"id": 13, "name": "Dua Lipa", "probability": 0.14}]},
        {"id": 108263, "name": "Next James Bond film: Actress cast as Bond girl", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 21, "name": "Zendaya", "probability": 0.25}, {"id": 22, "name": "Florence Pugh", "probability": 0.24}, {"id": 23, "name": "Margaret Qualley", "probability": 0.23}]},
        {"id": 108258, "name": "Next James Bond film: Actor cast as the villain", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 31, "name": "Cillian Murphy", "probability": 0.18}, {"id": 32, "name": "Callum Turner", "probability": 0.14}, {"id": 33, "name": "Aaron Taylor-Johnson", "probability": 0.12}]},
        # Who gets engaged? (includes reversed-order twin, politics-filed couple, Roblox noise, Taylor Swift wedding)
        {"id": 61085868, "name": "Scooter Braun and Sydney Sweeney engaged in 2026?", "status": "open", "source": "polymarket", "category": "entertainment", "outcomes": [{"id": 41, "name": "Yes", "probability": 0.36}]},
        {"id": 109618, "name": "Sydney Sweeney and Scooter Braun: Engaged this year?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 42, "name": "Yes", "probability": 0.35}]},
        {"id": 109385, "name": "Timothée Chalamet and Kylie Jenner: Engaged in 2026?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 43, "name": "Yes", "probability": 0.13}]},
        {"id": 113658, "name": "Katy Perry and Justin Trudeau engaged by end of 2026?", "status": "open", "source": "polymarket", "category": "other", "outcomes": [{"id": 44, "name": "Yes", "probability": 0.07}]},
        {"id": 8212355, "name": "Tiger Woods and Vanessa Trump: Engaged in 2026?", "status": "open", "source": "kalshi", "category": "politics", "outcomes": [{"id": 45, "name": "Yes", "probability": 0.06}]},
        # Must be excluded:
        {"id": 57774265, "name": "Roblox hours engaged in fiscal 2026", "status": "open", "source": "kalshi", "category": "economics", "outcomes": [{"id": 46, "name": "Yes", "probability": 0.55}]},
        {"id": 9990001, "name": "Taylor Swift wedding engaged before 2027?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 47, "name": "Yes", "probability": 0.90}]},
        # Single-person engagement markets (must be excluded so every row is a couple):
        {"id": 109394, "name": "Will Bobbi Althoff be engaged before 2027?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 48, "name": "Yes", "probability": 0.14}]},
        {"id": 109389, "name": "IShowSpeed: Engaged before 2027?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 49, "name": "Yes", "probability": 0.12}]},
    ]


@pytest.mark.asyncio
async def test_batch1_three_fun_groupings_build_cleanly_with_full_parity_and_twin_dedup() -> None:
    db = {"events": [], "markets": _sample_markets(), "paired_sets": {}, "market_histories": {}}

    # 1. White Christmas
    wc_def = load_machinery_definition("data/groupings/candidates/machinery-white-christmas.json")
    assert wc_def["stage"] == "preview"
    assert wc_def["look"] == "map"
    assert "weather" in (_category_llm_pool_for_definition(wc_def) or ())
    wc_prod = build_container_machinery_producer(wc_def)
    assert wc_prod.stage == "preview" and wc_prod.look == "map"
    wc_res = await produce_container_machinery(db, wc_def, now=NOW)
    assert wc_res.machinery_card["form_id"] == "benchmark_strip"
    assert wc_res.sections[0]["visual_block"]["item_noun"] == "cities"
    assert wc_res.machinery_card["stage"] == "preview"
    assert wc_res.machinery_card["look"] == "map"
    assert [r["name"] for r in wc_res.machinery_card["rows"]] == ["Pittsburgh", "Milwaukee", "Detroit"]
    assert [r["rendered_percent"] for r in wc_res.machinery_card["rows"]] == [44, 41, 38]
    assert wc_res.title == "Pittsburgh is the likeliest white Christmas at 44%, with Milwaukee at 41%"
    wc_fi = compose_roundup_feed_item(wc_prod, wc_res)
    wc_cp = compose_roundup_container(wc_prod, wc_res)
    c_p, p_p = _compute_member_number_parity(wc_fi, wc_cp)
    assert c_p["passes"] is True and p_p["passes"] is True

    # 2. The Next James Bond Film (including "to play M" role phrasing)
    jb_def = load_machinery_definition("data/groupings/candidates/machinery-next-james-bond.json")
    assert jb_def["stage"] == "preview"
    assert jb_def["look"] == "faces"
    jb_prod = build_container_machinery_producer(jb_def)
    assert jb_prod.stage == "preview" and jb_prod.look == "faces"
    bond_markets = list(_sample_markets()) + [
        {"id": 108259, "name": "Next James Bond film: Actor cast as M", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 91, "name": "Ralph Fiennes", "probability": 0.34}, {"id": 92, "name": "Gary Oldman", "probability": 0.12}, {"id": 93, "name": "Idris Elba", "probability": 0.08}]},
    ]
    jb_db = {"events": [], "markets": bond_markets, "paired_sets": {}, "market_histories": {}}
    jb_res = await produce_container_machinery(jb_db, jb_def, now=NOW)
    assert jb_res.machinery_card["form_id"] == "sibling_fields_grid"
    assert jb_res.machinery_card["stage"] == "preview"
    assert jb_res.machinery_card["look"] == "faces"
    assert len(jb_res.members) == 4
    assert jb_res.machinery_card["rows"][0]["name"].startswith("James Bond Theme · Raye")
    assert "with Ralph Fiennes to play M at 34%" in jb_res.title
    jb_fi = compose_roundup_feed_item(jb_prod, jb_res)
    jb_cp = compose_roundup_container(jb_prod, jb_res)
    c_p, p_p = _compute_member_number_parity(jb_fi, jb_cp)
    assert c_p["passes"] is True and p_p["passes"] is True

    # 3. Who Gets Engaged? (Ruling 273: B)
    eg_def = load_machinery_definition("data/groupings/candidates/machinery-who-gets-engaged.json")
    assert eg_def["stage"] == "preview"
    assert eg_def["look"] == "faces"
    assert "2026" not in eg_def["rule"]["sections"][0]["note"]
    assert "politics" in (_category_llm_pool_for_definition(eg_def) or ())
    eg_prod = build_container_machinery_producer(eg_def)
    assert eg_prod.stage == "preview" and eg_prod.look == "faces"
    eg_res = await produce_container_machinery(db, eg_def, now=NOW)
    assert eg_res.machinery_card["form_id"] == "benchmark_strip"
    assert eg_res.machinery_card["stage"] == "preview"
    assert eg_res.machinery_card["look"] == "faces"
    shown_ids = [m["id"] for m in eg_res.members]
    assert 57774265 not in shown_ids, "Roblox hours engaged must be excluded"
    assert 9990001 not in shown_ids, "Taylor Swift wedding must be excluded (273: B)"
    assert 109394 not in shown_ids, "Single-person Bobbi Althoff market must be excluded"
    assert 109389 not in shown_ids, "Single-person IShowSpeed market must be excluded"
    assert 8212355 in shown_ids, "Politics-filed couple must be included"
    # Reversed-order Sweeney/Braun twin (109618) deduped into covered_market_ids
    assert 61085868 in shown_ids and 109618 not in shown_ids
    assert 109618 in eg_res.covered_market_ids
    assert eg_res.sections[0]["visual_block"]["item_noun"] == "couples"
    assert eg_res.title == "Scooter Braun & Sydney Sweeney are the likeliest to get engaged at 36%, with Timothée Chalamet & Kylie Jenner at 13%"
    eg_fi = compose_roundup_feed_item(eg_prod, eg_res)
    assert 109618 in eg_fi["data"]["member_ids"]
    eg_cp = compose_roundup_container(eg_prod, eg_res)
    c_p, p_p = _compute_member_number_parity(eg_fi, eg_cp)
    assert c_p["passes"] is True and p_p["passes"] is True

    # 4. Returning-reader 32-C novelty seat eligibility (never pinned for first-time readers)
    base = [
        {"type": "futures", "score": 80.0 - i * 0.5, "data": {"id": 90000 + i, "name": f"S{i}", "status": "open"}}
        for i in range(25)
    ]
    base[12] = {"type": "futures", "score": 74.0, "data": {"id": 109618, "name": "Sydney Sweeney twin", "status": "open"}}
    first_time = insert_roundup_feed_items(base, [wc_fi, jb_fi, eg_fi], page_window=20, now=NOW, returning_reader=False)
    first_ids = [str((it.get("data") or {}).get("id") or "") for it in first_time]
    assert "109618" not in first_ids, "Unlinked twin 109618 must be pruned from Discover"
    assert not any(fid.startswith("roundup:machinery-") for fid in first_ids[:10]), "Never pinned for first-time readers"

    returning = apply_novelty_seats(first_time, returning_reader=True, seen_card_keys=set(), now=NOW)
    ret_ids = [str((it.get("data") or {}).get("id") or "") for it in returning]
    assert any(fid.startswith("roundup:machinery-") for fid in ret_ids[:10]), "Unseen fun set must be 32-C novelty-eligible"


@pytest.mark.asyncio
async def test_preview_stage_hidden_from_public_machinery_feed_and_search_but_served_on_preview() -> None:
    from unittest.mock import patch

    from app.utils.feed_cache import feed_response_cache_key
    from app.utils.roundup_containers import (
        add_roundup_feed_items,
        register_roundup_producer,
        reset_roundup_cache_for_tests,
    )
    from app.utils.search_collections import _append_roundup_matches

    # Existing public definitions default to stage='public', look='bars'
    fed_def = load_machinery_definition("data/groupings/candidates/machinery-fed-and-macro.json")
    assert fed_def["stage"] == "public"
    assert fed_def["look"] == "bars"

    # Cache keys stay isolated between 1.0.6 (False), machinery=1 (True), and machinery=preview
    k_none = feed_response_cache_key(limit=20, offset=0, machinery=False)
    k_pub = feed_response_cache_key(limit=20, offset=0, machinery=True)
    k_prev = feed_response_cache_key(limit=20, offset=0, machinery="preview")
    assert len({k_none, k_pub, k_prev}) == 3

    wc_def = load_machinery_definition("data/groupings/candidates/machinery-white-christmas.json")
    wc_prod = build_container_machinery_producer(wc_def, enabled=lambda: True)
    db = {"events": [], "markets": _sample_markets(), "paired_sets": {}, "market_histories": {}}
    base = [
        {"type": "futures", "score": 80.0 - i * 0.5, "data": {"id": 90000 + i, "name": f"S{i}", "status": "open"}}
        for i in range(25)
    ]

    with patch.dict(ROUNDUP_PRODUCERS, {}, clear=True):
        register_roundup_producer(wc_prod)
        reset_roundup_cache_for_tests()

        # Public machinery=1 MUST NOT serve stage="preview" groupings
        out_public = await add_roundup_feed_items(
            db,
            list(base),
            page_window=20,
            now=NOW,
            include_machinery=True,
            machinery_only=True,
            include_preview=False,
        )
        assert not any(
            ((it.get("data") or {}).get("collection_ref") or {}).get("slug") == "machinery-white-christmas"
            for it in out_public
        )

        # Public search MUST NOT leak stage="preview" groupings
        search_cards: list[dict] = []
        await _append_roundup_matches(db, search_cards, ("white", "christmas"))
        assert search_cards == []

        # Preview feed (machinery=preview) DOES serve stage="preview" groupings
        out_preview = await add_roundup_feed_items(
            db,
            list(base),
            page_window=20,
            now=NOW,
            include_machinery=True,
            machinery_only=True,
            include_preview=True,
        )
        assert any(
            ((it.get("data") or {}).get("collection_ref") or {}).get("slug") == "machinery-white-christmas"
            for it in out_preview
        )


@pytest.mark.asyncio
async def test_more_sets_excludes_preview_stage_under_public_set(monkeypatch: Any) -> None:
    """#13104 review: `select_more_sets` never offers stage='preview' sets under a public set page."""
    from unittest.mock import patch

    from app.utils.roundup_containers import (
        RoundupMembers,
        RoundupProducer,
        _roundup_local_cache,
        register_roundup_producer,
        reset_roundup_cache_for_tests,
        select_more_sets,
    )

    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    as_of = NOW.isoformat()
    now_ts = NOW.timestamp()
    fake_db = object()

    def _seed_producer(slug: str, name: str, category: str, stage: str) -> None:
        prod = RoundupProducer(
            slug=slug,
            name=name,
            kind="roundup",
            category=category,
            section_title="Markets",
            footer="2 markets",
            stage=stage,
            produce=lambda _db: RoundupMembers(()),
            enabled=lambda: True,
        )
        register_roundup_producer(prod)
        payload = {
            "slug": slug,
            "state": "published",
            "revision": 1,
            "subtitle": name,
            "member_count": 2,
            "container": {
                "id": 1000,
                "slug": slug,
                "name": name,
                "kind": "roundup",
                "category": category,
                "status": "open",
            },
            "sections": [
                {
                    "key": "0:roundup",
                    "class": "roundup",
                    "title": name,
                    "count": 1,
                    "members": [
                        {
                            "id": 700001,
                            "type": "market",
                            "card": {
                                "id": 700001,
                                "name": f"{name} leader",
                                "status": "open",
                                "price_observed_at": as_of,
                                "top_outcomes": [
                                    {"id": 1, "name": "Leader", "probability": 0.62, "rendered_percent": 62}
                                ],
                            },
                            "destination": {
                                "kind": "market",
                                "id": 700001,
                                "web": "/futures/700001",
                                "api": "/api/futures/700001",
                            },
                        }
                    ],
                }
            ],
        }
        _roundup_local_cache[(slug, id(fake_db))] = (now_ts, {"type": "bundle"}, payload)

    with patch.dict(ROUNDUP_PRODUCERS, {}, clear=True):
        reset_roundup_cache_for_tests()
        _seed_producer("machinery-oscars-best-picture", "Oscars Best Picture", "entertainment", "public")
        _seed_producer("machinery-fed-and-macro", "Fed & Macro", "economics", "public")
        _seed_producer("machinery-next-james-bond", "The Next James Bond Film", "entertainment", "preview")

        cards = await select_more_sets(
            fake_db,
            exclude_slugs={"machinery-oscars-best-picture"},
            current_slug="machinery-oscars-best-picture",
            current_category="entertainment",
            limit=2,
            now=NOW,
            evaluate_uncached=False,
        )
        slugs = [c["slug"] for c in cards]
        assert slugs == ["machinery-fed-and-macro"], f"preview set leaked into more_sets: {slugs}"

