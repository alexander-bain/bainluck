"""Batch 4 preview sets (#12288, Fable Item 4): four curated non-politics preview sets.

1. `machinery-game-awards-2026` — The Game Awards 2026 (6 rows, entertainment)
2. `machinery-big-championships-2027` — 2026–27 Championship Races (6 rows, sports)
3. `machinery-unsolved-big-problems` — Unsolved Big Problems (6 rows, science/tech)
4. `machinery-ai-and-big-tech-race` — The AI & Big Tech Race (8 rows, tech/business)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.utils.container_machinery import (
    _compute_member_number_parity,
    build_container_machinery_producer,
    discover_machinery_candidate_paths,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.discover_fun_tags import fun_market_ids_for_sub_tag
from app.utils.discover_image_policy import _REGISTER_PATH, sanitize_discover_feed_item
from app.utils.roundup_containers import (
    compose_roundup_container,
    compose_roundup_feed_item,
)

NOW = datetime(2026, 11, 21, 18, 0, tzinfo=timezone.utc)

BATCH4_SLUGS = (
    "machinery-game-awards-2026",
    "machinery-big-championships-2027",
    "machinery-unsolved-big-problems",
    "machinery-ai-and-big-tech-race",
)


def _sample_batch4_markets() -> list[dict]:
    rows = [
        # Set 1: The Game Awards 2026 (6 rows)
        {"id": 58399979, "name": "The Game Awards: Best Game Direction", "status": "open", "source": "polymarket", "category": "entertainment", "outcomes": [{"id": 101, "name": "Grand Theft Auto VI", "probability": 0.84}, {"id": 102, "name": "Control Resonant", "probability": 0.10}]},
        {"id": 58399941, "name": "The Game Awards: Best Narrative", "status": "open", "source": "polymarket", "category": "entertainment", "outcomes": [{"id": 103, "name": "Grand Theft Auto VI", "probability": 0.79}, {"id": 104, "name": "The Blood of Dawnwalker", "probability": 0.08}]},
        {"id": 58399980, "name": "The Game Awards: Best Audio Design", "status": "open", "source": "polymarket", "category": "entertainment", "outcomes": [{"id": 105, "name": "Grand Theft Auto VI", "probability": 0.72}]},
        {"id": 58399978, "name": "The Game Awards: Best Multiplayer", "status": "open", "source": "polymarket", "category": "entertainment", "outcomes": [{"id": 106, "name": "Big Walk", "probability": 0.68}]},
        {"id": 58399939, "name": "The Game Awards: Best Mobile Game", "status": "open", "source": "polymarket", "category": "entertainment", "outcomes": [{"id": 107, "name": "Arknights: Endfield", "probability": 0.59}]},
        {"id": 58399977, "name": "The Game Awards: Best Independent Game", "status": "open", "source": "polymarket", "category": "entertainment", "outcomes": [{"id": 108, "name": "Big Walk", "probability": 0.48}]},
        # Set 2: 2026-27 Championship Races (6 rows)
        {"id": 57792807, "name": "NCAA Football: 2026 Heisman Award Winner", "status": "open", "source": "polymarket", "category": "football", "outcomes": [{"id": 201, "name": "Jeremiah Smith", "probability": 0.63}]},
        {"id": 66031970, "name": "NBA: 2026-27 MVP", "status": "open", "source": "polymarket", "category": "basketball", "outcomes": [{"id": 202, "name": "Victor Wembanyama", "probability": 0.39}]},
        {"id": 70732924, "name": "UEFA Champions League: 2027 Champion", "status": "open", "source": "polymarket", "category": "soccer", "outcomes": [{"id": 203, "name": "Barcelona", "probability": 0.22}]},
        {"id": 20569230, "name": "NBA: 2027 Champion", "status": "open", "source": "polymarket", "category": "basketball", "outcomes": [{"id": 204, "name": "San Antonio Spurs", "probability": 0.21}]},
        {"id": 86832, "name": "NFL Super Bowl Winner", "status": "open", "source": "odds_api", "category": "football", "outcomes": [{"id": 205, "name": "San Francisco 49ers", "probability": 0.14}]},
        {"id": 52755659, "name": "2026-27 Stanley Cup Final Winner", "status": "open", "source": "kalshi", "category": "hockey", "outcomes": [{"id": 206, "name": "Carolina Hurricanes", "probability": 0.14}]},
        # Set 3: Unsolved Big Problems (6 rows)
        {"id": 53049401, "name": "When will the Riemann hypothesis win the Millennium Prize?", "status": "open", "source": "kalshi", "category": "tech", "outcomes": [{"id": 301, "name": "Before 2035", "probability": 0.91}]},
        {"id": 112792, "name": "When will the next Millennium Prize be awarded?", "status": "open", "source": "kalshi", "category": "tech", "outcomes": [{"id": 302, "name": "Before 2035", "probability": 0.86}]},
        {"id": 60626095, "name": "Which math problems will AI solve in 2026?", "status": "open", "source": "polymarket", "category": "tech", "outcomes": [{"id": 303, "name": "Riemann Hypothesis", "probability": 0.76}]},
        {"id": 108232, "name": "When will nuclear fusion be achieved?", "status": "open", "source": "kalshi", "category": "geopolitics", "outcomes": [{"id": 304, "name": "Before 2040", "probability": 0.75}]},
        {"id": 112835, "name": "When will OpenAI achieve AGI?", "status": "open", "source": "kalshi", "category": "tech", "outcomes": [{"id": 305, "name": "Before 2030", "probability": 0.64}]},
        {"id": 112826, "name": "When will the first useful quantum computer be developed?", "status": "open", "source": "kalshi", "category": "tech", "outcomes": [{"id": 306, "name": "Before 2040", "probability": 0.62}]},
        # Set 4: The AI & Big Tech Race (8 rows)
        {"id": 113318, "name": "Largest Company end of December 2026?", "status": "open", "source": "polymarket", "category": "economics", "outcomes": [{"id": 401, "name": "Apple", "probability": 0.94}]},
        {"id": 68806125, "name": "2nd Largest Company end of November 2026?", "status": "open", "source": "polymarket", "category": "tech", "outcomes": [{"id": 402, "name": "Microsoft", "probability": 0.80}]},
        {"id": 23449601, "name": "Anthropic vs OpenAI - higher valuation on December 31?", "status": "open", "source": "polymarket", "category": "economics", "outcomes": [{"id": 403, "name": "Anthropic", "probability": 0.67}]},
        {"id": 24586956, "name": "Lead Bank in OpenAI's IPO?", "status": "open", "source": "polymarket", "category": "economics", "outcomes": [{"id": 404, "name": "Goldman Sachs", "probability": 0.64}]},
        {"id": 68806126, "name": "3rd Largest Company end of November 2026?", "status": "open", "source": "polymarket", "category": "tech", "outcomes": [{"id": 405, "name": "Alphabet", "probability": 0.57}]},
        {"id": 66692564, "name": "Which company has the best Image-to-Video AI end of November?", "status": "open", "source": "polymarket", "category": "tech", "outcomes": [{"id": 406, "name": "Google", "probability": 0.52}]},
        {"id": 63617294, "name": "Which company has the best Text-to-Video AI end of December?", "status": "open", "source": "polymarket", "category": "tech", "outcomes": [{"id": 407, "name": "Google", "probability": 0.51}]},
        {"id": 113184, "name": "OpenAI IPO?", "status": "open", "source": "polymarket", "category": "tech", "outcomes": [{"id": 408, "name": "June 30, 2027", "probability": 0.39}]},
    ]
    for r in rows:
        r.setdefault("volume", 50000)
    return rows


def test_batch4_definitions_are_preview_non_politics_with_verified_pd_or_cc0_art() -> None:
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    register_doc = json.loads(_REGISTER_PATH.read_text(encoding="utf-8"))
    verified_urls = {
        str(entry.get("url") or "").strip()
        for entry in (register_doc.get("entries") or [])
        if isinstance(entry, dict)
    }
    expected_counts = {
        "machinery-game-awards-2026": 6,
        "machinery-big-championships-2027": 6,
        "machinery-unsolved-big-problems": 6,
        "machinery-ai-and-big-tech-race": 8,
    }
    batch3_ids: set[int] = set()
    for tag in (
        "batch3-2026-summed-up",
        "batch3-cast-delayed-cancelled",
        "batch3-stage-and-cover",
        "batch3-elon-musk-side-quests",
    ):
        batch3_ids.update(fun_market_ids_for_sub_tag(tag))

    for slug in BATCH4_SLUGS:
        assert slug in paths_by_slug
        defn = load_machinery_definition(paths_by_slug[slug])
        assert "market_id" not in json.dumps(defn)
        assert defn["stage"] == "preview"
        assert defn["category"] != "politics"
        rule = defn["rule"]
        assert rule.get("suppress_card_photo") is True
        url = str(rule.get("card_image_url") or "").strip()
        assert url.startswith("https://thumb.wikimedia.org/")
        assert url in verified_urls
        assert str(rule.get("card_image_alt") or "").strip()
        assert str(rule.get("card_image_credit") or "").strip()
        assert str(rule.get("card_image_author") or "").strip()
        lic = str(rule.get("card_image_license") or "").lower()
        assert "cc0" in lic or "public domain" in lic
        assert str(rule.get("card_image_source_page") or "").startswith(
            "https://commons.wikimedia.org/wiki/File:"
        )
        sec = rule["sections"][0]
        sub_tag = sec["atom_query"]["fun_sub_tag"]
        ids = fun_market_ids_for_sub_tag(sub_tag)
        assert len(ids) == expected_counts[slug]
        assert set(ids).isdisjoint(batch3_ids), f"{slug} overlaps with Batch 3"


@pytest.mark.asyncio
async def test_batch4_four_preview_sets_build_with_plain_speech_headlines_and_parity() -> None:
    db = {"events": [], "markets": _sample_batch4_markets(), "paired_sets": {}, "market_histories": {}}
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}

    expected_titles = {
        "machinery-game-awards-2026": (
            "Grand Theft Auto VI for Best Game Direction is at 84%, "
            "with Grand Theft Auto VI for Best Narrative at 79%"
        ),
        "machinery-big-championships-2027": (
            "Jeremiah Smith for the Heisman Trophy is at 63%, "
            "with Victor Wembanyama for NBA MVP at 39%"
        ),
        "machinery-unsolved-big-problems": (
            "The Riemann hypothesis winning a Millennium Prize before 2035 is at 91%, "
            "with the next Millennium Prize awarded before 2035 at 86%"
        ),
        "machinery-ai-and-big-tech-race": (
            "Apple as the largest company at the end of 2026 is at 94%, "
            "with Microsoft in second place at 80%"
        ),
    }

    for slug, expected_title in expected_titles.items():
        defn = load_machinery_definition(paths_by_slug[slug])
        prod = build_container_machinery_producer(defn)
        res = await produce_container_machinery(db, defn, now=NOW)
        assert res.machinery_card["stage"] == "preview"
        assert res.machinery_card["image_url"] == defn["rule"]["card_image_url"]
        assert res.title == expected_title
        assert ": " not in res.title
        assert "board" not in res.title.lower()
        fi = sanitize_discover_feed_item(compose_roundup_feed_item(prod, res))
        cp = compose_roundup_container(prod, res)
        c_p, p_p = _compute_member_number_parity(fi, cp)
        assert c_p["passes"] is True and p_p["passes"] is True
        assert fi["data"]["image_url"] == defn["rule"]["card_image_url"]
