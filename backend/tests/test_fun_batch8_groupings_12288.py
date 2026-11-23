"""Tests for #12288 Batch 8 preview fun groupings (8 sets matching Alex's mix)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pytest

from app.utils.container_machinery import (
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
    TOPIC_TECH_BUSINESS,
    classify_discover_opening_topic,
)
from app.utils.roundup_containers import compose_roundup_container, compose_roundup_feed_item

BATCH8_SLUGS: tuple[str, ...] = (
    "machinery-earth-quakes-and-storms-2026",
    "machinery-chess-milestones-and-curiosities",
    "machinery-climate-water-and-energy",
    "machinery-music-and-grammys-2026",
    "machinery-tv-and-gaming-2026",
    "machinery-soccer-cups-and-relegation",
    "machinery-nfl-conference-and-division-races",
    "machinery-ai-math-and-data-centers",
)
NOW = datetime(2026, 11, 23, 5, 0, tzinfo=timezone.utc)


def _sample_batch8_markets() -> list[dict]:
    now_iso = datetime(2026, 11, 23, 4, 30, tzinfo=timezone.utc).isoformat()
    specs = [
        # 1. Earth, Quakes & Storms (ODD)
        (113358, "Where will 2026 rank among the hottest years on record?", "weather", [("1", 0.938), ("2", 0.052)]),
        (114134, "How many 7.0 or above earthquakes in 2026?", "weather", [("14–16", 0.745), ("17–19", 0.195)]),
        (114137, "How many large volcano eruptions (VEI >=4) in 2026?", "weather", [("1", 0.550), ("0", 0.400)]),
        (58435808, "How many tropical cyclones will make landfall in China during 2026?", "weather", [("8", 0.735), ("Greater than 8", 0.140)]),
        (1234182, "How many Tornadoes in the US in 2026?", "weather", [("1250+", 0.920), ("1200–1249", 0.067)]),
        (59129330, "What will the peak RONI be for the 2026–27 El Nino?", "weather", [("Over 2.5", 0.635), ("2.25–2.5", 0.330)]),
        # 2. Chess, Milestones & Curiosities (ODD)
        (221, "FIDE World Chess Championship 2026 Winner", "chess", [("Javokhir Sindarov", 0.765), ("Gukesh Dommaraju", 0.245)]),
        (59693602, "When will the Rock & Roll Hall of Fame expansion be completed?", "entertainment", [("Before Mar 1, 2027", 0.810), ("Before Mar 1, 2028", 0.900)]),
        (52755900, "Taylor Swift: Wedding Dress", "entertainment", [("Dior", 0.415), ("Armani Prive", 0.050)]),
        (109379, "Will the FDA approve any psychedelic substance for medical use this year?", "tech", [("Yes", 0.145), ("No", 0.855)]),
        (109264, "Time's Person of the Year for 2026", "entertainment", [("James Talarico", 0.255), ("Zohran Mamdani", 0.225)]),
        # 3. Water, Rain & Climate Shifts (ODD)
        (65521875, "How much will it rain in Napa in November 2026 through March 2027?", "weather", [("Above 10 inches", 0.875), ("Above 15 inches", 0.790)]),
        (63828305, "Melbourne's wettest month of 2026?", "weather", [("October", 0.905), ("December", 0.048)]),
        (61980420, "Lowest Mississippi level at Baton Rouge by November 30?", "weather", [("5.00 to 5.99 ft", 0.230), ("3.00 to 3.99 ft", 0.022)]),
        (108250, "What will be the largest source of global primary energy consumption in 2030?", "weather", [("Oil", 0.650), ("Coal", 0.135)]),
        (108248, "US meets its climate goals?", "weather", [("By 2030", 0.181), ("By 2025", 0.038)]),
        # 4. Grammys & Chart Leaders (ENTERTAINMENT)
        (52755801, "Grammy Winner: Album of the Year", "entertainment", [("Lux", 0.515), ("you seem pretty sad", 0.310)]),
        (56775571, "Grammy Winner: Best New Artist", "entertainment", [("Ella Langley", 0.745), ("SIENNA SPIRO", 0.200)]),
        (62368119, "Grammy Winner: Best Contemporary Country Album", "entertainment", [("Dandelion", 0.890), ("Middle of Nowhere", 0.065)]),
        (58492244, "Grammys 2027: Best Rap Album Winner", "entertainment", [("Octane - Don Toliver", 0.405), ("Dillagence II", 0.182)]),
        (114301, "Billboard #1 Artist 2026", "entertainment", [("Morgan Wallen", 0.690), ("Kendrick Lamar", 0.069)]),
        (109508, "Top Song on Spotify in 2026?", "entertainment", [("End of Beginning", 0.865), ("Babydoll", 0.095)]),
        (57576624, "#2 US Spotify Song 2026", "entertainment", [("Man I Need – Olivia Dean", 0.794), ("Earrings – Malcom Todd", 0.202)]),
        (52755612, "Top U.S. Selling Vinyl Album: 2026", "entertainment", [("ARIRANG", 0.420), ("you seem pretty sad", 0.320)]),
        (109520, "Top Album on Spotify U.S in 2026?", "entertainment", [("I’m The Problem", 0.725), ("DeBI TiRAR MaS FOToS", 0.105)]),
        # 5. TV, Stage & Gaming Drops (ENTERTAINMENT)
        (60481087, "Dancing with the Stars Season 35 Winner", "entertainment", [("Ezra Frech", 0.475), ("Amber Glenn", 0.275)]),
        (70160350, "Who will win The Voice Season 30?", "entertainment", [("Joey Henley", 0.555), ("Mia Knight", 0.125)]),
        (60473244, "GTA VI Online: Release date", "entertainment", [("Before 2028", 0.835), ("Before July 2027", 0.645)]),
        (63336233, "Rockstar releases PC version of GTA VI by...?", "entertainment", [("December 31, 2027", 0.845), ("June 30, 2027", 0.450)]),
        (71176017, "How many GTA VI units sold reported before 2027?", "esports", [("48M+", 0.560), ("30M to 33M", 0.212)]),
        (69096405, "PGL Major Singapore 2026: Winner", "esports", [("Vitality", 0.285), ("MOUZ", 0.175)]),
        (65536362, "Critics Choice Awards: Best Actor in a Comedy Series", "entertainment", [("Matthew Rhys", 0.820), ("Jeremy Allen White", 0.040)]),
        (65536308, "Critics Choice Awards: Best Foreign Language Film", "entertainment", [("La Bola Negra", 0.785), ("Other", 0.120)]),
        # 6. Soccer Cups & Relegation (SPORTS)
        (59156925, "LaLiga: Top Goalscorer 2026-27", "soccer", [("Kylian Mbappe", 0.520), ("Robert Lewandowski", 0.140)]),
        (59516509, "Premier League: Teams relegated (2026-27)", "soccer", [("Coventry City", 0.500), ("Leeds United", 0.350)]),
        (55674269, "Liga MX Apertura Champion", "soccer", [("Guadalajara", 0.325), ("Club America", 0.210)]),
        (128718, "MLS Cup Winner 2026", "soccer", [("Vancouver Whitecaps FC", 0.280), ("Inter Miami", 0.220)]),
        (70732925, "UEFA Europa League: 2027 Champion", "soccer", [("Benfica", 0.180), ("Roma", 0.140)]),
        (56775477, "2030 FIFA World Cup Champion", "soccer", [("Spain", 0.164), ("France", 0.145)]),
        # 7. NFL Division & Seed Races (SPORTS)
        (129171, "Pro Football: 2027 NFC Champion", "football", [("San Francisco 49ers", 0.345), ("Chicago Bears", 0.180)]),
        (129172, "Pro Football: 2027 AFC Champion", "football", [("Buffalo Bills", 0.275), ("Jacksonville Jaguars", 0.205)]),
        (2248395, "Pro Football: NFC East Champion", "football", [("New York Giants", 0.700), ("Dallas Cowboys", 0.165)]),
        (53677, "AFC North Division Winner", "football", [("Cincinnati", 0.875), ("Cleveland", 0.070)]),
        (53676, "AFC South Division Winner", "football", [("Jacksonville", 0.915), ("Houston", 0.075)]),
        (52755859, "Pro Football: NFC #1 Seed", "football", [("San Francisco", 0.685), ("Chicago", 0.165)]),
        (52755860, "Pro Football: AFC #1 Seed", "football", [("Buffalo", 0.415), ("Denver", 0.185)]),
        # 8. AI Math & Data Centers (TECH)
        (60607593, "How many more Millennium Prize Problems will AI solve in 2026?", "tech", [("1", 0.415), ("0", 0.385)]),
        (60626097, "Which Millennium Prize Problem will AI solve next?", "tech", [("Riemann Hypothesis", 0.638), ("No solution by Dec 31, 2027", 0.097)]),
        (60518652, "AI lab announces another Millennium Prize solution by...?", "tech", [("December 31, 2027", 0.934), ("December 31, 2026", 0.600)]),
        (2415248, "When will any company achieve AGI?", "tech", [("Before Jan 1, 2031", 0.755), ("Before Jan 1, 2029", 0.695)]),
        (20571305, "AI data center in space by...?", "tech", [("December 31, 2027", 0.190), ("December 31, 2026", 0.009)]),
        (63267956, "Louisiana enacts data center moratorium by...?", "tech", [("December 31, 2028", 0.340), ("June 30, 2027", 0.125)]),
        (63263361, "Texas enacts data center moratorium by...?", "tech", [("December 31, 2028", 0.335), ("December 31, 2027", 0.195)]),
        (63267959, "Indiana enacts data center moratorium by...?", "tech", [("December 31, 2028", 0.305), ("December 31, 2027", 0.195)]),
        (70732962, "Will any state enact a data center moratorium by December 31?", "tech", [("Yes", 0.245), ("No", 0.755)]),
        (109305, "What kind of device will Jony Ive and OpenAI announce?", "tech", [("Necklace", 0.090), ("Glasses", 0.065)]),
    ]
    return [
        {
            "id": mid,
            "name": name,
            "title": name,
            "status": "open",
            "source": "polymarket",
            "category": cat,
            "llm_sport_category": cat,
            "volume": 50_000.0,
            "resolution_date": "2027-02-01T00:00:00+00:00",
            "newest_outcome_updated_at": now_iso,
            "outcomes": [
                {"id": mid * 10 + i + 1, "name": oname, "probability": prob, "last_updated": now_iso}
                for i, (oname, prob) in enumerate(outs)
            ],
        }
        for mid, name, cat, outs in specs
    ]


@pytest.mark.asyncio
async def test_batch8_eight_preview_groupings_build_and_hit_mix(caplog: pytest.LogCaptureFixture) -> None:
    clear_fun_markets_cache()
    caplog.set_level(logging.WARNING)
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    assert set(BATCH8_SLUGS) <= set(paths_by_slug)

    db = {
        "events": [],
        "markets": _sample_batch8_markets(),
        "teams": [],
        "paired_sets": {},
        "market_histories": {},
    }

    expected_topics = {
        "machinery-earth-quakes-and-storms-2026": TOPIC_ODD,
        "machinery-chess-milestones-and-curiosities": TOPIC_ODD,
        "machinery-climate-water-and-energy": TOPIC_ODD,
        "machinery-music-and-grammys-2026": TOPIC_ENTERTAINMENT,
        "machinery-tv-and-gaming-2026": TOPIC_ENTERTAINMENT,
        "machinery-soccer-cups-and-relegation": TOPIC_SPORTS,
        "machinery-nfl-conference-and-division-races": TOPIC_SPORTS,
        "machinery-ai-math-and-data-centers": TOPIC_TECH_BUSINESS,
    }

    seen_headlines: set[str] = set()
    for slug in BATCH8_SLUGS:
        defn = load_machinery_definition(paths_by_slug[slug])
        assert defn.get("stage") == "preview", slug
        prod = build_container_machinery_producer(defn)
        assert prod.stage == "preview", slug
        res = await produce_container_machinery(db, defn, now=NOW)
        assert hasattr(res, "machinery_card"), (slug, res)
        mc = res.machinery_card
        assert mc["stage"] == "preview"
        assert mc["title"] and "{answer}" not in mc["title"] and "{rank}" not in mc["title"], (slug, mc["title"])
        assert "by by " not in mc["title"], (slug, mc["title"])
        assert mc["title"] not in seen_headlines, f"Duplicate headline: {mc['title']}"
        seen_headlines.add(mc["title"])
        assert len(mc["rows"]) == 3, (slug, mc["rows"])

        fi = compose_roundup_feed_item(prod, res)
        cp = compose_roundup_container(prod, res)
        c_p, p_p = _compute_member_number_parity(fi, cp)
        assert c_p["passes"] is True and p_p["passes"] is True, (slug, c_p, p_p)
        assert classify_discover_opening_topic(fi) == expected_topics[slug], slug

    assert not any("dropped row pictures" in rec.message for rec in caplog.records)


def test_batch8_market_ids_disjoint_from_earlier_batches() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "data" / "groupings"
    earlier_ids: set[int] = set()
    for fname in (
        "batch3_curated_sets.json",
        "batch4_curated_sets.json",
        "batch5_curated_sets.json",
        "batch6_curated_sets.json",
    ):
        doc = json.loads((root / fname).read_text(encoding="utf-8"))
        for s in (doc.get("sets") or {}).values():
            for e in s.get("entries") or ():
                earlier_ids.add(int(e["id"]))

    b8 = json.loads((root / "batch8_curated_sets.json").read_text(encoding="utf-8"))
    b8_ids = [
        int(e["id"])
        for s in (b8.get("sets") or {}).values()
        for e in s.get("entries") or ()
    ]
    assert len(b8_ids) == len(set(b8_ids)), "Duplicate market id inside batch8_curated_sets.json"
    overlap = set(b8_ids) & earlier_ids
    assert not overlap, f"Batch 8 overlaps earlier curated sets: {sorted(overlap)}"
