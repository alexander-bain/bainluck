"""Batch 3 preview sets (#12288, Fable 6:17 AM PT note): four curated preview sets.

1. `machinery-2026-summed-up` — How 2026 gets summed up (9 rows)
2. `machinery-cast-delayed-cancelled` — Who gets cast, delayed, or cancelled (9 rows)
3. `machinery-stage-and-cover` — Who gets the stage and the cover (6 rows; Michelin dropped)
4. `machinery-elon-musk-side-quests` — Elon Musk's wildest side quests (6 rows; second trillionaire dropped)
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
from app.utils.discover_fun_tags import fun_market_ids_for_sub_tag
from app.utils.discover_image_policy import sanitize_discover_feed_item
from app.utils.roundup_containers import (
    compose_roundup_container,
    compose_roundup_feed_item,
)

NOW = datetime(2026, 11, 21, 14, 45, tzinfo=timezone.utc)

BATCH3_SLUGS = (
    "machinery-2026-summed-up",
    "machinery-cast-delayed-cancelled",
    "machinery-stage-and-cover",
    "machinery-elon-musk-side-quests",
)


def _sample_batch3_markets() -> list[dict]:
    rows = [
        # Set 1: How 2026 gets summed up (9 rows)
        {"id": 27467306, "name": "TIME Person of the Year 2026", "status": "open", "source": "polymarket", "category": "entertainment", "outcomes": [{"id": 101, "name": "James Talarico", "probability": 0.25}, {"id": 102, "name": "Zohran Mamdani", "probability": 0.22}]},
        {"id": 8431009, "name": "Merriam-Webster Word of the Year 2026?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 103, "name": "larping", "probability": 0.20}, {"id": 104, "name": "Agentic", "probability": 0.11}]},
        {"id": 109517, "name": "Top artist on Spotify in 2026?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 105, "name": "Bad Bunny", "probability": 0.96}, {"id": 106, "name": "Drake", "probability": 0.03}]},
        {"id": 70733200, "name": "Top Spotify Song 2026", "status": "open", "source": "polymarket", "category": "entertainment", "outcomes": [{"id": 107, "name": "End of Beginning – Djo", "probability": 0.85}]},
        {"id": 71373602, "name": "Top US Spotify Album 2026", "status": "open", "source": "polymarket", "category": "entertainment", "outcomes": [{"id": 108, "name": "I'm The Problem - Morgan Wallen", "probability": 0.71}]},
        {"id": 109527, "name": "When will Spotify release 2026 Wrapped?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 109, "name": "Before Dec 5, 2026", "probability": 0.88}]},
        {"id": 109614, "name": "The Game Awards: Game of the Year", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 110, "name": "Grand Theft Auto VI", "probability": 0.92}]},
        {"id": 109537, "name": "#2 Most Searched Person on Google in 2026?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 111, "name": "Bad Bunny", "probability": 0.07}]},
        {"id": 52755613, "name": "Top U.S. Streamed Song (On-Demand Audio): 2026", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 112, "name": "Choosin' Texas", "probability": 0.82}]},
        # Set 2: Who gets cast, delayed, or cancelled (9 rows)
        {"id": 109214, "name": "Avengers: Doomsday: Cast", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 201, "name": "Ryan Reynolds as Deadpool?", "probability": 0.97}, {"id": 202, "name": "Tobey Maguire as Spider-Man?", "probability": 0.97}]},
        {"id": 56867561, "name": "Will Avengers: Secret Wars be delayed?", "status": "open", "source": "polymarket", "category": "entertainment", "outcomes": [{"id": 203, "name": "Yes", "probability": 0.50}]},
        {"id": 108506, "name": "Marvel: Actor cast as Miles Morales", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 204, "name": "Caleb McLaughlin", "probability": 0.19}]},
        {"id": 70150106, "name": "The Brave and the Bold · Cast", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 205, "name": "Brandon Sklenar", "probability": 0.07}]},
        {"id": 70150102, "name": "Disney's Princess Tiana: Cast", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 206, "name": "Coco Jones", "probability": 0.13}]},
        {"id": 70150103, "name": "Emily Henry's Happy Place: Cast", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 207, "name": "Meghann Fahy", "probability": 0.07}]},
        {"id": 109250, "name": "TV shows cancelled this year", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 208, "name": "The Daily Show", "probability": 0.07}]},
        {"id": 108275, "name": "Will there be an announcement that The Simpsons is ending?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 209, "name": "Yes", "probability": 0.67}]},
        {"id": 59172754, "name": "Dune vs Avengers: Highest Rotten Tomatoes Score", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 210, "name": "Dune: Part Three", "probability": 0.84}]},
        # Set 3: Who gets the stage and the cover (6 rows; Michelin excluded)
        {"id": 62368061, "name": "Who will host Saturday Night Live Season 52?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 300, "name": "John Mulaney", "probability": 1.0}, {"id": 301, "name": "Timothée Chalamet", "probability": 0.87}]},
        {"id": 109296, "name": "Call Her Daddy: Guests this year", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 302, "name": "Miley Cyrus", "probability": 0.56}]},
        {"id": 109287, "name": "The Joe Rogan Experience: Guests in 2026", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 303, "name": "Tulsi Gabbard", "probability": 0.24}]},
        {"id": 56775621, "name": "Vogue (US) 2026: Cover Models", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 304, "name": "Jenna Ortega", "probability": 1.0}, {"id": 305, "name": "Taylor Swift", "probability": 0.60}]},
        {"id": 108505, "name": "Who will headline Coachella 2027?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 306, "name": "Tame Impala", "probability": 0.99}, {"id": 307, "name": "SZA", "probability": 0.98}]},
        {"id": 108504, "name": "Who will headline Rolling Loud Miami 2026?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 308, "name": "Future", "probability": 0.05}]},
        # Dropped Michelin rows (must NOT appear in stage-and-cover):
        {"id": 67804475, "name": "Which NYC restaurants earn a Michelin star in 2026?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 391, "name": "Kabawa", "probability": 0.33}]},
        {"id": 67804474, "name": "Which NYC restaurants earn three Michelin stars in 2026?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 392, "name": "Atomix", "probability": 0.20}]},
        {"id": 67804472, "name": "Which NYC restaurants lose Michelin stars in 2026?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 393, "name": "Masa", "probability": 0.13}]},
        # Set 4: Elon Musk's wildest side quests (6 rows; second trillionaire dropped)
        {"id": 109633, "name": "Next Superman film: Will Elon Musk be cast?", "status": "open", "source": "kalshi", "category": "entertainment", "outcomes": [{"id": 401, "name": "Yes", "probability": 0.05}]},
        {"id": 109412, "name": "Will Elon purchase Ryanair?", "status": "open", "source": "kalshi", "category": "politics", "outcomes": [{"id": 402, "name": "Yes", "probability": 0.05}]},
        {"id": 109316, "name": "Will Elon Musk buy a major sports team before 2027?", "status": "open", "source": "kalshi", "category": "culture", "outcomes": [{"id": 403, "name": "Yes", "probability": 0.01}]},
        {"id": 108218, "name": "Will Elon Musk visit Mars in his lifetime?", "status": "open", "source": "kalshi", "category": "culture", "outcomes": [{"id": 404, "name": "Yes", "probability": 0.12}]},
        {"id": 109490, "name": "Elon Musk out as Tesla CEO before 2027?", "status": "open", "source": "kalshi", "category": "economics", "outcomes": [{"id": 405, "name": "Yes", "probability": 0.04}]},
        {"id": 109489, "name": "Tesla Optimus released this year?", "status": "open", "source": "kalshi", "category": "tech", "outcomes": [{"id": 406, "name": "Yes", "probability": 0.02}]},
        # Dropped second-trillionaire row (must NOT appear in Musk side quests):
        {"id": 52755535, "name": "Who will be the world's second trillionaire?", "status": "open", "source": "kalshi", "category": "economics", "outcomes": [{"id": 499, "name": "Jeff Bezos", "probability": 0.25}]},
    ]
    for r in rows:
        r.setdefault("volume", 50000)
    return rows


def test_batch3_definitions_are_public_with_verified_pd_or_cc0_art_and_no_venue_names() -> None:
    import json

    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    expected_counts = {
        "machinery-2026-summed-up": 9,
        "machinery-cast-delayed-cancelled": 9,
        "machinery-stage-and-cover": 6,
        "machinery-elon-musk-side-quests": 6,
    }
    for slug in BATCH3_SLUGS:
        assert slug in paths_by_slug
        defn = load_machinery_definition(paths_by_slug[slug])
        assert "market_id" not in json.dumps(defn)
        assert defn["stage"] == "public"
        rule = defn["rule"]
        assert rule.get("suppress_card_photo") is True
        assert str(rule.get("card_image_url") or "").startswith("https://thumb.wikimedia.org/")
        assert str(rule.get("card_image_source_page") or "").startswith("https://commons.wikimedia.org/wiki/File:")
        lic = str(rule.get("card_image_license") or "").lower()
        assert "cc0" in lic or "public domain" in lic
        assert str(rule.get("card_image_author") or "").strip()
        sec = rule["sections"][0]
        sub_tag = sec["atom_query"]["fun_sub_tag"]
        assert len(fun_market_ids_for_sub_tag(sub_tag)) == expected_counts[slug]
        for venue in ("kalshi", "polymarket"):
            assert venue not in str(sec.get("note") or "").lower()
            assert venue not in str(rule.get("headline_predicate") or "").lower()

    # No other preview set changes stage under 321: A.
    for preview_slug in (
        "machinery-long-shots",
        "machinery-long-awaited",
        "machinery-space-race",
        "machinery-taylor-swift",
    ):
        assert load_machinery_definition(paths_by_slug[preview_slug])["stage"] == "preview"


@pytest.mark.asyncio
async def test_batch3_four_public_sets_build_with_parity_non_race_headlines_and_exclusions() -> None:
    db = {"events": [], "markets": _sample_batch3_markets(), "paired_sets": {}, "market_histories": {}}
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}

    # 1. How 2026 gets summed up
    s1_def = load_machinery_definition(paths_by_slug["machinery-2026-summed-up"])
    s1_prod = build_container_machinery_producer(s1_def)
    s1_res = await produce_container_machinery(db, s1_def, now=NOW)
    assert len(s1_res.members) == 9
    assert s1_res.machinery_card["stage"] == "public"
    assert s1_res.machinery_card["item_count"] == 9
    assert s1_res.machinery_card["image_url"] == s1_def["rule"]["card_image_url"]
    assert s1_res.title == (
        "Bad Bunny as Spotify's top artist is at 97%, "
        "with Grand Theft Auto VI for Game of the Year at 92%"
    )
    assert "board" not in s1_res.title.lower()
    assert ": " not in s1_res.title
    s1_fi = sanitize_discover_feed_item(compose_roundup_feed_item(s1_prod, s1_res))
    s1_cp = compose_roundup_container(s1_prod, s1_res)
    c_p, p_p = _compute_member_number_parity(s1_fi, s1_cp)
    assert c_p["passes"] is True and p_p["passes"] is True
    assert s1_fi["data"]["image_url"] == s1_def["rule"]["card_image_url"]

    # 2. Who gets cast, delayed, or cancelled (non-race headline; strips '?' from Deadpool outcome)
    s2_def = load_machinery_definition(paths_by_slug["machinery-cast-delayed-cancelled"])
    s2_prod = build_container_machinery_producer(s2_def)
    s2_res = await produce_container_machinery(db, s2_def, now=NOW)
    assert len(s2_res.members) == 9
    assert s2_res.machinery_card["stage"] == "public"
    assert "winner" not in s2_res.title.lower()
    assert "leads" not in s2_res.title.lower()
    assert "race" not in s2_res.title.lower()
    assert "board" not in s2_res.title.lower()
    assert "?" not in s2_res.title
    assert "topping Rotten Tomatoes" not in s2_res.title
    assert "in Avengers: Doomsday is at 97%" in s2_res.title
    assert "Dune: Part Three out-scoring Avengers on Rotten Tomatoes at 84%" in s2_res.title
    s2_fi = sanitize_discover_feed_item(compose_roundup_feed_item(s2_prod, s2_res))
    s2_cp = compose_roundup_container(s2_prod, s2_res)
    c_p, p_p = _compute_member_number_parity(s2_fi, s2_cp)
    assert c_p["passes"] is True and p_p["passes"] is True

    # 3. Who gets the stage and the cover (6 rows; Michelin excluded; non-race headline)
    s3_def = load_machinery_definition(paths_by_slug["machinery-stage-and-cover"])
    assert s3_def["name"] == "Who gets the stage and the cover"
    s3_prod = build_container_machinery_producer(s3_def)
    s3_res = await produce_container_machinery(db, s3_def, now=NOW)
    s3_ids = {m["id"] for m in s3_res.members}
    assert len(s3_ids) == 6
    assert s3_res.machinery_card["stage"] == "public"
    assert s3_ids.isdisjoint({67804475, 67804474, 67804472})
    assert "winner" not in s3_res.title.lower()
    assert "leads" not in s3_res.title.lower()
    assert "race" not in s3_res.title.lower()
    assert "board" not in s3_res.title.lower()
    assert ": " not in s3_res.title
    assert s3_res.title == (
        "Tame Impala headlining Coachella 2027 is at 99%, "
        "with Timothée Chalamet hosting SNL at 87%"
    )
    s3_fi = sanitize_discover_feed_item(compose_roundup_feed_item(s3_prod, s3_res))
    s3_cp = compose_roundup_container(s3_prod, s3_res)
    c_p, p_p = _compute_member_number_parity(s3_fi, s3_cp)
    assert c_p["passes"] is True and p_p["passes"] is True

    # 4. Elon Musk's wildest side quests (6 rows; second trillionaire excluded; per-row with-phrase)
    s4_def = load_machinery_definition(paths_by_slug["machinery-elon-musk-side-quests"])
    s4_prod = build_container_machinery_producer(s4_def)
    s4_res = await produce_container_machinery(db, s4_def, now=NOW)
    s4_ids = {m["id"] for m in s4_res.members}
    assert len(s4_ids) == 6
    assert s4_res.machinery_card["stage"] == "public"
    assert 52755535 not in s4_ids
    assert s4_res.title.startswith(
        "Visiting Mars in his lifetime is the likeliest Elon Musk side quest at 12%, with "
    )
    assert "with Buying " not in s4_res.title
    assert "with Cast " not in s4_res.title
    s4_fi = sanitize_discover_feed_item(compose_roundup_feed_item(s4_prod, s4_res))
    s4_cp = compose_roundup_container(s4_prod, s4_res)
    c_p, p_p = _compute_member_number_parity(s4_fi, s4_cp)
    assert c_p["passes"] is True and p_p["passes"] is True
    for fi in (s1_fi, s2_fi, s3_fi, s4_fi):
        assert all((s.get("data") or {}).get("image_url") is None for s in fi["data"].get("items") or ())


@pytest.mark.asyncio
async def test_musk_set_every_row_has_explicit_with_phrase_keeping_proper_nouns_capitalized() -> None:
    from app.utils.discover_fun_tags import fun_market_headline_with_phrase

    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    s4_def = load_machinery_definition(paths_by_slug["machinery-elon-musk-side-quests"])
    expected_with_phrases = {
        108218: "visiting Mars in his lifetime",
        109412: "buying Ryanair",
        109633: "being cast in the next Superman film",
        109316: "buying a major sports team before 2027",
        109490: "being out as Tesla CEO before 2027",
        109489: "Tesla Optimus released this year",
    }
    for mid, phrase in expected_with_phrases.items():
        assert (
            fun_market_headline_with_phrase(mid, sub_tag="batch3-elon-musk-side-quests")
            == phrase
        )
        # Put this row in second place and confirm the headline reads naturally after "with ".
        markets = _sample_batch3_markets()
        for m in markets:
            if m["id"] in expected_with_phrases:
                m["outcomes"][0]["probability"] = 0.01
        lead_id = 109412 if mid == 108218 else 108218
        for m in markets:
            if m["id"] == lead_id:
                m["outcomes"][0]["probability"] = 0.25
            elif m["id"] == mid:
                m["outcomes"][0]["probability"] = 0.10
        db = {"events": [], "markets": markets, "paired_sets": {}, "market_histories": {}}
        res = await produce_container_machinery(db, s4_def, now=NOW)
        assert f", with {phrase} at 10%" in res.title
