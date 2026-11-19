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
    ]


@pytest.mark.asyncio
async def test_batch1_three_fun_groupings_build_cleanly_with_full_parity_and_twin_dedup() -> None:
    db = {"events": [], "markets": _sample_markets(), "paired_sets": {}, "market_histories": {}}

    # 1. White Christmas
    wc_def = load_machinery_definition("data/groupings/candidates/machinery-white-christmas.json")
    assert "weather" in (_category_llm_pool_for_definition(wc_def) or ())
    wc_prod = build_container_machinery_producer(wc_def)
    wc_res = await produce_container_machinery(db, wc_def, now=NOW)
    assert wc_res.machinery_card["form_id"] == "benchmark_strip"
    assert [r["name"] for r in wc_res.machinery_card["rows"]] == ["Pittsburgh", "Milwaukee", "Detroit"]
    assert [r["rendered_percent"] for r in wc_res.machinery_card["rows"]] == [44, 41, 38]
    assert wc_res.title == "Pittsburgh leads White Christmas at 44%, with Milwaukee at 41%"
    wc_fi = compose_roundup_feed_item(wc_prod, wc_res)
    wc_cp = compose_roundup_container(wc_prod, wc_res)
    c_p, p_p = _compute_member_number_parity(wc_fi, wc_cp)
    assert c_p["passes"] is True and p_p["passes"] is True

    # 2. The Next James Bond Film
    jb_def = load_machinery_definition("data/groupings/candidates/machinery-next-james-bond.json")
    jb_prod = build_container_machinery_producer(jb_def)
    jb_res = await produce_container_machinery(db, jb_def, now=NOW)
    assert jb_res.machinery_card["form_id"] == "sibling_fields_grid"
    assert len(jb_res.members) == 3
    assert jb_res.machinery_card["rows"][0]["name"].startswith("James Bond Theme · Raye")
    jb_fi = compose_roundup_feed_item(jb_prod, jb_res)
    jb_cp = compose_roundup_container(jb_prod, jb_res)
    c_p, p_p = _compute_member_number_parity(jb_fi, jb_cp)
    assert c_p["passes"] is True and p_p["passes"] is True

    # 3. Who Gets Engaged? (Ruling 273: B)
    eg_def = load_machinery_definition("data/groupings/candidates/machinery-who-gets-engaged.json")
    assert "politics" in (_category_llm_pool_for_definition(eg_def) or ())
    eg_prod = build_container_machinery_producer(eg_def)
    eg_res = await produce_container_machinery(db, eg_def, now=NOW)
    assert eg_res.machinery_card["form_id"] == "benchmark_strip"
    shown_ids = [m["id"] for m in eg_res.members]
    assert 57774265 not in shown_ids, "Roblox hours engaged must be excluded"
    assert 9990001 not in shown_ids, "Taylor Swift wedding must be excluded (273: B)"
    assert 8212355 in shown_ids, "Politics-filed couple must be included"
    # Reversed-order Sweeney/Braun twin (109618) deduped into covered_market_ids
    assert 61085868 in shown_ids and 109618 not in shown_ids
    assert 109618 in eg_res.covered_market_ids
    assert eg_res.title.startswith("Scooter Braun & Sydney Sweeney lead Who Gets Engaged at 36%")
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
