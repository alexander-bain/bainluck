"""Tests for #13097 Batch 2 fun groupings (all stage='preview').

Covers the four Batch 2 sets:
1. machinery-taylor-swift (famous person #1: Taylor Swift, taste-guarded, wedding excluded)
2. machinery-long-shots (Long Shots People Talk About: aliens, Mars, Taylor Swift + Pope Leo XIV, etc.)
3. machinery-long-awaited (Long-Awaited Releases: Half-Life 3, Winds of Winter, Elder Scrolls VI, etc.)
4. machinery-space-race (Space & Mars: Moon/Mars milestones)

Verifies:
- All four load via discover_machinery_candidate_paths() with stage='preview'
  (excluded from public Discover feed / more_sets until Fable's look).
- fun_sub_tag selector enforces fun_market_ids_for_sub_tag + check_fun_taste_guard
  + exclude_tokens (wedding/divorce/pregnancy/etc. never leak).
- Card rows and container page rows maintain 100% parity (same titles & numbers),
  carry clean item_noun values, and produce sentence-shaped headlines.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.utils.container_machinery import (
    _compute_member_number_parity,
    build_container_machinery_producer,
    discover_machinery_candidate_paths,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.discover_fun_tags import (
    fun_market_ids_for_sub_tag,
    fun_market_short_label,
    load_fun_markets_registry,
)
from app.utils.roundup_containers import (
    RoundupRefusal,
    compose_roundup_container,
    compose_roundup_feed_item,
)

BATCH2_SLUGS = (
    "machinery-taylor-swift",
    "machinery-long-shots",
    "machinery-long-awaited",
    "machinery-space-race",
)
NOW = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)


def _mk_market(
    mid: int,
    name: str,
    outcomes: list[tuple[str, float]],
    *,
    category: str = "entertainment",
    volume: float = 50_000.0,
) -> dict:
    now_iso = datetime(2026, 11, 20, 17, 0, tzinfo=timezone.utc).isoformat()
    return {
        "id": mid,
        "name": name,
        "title": name,
        "status": "open",
        "source": "kalshi",
        "category": category,
        "llm_sport_category": category,
        "volume": volume,
        "resolution_date": "2027-06-01T00:00:00+00:00",
        "newest_outcome_updated_at": now_iso,
        "outcomes": [
            {
                "id": mid * 10 + i,
                "name": oname,
                "probability": prob,
                "last_updated": now_iso,
            }
            for i, (oname, prob) in enumerate(outcomes)
        ],
    }


def test_batch2_candidate_files_are_discovered_as_preview_with_clean_metadata():
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    expected_nouns = {
        "machinery-taylor-swift": "markets",
        "machinery-long-shots": "long shots",
        "machinery-long-awaited": "releases",
        "machinery-space-race": "milestones",
    }
    for slug in BATCH2_SLUGS:
        assert slug in paths_by_slug, f"Missing candidate file for {slug}"
        defn = load_machinery_definition(paths_by_slug[slug])
        assert defn["stage"] == "preview"
        rule = defn["rule"]
        assert rule.get("headline_predicate"), f"{slug} must set headline_predicate"
        sec = rule["sections"][0]
        assert sec.get("item_noun") == expected_nouns[slug]
        sub_tag = sec["atom_query"].get("fun_sub_tag")
        assert sub_tag and len(fun_market_ids_for_sub_tag(sub_tag)) >= 4


@pytest.mark.asyncio
async def test_taylor_swift_preview_builds_cleanly_and_blocks_wedding_and_taste_leaks():
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    defn = load_machinery_definition(paths_by_slug["machinery-taylor-swift"])
    prod = build_container_machinery_producer(defn)
    assert prod.stage == "preview"
    snapshot = {
        "events": [],
        "paired_sets": {},
        "market_histories": {},
        "markets": [
            _mk_market(109309, "Will Taylor Swift (Taylor's Version) be announced this year?", [("Yes", 0.42), ("No", 0.58)]),
            _mk_market(109310, "Will Reputation (Taylor's Version) be announced this year?", [("Yes", 0.08), ("No", 0.92)]),
            _mk_market(109295, "Will Taylor Swift meet with Pope Leo XIV before 2027?", [("Yes", 0.04), ("No", 0.96)]),
            _mk_market(109291, "Blake Lively and Taylor Swift seen together in public this year?", [("Yes", 0.035), ("No", 0.965)], category="politics"),
            # Untracked / wedding / taste leaks must never enter
            _mk_market(52755900, "Taylor Swift wedding dress designer?", [("Yes", 0.50), ("No", 0.50)]),
            _mk_market(99999901, "Taylor Swift pregnant in 2026?", [("Yes", 0.20), ("No", 0.80)]),
        ],
    }
    res = await produce_container_machinery(snapshot, defn, now=NOW)
    assert not isinstance(res, RoundupRefusal), f"Unexpected refusal: {res}"
    fi = compose_roundup_feed_item(prod, res)
    cp = compose_roundup_container(prod, res)
    assert fi is not None and cp is not None
    sec = cp["sections"][0]
    member_ids = [m["id"] for m in sec["members"]]
    assert set(member_ids) == {109309, 109310, 109295, 109291}
    assert 52755900 not in member_ids
    assert 99999901 not in member_ids
    c_p, p_p = _compute_member_number_parity(fi, cp)
    assert c_p["passes"] is True and p_p["passes"] is True


@pytest.mark.asyncio
async def test_long_shots_long_awaited_and_space_race_preview_builds_cleanly():
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}

    # 1. Long shots
    ls_defn = load_machinery_definition(paths_by_slug["machinery-long-shots"])
    ls_prod = build_container_machinery_producer(ls_defn)
    ls_snap = {
        "events": [],
        "paired_sets": {},
        "market_histories": {},
        "markets": [
            _mk_market(109435, "Will the U.S. confirm that aliens exist?", [("Before Jan 20, 2029", 0.155), ("Before Jan 1, 2028", 0.115)], category="tech"),
            _mk_market(108218, "Will Elon Musk visit Mars in his lifetime?", [("Yes", 0.115), ("No", 0.885)], category="culture"),
            _mk_market(109295, "Will Taylor Swift meet with Pope Leo XIV before 2027?", [("Yes", 0.04), ("No", 0.96)]),
            _mk_market(113504, "Will Jesus Christ return before 2027?", [("Yes", 0.009), ("No", 0.991)]),
        ],
    }
    ls_res = await produce_container_machinery(ls_snap, ls_defn, now=NOW)
    assert not isinstance(ls_res, RoundupRefusal), f"long-shots failed: {ls_res}"
    ls_fi = compose_roundup_feed_item(ls_prod, ls_res)
    ls_cp = compose_roundup_container(ls_prod, ls_res)
    assert ls_fi is not None and ls_cp is not None
    assert len(ls_cp["sections"][0]["members"]) == 4
    c_p, p_p = _compute_member_number_parity(ls_fi, ls_cp)
    assert c_p["passes"] is True and p_p["passes"] is True

    # 2. Long-awaited releases
    la_defn = load_machinery_definition(paths_by_slug["machinery-long-awaited"])
    la_prod = build_container_machinery_producer(la_defn)
    la_snap = {
        "events": [],
        "paired_sets": {},
        "market_histories": {},
        "markets": [
            _mk_market(113343, "Will Half-Life 3 be announced before 2027?", [("Yes", 0.075), ("No", 0.925)]),
            _mk_market(109247, "The Winds of Winter: Release date announced this year?", [("Yes", 0.055), ("No", 0.945)]),
            _mk_market(108494, "When will Elder Scrolls VI be released?", [("Before 2028", 0.12), ("Before 2027", 0.025)]),
            _mk_market(109540, "PS6 announced this year?", [("Yes", 0.025), ("No", 0.975)]),
        ],
    }
    la_res = await produce_container_machinery(la_snap, la_defn, now=NOW)
    assert not isinstance(la_res, RoundupRefusal), f"long-awaited failed: {la_res}"
    la_fi = compose_roundup_feed_item(la_prod, la_res)
    la_cp = compose_roundup_container(la_prod, la_res)
    assert la_fi is not None and la_cp is not None
    assert len(la_cp["sections"][0]["members"]) == 4
    c_p, p_p = _compute_member_number_parity(la_fi, la_cp)
    assert c_p["passes"] is True and p_p["passes"] is True

    # 3. Space & Mars
    sp_defn = load_machinery_definition(paths_by_slug["machinery-space-race"])
    sp_prod = build_container_machinery_producer(sp_defn)
    sp_snap = {
        "events": [],
        "paired_sets": {},
        "market_histories": {},
        "markets": [
            _mk_market(108300, "Will Blue Origin land on the moon before SpaceX?", [("Yes", 0.68), ("No", 0.32)], category="tech"),
            _mk_market(108236, "Will a humanoid robot walk on Mars before a human does?", [("Yes", 0.514), ("No", 0.486)], category="tech"),
            _mk_market(108273, "Will SpaceX land anything successfully on Mars before 2030?", [("Yes", 0.24), ("No", 0.76)], category="tech"),
            _mk_market(108218, "Will Elon Musk visit Mars in his lifetime?", [("Yes", 0.115), ("No", 0.885)], category="culture"),
        ],
    }
    sp_res = await produce_container_machinery(sp_snap, sp_defn, now=NOW)
    assert not isinstance(sp_res, RoundupRefusal), f"space-race failed: {sp_res}"
    sp_fi = compose_roundup_feed_item(sp_prod, sp_res)
    sp_cp = compose_roundup_container(sp_prod, sp_res)
    assert sp_fi is not None and sp_cp is not None
    assert len(sp_cp["sections"][0]["members"]) == 4
    c_p, p_p = _compute_member_number_parity(sp_fi, sp_cp)
    assert c_p["passes"] is True and p_p["passes"] is True


def test_all_fun_markets_have_short_labels_and_simpsons_beyonce_left_long_awaited():
    registry = load_fun_markets_registry()
    for mid, entry in registry.markets.items():
        assert entry.short_label, f"fun market {mid} ({entry.title}) is missing short_label"
        assert not entry.short_label.endswith("?"), f"short_label for {mid} should not be a question"
        assert fun_market_short_label(mid) == entry.short_label

    long_awaited_ids = set(fun_market_ids_for_sub_tag("long-awaited"))
    assert 108275 not in long_awaited_ids, "The Simpsons ending must not be in long-awaited"
    assert 108306 not in long_awaited_ids, "Beyoncé's next genre must not be in long-awaited"


@pytest.mark.asyncio
async def test_batch2_headlines_use_short_labels_leading_answers_and_long_shots_ceiling():
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}

    # 1. Taylor Swift uses short labels in rows and headline
    ts_defn = load_machinery_definition(paths_by_slug["machinery-taylor-swift"])
    ts_prod = build_container_machinery_producer(ts_defn)
    ts_snap = {
        "events": [],
        "paired_sets": {},
        "market_histories": {},
        "markets": [
            _mk_market(109309, "Will Taylor Swift (Taylor's Version) be announced this year?", [("Yes", 0.41), ("No", 0.59)]),
            _mk_market(109310, "Will Reputation (Taylor's Version) be announced this year?", [("Yes", 0.08), ("No", 0.92)]),
            _mk_market(109295, "Will Taylor Swift meet with Pope Leo XIV before 2027?", [("Yes", 0.04), ("No", 0.96)]),
            _mk_market(109291, "Blake Lively and Taylor Swift seen together in public this year?", [("Yes", 0.04), ("No", 0.96)], category="politics"),
        ],
    }
    ts_res = await produce_container_machinery(ts_snap, ts_defn, now=NOW)
    assert not isinstance(ts_res, RoundupRefusal)
    ts_fi = compose_roundup_feed_item(ts_prod, ts_res)
    assert ts_fi["data"]["roundup"]["machinery_card"]["title"] == (
        "Debut (Taylor's Version) is the likeliest Taylor Swift move at 41%, "
        "with Reputation (Taylor's Version) at 8%"
    )

    # 2. Long shots: ceiling <= 20%, thin markets (<10k) out, volume tie-break, leading answer in row + headline
    ls_defn = load_machinery_definition(paths_by_slug["machinery-long-shots"])
    ls_prod = build_container_machinery_producer(ls_defn)
    ls_snap = {
        "events": [],
        "paired_sets": {},
        "market_histories": {},
        "markets": [
            # Excluded: > 20%
            _mk_market(56762760, "LA28 Olympics run as scheduled?", [("Yes", 0.90), ("No", 0.10)], volume=58_597.0),
            _mk_market(112828, "Will a major meteor strike hit Earth before 2030?", [("Yes", 0.41), ("No", 0.59)], volume=160_340.0),
            _mk_market(112833, "Costco raises hot dog combo price?", [("Before 2030", 0.30), ("Before 2028", 0.10)], volume=80_147.0),
            # Excluded: thin volume (< 10,000) even when <= 20%
            _mk_market(63336261, "Will Jeff Bezos go to space before 2028?", [("Yes", 0.14), ("No", 0.86)], volume=440.0),
            _mk_market(30587891, "Will Banksy create a new mural?", [("Yes", 0.15), ("No", 0.85)], volume=4_209.0),
            # Included (all <= 20% and volume >= 10,000); tie at 15.5% broken by volume
            _mk_market(66925975, "Will Bryan Johnson dunk before 2027?", [("Yes", 0.155), ("No", 0.845)], volume=23_626.0),
            _mk_market(109435, "Will the U.S. confirm that aliens exist?", [("Before Jan 20, 2029", 0.155), ("Before Jan 1, 2028", 0.115)], volume=37_388_641.0),
            _mk_market(108339, "Will Trump go on SNL during his second term?", [("Yes", 0.155), ("No", 0.845)], volume=27_619.0),
            _mk_market(108218, "Will Elon Musk visit Mars in his lifetime?", [("Yes", 0.12), ("No", 0.88)], volume=126_757.0),
        ],
    }
    ls_res = await produce_container_machinery(ls_snap, ls_defn, now=NOW)
    assert not isinstance(ls_res, RoundupRefusal)
    ls_fi = compose_roundup_feed_item(ls_prod, ls_res)
    ls_cp = compose_roundup_container(ls_prod, ls_res)
    ls_items = ls_cp["sections"][0]["visual_block"]["items"]
    ls_ids = [it["market_id"] for it in ls_items]
    assert ls_ids == [109435, 108339, 66925975, 108218]
    assert all(it["outcomes"][0]["rendered_percent"] <= 20 for it in ls_items)
    assert ls_items[0]["title"] == "U.S. confirming aliens: Before Jan 20, 2029"
    assert ls_fi["data"]["roundup"]["machinery_card"]["title"] == (
        "U.S. confirming aliens: Before Jan 20, 2029 is the likeliest long shot at 16%, "
        "with Trump on SNL at 16%"
    )

    # 3. Long-awaited: Simpsons & Beyonce excluded; "when" market names leading answer in row + headline
    la_defn = load_machinery_definition(paths_by_slug["machinery-long-awaited"])
    la_prod = build_container_machinery_producer(la_defn)
    la_snap = {
        "events": [],
        "paired_sets": {},
        "market_histories": {},
        "markets": [
            _mk_market(108239, "Next Pirates of the Caribbean film: Will Johnny Depp be cast?", [("Yes", 0.74), ("No", 0.26)]),
            _mk_market(67717832, "GTA VI on PC in what month?", [("After March 2027", 0.69), ("Before Dec 2026", 0.05)]),
            _mk_market(108275, "Will there be an announcement that The Simpsons is ending?", [("Yes", 0.67), ("No", 0.33)]),
            _mk_market(108306, "What genre will Beyonce’s next album be?", [("Rock", 0.64), ("Country", 0.20)]),
            _mk_market(112760, "When will Frank Ocean release a new album?", [("2027", 0.31), ("2026", 0.18)]),
        ],
    }
    la_res = await produce_container_machinery(la_snap, la_defn, now=NOW)
    assert not isinstance(la_res, RoundupRefusal)
    la_fi = compose_roundup_feed_item(la_prod, la_res)
    la_cp = compose_roundup_container(la_prod, la_res)
    la_items = la_cp["sections"][0]["visual_block"]["items"]
    la_ids = [it["market_id"] for it in la_items]
    assert la_ids == [108239, 67717832, 112760]
    assert la_items[1]["title"] == "GTA VI on PC: After March 2027"
    assert la_items[2]["title"] == "Frank Ocean's next album: 2027"
    assert la_fi["data"]["roundup"]["machinery_card"]["title"] == (
        "Johnny Depp in Pirates is the likeliest long-awaited release at 74%, "
        "with GTA VI on PC: After March 2027 at 69%"
    )

    # 4. Space & Mars: "which" market names leading country in row + headline; thin Bezos ($440) out
    sp_defn = load_machinery_definition(paths_by_slug["machinery-space-race"])
    sp_prod = build_container_machinery_producer(sp_defn)
    sp_snap = {
        "events": [],
        "paired_sets": {},
        "market_histories": {},
        "markets": [
            _mk_market(108300, "Will Blue Origin land on the moon before SpaceX?", [("Yes", 0.68), ("No", 0.32)], category="tech"),
            _mk_market(108247, "Which country will be the next to send humans to the Moon?", [("United States", 0.57), ("China", 0.43)], category="tech"),
            _mk_market(108236, "Will a humanoid robot walk on Mars before a human does?", [("Yes", 0.514), ("No", 0.486)], category="tech"),
            _mk_market(63336261, "Will Jeff Bezos go to space before 2028?", [("Yes", 0.14), ("No", 0.86)], category="tech", volume=440.0),
        ],
    }
    sp_res = await produce_container_machinery(sp_snap, sp_defn, now=NOW)
    assert not isinstance(sp_res, RoundupRefusal)
    sp_fi = compose_roundup_feed_item(sp_prod, sp_res)
    sp_cp = compose_roundup_container(sp_prod, sp_res)
    sp_items = sp_cp["sections"][0]["visual_block"]["items"]
    assert [it["market_id"] for it in sp_items] == [108300, 108247, 108236]
    assert sp_items[1]["title"] == "Next country on the Moon: United States"
    assert sp_fi["data"]["roundup"]["machinery_card"]["title"] == (
        "Blue Origin beating SpaceX to the Moon leads the race to the Moon and Mars at 68%, "
        "with Next country on the Moon: United States at 57%"
    )
