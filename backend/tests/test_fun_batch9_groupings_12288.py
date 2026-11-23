"""Tests for #12288 Batch 9 preview groupings (six sets across diverse forms)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils.container_machinery import (
    _CATEGORY_LLM_POOL,
    _category_llm_pool_for_definition,
    _compute_member_number_parity,
    build_container_machinery_producer,
    discover_machinery_candidate_paths,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.discover_fun_tags import clear_fun_markets_cache
from app.utils.discover_opening_mix import (
    TOPIC_ENTERTAINMENT,
    TOPIC_ODD,
    TOPIC_SPORTS,
    classify_discover_opening_topic,
)
from app.utils.machinery_batch_gate import estimate_headline_lines_390px
from app.utils.roundup_containers import (
    compose_roundup_container,
    compose_roundup_feed_item,
)

BATCH9_SLUGS: tuple[str, ...] = (
    "machinery-golf-majors-and-ryder-cup",
    "machinery-ufc-next-fights-and-boxing",
    "machinery-critics-choice-and-oscars-2027",
    "machinery-the-big-one-and-cosmic-risks",
    "machinery-live-music-broadway-box-office",
    "machinery-tech-shocks-and-ai-bankruptcies",
)
NOW = datetime(2026, 11, 23, 18, 0, tzinfo=timezone.utc)


def _sample_batch9_markets() -> list[dict]:
    specs = [
        # 1. Golf Majors & The Ryder Cup
        (3970169, "2027 Ryder Cup Winner", "golf", [("Team Europe", 0.53), ("Team USA", 0.40), ("Tie", 0.07)]),
        (61056094, "2027 The Masters Champion", "golf", [("Scottie Scheffler", 0.21), ("Rory McIlroy", 0.12)]),
        (11224673, "Will LIV Golf announce shutdown in 2026?", "golf", [("Yes", 0.03)]),
        (176, "Will Scottie Scheffler win the grand slam before 2028?", "golf", [("Yes", 0.02)]),
        # 2. UFC Next Fights & Heavyweight Boxing
        (58852162, "UFC: Who Will Conor McGregor Fight Next?", "mma", [("Max Holloway", 0.30), ("Michael Chandler", 0.21), ("Nate Diaz", 0.14)]),
        (20565989, "UFC: Who Will Sean Strickland Fight Next?", "mma", [("Nassourdine Imavov", 0.81), ("Khamzat Chimaev", 0.07)]),
        (10603290, "UFC: Who will Carlos Ulberg fight next?", "mma", [("Magomed Ankalaev", 0.40), ("Paulo Costa", 0.10)]),
        (57284647, "UFC: Who Will Magomed Ankalaev Fight Next?", "mma", [("Carlos Ulberg", 0.28), ("Paulo Costa", 0.13)]),
        (10437337, "Tyson Fury and Anthony Joshua to Fight in 2026", "boxing", [("Yes", 0.04)]),
        (61141844, "UFC: Who Will Jean Silva Fight Next?", "mma", [("Lerone Murphy", 0.25), ("Kevin Vallejos", 0.24)]),
        # 3. Critics Choice & Below-the-Line Oscars
        (65536357, "Critics Choice Awards: Best Director", "entertainment", [("Christopher Nolan", 0.75), ("Denis Villeneuve", 0.12), ("Alejandro González Iñárritu", 0.08)]),
        (58495125, "Oscars 2027: Best Supporting Actor Winner", "entertainment", [("Paul Giamatti", 0.41), ("Andrew Garfield", 0.40), ("Sean Penn", 0.09)]),
        (58492242, "Oscars 2027: Best International Feature Film Winner", "entertainment", [("La Bola Negra", 0.83), ("All of a Sudden", 0.05)]),
        (58492241, "Oscars 2027: Best Original Score Winner", "entertainment", [("The Odyssey", 0.69), ("Dune: Part Three", 0.12)]),
        (65536307, "Critics Choice Awards: Best Picture", "entertainment", [("You Can See Everything", 0.66), ("The Odyssey", 0.20)]),
        (58495122, "Oscars 2027: Best Adapted Screenplay Winner", "entertainment", [("La Bola Negra", 0.62), ("The Invite", 0.24)]),
        # 4. The Big One & Cosmic Risks
        (114132, "5kt meteor strike in 2026?", "tech", [("Yes", 0.13)]),
        (59153600, "Highest earthquake magnitude in 2026?", "weather", [("7.9 or below", 0.67), ("9.0 or above", 0.12)]),
        (108235, "Will there be an at least 8.0 magnitude earthquake in California before 2035?", "weather", [("Before 2035", 0.21)]),
        (114083, "Major volcano eruption (VEI >=6) in 2026?", "weather", [("Yes", 0.05)]),
        (114162, "1 megaton meteor strike in 2026?", "weather", [("Yes", 0.04)]),
        # 5. Live Music, Broadway & Box Office
        (59693546, "How many people will attend Broadway shows during the 2026-27 season?", "entertainment", [("above 13,500,000", 0.96), ("above 13,750,000", 0.86)]),
        (59693469, "Who Will Perform at Red Rocks in 2027?", "entertainment", [("Mt. Joy", 0.95), ("Rebelution", 0.91)]),
        (11415154, "Which movie has biggest opening week in 2026?", "entertainment", [("Avengers: Doomsday", 0.89), ("Spider-Man: Brand New Day", 0.11)]),
        (52755614, "Top U.S. Selling Album: 2026", "entertainment", [("ARIRANG", 0.81), ("GNX", 0.05)]),
        (59693617, "When will Drake release a new album?", "entertainment", [("Before Jan 1, 2027", 0.06), ("Before Dec 1, 2026", 0.05)]),
        # 6. Tech Shocks & AI Bankruptcies
        (7266228, "When will Tesla and SpaceX merge?", "tech", [("Before 2028", 0.87), ("Before May 1, 2027", 0.66)]),
        (61321725, "CoreWeave announces bankruptcy by...?", "tech", [("December 31, 2027", 0.16), ("December 31, 2028", 0.23)]),
        (61321727, "Anthropic files for bankruptcy by...?", "tech", [("December 31, 2027", 0.09), ("December 31, 2028", 0.15)]),
        (61321742, "OpenAI files for bankruptcy by...?", "tech", [("December 31, 2027", 0.06), ("December 31, 2028", 0.12)]),
        (70733127, "Removed from U.S. defense list by June 30, 2027?", "tech", [("CXMT", 0.25), ("Hesai", 0.17)]),
    ]
    return [
        {
            "id": mid,
            "name": name,
            "status": "open",
            "source": "polymarket",
            "category": cat,
            "sport": None,
            "llm_sport_category": cat,
            "market_tier": 1,
            "volume": 300_000.0,
            "lifetime_volume": 300_000.0,
            "resolution_date": "2028-01-01T00:00:00Z",
            "newest_outcome_updated_at": NOW.isoformat(),
            "outcomes": [
                {"id": mid * 100 + i, "name": oname, "probability": prob}
                for i, (oname, prob) in enumerate(outs)
            ],
        }
        for mid, name, cat, outs in specs
    ]


def _sample_batch9_histories() -> dict[int, list[dict]]:
    # Outcome id for market 114132 ('Yes') is 114132 * 100 + 0 = 11413200
    pts = [
        {"timestamp": (NOW - timedelta(hours=160)).isoformat(), "probability": 0.05},
        {"timestamp": (NOW - timedelta(hours=84)).isoformat(), "probability": 0.19},
        {"timestamp": (NOW - timedelta(hours=4)).isoformat(), "probability": 0.13},
    ]
    return {11413200: pts}


@pytest.mark.asyncio
async def test_batch9_six_preview_groupings_build_with_form_diversity(caplog: pytest.LogCaptureFixture) -> None:
    clear_fun_markets_cache()
    caplog.set_level(logging.WARNING)
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    assert set(BATCH9_SLUGS) <= set(paths_by_slug)

    db = {
        "events": [],
        "markets": _sample_batch9_markets(),
        "paired_sets": {},
        "market_histories": _sample_batch9_histories(),
    }

    expected_topics = {
        "machinery-golf-majors-and-ryder-cup": TOPIC_SPORTS,
        "machinery-ufc-next-fights-and-boxing": TOPIC_SPORTS,
        "machinery-critics-choice-and-oscars-2027": TOPIC_ENTERTAINMENT,
        "machinery-the-big-one-and-cosmic-risks": TOPIC_ODD,
        "machinery-live-music-broadway-box-office": TOPIC_ENTERTAINMENT,
        "machinery-tech-shocks-and-ai-bankruptcies": TOPIC_ODD,
    }
    expected_forms = {
        "machinery-golf-majors-and-ryder-cup": "duel_bar",
        "machinery-ufc-next-fights-and-boxing": "contender_spotlight",
        "machinery-critics-choice-and-oscars-2027": "sibling_fields_grid",
        "machinery-the-big-one-and-cosmic-risks": "probability_history_chart",
        "machinery-live-music-broadway-box-office": "benchmark_strip",
        "machinery-tech-shocks-and-ai-bankruptcies": "benchmark_strip",
    }

    forms_seen: dict[str, str] = {}
    seen_headlines: set[str] = set()
    by_slug = {}

    for slug in BATCH9_SLUGS:
        defn = load_machinery_definition(paths_by_slug[slug])
        assert defn.get("stage") == "preview", slug
        pool = _category_llm_pool_for_definition(defn)
        assert pool is not None, f"{slug} missing scoped llm pool"
        prod = build_container_machinery_producer(defn)
        assert prod.stage == "preview", slug

        res = await produce_container_machinery(db, defn, now=NOW)
        assert hasattr(res, "machinery_card"), (slug, res)
        mc = res.machinery_card
        assert mc["stage"] == "preview"
        assert mc["title"] and "{answer}" not in mc["title"], (slug, mc["title"])
        assert "by by " not in mc["title"], (slug, mc["title"])
        assert mc["title"] not in seen_headlines, f"Duplicate headline: {mc['title']}"
        seen_headlines.add(mc["title"])

        fi = compose_roundup_feed_item(prod, res)
        cp = compose_roundup_container(prod, res)
        c_p, p_p = _compute_member_number_parity(fi, cp)
        assert c_p["passes"] is True and p_p["passes"] is True, (slug, c_p, p_p)
        assert classify_discover_opening_topic(fi) == expected_topics[slug], slug

        forms_seen[slug] = str(mc["form_id"])
        assert forms_seen[slug] == expected_forms[slug], (slug, forms_seen[slug])
        by_slug[slug] = (fi, cp, mc, defn)

    assert sum(1 for f in forms_seen.values() if f == "benchmark_strip") <= 2
    assert len(set(forms_seen.values())) >= 5
    assert not any("dropped row pictures" in rec.message for rec in caplog.records)

    # Check capitalization, 3-row Ryder Cup with Tie, settled exclusion, timeless copy, and <=3L headlines.
    ryder_cp, ryder_card = by_slug["machinery-golf-majors-and-ryder-cup"][1], by_slug["machinery-golf-majors-and-ryder-cup"][2]
    assert "2027 Ryder Cup" in ryder_card["title"]
    assert "Team Europe" in ryder_card["title"] and "Team USA" in ryder_card["title"]
    assert [r["name"] for r in ryder_card["rows"]] == ["Team Europe", "Team USA", "Tie"]
    for row in ryder_cp["sections"][0]["visual_block"]["items"][0]["outcomes"]:
        if row["name"] == "Tie":
            assert not row["art"]["url"], row
        else:
            assert row["art"]["url"], row

    ufc_card = by_slug["machinery-ufc-next-fights-and-boxing"][2]
    assert "Conor McGregor's" in ufc_card["title"]
    assert "the Conor" not in ufc_card["title"] and "the conor" not in ufc_card["title"].lower()
    for row in ufc_card["rows"]:
        assert row["art"]["url"], row

    critics_card = by_slug["machinery-critics-choice-and-oscars-2027"][2]
    assert "Christopher Nolan" in critics_card["title"]
    assert "Paul Giamatti" in critics_card["title"]
    assert "La Bola Negra" not in critics_card["title"]
    for row in critics_card["rows"]:
        assert row["art"]["url"], row

    cosmic_cp, cosmic_card = by_slug["machinery-the-big-one-and-cosmic-risks"][1], by_slug["machinery-the-big-one-and-cosmic-risks"][2]
    assert cosmic_card["title"].startswith("The chance of a 5-kiloton meteor strike in 2026 ")
    assert "shifted over the past week" not in str(cosmic_card.get("subtitle") or "")
    for sec in cosmic_cp["sections"]:
        assert "shifted over the past week" not in str(sec.get("note") or "")

    tech_card = by_slug["machinery-tech-shocks-and-ai-bankruptcies"][2]
    assert "by by" not in tech_card["title"]

    for slug in BATCH9_SLUGS:
        hl = str(by_slug[slug][2]["title"])
        assert estimate_headline_lines_390px(hl) <= 3, (slug, estimate_headline_lines_390px(hl), hl)

    # Approved licenses on all configured card hero images.
    for slug in BATCH9_SLUGS:
        rule = by_slug[slug][3].get("rule") or {}
        if rule.get("card_image_url"):
            lic = str(rule.get("card_image_license") or "").lower()
            assert "cc0" in lic or "public domain" in lic, (slug, lic)


def test_batch9_category_pools_cover_golf_and_mma() -> None:
    assert "golf" in _CATEGORY_LLM_POOL
    assert "mma" in _CATEGORY_LLM_POOL
    assert "boxing" in _CATEGORY_LLM_POOL["mma"]


def test_batch9_market_ids_disjoint_from_earlier_batches() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "groupings"
    earlier_ids: set[int] = set()
    for fname in (
        "batch3_curated_sets.json",
        "batch4_curated_sets.json",
        "batch5_curated_sets.json",
        "batch6_curated_sets.json",
        "batch7_curated_sets.json",
        "batch8_curated_sets.json",
    ):
        doc = json.loads((root / fname).read_text(encoding="utf-8"))
        for s in (doc.get("sets") or {}).values():
            for e in s.get("entries") or ():
                earlier_ids.add(int(e["id"]))

    b9 = json.loads((root / "batch9_curated_sets.json").read_text(encoding="utf-8"))
    b9_ids = [
        int(e["id"])
        for s in (b9.get("sets") or {}).values()
        for e in s.get("entries") or ()
    ]
    assert 70709343 not in b9_ids
    assert len(b9_ids) == len(set(b9_ids)), "Duplicate market id inside batch9_curated_sets.json"
    overlap = set(b9_ids) & earlier_ids
    assert not overlap, f"Batch 9 overlaps earlier curated sets: {sorted(overlap)}"
