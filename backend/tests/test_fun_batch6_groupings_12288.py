"""Tests for #12288 Batch 6 preview fun groupings (Fable 6:19 AM PT Sun Nov 22).

Covers:
1. machinery-google-year-in-search-2026 (ODD) — #1 rows on card face; Top 5 rows on set page only.
2. machinery-pop-culture-oddities (ODD) — all 6 culture rows on set page (113358 excluded); Elon Musk (108254) never leads headline/card face.
3. machinery-2026-box-office-showdown (ENTERTAINMENT).
4. machinery-golden-globes-2027 (ENTERTAINMENT, replacing Grammys).
"""

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
from app.utils.discover_image_policy import _REGISTER_PATH
from app.utils.discover_opening_mix import (
    TOPIC_ENTERTAINMENT,
    TOPIC_ODD,
    classify_discover_opening_topic,
)
from app.utils.roundup_containers import compose_roundup_container, compose_roundup_feed_item

BATCH6_SLUGS: tuple[str, ...] = (
    "machinery-google-year-in-search-2026",
    "machinery-pop-culture-oddities",
    "machinery-2026-box-office-showdown",
    "machinery-golden-globes-2027",
)
NOW = datetime(2026, 11, 22, 14, 30, tzinfo=timezone.utc)

GOOGLE_TOP1_IDS = frozenset({57792681, 57792626, 70733266, 57792616})
GOOGLE_TOP5_IDS = frozenset({60634621, 60634622, 60634620, 60634619})


