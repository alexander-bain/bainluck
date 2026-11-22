"""Tests for #12288 Item 4 row pictures and initials-in-circle fallback."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.utils.container_machinery import (
    SubjectArtResolver,
    discover_machinery_candidate_paths,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.discover_fun_tags import clear_fun_markets_cache
from app.utils.nation_flags import flag_url

NOW = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)

ROW_ART_ENABLED_SLUGS = (
    "machinery-golden-globes-2027",
    "machinery-google-year-in-search-2026",
    "machinery-2026-box-office-showdown",
    "machinery-pop-culture-oddities",
    "machinery-2026-summed-up",
    "machinery-cast-delayed-cancelled",
    "machinery-stage-and-cover",
)

ROW_ART_HIDDEN_SLUGS = (
    "machinery-ai-model-leaderboard-2026",
    "machinery-big-tech-deals-hardware",
)


def test_hide_row_art_turned_off_on_person_film_show_sets_and_kept_off_tech() -> None:
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    for slug in ROW_ART_ENABLED_SLUGS:
        defn = load_machinery_definition(paths_by_slug[slug])
        assert not defn["rule"].get("hide_row_art"), f"{slug} should allow row art"
    for slug in ROW_ART_HIDDEN_SLUGS:
        defn = load_machinery_definition(paths_by_slug[slug])
        assert defn["rule"].get("hide_row_art") is True, f"{slug} should stay hide_row_art=True"


def test_tmdb_vetted_portraits_posters_and_country_flags_resolve() -> None:
    resolver = SubjectArtResolver()
    for subject in (
        "Florence Pugh",
        "Kate O’Flynn",
        "David Harbour",
        "Beyoncé",
        "Olivia Colman",
        "Cillian Murphy",
        "Benedict Cumberbatch",
        "Sydney Sweeney",
        "Elon Musk",
        "MrBeast",
    ):
        art = resolver.resolve(subject, allow_team_lookup=False)
        assert art["url"] and "image.tmdb.org/t/p/" in art["url"], (subject, art)
        assert art["kind"] in {"person", "tmdb_headshot"}, (subject, art)

    for title in ("DTF St. Louis", "The Pitt", "Euphoria", "Avengers: Secret Wars", "Stranger Things"):
        art = resolver.resolve(title, allow_team_lookup=False)
        assert art["url"] and "image.tmdb.org/t/p/" in art["url"], (title, art)
        assert art["kind"] in {"film", "tmdb_poster"}, (title, art)

    # Erling Braut Haaland keeps the vetted Wikimedia portrait via alias.
    haaland = resolver.resolve("Erling Braut Haaland", allow_team_lookup=False)
    assert haaland["url"] and "wikimedia.org" in haaland["url"], haaland

    # Obsession (2026 horror film) stays omitted from vetted art and gets crisp initials.
    obsession = resolver.resolve("Obsession", allow_team_lookup=False)
    assert obsession["url"] is None
    assert obsession["kind"] == "monogram"
    assert obsession["initials"] == "OB"

    # Country flags resolve cleanly for major international markets.
    assert flag_url("China") == "https://flagcdn.com/w160/cn.png"
    for country in ("United States", "China", "India", "Russia", "United Kingdom", "France"):
        cart = resolver.resolve(country, allow_team_lookup=False)
        assert cart["kind"] == "flag", (country, cart)
        assert cart["url"] and "flagcdn.com/w160/" in cart["url"], (country, cart)


@pytest.mark.asyncio
async def test_partial_row_art_keeps_pictures_and_fills_initials_without_all_or_nothing() -> None:
    clear_fun_markets_cache()
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    defn = load_machinery_definition(paths_by_slug["machinery-pop-culture-oddities"])
    markets = [
        {
            "id": 67804457,
            "name": '"All I Want for Christmas Is You" Dec 19 Hot 100 rank',
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 1, "name": "Rank 1 to 2", "probability": 0.45}],
        },
        {
            "id": 108306,
            "name": "Beyonce next album genre?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 2, "name": "Rock", "probability": 0.40}],
        },
        {
            "id": 58903285,
            "name": "Turner Prize 2026 Winner?",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 3, "name": "Simeon Barclay", "probability": 0.35}],
        },
        {
            "id": 109309,
            "name": "Taylor Swift announces Taylor's Version?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 4, "name": "Yes", "probability": 0.30}, {"id": 5, "name": "No", "probability": 0.70}],
        },
        {
            "id": 67804475,
            "name": "NYC 2026 Michelin stars: Kabawa",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 6, "name": "Kabawa", "probability": 0.25}],
        },
        {
            "id": 108254,
            "name": "Time Person of the Decade?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "politics",
            "volume": 50000.0,
            "outcomes": [{"id": 7, "name": "Elon Musk", "probability": 0.80}],
        },
    ]
    res = await produce_container_machinery({"markets": markets, "teams": []}, defn, now=NOW)
    assert hasattr(res, "machinery_card"), res
    rows = res.machinery_card["rows"]
    assert len(rows) == 3
    by_mid = {int(r["market_id"]): r for r in rows}
    # Mariah Carey & Beyoncé keep their portraits instead of all-or-nothing stripping.
    assert "image.tmdb.org" in str(by_mid[67804457]["art"]["url"])
    assert "image.tmdb.org" in str(by_mid[108306]["art"]["url"])
    # Simeon Barclay has no vetted portrait and carries crisp monogram initials in the same slot.
    missing = by_mid[58903285]["art"]
    assert missing["url"] is None
    assert missing["kind"] == "monogram"
    assert missing["initials"] == "SB"
    assert missing["accent_color"].startswith("#")


@pytest.mark.asyncio
async def test_space_race_and_engaged_resolve_country_flags_and_couple_portraits() -> None:
    clear_fun_markets_cache()
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}

    space_defn = load_machinery_definition(paths_by_slug["machinery-space-race"])
    space_markets = [
        {
            "id": 108300,
            "name": "Blue Origin land on the moon before SpaceX?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "tech",
            "volume": 50000.0,
            "outcomes": [{"id": 11, "name": "Yes", "probability": 0.66}, {"id": 12, "name": "No", "probability": 0.34}],
        },
        {
            "id": 108247,
            "name": "Which country will be next to land humans on the Moon?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "tech",
            "volume": 50000.0,
            "outcomes": [{"id": 13, "name": "China", "probability": 0.57}, {"id": 14, "name": "United States", "probability": 0.43}],
        },
        {
            "id": 108236,
            "name": "Humanoid robot walks on Mars before a human?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "tech",
            "volume": 50000.0,
            "outcomes": [{"id": 15, "name": "Yes", "probability": 0.49}, {"id": 16, "name": "No", "probability": 0.51}],
        },
    ]
    space_res = await produce_container_machinery({"markets": space_markets, "teams": []}, space_defn, now=NOW)
    assert hasattr(space_res, "machinery_card"), space_res
    space_by_mid = {int(r["market_id"]): r for r in space_res.machinery_card["rows"]}
    assert space_by_mid[108247]["art"]["kind"] == "flag"
    assert space_by_mid[108247]["art"]["url"] == "https://flagcdn.com/w160/cn.png"
    assert space_by_mid[108300]["art"]["url"] is None
    assert space_by_mid[108300]["art"]["kind"] == "monogram"
    assert space_by_mid[108300]["art"]["initials"]

    engaged_defn = load_machinery_definition(paths_by_slug["machinery-who-gets-engaged"])
    engaged_markets = [
        {
            "id": 109618,
            "name": "Will Sydney Sweeney & Scooter Braun get engaged?",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "culture",
            "volume": 50000.0,
            "outcomes": [{"id": 21, "name": "Yes", "probability": 0.29}, {"id": 22, "name": "No", "probability": 0.71}],
        },
        {
            "id": 2519100,
            "name": "Will Puka Nacua & Sara Saffari get engaged?",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "culture",
            "volume": 50000.0,
            "outcomes": [{"id": 23, "name": "Yes", "probability": 0.25}, {"id": 24, "name": "No", "probability": 0.75}],
        },
        {
            "id": 109385,
            "name": "Will Timothee Chalamet & Kylie Jenner get engaged?",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "culture",
            "volume": 50000.0,
            "outcomes": [{"id": 25, "name": "Yes", "probability": 0.21}, {"id": 26, "name": "No", "probability": 0.79}],
        },
    ]
    eng_res = await produce_container_machinery({"markets": engaged_markets, "teams": []}, engaged_defn, now=NOW)
    assert hasattr(eng_res, "machinery_card"), eng_res
    eng_by_mid = {int(r["market_id"]): r for r in eng_res.machinery_card["rows"]}
    assert "image.tmdb.org" in str(eng_by_mid[109618]["art"]["url"])
    assert "image.tmdb.org" in str(eng_by_mid[109385]["art"]["url"])
    assert eng_by_mid[2519100]["art"]["url"] is None
    assert eng_by_mid[2519100]["art"]["kind"] == "monogram"
    assert eng_by_mid[2519100]["art"]["initials"]


@pytest.mark.asyncio
async def test_taylor_swift_uses_person_portrait_elon_skips_repeat_and_date_row_uses_subject_initials() -> None:
    clear_fun_markets_cache()
    resolver = SubjectArtResolver()
    ts_person = resolver.resolve("Taylor Swift", allow_team_lookup=False)
    assert ts_person["kind"] == "person"
    assert "image.tmdb.org" in str(ts_person["url"])
    ts_song = resolver.resolve("The Fate of Ophelia - Taylor Swift", allow_team_lookup=False)
    assert ts_song["kind"] == "song"
    assert "coverartarchive.org" in str(ts_song["url"])

    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    musk_defn = load_machinery_definition(paths_by_slug["machinery-elon-musk-side-quests"])
    musk_markets = [
        {
            "id": 108218,
            "name": "Will Elon Musk visit Mars in his lifetime?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "odd",
            "volume": 50000.0,
            "outcomes": [{"id": 31, "name": "Yes", "probability": 0.14}, {"id": 32, "name": "No", "probability": 0.86}],
        },
        {
            "id": 109412,
            "name": "Will Elon Musk buy Ryanair?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "business",
            "volume": 50000.0,
            "outcomes": [{"id": 33, "name": "Yes", "probability": 0.08}, {"id": 34, "name": "No", "probability": 0.92}],
        },
        {
            "id": 109633,
            "name": "Will Elon Musk be cast in Superman?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 35, "name": "Yes", "probability": 0.05}, {"id": 36, "name": "No", "probability": 0.95}],
        },
    ]
    musk_res = await produce_container_machinery({"markets": musk_markets, "teams": []}, musk_defn, now=NOW)
    assert hasattr(musk_res, "machinery_card"), musk_res
    assert all((r.get("art") or {}).get("url") is None for r in musk_res.machinery_card["rows"])

    summed_defn = load_machinery_definition(paths_by_slug["machinery-2026-summed-up"])
    summed_markets = [
        {
            "id": 109517,
            "name": "Top Spotify artist of 2026?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 41, "name": "Bad Bunny", "probability": 0.45}],
        },
        {
            "id": 109614,
            "name": "Game of the Year 2026?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 42, "name": "Grand Theft Auto VI", "probability": 0.35}],
        },
        {
            "id": 109527,
            "name": "When will Spotify Wrapped 2026 release?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 43, "name": "Before Dec 5, 2026", "probability": 0.55}],
        },
    ]
    summed_res = await produce_container_machinery({"markets": summed_markets, "teams": []}, summed_defn, now=NOW)
    assert hasattr(summed_res, "machinery_card"), summed_res
    s_by_mid = {int(r["market_id"]): r for r in summed_res.machinery_card["rows"]}
    assert s_by_mid[109527]["art"]["initials"] not in {"DEC", "JAN", "B2"}
    assert s_by_mid[109527]["art"]["initials"] == "SR"