def _sample_batch6_markets(*, elon_prob: float = 0.35) -> list[dict]:
    now_iso = datetime(2026, 11, 22, 14, 0, tzinfo=timezone.utc).isoformat()
    specs = [
        # 1. Google's 2026 Year in Search (#1 rows)
        (70733266, "#1 Searched Actor on Google 2026?", "tech", [("Inde Navarrette", 0.471), ("Robert Pattinson", 0.146)]),
        (57792616, "#1 Searched Athlete on Google 2026?", "tech", [("Erling Braut Haaland", 0.444), ("Alysa Liu", 0.092)]),
        (57792681, "#1 Searched Movie on Google 2026?", "entertainment", [("Obsession", 0.378), ("The Odyssey", 0.321)]),
        (57792626, "#1 Searched TV Show on Google 2026?", "entertainment", [("Euphoria", 0.333), ("Stranger Things", 0.252)]),
        # Google Top 5 rows (set page only, intentionally higher probs than #1 rows)
        (60634621, "Top 5 Most Searched Movies on Google 2026", "tech", [("The Odyssey", 0.935), ("Obsession", 0.885)]),
        (60634619, "Top 5 Most Searched Athletes on Google 2026", "tech", [("Erling Braut Haaland", 0.895), ("Alysa Liu", 0.715)]),
        (60634622, "Top 5 Most Searched Actors on Google 2026", "tech", [("Inde Navarrette", 0.850), ("Jaafar Jackson", 0.570)]),
        (60634620, "Top 5 Most Searched TV Shows on Google 2026", "tech", [("Euphoria", 0.645), ("Heated Rivalry", 0.445)]),
        # 2. Pop Culture Oddities (7 rows)
        (113358, "Where will 2026 rank among the hottest years on record?", "tech", [("1", 0.951), ("2", 0.047)]),
        (67804457, '"All I Want for Christmas Is You" · Billboard Hot 100 rank (Dec 19, 2026)', "entertainment", [("Rank 1 to 2", 0.796), ("Rank 3 to 4", 0.150)]),
        (108306, "What genre will Beyonce’s next album be?", "entertainment", [("Rock", 0.640), ("R&B/Hip-Hop", 0.460)]),
        (109309, "Will Taylor Swift (Taylor's Version) be announced this year?", "entertainment", [("Yes", 0.425), ("No", 0.575)]),
        (108254, "Time's Person of the Decade", "entertainment", [("Elon Musk", elon_prob), ("Volodymyr Zelenskyy", 0.30)]),
        (67804475, "Which New York City restaurants earn a Michelin star in 2026?", "entertainment", [("Kabawa", 0.320), ("HWARO", 0.270)]),
        (58903285, "Turner Prize 2026 Winner", "entertainment", [("Simeon Barclay", 0.287), ("Tanoa Sasraku", 0.261)]),
        # 3. 2026 Box Office Showdown (6 rows)
        (114149, "Will Dune 3 or Avengers: Doomsday gross more on their opening weekend?", "entertainment", [("Avengers: Doomsday", 0.980), ("Dune 3", 0.020)]),
        (113355, "Highest grossing movie in 2026?", "entertainment", [("Spider-Man: Brand New Day", 0.905), ("Avengers: Doomsday", 0.100)]),
        (113356, "Which movie has biggest opening weekend in 2026?", "entertainment", [("Avengers: Doomsday", 0.895), ("Spider-Man: Brand New Day", 0.110)]),
        (56867563, "Which movie has 2nd biggest opening weekend in 2026?", "entertainment", [("Spider-Man: Brand New Day", 0.882), ("Avengers: Doomsday", 0.116)]),
        (68365230, '"Avengers: Doomsday" Opening Weekend Box Office', "entertainment", [("400m+", 0.719), ("360m-400m", 0.202)]),
        (68365233, '"Dune: Part Three" Opening Weekend Box Office', "entertainment", [("110m-130m", 0.442), ("130m+", 0.224)]),
        # 4. The 2027 Golden Globes (10 rows)
        (70160313, "Golden Globe Winner: Best Actress in a Motion Picture – Musical or Comedy", "entertainment", [("Julianne Moore", 0.770), ("Inde Navarrette", 0.070)]),
        (70160296, "Golden Globe Winner: Best Actress in a Limited Series", "entertainment", [("Florence Pugh", 0.720), ("Sally Field", 0.065)]),
        (70160294, "Golden Globe Winner: Best Supporting Actress on TV", "entertainment", [("Kate O’Flynn", 0.705), ("Linda Cardellini", 0.120)]),
        (70160314, "Golden Globe Winner: Best Actor in a Motion Picture – Musical or Comedy", "entertainment", [("John Malkovich", 0.658), ("Anthony Ippolito", 0.147)]),
        (70160312, "Golden Globe Winner: Best Motion Picture - Musical or Comedy", "entertainment", [("Wild Horse Nine", 0.516), ("The Debut", 0.169)]),
        (70160308, "Golden Globe Winner: Best Motion Picture - Drama", "entertainment", [("The Odyssey", 0.507), ("La Bola Negra", 0.338)]),
        (70160311, "Golden Globe Winner: Best Actor in a Motion Picture – Drama", "entertainment", [("Andrew Scott", 0.483), ("Matt Damon", 0.177)]),
        (70160298, "Golden Globe Winner: Best Television Series - Limited Series", "entertainment", [("DTF St. Louis", 0.449), ("East of Eden", 0.404)]),
        (70160295, "Golden Globe Winner: Best Supporting Actor on TV", "entertainment", [("David Harbour", 0.449), ("Stephen Root", 0.267)]),
        (70239565, "Golden Globes 2027: Best Television Series – Drama Winner", "entertainment", [("The Pitt", 0.331), ("Slow Horses", 0.294)]),
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


def test_batch6_candidates_are_preview_with_verified_art() -> None:
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    backend_art_text = _REGISTER_PATH.read_text(encoding="utf-8")
    verified_urls = {
        str(e.get("url") or "").strip()
        for e in (json.loads(backend_art_text).get("entries") or ())
        if isinstance(e, dict)
    }

    for slug in BATCH6_SLUGS:
        assert slug in paths_by_slug, slug
        defn = load_machinery_definition(paths_by_slug[slug])
        assert defn["stage"] == "preview"
        rule = defn["rule"]
        assert rule.get("suppress_card_photo") is True
        assert rule.get("hide_row_art") is True
        assert str(rule.get("card_image_url") or "") in verified_urls
        assert str(rule.get("card_image_license") or "") in {"CC0 1.0 Public Domain", "Public domain"}
        assert "trading" not in json.dumps(defn).lower()


@pytest.mark.asyncio
async def test_batch6_builds_clean_headlines_google_card_split_and_no_elon_lead(
    caplog: pytest.LogCaptureFixture,
) -> None:
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    markets = _sample_batch6_markets(elon_prob=0.35)

    with caplog.at_level(logging.WARNING, logger="app.utils.container_machinery"):
        for slug in BATCH6_SLUGS:
            defn = load_machinery_definition(paths_by_slug[slug])
            producer = build_container_machinery_producer(defn)
            res = await produce_container_machinery({"markets": markets, "teams": []}, defn, now=NOW)
            assert hasattr(res, "machinery_card"), (slug, res)
            item = compose_roundup_feed_item(producer, res)
            assert item is not None
            container = compose_roundup_container(producer, res)
            card_parity, page_parity = _compute_member_number_parity(item, container)
            assert card_parity["passes"], (slug, card_parity)
            assert page_parity["passes"], (slug, page_parity)
            mc = res.machinery_card
            title = mc["title"]
            assert "? at " not in title, title
            assert "trading" not in title.lower(), title

            expected_topic = (
                TOPIC_ODD
                if slug in {"machinery-google-year-in-search-2026", "machinery-pop-culture-oddities"}
                else TOPIC_ENTERTAINMENT
            )
            assert classify_discover_opening_topic(item) == expected_topic

            if slug == "machinery-google-year-in-search-2026":
                card_mids = {r["market_id"] for r in mc["rows"]}
                assert card_mids <= GOOGLE_TOP1_IDS, card_mids
                assert not (card_mids & GOOGLE_TOP5_IDS), card_mids
                assert "top 5" not in title.lower(), title
                assert len(res.sections) == 2
                sec1_mids = {it["market_id"] for it in res.sections[0]["visual_block"]["items"]}
                sec2_mids = {it["market_id"] for it in res.sections[1]["visual_block"]["items"]}
                assert sec1_mids == GOOGLE_TOP1_IDS
                assert sec2_mids == GOOGLE_TOP5_IDS

            if slug == "machinery-pop-culture-oddities":
                assert "elon musk" not in title.lower(), title
                assert "Rank 1 to 2" not in title, title
                assert "hottest year" not in title.lower(), title
                assert "climate records" not in str(mc.get("subtitle") or "").lower(), mc.get("subtitle")
                assert "landing in the top 2 of the Dec 19 Hot 100" in title, title
                assert "Beyoncé's next album being rock" in title, title
                assert mc["rows"][0]["name"] == "\"All I Want for Christmas Is You\" in the Hot 100's top 2 on Dec 19"
                assert res.rows[0]["label"] == "\"All I Want for Christmas Is You\" in the Hot 100's top 2 on Dec 19"
                card_mids = {r["market_id"] for r in mc["rows"]}
                assert 108254 not in card_mids
                assert 113358 not in card_mids
                all_page_mids = {it["market_id"] for it in res.sections[0]["visual_block"]["items"]}
                assert 108254 in all_page_mids
                assert 113358 not in all_page_mids
                assert len(all_page_mids) == 6

            if slug == "machinery-2026-box-office-showdown":
                assert mc["rows"][0]["name"] == "Bigger opening weekend than Dune 3: Avengers: Doomsday"
                assert res.rows[0]["label"] == "Bigger opening weekend than Dune 3: Avengers: Doomsday"

    assert not any("dropped row pictures" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_pop_culture_oddities_never_leads_with_elon_even_at_99_percent() -> None:
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    defn = load_machinery_definition(paths_by_slug["machinery-pop-culture-oddities"])
    markets = _sample_batch6_markets(elon_prob=0.99)
    res = await produce_container_machinery({"markets": markets, "teams": []}, defn, now=NOW)
    assert hasattr(res, "machinery_card")
    assert "elon musk" not in res.machinery_card["title"].lower()
    assert all(r["market_id"] != 108254 for r in res.machinery_card["rows"])
    assert any(it["market_id"] == 108254 for it in res.sections[0]["visual_block"]["items"])


@pytest.mark.asyncio
async def test_pop_culture_oddities_rank_slot_formats_top_and_spots() -> None:
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    defn = load_machinery_definition(paths_by_slug["machinery-pop-culture-oddities"])
    markets = _sample_batch6_markets(elon_prob=0.35)
    for m in markets:
        if m["id"] == 67804457:
            m["outcomes"] = [
                {"id": 678044572, "name": "Rank 3 to 4", "probability": 0.85, "last_updated": m["newest_outcome_updated_at"]},
                {"id": 678044571, "name": "Rank 1 to 2", "probability": 0.10, "last_updated": m["newest_outcome_updated_at"]},
            ]
    res = await produce_container_machinery({"markets": markets, "teams": []}, defn, now=NOW)
    assert hasattr(res, "machinery_card")
    row0_label = res.machinery_card["rows"][0]["name"]
    assert row0_label == "\"All I Want for Christmas Is You\" in the Hot 100's spots 3 to 4 on Dec 19"
    assert "top 2" not in row0_label
    assert "landing in spots 3 to 4 of the Dec 19 Hot 100" in res.machinery_card["title"]
